from __future__ import annotations

from ai_platform.agent.context import AgentContext, clear_agent_context, get_agent_context, set_agent_context
from ai_platform.agent.state import AgentState


def test_agent_state_records_core_fields():
    state = AgentState(request={"input": "hello"})
    state.set_plan({"tool": "query_order"})
    state.add_llm_call(
        provider="ollama_generate",
        model="qwen2.5:7b",
        prompt="plan",
        response='{"tool":"query_order"}',
        latency_ms=12.5,
        metadata={"caller": "planner"},
    )
    state.add_tool_result(tool="query_order", result={"ok": True})
    state.set_answer({"status": "ok"})

    data = state.as_dict()
    assert data["request"] == {"input": "hello"}
    assert data["plan"] == {"tool": "query_order"}
    assert data["tool_result"][0]["tool"] == "query_order"
    assert data["llm_call"][0]["provider"] == "ollama_generate"
    assert data["answer"] == {"status": "ok"}
    assert data["status"] == "new"
    assert data["metadata"]["has_plan"] is True
    assert data["metadata"]["has_answer"] is True


def test_agent_state_error_serialization():
    state = AgentState()
    state.set_error(RuntimeError("boom"))

    data = state.as_dict()
    assert data["error"] == {"type": "RuntimeError", "message": "boom"}


def test_agent_context_round_trip():
    clear_agent_context()
    ctx = AgentContext(request_id="req-1", trace_id="trace-1", caller="test")
    set_agent_context(ctx)
    try:
        current = get_agent_context()
        assert current is not None
        assert current.request_id == "req-1"
        assert current.trace_id == "trace-1"
        assert current.caller == "test"
    finally:
        clear_agent_context()

    assert get_agent_context() is None
