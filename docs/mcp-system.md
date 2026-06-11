# MCP 工具系统

> 本文档解释 gtg_agent 中 MCP（Model Context Protocol）工具集成的架构与实现，
> 帮助理解如何添加 MCP server、管理工具，以及 Agent 如何调用 MCP 工具。
>
> **关键文件**: `src/mcp/` 下的 client.py / adapter.py / db.py / router.py

---

## 1. 概述

**MCP** 是一种开放协议，允许 LLM 应用通过标准化的接口调用外部工具——如天气查询、数据库访问、文件操作、API 调用等。

本项目的 MCP 集成提供：

- **双模传输**：支持 Streamable HTTP（直连）和 SSE（标准 MCP）两种模式
- **Web 可视化管理**：通过浏览器页面添加/删除/测试 MCP server
- **LangChain 适配**：将 MCP 工具包装为 LangChain `BaseTool`，Agent 直接调用
- **SQLite 持久化**：server 配置和工具列表重启不丢失
- **双路径集成**：沙箱路径（Route A）和纯工具路径（Route C）

---

## 2. 架构总览

```
┌───────────────────────────────────────────────────────────────┐
│                    MCP 子系统                                  │
│                                                               │
│  ┌──────────┐    ┌──────────┐    ┌───────────────────┐        │
│  │ SQLite    │    │ FastAPI  │    │ Web 管理页面      │        │
│  │ (持久化)  │◄───│ Router   │◄───│ (mcp.html)        │        │
│  └────┬─────┘    └──────────┘    └───────────────────┘        │
│       │                                                       │
│       ▼                                                       │
│  ┌──────────┐    ┌──────────────────┐     ┌──────────────┐    │
│  │ MCPClient│───►│ MCPTool(BaseTool)│────►│ create_deep  │    │
│  │ 双模传输 │    │ (LangChain适配)   │     │ _agent       │    │
│  └──────────┘    └──────────────────┘     └──────┬───────┘    │
│                                                   │           │
└───────────────────────────────────────────────────┼───────────┘
                                                     │
                          ┌──────────────────────────┼──────────┐
                          ▼                          ▼          ▼
                    Route A (沙箱)             Route C (纯工具)
                    run_agent                  run_agent_with_mcp
```

### 文件结构

| 文件 | 职责 |
|------|------|
| `client.py` | MCP HTTP 客户端，实现双模传输协议 |
| `adapter.py` | 将 MCP 工具定义转换为 LangChain `BaseTool` |
| `db.py` | SQLite 持久层，管理 server 和 tool 配置 |
| `router.py` | FastAPI 管理路由，提供 REST CRUD 接口 |
| `__init__.py` | 包声明 |

---

## 3. 双模传输（MCPClient）

`src/mcp/client.py` — `MCPClient` 支持三种传输模式：

### 3.1 Streamable HTTP（默认）

```
POST /mcp-url  →  initialize (JSON-RPC 2.0)
              ←  200 OK + Mcp-Session-Id 头
POST /mcp-url  →  tools/list (带 Mcp-Session-Id)
POST /mcp-url  →  tools/call (带 Mcp-Session-Id)
```

特点：
- 单一 HTTP 端点，所有请求走 POST
- 通过 `Mcp-Session-Id` 头维持会话
- 首次 `initialize` 请求自动获得 session_id
- 性能好，延迟低

```python
client = MCPClient()
client.connect("http://localhost:8080/mcp", transport_mode="streamable-http")
tools = client.list_tools()       # → [{"name": "get_weather", ...}]
result = client.call_tool("get_weather", {"city": "北京"})
```

### 3.2 SSE（标准 MCP）

```
GET  /mcp-url  →  event: endpoint + data: /messages
POST /messages →  tools/list
POST /messages →  tools/call
```

特点：
- 先通过 SSE 获取 post 端点 URL
- 后续所有请求发往该端点
- 兼容所有标准 MCP 服务端

### 3.3 自动检测

传输模式在 Web UI 上配置，支持三个值：

| mode | 行为 |
|------|------|
| `auto` | 先尝试 Streamable HTTP，失败后回退 SSE |
| `streamable-http` | 只用直连，不尝试 SSE |
| `sse` | 只用 SSE，跳过 Streamable HTTP 尝试 |

### 3.4 代理绕过

MCP 连接默认绕过系统代理（如 Clash / v2ray），通过设置 `NO_PROXY` 环境变量实现：

```python
os.environ["NO_PROXY"] = "localhost,127.0.0.1,::1," + no_proxy
```

确保 MCP 服务器直连，不受本地代理干扰。

---

## 4. MCPTool 适配器

`src/mcp/adapter.py` — 将 MCP 工具定义转换为 LangChain 工具。

### 核心类：MCPTool

```python
class MCPTool(BaseTool):
    mcp_client: MCPClient        # 持有 MCP 客户端引用
    mcp_tool_name: str           # MCP 工具名
    mcp_tool_schema: dict        # 原始 JSON Schema
```

继承自 `BaseTool`，实现 `_run(**kwargs)` 方法：

```python
def _run(self, **kwargs):
    result = self.mcp_client.call_tool(self.mcp_tool_name, kwargs)
    # 提取 text 类型的内容，拼接返回
    texts = [item["text"] for item in result if item.get("type") == "text"]
    return "\n".join(texts)
```

### 构建工厂

```python
def build_tools_for_server(server_config) -> list[BaseTool]:
    """连接 MCP server → 拉取工具列表 → 每个工具包装为 MCPTool"""
    client = MCPClient()
    client.connect(server_config["url"], ...)
    tools_defs = client.list_tools()
    return [MCPTool.from_mcp_definition(client, td, server_config["name"])
            for td in tools_defs]
```

每个 MCP 工具的 JSON Schema 会自动转换为 Pydantic 模型作为参数校验：

```
工具 inputSchema → _json_schema_to_pydantic() → Pydantic BaseModel
```

---

## 5. SQLite 持久层

`src/mcp/db.py` — 使用 SQLite 存储 MCP server 和工具配置。

### 数据库位置

```
.omo/mcp/mcp.db   (WAL 模式，自动创建)
```

### 表结构

**mcp_servers**：

| 字段 | 类型 | 说明 |
|------|------|------|
| `id` | TEXT PK | UUID |
| `name` | TEXT | 服务器名称（如 "天气服务"） |
| `url` | TEXT | MCP 服务端 URL |
| `timeout` | INTEGER | 连接超时（秒，默认 60） |
| `transport_mode` | TEXT | `auto` / `streamable-http` / `sse` |
| `created_at` | TEXT | 创建时间 |
| `updated_at` | TEXT | 更新时间 |

**mcp_tools**：

| 字段 | 类型 | 说明 |
|------|------|------|
| `id` | TEXT PK | UUID |
| `server_id` | TEXT FK | 所属 server，级联删除 |
| `name` | TEXT | 工具名（如 `get_weather`） |
| `description` | TEXT | 工具描述 |
| `input_schema` | TEXT | JSON Schema（JSON 字符串） |
| `enabled` | INTEGER | 1=启用，0=禁用 |

### 关键函数

```python
get_enabled_servers()
    # → 返回至少有一个启用工具的 server 列表
    # 用于 Agent 运行时决定加载哪些 MCP 工具
```

---

## 6. 管理 API

`src/mcp/router.py` — FastAPI 路由，前缀 `/mcp`，注册在 `api.py` 中。

### 端点一览

| 方法 | 路径 | 说明 |
|------|------|------|
| `GET` | `/mcp/servers` | 列出所有 server |
| `POST` | `/mcp/servers` | 添加 server |
| `PUT` | `/mcp/servers/{id}` | 更新 server |
| `DELETE` | `/mcp/servers/{id}` | 删除 server（级联删除工具） |
| `POST` | `/mcp/servers/{id}/test` | 测试连接（实际连接并列出工具） |
| `POST` | `/mcp/servers/{id}/sync` | 同步工具列表（从 server 拉取最新工具） |
| `GET` | `/mcp/tools` | 列出所有工具（可选 `?server_id=` 过滤） |
| `PUT` | `/mcp/tools/{id}` | 启用/禁用工具 |

### 请求示例

```bash
# 添加 MCP 服务
curl -X POST http://localhost:8000/mcp/servers \
  -H "Content-Type: application/json" \
  -d '{"name": "天气服务", "url": "http://localhost:8081/mcp"}'

# 测试连接
curl -X POST http://localhost:8000/mcp/servers/{id}/test
# → {"ok": true, "tools_count": 3, "tools": ["get_weather", ...]}

# 同步工具列表
curl -X POST http://localhost:8000/mcp/servers/{id}/sync
# → {"ok": true, "tools_count": 3}

# 启用/禁用工具
curl -X PUT http://localhost:8000/mcp/tools/{id} \
  -H "Content-Type: application/json" \
  -d '{"enabled": true}'
```

---

## 7. Web 管理界面

`static/mcp.html` + `static/mcp.js` — 浏览器端 MCP 管理页面，通过 `GET /mcp/` 访问。

功能：
- 列出所有已注册的 MCP server
- 添加/编辑/删除 server
- 测试连接
- 同步工具列表
- 启用/禁用单个工具
- 传输模式选择器（auto / HTTP / SSE）

---

## 8. Agent 集成

MCP 工具在 Agent 的两个路径中加载：

### Route A（沙箱路径）— nodes.py:408-420

```python
# 在 code_exec / data_analysis / multi_step 路径中：
#   analyze_intent → create_sandbox → upload_files → run_agent
#                                                    ↓
#                                            加载 MCP 工具
#                                            create_deep_agent(tools=..., backend=...)
```

有沙箱 + MCP 工具，适合需要代码执行同时需要外部工具的复杂场景。

### Route C（纯工具路径）— nodes.py:455-504

```python
# 在 tool_task 路径中：
#   analyze_intent → run_agent_with_mcp
#                      ↓
#               加载 MCP 工具
#               create_deep_agent(tools=..., 无 backend)
```

无沙箱，仅有 MCP 工具，适合天气查询、数据库查询等无需代码执行的场景。无 MCP 工具时自动回退纯文本回答。

### 加载逻辑

```
get_enabled_servers()
    → 遍历每个 server
        → MCPClient.connect(url, transport_mode)
            → 获取 enable 的工具列表
                → 每个工具包装为 MCPTool(BaseTool)
                    → create_deep_agent(tools=[...])
```

异常安全：单 server 连接失败不影响其他 server，日志记录错误，Agent 继续运行。

---

## 9. 配置与使用流程

### 添加 MCP 服务

```
1. 启动服务端: uvicorn api:app --port 8000
2. 打开浏览器 → http://localhost:8000/mcp/
3. 点击"添加 Server" → 输入名称、URL、传输模式
4. 点击"测试连接"验证是否可达
5. 点击"同步工具"拉取工具列表
6. 启用需要的工具（默认全部启用）
7. 在聊天界面提问，Agent 自动调用 MCP 工具
```

### 配置参数

MCP 的相关配置存储在两个地方：

| 配置 | 位置 | 说明 |
|------|------|------|
| Server 配置 | SQLite (`.omo/mcp/mcp.db`) | 通过 Web UI 管理，重启不丢失 |
| 传输模式 | Server 配置字段 | 每个 server 独立设置 |
| 连接超时 | Server 配置字段 | 每个 server 独立设置（默认 60s） |

没有环境变量配置——所有 MCP 管理通过 Web UI 完成。

---

## 10. 安全设计

| 防线 | 机制 |
|------|------|
| 代理绕过 | MCP 连接绕过系统代理，防止中间人 |
| 异常隔离 | 单 server 连接失败不阻塞整个 Agent |
| 工具开关 | 每个工具独立启用/禁用，不在同步时自动启用 |
| 级联删除 | 删除 server 时自动删除其所有工具 |
| 连接测试 | 新增/修改 server 后可测试连接再同步 |

---

## 11. 与其他子系统的关系

```
MCP 工具系统
    │
    ├──► Agent 管线 (agent-pipeline-architecture.md)
    │      Route A 和 Route C 中加载 MCP 工具
    │
    ├──► LangChain 工具系统
    │      MCPTool(BaseTool) 融入 LangChain 工具生态
    │
    └──► Web UI
           mcp.html 提供可视化管理界面
```
