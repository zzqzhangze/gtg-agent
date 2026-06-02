# Skills 技能系统原理

> 本文档解释 Skills 系统的完整链路：从宿主机文件 → 沙箱上传 → SkillsMiddleware 注入。
>
> **关键文件**: `src/skills/loader.py`, `src/agent/nodes.py`（集成点）

---

## 1. 完整链路

```
宿主机                                      沙箱
───────                                    ────────
.sisyphus/skills/<name>/SKILL.md
    │
    ▼
discover_skills()                           SkillsMiddleware
  → 遍历目录，读取 SKILL.md                     → backend.ls() 扫描子目录
  → 返回 [{name, content}]                     → backend.download_files() 读 SKILL.md
    │                                           → 解析 YAML frontmatter
    ▼                                           → 注入 system prompt
upload_skills_to_sandbox()
  → backend.upload_files() 或              
    _sandbox.write() 回退                      
    │                                          agent 自主判断
    ▼                                          → read_file(path) 读完整技能
/home/user/.sisyphus/skills/<name>/SKILL.md     → 按技能指令执行
    │
    ▼
create_deep_agent(skills=[SA_SKILLS_ROOT])
```

## 2. 组件详解

### 2.1 discover_skills() — 宿主机发现

```python
def discover_skills() -> list[dict]:
    SKILLS_DIR = ".sisyphus/skills/"
    for entry in SKILLS_DIR.iterdir():
        if entry.is_dir() and (entry / "SKILL.md").exists():
            content = (entry / "SKILL.md").read_text(encoding="utf-8")
            skills.append({"name": entry.name, "content": content})
    return skills
```

**约束**：
- 每个技能一个子目录，目录名即技能名
- 子目录内必须有 `SKILL.md` 文件
- 忽略没有 `SKILL.md` 的子目录（打印 warning）

### 2.2 upload_skills_to_sandbox() — 上传到沙箱

```python
SA_SKILLS_ROOT = "/home/user/.sisyphus/skills"

def upload_skills_to_sandbox(backend, skills):
    files_to_upload = []
    for skill in skills:
        skill_path = f"{SA_SKILLS_ROOT}/{skill['name']}/SKILL.md"
        files_to_upload.append((skill_path, skill["content"].encode()))

    # 优先用 backend.upload_files() 批量上传
    if hasattr(backend, "upload_files"):
        backend.upload_files(files_to_upload)
    else:
        # 回退：逐个 _sandbox.write()
        for path, content in files_to_upload:
            backend._sandbox.write(path, content)
```

**设计要点**：
- 优先批量上传（一次 HTTP 调用）
- 如果 backend 不支持批量，逐个 fallback
- 如果 backend 完全不支持文件上传，记录 warning，技能不影响 agent 运行

### 2.3 SkillsMiddleware — 渐进式披露

SkillsMiddleware 是 DeepAgents 原生的中间件，分两个阶段工作：

**加载阶段**（每 session 一次，`before_agent`）：

```
1. backend.ls(SA_SKILLS_ROOT)
   → 返回子目录列表: ["python-output/", "web-research/"]

2. backend.download_files(["python-output/SKILL.md", ...])
   → 读取每个 SKILL.md 原始内容

3. 解析 YAML frontmatter（正则匹配 ^---\n(.*?)\n---\n）
   → 提取 name / description / allowed-tools / metadata

4. 存入 state["skills_metadata"]
```

**注入阶段**（每次 LLM 调用，`before_model`）：

```
state["skills_metadata"]
  → 格式化为 system prompt 片段：

     ## Skills System
     **Available Skills:**
     - **python-output**: Best practices for Python output
       → Read /home/user/.sisyphus/skills/python-output/SKILL.md
     ...

     **How to Use (Progressive Disclosure):**
     1. Recognize when a skill applies
     2. Read the skill's full instructions: use read_file(path)
     3. Follow the skill's instructions
```

### 2.4 run_agent 集成点

```python
# nodes.py run_agent() 中
# ── Skills loading ──
sa_skills_root: str | None = None
try:
    skills_list = discover_skills()
    if skills_list:
        sa_skills_root = upload_skills_to_sandbox(backend, skills_list)
        print(f"[Skills] Loaded {len(skills_list)} skills")
except Exception as e:
    print(f"[Skills] Failed to load skills: {e}")

agent = create_deep_agent(
    model=llm,
    backend=backend,
    skills=[sa_skills_root] if sa_skills_root else None,  # ← 关键：传沙箱路径列表
    tools=mcp_additional_tools or None,
    system_prompt=...,
)
```

特别注意：`create_deep_agent(skills=...)` 接受的是 `list[str]`（沙箱内目录路径），
不是 skill 对象列表。SkillsMiddleware 通过 `backend.ls()` 读取该目录下的子目录。

---

## 3. SKILL.md 格式

```markdown
---
name: python-output
description: Best practices for formatting Python script output
allowed-tools:
  - read_file
  - write_file
metadata:
  author: team-x
---

# Skill Title

## Instructions
(技能正文)
```

**必须字段**：`name`、`description`
**约束**：name ≤ 100 字符，description ≤ 200 字符，总大小 ≤ 64KB

---

## 4. 设计哲学：渐进式披露

```
为什么不是直接把技能内容注入 system prompt？
────────────────────────────────────────
token 预算：如果 10 个技能每个 2KB，注入 system prompt 就是 20KB
           严重压缩了实际对话可用的上下文窗口

渐进式披露方案：
  system prompt 只写：技能名 + 一句话描述 + 文件路径
  agent 自主判断：这个任务需要读哪个技能？
  决定读取后：调用 read_file(path) 获取完整内容

结果：
  - 大部分情况 agent 不需要读技能（任务简单）
  - 即使需要，也只读 1-2 个相关技能
  - token 节省 10x 以上
```

---

## 5. 边界场景

| 场景 | 处理方式 |
|------|----------|
| `.sisyphus/skills/` 不存在 | `discover_skills()` 返回空列表，静默跳过 |
| 目录下没有 SKILL.md | 记录 warning，跳过该目录 |
| YAML frontmatter 缺失 name/description | 记录 warning，跳过该技能（SkillsMiddleware 决定） |
| SKILL.md 编码非 UTF-8 | 读取失败，记录 warning |
| backend 不支持文件上传 | 记录 warning，不影响 agent 运行 |
| 同名技能 | SkillsMiddleware 内部 dict 去重，后加载覆盖先加载 |

---

## 6. Skills vs MCP 的关系

两者在 `run_agent` 节点中**并行加载**，互不依赖：

```
run_agent:
  ├── Skills ──────────→ skills=[sa_skills_root]
  ├── MCP 工具 ─────────→ tools=[mcp_tools]
  └── create_deep_agent(tools=..., skills=..., ...)
```

- **Skills**：注入 agent 的 system prompt，影响 LLM 行为方式（长指令）
- **MCP 工具**：注入 agent 的 tool 列表，让 LLM 可以调用外部功能（具体操作）
- 一个失败不影响另一个
