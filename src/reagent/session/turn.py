from __future__ import annotations

import asyncio
import json
from collections import deque
from collections.abc import Mapping
from typing import Any, cast

import litellm

litellm.drop_params = True
from litellm import acompletion  # noqa: E402
from litellm.exceptions import APIError, BadRequestError  # noqa: E402
from litellm.types.utils import ModelResponse  # noqa: E402

from reagent.compact import make_compact_fn  # noqa: E402
from reagent.config import Config  # noqa: E402
from reagent.results import ErrorResult  # noqa: E402
from reagent.session.prompt import system_prompt, task_context  # noqa: E402
from reagent.session.recorder import to_provider_message  # noqa: E402
from reagent.session.session import Session  # noqa: E402
from reagent.tools import TOOLS  # noqa: E402
from reagent.skills import SkillMetadata  # noqa: E402
from reagent.tools.load_skill import LoadSkillTool  # noqa: E402


def _consume_done(task: asyncio.Task[Any]) -> None:
    try:
        task.exception()
    except asyncio.CancelledError:
        pass


async def _call_llm(**kwargs: Any) -> Any:
    task = asyncio.create_task(acompletion(**kwargs))
    try:
        return await asyncio.shield(task)
    except asyncio.CancelledError:
        task.add_done_callback(_consume_done)
        raise


def extract_reasoning(message: Any) -> str:
    rc = getattr(message, "reasoning_content", None)
    if isinstance(rc, str) and rc.strip():
        return rc.strip()
    return ""


def extract_text(message: Any) -> str:
    content = getattr(message, "content", None)

    if isinstance(content, str):
        return content

    if not isinstance(content, list):
        return ""

    texts = []
    for block in content:
        text = block.get("text") if isinstance(block, dict) else getattr(block, "text", None)
        if text:
            texts.append(str(text))

    return "\n".join(texts).strip()


def to_provider_messages(messages: tuple[Mapping[str, Any], ...]) -> list[dict[str, Any]]:
    return [to_provider_message(message) for message in messages]


_STALL_THRESHOLD = 4  # turns on the same in_progress task before warning
_DOOM_LOOP_THRESHOLD = 3  # identical (tool, args) calls in a row before warning
# task_list / task_get are diagnostic reads the agent uses to orient itself;
# detecting "loops" on them would produce false positives.
_DOOM_LOOP_SKIP = frozenset({"task_list", "task_get"})


async def run_turn(session: Session, config: Config, skills: list[SkillMetadata] | None = None) -> None:
    compact_fn = make_compact_fn(config.llm.model)
    sys_prompt = system_prompt()
    tools = list(TOOLS)
    tool_handlers = dict(session.tool_handlers)
    if skills:
        load_skill_tool = LoadSkillTool(skills)
        tools.append(load_skill_tool.to_schema())

        async def load_skill_handler(params: dict[str, Any]):
            return await asyncio.to_thread(load_skill_tool.run, params)

        tool_handlers[load_skill_tool.name] = load_skill_handler

    stall_task_id: str | None = None
    stall_count: int = 0
    recent_calls: deque[tuple[str, str]] = deque(maxlen=_DOOM_LOOP_THRESHOLD)

    for _ in range(config.agent.max_turns):
        before = session._estimate_tokens()
        await session.compact(compact_fn)
        after = session._estimate_tokens()

        if after < before:
            session.emit_status(f"[compact: {before} → {after} tokens]")

        current_task_context = task_context(session.task_registry.list())
        system_content = f"{sys_prompt}\n{current_task_context}" if current_task_context else sys_prompt
        if stall_count >= _STALL_THRESHOLD:
            system_content += (
                f"\n\nSTALL: task {stall_task_id!r} has been in_progress for {stall_count} turns. "
                "First ask: is this task granular enough? If not, subdivide it. "
                "If the approach is genuinely exhausted, mark it failed with a diagnosis note "
                "and create a sibling task whose title names how the new approach differs."
            )
        messages = [{"role": "system", "content": system_content}, *to_provider_messages(session.messages)]
        session.emit_thinking_update("up", session._estimate_tokens())
        try:
            resp = cast(
                ModelResponse,
                await _call_llm(
                    model=config.llm.model,
                    messages=messages,
                    tools=tools,
                    reasoning_effort=config.llm.reasoning_effort,
                    thinking={"type": "enabled", "budget_tokens": config.llm.thinking_budget_tokens},
                    max_retries=10,
                ),
            )
        except BadRequestError as exc:
            session._sink.on_assistant(f"Stopped: request rejected by API - {exc}")
            return
        except APIError as exc:
            session._sink.on_assistant(f"Stopped: API error - {exc}")
            return
        except asyncio.CancelledError:
            raise
        except Exception as exc:
            session._sink.on_assistant(f"Stopped: {type(exc).__name__}: {exc}")
            return

        usage = getattr(resp, "usage", None)
        down_tokens = getattr(usage, "completion_tokens", 0) or 0
        session.emit_thinking_update("down", down_tokens)
        session.record_usage(usage)
        choice0 = resp.choices[0]
        message = choice0.message
        text = extract_text(message)

        if choice0.finish_reason == "length":
            session.add_assistant("Stopped: response hit max tokens. The output may be incomplete.")
            return

        thought = extract_reasoning(choice0.message)
        if thought:
            session.add_think(thought)

        if choice0.finish_reason != "tool_calls":
            session.add_assistant(text)
            return

        if not message.tool_calls:
            raise RuntimeError(f"finish_reason=tool_calls but tool_calls is empty: {message}")

        tool_results = []
        for tc in message.tool_calls:
            name = tc.function.name or ""

            try:
                tool_input = json.loads(tc.function.arguments)
            except json.JSONDecodeError as exc:
                tool_results.append((tc.id, ErrorResult(f"Error: invalid tool arguments: {exc}")))
                continue

            session.emit_tool_call(tc.id, name, tool_input)

            # Doom loop: identical (tool, args) repeated _DOOM_LOOP_THRESHOLD times in a row
            if name not in _DOOM_LOOP_SKIP:
                sig = (name, json.dumps(tool_input, sort_keys=True))
                recent_calls.append(sig)
                if len(recent_calls) == _DOOM_LOOP_THRESHOLD and len(set(recent_calls)) == 1:
                    recent_calls.clear()
                    tool_results.append((
                        tc.id,
                        ErrorResult(
                            f"LOOP DETECTED: '{name}' called with identical arguments "
                            f"{_DOOM_LOOP_THRESHOLD} times in a row. This approach is not working. "
                            "Stop, diagnose the root cause, and try something fundamentally different."
                        ),
                    ))
                    continue

            handler = tool_handlers.get(name)
            if handler is not None:
                result = await handler(tool_input)
            else:
                result = ErrorResult(f"Error: unknown tool {name!r}")

            tool_results.append((tc.id, result))

        session.add_tool_calls(message)
        for tool_call_id, result in tool_results:
            session.add_tool_result(tool_call_id, result)

        # Stall detection: same in_progress task with no status change
        in_progress = [t for t in session.task_registry.list() if t.status == "in_progress"]
        current_id = in_progress[0].id if in_progress else None
        if current_id is not None and current_id == stall_task_id:
            stall_count += 1
        else:
            stall_task_id = current_id
            stall_count = 0

    session.add_assistant(f"Stopped: reached iteration limit of {config.agent.max_turns}.")
