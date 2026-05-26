from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
import json
import os
from typing import Any, Literal, TypedDict, cast

from dotenv import load_dotenv

load_dotenv(override=True)
os.environ.setdefault("LITELLM_LOG", "ERROR")

from litellm import completion  # noqa: E402
from litellm.types.utils import ModelResponse  # noqa: E402

from reagent.tools import TOOLS, TOOL_HANDLERS  # noqa: E402


MODEL = os.environ["MODEL_ID"]


class Message(TypedDict):
    role: Literal["user", "assistant", "tool"]
    content: str | None


@dataclass
class Session:
    history: list[Message]


def extract_text(message: Any) -> str:
    content = getattr(message, "content", None)

    if isinstance(content, str):
        return content

    if not isinstance(content, list):
        return ""

    texts = []
    for block in content:
        text = (
            block.get("text")
            if isinstance(block, dict)
            else getattr(block, "text", None)
        )
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
    while True:
        messages = [{"role": "system", "content": system_prompt()}, *session.history]
        response = completion(
            model=MODEL,
            messages=messages,
            tools=TOOLS,
        )

        choice0 = cast(ModelResponse, response).choices[0]
        message = choice0.message

        if choice0.finish_reason != "tool_calls":
            session.history.append(
                Message(role="assistant", content=extract_text(message))
            )
            return

        if not message.tool_calls:
            raise RuntimeError(
                f"finish_reason=tool_calls but tool_calls is empty: {message}"
            )

        session.history.append(
            {
                "role": "assistant",
                "content": message.content,
                "tool_calls": message.tool_calls,  # type: ignore[arg-type]
            }
        )

        for tc in message.tool_calls:
            name = tc.function.name or ""

            try:
                tool_input = json.loads(tc.function.arguments)
            except json.JSONDecodeError as exc:
                session.history.append(
                    {
                        "role": "tool",
                        "tool_call_id": tc.id,  # type: ignore[arg-type]
                        "content": f"Error: invalid tool arguments: {exc}",
                    }
                )
                continue

            print(f"\n\033[32m•\033[0m {name}({tool_input})")
            handler = TOOL_HANDLERS.get(name)
            result = handler(tool_input) if handler else f"Error: unknown tool {name!r}"
            print(f"\033[90m{result}\033[0m")

            session.history.append(
                {"role": "tool", "tool_call_id": tc.id, "content": result}  # type: ignore[arg-type]
            )


def main() -> int:
    session = Session(history=[])
    while True:
        try:
            prompt = input("\033[36m> \033[0m")
        except (EOFError, KeyboardInterrupt):
            break

        if prompt.strip().lower() in ("/quit", "/exit"):
            break

        session.history.append(Message(role="user", content=prompt))
        agent_loop(session)

        result = session.history[-1]["content"]
        if result:
            print()
            print(result)

        print()
    return 0
