from collections.abc import Callable
import os
import re
import subprocess
from typing import Any


SHELL_TIMEOUT = 30
MAX_OUTPUT = 50_000

TOOLS = [
    {
        "type": "function",
        "function": {
            "name": "shell",
            "description": "Run a shell command in the current workspace.",
            "parameters": {
                "type": "object",
                "properties": {"command": {"type": "string"}},
                "required": ["command"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "read_file",
            "description": "Read the contents of a file. Optionally specify a 1-indexed line range.",
            "parameters": {
                "type": "object",
                "properties": {
                    "path": {"type": "string"},
                    "start_line": {
                        "type": "integer",
                        "description": "First line to read (1-indexed, inclusive).",
                    },
                    "end_line": {
                        "type": "integer",
                        "description": "Last line to read (1-indexed, inclusive).",
                    },
                },
                "required": ["path"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "write_file",
            "description": "Create or overwrite a file with the given content.",
            "parameters": {
                "type": "object",
                "properties": {
                    "path": {"type": "string"},
                    "content": {"type": "string"},
                },
                "required": ["path", "content"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "edit_file",
            "description": "Replace a range of lines in an existing file. Use read_file first to get line numbers.",
            "parameters": {
                "type": "object",
                "properties": {
                    "path": {"type": "string"},
                    "start_line": {
                        "type": "integer",
                        "description": "First line to replace (1-indexed, inclusive).",
                    },
                    "end_line": {
                        "type": "integer",
                        "description": "Last line to replace (1-indexed, inclusive). Defaults to start_line.",
                    },
                    "content": {"type": "string"},
                },
                "required": ["path", "start_line", "content"],
            },
        },
    },
]


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


def read_file(
    path: str, start_line: int | None = None, end_line: int | None = None
) -> str:
    path = os.path.abspath(path)
    try:
        with open(path) as f:
            lines = f.readlines()

    except (FileNotFoundError, PermissionError, OSError) as e:
        return f"Error: {e}"

    total = len(lines)
    s = (start_line or 1) - 1
    end = end_line or total
    chunk = lines[s:end]

    numbered = "".join(f"{s + i + 1}: {line}" for i, line in enumerate(chunk))

    if not numbered:
        return "(empty file)"

    if len(numbered) > MAX_OUTPUT:
        numbered = numbered[:MAX_OUTPUT]
        last_newline = numbered.rfind("\n")
        if last_newline != -1:
            numbered = numbered[: last_newline + 1]

        next_line = s + numbered.count("\n") + 1
        numbered += f"(truncated, use start_line={next_line} to continue, file has {total} lines total)\n"

    return numbered


def write_file(path: str, content: str) -> str:
    path = os.path.abspath(path)
    try:
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, "w") as f:
            f.write(content)

        return f"Written {len(content)} bytes to {path}"

    except (PermissionError, OSError) as e:
        return f"Error: {e}"


def edit_file(path: str, start_line: int, end_line: int | None, content: str) -> str:
    path = os.path.abspath(path)
    try:
        with open(path) as f:
            lines = f.readlines()

        s = start_line - 1
        e = end_line if end_line is not None else start_line

        new_content = content if content.endswith("\n") else content + "\n"
        lines[s:e] = [new_content]

        final = "".join(lines)
        with open(path, "w") as f:
            f.write(final)

        return f"Replaced lines {start_line}-{e} in {path}"

    except (FileNotFoundError, PermissionError, OSError) as e:
        return f"Error: {e}"


TOOL_HANDLERS: dict[str, Callable[[dict[str, Any]], str]] = {
    "shell": lambda param: run_shell(param["command"], timeout=SHELL_TIMEOUT),
    "read_file": lambda param: read_file(
        param["path"], param.get("start_line"), param.get("end_line")
    ),
    "write_file": lambda param: write_file(param["path"], param["content"]),
    "edit_file": lambda param: edit_file(
        param["path"], param["start_line"], param.get("end_line"), param["content"]
    ),
}
