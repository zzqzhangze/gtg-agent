"""
FastAPI 服务入口 — 将 LangGraph Agent 暴露为 REST API。

启动方式:
    uvicorn api:app --host 0.0.0.0 --port 8000 --reload

请求示例:
    curl -X POST http://localhost:8000/chat \\
        -F "message=在沙箱打印hello world" \\
        -F "files=@report.txt"

使用 pip 安装依赖:
    pip install fastapi uvicorn python-multipart
"""

import os
import uuid
import tempfile
import shutil
from pathlib import Path

from dotenv import load_dotenv
from fastapi import FastAPI, UploadFile, File, Form, HTTPException
from fastapi.responses import JSONResponse, FileResponse

# 加载环境变量
env_path = os.path.join(os.path.dirname(__file__), "config.env")
load_dotenv(dotenv_path=env_path)

from src.agent.graph import build_graph

app = FastAPI(
    title="My Deep Agent API",
    description="本地 AI 代码执行 Agent — 支持文件上传、沙箱执行、结果下载",
    version="0.1.0",
)

# 全局图实例（线程安全：LangGraph 的 StateGraph 是纯函数式的）
_graph = build_graph()

# 会话文件的临时存储根目录
UPLOAD_DIR = Path(tempfile.gettempdir()) / "my_deep_agent_uploads"
UPLOAD_DIR.mkdir(parents=True, exist_ok=True)


def get_session_dir(session_id: str) -> Path:
    """每个会话一个独立目录，避免文件冲突"""
    session_dir = UPLOAD_DIR / session_id
    session_dir.mkdir(parents=True, exist_ok=True)
    return session_dir


@app.post("/chat")
async def chat(
    message: str = Form(..., description="用户消息"),
    session_id: str = Form("default", description="会话 ID，用于追踪对话上下文"),
    files: list[UploadFile] = File(None, description="待上传的文件（可选）"),
):
    """
    核心聊天接口。

    - 上传的文件会先保存到临时目录，然后传入图的 input_files 字段。
    - 若 Agent 在沙箱内产生了输出文件，可通过 output_files 字段指定路径，
      本接口在 stream 结束后自动返回这些文件。
    """
    # 1. 保存上传文件到会话目录
    session_dir = get_session_dir(session_id)
    local_files = []

    if files:
        for f in files:
            if f.filename:
                dest = session_dir / f.filename
                content = await f.read()
                dest.write_bytes(content)
                local_files.append(str(dest))
                print(f"[API] 收到上传文件: {f.filename} ({len(content)} bytes)")

    # 2. 构建图输入
    input_data = {
        "messages": [{"role": "user", "content": message}],
        "input_files": local_files,
        "output_files": [],  # 由 run_agent 节点内部根据业务逻辑填充
    }
    config = {"configurable": {"thread_id": session_id}}

    # 3. 流式执行图，收集结果
    result_text = ""
    downloaded = []

    for event in _graph.stream(input_data, config, stream_mode="values"):
        if "messages" in event and len(event["messages"]) > 0:
            last_msg = event["messages"][-1]
            result_text = last_msg.content if hasattr(last_msg, "content") else str(last_msg)

        if "downloaded_paths" in event and event["downloaded_paths"]:
            downloaded = event["downloaded_paths"]

    # 4. 响应
    return JSONResponse({
        "session_id": session_id,
        "response": result_text,
        "downloaded_files": downloaded,
    })


@app.get("/files/{session_id}/{filename}")
async def download_file(session_id: str, filename: str):
    """
    下载 Agent 处理后的文件。

    文件路径: {temp_dir}/{session_id}/{filename}
    """
    file_path = UPLOAD_DIR / session_id / filename
    if not file_path.exists():
        raise HTTPException(status_code=404, detail="文件不存在")
    return FileResponse(
        path=str(file_path),
        filename=filename,
        media_type="application/octet-stream",
    )


@app.get("/health")
async def health():
    """健康检查接口"""
    return {"status": "ok"}


@app.get("/")
async def root():
    """API 信息"""
    return {
        "service": "My Deep Agent",
        "version": "0.1.0",
        "endpoints": {
            "POST /chat": "发送消息并处理文件",
            "GET /files/{session_id}/{filename}": "下载处理后的文件",
            "GET /health": "健康检查",
        },
    }
