import os
from typing import Any

from reagent.tools.base import Tool, params, prop


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


class EditFileTool(Tool):
    name = "edit_file"
    description = "Replace a range of lines in an existing file. Use read_file first to get line numbers."

    @property
    def parameters(self) -> dict[str, Any]:
        return params(
            {
                "path": prop("string"),
                "start_line": prop("integer", "First line to replace (1-indexed, inclusive)."),
                "end_line": prop("integer", "Last line to replace (1-indexed, inclusive). Defaults to start_line."),
                "content": prop("string"),
            },
            required=["path", "start_line", "content"],
        )

    def run(self, params: dict[str, Any]) -> str:
        return edit_file(params["path"], params["start_line"], params.get("end_line"), params["content"])
