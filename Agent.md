```text
my_deep_agent/
├── config.env                  # 环境变量配置
├── main.py               # 项目的总入口
└── src/                  # 核心源代码目录
    ├── __init__.py
    ├── sandbox/          # 专门负责与底层沙箱打交道的模块
    │   ├── __init__.py
    │   ├── client.py     # 包含异步线程循环、LocalSandbox 和 SandboxClient
    │   └── backend.py    # 也就是之前的 langsmith_backend.py（翻译官）
    └── agent/            # 专门负责智能体大脑和流程的模块
        ├── __init__.py
        ├── state.py      # 共享账本定义
        ├── nodes.py      # 所有的车间（分析意图、执行代理、清理等）
        └── graph.py      # 传送带编排（组装图）
```
