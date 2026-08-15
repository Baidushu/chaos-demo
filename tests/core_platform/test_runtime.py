from __future__ import annotations

from ai_platform.agent.context import AgentContext, get_agent_context
from ai_platform.agent.runtime import AgentRuntime
from ai_platform.agent.state import AgentState


class PlannerNode:
    name = "planner"

    def run(self, state: AgentState):
        state.set_plan({"tool": "query_order", "args": {"order_id": "A1001"}})
        state.add_llm_call(
            provider="ollama_generate",
            model="qwen2.5:7b",
            prompt="plan",
            response='{"tool":"query_order"}',
            latency_ms=1.0,
        )
        return state


class ToolNode:
    name = "tool"

    def run(self, state: AgentState):
        state.add_tool_result(tool="query_order", result={"ok": True, "order_id": "A1001"})
        state.set_answer("done")
        return state


class ErrorNode:
    name = "error"

    def run(self, state: AgentState):
        raise RuntimeError("node failed")


def test_runtime_executes_workflow_and_sets_context():
    runtime = AgentRuntime(
        workflow=[PlannerNode(), ToolNode()],
        context=AgentContext(request_id="req-2", trace_id="trace-2"),
        default_metadata={"phase": "2.0"},
    )

    state = runtime.run({"input": "query"})
    assert state.status == "succeeded"
    assert state.plan == {"tool": "query_order", "args": {"order_id": "A1001"}}
    assert state.answer == "done"
    assert state.tool_result[0]["tool"] == "query_order"
    assert state.llm_call[0]["provider"] == "ollama_generate"
    assert state.metadata["phase"] == "2.0"
    assert get_agent_context() is None


def test_runtime_captures_exceptions():
    runtime = AgentRuntime(workflow=[PlannerNode(), ErrorNode(), ToolNode()])

    state = runtime.run({"input": "query"})
    assert state.status == "failed"
    assert state.error == {"type": "RuntimeError", "message": "node failed"}
    assert state.plan == {"tool": "query_order", "args": {"order_id": "A1001"}}
