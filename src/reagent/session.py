from __future__ import annotations

import json
from typing import Any, Literal, TypedDict

TOKEN_LIMIT = 80_000


class UserMessage(TypedDict):
    role: Literal["user"]
    content: str


class AssistantMessage(TypedDict):
    role: Literal["assistant"]
    content: str | None


class AssistantToolCallMessage(TypedDict):
    role: Literal["assistant"]
    content: str | None
    tool_calls: list


class ToolMessage(TypedDict):
    role: Literal["tool"]
    tool_call_id: str
    content: str


Message = UserMessage | AssistantMessage | AssistantToolCallMessage | ToolMessage


class Session:
    def __init__(self) -> None:
        self._history: list[Message] = []

    @property
    def messages(self) -> tuple[Message, ...]:
        return tuple(self._history)

    def add_user(self, content: str) -> None:
        self._history.append(UserMessage(role="user", content=content))

    def add_assistant(self, content: str) -> None:
        self._history.append(AssistantMessage(role="assistant", content=content))
        if content:
            print(f"\n{content}")

    def add_tool_calls(self, raw_message: Any) -> None:
        self._history.append(
            AssistantToolCallMessage(
                role="assistant",
                content=raw_message.content,
                tool_calls=raw_message.tool_calls,
            )
        )

    def add_tool_result(self, tool_call_id: str, content: str) -> None:
        self._history.append(ToolMessage(role="tool", tool_call_id=tool_call_id, content=content))
        print(f"\033[90m{content}\033[0m")

    def _estimate_tokens(self) -> int:
        return len(json.dumps(list(self._history), default=str)) // 4

    def truncate(self) -> None:
        if self._estimate_tokens() <= TOKEN_LIMIT:
            return

        # Find turn boundaries: each UserMessage (except the first) starts a new turn.
        # Drop whole turns from index 1 onward until we're under the limit.
        while self._estimate_tokens() > TOKEN_LIMIT and len(self._history) > 1:
            # Find the end of the first droppable turn (from index 1 to the next UserMessage)
            end = 2
            while end < len(self._history) and self._history[end]["role"] != "user":
                end += 1
            del self._history[1:end]
