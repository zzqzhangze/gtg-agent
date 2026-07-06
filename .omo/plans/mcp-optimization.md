# MCP 集成优化实施计划

> status: completed (P0+P1.1~1.3 done; P1.4 cancelled — 连接缓存已满足效率需求，跨进程 session 复用复杂度高收益低)
> branch: feat/mcp-optimization
> created: 2026-07-06
> updated: 2026-07-06

**设计文档**: `docs/design/mcp-optimization-plan.md`

**提交记录**:
- `b591ba1` feat: MCP connection cache, parallel loading, and Route B tool support
- `ab4ffb1` docs: register mcp-optimization plan

---

## 任务分解

### Task 1: MCP 连接缓存 + 多 Server 并行连接

**目标**: `build_tools_for_server()` 每次都 `new MCPClient()` → `connect()`，同一 server 在同一次 agent 调用中被多次连接；且多个 server 串行连接，一个超时卡住全部。

- [x] **1.1 adapter.py: 添加模块级连接缓存 `_CLIENT_CACHE`**
  - key: `(server_name, url)` → `MCPClient`
  - `build_tools_for_server()` 先从缓存取，未命中则创建
  - 同时添加 `clear_client_cache()` 供外部清理

- [x] **1.2 adapter.py: `build_tools_for_server()` 支持可选复用 client**
  - 新 client 创建后入缓存，后续同名 server 直接拿已有 client
  - 缓存的 client 保持连接状态，MCPTool 持有引用可正常调用

- [x] **1.3 nodes.py: 两处 MCP 加载改为 `_load_mcp_tools()` 并行加载**
  - 提取 `_load_mcp_tools()` 辅助函数，内部用 ThreadPoolExecutor 并行连接所有 server
  - 同时替换 Route A 和 `run_agent_with_mcp` 中的串行循环

### Task 2: Route B（chat/compute）加载 MCP 工具

**目标**: `run_agent` 的 Route B（无沙箱）目前裸 `llm.invoke()`，不加载 MCP 工具。

- [x] **2.1 nodes.py: Route B 缺省分支中加载 MCP 工具**
  - 调用 `_load_mcp_tools()` 加载工具
  - 有工具 → `create_deep_agent(tools=...)` 执行
  - 无工具 → 回退 `llm.invoke()`（保留原有行为）

### Task 3: Route A 中 Skills 和 MCP 并行加载

**目标**: `run_agent` Route A 中 Skills loading 和 MCP tools loading 串行。

- [x] **3.1 nodes.py: 用 ThreadPoolExecutor 并行化 Skills 和 MCP 加载**
  - 2-worker pool 同时跑 Skills 上传和 MCP 工具加载
  - 各自独立 try/except，一个失败不影响另一个

### Task 4: session_id 持久化

**目标**: 将 MCPClient 的 session_id（streamable HTTP）存到 `mcp_servers` 表。

- [ ] ~~4.1~4.3~~ **已取消** — 原因：
  - 模块级 `_CLIENT_CACHE` 已解决同一 agent 调用内的重复连接问题
  - 跨调用复用 session_id 需修改 `connect()` 核心路径，增加脆弱性
  - streamable HTTP session 可能被服务端随时过期，收益不确定
  - 当前方案是更稳的 trade-off

### Task 5：验证

**目标**: 确保改动不会引入语法错误或破坏现有行为。

- [x] **5.1 Python 语法检查**: `py_compile src/agent/nodes.py src/mcp/adapter.py` ✅ 通过
- [ ] **5.2 已有测试通过**: `pytest tests/ -v` ⚠️ 预存 `deepagents` 模块缺失（非本次引入）
