# Agent — 开发规范

> 项目结构和工作流见 [README.md](README.md)。本文档面向需要修改代码的开发者。

---

## 核心概念

| 术语 | 说明 |
|------|------|
| **State** | LangGraph 状态，在节点间传递。定义在 `src/agent/state.py` |
| **Node** | 处理节点，接收 State → 处理 → 返回 State 更新。定义在 `src/agent/nodes.py` |
| **Edge** | 节点间的连接，决定数据流向。定义在 `src/agent/graph.py` |
| **Sandbox** | Docker 隔离环境，代码在其中安全执行。接口在 `src/sandbox/` |

---

## 文档维护规范

| 文件 | 读者 | 内容 |
|------|------|------|
| `README.md` | 用户 | 项目说明、架构图、快速开始、API |
| `Agent.md` | 开发者 | 开发原则、代码规范、本文 |
| `docs/` | 未来 | 备选方案、设计决策 |

基本原则：

- **改了代码没改文档 = 没改完。**
- 文档只写"做什么"和"怎么用"，不写"怎么做"。
- 代码注释写 Why，不写 What：
  - `x += 1  # 计数器加1` → 废话
  - `x += 1  # 跳过 BOM 头` → 有用

---

## 开发原则

### 扩展工作流（加节点）

1. `state.py` — 加字段（如果新节点需要读写新数据）
2. `nodes.py` — 写节点函数 `def my_node(state: SandboxAgentState) -> dict[str, Any]:`
3. `graph.py` — `add_node()` + `add_edge()` 注册和连线
4. `README.md` — 更新架构图和流程说明

### 沙箱操作

- **永远不要**在宿主机直接执行用户代码。
- 所有文件传输通过 `LocalSandbox.read()` / `write()` 走 Docker 沙箱 API。
- `cleanup_sandbox` 是强制必经之路，新加的沙箱相关节点必须在它之前。

### 错误处理

- 每个节点都要处理异常，不能因为一个节点的失败阻塞整个图。
- 网络断开检测（`"All connection attempts failed"`）必须保留，防止无限重试。
- 使用 `print()` 记录关键日志（生产可改为 `logging`）。

### 测试

- 核心逻辑（`analyze_intent`、`route_after_analysis`）应有单元测试。
- 图集成测试可用 mock 沙箱，不需要真实 Docker。
- 新增节点时同步加测试。

### 依赖管理

- 使用 `uv` 管理依赖。
- `pyproject.toml` 只列直接依赖，传递依赖由 `uv.lock` 锁定。
- 加新依赖前确认：**是否可以在现有依赖上实现？**

### CLAD.md / AGENTS.md

当前项目未使用。若未来引入：

- `CLAD.md` 放你对这个项目的偏好（命名风格、架构倾向等）
- `AGENTS.md` 放给 AI 的全局性工作指令

优先级：CLAD.md > Agent.md > README.md > 代码注释。
