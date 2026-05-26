from __future__ import annotations

from dataclasses import dataclass
import os
from typing import Any, cast

from dotenv import load_dotenv

load_dotenv(override=True)
os.environ.setdefault("LITELLM_LOG", "ERROR")

from litellm import completion  # noqa: E402
from litellm.types.utils import ModelResponse  # noqa: E402


MODEL = os.environ["MODEL_ID"]


@dataclass
class SessionState:
    messages: list


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


def agent_loop(state: SessionState):
    while True:
        response = completion(
            model=MODEL,
            messages=state.messages,
            stream=False,
        )

        choice0 = cast(ModelResponse, response).choices[0]

        state.messages.append(
            {
                "role": "assistant",
                "content": extract_text(choice0.message),
            }
        )

        if choice0.finish_reason == "stop":
            return

        # if choice0.finish_reason != "tool_calls":
        #     return


def main() -> int:
    history = []
    while True:
        try:
            prompt = input("\033[36m> \033[0m")
        except (EOFError, KeyboardInterrupt):
            break

        if prompt.strip().lower() in ("/quit", "/exit"):
            break

        history.append({"role": "user", "content": prompt})
        state = SessionState(messages=history)
        agent_loop(state)

        result = state.messages[-1]["content"]
        if result:
            print()
            print(result)

        print()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
