import inspect
import asyncio
import json
from types import SimpleNamespace

import pytest

from reagent.config import AgentConfig, Config, LLMConfig, LLMModelsConfig, MCPConfig, SkillsConfig
from reagent.results import TextResult
import reagent.session.turn as turn
from reagent.session import Session, load_session
from reagent.session.recorder import SessionRecorder, read_entries
from reagent.session.turn import to_provider_messages, run_turn


def test_run_turn_is_coroutine():
    assert inspect.iscoroutinefunction(run_turn)


def test_to_provider_messages_strips_local_ids():
    messages = (
        {"role": "user", "content": "hello", "id": "m1", "parent_id": None},
        {"role": "assistant", "content": "hi", "id": "m2", "parent_id": "m1"},
    )

    assert to_provider_messages(messages) == [
        {"role": "user", "content": "hello"},
        {"role": "assistant", "content": "hi"},
    ]


def _test_config(*, max_turns=1):
    return Config(
        llm=LLMConfig(
            model="test-model",
            reasoning_effort="high",
            thinking_budget_tokens=1234,
            models=LLMModelsConfig(available=[]),
        ),
        agent=AgentConfig(max_turns=max_turns),
        providers={},
        mcp=MCPConfig(servers={}),
        skills=SkillsConfig(enabled=True, paths=[]),
    )


async def test_llm_call_finishes_in_background_after_caller_is_cancelled(monkeypatch):
    started = asyncio.Event()
    release = asyncio.Event()
    finished = asyncio.Event()

    async def fake_acompletion(**kwargs):
        started.set()
        await release.wait()
        finished.set()
        return object()

    monkeypatch.setattr(turn, "acompletion", fake_acompletion)

    task = asyncio.create_task(turn._call_llm(model="test", messages=[]))
    await started.wait()

    task.cancel()
    with pytest.raises(asyncio.CancelledError):
        await task

    assert not finished.is_set()

    release.set()
    await asyncio.wait_for(finished.wait(), timeout=1)


async def test_run_turn_uses_runtime_config(monkeypatch):
    calls = []
    session = Session()
    session.add_user("hello")
    config = _test_config()

    async def fake_call_llm(**kwargs):
        calls.append(kwargs)
        return SimpleNamespace(
            usage=None,
            choices=[
                SimpleNamespace(
                    finish_reason="stop",
                    message=SimpleNamespace(content="done", reasoning_content=""),
                )
            ],
        )

    monkeypatch.setattr(turn, "_call_llm", fake_call_llm)
    monkeypatch.setattr(turn, "make_compact_fn", lambda model: lambda messages: "")

    await run_turn(session, config)

    assert calls == [
        {
            "model": "test-model",
            "messages": [
                {"role": "system", "content": turn.system_prompt()},
                {"role": "user", "content": "hello"},
            ],
            "tools": turn.TOOLS,
            "reasoning_effort": "high",
            "thinking": {"type": "enabled", "budget_tokens": 1234},
            "max_retries": 10,
        }
    ]


async def test_run_turn_propagates_cancellation_without_recording_stopped_message(monkeypatch):
    started = asyncio.Event()
    session = Session()
    session.add_user("hello")

    async def fake_call_llm(**kwargs):
        started.set()
        await asyncio.Event().wait()

    monkeypatch.setattr(turn, "_call_llm", fake_call_llm)
    monkeypatch.setattr(turn, "make_compact_fn", lambda model: lambda messages: "")

    task = asyncio.create_task(run_turn(session, _test_config()))
    await started.wait()

    task.cancel()
    with pytest.raises(asyncio.CancelledError):
        await task

    assert session.messages == ({"role": "user", "content": "hello"},)


async def test_run_turn_cancellation_during_tool_handler_does_not_record_tool_call_block(
    monkeypatch, tmp_path
):
    handler_started = asyncio.Event()
    session = Session(
        recorder=SessionRecorder.create(
            root=tmp_path,
            cwd="/repo",
            model="model",
        )
    )
    session.add_user("hello")

    first_tool_call = SimpleNamespace(
        id="call-1",
        function=SimpleNamespace(name="fast_tool", arguments=json.dumps({"value": 1})),
    )
    second_tool_call = SimpleNamespace(
        id="call-2",
        function=SimpleNamespace(name="slow_tool", arguments=json.dumps({"value": 1})),
    )

    async def fake_call_llm(**kwargs):
        return SimpleNamespace(
            usage=None,
            choices=[
                SimpleNamespace(
                    finish_reason="tool_calls",
                    message=SimpleNamespace(
                        content=None,
                        reasoning_content="",
                        tool_calls=[first_tool_call, second_tool_call],
                    ),
                )
            ],
        )

    async def fast_tool(tool_input):
        return TextResult("already committed")

    async def slow_tool(tool_input):
        handler_started.set()
        await asyncio.Event().wait()
        return TextResult("late result")

    monkeypatch.setattr(turn, "_call_llm", fake_call_llm)
    monkeypatch.setattr(turn, "make_compact_fn", lambda model: lambda messages: "")
    session.tool_handlers = {"fast_tool": fast_tool, "slow_tool": slow_tool}

    task = asyncio.create_task(run_turn(session, _test_config()))
    await handler_started.wait()

    task.cancel()
    with pytest.raises(asyncio.CancelledError):
        await task

    assert session.messages == ({"role": "user", "content": "hello"},)
    assert session.tool_calls == 0

    assert session._recorder is not None
    entries, _ = read_entries(session._recorder.path)
    message_data = [entry["data"] for entry in entries if entry["type"] == "message"]
    assert message_data == [
        {
            "role": "user",
            "content": "hello",
            "id": message_data[0]["id"],
            "parent_id": None,
        }
    ]

    resumed = load_session(session._recorder.path)
    assert resumed.messages == ({"role": "user", "content": "hello"},)
    assert resumed.tool_calls == 0


async def test_run_turn_tool_cancellation_stops_remaining_tool_calls(monkeypatch):
    session = Session()
    session.add_user("hello")
    calls = []

    tool_calls = [
        SimpleNamespace(
            id=f"call-{i}",
            function=SimpleNamespace(name=name, arguments=json.dumps({"value": i})),
        )
        for i, name in enumerate(["cancel_tool", "second_tool", "third_tool"], start=1)
    ]

    async def fake_call_llm(**kwargs):
        return SimpleNamespace(
            usage=None,
            choices=[
                SimpleNamespace(
                    finish_reason="tool_calls",
                    message=SimpleNamespace(content=None, reasoning_content="", tool_calls=tool_calls),
                )
            ],
        )

    async def cancel_tool(tool_input):
        calls.append("cancel_tool")
        raise asyncio.CancelledError()

    async def second_tool(tool_input):
        calls.append("second_tool")
        return TextResult("second")

    async def third_tool(tool_input):
        calls.append("third_tool")
        return TextResult("third")

    monkeypatch.setattr(turn, "_call_llm", fake_call_llm)
    monkeypatch.setattr(turn, "make_compact_fn", lambda model: lambda messages: "")
    session.tool_handlers = {
        "cancel_tool": cancel_tool,
        "second_tool": second_tool,
        "third_tool": third_tool,
    }

    with pytest.raises(asyncio.CancelledError):
        await run_turn(session, _test_config())

    assert calls == ["cancel_tool"]
    assert session.messages == ({"role": "user", "content": "hello"},)
    assert session.tool_calls == 0
