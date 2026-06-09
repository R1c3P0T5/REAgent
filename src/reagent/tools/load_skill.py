from __future__ import annotations

from collections.abc import Sequence
from typing import Any

from reagent.results import ErrorResult, SkillResult, ToolResult
from reagent.skills import SkillMetadata, resolve_skill_content, skill_body
from reagent.tools.base import MAX_OUTPUT, Tool, params, prop


class LoadSkillTool(Tool):
    name = "load_skill"

    def __init__(self, skills: Sequence[SkillMetadata]) -> None:
        self._skills = tuple(skills)

    @property
    def description(self) -> str:
        lines = ["Load the full workflow for an available skill by name before following it."]
        if self._skills:
            lines.append("\nAvailable skills:")
            for skill in self._skills:
                line = f"- {skill.name}: {skill.description}"
                if skill.compatibility:
                    line += f" (requires: {skill.compatibility})"
                lines.append(line)
        return "\n".join(lines)

    @property
    def parameters(self) -> dict[str, Any]:
        return params(
            {"name": prop("string", "Name of the available skill to load.")},
            required=["name"],
        )

    def run(self, params: dict[str, Any]) -> ToolResult:
        name = params["name"]
        try:
            content = resolve_skill_content(name, self._skills)
        except KeyError:
            return ErrorResult(f"Error: unknown skill {name!r}")
        except OSError as exc:
            return ErrorResult(f"Error: failed to load skill {name!r}: {exc}")

        body = skill_body(content)
        if len(body) > MAX_OUTPUT:
            body = body[:MAX_OUTPUT]
            last_newline = body.rfind("\n")
            if last_newline != -1:
                body = body[: last_newline + 1]
            body += "(truncated)\n"

        return SkillResult(path=str(content.path), content=body)
