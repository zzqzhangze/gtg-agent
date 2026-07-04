# MCP 工具接入设计方案

> 给 gtg_agent 增加 MCP 协议工具接入能力，支持 Web 端可视化管理 MCP server 和工具启用。
>
> **状态**: 已实施（v1 完成，详见 .omo/plans/mcp-tool-integration.md）
> **创建**: 2026-06-01
> **更新**: 2026-06-01

## 1. 背景

### 1.1 现状

`run_agent` 节点已使用 `deepagents.create_deep_agent()` 构建 agent：

```python
# src/agent/nodes.py
agent = create_deep_agent(
    model=llm,
    backend=backend,
    system_prompt=...,
    checkpointer=MemorySaver(),
)
```

agent 目前只有 sandbox 内置工具（`ls`/`read`/`write`/`execute` 等），没有接入外部工具。

### 1.2 架构约束

- **agent 在 Docker 沙箱内执行**，不会触及宿主机 → MCP 仅用 **HTTP** 模式（streamable-http + SSE），不支持 stdio 子进程
- 内网环境可能出网（连远程 MCP server），也可能访问局域网内 MCP 服务
- **启用的工具对所有会话生效**，不按会话隔离

### 1.3 方案依据

deepagents SDK 已经安装并投入使用，无需自定义 middleware 层。核心思路：

1. MCP HTTP SSE 客户端 → 获取 `tools/list`
2. 每个 MCP tool → 包装为 LangChain `BaseTool`
3. 通过 `create_deep_agent(tools=[...])` 注入
4. Web 页面管理 MCP server 配置（SQLite 持久化）

---

## 2. MCP 协议与 HTTP SSE

MCP（Model Context Protocol）基于 JSON-RPC 2.0。HTTP SSE 传输层：

```
初始连接:
  Client ── GET /sse ──────────────────────→ MCP Server
  Client ←─ event: endpoint ─────────────── MCP Server
              data: /message?session_id=xxx

工具调用:
  Client ── POST /message?session_id=xxx ──→ MCP Server
              {"jsonrpc":"2.0","id":1,"method":"tools/call","params":{...}}
  Client ←─ event: message ─────────────── MCP Server
              {"jsonrpc":"2.0","id":1,"result":{"content":[{"type":"text","text":"..."}]}}
```

涉及的 MCP 方法：

| 方法 | 用途 |
|------|------|
| `initialize` | 握手（协议版本 + 能力协商） |
| `tools/list` | 获取服务端提供的工具列表（含 JSON Schema） |
| `tools/call` | 调用指定工具（参数由 LLM 按 schema 生成） |

---

## 3. 架构

```
┌─────────────────────────────────────────────────────────────┐
│                        Web 管理页                            │
│  (static/mcp.html + static/mcp.js)                          │
└──────────┬──────────────────────────────────────────────────┘
           │ fetch()
           ▼
┌──────────────────────┐     ┌───────────────────────────────┐
│   FastAPI Server      │     │   SQLite (.omo/mcp.db)   │
│                       │     │   mcp_servers / mcp_tools     │
│  /mcp/servers  CRUD   │◄───►│                               │
│  /mcp/tools   list    │     └───────────────────────────────┘
│  /mcp/servers/test    │
└──────────┬────────────┘
           │ 每次 agent 调用时读取配置
           ▼
┌──────────────────────────────────────────────────────────────┐
│  run_agent 节点                                              │
│                                                              │
│  1. 读 SQLite → 获取已启用 MCP server 列表                    │
│  2. 对每个 server → SSE 连接 → tools/list → 获取工具列表      │
│  3. 每个 tool → 包装为 LangChain BaseTool                    │
│  4. create_deep_agent(tools=[sandbox_tools + mcp_tools])     │
└──────────────────────────────────────────────────────────────┘
           │
           ▼
     ┌─────────────┐     ┌──────────────┐
     │  MCP Server 1 │     │  MCP Server 2 │
     │  (HTTP SSE)   │     │  (HTTP SSE)   │
     └───────────────┘     └──────────────┘
```

---

## 4. 组件设计

### 4.1 MCP 客户端

`src/mcp/client.py` — HTTP SSE 客户端，连接远程 MCP server。

```
MCPClient
├── connect(url, timeout)    → SSE 连接（背景线程读 stream）
├── list_tools()             → tools/list → 返回工具定义列表
├── call_tool(name, args)    → tools/call → 返回执行结果
└── disconnect()             → 清理连接
```

**连接生命周期**：
1. `run_agent` 中，遍历已启用的 MCP server，每个 server 实例化一个 `MCPClient`
2. `connect()` 时发起 HTTP GET 到 SSE 端点，收到 `endpoint` 事件后建立 POST 通道
3. SSE 读取在独立线程中运行，JSON-RPC 响应按 `id` 匹配分发
4. 调用完成后 `disconnect()` 清理

**SSE 实现**：不使用第三方 SSE 库，直接用 `httpx` 流式读取：

```python
import httpx

with httpx.Client() as client:
    response = client.get(url, stream=True)
    for line in response.iter_lines():
        # 解析 SSE event/data 格式
        if line.startswith("data:"):
            data = json.loads(line[5:].strip())
```

### 4.2 MCP Tool → BaseTool 适配器

`src/mcp/adapter.py` — 将 MCP 工具包装为 LangChain `BaseTool`。

```python
class MCPTool(BaseTool):
    """LangChain BaseTool — 调用时委托给 MCP server。"""

    mcp_client: MCPClient            # MCP 客户端实例
    mcp_tool_name: str               # MCP 工具名
    mcp_tool_schema: dict            # MCP 的 inputSchema

    # BaseTool 自动从 mcp_tool_schema 推导 args_schema

    def _run(self, **kwargs: Any) -> Any:
        return self.mcp_client.call_tool(self.mcp_tool_name, kwargs)
```

- `name`、`description` 直接从 MCP `tools/list` 响应继承
- `args_schema` 从 MCP `inputSchema`（JSON Schema）推导
- 工具描述中可以追加 MCP source server 标识，帮助 LLM 区分不同来源

### 4.3 持久化

`src/mcp/db.py` — SQLite 存储 MCP server 配置和工具状态。

```sql
CREATE TABLE mcp_servers (
    id TEXT PRIMARY KEY,
    name TEXT NOT NULL,
    url TEXT NOT NULL,                   -- MCP SSE endpoint 完整 URL
    timeout INTEGER DEFAULT 60,
    created_at TEXT DEFAULT (datetime('now')),
    updated_at TEXT DEFAULT (datetime('now'))
);

CREATE TABLE mcp_tools (
    id TEXT PRIMARY KEY,
    server_id TEXT NOT NULL REFERENCES mcp_servers(id) ON DELETE CASCADE,
    name TEXT NOT NULL,
    description TEXT,
    input_schema TEXT,                   -- JSON string
    enabled INTEGER DEFAULT 1,
    UNIQUE(server_id, name)
);
```

数据库文件位置：`.omo/mcp/mcp.db`（遵循 `.omo/sessions/sessions.db` 模式统一到子目录）。

**mcp_tools 的作用**：
- 记录从 MCP server 同步来的工具列表
- 用户可以在 Web 页面启用/禁用单个工具
- `enabled=0` 的工具不会注入到 agent

### 4.4 API 端点

`src/mcp/router.py` — FastAPI 路由，注册到 `api.py`。

| 方法 | 路径 | 说明 |
|------|------|------|
| GET | `/mcp/servers` | 列出所有已注册的 MCP server |
| POST | `/mcp/servers` | 添加一个新的 MCP server |
| PUT | `/mcp/servers/{id}` | 更新 MCP server 配置 |
| DELETE | `/mcp/servers/{id}` | 删除 MCP server（级联删除工具） |
| POST | `/mcp/servers/{id}/test` | 测试连接：连接 MCP server 并调用 tools/list 看是否成功 |
| POST | `/mcp/servers/{id}/sync` | 从 MCP server 同步工具列表 |
| GET | `/mcp/tools` | 列出所有已发现的工具（含启用状态） |
| PUT | `/mcp/tools/{id}` | 切换工具启用/禁用状态 |

### 4.5 集成点

在 `src/agent/nodes.py` 的 `run_agent` 函数中，`create_deep_agent()` 调用之前加入 MCP 工具加载：

```python
def run_agent(state: SandboxAgentState) -> dict[str, Any]:
    llm = ChatOpenAIWithReasoning(...)

    if state.get("sandbox_id"):
        client = SandboxClient()
        sb = client.get_sandbox(name=state["sandbox_id"])
        backend = LangSmithBackend(sb)

        # ── MCP 工具加载 ─────────────────────────────────
        mcp_additional_tools: list[BaseTool] = []
        try:
            from src.mcp.db import get_enabled_tools
            from src.mcp.adapter import mcp_tools_for_server

            for server in get_enabled_servers():
                mcp_tools = mcp_tools_for_server(server)
                mcp_additional_tools.extend(mcp_tools)
        except Exception as e:
            print(f"[MCP] 加载 MCP 工具失败: {e}")

        agent = create_deep_agent(
            model=llm,
            backend=backend,
            tools=mcp_additional_tools or None,
            system_prompt=(
                "You are a helpful coding assistant with filesystem access "
                "via a sandbox.\n\n"
                "OUTPUT FILES:\n"
                "- User's uploaded files are at /workspace/input/\n"
                "- ALWAYS save all generated output files to /workspace/output/\n"
                "- The system will automatically deliver /workspace/output/ files to the user"
            ),
            checkpointer=MemorySaver(),
        )

        result = agent.invoke(...)
        return {"messages": result["messages"]}
    # ... route B unchanged
```

加载时机：**每次 agent 调用时**（而非启动时），因为 MCP server 配置可能实时变更。

### 4.6 Web UI

`static/mcp.html` + `static/mcp.js` — 管理页面，通过 `/mcp/` 访问。

功能布局：

| 功能 | 操作 |
|------|------|
| Server 列表 | 展示名称、URL、状态、操作按钮 |
| 添加 Server | 表单：名称、URL（SSE 端点）、超时 |
| 编辑 Server | 同添加表单，预填现有值 |
| 删除 Server | 确认后删除，级联删除工具 |
| 测试连接 | 尝试连接并 `tools/list`，反馈成功/失败 |
| 同步工具 | 从 server 拉取最新 tool 列表 |
| 工具列表 | 展示所有 server 的所有工具，每行有启用/禁用开关 |

---

## 5. 实现步骤

| 步骤 | 文件 | 内容 |
|------|------|------|
| 1 | `src/mcp/client.py` | HTTP SSE 客户端（connect/list_tools/call_tool/disconnect） |
| 2 | `src/mcp/adapter.py` | MCPTool(BaseTool) 适配器 |
| 3 | `src/mcp/db.py` | SQLite CRUD（servers + tools） + 建表 |
| 4 | `src/mcp/router.py` | FastAPI 路由（8 个端点） |
| 5 | `src/agent/nodes.py` | run_agent 集成 MCP 工具加载 |
| 6 | `api.py` | 注册 `/mcp/` 路由 + 静态文件 |
| 7 | `static/mcp.html` | 页面结构 |
| 8 | `static/mcp.js` | 交互逻辑（CRUD + 测试 + 同步 + 开关） |
| 9 | `AGENTS.md` | 更新文档铁律：MCP 相关约束 |
| 10 | `pyproject.toml` | 如有新增依赖（httpx/sse 相关） |

依赖评估：
- `httpx` — 已通过 `opensandbox` 间接依赖 ✅
- `sse-starlette` — 可选（后端无需 SSE，前端也不需要）

---

## 6. 边界场景

| 场景 | 处理策略 |
|------|----------|
| server 连接失败 | 记录错误，跳过该 server，不影响其他 server 和主流程 |
| server 中途断连 | 工具调用返回错误，LLM 自行决定是否重试 |
| tool 调用超时 | 按 `timeout` 配置（默认 60s），超时抛异常 |
| tool 调用报错 | 透传错误信息给 LLM |
| 同名 tool 冲突 | server 维度隔离，不同 server 允许同名 |
| 无 MCP 配置 | 空列表，走现版本逻辑 |
| MCP server 返回不标准 | `call_tool` 结果提取 `result.content`，非标准格式兜底 |

---

## 8. Skills 系统实现

> 版本：v1 — 2026-06-02 实施完成

### 8.1 架构

```
宿主机                         沙箱
───────                       ────────
.omo/skills/             /home/user/.omo/skills/
  ├── python-output/            ├── python-output/
  │   └── SKILL.md     ──upload──└── SKILL.md
  └── web-research/             └── web-research/
      └── SKILL.md                  └── SKILL.md
                                        │
                                  SkillsMiddleware
                                  ├── backend.ls() 扫描子目录
                                  ├── backend.download_files() 读 SKILL.md
                                  └── 解析 YAML frontmatter → 注入 system prompt
                                        │
                                  create_deep_agent(skills=[SA_SKILLS_ROOT])
```

### 8.2 组件

#### `src/skills/loader.py`

两个函数 + 一个常量：

| 符号 | 作用 |
|------|------|
| `SA_SKILLS_ROOT = "/home/user/.omo/skills"` | 沙箱内技能文件根目录 |
| `discover_skills()` | 扫描宿主机 `.omo/skills/*/SKILL.md`，返回 `[{name, content}]` |
| `upload_skills_to_sandbox(backend, skills)` | 调用 `backend.upload_files()` 上传到沙箱，返回根路径 |

`discover_skills()` 在宿主机执行（`run_agent` 节点内），读本地文件系统。结果传给 `upload_skills_to_sandbox()` 上传到沙箱。

#### `src/agent/nodes.py` — 集成点

在 `create_deep_agent()` 调用前插入：

```python
# ── Skills loading ──
sa_skills_root: str | None = None
try:
    from src.skills.loader import discover_skills, upload_skills_to_sandbox
    skills_list = discover_skills()
    if skills_list:
        sa_skills_root = upload_skills_to_sandbox(backend, skills_list)
        skill_names = [s["name"] for s in skills_list]
        print(f"[Skills] Loaded {len(skills_list)} skills: {skill_names}")
except Exception as e:
    print(f"[Skills] Failed to load skills: {e}")

agent = create_deep_agent(
    model=llm,
    backend=backend,
    skills=[sa_skills_root] if sa_skills_root else None,
    ...
)
```

关键：`create_deep_agent(skills=...)` 接受 `list[str]`（沙箱内目录路径），不是 `list[dict]`。

### 8.3 SkillsMiddleware 运行机制

SkillsMiddleware 是 deepagents 原生中间件，注册在 agent 的 middleware 栈中。

**加载阶段**（`before_agent`，每会话一次）：

```
skills=[SA_SKILLS_ROOT]
  │
  ├─ backend.ls(SA_SKILLS_ROOT)
  │     → 返回子目录列表: ["python-output/", "web-research/"]
  │
  ├─ backend.download_files(["python-output/SKILL.md", "web-research/SKILL.md"])
  │     → 读取每个 SKILL.md 的原始内容
  │
  ├─ 解析 YAML frontmatter（正则匹配 ^---\\n(.*?)\\n---\\n）
  │     → 提取 name / description / allowed-tools / metadata 等
  │
  └─ 存入 state["skills_metadata"] 供后续使用
```

**注入阶段**（`before_model`，每次 LLM 调用）：

```
state["skills_metadata"]
  └─ _format_skills_list()
       → 格式化为 system prompt 片段:

          ## Skills System
          ...
          **Available Skills:**
          - **python-output**: Best practices for formatting Python script output
            -> Read /home/user/.omo/skills/python-output/SKILL.md for full instructions
          ...
          
          **How to Use Skills (Progressive Disclosure):**
          1. Recognize when a skill applies
          2. Read the skill's full instructions: use read_file on the path
          3. Follow the skill's instructions
```

**渐进式披露**设计要点：
- 技能正文**不会**自动注入 system prompt（避免 token 膨胀）
- agent 根据任务自主判断是否需要读哪个技能文件
- 需要 agent 主动调用 `read_file(path)` 来获取完整指令

### 8.4 SKILL.md 格式要求

```markdown
---
name: python-output
description: Best practices for formatting Python script output in sandbox
# 可选字段：
# allowed-tools:
#   - read_file
#   - write_file
# metadata:
#   author: team-x
# compatibility: ">=0.6.0"
# license: MIT
---

# Skill Title

## Instructions
(技能正文，agent 读取后执行的指令)
```

**必须字段：**
- `name` — 技能名称，用于在 system prompt 中标识
- `description` — 技能描述，agent 据此判断技能是否适用

**约束：**
- `name` ≤ 100 字符
- `description` ≤ 200 字符
- SKILL.md 总大小 ≤ 64KB
- `allowed-tools` 限定技能可用的工具名列表（可选）

### 8.5 边界场景

| 场景 | 处理 |
|------|------|
| `.omo/skills/` 不存在 | `discover_skills()` 返回 `[]`，静默跳过 |
| 目录下没有 SKILL.md | 记录 warning，跳过该目录 |
| YAML frontmatter 缺少 name/description | 记录 warning，跳过该技能 |
| SKILL.md 编码非 UTF-8 | 记录 warning，跳过 |
| `backend.upload_files()` 不支持 | fallback 走 `_sandbox.write()` |
| backend 不支持文件上传 | 记录 warning，技能不影响 agent 运行 |
| 同名技能 | 后加载的覆盖先加载的（SkillsMiddleware 内部 `dict` 去重） |

### 8.6 与 MCP 的关系

Skills 和 MCP 是两个独立的系统，在 `run_agent` 节点中并行加载：

```
run_agent:
  ├── MCP 工具加载 → tools=[mcp_tools] (src/mcp/)
  ├── Skills 加载  → skills=[sa_skills_root] (src/skills/)
  └── create_deep_agent(tools=..., skills=..., ...)
```

互不依赖，互不阻塞。一个失败不影响另一个。

