# MCP 集成优化方案

> 基于当前 MCP 集成实现（feat/mcp-integration）的分析。
> 记录角度：Agent 智能化 + 执行效率。

---

## P0 — 功能缺陷（必须修）

### MCP 工具被沙箱路径绑架

**现状**：

```
analyze_intent
  ├─ chat / compute → Route B → run_agent（无沙箱）
  │                              └─ llm.invoke()           ← ❌ 不加载 MCP 工具
  └─ code_exec / ... → Route A → create_sandbox → run_agent（有沙箱）
                                                   └─ create_deep_agent(tools=MCP)  ← ✅ 有 MCP
```

`build_tools_for_server()` 只在 `run_agent` 的沙箱分支（`src/agent/nodes.py:389`）中调用。
如果 `analyze_intent` 把用户请求分类为 `chat` 或 `compute`，走 Route B（裸 `llm.invoke()`），**MCP 工具完全不加载**，LLM 看不到它们。

**后果**：用户连好 MCP 工具后问"现在几点"，因为分类为 `chat`，LLM 回答"我不知道"而不是调 `get_current_time`。

**方案**：Route B 也要加载 MCP 工具，用 LLM 原生的 `bind_tools` / function calling 直接执行，不经过沙箱。

```python
# Route B 伪代码
mcp_tools = load_enabled_mcp_tools()
if mcp_tools:
    llm_with_tools = llm.bind_tools(mcp_tools)
    response = llm_with_tools.invoke(state["messages"])
    # 如果 LLM 选择调 tool → 执行 → 返回结果
    # 否则 → 返回纯文本
else:
    response = llm.invoke(state["messages"])
```

**涉及文件**：`src/agent/nodes.py`（run_agent 函数）

---

## P1 — 效率浪费（应该修）

### 1. 每次对话都重建 MCP 连接

**现状**：`build_tools_for_server()` 每次调用都 `new MCPClient()` → `connect()`（`initialize` 握手 + 拿 session_id）。用户每发一条消息，agent 每跑一轮，都会重新握手。

**后果**：n 条消息 = n 次 initialize 往返，MCP 服务端创建 n 个 session。

**方案**：模块级 LRU 缓存或按 server URL + session 维度的连接池。缓存生命周期与 Web UI 中"断开连接"操作绑定。

### 2. MCP 与 Skills 串行加载

**现状**（`src/agent/nodes.py:394-420`）：

```python
# ── Skills loading ──           # 等 Skills 加载完
...
# ── MCP tools loading ──        # 再等 MCP 加载完
...
```

两者无依赖，可以并行。

**方案**：用 `threading.Thread` 或 `concurrent.futures` 让 Skills 和 MCP 同时加载。

### 3. 多 MCP Server 串行连接

**现状**：`for server in get_enabled_servers(): build_tools_for_server(server)` — 逐个连接，一个超时卡住后面所有。

**方案**：用 `concurrent.futures.ThreadPoolExecutor` 并行连接，设置独立超时。

### 4. 无连接状态缓存

**现状**：`MCPClient` 实例用完即丢（GC 回收），session_id 不持久化。

**方案**：将 session_id 存入 `mcp_tools` 或 `mcp_servers` 表，下次启动时复用（对 streamable HTTP 有效）。

---

## P2 — 智能化提升（锦上添花）

### 1. 工具调用失败可恢复

**现状**：`MCPTool._run()` 抛异常直接冒泡，LLM 收不到结构化错误信息，没有重试机会。

**方案**：在 `_run()` 中 catch 异常，返回格式化的错误文本（如 `[MCP Error: add_numbers - Connection refused]`），让 LLM 能据此给出解释或尝试其他策略。

### 2. 异步 / 流式支持

**现状**：`_run()` 是同步的。长时间运行的 MCP 工具（如文件处理、数据查询）阻塞整个 agent。

**方案**：
- 实现 `_arun()`（async version）
- 对大响应使用 SSE 流式消费，边收边返回

### 3. 工具使用透明化

**现状**：LLM 调了 MCP 工具后，结果是纯文本塞回消息流，没有"已调用了工具 X"的显式标记。

**方案**：在消息中插入结构化工具调用记录（类似 LangChain 的 `AIMessage.tool_calls`），让后续对话轮次能感知历史工具调用。

### 4. 意图分析感知 MCP 工具

**现状**：`analyze_intent` 的 prompt 里没有 MCP 工具的信息，分类时不知道有哪些工具可用。

**方案**：在 `_INTENT_SYSTEM_PROMPT` 中动态注入已启用的 MCP 工具列表，让意图分类更精确。

---

## 优先级矩阵

| 编号 | 维度 | 影响面 | 实现成本 | 优先级 |
|------|------|--------|---------|--------|
| P0 | chat/compute 无 MCP 工具 | 功能缺失 | 低（~20 行） | 🔴 **最高** |
| P1.1 | 重复连接 | 效率 | 中（缓存层） | 🟡 |
| P1.2 | Skills/MCP 串行 | 效率 | 低（并行加载） | 🟡 |
| P1.3 | 多 Server 串行 | 效率 | 低（ThreadPool） | 🟡 |
| P1.4 | 无连接缓存 | 效率 | 中（DB 存 session） | 🟢 |
| P2.1 | 失败可恢复 | 体验 | 低 | 🟢 |
| P2.2 | 异步/流式 | 体验 | 高（架构改动） | 🟢 |
| P2.3 | 工具透明化 | 可观测性 | 中 | 🟢 |
| P2.4 | 意图感知 MCP | 准确率 | 低 | 🟢 |

---

## 涉及文件清单

| 文件 | 相关优化 |
|------|---------|
| `src/agent/nodes.py` | P0（Route B 加 MCP）、P1.2（并行加载） |
| `src/mcp/adapter.py` | P2.1（异常处理）、P2.2（异步） |
| `src/mcp/client.py` | P1.1（连接缓存）、P1.4（session 持久化） |
| `src/mcp/db.py` | P1.4（session_id 字段） |
| `src/mcp/router.py` | P1.1（连接生命周期管理） |
| `src/agent/graph.py` | P0（路由逻辑） |
