import re
import subprocess
from typing import Any

from reagent.tools.base import MAX_OUTPUT, Tool, params, prop


SHELL_TIMEOUT = 30

_DANGEROUS_PATTERNS = [
    r"rm\s+-rf\s+/",
    r"mkfs",
    r"dd\s+if=",
    r":\(\)\s*\{.*\}",
    r">\s*/dev/sd",
]


def run_shell(command: str, timeout: int) -> str:
    if any(re.search(p, command) for p in _DANGEROUS_PATTERNS):
        return "Error: Dangerous command blocked"

    try:
        result = subprocess.run(
            command,
            shell=True,
            capture_output=True,
            text=True,
            timeout=timeout,
        )

    except subprocess.TimeoutExpired:
        return f"Error: Timeout ({timeout}s)"

    except (FileNotFoundError, OSError) as e:
        return f"Error: {e}"

    output = (result.stdout + result.stderr).strip()
    return output[:MAX_OUTPUT] if output else "(no output)"


class ShellTool(Tool):
    name = "shell"
    description = "Run a shell command in the current workspace."

    @property
    def parameters(self) -> dict[str, Any]:
        return params({"command": prop("string")}, required=["command"])

    def run(self, params: dict[str, Any]) -> str:
        return run_shell(params["command"], SHELL_TIMEOUT)
