import os
from typing import Any

from reagent.tools.base import MAX_OUTPUT, Tool, params, prop


def read_file(path: str, start_line: int | None = None, end_line: int | None = None) -> str:
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


class ReadFileTool(Tool):
    name = "read_file"
    description = "Read the contents of a file. Optionally specify a 1-indexed line range."

    @property
    def parameters(self) -> dict[str, Any]:
        return params(
            {
                "path": prop("string"),
                "start_line": prop("integer", "First line to read (1-indexed, inclusive)."),
                "end_line": prop("integer", "Last line to read (1-indexed, inclusive)."),
            },
            required=["path"],
        )

    def run(self, params: dict[str, Any]) -> str:
        return read_file(params["path"], params.get("start_line"), params.get("end_line"))
