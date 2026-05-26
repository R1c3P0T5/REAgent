from __future__ import annotations

from datetime import datetime, timezone
import json
import os
from typing import Any, cast

from dotenv import load_dotenv

load_dotenv(override=True)
os.environ.setdefault("LITELLM_LOG", "ERROR")

import litellm  # noqa: E402

litellm.drop_params = True
from litellm import completion  # noqa: E402
from litellm.exceptions import BadRequestError  # noqa: E402
from litellm.types.utils import ModelResponse  # noqa: E402

from reagent.compact import make_compact_fn  # noqa: E402
from reagent.session import Session  # noqa: E402
from reagent.tools import TOOLS, TOOL_HANDLERS  # noqa: E402


MODEL = os.environ["MODEL_ID"]
MAX_ITERATIONS = 50
THINKING_BUDGET = 8192


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


def system_prompt() -> str:
    return f"""\
You are an autonomous problem-solving agent. Work until the task is fully resolved.

Current date/time: {datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")}
Current working directory: {os.getcwd()}

Think before every action. After each result, reflect on what it tells you — \
then decide your next move. If an approach isn't working after a reasonable attempt, \
stop repeating it. Diagnose why it failed, reconsider your assumptions, and try \
something fundamentally different.

When you have the answer, state it clearly and stop.
"""


def agent_loop(session: Session) -> None:
    compact_fn = make_compact_fn(MODEL)

    for _ in range(MAX_ITERATIONS):
        before = session._estimate_tokens()
        session.compact(compact_fn)
        after = session._estimate_tokens()

        if after < before:
            print(f"\033[33m[compact: {before} → {after} tokens]\033[0m")

        messages = [{"role": "system", "content": system_prompt()}, *session.messages]
        try:
            resp = cast(
                ModelResponse,
                completion(
                    model=MODEL,
                    messages=messages,
                    tools=TOOLS,
                    reasoning_effort="medium",
                    thinking={"type": "enabled", "budget_tokens": THINKING_BUDGET},
                    num_retries=10,
                ),
            )
        except BadRequestError as exc:
            session.add_assistant(f"Stopped: request rejected by API - {exc}")
            return

        session.record_usage(getattr(resp, "usage", None))
        choice0 = resp.choices[0]
        message = choice0.message
        text = extract_text(message)

        if choice0.finish_reason == "length":
            session.add_assistant("Stopped: response hit max tokens. The output may be incomplete.")
            return

        thought = extract_reasoning(choice0.message) or text
        if thought and choice0.finish_reason == "tool_calls":
            session.add_think(thought)

        if choice0.finish_reason != "tool_calls":
            session.add_assistant(text)
            return

        if not message.tool_calls:
            raise RuntimeError(f"finish_reason=tool_calls but tool_calls is empty: {message}")

        session.add_tool_calls(message)

        for tc in message.tool_calls:
            name = tc.function.name or ""

            try:
                tool_input = json.loads(tc.function.arguments)
            except json.JSONDecodeError as exc:
                session.add_tool_result(tc.id, f"Error: invalid tool arguments: {exc}")
                continue

            print(f"\n\033[32m•\033[0m {name}({tool_input})")
            handler = TOOL_HANDLERS.get(name)
            result = handler(tool_input) if handler else f"Error: unknown tool {name!r}"

            session.add_tool_result(tc.id, result)

    session.add_assistant(f"Stopped: reached iteration limit of {MAX_ITERATIONS}.")


def main() -> int:
    session = Session()
    while True:
        try:
            prompt = input("\033[36m> \033[0m")
        except (EOFError, KeyboardInterrupt):
            break

        if prompt.strip().lower() in ("/quit", "/exit"):
            break

        session.add_user(prompt)
        agent_loop(session)
        print()
    return 0
