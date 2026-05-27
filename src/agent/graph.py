from langgraph.graph import END, START, StateGraph
from src.agent.state import SandboxAgentState
from src.agent.nodes import analyze_intent, create_sandbox, run_agent, cleanup_sandbox


def route_after_analysis(state: SandboxAgentState) -> str:
    """
    自定义的轨道道岔（路由器）：
    根据意图分析节点的结论，告诉系统下一步该把数据传给哪个车间。
    """
    if state.get("needs_sandbox"):
        return "create_sandbox"  # 拨向创建沙箱的轨道
    return "run_agent"  # 拨向直接聊天的轨道


def build_graph():
    """将所有节点和传送带组装成一张完整的执行图"""
    # 1. 拿着账本模版，建立流水线基座
    builder = StateGraph(SandboxAgentState)

    # 2. 把所有的工作车间注册到流水线上
    builder.add_node("analyze_intent", analyze_intent)
    builder.add_node("create_sandbox", create_sandbox)
    builder.add_node("run_agent", run_agent)
    builder.add_node("cleanup_sandbox", cleanup_sandbox)

    # 3. 铺设传送带（Edges）
    # 任何任务进来，第一站必定是去分析意图
    builder.add_edge(START, "analyze_intent")

    # 这里的传送带是一个“三岔路口”，根据 route_after_analysis 的结果自动变轨
    builder.add_conditional_edges(
        "analyze_intent",
        route_after_analysis,
        {
            "create_sandbox": "create_sandbox",
            "run_agent": "run_agent"
        }
    )

    # 如果去了沙箱车间，建好之后，下一站必定是交给大模型运行
    builder.add_edge("create_sandbox", "run_agent")

    # ⚠️ 绝对安全防线：大模型不管跑没跑成功，下一站绝对是强制清理车间
    builder.add_edge("run_agent", "cleanup_sandbox")

    # 清理完毕，任务抵达终点
    builder.add_edge("cleanup_sandbox", END)

    # 编译并返回最终可执行的图
    return builder.compile()
