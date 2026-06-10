from __future__ import annotations

import os
from datetime import datetime, timezone

from reagent.tools.task import Task


_OPEN_TASK_STATUSES = frozenset({"pending", "in_progress", "failed"})
_MAX_NOTE_CHARS = 300
_MAX_NOTE_CHARS_FAILED = 600  # failed tasks need more room for diagnosis


def _clip_note(note: str, limit: int = _MAX_NOTE_CHARS) -> str:
    note = " ".join(note.split())
    if len(note) <= limit:
        return note
    return f"{note[: limit - 1].rstrip()}..."


def task_context(tasks: list[Task]) -> str:
    open_tasks = [task for task in tasks if task.status in _OPEN_TASK_STATUSES]
    if not open_tasks:
        return ""

    open_ids = {task.id for task in open_tasks}
    by_parent: dict[str | None, list[Task]] = {}
    for task in open_tasks:
        parent_id = task.parent_id if task.parent_id in open_ids else None
        by_parent.setdefault(parent_id, []).append(task)

    lines = [
        "## Current task context",
        "",
        "This is live session state injected for continuity. Use it before deciding what to do next.",
        "Update these tasks with task tools as work progresses; do not recreate duplicate tasks.",
        "",
    ]

    def walk(parent_id: str | None, depth: int) -> None:
        for task in by_parent.get(parent_id, []):
            indent = "  " * depth
            lines.append(f"{indent}- [{task.status}] {task.id}: {task.title}")
            if task.notes:
                limit = _MAX_NOTE_CHARS_FAILED if task.status == "failed" else _MAX_NOTE_CHARS
                lines.append(f"{indent}  notes: {_clip_note(task.notes, limit)}")
            walk(task.id, depth + 1)

    walk(None, 0)
    return "\n".join(lines)


def system_prompt() -> str:
    return f"""\
You are an autonomous problem-solving agent. Work until the task is fully resolved.

Current date/time: {datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")}
Current working directory: {os.getcwd()}

Think before every action. After each result, reflect on what it tells you — \
then decide your next move. If an approach isn't working after a reasonable attempt, \
stop repeating it. Diagnose why it failed, reconsider your assumptions, and try \
something fundamentally different.

Work like a careful engineer: decompose large work into small verifiable units, \
plan before acting, test explicit hypotheses, preserve durable findings, and verify before claiming completion.

When you have the answer, state it clearly and stop.

## Tasks

Use task tools for multi-step work: 3+ steps, independent sub-goals, or hypothesis → verify loops.
Skip for single actions or conversational requests.

**Structure** — one root task per goal, children for each phase:
1. explore — gather information needed to act
2. plan — record decisions and approach (complete before implement)
3. implement — one subtask per logical unit
4. verify — confirm outcome matches goal

**Starting** — call task_create for the full plan first; mark exactly one task in_progress before any other action.

**Rhythm** — before each tool call, check: is the right task in_progress? Are notes current?
Every 3–5 tool calls, pause: update notes with findings, revise remaining plan if needed.
When a phase completes, update its tasks before starting the next phase.

**Ongoing** — revise/subdivide as you learn; complete tasks immediately when done; delete irrelevant ones.
On a failed task: mark it failed with a note on why, then create a sibling task with a different approach — do not retry the same approach or abandon the parent goal.

## Skills

If a skill in load_skill matches the current task, call it before proceeding.
"""
