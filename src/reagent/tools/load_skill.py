from __future__ import annotations

from collections.abc import Sequence
from typing import Any

from reagent.results import ErrorResult, ReadResult, ToolResult
from reagent.skills import SkillMetadata, find_skill, read_skill
from reagent.tools.base import MAX_OUTPUT, Tool, params, prop


class LoadSkillTool(Tool):
    name = "load_skill"
    description = "Load the instructions for an available skill by name before following its workflow."

    def __init__(self, skills: Sequence[SkillMetadata]) -> None:
        self._skills = tuple(skills)

    @property
    def parameters(self) -> dict[str, Any]:
        return params(
            {"name": prop("string", "Name of the available skill to load.")},
            required=["name"],
        )

    def run(self, params: dict[str, Any]) -> ToolResult:
        name = params["name"]
        skill = find_skill(name, self._skills)
        if skill is None:
            return ErrorResult(f"Error: unknown skill {name!r}")

        try:
            content = read_skill(skill)
        except OSError as exc:
            return ErrorResult(f"Error: failed to load skill {name!r}: {exc}")

        body = content.body
        if len(body) > MAX_OUTPUT:
            body = body[:MAX_OUTPUT]
            last_newline = body.rfind("\n")
            if last_newline != -1:
                body = body[: last_newline + 1]
            body += "(truncated)\n"

        return ReadResult(path=str(content.path), content=body)
