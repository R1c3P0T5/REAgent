from abc import ABC, abstractmethod
from typing import Any, Literal


MAX_OUTPUT = 50_000

PropType = Literal["string", "integer", "number", "boolean", "array", "object", "null"]


def prop(type: PropType, description: str = "") -> dict[str, Any]:
    return {"type": type, "description": description} if description else {"type": type}


def params(properties: dict[str, Any], required: list[str]) -> dict[str, Any]:
    return {"type": "object", "properties": properties, "required": required}


class Tool(ABC):
    name: str
    description: str

    @property
    @abstractmethod
    def parameters(self) -> dict[str, Any]: ...

    @abstractmethod
    def run(self, params: dict[str, Any]) -> str: ...

    def to_schema(self) -> dict[str, Any]:
        return {
            "type": "function",
            "function": {
                "name": self.name,
                "description": self.description,
                "parameters": self.parameters,
            },
        }
