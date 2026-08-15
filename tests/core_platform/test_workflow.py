from __future__ import annotations

from ai_platform.agent.context import AgentContext
from ai_platform.agent.runtime import AgentRuntime
from ai_platform.workflow.nodes.judge_node import JudgeNode
from ai_platform.workflow.nodes.planner_node import PlannerNode
from ai_platform.workflow.nodes.tool_node import ToolNode
from ai_platform.workflow.engine import WorkflowEngine
from ai_platform.workflow.node import BaseNode
from ai_platform.workflow.router import WorkflowRouter


class RecordNode(BaseNode):
    def __init__(self, name: str) -> None:
        self.name = name

    def execute(self, state, context):
        order = list(state.metadata.get("node_order", []))
        order.append(self.name)
        state.metadata["node_order"] = order
        return state


class BoomNode(BaseNode):
    name = "boom"

    def execute(self, state, context):
        raise RuntimeError("workflow exploded")


class FakeToolsClient:
    chaos_mode = "none"

    def query_order(self, order_id: str, retry_index: int = 0):
        return {"ok": True, "status_code": 200, "body": {"order_id": order_id}}

    def place_order(self, item_name: str, quantity: int, address: str, retry_index: int = 0):
        return {
            "ok": True,
            "status_code": 201,
            "body": {"status": "ok", "order_id": "A2001"},
            "address": address,
        }

    def cancel_order(self, order_id: str, retry_index: int = 0):
        return {"ok": True, "status_code": 200, "body": {"order_id": order_id}}


def test_workflow_engine_registers_and_orders_nodes():
    engine = WorkflowEngine(router=WorkflowRouter(node_names=["planner", "tool"]))
    engine.register(RecordNode("tool"))
    engine.register(RecordNode("planner"))
    engine.register(RecordNode("judge"))

    runtime = AgentRuntime(workflow=engine, context=AgentContext(caller="workflow-test"))
    state = runtime.run({"input": "query"})
    assert state.status == "succeeded"
    assert state.metadata["node_order"] == ["planner", "tool"]


def test_workflow_engine_propagates_to_runtime_failure():
    engine = WorkflowEngine()
    engine.register(RecordNode("planner"))
    engine.register(BoomNode())

    runtime = AgentRuntime(workflow=engine)
    state = runtime.run({"input": "query"})
    assert state.status == "failed"
    assert state.error == {"type": "RuntimeError", "message": "workflow exploded"}
    assert state.metadata["node_order"] == ["planner"]


def test_planner_tool_judge_nodes_drive_workflow():
    planner = PlannerNode(
        planner=lambda text: (
            {
                "tool": "query_order",
                "args": {"order_id": "A1001"},
                "_planner_valid": True,
            },
            {
                "llm_prompt_tokens": 10,
                "llm_completion_tokens": 8,
                "llm_total_tokens": 18,
            },
        ),
        rule_planner=lambda text: {"tool": "ask_user", "args": {"reason": "fallback"}},
        validator=lambda plan: plan,
        agent_mode="ollama",
    )
    tool = ToolNode(tools_client=FakeToolsClient(), max_retry=1)
    captured = {}

    def fake_judge(user_input: str, expected: str, actual: str) -> str:
        captured["user_input"] = user_input
        captured["expected"] = expected
        captured["actual"] = actual
        return "PASS"

    judge = JudgeNode(judge=fake_judge)
    engine = WorkflowEngine()
    engine.register(planner)
    engine.register(tool)
    engine.register(judge)

    runtime = AgentRuntime(workflow=engine, context=AgentContext(caller="phase2.1"))
    state = runtime.run(
        {
            "input": "查询订单A1001",
            "expected_tools": ["query_order"],
            "expected_args": {"order_id": "A1001"},
        },
        metadata={"phase": "2.1"},
    )

    assert state.status == "succeeded"
    assert state.plan["tool"] == "query_order"
    assert state.answer == "订单查询完成。"
    assert state.tool_result[0]["tool"] == "query_order"
    assert state.metadata["called_tools"] == ["query_order"]
    assert state.metadata["retry_count"] == 0
    assert state.metadata["judge_result"] == "PASS"
    assert state.metadata["planner_valid"] is True
    assert state.metadata["phase"] == "2.1"
    assert captured["user_input"] == "查询订单A1001"
    assert "expected_tools" in captured["expected"]
    assert captured["actual"] == "订单查询完成。"
