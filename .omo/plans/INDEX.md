# Plan 注册表

> 本文件由 AI 在 plan 状态变更时自动更新。
> 不手动编辑——通过"更新 plan X 状态为 Y"来间接修改。

## 活跃 Plan

| Plan | 状态 | 优先级 | 分支 | 创建日期 | 最后更新 |
|------|------|--------|------|----------|----------|
| [agent-intelligence-upgrade.md](./agent-intelligence-upgrade.md) | partial | P0 | — | 2026-05-29 | 2026-06-03（方向一/四/五 ✅ → master；方向二/三/六/七 待定） |
| [mcp-optimization.md](./mcp-optimization.md) | completed | P1 | feat/mcp-optimization | 2026-07-06 | 2026-07-06（P0+P1.1~1.3 ✅; P1.4 ❌ 收益不足取消） |

## 已完成 Plan

| Plan | 状态 | 优先级 | 备注 | 创建日期 | 最后更新 |
|------|------|--------|------|----------|----------|
| [web-ui.md](./web-ui.md) | completed | P1 | merged → master (ad42340) | 2026-05-31 | 2026-06-01 |
| [download-optimization.md](./download-optimization.md) | completed | P2 | merged → master (06d7692) | 2026-06-01 | 2026-06-01 |
| [skills-system.md](./skills-system.md) | completed (v1) | P1 | merged → master (dcb646e) | 2026-06-01 | 2026-06-02 |
| [mcp-tool-integration.md](./mcp-tool-integration.md) | completed (v1) | P1 | merged → master (abce98e) | 2026-06-01 | 2026-06-02 |

## 状态说明

| 状态 | 含义 |
|------|------|
| draft | 草案中，内容可能变更 |
| review | 正在评审（Momus），或等待用户确认 |
| approved | 已定稿，可执行 |
| in_progress | 正在执行 |
| completed | 执行完成，待归档 |
| archived | 已归档，不再活跃 |
| cancelled | 已取消 |

## 标准操作

> 对 AI 说以下话即可触发：

| 你说 | AI 做 |
|------|-------|
| *"执行 plan X"* | 加载 plan → 拆 todo → delegate 执行 |
| *"评审 plan X"* | 调 Momus agent 做正式评审 |
| *"更新 plan X"* + 你的修改内容 | 读取 plan → 追加/修改内容 → 更新 INDEX |
| *"启动所有待执行的 plan"* | 扫描 INDEX 中 approved 的 plan → 逐个执行 |
