from __future__ import annotations

from dataclasses import dataclass
import os

from dotenv import load_dotenv
from openai import OpenAI

load_dotenv(override=True)

client = OpenAI(api_key=os.environ.get("OPENAI_API_KEY"))
MODEL = os.environ["MODEL_ID"]


@dataclass
class SessionState:
    messages: list


def agent_loop(state: SessionState):
    while True:
        response = client.chat.completions.create(
            model=MODEL,
            messages=state.messages,
            max_completion_tokens=8000,
        )
        state.messages.append(
            {"role": "assistant", "content": response.choices[0].message.content}
        )

        if response.choices[0].finish_reason == "stop":
            return

        # if response.choices[0].finish_reason != "tool_calls":
        #     return


def main() -> int:
    history = []
    while True:
        try:
            prompt = input("\033[36m > \033[0m")
        except (EOFError, KeyboardInterrupt):
            break

        if prompt.strip().lower() in ("/quit", "/exit"):
            break

        history.append({"role": "user", "content": prompt})
        state = SessionState(messages=history)
        agent_loop(state)

        result = state.messages[-1]["content"]
        if result:
            print(result)

        print()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
