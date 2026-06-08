import inspect
import asyncio
from types import SimpleNamespace

import pytest

from reagent.config import AgentConfig, Config, LLMConfig, LLMModelsConfig, MCPConfig, SkillsConfig
import reagent.session.turn as turn
from reagent.session import Session
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
    config = Config(
        llm=LLMConfig(
            model="test-model",
            reasoning_effort="high",
            thinking_budget_tokens=1234,
            models=LLMModelsConfig(available=[]),
        ),
        agent=AgentConfig(max_turns=1),
        providers={},
        mcp=MCPConfig(servers={}),
        skills=SkillsConfig(enabled=True, paths=[]),
    )

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

    assert len(calls) == 1
    call = calls[0]
    assert call["model"] == "test-model"
    assert call["messages"][0]["role"] == "system"
    assert "You are REAgent" in call["messages"][0]["content"]
    assert call["messages"][1] == {"role": "user", "content": "hello"}
    assert call["tools"] == turn.build_tools()
    assert call["reasoning_effort"] == "high"
    assert call["thinking"] == {"type": "enabled", "budget_tokens": 1234}
    assert call["num_retries"] == 10


async def test_run_turn_includes_configured_skill_catalog(monkeypatch, tmp_path):
    skill_path = tmp_path / "skills" / "pe-analysis" / "SKILL.md"
    skill_path.parent.mkdir(parents=True)
    skill_path.write_text(
        """\
---
name: pe-analysis
description: Analyze Windows PE executables, DLLs, drivers, imports, exports, and resources.
---

# PE Analysis
""",
        encoding="utf-8",
    )
    calls = []
    session = Session()
    session.add_user("analyze sample.exe")
    config = Config(
        llm=LLMConfig(
            model="test-model",
            reasoning_effort="high",
            thinking_budget_tokens=1234,
            models=LLMModelsConfig(available=[]),
        ),
        agent=AgentConfig(max_turns=1),
        providers={},
        mcp=MCPConfig(servers={}),
        skills=SkillsConfig(enabled=True, paths=[str(tmp_path / "skills")]),
    )

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

    system_message = calls[0]["messages"][0]["content"]
    assert "Available skills:" in system_message
    assert "pe-analysis: Analyze Windows PE executables" in system_message
    assert str(skill_path.resolve()) not in system_message
    tool_names = {tool["function"]["name"] for tool in calls[0]["tools"]}
    assert "load_skill" in tool_names


async def test_run_turn_omits_load_skill_tool_without_configured_skills(monkeypatch):
    calls = []
    session = Session()
    session.add_user("hello")
    config = Config(
        llm=LLMConfig(
            model="test-model",
            reasoning_effort="high",
            thinking_budget_tokens=1234,
            models=LLMModelsConfig(available=[]),
        ),
        agent=AgentConfig(max_turns=1),
        providers={},
        mcp=MCPConfig(servers={}),
        skills=SkillsConfig(enabled=True, paths=[]),
    )

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

    tool_names = {tool["function"]["name"] for tool in calls[0]["tools"]}
    assert "load_skill" not in tool_names
