# GTG Agent

<p>
  <img src="https://img.shields.io/badge/python-3.13-blue?logo=python" alt="Python 3.13">
  <img src="https://img.shields.io/github/license/zzqzhangze/gtg-agent" alt="License">
  <img src="https://img.shields.io/github/actions/workflow/status/zzqzhangze/gtg-agent/ci.yml?branch=master&label=CI" alt="CI">
  <img src="https://img.shields.io/badge/uv-1.0+-blue?logo=uv" alt="uv">
</p>

AI Agent，基于 LangGraph 编排，通过 OpenAI 兼容协议接入 LLM，Docker 沙箱安全隔离执行任务。

## 架构

```
用户输入 ──→ Web UI ──→ FastAPI /chat ──→ LangGraph Pipeline (SqliteSaver 持久化)
                                                 │
                                                 ▼
                                          analyze_intent
                                      (LLM 意图分类)
                                    ┌──────┼──────────┐
                                    │      │          │
                                    ▼      ▼          ▼
                              tool_task  chat/     code_exec/
                             (MCP工具)  compute   data_analysis/
                                        (直接LLM)  multi_step
                                    │      │     (需要沙箱)
                                    │      │          │
                                    │      │    create_sandbox
                                    │      │    upload_files
                                    │      │    Skills + MCP
                                    │      │    run_agent(DeepAgent)
                                    │      │    detect/analyze/download
                                    │      │          │
                                    └──┬───┴──────────┘
                                       ▼
                                 cleanup_sandbox
                                       │
                                       ▼
                                      END
```

> 意图分析使用 LLM 分类，支持 `chat` / `compute` / `tool_task` / `code_exec` / `data_analysis` / `multi_step`。
> 沙箱模板根据任务类型动态选择。对话消息持久化到 `.omo/sessions/graph.db`，通过 `session_id` 隔离。

## 快速开始

部署指南（沙箱服务、完整配置、FAQ）：[`docs/deployment.md`](docs/deployment.md)

## 项目结构

```
gtg_agent/
├── api.py              # FastAPI 服务入口（含 Web UI 静态文件服务）
├── main.py             # 命令行入口
├── static/             # Web UI 前端文件
├── pyproject.toml      # 项目元数据与依赖声明
├── config.env          # 环境变量配置
├── AGENTS.md           # AI 行为指令（精简指令集）
├── CONTRIBUTING.md     # 开发参考（核心概念、Skills、MCP）
├── src/                # 核心代码
│   ├── config.py       # 集中配置（所有环境变量在此读取）
│   ├── llm.py          # LLM 兼容层（多厂商 reasoning 透传）
│   ├── sandbox/        # 沙箱接口层（async→sync 桥接 + 模板注册表）
│   ├── agent/          # Agent 编排层（LangGraph 状态机）
│   │   ├── state.py    # 全局共享状态（账本）
│   │   ├── nodes.py    # 处理节点（8 个车间）
│   │   └── graph.py    # 节点连线与路由
│   ├── mcp/            # MCP 协议工具集成
│   │   ├── client.py   # 双模传输客户端（streamable-http + SSE）
│   │   ├── adapter.py  # MCPTool(BaseTool) 适配器
│   │   ├── db.py       # SQLite 持久层（servers + tools）
│   │   └── router.py   # FastAPI 管理路由
│   └── skills/         # Skills 技能系统
│       ├── __init__.py
│       └── loader.py   # 技能发现与沙箱上传
├── .omo/              # 运行时数据（sessions/mcp/skills）+ 开发文档（plans/workflows）
└── docs/               # 部署指南、设计文档
    └── deployment.md   # 部署指南
```

> AI 行为指令见 [AGENTS.md](AGENTS.md)，开发参考见 [CONTRIBUTING.md](CONTRIBUTING.md)。

## 许可

[MIT](LICENSE)
