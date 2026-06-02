import base64
import json
import os
from typing import Any
from deepagents import create_deep_agent
from langchain_core.messages import HumanMessage, SystemMessage
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


# ── 文件分析辅助函数 ──────────────────────────────────────────────────
_MIME_TYPE_MAP: dict[str, str] = {
    # data
    ".csv": "csv",
    ".xlsx": "xlsx",
    ".xls": "xls",
    ".json": "json",
    ".xml": "xml",
    # images
    ".png": "png",
    ".jpg": "jpg",
    ".jpeg": "jpeg",
    ".gif": "gif",
    ".svg": "svg",
    ".webp": "webp",
    # documents
    ".pdf": "pdf",
    ".md": "md",
    ".txt": "txt",
    ".log": "log",
    ".html": "html",
    ".htm": "html",
    # archives
    ".zip": "zip",
    ".gz": "gz",
    ".tar": "tar",
    ".gz2": "bz2",
    # code — Python
    ".py": "py",
    ".ipynb": "ipynb",
    ".pyx": "pyx",
    ".pyi": "pyi",
    # code — JavaScript / TypeScript / Web
    ".js": "js",
    ".jsx": "jsx",
    ".ts": "ts",
    ".tsx": "tsx",
    ".css": "css",
    ".scss": "scss",
    ".less": "less",
    ".vue": "vue",
    ".svelte": "svelte",
    # code — Shell / Config
    ".sh": "sh",
    ".bash": "bash",
    ".zsh": "zsh",
    ".yaml": "yaml",
    ".yml": "yml",
    ".toml": "toml",
    ".ini": "ini",
    ".cfg": "cfg",
    ".env": "env",
    ".dockerfile": "dockerfile",
    # code — Go / Rust / Java / C++
    ".go": "go",
    ".rs": "rs",
    ".java": "java",
    ".kt": "kt",
    ".rb": "rb",
    ".php": "php",
    ".swift": "swift",
    ".c": "c",
    ".cpp": "cpp",
    ".h": "h",
    ".hpp": "hpp",
    # code — other
    ".r": "r",
    ".sql": "sql",
    ".lua": "lua",
}


def _detect_mime_type(path: str) -> str:
    ext = os.path.splitext(path)[1].lower()
    return _MIME_TYPE_MAP.get(ext, "unknown")


def _generate_preview(sb, path: str, mime_type: str) -> str | None:
    """根据文件类型生成轻量文本预览（不读取大文件进 LLM）。"""
    try:
        # 代码文件类型（需要更详细的预览）
        code_types = {
            "py", "ipynb", "pyx", "pyi",
            "js", "jsx", "ts", "tsx", "css", "scss", "less", "vue", "svelte",
            "sh", "bash", "zsh", "yaml", "yml", "toml", "ini", "cfg", "env", "dockerfile",
            "go", "rs", "java", "kt", "rb", "php", "swift", "c", "cpp", "h", "hpp",
            "r", "sql", "lua",
        }
        text_types = {"csv", "json", "txt", "md", "xml", "log", "html"}

        if mime_type in text_types or mime_type in code_types:
            content = sb.read(path).decode("utf-8", errors="replace")
            lines = content.splitlines()
            total = len(lines)

            if mime_type in code_types and total > 10:
                # 代码文件：展示前 25 行 + 结构概要
                show_lines = min(total, 25)
                preview = "\n".join(lines[:show_lines])
                if total > show_lines:
                    preview += f"\n... ({total - show_lines} more lines)"

                # 提取结构信息帮助 LLM 判断
                func_count = sum(1 for l in lines if l.strip().startswith(("def ", "class ", "async def ", "fn ", "func ", "function ")))
                preview += f"\n\n[File: {total} lines, {func_count} function(s)/class(es)]"
            else:
                # 纯文本/数据：展示前 10 行
                show_lines = min(total, 10)
                preview = "\n".join(lines[:show_lines])
                if total > show_lines:
                    preview += f"\n... ({total - show_lines} more lines)"
                preview += f"\n\n[File: {total} lines total]"

            return preview

        if mime_type == "log":
            total = sb.run(f"wc -l < '{path}'", timeout=5).stdout.strip()
            errors = sb.run(f"grep -i -c error '{path}'", timeout=5).stdout.strip()
            warns = sb.run(f"grep -i -c warning '{path}'", timeout=5).stdout.strip()
            return f"Lines: {total}, Errors: {errors}, Warnings: {warns}"

        if mime_type == "html":
            title = sb.run(
                f"head -100 '{path}' | grep -o '<title>[^<]*</title>'",
                timeout=5,
            ).stdout.strip()
            return title or "[No title tag found]"

        if mime_type in ("png", "jpg", "jpeg", "gif"):
            raw = sb.read(path)
            b64 = base64.b64encode(raw).decode()
            # 只放前 200 chars 作为预览标记，不塞整个 base64 进 LLM
            return f"[Image: {mime_type.upper()}, {len(raw)} bytes, base64:{b64[:80]}...]"

        if mime_type in ("xlsx", "xls", "pdf", "zip"):
            return f"[Binary file: {mime_type.upper()}, cannot preview text]"

        return None
    except Exception as e:
        return f"[preview error: {e}]"


_ANALYZE_FILES_PROMPT = """You are a file analysis assistant. Below is the user's original request and the task type determined by intent analysis.

--- User Request ---
{user_request}

--- Task Type ---
{task_type}

--- Files Produced by AI ---
{file_details}

TASK TYPE SPECIFIC RULES:
- code_exec: Generated code files (.py, .js, .html, etc.) are HIGH value — they ARE the output the user asked for. Logs, temp files, and cache are LOW.
- data_analysis: Result files (charts, CSVs, reports, analysis notebooks) are HIGH value. Intermediate analysis scripts are LOW.
- multi_step: ALL generated files are HIGH value — complex projects produce multiple deliverables.
- chat/compute: Low value unless a file clearly represents a tangible deliverable.

For each file, decide:
1. **value**: "high" if this file IS what the user asked for, or is a key deliverable that directly satisfies the request. "low" if it's an intermediate/working artifact (temp script the user did NOT ask for, cache, config, log of intermediate steps).
2. **summary**: One-sentence Chinese description of what this file contains and why it matters (or why it's low value).

CRITICAL: Judge by INTENT, not by file extension. If the user asked for a Python script, a .py file IS high value. If they asked for data analysis, the report/CSV/chart IS high value. Always ask: "Does this file deliver what the user specifically asked for?"

Respond in this exact JSON format (NO markdown code fences, pure JSON only):
{{"files": [{{"path": "...", "value": "high|low", "summary": "..."}}]}}
"""


# ── 文件类型分类（用于预判价值） ─────────────────────────────────────
_CODE_EXTENSIONS = {
    "py", "ipynb", "pyx", "pyi",
    "js", "jsx", "ts", "tsx", "css", "scss", "less", "vue", "svelte",
    "sh", "bash", "zsh", "yaml", "yml", "toml", "ini", "cfg", "env", "dockerfile",
    "go", "rs", "java", "kt", "rb", "php", "swift", "c", "cpp", "h", "hpp",
    "r", "sql", "lua",
}
_DATA_EXTENSIONS = {"csv", "json", "xml", "xlsx", "xls"}
_IMAGE_EXTENSIONS = {"png", "jpg", "jpeg", "gif", "svg", "webp"}
_DOC_EXTENSIONS = {"md", "txt", "html", "log"}
_ARCHIVE_EXTENSIONS = {"zip", "gz", "tar", "bz2"}


def _classify_file_type(mime_type: str) -> str:
    """将 mime_type 归类为: code / data / image / doc / archive / binary / unknown"""
    if mime_type in _CODE_EXTENSIONS:
        return "code"
    if mime_type in _DATA_EXTENSIONS:
        return "data"
    if mime_type in _IMAGE_EXTENSIONS:
        return "image"
    if mime_type in _DOC_EXTENSIONS:
        return "doc"
    if mime_type in _ARCHIVE_EXTENSIONS:
        return "archive"
    if mime_type == "pdf":
        return "binary"
    return "unknown"


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

        # ── Skills loading ──
        skills_list: list[dict[str, Any]] = []
        try:
            from src.skills.loader import discover_skills, upload_skills_to_sandbox

            skills_list = discover_skills()
            if skills_list:
                upload_skills_to_sandbox(backend, skills_list)
                skill_names = [s["name"] for s in skills_list]
                print(f"[Skills] Loaded {len(skills_list)} skills: {skill_names}")
        except Exception as e:
            print(f"[Skills] Failed to load skills: {e}")

        # 组装超级机器人
        agent = create_deep_agent(
            model=llm,
            backend=backend,
            skills=skills_list or None,
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
    作用：扫描沙箱输出目录，识别每个文件的路径和类型，返回结构化列表。
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

    # 解析输出，构建结构化结果
    raw_paths = [line.strip() for line in result.stdout.split("\n") if line.strip()]
    if not raw_paths:
        print("[文件发现] 未发现新文件。")
        return {"output_files": []}

    files = []
    for path in raw_paths:
        files.append({
            "path": path,
            "mime_type": _detect_mime_type(path),
        })

    print(f"[文件发现] 发现 {len(files)} 个文件:")
    for f in files:
        print(f"  - {f['path']} ({f['mime_type']})")

    return {"output_files": files}


def analyze_output_files(state: SandboxAgentState) -> dict[str, Any]:
    """
    【车间 7：智能分析输出文件】
    作用：读取每个文件的预览，用 LLM 判断价值并生成中文摘要。
    高价值文件标记后由 download_files 下载，低价值仅列路径。
    """
    output_files: list[dict[str, Any]] = state.get("output_files", [])
    if not output_files or not state.get("sandbox_id"):
        return {}

    client = SandboxClient()
    sb = client.get_sandbox(name=state["sandbox_id"])

    # 为每个文件生成预览
    print("[文件分析] 正在分析输出文件...")
    preview_lines = []
    for f in output_files:
        f["size"] = _get_file_size(sb, f["path"]) if "size" not in f else f["size"]
        preview = _generate_preview(sb, f["path"], f["mime_type"])
        if preview:
            f["preview"] = preview
        name = os.path.basename(f["path"])
        preview_lines.append(
            f"File: {name} | type={f['mime_type']} | size={f.get('size', '?')}B"
        )
        if preview:
            preview_lines.append(f"Preview:\n{preview}")
        preview_lines.append("")

    # 预分类：按 task_type + 文件类型设定默认价值
    task_type = state.get("task_type", "unknown")
    for f in output_files:
        ext_type = _classify_file_type(f["mime_type"])
        if task_type == "code_exec":
            # code_exec：代码/文档/数据/图片都是潜在交付物
            if ext_type in ("code", "data", "image", "doc"):
                f["value"] = "high"
                f["summary"] = "生成的交付文件，是本次任务的直接产出"
            else:
                f["value"] = "high"  # 保险：unknown 默认下载
                f["summary"] = "任务产出文件"
        elif task_type == "data_analysis":
            # data_analysis：数据/图表/报告是高价值，脚本是中间产物
            if ext_type in ("data", "image", "doc"):
                f["value"] = "high"
                f["summary"] = "分析结果文件"
            else:
                f["value"] = "low"
                f["summary"] = "中间分析脚本，结果在数据/报告中"
        elif task_type == "multi_step":
            # multi_step：所有文件都是交付物
            f["value"] = "high"
            f["summary"] = "多步骤任务的产出文件"
        else:
            # chat/compute：默认安全处理
            f["value"] = "high"
            f["summary"] = "文件产出"

    # 提取用户意图，让 LLM 按需求而非文件类型做判断
    messages = state.get("messages", [])
    user_request = messages[-1].content if messages else "(unknown)"
    task_type = state.get("task_type", "unknown")
    file_details = "\n".join(preview_lines)

    prompt = _ANALYZE_FILES_PROMPT.format(
        user_request=user_request,
        task_type=task_type,
        file_details=file_details,
    )

    # 构造 LLM 请求
    try:
        llm = ChatOpenAIWithReasoning(
            base_url=settings.openai_api_base,
            api_key=settings.openai_api_key,
            model=settings.model_name,
            temperature=0.1,
        )
        response = llm.invoke([HumanMessage(content=prompt)])

        result = _parse_intent_json(response.content)
        print(f"[文件分析] LLM 判断: {result}")
        if result and "files" in result:
            llm_judgments = {f["path"]: f for f in result["files"]}
            for f in output_files:
                judgement = llm_judgments.get(f["path"])
                if judgement:
                    f["value"] = judgement.get("value", "high")
                    f["summary"] = judgement.get("summary", "")

    except Exception as e:
        print(f"[文件分析] ⚠️ LLM 分析失败 ({type(e).__name__})，全部文件默认下载")
        for f in output_files:
            f.setdefault("value", "high")
            f.setdefault("summary", "")

    # 打印分析结果
    high_count = sum(1 for f in output_files if f.get("value") == "high")
    low_count = sum(1 for f in output_files if f.get("value") != "high")
    print(f"[文件分析] 完成: {high_count} 个高价值, {low_count} 个低价值")
    for f in output_files:
        tag = "📦" if f.get("value") == "high" else "🗑️"
        print(f"  {tag} {os.path.basename(f['path'])} — {f.get('summary', '')}")

    return {"output_files": output_files}


def _get_file_size(sb, path: str) -> int:
    """获取沙箱内文件大小（字节）。"""
    try:
        r = sb.run(f"stat -c '%s' '{path}' 2>/dev/null || echo 0", timeout=5)
        return int(r.stdout.strip() or 0)
    except Exception:
        return 0


def download_files(state: SandboxAgentState) -> dict[str, Any]:
    """
    【车间 8：文件下载】
    作用：只下载高价值文件到本地 downloads/ 目录，低价值仅打印路径。
    返回：记录下载结果到 downloaded_paths 字段。
    """
    output_files: list[dict[str, Any]] = state.get("output_files", [])
    if not output_files:
        print("[文件下载] 没有需要下载的文件，跳过。")
        return {"downloaded_paths": []}

    if not state.get("sandbox_id"):
        print("[文件下载] 错误：没有可用的沙箱。")
        return {"downloaded_paths": []}

    client = SandboxClient()
    sb = client.get_sandbox(name=state["sandbox_id"])

    # 使用 session_id 隔离下载目录，回退到 "default"
    session_id = state.get("session_id", "default")
    download_dir = os.path.join(os.getcwd(), "downloads", session_id)
    os.makedirs(download_dir, exist_ok=True)

    high_value = [f for f in output_files if f.get("value") == "high"]
    low_value = [f for f in output_files if f.get("value") != "high"]

    downloaded = []
    for f in high_value:
        sandbox_path = f["path"]
        basename = os.path.basename(sandbox_path)
        local_path = os.path.join(download_dir, basename)

        print(f"[文件下载] 📦 {basename} → {local_path}")
        content = sb.read(sandbox_path)

        # 文件名去重：如果已存在，加数字后缀
        counter = 1
        orig = local_path
        while os.path.exists(local_path):
            name, ext = os.path.splitext(orig)
            local_path = f"{name}_{counter}{ext}"
            counter += 1

        with open(local_path, "wb") as f_out:
            f_out.write(content)

        file_size = os.path.getsize(local_path)

        downloaded.append({
            "sandbox": sandbox_path,
            "local": local_path,
            "size": file_size,
            "mime_type": f.get("mime_type", "application/octet-stream"),
            "summary": f.get("summary", ""),
        })

    # 打印结果摘要
    print(f"\n{'=' * 48}")
    if downloaded:
        print(f"  ✅ 已下载 {len(downloaded)} 个文件：")
        for d in downloaded:
            print(f"     📄 {os.path.basename(d['sandbox'])} → {d['local']} ({d['size']} bytes)")
            if d["summary"]:
                print(f"        {d['summary']}")
    if low_value:
        print(f"  🗑️ 跳过 {len(low_value)} 个低价值文件：")
        for f in low_value:
            print(f"     - {os.path.basename(f['path'])} ({f.get('summary', '中间文件，无需下载')})")
    print(f"{'=' * 48}\n")

    return {"downloaded_paths": downloaded}
