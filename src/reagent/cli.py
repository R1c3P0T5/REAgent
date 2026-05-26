from __future__ import annotations

from dataclasses import dataclass
import os
from typing import Any, Literal, TypedDict, cast

from dotenv import load_dotenv

load_dotenv(override=True)
os.environ.setdefault("LITELLM_LOG", "ERROR")

from litellm import completion  # noqa: E402
from litellm.types.utils import ModelResponse  # noqa: E402


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


def agent_loop(session: Session) -> None:
    while True:
        response = completion(
            model=MODEL,
            messages=session.history,
        )

        choice0 = cast(ModelResponse, response).choices[0]

        reply = Message(role="assistant", content=extract_text(choice0.message))
        session.history.append(reply)

        if choice0.finish_reason == "stop":
            return


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


if __name__ == "__main__":
    raise SystemExit(main())
