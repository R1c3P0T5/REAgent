from __future__ import annotations

from reagent.skills import discover_skills
from reagent.tools.load_skill import LoadSkillTool


def test_load_skill_tool_returns_skill_body_for_configured_skill(tmp_path):
    skill_path = tmp_path / "skills" / "pe-analysis" / "SKILL.md"
    skill_path.parent.mkdir(parents=True)
    skill_path.write_text(
        """\
---
name: pe-analysis
description: Analyze PE files.
---

# PE Analysis

Use bounded strings output.
""",
        encoding="utf-8",
    )
    tool = LoadSkillTool(discover_skills([str(tmp_path / "skills")]))

    result = tool.run({"name": "pe-analysis"})

    assert result.path == str(skill_path.resolve())
    assert "# PE Analysis" in result.content
    assert "Use bounded strings output." in result.content
    assert result.text.startswith("# PE Analysis")
    assert "1: # PE Analysis" not in result.text


def test_load_skill_tool_rejects_unknown_skill(tmp_path):
    tool = LoadSkillTool(discover_skills([str(tmp_path / "skills")]))

    result = tool.run({"name": "missing"})

    assert result.text == "Error: unknown skill 'missing'"
