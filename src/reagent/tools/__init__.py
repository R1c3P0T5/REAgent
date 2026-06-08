from collections.abc import Callable
from typing import Any

from reagent.results import ToolResult
from reagent.skills import SkillMetadata
from reagent.tools.base import Tool
from reagent.tools.edit_file import EditFileTool
from reagent.tools.load_skill import LoadSkillTool
from reagent.tools.read_file import ReadFileTool
from reagent.tools.shell import ShellTool
from reagent.tools.write_file import WriteFileTool

_BASE_TOOLS: list[Tool] = [ShellTool(), ReadFileTool(), WriteFileTool(), EditFileTool()]


def build_tool_objects(skills: list[SkillMetadata] | None = None) -> list[Tool]:
    tools = list(_BASE_TOOLS)
    if skills:
        tools.append(LoadSkillTool(skills))
    return tools


def build_tools(skills: list[SkillMetadata] | None = None) -> list[dict[str, Any]]:
    return [tool.to_schema() for tool in build_tool_objects(skills)]


def build_tool_handlers(skills: list[SkillMetadata] | None = None) -> dict[str, Callable[[dict[str, Any]], ToolResult]]:
    return {tool.name: tool.run for tool in build_tool_objects(skills)}


TOOLS: list[dict[str, Any]] = build_tools()
TOOL_HANDLERS: dict[str, Callable[[dict[str, Any]], ToolResult]] = build_tool_handlers()

__all__ = ["Tool", "TOOLS", "TOOL_HANDLERS", "build_tool_handlers", "build_tools"]
