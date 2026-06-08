from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class SkillMetadata:
    name: str
    description: str
    path: Path
    root: Path


def discover_skills(paths: list[str], enabled: bool = True) -> list[SkillMetadata]:
    if not enabled:
        return []

    from reagent.config import DEFAULTS
    effective_paths = paths if paths else DEFAULTS["skills"]["paths"]
    skills: list[SkillMetadata] = []
    for raw_path in effective_paths:
        path = Path(raw_path).expanduser()
        root = _skill_root(path)
        skill_files = _skill_files(path)
        for skill_file in skill_files:
            metadata = _read_skill_metadata(skill_file, root=root)
            if metadata is not None:
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
    try:
        text = path.read_text(encoding="utf-8")
    except OSError:
        return None

    fields = _parse_frontmatter(text)
    name = fields.get("name")
    description = fields.get("description")
    if not name or not description:
        return None

    return SkillMetadata(name=name, description=description, path=path.resolve(), root=root)


def _parse_frontmatter(text: str) -> dict[str, str]:
    lines = text.splitlines()
    if not lines or lines[0].strip() != "---":
        return {}

    fields: dict[str, str] = {}
    for line in lines[1:]:
        if line.strip() == "---":
            break
        key, sep, value = line.partition(":")
        if not sep:
            continue
        key = key.strip()
        value = value.strip().strip("\"'")
        if key in {"name", "description"}:
            fields[key] = value

    return fields
