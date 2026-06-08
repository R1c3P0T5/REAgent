import asyncio
import inspect
from collections.abc import Awaitable, Callable, Sequence
from typing import Any

from reagent.results import ToolResult
from reagent.skills import SkillMetadata
from reagent.tools.base import Tool
from reagent.tools.edit_file import EditFileTool
from reagent.tools.load_skill import LoadSkillTool
from reagent.tools.read_file import ReadFileTool
from reagent.tools.shell import ShellTool
from reagent.tools.task import (
    TaskCreateTool,
    TaskDeleteTool,
    TaskGetTool,
    TaskListTool,
    TaskRegistry,
    TaskUpdateTool,
)
from reagent.tools.write_file import WriteFileTool

AsyncHandler = Callable[[dict[str, Any]], Awaitable[ToolResult]]

_BASE_TOOLS: list[Tool] = [
    ShellTool(),
    ReadFileTool(),
    WriteFileTool(),
    EditFileTool(),
]

_TASK_TOOL_CLASSES = [TaskCreateTool, TaskListTool, TaskGetTool, TaskUpdateTool, TaskDeleteTool]

# Throwaway registry — schemas don't depend on registry state.
_schema_registry = TaskRegistry()
_TASK_SCHEMA_TOOLS = [cls(_schema_registry) for cls in _TASK_TOOL_CLASSES]

TOOLS: list[dict[str, Any]] = [t.to_schema() for t in _BASE_TOOLS + _TASK_SCHEMA_TOOLS]
TOOLS_BY_NAME: dict[str, Tool] = {}  # populated by register_tools for dynamically added tools

SILENT_TOOL_NAMES: frozenset[str] = frozenset(t.name for t in _TASK_SCHEMA_TOOLS)


def _as_async(fn: Callable[[dict[str, Any]], Any]) -> AsyncHandler:
    async def wrapper(params: dict[str, Any]) -> ToolResult:
        return await asyncio.to_thread(fn, params)

    return wrapper


BASE_TOOL_HANDLERS: dict[str, AsyncHandler] = {t.name: _as_async(t.run) for t in _BASE_TOOLS}

# Async handlers for dynamically registered tools (e.g. MCP), populated at startup.
EXTRA_HANDLERS: dict[str, AsyncHandler] = {}


def make_task_handlers(registry: TaskRegistry) -> dict[str, AsyncHandler]:
    """Return task tool handlers bound to a specific registry instance."""
    return {t.name: _as_async(t.run) for t in [cls(registry) for cls in _TASK_TOOL_CLASSES]}


def build_tool_objects(skills: list[SkillMetadata] | None = None) -> list[Tool]:
    tools = list(_BASE_TOOLS + _TASK_SCHEMA_TOOLS)
    if skills:
        tools.append(LoadSkillTool(skills))
    return tools


def register_tools(extra: Sequence[Tool]) -> None:
    for t in extra:
        TOOLS.append(t.to_schema())
        TOOLS_BY_NAME[t.name] = t
        run = t.run
        EXTRA_HANDLERS[t.name] = run if inspect.iscoroutinefunction(run) else _as_async(run)  # type: ignore[arg-type]


__all__ = [
    "Tool",
    "TOOLS",
    "TOOLS_BY_NAME",
    "AsyncHandler",
    "BASE_TOOL_HANDLERS",
    "EXTRA_HANDLERS",
    "SILENT_TOOL_NAMES",
    "build_tool_objects",
    "make_task_handlers",
    "register_tools",
]
