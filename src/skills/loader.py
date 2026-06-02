import logging
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)

SKILLS_DIR = Path(__file__).resolve().parents[2] / ".sisyphus" / "skills"


SA_SKILLS_ROOT = "/home/user/.sisyphus/skills"
"""Root directory on the sandbox where skill files are uploaded.

Expected structure:
  {SA_SKILLS_ROOT}/
    skill-name-1/
      SKILL.md
    skill-name-2/
      SKILL.md

Pass this path in create_deep_agent(skills=[SA_SKILLS_ROOT]).
"""


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


def upload_skills_to_sandbox(backend: Any, skills: list[dict[str, Any]]) -> str:
    """Upload SKILL.md files to sandbox and return the root directory path.

    The returned path can be passed to ``create_deep_agent(skills=[path])``.

    SkillsMiddleware expects this structure on the backend:
      root/
        skill-name/
          SKILL.md

    Args:
        backend: LangSmithBackend (or equivalent) with upload_files().
        skills: List of {"name": ..., "content": ...} from discover_skills().

    Returns:
        Sandbox root path for use with create_deep_agent(skills=[...]).
    """
    files_to_upload: list[tuple[str, bytes]] = []
    for skill in skills:
        skill_dir = f"{SA_SKILLS_ROOT}/{skill['name']}"
        skill_path = f"{skill_dir}/SKILL.md"
        files_to_upload.append((skill_path, skill["content"].encode("utf-8")))
        logger.info("Prepared skill '%s' → sandbox:%s", skill["name"], skill_path)

    if files_to_upload and hasattr(backend, "upload_files"):
        backend.upload_files(files_to_upload)
    else:
        # Fallback: write one by one via _sandbox.write()
        for skill_path, content in files_to_upload:
            if hasattr(backend, "_sandbox") and hasattr(backend._sandbox, "write"):
                backend._sandbox.write(skill_path, content)
            else:
                logger.warning(
                    "Backend %s does not support file upload, skills may not work",
                    type(backend).__name__,
                )

    return SA_SKILLS_ROOT
