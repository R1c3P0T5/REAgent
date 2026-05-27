from __future__ import annotations

from typing import Protocol, runtime_checkable


@runtime_checkable
class OutputSink(Protocol):
    def on_assistant(self, text: str) -> None: ...
    def on_think(self, text: str) -> None: ...
    def on_tool_call(self, name: str, args: dict) -> None: ...
    def on_tool_result(self, tool_call_id: str, content: str) -> None: ...
    def on_status(self, msg: str) -> None: ...


class TerminalSink:
    def on_assistant(self, text: str) -> None:
        if text:
            print(f"\n{text}")

    def on_think(self, text: str) -> None:
        if text:
            print(f"\n\033[90m{text}\033[0m")

    def on_tool_call(self, name: str, args: dict) -> None:
        print(f"\n\033[32m•\033[0m {name}({args})")

    def on_tool_result(self, tool_call_id: str, content: str) -> None:
        print(f"\033[90m{content}\033[0m")

    def on_status(self, msg: str) -> None:
        print(msg)


class SilentSink:
    def on_assistant(self, text: str) -> None:
        pass

    def on_think(self, text: str) -> None:
        pass

    def on_tool_call(self, name: str, args: dict) -> None:
        pass

    def on_tool_result(self, tool_call_id: str, content: str) -> None:
        pass

    def on_status(self, msg: str) -> None:
        pass
