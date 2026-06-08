import asyncio

import pytest

from reagent.repl import (
    _BUSY_HINT,
    _Call,
    _PendingCalls,
    _ReplState,
    _SlashRoute,
    _cancel_active_turn,
    _clear_pending_calls,
    _enter_action,
    _exit_hint_expired,
    _fmt_usage,
    _route_slash_result,
)
from reagent.slash_commands import SlashResult


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


def test_route_slash_result_submits_normal_input():
    result = _route_slash_result("hello", SlashResult(outcome="not_slash"))

    assert result == _SlashRoute(action="submit", prompt="hello")


def test_route_slash_result_submits_expanded_prompt():
    result = _route_slash_result("/draft topic", SlashResult(outcome="submit_prompt", prompt="expanded prompt"))

    assert result == _SlashRoute(action="submit", prompt="expanded prompt")


def test_route_slash_result_displays_skill_name_for_skill_prompt():
    result = _route_slash_result(
        "/binary-triage target.exe",
        SlashResult(outcome="submit_prompt", prompt="expanded skill prompt", command_name="binary-triage"),
    )

    assert result == _SlashRoute(
        action="submit",
        prompt="expanded skill prompt",
        message="/binary-triage",
    )


def test_route_slash_result_exits():
    result = _route_slash_result("/exit", SlashResult(outcome="exit"))

    assert result == _SlashRoute(action="exit")


def test_route_slash_result_keeps_local_message_out_of_prompt_submission():
    result = _route_slash_result("/status", SlashResult(outcome="handled", message="status text"))

    assert result == _SlashRoute(action="handled", message="status text")


def test_route_slash_result_treats_unknown_as_local_message():
    result = _route_slash_result("/nope", SlashResult(outcome="unknown", message="Unknown command: /nope"))

    assert result == _SlashRoute(action="handled", message="Unknown command: /nope")


def test_ctrl_c_hint_clears_after_exit_window():
    assert _exit_hint_expired(
        now=3.0,
        last_ctrl_c=1.0,
        hint="Press Ctrl+C again to exit",
        active_turn=False,
    )


def test_ctrl_c_hint_does_not_clear_while_turn_is_active():
    assert not _exit_hint_expired(
        now=3.0,
        last_ctrl_c=1.0,
        hint="Press Ctrl+C again to exit",
        active_turn=True,
    )


def test_usage_summary_omits_missing_optional_counts():
    assert _fmt_usage(total=1500, input_tokens=1000, output_tokens=500, cached_tokens=0, reasoning_tokens=0) == (
        "Usage: total=1,500 input=1,000 output=500"
    )


def test_usage_summary_includes_cached_and_reasoning_counts():
    assert (
        _fmt_usage(
            total=107505,
            input_tokens=92781,
            output_tokens=14724,
            cached_tokens=2585600,
            reasoning_tokens=4631,
        )
        == "Usage: total=107,505 input=92,781 (+ 2,585,600 cached) output=14,724 (reasoning 4,631)"
    )
