from __future__ import annotations

from ai_platform.tools.base import BaseTool
from ai_platform.tools.executor import ToolExecutionResult, ToolExecutor
from ai_platform.tools.registry import ToolRegistry


class EchoTool(BaseTool):
    name = "echo"
    description = "echo tool"
    schema = {"message": {"type": str, "required": True}}

    def execute(self, params, *, context=None):
        return ToolExecutionResult(
            tool=self.name,
            ok=True,
            result={"ok": True, "message": params["message"]},
            attempts=[{"tool": self.name, "result": {"ok": True, "message": params["message"]}}],
        )


class FailingTool(BaseTool):
    name = "fail"
    description = "fail tool"
    schema = {}

    def execute(self, params, *, context=None):
        raise RuntimeError("boom")


def test_executor_executes_registered_tool():
    registry = ToolRegistry()
    registry.register(EchoTool())
    executor = ToolExecutor(registry=registry)

    result = executor.execute("echo", {"message": "hello"})
    assert result.ok is True
    assert result.result == {"ok": True, "message": "hello"}
    assert result.attempts[0]["tool"] == "echo"


def test_executor_validates_params():
    registry = ToolRegistry()
    registry.register(EchoTool())
    executor = ToolExecutor(registry=registry)

    result = executor.execute("echo", {"message": 1})
    assert result.ok is False
    assert "expected str" in str(result.error)


def test_executor_captures_unexpected_exception():
    registry = ToolRegistry()
    registry.register(FailingTool())
    executor = ToolExecutor(registry=registry)

    result = executor.execute("fail", {})
    assert result.ok is False
    assert result.error == "boom"
