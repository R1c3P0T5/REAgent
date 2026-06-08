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

registry = TaskRegistry()


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
    description = "Create a TODO task. Pass parent_id to nest under an existing task."

    @property
    def parameters(self) -> dict[str, Any]:
        return params(
            {
                "title": prop("string", "Short task title"),
                "description": prop("string", "Optional details"),
                "parent_id": prop("string", "Parent task ID to nest under"),
            },
            required=["title"],
        )

    def run(self, p: dict[str, Any]) -> ToolResult:
        result = registry.create(p["title"], p.get("description", ""), p.get("parent_id"))
        if isinstance(result, str):
            return ErrorResult(f"Error: {result}")
        return ShellResult(json.dumps(asdict(result)))


class TaskListTool(Tool):
    name = "task_list"
    description = "List all TODO tasks as a tree."

    @property
    def parameters(self) -> dict[str, Any]:
        return params({}, required=[])

    def run(self, p: dict[str, Any]) -> ToolResult:
        tasks = registry.list()
        return ShellResult(json.dumps([asdict(t) for t in tasks]))


class TaskGetTool(Tool):
    name = "task_get"
    description = "Get a task and its direct children."

    @property
    def parameters(self) -> dict[str, Any]:
        return params({"task_id": prop("string")}, required=["task_id"])

    def run(self, p: dict[str, Any]) -> ToolResult:
        task = registry.get(p["task_id"])
        if task is None:
            return ErrorResult(f"Error: task {p['task_id']!r} not found")
        return ShellResult(json.dumps(asdict(task)))


class TaskUpdateTool(Tool):
    name = "task_update"
    description = "Update a task's status or notes. status: pending | in_progress | completed | cancelled | failed"

    @property
    def parameters(self) -> dict[str, Any]:
        return params(
            {
                "task_id": prop("string"),
                "status": prop("string", "pending | in_progress | completed | cancelled | failed"),
                "notes": prop("string", "Optional progress notes"),
            },
            required=["task_id"],
        )

    def run(self, p: dict[str, Any]) -> ToolResult:
        status = p.get("status")
        if status is not None and status not in _VALID_STATUSES:
            return ErrorResult(f"Error: invalid status {status!r}. Use: {', '.join(sorted(_VALID_STATUSES))}")
        task = registry.update(p["task_id"], status=status, notes=p.get("notes"))  # type: ignore[arg-type]
        return ShellResult(json.dumps(asdict(task))) if task else ErrorResult(f"Error: task {p['task_id']!r} not found")


class TaskDeleteTool(Tool):
    name = "task_delete"
    description = "Remove a task from the list."

    @property
    def parameters(self) -> dict[str, Any]:
        return params({"task_id": prop("string")}, required=["task_id"])

    def run(self, p: dict[str, Any]) -> ToolResult:
        if not registry.delete(p["task_id"]):
            return ErrorResult(f"Error: task {p['task_id']!r} not found")
        return ShellResult(json.dumps({"deleted": p["task_id"]}))
