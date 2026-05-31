from typing import TypedDict

from langgraph.graph.message import MessagesState


class OutputFile(TypedDict, total=False):
    """沙箱输出文件的结构化信息。"""
    path: str          # 文件在沙箱内的绝对路径
    mime_type: str     # MIME 类型（如 text/plain, image/png, application/pdf）
    size: int          # 文件大小（字节）
    preview: str       # 预览内容（文本预览/截取/摘要）
    value: str         # LLM 价值判断: "high" | "low"
    summary: str       # 中文摘要（给用户看）


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
    # 新代码应优先使用 task_type 字段判断，此字段保留向后兼容。
    needs_sandbox: bool | None = None

    # LLM 意图分析结果：任务类型分类。
    # "chat" | "compute" | "code_exec" | "data_analysis" | "multi_step"
    task_type: str | None = None

    # LLM 意图分析的推理过程（供调试和日志使用）。
    intent_reasoning: str | None = None

    # LLM 建议的沙箱模板名（如 python-sandbox / node-sandbox / data-analysis）。
    # 为 None 表示无需沙箱。
    suggested_template: str | None = None

    # 用户提供的本地文件路径列表，需要在创建沙箱后上传到沙箱内。
    input_files: list[str] = []

    # 沙箱内处理完成后需要下载回本地的文件信息列表。
    # detect_output_files 写入 [{path, mime_type}]，
    # analyze_output_files 补充 {size, preview, value, summary}。
    output_files: list[OutputFile] = []
