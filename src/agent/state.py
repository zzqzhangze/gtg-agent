from langgraph.graph.message import MessagesState


# 继承 MessagesState 后，账本天生自带一个 "messages" 列表，用来自动保存聊天记录
class SandboxAgentState(MessagesState):
    """
    智能体全局共享账本 (State)
    所有的节点 (Node) 都会接收这个账本，并返回需要更新的字段。
    """

    # 记录当前挂载的 WSL 沙箱 ID。
    # 如果是 None，说明当前没有开启任何沙箱。
    sandbox_id: str | None = None

    # 意图分析节点的分析结果。
    # True 表示大模型需要写代码，必须拉起沙箱；False 表示只是普通聊天，无需沙箱。
    needs_sandbox: bool | None = None
