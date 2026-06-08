import asyncio
import inspect
from collections.abc import Awaitable, Callable, Sequence
from typing import Any

from reagent.results import ToolResult
from reagent.tools.base import Tool
from reagent.tools.edit_file import EditFileTool
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

TOOLS: list[dict[str, Any]] = [t.to_schema() for t in _BASE_TOOLS] + [
    cls.to_schema() for cls in _TASK_TOOL_CLASSES
]

SILENT_TOOL_NAMES: frozenset[str] = frozenset(cls.name for cls in _TASK_TOOL_CLASSES)


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


def register_tools(extra: Sequence[Tool]) -> None:
    TOOLS.extend(t.to_schema() for t in extra)
    for t in extra:
        run = t.run
        EXTRA_HANDLERS[t.name] = run if inspect.iscoroutinefunction(run) else _as_async(run)  # type: ignore[arg-type]


__all__ = ["Tool", "TOOLS", "AsyncHandler", "BASE_TOOL_HANDLERS", "EXTRA_HANDLERS", "SILENT_TOOL_NAMES", "make_task_handlers", "register_tools"]
