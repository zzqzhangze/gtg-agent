from langgraph.graph import END, START, StateGraph
from src.agent.state import SandboxAgentState
from src.agent.nodes import (
    analyze_intent,
    analyze_output_files,
    create_sandbox,
    upload_files,
    run_agent,
    run_agent_with_mcp,
    detect_output_files,
    download_files,
    cleanup_sandbox,
)


def route_after_run_agent(state: SandboxAgentState) -> str:
    """
    run_agent 之后的路由器：
    如果有沙箱 → 继续走文件发现/分析/下载流程
    没有沙箱（chat/compute）→ 直接跳到清理（实际为无操作，但不中断图流程）
    """
    if state.get("sandbox_id"):
        return "detect_output_files"
    return "cleanup_sandbox"


def route_after_analysis(state: SandboxAgentState) -> str:
    """
    自定义的轨道道岔（路由器）：
    根据 task_type 决定下一步路线。
    chat / compute → 直接 LLM 回复（无需沙箱，无工具）
    tool_task → MCP 工具调用（无需沙箱，有工具）
    code_exec / data_analysis / multi_step → 创建沙箱
    """
    task_type = state.get("task_type", "chat")
    sandbox_types = {"code_exec", "data_analysis", "multi_step"}
    if task_type == "tool_task":
        return "run_agent_with_mcp"
    if task_type in sandbox_types:
        return "create_sandbox"  # 拨向创建沙箱的轨道
    return "run_agent"  # 拨向直接聊天的轨道


def build_graph(*, checkpointer=None):
    """将所有节点和传送带组装成一张完整的执行图

    Args:
        checkpointer: 可选，LangGraph 的 Checkpointer 实例（如 SqliteSaver），
                      用于持久化对话状态。为 None 时保持现有行为（无持久化）。
    """
    # 1. 拿着账本模版，建立流水线基座
    builder = StateGraph(SandboxAgentState)

    # 2. 把所有的工作车间注册到流水线上
    builder.add_node("analyze_intent", analyze_intent)
    builder.add_node("create_sandbox", create_sandbox)
    builder.add_node("upload_files", upload_files)
    builder.add_node("run_agent", run_agent)
    builder.add_node("run_agent_with_mcp", run_agent_with_mcp)
    builder.add_node("detect_output_files", detect_output_files)
    builder.add_node("analyze_output_files", analyze_output_files)
    builder.add_node("download_files", download_files)
    builder.add_node("cleanup_sandbox", cleanup_sandbox)

    # 3. 铺设传送带（Edges）
    # 任何任务进来，第一站必定是去分析意图
    builder.add_edge(START, "analyze_intent")

    # 这里的传送带是一个"三岔路口"，根据 route_after_analysis 的结果自动变轨
    builder.add_conditional_edges(
        "analyze_intent",
        route_after_analysis,
        {
            "create_sandbox": "create_sandbox",
            "run_agent": "run_agent",
            "run_agent_with_mcp": "run_agent_with_mcp",
        }
    )

    # 如果去了沙箱车间，建好之后先上传用户文件
    builder.add_edge("create_sandbox", "upload_files")

    # 文件上传完，再交给大模型运行
    builder.add_edge("upload_files", "run_agent")

    # MCP 工具执行完，直接走清理（无沙箱，无需文件发现）
    builder.add_edge("run_agent_with_mcp", "cleanup_sandbox")

    # 大模型跑完，有沙箱则自动发现输出文件，无沙箱（chat/compute）跳过文件步骤
    builder.add_conditional_edges(
        "run_agent",
        route_after_run_agent,
        {
            "detect_output_files": "detect_output_files",
            "cleanup_sandbox": "cleanup_sandbox",
        }
    )

    # 发现完文件，先智能分析（预览+价值判断+摘要），再下载
    builder.add_edge("detect_output_files", "analyze_output_files")

    # 分析完文件，下载回本地（仅高价值文件）
    builder.add_edge("analyze_output_files", "download_files")

    # ⚠️ 绝对安全防线：下载完成后强制清理沙箱
    builder.add_edge("download_files", "cleanup_sandbox")

    # 清理完毕，任务抵达终点
    builder.add_edge("cleanup_sandbox", END)

    # 编译并返回最终可执行的图
    return builder.compile(checkpointer=checkpointer)
