# MCP 集成优化实施计划

> status: in_progress
> branch: feat/mcp-optimization
> created: 2026-07-06
> updated: 2026-07-06

**设计文档**: `docs/design/mcp-optimization-plan.md`

---

## 任务分解

### Task 1: MCP 连接缓存 + 多 Server 并行连接

**目标**: `build_tools_for_server()` 每次都 `new MCPClient()` → `connect()`，同一 server 在同一次 agent 调用中被多次连接；且多个 server 串行连接，一个超时卡住全部。

- [ ] **1.1 adapter.py: 添加模块级连接缓存 `_CLIENT_CACHE`**
  - key: `(server_name, url)` → `MCPClient`
  - `build_tools_for_server()` 先从缓存取，未命中则创建
  - 注意：缓存仅限于单次 agent 调用周期（模块级变量会自动随进程存活，但同一个 agent 调用内重复 `get_enabled_servers()` 的场景可受益）

- [ ] **1.2 adapter.py: `build_tools_for_server()` 支持可选复用 client**
  - 因为 `MCPTool.from_mcp_definition()` 持有 `mcp_client` 引用，缓存的 client 必须保持连接
  - 策略：新 client 创建后入缓存，后续同名 server 直接拿已有 client

- [ ] **1.3 nodes.py: 两处 `for server in get_enabled_servers()` 改为 ThreadPoolExecutor 并行**
  - Route A（沙箱路径）— nodes.py:434
  - Route C（run_agent_with_mcp）— nodes.py:497

### Task 2: Route B（chat/compute）加载 MCP 工具

**目标**: `run_agent` 的 Route B（无沙箱）目前裸 `llm.invoke()`，不加载 MCP 工具。

- [ ] **2.1 nodes.py: Route B 缺省分支中加载 MCP 工具**
  - 复用与 Route A 相同的 MCP 加载逻辑（加载 `mcp_additional_tools`）
  - 如有工具 → 用 `create_deep_agent(tools=mcp_additional_tools)` 执行（同 `run_agent_with_mcp` 模式）
  - 如无工具 → 回退 `llm.invoke()`（现有行为）

### Task 3: Route A 中 Skills 和 MCP 并行加载

**目标**: `run_agent` Route A 中 Skills loading 和 MCP tools loading 串行（先等 Skills 上传完，再等 MCP 握手）

- [ ] **3.1 nodes.py: 用 ThreadPoolExecutor 并行化 Skills 和 MCP 加载**
  - 两个 task 分别加载 Skills 和 MCP tools
  - 各自有独立 try/except，一个失败不影响另一个
  - 合并结果后传给 `create_deep_agent()`

### Task 4: session_id 持久化

**目标**: 将 MCPClient 的 session_id（streamable HTTP）存到 `mcp_servers` 表，下次连接时复用。

- [ ] **4.1 db.py: mcp_servers 表加 mcp_session_id 列（ALTER TABLE 迁移）**
- [ ] **4.2 db.py: 新增 `update_server_session()` 函数**
- [ ] **4.3 client.py: connect() 接受可选 `session_id` 参数，初始化时带上**
  - streamable-http 模式下，首次 initialize 带上 session_id 尝试复用
  - 服务端拒绝则重新 initialize

### Task 5：验证

**目标**: 确保改动不会引入语法错误或破坏现有行为

- [ ] **5.1 Python 语法检查**: `py_compile` 所有改动文件
- [ ] **5.2 已有测试通过**: `pytest tests/ -v`
