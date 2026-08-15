from __future__ import annotations

from ai_platform.tools.base import BaseTool


class DummyTool(BaseTool):
    name = "dummy"
    description = "dummy tool"
    schema = {"value": {"type": int, "required": True}}

    def execute(self, params, *, context=None):
        return {"ok": True, "value": params["value"]}


def test_base_tool_contract():
    tool = DummyTool()
    assert tool.name == "dummy"
    assert tool.description == "dummy tool"
    assert tool.schema["value"]["required"] is True
    assert tool.execute({"value": 3}) == {"ok": True, "value": 3}
