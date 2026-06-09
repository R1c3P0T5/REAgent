from __future__ import annotations

import asyncio
import json
import os
import subprocess
from collections.abc import Callable
from contextlib import AsyncExitStack, suppress
from dataclasses import dataclass
from datetime import timedelta
from types import TracebackType
from typing import Any

from mcp import ClientSession
from mcp.client.stdio import StdioServerParameters, stdio_client
from mcp.client.streamable_http import streamablehttp_client
from mcp.types import Tool

from reagent.mcp.types import ServerSpec
from reagent.results import ErrorResult, TextResult, ToolResult


@dataclass
class _Entry:
    spec: ServerSpec
    session: ClientSession
    tool: str
    input_schema: dict[str, Any]
    description: str


def _run_headers_cmd(command: str, timeout: float = 10.0) -> dict[str, str]:
    """Run a shell command and parse its stdout as a JSON object of header key/values.

    For servers whose token rotates out-of-band (e.g. written to a local file on each
    restart). Runs fresh on every connection; the value is never stored.
    """
    proc = subprocess.run(command, shell=True, capture_output=True, text=True, timeout=timeout)
    if proc.returncode != 0:
        raise RuntimeError(f"headers_command failed ({proc.returncode}): {proc.stderr.strip()}")
    data = json.loads(proc.stdout)
    if not isinstance(data, dict) or not all(isinstance(v, str) for v in data.values()):
        raise ValueError("headers_command must output a JSON object of string values")
    return data


class MCPClient:
    def __init__(self, specs: list[ServerSpec], emit: Callable[[str], None] | None = None) -> None:
        self._specs = list(specs)
        self._emit = emit or (lambda _msg: None)
        self._stack = AsyncExitStack()
        self._tools: dict[str, _Entry] = {}

    async def __aenter__(self) -> MCPClient:
        await self._stack.__aenter__()
        for spec in self._specs:
            await self._connect(spec)
        return self

    async def __aexit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        tb: TracebackType | None,
    ) -> bool | None:
        return await self._stack.__aexit__(exc_type, exc, tb)

    async def _connect(self, spec: ServerSpec) -> None:
        stack = AsyncExitStack()
        try:
            session, tools = await self._open(spec, stack)
        except BaseException as exc:
            with suppress(BaseException):
                await stack.aclose()
            if isinstance(exc, (KeyboardInterrupt, SystemExit)):
                raise
            self._emit(f"[mcp] {spec.name}: connection failed, skipping ({type(exc).__name__})")
            return
        self._stack.push_async_callback(stack.aclose)

        count = 0
        for tool in tools:
            if not spec.allows(tool.name):
                continue
            self._tools[f"{spec.name}__{tool.name}"] = _Entry(
                spec=spec,
                session=session,
                tool=tool.name,
                input_schema=tool.inputSchema or {"type": "object", "properties": {}},
                description=tool.description or "",
            )
            count += 1
        self._emit(f"[mcp] {spec.name}: {count} tool(s) ready")

    async def _open(self, spec: ServerSpec, stack: AsyncExitStack) -> tuple[ClientSession, list[Tool]]:
        if spec.transport == "stdio":
            assert spec.command is not None
            params = StdioServerParameters(
                command=spec.command,
                args=list(spec.args),
                env={**os.environ, **spec.env},
            )
            devnull = stack.enter_context(open(os.devnull, "w"))
            read, write = await stack.enter_async_context(stdio_client(params, errlog=devnull))

        else:
            assert spec.url is not None
            headers = dict(spec.headers)
            if spec.headers_command:
                headers.update(await asyncio.to_thread(_run_headers_cmd, spec.headers_command, spec.connect_timeout))
            read, write, _ = await stack.enter_async_context(
                streamablehttp_client(
                    spec.url,
                    headers=headers,
                    timeout=timedelta(seconds=spec.connect_timeout),
                )
            )

        session = await stack.enter_async_context(ClientSession(read, write))
        await session.initialize()
        return session, (await session.list_tools()).tools

    def schemas(self) -> list[dict[str, Any]]:
        return [
            {
                "type": "function",
                "function": {
                    "name": name,
                    "description": entry.description,
                    "parameters": entry.input_schema,
                },
            }
            for name, entry in self._tools.items()
        ]

    def list_tools(self) -> list[tuple[str, str, dict[str, Any]]]:
        return [(name, entry.description, entry.input_schema) for name, entry in self._tools.items()]

    def has(self, name: str) -> bool:
        return name in self._tools

    @property
    def tool_names(self) -> list[str]:
        return list(self._tools)

    async def call(self, name: str, args: dict[str, Any]) -> ToolResult:
        entry = self._tools.get(name)
        if entry is None:
            return ErrorResult(f"Error: unknown MCP tool {name!r}")
        try:
            result = await asyncio.wait_for(
                entry.session.call_tool(entry.tool, arguments=args),
                timeout=entry.spec.call_timeout,
            )
        except asyncio.TimeoutError:
            return ErrorResult(f"Error: MCP tool {name!r} timed out after {entry.spec.call_timeout}s")
        except Exception as exc:
            return ErrorResult(f"Error: {exc}")
        return TextResult(content=result.model_dump_json())
