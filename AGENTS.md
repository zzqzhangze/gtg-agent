# AGENTS.md — AI 工作指令

> 项目结构和工作流见 [README.md](README.md)。本文档约束 AI 的行为，不是给人看的。

## 文档铁律

- **改了代码没改文档 = 没改完。** README / AGENTS.md / 代码注释与代码同步修改，缺一不可。
- 文档写"做什么"和"怎么用"，不写"怎么做"。
- 代码注释写 Why，不写 What：
  - `x += 1  # 计数器加1` → ❌ 废话
  - `x += 1  # 跳过 BOM 头` → ✅ 有用

## 代码约束

- 永远不要在宿主机直接执行用户代码。
- 所有文件传输通过 `LocalSandbox.read()` / `write()` 走 Docker 沙箱 API。
- `cleanup_sandbox` 是必经节点，新增沙箱节点必须在它之前。
- 禁止使用 `as any`、`# type: ignore`、`@ts-ignore` 压制类型错误。
- 每个节点都要处理异常，不能因为一个节点失败阻塞整个图。
- `analyze_intent` 使用 LLM 驱动意图分类（而非关键词匹配）。修改其行为应调整 `_INTENT_SYSTEM_PROMPT` 常量而非关键词列表。LLM 调用失败时自动回退到关键词匹配。

## 扩展工作流（加节点）

```
1. state.py   → 加字段
2. nodes.py   → 写节点函数
3. graph.py   → add_node() + add_edge() 注册
4. README.md  → 更新架构图和流程说明
```

## 计划管理规范

计划（`.sisyphus/plans/*.md`）不是静态文档，是**活的管理工具**。必须遵守：

### 分支优先

**每个计划必须在独立分支上实施，禁止直接在 master 上开发。** 实施完成后推送分支，由用户测试批准后才合并到 master。
详情见 [分支管理规范](.sisyphus/workflows/branch-management.md)。

### 创建新计划时

1. 写入 `.sisyphus/plans/<name>.md`
2. **立即在 `INDEX.md`（中央注册表）中注册**，包含状态和分支名

### 实施过程中

每条完成一个步骤，**立即**同步更新计划文件：
- `- [ ]` → `- [x]`
- 头部 `updated:` 日期
- `INDEX.md` 中同步状态（如 `进行中` → `v1 完成，待合并`）

### 状态变更触发

| 事件 | 必须更新 |
|------|---------|
| 新开分支 | `INDEX.md` 加一行 + 写分支名 |
| 步骤完成 | plan 文件 checkbox |
| 推送分支等待测试 | `INDEX.md` 状态改为 `vN 完成，待合并` + `updated` |
| 合并到 master | `INDEX.md` ✅ + 删除分支字段 |

### 计划文件头格式（必须包含）

```markdown
> status: [draft / in_progress / completed (vN)]
> branch: feat/<name>
> created: YYYY-MM-DD
> updated: YYYY-MM-DD
```

## 验证标准

任务未完成，直到以下检查全部通过：

| 检查项 | 工具 |
|--------|------|
| 改过的文件无新诊断错误 | `lsp_diagnostics` |
| 测试通过 | `pytest` 或项目等效命令 |
| 文档同步更新 | 人工复核 |

## 核心概念（快速参考）

| 术语 | 定义位置 |
|------|----------|
| **State** | `src/agent/state.py` — LangGraph 状态 |
| **Node** | `src/agent/nodes.py` — 处理节点 |
| **Edge** | `src/agent/graph.py` — 节点连线 |
| **Sandbox** | `src/sandbox/` — Docker 隔离执行环境 |
| **Config** | `src/config.py` — 环境变量集中读取 |
| **分支工作流** | `.sisyphus/workflows/branch-management.md` — 分支管理规范 |
| **计划** | `.sisyphus/plans/` — 活计划，持续同步实施进度 |
| **计划注册表** | `.sisyphus/plans/INDEX.md` — 所有计划的集中索引 |

## 优先级

CLAUDE.md > AGENTS.md > README.md > 代码注释

## Skills 系统

- SKILL.md 文件存放在宿主机的 `.sisyphus/skills/<name>/SKILL.md`
- agent 运行时自动上传到沙箱并注入 `create_deep_agent(skills=...)`
- 技能通过 DeepAgents 原生 SkillsMiddleware 生效
- 新增技能只需在 `.sisyphus/skills/` 下创建目录 + SKILL.md，无需重启服务
