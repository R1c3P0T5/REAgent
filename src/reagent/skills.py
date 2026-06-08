from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path


_SKILL_NAME = re.compile(r"^[a-z0-9][a-z0-9_-]*$")
_RESERVED_SKILL_NAMES = {"compact", "exit", "quit", "status"}


@dataclass(frozen=True)
class SkillMetadata:
    name: str
    description: str
    path: Path
    root: Path


def discover_skills(paths: list[str], enabled: bool = True) -> list[SkillMetadata]:
    if not enabled:
        return []

    skills: list[SkillMetadata] = []
    seen: set[str] = set()
    for raw_path in paths:
        path = Path(raw_path).expanduser()
        root = _skill_root(path)
        skill_files = _skill_files(path)
        for skill_file in skill_files:
            metadata = _read_skill_metadata(skill_file, root=root)
            if metadata is not None and metadata.name not in seen:
                seen.add(metadata.name)
                skills.append(metadata)

    return sorted(skills, key=lambda skill: skill.name.lower())


def _skill_root(path: Path) -> Path:
    if path.is_file():
        return path.parent.resolve()
    return path.resolve()


def _skill_files(path: Path) -> list[Path]:
    if path.is_file():
        return [path] if path.name == "SKILL.md" else []

    if not path.is_dir():
        return []

    skill_file = path / "SKILL.md"
    if skill_file.is_file():
        return [skill_file]

    return sorted(
        candidate
        for candidate in path.rglob("SKILL.md")
        if candidate.is_file()
    )


def _read_skill_metadata(path: Path, *, root: Path) -> SkillMetadata | None:
    resolved_path = path.resolve()
    resolved_root = root.resolve()
    if not resolved_path.is_relative_to(resolved_root):
        return None

    try:
        text = resolved_path.read_text(encoding="utf-8")
    except OSError:
        return None

    fields = _parse_frontmatter(text)
    name = fields.get("name")
    description = fields.get("description")
    if not name or not description:
        return None
    if not _is_valid_skill_name(name):
        return None

    return SkillMetadata(name=name, description=description, path=resolved_path, root=resolved_root)


def _is_valid_skill_name(name: str) -> bool:
    return bool(_SKILL_NAME.fullmatch(name)) and name not in _RESERVED_SKILL_NAMES


def _parse_frontmatter(text: str) -> dict[str, str]:
    lines = text.splitlines()
    if not lines or lines[0].strip() != "---":
        return {}

    fields: dict[str, str] = {}
    closed = False
    for line in lines[1:]:
        if line.strip() == "---":
            closed = True
            break
        key, sep, value = line.partition(":")
        if not sep:
            continue
        key = key.strip()
        value = value.strip().strip("\"'")
        if key in {"name", "description"}:
            fields[key] = value

    return fields if closed else {}
