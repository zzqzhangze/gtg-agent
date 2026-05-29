import sys

# 配置由 src.config 在 import 时自动加载 config.env
from src.agent.graph import build_graph

if __name__ == "__main__":
    print("启动智能体应用...")

    graph = build_graph()

    # 从命令行参数获取消息和文件
    # 用法: python main.py "消息内容" [文件路径1] [文件路径2] ...
    if len(sys.argv) > 1:
        user_message = sys.argv[1]
        input_files = sys.argv[2:]  # 剩余参数作为文件路径
        print(f"\n用户消息: {user_message}")
        if input_files:
            print(f"附带文件: {input_files}")
    else:
        # 默认测试
        user_message = "在沙箱打印:hello world"
        input_files = []

    test_input = {
        "messages": [
            {"role": "user", "content": user_message}
        ],
        "input_files": input_files,
        "output_files": [],
    }

    config = {"configurable": {"thread_id": "local-test-thread"}}

    print("\n================== 任务开始 ==================")
    for event in graph.stream(test_input, config, stream_mode="values"):
        if "messages" in event and len(event["messages"]) > 0:
            last_msg = event["messages"][-1]
            last_msg.pretty_print()

        if "downloaded_paths" in event and event["downloaded_paths"]:
            print("\n[下载的文件]:")
            for item in event["downloaded_paths"]:
                print(f"  {item['sandbox']} → {item['local']}")

        if "uploaded_paths" in event and event["uploaded_paths"]:
            print("\n[上传的文件]:")
            for item in event["uploaded_paths"]:
                print(f"  {item['local']} → 沙箱:{item['sandbox']}")

    print("================== 任务结束 ==================\n")
