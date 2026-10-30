"""Agent Skills (agentskills.io `SKILL.md` folders) for the voice assistant.

A skill is a folder holding a SKILL.md: YAML front matter with `name` and
`description`, then Markdown instructions. Jarvis follows progressive
disclosure: only names and descriptions are advertised, the instructions are
read when a skill is used, and bundled reference files on explicit request.

Skills are read, never executed: Jarvis does not run a skill's scripts. The
instructions guide the model, which still acts only through its own guarded
tools, so confirmations and safe mode apply unchanged.

Search path: ~/Library/Application Support/Jarvis/skills, or the folders in
JARVIS_SKILLS_PATH (separated by ':').
"""
from __future__ import annotations

import os
import re
from dataclasses import dataclass
from pathlib import Path

from jarvis.capabilities.results import ToolResult

MAX_SKILLS = 100
MAX_SKILL_FILE_BYTES = 256 * 1024
MAX_INSTRUCTIONS_CHARS = 8000
MAX_DESCRIPTION_CHARS = 1024
_NAME = re.compile(r"^[a-z0-9][a-z0-9-]{0,63}$")
_TEXT_SUFFIXES = {".md", ".txt", ".json", ".yaml", ".yml", ".csv"}


def default_skill_dirs() -> list[Path]:
    override = os.environ.get("JARVIS_SKILLS_PATH")
    if override:
        return [Path(part).expanduser() for part in override.split(os.pathsep) if part]
    return [Path.home() / "Library" / "Application Support" / "Jarvis" / "skills"]


@dataclass(frozen=True)
class Skill:
    name: str
    description: str
    path: Path

    @property
    def folder(self) -> Path:
        return self.path.parent


def _front_matter(text: str) -> tuple[dict, str] | None:
    if not text.startswith("---"):
        return None
    end = text.find("\n---", 3)
    if end < 0:
        return None
    header, body = text[3:end], text[end + 4:]
    try:
        import yaml
        data = yaml.safe_load(header)
    except ImportError:  # pragma: no cover - yaml ships with the live extras
        data = dict(
            (key.strip(), value.strip().strip("'\""))
            for key, _, value in (line.partition(":") for line in header.splitlines())
            if key.strip() and value.strip()
        )
    except Exception:
        return None
    return (data, body.lstrip("\n")) if isinstance(data, dict) else None


def parse_skill(path: Path) -> Skill | None:
    """Return the skill described by a SKILL.md, or None if it is not valid."""
    try:
        if path.stat().st_size > MAX_SKILL_FILE_BYTES:
            return None
        parsed = _front_matter(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError):
        return None
    if parsed is None:
        return None
    data, _ = parsed
    name, description = data.get("name"), data.get("description")
    if not isinstance(name, str) or not _NAME.match(name.strip()):
        return None
    if not isinstance(description, str) or not description.strip():
        return None
    return Skill(name.strip(), " ".join(description.split())[:MAX_DESCRIPTION_CHARS], path)


class SkillLibrary:
    def __init__(self, directories: list[Path] | None = None):
        self._directories = directories
        self._skills: dict[str, Skill] | None = None

    def skills(self) -> dict[str, Skill]:
        if self._skills is None:
            found: dict[str, Skill] = {}
            for root in self._directories if self._directories is not None else default_skill_dirs():
                try:
                    candidates = sorted(root.glob("*/SKILL.md"))
                except OSError:
                    continue
                for path in candidates:
                    skill = parse_skill(path)
                    # First folder wins on a duplicate name; the cap bounds work.
                    if skill is not None and skill.name not in found and len(found) < MAX_SKILLS:
                        found[skill.name] = skill
            self._skills = found
        return self._skills

    def reload(self) -> None:
        self._skills = None

    def list_skills(self) -> ToolResult:
        skills = [
            {"name": skill.name, "description": skill.description}
            for skill in sorted(self.skills().values(), key=lambda s: s.name)
        ]
        message = f"{len(skills)} skill(s) installee(s)." if skills else "Aucune skill installee."
        return ToolResult.success("list_skills", message, skills=skills)

    def use_skill(self, name: str, file: str = "") -> ToolResult:
        action = "use_skill"
        skill = self.skills().get((name or "").strip())
        if skill is None:
            known = ", ".join(sorted(self.skills())) or "aucune"
            return ToolResult.failure(action, f"Skill inconnue : {name}. Skills installees : {known}.", "skill_not_found")
        if file:
            return self._read_bundled(skill, file)
        try:
            parsed = _front_matter(skill.path.read_text(encoding="utf-8"))
        except (OSError, UnicodeDecodeError):
            parsed = None
        if parsed is None:
            return ToolResult.failure(action, f"La skill {skill.name} est illisible.", "skill_unreadable")
        body = parsed[1]
        files = sorted(
            str(path.relative_to(skill.folder))
            for path in skill.folder.rglob("*")
            if path.is_file() and path.name != "SKILL.md" and not path.name.startswith(".")
        )[:50]
        return ToolResult.success(
            action,
            "Instructions de la skill. Suis-les avec tes propres outils : les "
            "confirmations restent obligatoires et Jarvis n'execute jamais les "
            "scripts fournis par une skill.",
            skill=skill.name,
            instructions=body[:MAX_INSTRUCTIONS_CHARS],
            truncated=len(body) > MAX_INSTRUCTIONS_CHARS,
            files=files,
        )

    def _read_bundled(self, skill: Skill, file: str) -> ToolResult:
        action = "use_skill"
        folder = skill.folder.resolve()
        target = (folder / file).resolve()
        if not target.is_relative_to(folder) or not target.is_file():
            return ToolResult.failure(action, f"Fichier absent de la skill {skill.name} : {file}.", "skill_file_not_found")
        if target.suffix.lower() not in _TEXT_SUFFIXES:
            return ToolResult.failure(
                action, "Seuls les fichiers texte de reference sont lisibles ; les scripts ne sont jamais executes.",
                "skill_file_not_text",
            )
        try:
            if target.stat().st_size > MAX_SKILL_FILE_BYTES:
                return ToolResult.failure(action, "Fichier de skill trop volumineux.", "skill_file_too_large")
            text = target.read_text(encoding="utf-8")
        except (OSError, UnicodeDecodeError):
            return ToolResult.failure(action, "Fichier de skill illisible.", "skill_unreadable")
        return ToolResult.success(
            action, "Fichier de reference de la skill.", skill=skill.name, file=file,
            content=text[:MAX_INSTRUCTIONS_CHARS], truncated=len(text) > MAX_INSTRUCTIONS_CHARS,
        )
