# My Deep Agent

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
> 沙箱模板根据任务类型动态选择。对话消息持久化到 `.sisyphus/sessions/`，通过 `session_id` 隔离。
> Web UI 通过 `GET /` 访问。

## 快速开始

### 依赖

- Python >= 3.13
- 任意兼容 OpenAI 协议的 LLM 服务（如 Ollama、OpenAI API、vLLM、Azure OpenAI 等）
- [OpenSandbox](https://opensandbox.dev/) 沙箱服务

### 安装

项目使用 [uv](https://docs.astral.sh/uv/) 管理虚拟环境和依赖：

```bash
# 创建 .venv 并安装所有依赖
uv sync
```

### 配置

编辑 `config.env`，按需填写 LLM 地址和模型名（兼容任何 OpenAI API 格式的服务）：

```env
# ── LLM ──────────────────────────────────────────────────────────────
# 兼容任何 OpenAI API 格式的服务（Ollama / OpenAI / vLLM / DeepSeek 等）
OPENAI_API_BASE=https://api.openai.com/v1
OPENAI_API_KEY=sk-xxxxx
MODEL_NAME=gpt-4o

# ── Sandbox ──────────────────────────────────────────────────────────
SANDBOX_API_URL=http://127.0.0.1:8080
# SANDBOX_API_KEY=my-secret-api-key-007
# SANDBOX_USE_SERVER_PROXY=false   # 是否通过代理连接沙箱
```

### 运行

**命令行模式：**

```bash
# 交互式对话（REPL）
python main.py

# 单次执行（带消息和文件）
python main.py "帮我总结这个文件" report.txt data.csv
```

REPL 模式下支持以下命令：

| 命令 | 说明 |
|------|------|
| `/file <路径>` | 添加文件到本轮对话 |
| `/files` | 查看已添加的文件列表 |
| `/clear` | 清空文件列表 |
| `/history` | 查看本轮对话历史 |
| `/history all` | 查看所有已持久化的历史会话 |
| `/history clear` | 清除本轮对话历史 |
| `/history clear --all` | 清除所有历史会话 |
| `/help` | 显示帮助 |
| `/exit` 或 Ctrl+C | 退出 |

**API 服务模式：**

```bash
# 安装额外依赖（如已在 pyproject.toml 中声明则跳过）
uv add fastapi uvicorn python-multipart

# 启动服务
uv run uvicorn api:app --host 0.0.0.0 --port 8000 --reload

# 方案 A：浏览器打开 Web UI
open http://localhost:8000

# 方案 B：命令行调用（返回 JSON）
curl -X POST http://localhost:8000/chat \
  -F "message=读取并分析这个 CSV" \
  -F "files@=data.csv"
```

API 端点：

| 方法 | 路径 | 说明 |
|------|------|------|
| GET | `/` | Web 聊天界面（浏览器打开） |
| POST | `/chat` | 发送消息 + 上传文件；`session_id` 参数决定对话记忆隔离 |
| GET | `/api-info` | API 信息 |
| GET | `/health` | 健康检查 |
| GET | `/files/{session_id}/{filename}` | 下载处理后的文件 |
| GET | `/sessions/{session_id}/downloads/{filename}` | 下载沙箱输出文件 |
| GET | `/sessions/{session_id}/downloads/zip` | 批量打包下载沙箱输出文件 |
| DELETE | `/sessions/{session_id}/history` | 删除指定会话的持久化记忆 |
| GET | `/mcp/` | MCP 管理页面（浏览器打开） |
| GET | `/mcp/servers` | 列出已注册的 MCP server |
| POST | `/mcp/servers` | 添加 MCP server |
| PUT | `/mcp/servers/{id}` | 更新 MCP server 配置 |
| DELETE | `/mcp/servers/{id}` | 删除 MCP server |
| POST | `/mcp/servers/{id}/test` | 测试 MCP 连接 |
| POST | `/mcp/servers/{id}/sync` | 同步 MCP 工具列表 |
| GET | `/mcp/tools` | 列出 MCP 工具 |
| PUT | `/mcp/tools/{id}` | 启用/禁用 MCP 工具 |

## 项目结构

```
my_deep_agent/
├── api.py              # FastAPI 服务入口（含 Web UI 静态文件服务）
├── main.py             # 命令行入口
├── static/             # Web UI 前端文件
│   ├── index.html      # 聊天界面 HTML
│   ├── style.css       # 样式 + 暗色模式
│   ├── app.js          # 交互逻辑
│   ├── mcp.html        # MCP 管理页面
│   ├── mcp.js          # MCP 管理交互逻辑
│   └── marked.min.js   # Markdown 渲染库
├── pyproject.toml      # 项目元数据与依赖声明
├── uv.lock             # uv 依赖锁定文件
├── .python-version     # Python 版本声明
├── config.env          # 环境变量配置
├── AGENTS.md           # AI 行为指令
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
├── .sisyphus/
│   ├── sessions/       # 对话消息持久化数据库（自动创建）
│   ├── plans/          # 实施计划（活文档）
│   ├── skills/         # 技能 SKILL.md 文件
│   ├── workflows/      # 工作流规范
│   └── mcp/            # MCP 配置数据库（自动创建）
├── downloads/          # 沙箱结果文件下载目录（自动创建）
└── docs/               # 备选方案、设计文档存档、优化方案
```

> AI 行为指令（文档铁律、代码约束、扩展工作流）见 [AGENTS.md](AGENTS.md)。

## 许可

MIT
