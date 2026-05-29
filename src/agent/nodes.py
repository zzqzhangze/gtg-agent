import os
from typing import Any
from langchain_openai import ChatOpenAI
from deepagents import create_deep_agent
from langgraph.checkpoint.memory import MemorySaver

from src.config import settings
from src.sandbox.client import SandboxClient
from src.sandbox.backend import LangSmithBackend
from src.agent.state import SandboxAgentState

TEMPLATE_NAME = "python-sandbox"


def analyze_intent(state: SandboxAgentState) -> dict[str, Any]:
    """
    【车间 1：意图分析】
    作用：充当门卫，拦截并分析用户的最后一句话，决定后续走哪条路线。
    返回：更新账本上的 needs_sandbox 字段。
    """
    # 提取用户最新的一条消息
    last_message = state["messages"][-1].content
    print(f"\n[意图分析] 收到用户提问: '{last_message}'")

    # 简单的关键词匹配逻辑（如果未来换了强大的大模型，可以改成让大模型来判断）
    keywords = ["跑", "执行", "代码", "python", "sh", "cmd", "打印", "run", "exec"]
    if any(kw in last_message.lower() for kw in keywords):
        print("[意图分析] 🔍 决定【启动】沙箱。")
        return {"needs_sandbox": True}

    print("[意图分析] 📝 纯聊天意图，决定【跳过】沙箱。")
    return {"needs_sandbox": False}


def create_sandbox(state: SandboxAgentState) -> dict[str, Any]:
    """
    【车间 2：拉起沙箱】
    作用：向 WSL 发送指令，启动一个全新的 Docker 容器作为代码运行环境。
    返回：将成功创建的沙箱 ID 写回账本。
    """
    client = SandboxClient()
    print("正在创建隔离沙箱环境...")

    # timeout=3600 表示允许这个沙箱存活 1 小时，防止大模型思考太久导致沙箱被系统自动干掉
    sb = client.create_sandbox(template_name=TEMPLATE_NAME, timeout=3600)

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
    llm = ChatOpenAI(
        base_url=settings.openai_api_base,
        api_key=settings.openai_api_key,
        model=settings.model_name,
        temperature=0.1
    )

    # 路线 A：如果账本上有 sandbox_id，说明前方已经为它准备好了沙箱
    if state.get("sandbox_id"):
        client = SandboxClient()
        sb = client.get_sandbox(name=state["sandbox_id"])
        backend = LangSmithBackend(sb)  # 给大模型装上“沙箱机械臂”

        # 组装超级机器人
        agent = create_deep_agent(
            model=llm,
            backend=backend,
            system_prompt="You are a helpful coding assistant with filesystem access via a sandbox.",
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

    print(f"[文件下载] 完成，共下载 {len(downloaded)} 个文件。")
    return {"downloaded_paths": downloaded}
