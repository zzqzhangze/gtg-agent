# Plan 注册表

> 本文件由 AI 在 plan 状态变更时自动更新。
> 不手动编辑——通过"更新 plan X 状态为 Y"来间接修改。

## 活跃 Plan

| Plan | 状态 | 优先级 | 分支 | 创建日期 | 最后更新 |
|------|------|--------|------|----------|----------|
| [agent-intelligence-upgrade.md](./agent-intelligence-upgrade.md) | approved | P0 | — | 2026-05-29 | 2026-05-31（优先级已更新，剩余方向：三→二→四/六/七） |
| [web-ui.md](./web-ui.md) | ✅ merged → master (ad42340) | P1 | — | 2026-05-31 | 2026-06-01 |
| [download-optimization.md](./download-optimization.md) | ✅ merged → master (06d7692) | P2 | — | 2026-06-01 | 2026-06-01 |

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
