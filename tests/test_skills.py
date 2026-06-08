from __future__ import annotations

from pathlib import Path

from reagent.skills import discover_skills


def write_skill(path: Path, text: str) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")
    return path


def test_discover_skills_reads_frontmatter_from_skill_directories(tmp_path):
    pe_skill = write_skill(
        tmp_path / "skills" / "pe-analysis" / "SKILL.md",
        """\
---
name: pe-analysis
description: Analyze Windows PE executables, DLLs, drivers, imports, exports, and resources.
---

# PE Analysis
""",
    )
    elf_skill = write_skill(
        tmp_path / "skills" / "elf-analysis" / "SKILL.md",
        """\
---
name: elf-analysis
description: Analyze Linux ELF binaries and firmware userland executables.
---

# ELF Analysis
""",
    )

    skills = discover_skills([str(tmp_path / "skills")])

    assert skills[0].name == "elf-analysis"
    assert skills[0].path == elf_skill.resolve()
    assert skills[0].root == (tmp_path / "skills").resolve()
    assert skills[1].name == "pe-analysis"
    assert skills[1].path == pe_skill.resolve()
    assert skills[1].root == (tmp_path / "skills").resolve()


def test_discover_skills_only_supports_uppercase_skill_md(tmp_path):
    write_skill(
        tmp_path / "skills" / "lowercase-skill" / "skill.md",
        """\
---
name: lowercase-skill
description: This should not load.
---

# Lowercase Skill
""",
    )

    assert discover_skills([str(tmp_path / "skills")]) == []


def test_discover_skills_ignores_direct_file_paths_not_named_skill_md(tmp_path):
    skill_file = write_skill(
        tmp_path / "skills" / "pe-analysis.md",
        """\
---
name: pe-analysis
description: This should not load.
---
""",
    )

    assert discover_skills([str(skill_file)]) == []


def test_discover_skills_ignores_files_without_required_metadata(tmp_path):
    write_skill(
        tmp_path / "skills" / "broken" / "SKILL.md",
        """\
---
name: broken
---

# Missing Description
""",
    )

    assert discover_skills([str(tmp_path / "skills")]) == []


def test_discover_skills_preserves_colons_in_simple_frontmatter_values(tmp_path):
    write_skill(
        tmp_path / "skills" / "pe-analysis" / "SKILL.md",
        """\
---
name: pe-analysis
description: Analyze PE files: imports, exports, resources.
---

# PE Analysis
""",
    )

    skills = discover_skills([str(tmp_path / "skills")])

    assert skills[0].description == "Analyze PE files: imports, exports, resources."


def test_discover_skills_respects_disabled_flag(tmp_path):
    write_skill(
        tmp_path / "skills" / "pe-analysis" / "SKILL.md",
        """\
---
name: pe-analysis
description: Analyze PE files.
---
""",
    )

    assert discover_skills([str(tmp_path / "skills")], enabled=False) == []
