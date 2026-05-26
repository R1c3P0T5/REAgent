from __future__ import annotations

from datetime import datetime, timezone
import json
import os
from typing import Any, cast

from dotenv import load_dotenv

load_dotenv(override=True)
os.environ.setdefault("LITELLM_LOG", "ERROR")

from litellm import completion  # noqa: E402
from litellm.exceptions import BadRequestError  # noqa: E402
from litellm.types.utils import ModelResponse  # noqa: E402

from reagent.session import Session  # noqa: E402
from reagent.tools import TOOLS, TOOL_HANDLERS  # noqa: E402


MODEL = os.environ["MODEL_ID"]
MAX_ITERATIONS = 50


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
    return (
        "You are a CTF agent.\n"
        f"Current date/time: {datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M UTC')}\n"
        f"Current working directory: {os.getcwd()}\n"
    )


def agent_loop(session: Session) -> None:
    for _ in range(MAX_ITERATIONS):
        messages = [{"role": "system", "content": system_prompt()}, *session.messages]
        try:
            response = completion(
                model=MODEL,
                messages=messages,
                tools=TOOLS,
                num_retries=10,
            )
        except BadRequestError as exc:
            session.add_assistant(f"Stopped: request rejected by API - {exc}")
            return

        choice0 = cast(ModelResponse, response).choices[0]
        message = choice0.message

        if choice0.finish_reason == "length":
            session.add_assistant("Stopped: response hit max tokens. The output may be incomplete.")
            return

        if choice0.finish_reason != "tool_calls":
            session.add_assistant(extract_text(message))
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
