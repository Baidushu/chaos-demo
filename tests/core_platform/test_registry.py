from __future__ import annotations

import pytest

from ai_platform.tools.base import BaseTool
from ai_platform.tools.registry import ToolRegistry


class DummyTool(BaseTool):
    name = "dummy"
    description = "dummy tool"
    schema = {}

    def execute(self, params, *, context=None):
        return {"ok": True}


def test_registry_register_get_and_list():
    registry = ToolRegistry()
    registry.register(DummyTool())

    assert registry.get("dummy") is not None
    assert registry.list_tools() == ["dummy"]


def test_registry_rejects_duplicate_names():
    registry = ToolRegistry()
    registry.register(DummyTool())
    with pytest.raises(ValueError, match="Tool already registered"):
        registry.register(DummyTool())
