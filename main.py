"""
CLI 入口 — 支持单次执行与交互式 REPL 两种模式。

用法:
    python main.py "消息内容" [文件路径1 ...]    单次执行
    python main.py                               交互式对话
"""

from __future__ import annotations

import logging
import os
import sqlite3
import sys
import shutil
import uuid

# Windows GBK 终端兼容：print(emoji) 不会崩
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

# Diagnostic logging for reasoning_content fix
logging.basicConfig(level=logging.WARNING, format="%(name)s %(levelname)s %(message)s", stream=sys.stderr)

from langgraph.checkpoint.sqlite import SqliteSaver
from src.agent.graph import build_graph


# ── 持久化初始化 ─────────────────────────────────────────────────────
_SESSIONS_DIR = os.path.join(os.path.dirname(__file__), ".sisyphus", "sessions")


def _create_checkpointer() -> SqliteSaver:
    """创建 SqliteSaver，持久化到 .sisyphus/sessions/sessions.db。"""
    os.makedirs(_SESSIONS_DIR, exist_ok=True)
    db_path = os.path.join(_SESSIONS_DIR, "sessions.db")
    conn = sqlite3.connect(db_path, check_same_thread=False)
    saver = SqliteSaver(conn)
    return saver


def _get_thread_messages(saver: SqliteSaver, thread_id: str) -> list:
    """从 checkpointer 加载指定 thread 的所有消息。"""
    try:
        tuples = list(saver.list({"configurable": {"thread_id": thread_id}}, limit=1))
        if not tuples:
            return []
        checkpoint = tuples[0]
        state = checkpoint.checkpoint
        # 检查点结构: {"channel_values": {"messages": [...]}, ...}
        channel_values = state.get("channel_values", {})
        messages = channel_values.get("messages", [])
        return messages
    except Exception:
        return []


def _list_all_threads(saver: SqliteSaver) -> list[tuple[str, int]]:
    """列出所有 thread_id 及其消息数。"""
    # 直接查 SQLite 获取去重的 thread_id 列表
    try:
        cur = saver.conn.execute(
            "SELECT thread_id, COUNT(*) FROM checkpoints GROUP BY thread_id ORDER BY MAX(checkpoint_id) DESC"
        )
        return [(row[0], row[1]) for row in cur.fetchall()]
    except Exception:
        return []


# ── 终端着色（非 TTY 时自动降级） ─────────────────────────────────────
def _c(code: str, text: str) -> str:
    return f"\033[{code}m{text}\033[0m" if sys.stdout.isatty() else text


BOLD = lambda t: _c("1", t)
GREEN = lambda t: _c("32", t)
CYAN = lambda t: _c("36", t)
YELLOW = lambda t: _c("33", t)
RED = lambda t: _c("31", t)
DIM = lambda t: _c("2", t)


# ── 帮助信息 ─────────────────────────────────────────────────────────
HELP_TEXT = f"""
  {BOLD('可用命令')}
  {CYAN('/file <路径>')}     添加文件到本轮对话
  {CYAN('/files')}          查看已添加的文件列表
  {CYAN('/clear')}          清空文件列表
  {CYAN('/history')}          显示本轮对话历史
  {CYAN('/history all')}      显示所有历史会话
  {CYAN('/history clear')}    清除本轮对话历史
  {CYAN('/history clear --all')}  清除所有历史会话
  {CYAN('/help')}             显示此帮助
  {CYAN('/exit')}             退出（也可按 Ctrl+C）

  {BOLD('使用示例')}
  >>> /file data.csv
  >>> 读取这个 CSV，统计每列的空值数量
"""


# ── 核心处理 ─────────────────────────────────────────────────────────
def stream_and_show(graph, input_data: dict, config: dict) -> tuple[bool, list]:
    """执行图并打印所有输出。返回值 (files_uploaded, final_messages)。"""
    files_uploaded = False
    final_messages = []
    for event in graph.stream(input_data, config, stream_mode="values"):
        _show_messages(event)
        _show_file_ops(event)
        if event.get("uploaded_paths"):
            files_uploaded = True
        msgs = event.get("messages")
        if msgs:
            final_messages = msgs
    return files_uploaded, final_messages


def _show_messages(event: dict) -> None:
    """打印 AI 的文本回复（只显示有实际内容的 AIMessage）。"""
    msgs = event.get("messages")
    if not msgs:
        return
    last = msgs[-1]
    content = getattr(last, "content", str(last))
    if not content:
        return
    # 跳过 intermediate 空消息
    print(content)


def _show_file_ops(event: dict) -> None:
    """打印文件上传/下载记录。"""
    uploaded = event.get("uploaded_paths")
    if uploaded:
        print(f"\n{DIM('上传的文件:')}")
        for item in uploaded:
            print(f"  {DIM(f'{item['local']} → 沙箱:{item['sandbox']}')}")

    downloaded = event.get("downloaded_paths")
    if downloaded:
        print(f"\n{DIM('下载的文件:')}")
        for item in downloaded:
            print(f"  {DIM(f'{item['sandbox']} → {item['local']}')}")


# ── 模式 1：单次执行 ─────────────────────────────────────────────────
def run_single(graph, saver=None) -> None:
    """python main.py "消息" [文件...] — 执行一次后退出。"""
    user_message = sys.argv[1]
    input_files = sys.argv[2:]

    print(f"用户消息: {user_message}")
    if input_files:
        print(f"附带文件: {input_files}")

    thread_id = str(uuid.uuid4())
    input_data = {
        "messages": [{"role": "user", "content": user_message}],
        "input_files": input_files,
        "output_files": [],
        "uploaded_paths": [],
        "downloaded_paths": [],
        "sandbox_id": None,
        "needs_sandbox": None,
        "task_type": None,
        "intent_reasoning": None,
        "suggested_template": None,
        "session_id": thread_id,
    }
    config = {"configurable": {"thread_id": thread_id}}

    print(BOLD("\n──── 任务开始 ────"))
    stream_and_show(graph, input_data, config)
    print(BOLD("──── 任务结束 ────"))


# ── 模式 2：交互式 REPL ─────────────────────────────────────────────
def run_interactive(graph, saver) -> None:
    """python main.py — 进入交互式对话。"""
    thread_id = str(uuid.uuid4())
    config = {"configurable": {"thread_id": thread_id}}
    pending_files: list[str] = []

    print_banner()
    print(f"{DIM(f'Session: {thread_id[:8]}...')}")

    while True:
        try:
            raw = input(f"\n{DIM('>>>')} " if sys.stdout.isatty() else "\n>>> ").strip()
        except (EOFError, KeyboardInterrupt):
            print(f"\n{GREEN('再见！')}")
            break

        if not raw:
            continue

        # ── 命令分发 ──────────────────────────────────────────────
        if raw == "/exit":
            print(GREEN("再见！"))
            break

        if raw == "/help":
            print(HELP_TEXT)
            continue

        if raw == "/history":
            _show_history(saver, thread_id)
            continue

        if raw == "/history all":
            _show_all_history(saver)
            continue

        if raw == "/history clear":
            _clear_session(saver, thread_id)
            continue

        if raw == "/history clear --all":
            _clear_all_sessions(saver)
            continue

        if raw == "/clear":
            pending_files.clear()
            print(f"  {GREEN('✓')} 文件列表已清空")
            continue

        if raw.startswith("/file "):
            path = raw[6:].strip()
            if not path:
                print(f"  {YELLOW('用法')}: /file <文件路径>")
                continue
            if not os.path.isfile(path):
                print(f"  {RED('文件不存在')}: {path}")
                continue
            pending_files.append(path)
            print(f"  {GREEN('✓')} 已添加: {path}")
            continue

        if raw == "/files":
            if pending_files:
                print(f"  待上传文件 ({len(pending_files)}):")
                for f in pending_files:
                    print(f"    {DIM(f)}")
                print(f"  {DIM('(发送需要沙箱的消息时自动上传)')}")
            else:
                print(DIM("  (暂无待上传文件，用 /file <路径> 添加)"))
            continue

        # ── 普通消息发送 ──────────────────────────────────────────
        # 只传入新增消息，checkpointer 自动恢复历史
        # 显式重置非消息状态字段，避免跨轮残留
        input_data = {
            "messages": [{"role": "user", "content": raw}],
            "input_files": list(pending_files),
            "output_files": [],
            "uploaded_paths": [],
            "downloaded_paths": [],
            "sandbox_id": None,
            "needs_sandbox": None,
            "task_type": None,
            "intent_reasoning": None,
            "suggested_template": None,
            "session_id": thread_id,
        }

        print(BOLD("──── 回应 ────"))
        files_consumed, _ = stream_and_show(graph, input_data, config)
        if files_consumed:
            # 文件已进入沙箱，清空列表等待下一轮
            pending_files.clear()
        elif pending_files:
            # 本轮未触发沙箱（纯聊天），文件保留，下轮继续尝试
            print(DIM(f"  (文件未使用，继续保留: {pending_files})"))


def _show_history(saver: SqliteSaver, thread_id: str) -> None:
    """从 checkpointer 加载并显示本轮消息历史。"""
    messages = _get_thread_messages(saver, thread_id)
    if not messages:
        print(DIM("  (暂无对话历史)"))
        return
    for i, m in enumerate(messages, 1):
        role = BOLD("用户") if getattr(m, "role", None) == "user" else BOLD("助手")
        text = m.content if hasattr(m, "content") else str(m)
        preview = text[:200] + ("..." if len(text) > 200 else "")
        print(f"  [{i}] {role}: {preview}")


def _show_all_history(saver: SqliteSaver) -> None:
    """列出所有历史会话及其摘要。"""
    threads = _list_all_threads(saver)
    if not threads:
        print(DIM("  (尚无历史会话)"))
        return
    print(f"  {BOLD('历史会话:')}")
    for thread_id, ckpt_count in threads:
        # 获取该会话的第一条用户消息作为摘要
        messages = _get_thread_messages(saver, thread_id)
        preview = ""
        if messages:
            first = messages[0]
            text = first.content if hasattr(first, "content") else str(first)
            preview = text[:80] + ("..." if len(text) > 80 else "")
        print(f"  [{thread_id[:8]}...] {DIM(f'({ckpt_count} 条记录)')} {preview}")


def _clear_session(saver: SqliteSaver, thread_id: str) -> None:
    """删除当前会话的所有 checkpoints。"""
    try:
        saver.conn.execute("DELETE FROM writes WHERE thread_id = ?", (thread_id,))
        saver.conn.execute("DELETE FROM checkpoints WHERE thread_id = ?", (thread_id,))
        saver.conn.commit()
        print(f"  {GREEN('✓')} 当前会话已清除")
    except Exception as e:
        print(f"  {RED('清除失败')}: {e}")


def _clear_all_sessions(saver: SqliteSaver) -> None:
    """删除所有历史会话。"""
    try:
        saver.conn.execute("DELETE FROM writes")
        saver.conn.execute("DELETE FROM checkpoints")
        saver.conn.commit()
        print(f"  {GREEN('✓')} 所有历史会话已清除")
    except Exception as e:
        print(f"  {RED('清除失败')}: {e}")


def _cleanup_old_sessions(saver: SqliteSaver, max_threads: int = 30) -> None:
    """启动时清理：只保留最近的 max_threads 个会话，删除更早的。"""
    try:
        cur = saver.conn.execute(
            "SELECT thread_id, MIN(checkpoint_id) as first_cpid "
            "FROM checkpoints GROUP BY thread_id "
            "ORDER BY first_cpid DESC LIMIT -1 OFFSET ?",
            (max_threads,)
        )
        old_threads = [r[0] for r in cur.fetchall()]
        if not old_threads:
            return
        placeholders = ",".join("?" for _ in old_threads)
        saver.conn.execute(f"DELETE FROM writes WHERE thread_id IN ({placeholders})", old_threads)
        saver.conn.execute(f"DELETE FROM checkpoints WHERE thread_id IN ({placeholders})", old_threads)
        saver.conn.commit()
        print(f"[清理] 已清理 {len(old_threads)} 个过期会话")
    except Exception as e:
        print(f"[清理] 跳过（{e}）")


def print_banner() -> None:
    """启动画面。"""
    term_width = shutil.get_terminal_size().columns
    print("━" * term_width)
    print(f"{BOLD('My Deep Agent')} — 本地 AI 代码执行助手")
    print(f"输入消息开始对话，输入 {CYAN('/help')} 查看命令")
    print("━" * term_width)


# ── 入口 ─────────────────────────────────────────────────────────────
if __name__ == "__main__":
    saver = _create_checkpointer()
    _cleanup_old_sessions(saver, max_threads=30)
    graph = build_graph(checkpointer=saver)

    if len(sys.argv) > 1:
        run_single(graph, saver)
    else:
        run_interactive(graph, saver)
