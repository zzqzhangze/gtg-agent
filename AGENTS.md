# AGENTS.md — AI 工作指令

优先级：CLAUDE.md > AGENTS.md > README.md > 代码注释

## 文档铁律

- **改了代码没改文档 = 没改完。**
- 代码注释写 Why，不写 What。

## 代码约束

- 禁止使用 `as any`、`# type: ignore`、`@ts-ignore` 压制类型错误。
- 每个节点必须处理异常，不能因为一个节点失败阻塞整个图。
- `analyze_intent` 使用 LLM 驱动意图分类，失败时自动回退到关键词匹配。

## 分支决策

核心标准：**master 收到一半改动时出问题会坏事吗？**

| 走分支 (`feat/<name>`) | 直接 master |
|------------------------|-------------|
| 新功能、架构变更、多步骤跨多文件 | 小修小补、bugfix、≤3 文件 |
| 需要测试批准后才能合入 | 用户信任可直接生效 |
| 中间状态会破坏 master | 改动独立完整 |

## 计划管理

`.omo/plans/*.md` 是活的管理工具。每完成一步立即同步更新。

### 触发条件

| 需要创建计划 | 不需要 |
|-------------|--------|
| 新功能 / 架构变更 | bugfix / 小修小补 |
| 多步骤（2+ 步） | 单步骤、≤3 文件 |
| 跨 4+ 文件 | 单次会话快速迭代 |
| 需要测试批准后才合入 | 用户信任可直接生效 |

**不确定时 → 问用户。** 不要猜。

### 同步触发

| 事件 | 动作 |
|------|------|
| 新开分支 | 创建 plan 文件 + 注册 INDEX.md |
| 步骤完成 | checkbox + updated + INDEX.md 同步 |
| 推送等待测试 | INDEX.md 状态改为"待合并" |
| 合并到 master | INDEX.md ✅ + 清理分支字段 |

### 文件头格式

```markdown
> status: [draft / in_progress / completed (vN)]
> branch: feat/<name>
> created: YYYY-MM-DD
> updated: YYYY-MM-DD
```

## 验证标准

任务未完成，直到以下全部通过：

| 检查项 | 工具 |
|--------|------|
| 改过的文件无新诊断错误 | `lsp_diagnostics` |
| 测试通过 | `pytest` |
| 文档同步更新 | 人工复核 |

## 参考文档

| 遇到问题时 | 去看 |
|-----------|------|
| MCP 配置/传输模式/工具管理 | `CONTRIBUTING.md`（### MCP 工具管理） |
| Skills 新增 | `CONTRIBUTING.md`（### 新增技能） |
| 部署/沙箱/环境变量 | `docs/deployment.md` |
| 分支/计划执行状态 | `.omo/plans/INDEX.md` |
