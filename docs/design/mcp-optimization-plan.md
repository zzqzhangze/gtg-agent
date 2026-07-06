# MCP 集成优化方案

> 基于当前 MCP 集成实现（feat/mcp-integration）的分析。
> 记录角度：Agent 智能化 + 执行效率。

---

> ⚡ **实现状态（feat/mcp-optimization, 2026-07-06）**：
> P0 ✅、P1.1 ✅、P1.2 ✅、P1.3 ✅、P1.4 ❌（已取消）
> 合并请求参考 [feat/mcp-optimization 分支](.)。

---

## P0 — 功能缺陷（必须修）✅

### MCP 工具被沙箱路径绑架

**现状**：

```
analyze_intent
  ├─ chat / compute → Route B → run_agent（无沙箱）
  │                              └─ llm.invoke()           ← ❌ 不加载 MCP 工具
  └─ code_exec / ... → Route A → create_sandbox → run_agent（有沙箱）
                                                   └─ create_deep_agent(tools=MCP)  ← ✅ 有 MCP
```

`build_tools_for_server()` 只在 `run_agent` 的沙箱分支中调用（原 `nodes.py:427`）。
如果 `analyze_intent` 把用户请求分类为 `chat` 或 `compute`，走 Route B（裸 `llm.invoke()`），**MCP 工具完全不加载**，LLM 看不到它们。

**后果**：用户连好 MCP 工具后问"现在几点"，因为分类为 `chat`，LLM 回答"我不知道"而不是调 `get_current_time`。

**实现**：

1. 提取共享辅助函数 `_load_mcp_tools()`（`nodes.py`）— 内部用 `ThreadPoolExecutor` 并行连接所有已启用 server，返回 `list[BaseTool]`
2. Route B 中加载 MCP 工具：
   - 有工具 → `create_deep_agent(tools=mcp_tools)` 执行（复用 `run_agent_with_mcp` 模式，提供完整 agent 循环和 tool calling 能力）
   - 无工具 → 回退 `llm.invoke()`（保留原有行为）
3. Route A 和 `run_agent_with_mcp` 也改用 `_load_mcp_tools()`，消除重复的串行循环

> **为什么不用 `bind_tools`？** `create_deep_agent` 提供了一致的 agent 包装（工具调用循环、错误处理、结构化输出），`bind_tools` 只绑定工具到一次 invoke，如果需要多轮交互（工具调工具）就不够。

**涉及文件**：`src/agent/nodes.py`（run_agent 函数）

---

## P1 — 效率浪费（应该修）

### 1. 每次对话都重建 MCP 连接 ✅

**现状**：`build_tools_for_server()` 每次调用都 `new MCPClient()` → `connect()`（`initialize` 握手 + 拿 session_id）。用户每发一条消息，agent 每跑一轮，都会重新握手。

**后果**：n 条消息 = n 次 initialize 往返，MCP 服务端创建 n 个 session。

**实现**（`src/mcp/adapter.py`）：

```
_CLIENT_CACHE: dict[tuple[str, str], MCPClient]  ← 模块级 dict，key=(server_name, url)
```

- `build_tools_for_server()` 先从缓存查，命中直接复用 client（连接已建立，tool list 已就绪）
- 未命中则创建新 client → connect → 获取 tool list → 入缓存
- 新增 `clear_client_cache()` 清空所有缓存连接（供 Web UI "断开连接"调用）
- 使用 `tool_cache_key` 参数区分调用方：相同 server 在不同调用场景不会互相污染

> **为什么不用 LRU？** 单次 agent 调用周期极短，模块级 dict 即可覆盖重用场景；LRU 的过期策略在当前架构下不增加价值。

### 2. MCP 与 Skills 串行加载 ✅

**现状**（原 `nodes.py:411-443`）：Skills 上传完成 → MCP 工具加载，两者无依赖却串行等待。

**实现**：Route A 中用 `ThreadPoolExecutor(max_workers=2)` 同时提交 Skills 加载和 MCP 工具加载两个 task：

```python
with ThreadPoolExecutor(max_workers=2) as pool:
    skills_future = pool.submit(_load_skills, ...)    # 上传 Skills 到沙箱
    mcp_future = pool.submit(_load_mcp_tools, ...)     # 并行连接 MCP server
    skills_result = skills_future.result()
    mcp_tools = mcp_future.result()
```

各自有独立 `try/except`，一个失败不影响另一个。

### 3. 多 MCP Server 串行连接 ✅

**现状**：`for server in get_enabled_servers(): build_tools_for_server(server)` — 逐个连接，一个超时卡住后面所有。

**实现**：共享函数 `_load_mcp_tools()` 内部使用 `ThreadPoolExecutor` 并行连接所有 server，每个 server 独立超时：

```python
def _load_mcp_tools(...) -> list[BaseTool]:
    servers = get_enabled_servers()
    with ThreadPoolExecutor(max_workers=len(servers)) as pool:
        futures = {pool.submit(build_tools_for_server, s): s for s in servers}
        for future in as_completed(futures):
            try:
                tools.extend(future.result(timeout=30))
            except Exception:
                log(f"Server {futures[future]} failed")
    return tools
```

该函数同时替换 Route A 和 `run_agent_with_mcp` 中的原始串行循环。

### 4. 无连接状态缓存 ❌（已取消）

**现状**：`MCPClient` 实例用完即丢（GC 回收），session_id 不持久化。

**取消原因**：
- 模块级 `_CLIENT_CACHE` 已覆盖单次 agent 调用内的重复连接问题（P1.1）
- 跨调用复用 session_id 需要修改 `MCPClient.connect()` 核心路径，增加脆弱性
- streamable HTTP session 可能被服务端随时过期，收益不确定
- 当前方案（缓存 client 实例 + 进程级缓存）是更稳的 trade-off

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

| 编号 | 维度 | 影响面 | 实现成本 | 优先级 | 状态 |
|------|------|--------|---------|--------|------|
| P0 | chat/compute 无 MCP 工具 | 功能缺失 | 中（~40 行 + 提取共享函数） | 🔴 **最高** | ✅ |
| P1.1 | 重复连接 | 效率 | 中（模块级 dict 缓存） | 🟡 | ✅ |
| P1.2 | Skills/MCP 串行 | 效率 | 低（并行加载） | 🟡 | ✅ |
| P1.3 | 多 Server 串行 | 效率 | 低（ThreadPool） | 🟡 | ✅ |
| P1.4 | 无连接缓存 | 效率 | 中（DB 存 session） | 🟢 | ❌ 取消 |
| P2.1 | 失败可恢复 | 体验 | 低 | 🟢 | ⏳ |
| P2.2 | 异步/流式 | 体验 | 高（架构改动） | 🟢 | ⏳ |
| P2.3 | 工具透明化 | 可观测性 | 中 | 🟢 | ⏳ |
| P2.4 | 意图感知 MCP | 准确率 | 低 | 🟢 | ⏳ |

---

## 涉及文件清单

| 文件 | 实际变更 |
|------|---------|
| `src/agent/nodes.py` | P0 ✅、P1.2 ✅、P1.3 ✅ — `_load_mcp_tools()` 共享函数、Route B MCP 工具、Route A Skills/MCP 并行 |
| `src/mcp/adapter.py` | P1.1 ✅ — 模块级 `_CLIENT_CACHE`、`build_tools_for_server()` 缓存逻辑、`clear_client_cache()` |
| `src/mcp/client.py` | 无变更（缓存由 adapter.py 管理，无需修改 client） |
| `src/mcp/db.py` | 无变更（P1.4 取消） |
| `src/mcp/router.py` | 无变更（当前缓存生命周期由 process 管理，不需要 router 介入） |
| `src/agent/graph.py` | 无变更（路由逻辑不需要修改） |
