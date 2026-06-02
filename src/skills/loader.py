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
            logger.warning(
                "Backend %s does not support file upload, skills may not work",
                type(backend).__name__,
            )

        sandbox_paths.append(skill_path)
        logger.info("Uploaded skill '%s' to sandbox: %s", skill["name"], skill_path)

    return sandbox_paths
