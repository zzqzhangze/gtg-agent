# 分支管理工作流

> 基于 `feat/llm-intent-analysis` → `feat/file-discovery` 分支整理实践总结。
> 目标：每个分支职责单一，master 始终可工作。

---

## 核心原则

### 1. 一条方向 = 一个分支

Plan 里的每个方向（direction）对应独立的 feature 分支。不在一个分支上堆砌多个方向的工作。

```
✅ 正确：
  方向一 → feat/llm-intent-analysis
  方向五 → feat/file-discovery

❌ 错误：
  方向一 + 方向五 → feat/llm-intent-analysis (混在一起)
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

### 3. 完成即合入，合入即删除

方向做完了立刻合并到 master，不积压。合并后删掉 feature 分支，不保留僵尸分支。

```
完成 → merge --no-ff → 删除 feature 分支
```

`--no-ff` 保留合并拓扑，一眼看出哪些 commit 属于哪个方向。

### 4. 不堆叠

新方向从 **master** 拉分支，不从未合入的 feature 分支拉。避免"分支上的分支"，简化回退和 rebase。

## 操作流程

### 启动新方向

```bash
git checkout master          # 从 master 出发
git pull                     # 确保最新
git checkout -b feat/<name>  # 拉新分支
```

### 方向完成，合并回 master

```bash
# 在 feature 分支上
git add -A && git commit     # 提交所有改动

# 切到 master 合并
git checkout master
git merge feat/<name> --no-ff -m "feat: merge <scope> - <summary>"
git branch -d feat/<name>    # 删除 feature 分支
```

### 发现当前分支跑偏了（混入了其他方向的改动）

```bash
git stash                    # 暂存跑偏的改动
git checkout master          # 回 master
git checkout -b feat/correct-name  # 拉正确的新分支
git stash pop                # 恢复改动
```

### 合并后 Master 的日志形态

```
*   b320c96 (master) feat: merge direction 1 - LLM-driven intent analysis
|\  
| * 71551de docs: update plan
| * e281c54 feat: implement template registry
| * 33b39a4 feat: replace keyword intent analysis with LLM
|/  
* 365d2ba docs: add plan management system
```

合并节点下一级缩进的 commit 全部属于同一个方向，职责一目了然。

## 检查清单（提交前自检）

- [ ] 分支名精确描述了改动范围？
- [ ] 这个分支只做一个方向的事？
- [ ] 功能完整可工作？
- [ ] 已跑的测试通过了？
- [ ] 合并时用了 `--no-ff`？
- [ ] 合完后删除了 feature 分支？

## 例外处理

| 场景 | 处理方式 |
|------|----------|
| 紧急修复 | 从 master 拉 `fix/<bug-short-desc>`，修完直接合并，不经过 plan 流程 |
| 实验性探索 | 用 `explore/<topic>` 前缀，探索完删除，不合入 master |
| 文档/配置 | 可以直接在 master 上提交，不需要拉分支（单文件、无风险） |
