"""
CLI 入口 — 支持单次执行与交互式 REPL 两种模式。

用法:
    python main.py "消息内容" [文件路径1 ...]    单次执行
    python main.py                               交互式对话
"""

from __future__ import annotations

import os
import sys
import shutil

from src.agent.graph import build_graph

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
  {CYAN('/history')}        显示当前对话历史
  {CYAN('/help')}           显示此帮助
  {CYAN('/exit')}           退出（也可按 Ctrl+C）

  {BOLD('使用示例')}
  >>> /file data.csv
  >>> 读取这个 CSV，统计每列的空值数量
"""


# ── 核心处理 ─────────────────────────────────────────────────────────
def stream_and_show(graph, input_data: dict, config: dict) -> None:
    """执行图并打印所有输出（消息 + 文件传输记录）。"""
    for event in graph.stream(input_data, config, stream_mode="values"):
        _show_messages(event)
        _show_file_ops(event)


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
def run_single(graph) -> None:
    """python main.py "消息" [文件...] — 执行一次后退出。"""
    user_message = sys.argv[1]
    input_files = sys.argv[2:]

    print(f"用户消息: {user_message}")
    if input_files:
        print(f"附带文件: {input_files}")

    input_data = {
        "messages": [{"role": "user", "content": user_message}],
        "input_files": input_files,
        "output_files": [],
    }
    config = {"configurable": {"thread_id": "local-test-thread"}}

    print(BOLD("\n──── 任务开始 ────"))
    stream_and_show(graph, input_data, config)
    print(BOLD("──── 任务结束 ────"))


# ── 模式 2：交互式 REPL ─────────────────────────────────────────────
def run_interactive(graph) -> None:
    """python main.py — 进入交互式对话。"""
    config = {"configurable": {"thread_id": "interactive-session"}}
    # 手动维护对话历史（图本身无 checkpointer，消息不自动持久化）
    messages: list[dict] = []
    pending_files: list[str] = []

    print_banner()

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
            _show_history(messages)
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
            else:
                print(DIM("  (暂无待上传文件)"))
            continue

        # ── 普通消息发送 ──────────────────────────────────────────
        messages.append({"role": "user", "content": raw})
        input_data = {
            "messages": list(messages),  # 携带完整历史
            "input_files": list(pending_files),
            "output_files": [],
        }

        print(BOLD("──── 回应 ────"))
        stream_and_show(graph, input_data, config)
        # 文件已消费（上传到本轮创建的沙箱），清空等待下一轮
        pending_files.clear()


def _show_history(messages: list[dict]) -> None:
    """打印对话历史。"""
    if not messages:
        print(DIM("  (暂无对话历史)"))
        return
    for i, m in enumerate(messages, 1):
        role = BOLD("用户") if m["role"] == "user" else BOLD("助手")
        text = m.get("content", "")
        preview = text[:200] + ("..." if len(text) > 200 else "")
        print(f"  [{i}] {role}: {preview}")


def print_banner() -> None:
    """启动画面。"""
    term_width = shutil.get_terminal_size().columns
    print("━" * term_width)
    print(f"{BOLD('My Deep Agent')} — 本地 AI 代码执行助手")
    print(f"输入消息开始对话，输入 {CYAN('/help')} 查看命令")
    print("━" * term_width)


# ── 入口 ─────────────────────────────────────────────────────────────
if __name__ == "__main__":
    graph = build_graph()

    if len(sys.argv) > 1:
        run_single(graph)
    else:
        run_interactive(graph)
