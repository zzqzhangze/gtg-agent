# 贡献指南

## 扩展工作流（加节点）

```
1. state.py   → 加字段
2. nodes.py   → 写节点函数
3. graph.py   → add_node() + add_edge() 注册
4. README.md  → 更新架构图和流程说明
```

## 核心概念

| 术语 | 定义位置 | 说明 |
|------|----------|------|
| **State** | `src/agent/state.py` | LangGraph 共享状态 |
| **Node** | `src/agent/nodes.py` | 处理节点函数 |
| **Edge** | `src/agent/graph.py` | 节点连线与路由 |
| **Sandbox** | `src/sandbox/` | Docker 隔离执行环境 |
| **Config** | `src/config.py` | 环境变量集中读取 |
| **MCP** | `src/mcp/` | MCP 协议客户端 + BaseTool 适配器 + 管理 API |
| **Skills** | `src/skills/` | 技能发现与沙箱上传 |
| **LLM 兼容层** | `src/llm.py` | 多厂商 reasoning 字段透传 |
| **分支工作流** | `.omo/workflows/branch-management.md` | 分支管理规范 |
| **计划** | `.omo/plans/` | 活计划，持续同步实施进度 |
| **计划注册表** | `.omo/plans/INDEX.md` | 所有计划的集中索引 |

## Skills 系统

SKILL.md 文件存放在宿主机的 `.omo/skills/<name>/SKILL.md`，agent 运行时自动上传到沙箱并注入 `create_deep_agent(skills=...)`。

### 实现原理

```
宿主 .omo/skills/<name>/SKILL.md
  → discover_skills() 读取
    → upload_skills_to_sandbox() 上传到沙箱
      → SkillsMiddleware.ls() + download_files() 加载
        → 解析 YAML frontmatter → 注入 system prompt
          → agent 自主判断是否需要读 SKILL.md 文件
```

### 约束

- SKILL.md **必须**以 `---` YAML frontmatter 开头，至少包含 `name` 和 `description`
- SkillsMiddleware 是**渐进式披露**设计：agent 自主决定是否读取完整内容
- 技能内容不会自动注入 system prompt
- 技能在每次 `run_agent`（有沙箱的路径）时重新加载，不缓存

### 新增技能

只需在 `.omo/skills/` 下创建目录 + SKILL.md，无需重启服务。

## MCP 工具管理

- MCP server 配置通过 Web UI（`/mcp/`）管理，持久化在 `.omo/mcp/mcp.db`
- 支持双模传输：**Streamable HTTP** 和 **HTTP SSE**，Web UI 提供传输模式选择
- 不支持 stdio（所有操作在沙箱外，Agent 框架侧）
- 启用的工具对所有会话有效
- 新增 MCP server 后需在 Web UI 同步拉取工具列表，再启用需要的工具
- `run_agent` 节点中 MCP 和 Skills 并行加载，互不阻塞
