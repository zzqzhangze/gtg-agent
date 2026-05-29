# Agent — 架构与开发规范

## 项目结构

```
my_deep_agent/
├── config.env                  # 环境变量配置
├── main.py               # 命令行入口
├── api.py                # FastAPI 服务入口
├── Agent.md              # 本文档：架构 + 开发规范
├── README.md             # 项目说明
├── pyproject.toml        # 项目配置与依赖
├── uv.lock               # 依赖版本锁定
└── src/                  # 核心源代码目录
    ├── __init__.py
    ├── sandbox/          # 沙箱接口层
    │   ├── __init__.py
    │   ├── client.py     # 异步线程循环、LocalSandbox、SandboxClient
    │   └── backend.py    # DeepAgents 协议适配器（LangSmithBackend）
    └── agent/            # Agent 编排层
        ├── __init__.py
        ├── state.py      # LangGraph 状态定义
        ├── nodes.py      # 各处理节点（车间）
        └── graph.py      # 图编排（传送带）
```

---

## 工作流

```
START
  │
  ▼
analyze_intent ──→ [纯聊天] ──→ run_agent ──→ END
  │                                  │
  [需要沙箱]                       run_agent
  │                                  │
  ▼                                  ▼
create_sandbox → upload_files → run_agent → download_files → cleanup_sandbox → END
```

---

## 核心概念

| 术语 | 解释 |
|------|------|
| **State** | LangGraph 状态，在节点间传递。定义在 `state.py` |
| **Node** | 处理节点，接收 State → 处理 → 返回 State 更新。定义在 `nodes.py` |
| **Edge** | 节点间的连接，决定数据流向。定义在 `graph.py` |
| **Sandbox** | Docker 隔离环境，代码在其中安全执行 |

---

## 文档维护规范

### README.md

面向 **新用户**。必须包含：

1. **一句话说明** — 这个项目做什么
2. **架构图** — 文字流程图，展示核心工作流
3. **快速开始** — 安装 → 配置 → 运行，三步内能跑起来
4. **项目结构** — 目录树，标注每个文件的作用
5. **API 文档**（如果有 API）— 端点列表，请求示例

修改 graph 流程或新增节点时，必须同步更新架构图和流程说明。

### Agent.md

面向 **开发者**。必须包含：

1. **项目结构** — 当前目录树
2. **工作流** — 当前图的完整流程
3. **核心概念** — State / Node / Edge / Sandbox 的定义
4. **文档维护规范**（本文）
5. **开发原则**（见下）

新增模块、修改架构、变更流程时必须更新 Agent.md。

### docs/

面向 **后续优化升级**。

- `docs/deployment-alternatives.md` — 部署方案备选，新增方案时追加
- 后续新增 spec、设计文档按 `docs/superpowers/specs/YYYY-MM-DD-<topic>-design.md` 命名

### 基本原则

- **README.md 和 Agent.md 永远保持最新**。改了代码没改文档 = 没改完。
- **README.md 删除比添加更难**。功能废弃后记得删对应的文档。
- **文档不写实现细节**。只说"做什么"和"怎么用"，不说"怎么做"。
- **代码注释写 Why，不写 What**。`x += 1  # 计数器加1` 是废话；`x += 1  # 跳过 BOM 头` 是有用的。

---

## 开发原则

### 扩展工作流

新增一个节点（车间）的步骤：

1. `state.py` — 加字段（如果节点需要读写新数据）
2. `nodes.py` — 写节点函数 `def my_node(state: SandboxAgentState) -> dict[str, Any]:`
3. `graph.py` — `add_node()` + `add_edge()` 注册和连线
4. `README.md` / `Agent.md` — 更新架构图和流程说明

### 沙箱操作

- **永远不要**在宿主机直接执行用户代码。
- 所有文件传输通过 `LocalSandbox.read()` / `write()` 走 Docker 沙箱 API。
- `cleanup_sandbox` 是**强制必经之路**，新加的沙箱相关节点必须在它之前。

### 错误处理

- 每个节点都要处理异常，不能因为一个节点的失败阻塞整个图。
- 网络断开检测（`"All connection attempts failed"`）必须保留，防止无限重试。
- 使用 `print()` 记录关键日志（生产可改为 `logging`）。

### 测试

- 核心逻辑（`analyze_intent`、`route_after_analysis`）应该有单元测试。
- 图集成测试可以用 mock 沙箱，不需要真实 Docker。
- 新增节点时同步加测试。

### 依赖管理

- 使用 `uv` 管理依赖。
- `pyproject.toml` 只列直接依赖，传递依赖由 `uv.lock` 锁定。
- 加新依赖前确认：**是不是可以在现有依赖上实现？**
