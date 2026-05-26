import os
from typing import Any

from reagent.tools.base import Tool, params, prop


def write_file(path: str, content: str) -> str:
    path = os.path.abspath(path)
    try:
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, "w") as f:
            f.write(content)

        return f"Written {len(content)} bytes to {path}"

    except (PermissionError, OSError) as e:
        return f"Error: {e}"


class WriteFileTool(Tool):
    name = "write_file"
    description = "Create or overwrite a file with the given content."

    @property
    def parameters(self) -> dict[str, Any]:
        return params(
            {"path": prop("string"), "content": prop("string")},
            required=["path", "content"],
        )

    def run(self, params: dict[str, Any]) -> str:
        return write_file(params["path"], params["content"])
