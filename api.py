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
import sqlite3
import sys
import uuid
import tempfile
import shutil
import time
import zipfile
import io
from typing import Optional
from pathlib import Path

from fastapi import FastAPI, UploadFile, File, Form, HTTPException, Query
from fastapi.responses import JSONResponse, FileResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles
from langgraph.checkpoint.sqlite import SqliteSaver

# 配置由 src.config 在 import 时自动加载 config.env
from src.agent.graph import build_graph
from src.mcp.router import router as mcp_router

# Windows GBK 终端兼容
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

app = FastAPI(
    title="My Deep Agent API",
    description="本地 AI 代码执行 Agent — 支持文件上传、沙箱执行、结果下载",
    version="0.1.0",
)

# 持久化 checkpointer
_SESSIONS_DIR = os.path.join(os.path.dirname(__file__), ".sisyphus", "sessions")
os.makedirs(_SESSIONS_DIR, exist_ok=True)
_db_path = os.path.join(_SESSIONS_DIR, "sessions.db")
_conn = sqlite3.connect(_db_path, check_same_thread=False)
_saver = SqliteSaver(_conn)

# 启动时清理过期会话（只保留最近 30 个）
def _cleanup_old_sessions(max_threads: int = 30) -> None:
    try:
        cur = _saver.conn.execute(
            "SELECT thread_id FROM (SELECT thread_id, MIN(checkpoint_id) as first_cpid "
            "FROM checkpoints GROUP BY thread_id ORDER BY first_cpid DESC LIMIT -1 OFFSET ?)",
            (max_threads,)
        )
        old = [r[0] for r in cur.fetchall()]
        if old:
            ph = ",".join("?" for _ in old)
            _saver.conn.execute(f"DELETE FROM writes WHERE thread_id IN ({ph})", old)
            _saver.conn.execute(f"DELETE FROM checkpoints WHERE thread_id IN ({ph})", old)
            _saver.conn.commit()
            print(f"[清理] 已清理 {len(old)} 个过期会话")
    except Exception as e:
        print(f"[清理] 跳过（{e}）")

_cleanup_old_sessions(max_threads=30)

# 全局图实例（线程安全：LangGraph 的 StateGraph 是纯函数式的）
_graph = build_graph(checkpointer=_saver)

# 挂载静态文件目录（前端界面）
app.mount("/static", StaticFiles(directory="static"), name="static")

# 注册 MCP 管理路由
app.include_router(mcp_router)

# 下载端点由 /sessions/{session_id}/downloads/{filename} 动态路由提供

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
        "output_files": [],
        "uploaded_paths": [],
        "downloaded_paths": [],
        "sandbox_id": None,
        "needs_sandbox": None,
        "task_type": None,
        "intent_reasoning": None,
        "suggested_template": None,
        "session_id": session_id,  # 文件下载目录隔离
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


@app.get("/sessions/{session_id}/downloads/zip")
async def download_session_zip(session_id: str, files: list[str] = Query([], description="要打包的文件名列表，为空则打包全部")):
    """
    将指定会话的沙箱输出文件打包为 zip 下载。
    可通过 ?files= 指定具体文件名（可重复），不传则打包全部。
    """
    session_dir = Path("downloads") / session_id
    if not session_dir.exists() or not any(session_dir.iterdir()):
        raise HTTPException(status_code=404, detail="该会话没有可下载的文件")

    # 如果指定了文件名，只打包指定文件
    target_files = files if files else None

    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
        for f in sorted(session_dir.iterdir()):
            if f.is_file():
                if target_files is None or f.name in target_files:
                    zf.write(str(f), arcname=f.name)
    buf.seek(0)

    return StreamingResponse(
        buf,
        media_type="application/zip",
        headers={"Content-Disposition": f"attachment; filename={session_id}.zip"},
    )


@app.delete("/sessions/{session_id}/history")
async def delete_session_history(session_id: str):
    """
    删除指定会话的持久化记忆（checkpoints）。
    不影响本地文件下载目录，只删除对话历史。
    """
    try:
        _saver.conn.execute("DELETE FROM writes WHERE thread_id = ?", (session_id,))
        _saver.conn.execute("DELETE FROM checkpoints WHERE thread_id = ?", (session_id,))
        _saver.conn.commit()
        return JSONResponse({"status": "ok", "session_id": session_id})
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"删除失败: {e}")


@app.get("/sessions/{session_id}/downloads/{filename}")
async def download_session_file(session_id: str, filename: str):
    """
    下载指定会话的沙箱输出文件。

    文件路径: downloads/{session_id}/{filename}
    """
    if ".." in filename or "/" in filename or "\\" in filename:
        raise HTTPException(status_code=400, detail="非法文件名")

    file_path = Path("downloads") / session_id / filename
    if not file_path.exists():
        raise HTTPException(status_code=404, detail="文件不存在或已过期")
    return FileResponse(
        path=str(file_path),
        filename=filename,
        media_type="application/octet-stream",
    )


# ── 文件过期清理 ──────────────────────────────────────

def _cleanup_expired_files(max_age_hours: int = 24):
    """
    清理 downloads/ 下超过 max_age_hours 的过期文件。
    在 FastAPI startup 事件中调用。
    """
    downloads_root = Path("downloads")
    if not downloads_root.exists():
        return

    now = time.time()
    max_age_seconds = max_age_hours * 3600
    removed_count = 0
    removed_size = 0

    for session_dir in downloads_root.iterdir():
        if not session_dir.is_dir():
            continue
        for f in session_dir.iterdir():
            if f.is_file():
                age = now - f.stat().st_mtime
                if age > max_age_seconds:
                    removed_size += f.stat().st_size
                    f.unlink()
                    removed_count += 1
        # 如果 session 目录空了，删除目录本身
        if session_dir.exists() and not any(session_dir.iterdir()):
            session_dir.rmdir()

    if removed_count > 0:
        print(f"[清理] 已删除 {removed_count} 个过期文件 ({removed_size / 1024:.1f} KB)")


@app.on_event("startup")
async def startup_cleanup():
    """服务启动时清理过期文件"""
    _cleanup_expired_files(max_age_hours=24)


@app.get("/health")
async def health():
    """健康检查接口"""
    return {"status": "ok"}


@app.get("/")
async def root():
    """Web UI 入口"""
    return FileResponse("static/index.html")


@app.get("/mcp/")
async def mcp_ui():
    """MCP 管理页面"""
    return FileResponse("static/mcp.html")

@app.get("/api-info")
async def api_info():
    """API 信息（旧根路由挪到 /api-info）"""
    return {
        "service": "My Deep Agent",
        "version": "0.1.0",
        "endpoints": {
            "POST /chat": "发送消息并处理文件",
            "GET /files/{session_id}/{filename}": "下载处理后的文件",
            "GET /sessions/{session_id}/downloads/{filename}": "下载沙箱输出文件",
            "GET /sessions/{session_id}/downloads/zip": "批量打包下载沙箱输出文件",
            "GET /health": "健康检查",
        },
    }
