from __future__ import annotations

from ai_platform.agent.context import AgentContext
from ai_platform.agent.state import AgentState
from ai_platform.workflow.nodes.tool_node import ToolNode
from ai_platform.tools.base import BaseTool
from ai_platform.tools.executor import ToolExecutionResult, ToolExecutor
from ai_platform.tools.legacy_tool import build_legacy_registry
from ai_platform.tools.registry import ToolRegistry


class FakeToolsClient:
    chaos_mode = "mixed"

    def place_order(self, item_name: str, quantity: int, address: str, retry_index: int = 0):
        if retry_index == 0:
            return {"ok": False, "status_code": 503, "body": {"error": "busy"}}
        return {
            "ok": True,
            "status_code": 201,
            "body": {"status": "ok", "order_id": "A3001"},
            "address": address,
        }

    def query_order(self, order_id: str, retry_index: int = 0):
        return {"ok": True, "status_code": 200, "body": {"order_id": order_id}}

    def cancel_order(self, order_id: str, retry_index: int = 0):
        return {"ok": True, "status_code": 200, "body": {"order_id": order_id}}


class AskTool(BaseTool):
    name = "ask_user"
    description = "ask for more info"
    schema = {"reason": {"type": str, "required": False}}

    def execute(self, params, *, context=None):
        return ToolExecutionResult(
            tool=self.name,
            ok=True,
            result={"ok": True},
            attempts=[{"tool": self.name, "result": {"ok": True}}],
            metadata={"response_text": "参数不足或请求不合理，请补充信息。", "retry_count": 0},
        )


def test_tool_node_uses_executor_abstraction():
    registry = ToolRegistry()
    registry.register(AskTool())
    executor = ToolExecutor(registry=registry)
    node = ToolNode(executor=executor)

    state = AgentState(
        request={"input": "x"},
        plan={"tool": "ask_user", "args": {"reason": "missing"}},
    )
    out = node.execute(state, AgentContext())

    assert out.answer == "参数不足或请求不合理，请补充信息。"
    assert out.tool_result[0]["tool"] == "ask_user"
    assert out.metadata["called_tools"] == ["ask_user"]


def test_tool_node_keeps_legacy_tools_client_compatibility():
    registry = build_legacy_registry(tools_client=FakeToolsClient(), max_retry=1)
    executor = ToolExecutor(registry=registry, metadata={"chaos_mode": "mixed"})
    node = ToolNode(executor=executor)
    state = AgentState(
        request={"input": "下单"},
        plan={
            "tool": "place_order",
            "args": {"item_name": "可乐", "quantity": 1, "address": "学院路1号"},
        },
        metadata={"llm_meta": {"llm_total_tokens": 18}},
    )

    out = node.execute(state, AgentContext())
    assert out.answer == "已下单，订单号 A3001"
    assert out.metadata["retry_count"] == 1
    assert out.metadata["called_tools"] == ["place_order"]
    assert out.metadata["chaos_mode"] == "mixed"
    assert out.tool_result[0]["tool"] == "place_order"
    assert out.tool_result[1]["tool"] == "place_order_retry_1"
