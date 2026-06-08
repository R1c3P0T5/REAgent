from __future__ import annotations

from pathlib import Path

from reagent.skills import discover_skills, find_skill, read_skill, substitute_arguments


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


def test_discover_skills_empty_paths_discovers_nothing():
    assert discover_skills([]) == []


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


def test_discover_skills_ignores_names_that_are_not_slash_safe(tmp_path):
    write_skill(
        tmp_path / "skills" / "bad-name" / "SKILL.md",
        """\
---
name: Bad Name
description: This should not load.
---
""",
    )

    assert discover_skills([str(tmp_path / "skills")]) == []


def test_discover_skills_ignores_builtin_slash_command_collisions(tmp_path):
    write_skill(
        tmp_path / "skills" / "status" / "SKILL.md",
        """\
---
name: status
description: This should not load.
---
""",
    )

    assert discover_skills([str(tmp_path / "skills")]) == []


def test_discover_skills_ignores_metadata_symlink_outside_root(tmp_path):
    outside = write_skill(
        tmp_path / "outside.md",
        """\
---
name: outside-skill
description: This should not leak.
---
""",
    )
    skill_file = tmp_path / "skills" / "outside-skill" / "SKILL.md"
    skill_file.parent.mkdir(parents=True)
    skill_file.symlink_to(outside)

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


def test_find_skill_matches_discovered_skill_by_name(tmp_path):
    skill_path = write_skill(
        tmp_path / "skills" / "pe-analysis" / "SKILL.md",
        """\
---
name: pe-analysis
description: Analyze PE files.
---

# PE Analysis
""",
    )
    skills = discover_skills([str(tmp_path / "skills")])

    skill = find_skill("pe-analysis", skills)

    assert skill is not None
    assert skill.name == "pe-analysis"
    assert skill.path == skill_path.resolve()
    assert find_skill("missing", skills) is None


def test_read_skill_returns_full_skill_file_content(tmp_path):
    skill_path = write_skill(
        tmp_path / "skills" / "pe-analysis" / "SKILL.md",
        """\
---
name: pe-analysis
description: Analyze PE files.
---

# PE Analysis

Use bounded strings output.
""",
    )
    skill = discover_skills([str(tmp_path / "skills")])[0]

    content = read_skill(skill)

    assert content.name == "pe-analysis"
    assert content.path == skill_path.resolve()
    assert "# PE Analysis" in content.body
    assert "Use bounded strings output." in content.body


def test_read_skill_rejects_paths_that_resolve_outside_skill_root(tmp_path):
    skill_path = write_skill(
        tmp_path / "skills" / "pe-analysis" / "SKILL.md",
        """\
---
name: pe-analysis
description: Analyze PE files.
---

# PE Analysis
""",
    )
    skill = discover_skills([str(tmp_path / "skills")])[0]
    skill_path.unlink()
    skill_path.symlink_to(tmp_path / "outside.md")
    (tmp_path / "outside.md").write_text("outside", encoding="utf-8")

    try:
        read_skill(skill)
    except PermissionError as exc:
        assert "outside configured skill root" in str(exc)
    else:
        raise AssertionError("read_skill should reject a replaced symlink outside the skill root")


def test_substitute_arguments_replaces_placeholder():
    body = "Analyze $ARGUMENTS for vulnerabilities."
    assert substitute_arguments(body, "target.exe") == "Analyze target.exe for vulnerabilities."


def test_substitute_arguments_replaces_all_occurrences():
    body = "Target: $ARGUMENTS\nFile: $ARGUMENTS"
    assert substitute_arguments(body, "foo.bin") == "Target: foo.bin\nFile: foo.bin"


def test_substitute_arguments_empty_args():
    body = "Run analysis on $ARGUMENTS"
    assert substitute_arguments(body, "") == "Run analysis on "


def test_substitute_arguments_no_placeholder():
    body = "Run standard analysis workflow."
    assert substitute_arguments(body, "target.exe") == "Run standard analysis workflow."
