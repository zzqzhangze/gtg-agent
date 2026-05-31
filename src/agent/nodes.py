import json
import os
from typing import Any
from deepagents import create_deep_agent
from langgraph.checkpoint.memory import MemorySaver

from src.config import settings
from src.llm import ChatOpenAIWithReasoning
from src.sandbox.client import SandboxClient
from src.sandbox.backend import LangSmithBackend
from src.agent.state import SandboxAgentState

TEMPLATE_FALLBACK = "python-sandbox"

# ── LLM 意图分析系统提示词 ────────────────────────────────────────────
_INTENT_SYSTEM_PROMPT = """You are an intelligent task intent analyzer. Classify the user's last message into one of these task types:

- chat: Pure conversation, greetings, casual talk. No computation needed.
- compute: Simple calculation, math, reasoning that LLM can handle directly without sandbox.
- code_exec: User needs code to be written and executed. No file upload needed.
- data_analysis: User uploaded files and needs analysis. Requires sandbox + files.
- multi_step: Complex project requiring multiple iterations (web app, multi-file project, etc).

Sandbox templates (only relevant if sandbox is needed):
- python-sandbox: General Python coding tasks
- data-analysis: Data analysis with pandas/numpy/matplotlib
- node-sandbox: Node.js/JavaScript/TypeScript tasks

Respond in JSON format only (no markdown, no code fences):
{
    "task_type": "chat|compute|code_exec|data_analysis|multi_step",
    "reasoning": "Brief explanation in Chinese of why this classification",
    "suggested_template": "template_name or null if no sandbox needed",
    "needs_sandbox": true or false
}

Examples:
User: "你好" -> {"task_type": "chat", "reasoning": "纯问候，无需计算或执行", "suggested_template": null, "needs_sandbox": false}
User: "25 * 48 等于多少" -> {"task_type": "compute", "reasoning": "简单数学计算，LLM 可直接回答", "suggested_template": null, "needs_sandbox": false}
User: "用Python打印斐波那契数列前20项" -> {"task_type": "code_exec", "reasoning": "需要写代码并执行验证结果", "suggested_template": "python-sandbox", "needs_sandbox": true}
User: "帮我写一个完整的博客网站" -> {"task_type": "multi_step", "reasoning": "复杂项目需要多轮迭代开发", "suggested_template": "node-sandbox", "needs_sandbox": true}
User: "分析这个CSV" with uploaded files -> {"task_type": "data_analysis", "reasoning": "需要读取上传的文件进行数据分析", "suggested_template": "data-analysis", "needs_sandbox": true}
"""


def _parse_intent_json(content: str) -> dict[str, Any] | None:
    """从 LLM 响应中提取 JSON，兼容可能的 markdown 代码围栏。"""
    text = content.strip()
    # 移除 markdown 代码围栏
    if text.startswith("```"):
        lines = text.splitlines()
        # 去掉第一行 ```xxx 和最后一行 ```
        text = "\n".join(lines[1:])
        if text.endswith("```"):
            text = text[:-3].strip()
        elif text.endswith("``"):
            text = text[:-2].strip()
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        return None


def analyze_intent(state: SandboxAgentState) -> dict[str, Any]:
    """
    【车间 1：意图分析】
    作用：用 LLM 分析用户意图，智能判断是否需要沙箱以及使用哪种模板。
    LLM 调用失败时自动回退到关键词匹配。
    返回：更新账本上的 task_type, intent_reasoning, suggested_template, needs_sandbox。
    """
    last_message = state["messages"][-1].content
    print(f"\n[意图分析] 收到用户提问: '{last_message}'")

    # 检测是否有待上传的文件（影响意图判断）
    uploaded_files = state.get("input_files", [])
    file_context = f"\n(用户已上传文件: {uploaded_files})" if uploaded_files else ""

    try:
        llm = ChatOpenAIWithReasoning(
            base_url=settings.openai_api_base,
            api_key=settings.openai_api_key,
            model=settings.model_name,
            temperature=0.1,
        )

        from langchain_core.messages import HumanMessage, SystemMessage

        response = llm.invoke([
            SystemMessage(content=_INTENT_SYSTEM_PROMPT),
            HumanMessage(content=f"用户消息: {last_message}{file_context}"),
        ])

        parsed = _parse_intent_json(response.content)
        if parsed is None:
            raise ValueError(f"LLM 返回无法解析: {response.content[:200]}")

        task_type = parsed.get("task_type", "chat")
        reasoning = parsed.get("reasoning", "")
        suggested_template = parsed.get("suggested_template")
        needs_sandbox = parsed.get("needs_sandbox", False)

        # 校验 task_type 合法性
        valid_types = {"chat", "compute", "code_exec", "data_analysis", "multi_step"}
        if task_type not in valid_types:
            print(f"[意图分析] ⚠️ LLM 返回未知 task_type={task_type}，回退到 chat")
            task_type, needs_sandbox = "chat", False

        print(f"[意图分析] 🤖 LLM 分类: {task_type}")
        if reasoning:
            print(f"[意图分析]   └─ 推理: {reasoning}")
        if suggested_template:
            print(f"[意图分析]   └─ 模板: {suggested_template}")
        return {
            "task_type": task_type,
            "intent_reasoning": reasoning,
            "suggested_template": suggested_template,
            "needs_sandbox": needs_sandbox,
        }

    except Exception as e:
        print(f"[意图分析] ⚠️ LLM 分析失败 ({type(e).__name__}: {e})")
        print("[意图分析]   └─ 回退到关键词匹配模式")

        # Fallback: keyword matching
        keywords = [
            "跑", "执行", "代码", "python", "sh", "cmd",
            "打印", "run", "exec", "分析", "统计", "计算",
        ]
        if any(kw in last_message.lower() for kw in keywords):
            print("[意图分析] 🔍 关键词匹配 → code_exec")
            return {
                "task_type": "code_exec",
                "intent_reasoning": "关键词匹配（LLM fallback）",
                "suggested_template": "python-sandbox",
                "needs_sandbox": True,
            }
        print("[意图分析] 📝 无关键词匹配 → chat")
        return {
            "task_type": "chat",
            "intent_reasoning": "关键词无匹配（LLM fallback）",
            "suggested_template": None,
            "needs_sandbox": False,
        }


def create_sandbox(state: SandboxAgentState) -> dict[str, Any]:
    """
    【车间 2：拉起沙箱】
    作用：启动一个 Docker 容器作为代码运行环境。
    模板名优先使用 state.suggested_template（由 analyze_intent 提供），
    未指定时回退到 TEMPLATE_FALLBACK。
    返回：将成功创建的沙箱 ID 写回账本。
    """
    client = SandboxClient()
    template = state.get("suggested_template") or TEMPLATE_FALLBACK
    print(f"正在创建隔离沙箱环境 (模板: {template})...")

    sb = client.create_sandbox(
        template_name=template,
        timeout=settings.sandbox_lifetime_seconds,
    )

    # 健康检查：尝试在沙箱里打印 ready，确保它真的活过来了
    result = sb.run("echo ready", timeout=5)
    if result.exit_code != 0:
        raise RuntimeError("沙箱健康检查失败！")

    print(f"沙箱准备就绪: {sb.name}")
    return {"sandbox_id": sb.name}


def run_agent(state: SandboxAgentState) -> dict[str, Any]:
    """
    【车间 3：智能体核心大脑】
    作用：将大模型与沙箱工具结合。如果是复杂任务，让它自己写代码并去沙箱运行；如果是简单任务，直接回答。
    返回：把大模型的最终回答追加到账本的 messages 列表里。
    """
    # 初始化 LLM（通过 settings 读取配置，支持任意 OpenAI 兼容服务）
    llm = ChatOpenAIWithReasoning(
        base_url=settings.openai_api_base,
        api_key=settings.openai_api_key,
        model=settings.model_name,
        temperature=0.1
    )

    # 路线 A：如果账本上有 sandbox_id，说明前方已经为它准备好了沙箱
    if state.get("sandbox_id"):
        client = SandboxClient()
        sb = client.get_sandbox(name=state["sandbox_id"])
        backend = LangSmithBackend(sb)  # 给大模型装上"沙箱机械臂"

        # 组装超级机器人
        agent = create_deep_agent(
            model=llm,
            backend=backend,
            system_prompt=(
                "You are a helpful coding assistant with filesystem access via a sandbox.\n\n"
                "OUTPUT FILES:\n"
                "- User's uploaded files are at /workspace/input/\n"
                "- ALWAYS save all generated output files to /workspace/output/\n"
                "- The system will automatically deliver /workspace/output/ files to the user"
            ),
            checkpointer=MemorySaver(),  # 给它记忆功能
        )

        # 让机器人开始干活（这步是自动死循环，直到任务成功才会退出）
        result = agent.invoke(
            {"messages": state["messages"]},
            config={"configurable": {"thread_id": state["sandbox_id"]}},
        )
        return {"messages": result["messages"]}

    # 路线 B：如果账本上没有沙箱，说明只是简单问候，直接盲答
    else:
        print("[Agent 执行] 检测到无沙箱模式，正在以纯文本直接回复...")
        response = llm.invoke(state["messages"])
        return {"messages": [response]}


def cleanup_sandbox(state: SandboxAgentState) -> dict[str, Any]:
    """
    【车间 4：打扫战场】
    作用：无论是正常结束还是中途报错，最终都会流经这里，负责强制删除 Docker 容器，防止内存泄露。
    返回：把账本上的 sandbox_id 清空。
    """
    if state.get("sandbox_id"):
        print(f"正在清理并销毁沙箱: {state['sandbox_id']}...")
        client = SandboxClient()
        try:
            client.delete_sandbox(state["sandbox_id"])
            print("沙箱已彻底删除，内存已释放。")
        except Exception as e:
            print(f"警告: 沙箱删除失败: {e}")
    else:
        print("[生命周期] 检查完毕：本次会话未启动沙箱，无需清理。")

    return {"sandbox_id": None}


def upload_files(state: SandboxAgentState) -> dict[str, Any]:
    """
    【车间 5：文件上传】
    作用：将 state.input_files 中指定的本地文件上传到沙箱内的 /workspace/input/ 目录。
    返回：更新账本上的 sandbox_id（不变），以及 uploaded_paths 记录映射关系。
    """
    input_files = state.get("input_files", [])
    if not input_files:
        print("[文件上传] 没有需要上传的文件，跳过。")
        return {"uploaded_paths": []}

    if not state.get("sandbox_id"):
        print("[文件上传] 错误：没有可用的沙箱。")
        return {"uploaded_paths": []}

    client = SandboxClient()
    sb = client.get_sandbox(name=state["sandbox_id"])
    uploaded = []

    for local_path in input_files:
        if not os.path.isfile(local_path):
            print(f"[文件上传] 警告：本地文件不存在，跳过: {local_path}")
            continue

        basename = os.path.basename(local_path)
        sandbox_path = f"/workspace/input/{basename}"
        print(f"[文件上传] {local_path} → 沙箱:{sandbox_path}")

        with open(local_path, "rb") as f:
            sb.write(sandbox_path, f.read())

        uploaded.append({"local": local_path, "sandbox": sandbox_path})

    print(f"[文件上传] 完成，共上传 {len(uploaded)} 个文件。")
    return {"uploaded_paths": uploaded}


def detect_output_files(state: SandboxAgentState) -> dict[str, Any]:
    """
    【车间 6：自动发现沙箱输出文件】
    作用：DeepAgent 在沙箱内执行完代码后，自动扫描 /workspace/ 下新产生的文件
          （排除用户上传的 /workspace/input/ 目录），填充 state.output_files。
    这样智能体不需要特意声明它创建了哪些文件——框架自己感知。
    """
    if not state.get("sandbox_id"):
        print("[文件发现] 没有可用沙箱，跳过。")
        return {"output_files": []}

    client = SandboxClient()
    sb = client.get_sandbox(name=state["sandbox_id"])

    # 只扫 agent 输出目录（system_prompt 已告知 agent 存到 /workspace/output/）
    # 附加扫 workspace 根目录（非递归，仅常见输出格式，防 agent 未遵循指引）
    print("[文件发现] 扫描沙箱查找输出文件...")
    result = sb.run(
        "find /workspace/output -type f 2>/dev/null; "
        "find /workspace -maxdepth 1 -type f "
        "\\( -name '*.csv' -o -name '*.json' -o -name '*.pdf' "
        "-o -name '*.png' -o -name '*.jpg' -o -name '*.jpeg' "
        "-o -name '*.html' -o -name '*.xlsx' -o -name '*.xls' "
        "-o -name '*.md' -o -name '*.txt' -o -name '*.zip' "
        "-o -name '*.svg' -o -name '*.gif' -o -name '*.log' "
        "\\) ! -path '/workspace/input/*' 2>/dev/null || true",
        timeout=settings.sandbox_command_timeout_seconds,
    )

    if result.exit_code != 0:
        print(f"[文件发现] 扫描失败 (exit={result.exit_code}): {result.stderr}")
        return {"output_files": []}

    # 解析输出：每行一个文件路径
    files = [line.strip() for line in result.stdout.split("\n") if line.strip()]
    if not files:
        print("[文件发现] 未发现新文件。")
        return {"output_files": []}

    print(f"[文件发现] 发现 {len(files)} 个文件:")
    for f in files:
        print(f"  - {f}")

    return {"output_files": files}


def download_files(state: SandboxAgentState) -> dict[str, Any]:
    """
    【车间 6：文件下载】
    作用：将沙箱内 output_files 指定的文件下载到本地 downloads/ 目录。
    返回：记录下载结果到 downloaded_paths 字段。
    """
    output_files = state.get("output_files", [])
    if not output_files:
        print("[文件下载] 没有需要下载的文件，跳过。")
        return {"downloaded_paths": []}

    if not state.get("sandbox_id"):
        print("[文件下载] 错误：没有可用的沙箱。")
        return {"downloaded_paths": []}

    client = SandboxClient()
    sb = client.get_sandbox(name=state["sandbox_id"])

    # 确保本地下载目录存在
    download_dir = os.path.join(os.getcwd(), "downloads")
    os.makedirs(download_dir, exist_ok=True)

    downloaded = []
    for sandbox_path in output_files:
        basename = os.path.basename(sandbox_path)
        local_path = os.path.join(download_dir, basename)

        print(f"[文件下载] 沙箱:{sandbox_path} → {local_path}")

        content = sb.read(sandbox_path)

        with open(local_path, "wb") as f:
            f.write(content)

        downloaded.append({"sandbox": sandbox_path, "local": local_path})

    # 打印清晰的结果摘要，隐藏沙箱实现细节
    print(f"\n{'=' * 48}")
    print(f"  ✅ 处理完成，共 {len(downloaded)} 个文件已就绪：")
    for d in downloaded:
        print(f"     📄 {os.path.basename(d['sandbox'])} → {d['local']}")
    print(f"{'=' * 48}\n")
    return {"downloaded_paths": downloaded}
