from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any


class BaseTool(ABC):
    name: str
    description: str
    schema: dict[str, dict[str, Any]]

    @abstractmethod
    def execute(self, params: dict[str, Any], *, context: Any | None = None) -> Any:
        raise NotImplementedError
