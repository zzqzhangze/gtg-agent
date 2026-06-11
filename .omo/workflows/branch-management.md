# 分支管理工作流

> 基于 `feat/llm-intent-analysis` → `feat/file-discovery` 分支整理实践总结。
> 目标：每个分支职责单一，master 始终可工作。

---

## 核心原则

### 1. 一个分支只做一件事

一个分支对应一个独立的功能/修复范围。**不在一个分支上堆砌多个不相关的改动。**

```
✅ 正确：
  feat/llm-intent-analysis       ← 只做意图分析
  feat/file-discovery            ← 只做文件发现

❌ 错误：
  feat/llm-intent-analysis       ← 混入了文件发现的代码
```

### 2. 分支名 = 精确范围

分支名精确描述这个分支做的事，不是模糊的大类名。

```
✅ feat/llm-intent-analysis       ← 意图分析
✅ feat/file-discovery            ← 文件发现与下载
✅ feat/evaluate-retry            ← 评估重试闭环

❌ feat/upgrade                   ← 太宽泛
❌ feat/optimize                  ← 看不出做什么
❌ dev                            ← 什么都往这堆
```

### 3. 用户审批制：完成推送，用户批准后合入

实施完成后**不直接合并**，先推送分支到远程，通知用户测试。用户批准后才能合并。

```
实施完成 → git push origin feat/<name> → 通知用户 → 用户测试
    ↓ 用户说"合并"
merge --no-ff → 删除 feature 分支
```

`--no-ff` 保留合并拓扑，提交踪迹里一眼看出分支线和哪些 commit 属于哪个改动。

### 4. 不堆叠

新功能从 **master** 拉分支，不从未合入的 feature 分支拉。避免"分支上的分支"，简化回退和 rebase。

## 分支决策（AI 自主判断）

AI 接手任务时分析以下问题来决定是否拉分支：

| 走分支 | 直接 master |
|--------|-------------|
| 新功能、架构变更 | 小修小补、bugfix |
| 多步骤、跨多文件 | 单文件/≤3 文件的小改动 |
| 用户需要测试和批准后才能合入 | 用户信任可以直接生效 |
| 中间状态会破坏 master | 改动独立完整，不依赖后续步骤 |

**核心判断标准：如果 master 在收到这个改动的一半时出问题，会坏事吗？会 → 走分支。不会 → 直接 master。**

## 操作流程

### 启动新功能（走分支时）

```bash
git checkout master          # 从 master 出发
git pull                     # 确保最新
git checkout -b feat/<name>  # 拉新分支
```

### 功能完成，推送分支等待测试

```bash
# 在 feature 分支上
git add -A && git commit     # 提交所有改动
git push origin feat/<name>  # 推送到远程
# 通知用户测试。等待用户说"合并"后再继续下一步
```

### 用户批准后，合并回 master

```bash
# 确保 master 是最新的
git checkout master
git pull

# 合并（保留分支线）
git merge feat/<name> --no-ff -m "feat: merge <scope> - <summary>"
git branch -d feat/<name>    # 删除 feature 分支
git push origin master       # 推送合并结果
git push origin --delete feat/<name>  # 删除远程分支
```

### 发现当前分支跑偏了（混入了其他改动的代码）

```bash
git stash                    # 暂存跑偏的改动
git checkout master          # 回 master
git checkout -b feat/correct-name  # 拉正确的新分支
git stash pop                # 恢复改动
```

### 合并后 Master 的日志形态

```
*   b320c96 (master) feat: merge LLM-driven intent analysis
|\  
| * 71551de docs: update plan
| * e281c54 feat: implement template registry
| * 33b39a4 feat: replace keyword intent analysis with LLM
|/  
* 365d2ba docs: add plan management system
```

合并节点下一级缩进的 commit 全部属于同一个功能范围，职责一目了然。

## 检查清单（提交前自检）

- [ ] 分支名精确描述了改动范围？
- [ ] 这个分支只做一件事？
- [ ] 功能完整可工作？
- [ ] 已推送到远程？
- [ ] 用户已测试并批准？
- [ ] 合并时用了 `--no-ff`？
- [ ] 合完后删除了本地和远程分支？
