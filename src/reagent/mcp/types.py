from __future__ import annotations

from dataclasses import dataclass, field
from typing import Literal


@dataclass(frozen=True)
class ServerSpec:
    name: str
    transport: Literal["http", "stdio"] = "http"
    url: str | None = None
    headers: dict[str, str] = field(default_factory=dict)
    headers_command: str | None = None
    allow: tuple[str, ...] | None = None
    connect_timeout: float = 10.0
    call_timeout: float = 60.0
    command: str | None = None
    args: tuple[str, ...] = field(default_factory=tuple)
    env: dict[str, str] = field(default_factory=dict)

    def allows(self, tool: str) -> bool:
        return self.allow is None or tool in self.allow
