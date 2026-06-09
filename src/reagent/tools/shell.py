import asyncio
import re
import signal
import subprocess
import tempfile
from typing import Any

from reagent.constants import SHELL_OUTPUT_PREFIX
from reagent.results import ErrorResult, ShellResult, ToolResult
from reagent.tools.base import MAX_OUTPUT, Tool, params, prop


SHELL_TIMEOUT = 30
_HEAD_SIZE = 5_000
_TAIL_SIZE = MAX_OUTPUT - _HEAD_SIZE

_DANGEROUS_PATTERNS = [
    r"rm\s+-rf\s+/",
    r"mkfs",
    r"dd\s+if=",
    r":\(\)\s*\{.*\}",
    r">\s*/dev/sd",
]

_INTERRUPTED_RETURNCODES = {
    -signal.SIGINT,
    128 + signal.SIGINT,
}


def _truncate(output: str) -> str:
    if len(output) <= MAX_OUTPUT:
        return output

    with tempfile.NamedTemporaryFile(mode="w", prefix=SHELL_OUTPUT_PREFIX, suffix=".txt", dir="/tmp", delete=False) as f:
        f.write(output)
        spill_path = f.name

    head = output[:_HEAD_SIZE]
    tail = output[-_TAIL_SIZE:]
    omitted = len(output) - _HEAD_SIZE - _TAIL_SIZE
    return f"{head}\n... {omitted} chars omitted — full output saved to {spill_path} ...\n{tail}"


def run_shell(command: str, timeout: int) -> ToolResult:
    if any(re.search(p, command) for p in _DANGEROUS_PATTERNS):
        return ErrorResult("Error: Dangerous command blocked")

    try:
        result = subprocess.run(
            command,
            shell=True,
            capture_output=True,
            text=True,
            timeout=timeout,
        )

    except subprocess.TimeoutExpired:
        return ErrorResult(f"Error: Timeout ({timeout}s)")

    except (FileNotFoundError, OSError) as e:
        return ErrorResult(f"Error: {e}")

    if result.returncode in _INTERRUPTED_RETURNCODES:
        raise asyncio.CancelledError()

    output = (result.stdout + result.stderr).strip()
    return ShellResult(_truncate(output) if output else "(no output)")


class ShellTool(Tool):
    name = "shell"
    description = "Run a shell command in the current workspace."

    parameters = params({"command": prop("string")}, required=["command"])

    def run(self, params: dict[str, Any]) -> ToolResult:
        return run_shell(params["command"], SHELL_TIMEOUT)
