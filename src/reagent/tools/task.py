from __future__ import annotations

import json
import threading
import uuid
from dataclasses import asdict, dataclass
from typing import Any, Literal

from reagent.results import ErrorResult, ShellResult, ToolResult
from reagent.tools.base import Tool, params, prop


TaskStatus = Literal["pending", "in_progress", "completed", "cancelled", "failed"]
_STATUS_ICON = {"pending": "○", "in_progress": "◉", "completed": "✓", "cancelled": "⊘", "failed": "✗"}
_VALID_STATUSES: frozenset[str] = frozenset(_STATUS_ICON)


@dataclass
class Task:
    id: str
    title: str
    description: str
    status: TaskStatus
    parent_id: str | None = None
    notes: str = ""


class TaskRegistry:
    def __init__(self) -> None:
        self._tasks: dict[str, Task] = {}
        self._lock = threading.Lock()

    def create(self, title: str, description: str = "", parent_id: str | None = None) -> Task | str:
        """Returns Task on success, or an error string if parent_id not found."""
        with self._lock:
            if parent_id is not None and parent_id not in self._tasks:
                return f"parent task {parent_id!r} not found"
            task = Task(
                id=str(uuid.uuid4())[:8],
                title=title,
                description=description,
                status="pending",
                parent_id=parent_id,
            )
            self._tasks[task.id] = task
            return task

    def get(self, task_id: str) -> Task | None:
        with self._lock:
            return self._tasks.get(task_id)

    def list(self) -> list[Task]:
        with self._lock:
            return list(self._tasks.values())

    def update(self, task_id: str, *, status: TaskStatus | None = None, notes: str | None = None) -> Task | None:
        with self._lock:
            task = self._tasks.get(task_id)
            if task is None:
                return None
            if status is not None:
                task.status = status
                if status in ("completed", "cancelled", "failed"):
                    # cascade to all descendants
                    queue = [t.id for t in self._tasks.values() if t.parent_id == task_id]
                    while queue:
                        tid = queue.pop()
                        self._tasks[tid].status = status
                        queue.extend(t.id for t in self._tasks.values() if t.parent_id == tid)
            if notes is not None:
                task.notes = notes
            return task

    def delete(self, task_id: str) -> bool:
        with self._lock:
            if task_id not in self._tasks:
                return False
            # collect all descendants breadth-first then remove together
            to_delete = [task_id]
            i = 0
            while i < len(to_delete):
                current = to_delete[i]
                to_delete.extend(t.id for t in self._tasks.values() if t.parent_id == current)
                i += 1
            for tid in to_delete:
                self._tasks.pop(tid, None)
            return True

def fmt_tree_lines(tasks: list[Task]) -> list[tuple[str, str, str]]:
    """Returns (indent, icon, title) tuples for UI rendering."""
    by_parent: dict[str | None, list[Task]] = {}
    for t in tasks:
        by_parent.setdefault(t.parent_id, []).append(t)

    def _walk(parent_id: str | None, depth: int) -> list[tuple[str, str, str]]:
        result: list[tuple[str, str, str]] = []
        for task in by_parent.get(parent_id, []):
            result.append(("  " * depth, _STATUS_ICON.get(task.status, "○"), task.title))
            result.extend(_walk(task.id, depth + 1))
        return result

    return _walk(None, 0)


class TaskCreateTool(Tool):
    name = "task_create"
    description = (
        "Create a task. Call this first to lay out the full plan before acting. "
        "Pass parent_id to nest under a phase or goal."
    )
    parameters = params(
        {
            "title": prop("string", "Short task title"),
            "description": prop("string", "Acceptance criteria or planned approach"),
            "parent_id": prop("string", "Parent task ID to nest under"),
        },
        required=["title"],
    )

    def __init__(self, registry: TaskRegistry) -> None:
        self._registry = registry

    def run(self, params: dict[str, Any]) -> ToolResult:
        result = self._registry.create(params["title"], params.get("description", ""), params.get("parent_id"))
        if isinstance(result, str):
            return ErrorResult(f"Error: {result}")
        return ShellResult(json.dumps(asdict(result)))


class TaskListTool(Tool):
    name = "task_list"
    description = "List all tasks including completed/cancelled ones (injected context only shows open tasks)."
    parameters = params({}, required=[])

    def __init__(self, registry: TaskRegistry) -> None:
        self._registry = registry

    def run(self, params: dict[str, Any]) -> ToolResult:
        tasks = self._registry.list()
        return ShellResult(json.dumps([asdict(t) for t in tasks]))


class TaskGetTool(Tool):
    name = "task_get"
    description = "Get full task details including untruncated notes (injected context clips notes at 300 chars)."
    parameters = params({"task_id": prop("string")}, required=["task_id"])

    def __init__(self, registry: TaskRegistry) -> None:
        self._registry = registry

    def run(self, params: dict[str, Any]) -> ToolResult:
        task = self._registry.get(params["task_id"])
        if task is None:
            return ErrorResult(f"Error: task {params['task_id']!r} not found")
        return ShellResult(json.dumps(asdict(task)))


class TaskUpdateTool(Tool):
    name = "task_update"
    description = (
        "Update a task's status or notes. "
        "Notes should capture key findings and decisions — enough to resume the task cold. "
        "Call before switching tasks and after completing a phase."
    )
    parameters = params(
        {
            "task_id": prop("string"),
            "status": prop("string", "pending | in_progress | completed | cancelled | failed"),
            "notes": prop("string", "Findings and decisions so far; written to be resumable"),
        },
        required=["task_id"],
    )

    def __init__(self, registry: TaskRegistry) -> None:
        self._registry = registry

    def run(self, params: dict[str, Any]) -> ToolResult:
        status = params.get("status")
        if status is not None and status not in _VALID_STATUSES:
            return ErrorResult(f"Error: invalid status {status!r}. Use: {', '.join(sorted(_VALID_STATUSES))}")
        task = self._registry.update(params["task_id"], status=status, notes=params.get("notes"))  # type: ignore[arg-type]
        return ShellResult(json.dumps(asdict(task))) if task else ErrorResult(f"Error: task {params['task_id']!r} not found")


class TaskDeleteTool(Tool):
    name = "task_delete"
    description = "Delete a task and all its subtasks."
    parameters = params({"task_id": prop("string")}, required=["task_id"])

    def __init__(self, registry: TaskRegistry) -> None:
        self._registry = registry

    def run(self, params: dict[str, Any]) -> ToolResult:
        if not self._registry.delete(params["task_id"]):
            return ErrorResult(f"Error: task {params['task_id']!r} not found")
        return ShellResult(json.dumps({"deleted": params["task_id"]}))
