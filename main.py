import os
from dotenv import load_dotenv

# 明确指定加载 config.env 文件
# os.path.join 确保无论你在哪个目录运行脚本，都能准确找到这个文件
env_path = os.path.join(os.path.dirname(__file__), 'config.env')
load_dotenv(dotenv_path=env_path)

from src.agent.graph import build_graph

if __name__ == "__main__":
    print("启动智能体应用...")

    graph = build_graph()

    # 测试对话
    test_input = {
        "messages": [
            {"role": "user", "content": "hi"}
        ]
    }

    config = {"configurable": {"thread_id": "local-test-thread"}}

    print("\n================== 任务开始 ==================")
    for event in graph.stream(test_input, config, stream_mode="values"):
        if "messages" in event and len(event["messages"]) > 0:
            last_msg = event["messages"][-1]
            last_msg.pretty_print()

    print("================== 任务结束 ==================\n")
