import asyncio

import pytest

from reagent.repl import (
    _BUSY_HINT,
    _Call,
    _PendingCalls,
    _ReplState,
    _cancel_active_turn,
    _clear_pending_calls,
    _enter_action,
)


async def test_cancel_active_turn_cancels_task_and_clears_busy_hint():
    async def wait_forever():
        await asyncio.Event().wait()

    task = asyncio.create_task(wait_forever())
    state = _ReplState(active_turn=task, hint=_BUSY_HINT)

    assert _cancel_active_turn(state)

    with pytest.raises(asyncio.CancelledError):
        await task
    assert state.hint == ""


def test_cancel_active_turn_reports_noop_without_active_task():
    state = _ReplState(hint=_BUSY_HINT)

    assert not _cancel_active_turn(state)
    assert state.hint == _BUSY_HINT


def test_clear_pending_calls_removes_interrupted_tool_display():
    calls = _PendingCalls()
    calls.calls["call-1"] = _Call(name="slow_tool", args={"value": 1}, started_at=0.0)

    assert _clear_pending_calls(calls)

    assert calls.calls == {}


def test_clear_pending_calls_reports_noop_when_empty():
    calls = _PendingCalls()

    assert not _clear_pending_calls(calls)


def test_enter_action_submits_non_empty_input_even_while_turn_may_be_running():
    assert _enter_action("next prompt") == "submit"


def test_enter_action_preserves_existing_newline_and_ignore_behaviors():
    assert _enter_action("line\\") == "newline"
    assert _enter_action("   ") == "ignore"
