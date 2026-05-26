from __future__ import annotations

from typing import Any, Literal, TypedDict


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
