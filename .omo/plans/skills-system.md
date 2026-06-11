# Skills System Implementation Plan

> status: completed (v1)
> branch: feat/skills-system
> created: 2026-06-01
> updated: 2026-06-02

**Goal:** Host SKILL.md files on host machine and inject them into DeepAgents runtime as `skills` parameter.

**Architecture:** 
- Host directory `.sisyphus/skills/<name>/SKILL.md` stores skill content
- `src/skills/loader.py` scans and loads skills into DeepAgents-compatible format
- `run_agent` passes `skills` param to `create_deep_agent()`, invoking native SkillsMiddleware

**Design doc:** `docs/mcp-skills-upgrade-design.md`

---

## File Structure

| File | Action | Responsibility |
|------|--------|---------------|
| `.sisyphus/skills/` | **Create** | Directory for skill subdirectories |
| `src/skills/__init__.py` | **Create** | Package init |
| `src/skills/loader.py` | **Create** | `load_skills()` function: scans `.sisyphus/skills/`, reads SKILL.md files |
| `src/agent/nodes.py` | **Modify** | `run_agent`: load skills and pass to `create_deep_agent()` |
| `.sisyphus/plans/INDEX.md` | **Modify** | Register this plan |
| `AGENTS.md` | **Modify** | Add Skills workflow notes |

---

### Task 1: Skills loader

**Files:**
- Create: `src/skills/__init__.py`
- Create: `src/skills/loader.py`
- Create: `.sisyphus/skills/` directory

- [x] **Step 1: Create `src/skills/__init__.py`** (empty)

- [x] **Step 2: Write `src/skills/loader.py`**

DeepAgents' `create_deep_agent()` accepts a `skills` parameter. Based on the architecture analysis, the expected format is a list of skill objects, where each skill has at minimum a `name` and `content` field (the full SKILL.md content).

For the sandbox-based deployment:
- Skills live on the host at `.sisyphus/skills/<name>/SKILL.md`
- We need to upload them to the sandbox before passing to `create_deep_agent()`
- `LangSmithBackend` (which wraps a `Sandbox`) provides `upload_file()` for this

The flow:
1. `load_skills()` reads `.sisyphus/skills/*/SKILL.md` from host
2. Returns list of skill dicts: `[{"name": "...", "content": "..."}]`
3. In `run_agent`, after creating `backend`, upload each SKILL.md to sandbox
4. Pass skill names (or the skill objects) to `create_deep_agent(skills=...)`

```python
import logging
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)

SKILLS_DIR = Path(__file__).resolve().parents[2] / ".sisyphus" / "skills"


def discover_skills() -> list[dict[str, Any]]:
    """Scan .sisyphus/skills/ and return list of skill dicts.

    Each skill is a dict with keys: name, content
    """
    if not SKILLS_DIR.exists():
        logger.info("Skills directory not found: %s", SKILLS_DIR)
        return []

    skills = []
    for entry in sorted(SKILLS_DIR.iterdir()):
        if not entry.is_dir():
            continue
        skill_file = entry / "SKILL.md"
        if not skill_file.exists():
            logger.warning("Skill dir '%s' has no SKILL.md, skipping", entry.name)
            continue
        content = skill_file.read_text(encoding="utf-8")
        skills.append({"name": entry.name, "content": content})
        logger.info("Discovered skill: %s (%d chars)", entry.name, len(content))

    return skills


def upload_skills_to_sandbox(backend: Any, skills: list[dict[str, Any]]) -> list[str]:
    """Upload SKILL.md files to sandbox via backend.

    Returns list of sandbox paths.
    """
    sandbox_paths = []
    for skill in skills:
        skill_dir = f"/home/user/.sisyphus/skills/{skill['name']}"
        skill_path = f"{skill_dir}/SKILL.md"

        # Use backend's upload_file if available
        if hasattr(backend, "upload_file"):
            backend.upload_file(
                sandbox_path=skill_path,
                content=skill["content"],
            )
        elif hasattr(backend, "_sandbox") and hasattr(backend._sandbox, "write"):
            backend._sandbox.write(skill_path, skill["content"])
        else:
            logger.warning("Backend %s does not support file upload, skills may not work", type(backend).__name__)

        sandbox_paths.append(skill_path)
        logger.info("Uploaded skill '%s' to sandbox: %s", skill["name"], skill_path)

    return sandbox_paths
```

- [x] **Step 3: Create `.sisyphus/skills/` directory** (empty, holds skill subdirectories)

- [x] **Step 4: Commit** (79e12fa)

```bash
git add src/skills/
git add .sisyphus/skills/
git commit -m "feat: add skills loader"
```

---

### Task 2: Integrate skills into run_agent

**Files:**
- Modify: `src/agent/nodes.py`

- [x] **Step 1: Modify `run_agent` in `src/agent/nodes.py`**

After the MCP tools loading block (or in the same area before `create_deep_agent()`), insert:

```python
        # ── Skills loading ──
        try:
            from src.skills.loader import discover_skills, upload_skills_to_sandbox

            skills_list = discover_skills()
            if skills_list:
                upload_skills_to_sandbox(backend, skills_list)
                skill_names = [s["name"] for s in skills_list]
                print(f"[Skills] Loaded {len(skills_list)} skills: {skill_names}")
        except Exception as e:
            print(f"[Skills] Failed to load skills: {e}")
            skills_list = []
```

Change `create_deep_agent()` call to add `skills` parameter:

```python
        agent = create_deep_agent(
            model=llm,
            backend=backend,
            tools=mcp_additional_tools or None,
            skills=skills_list or None,
            system_prompt=(...),
            checkpointer=MemorySaver(),
        )
```

- [x] **Step 2: Commit** (bf8abc2)

```bash
git add src/agent/nodes.py
git commit -m "feat: integrate skills into run_agent"
```

---

### Task 3: Documentation

**Files:**
- Modify: `AGENTS.md`
- Modify: `.sisyphus/plans/INDEX.md`

- [x] **Step 1: Update AGENTS.md**
- [x] **Step 2: Update INDEX.md plan status**

- [x] **Step 3: Commit** (0078e8d)

```bash
git add AGENTS.md .sisyphus/plans/INDEX.md
git commit -m "docs: add skills system notes"
```
