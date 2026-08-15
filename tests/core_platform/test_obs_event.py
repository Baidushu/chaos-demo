from __future__ import annotations

from ai_platform.observability.event import (
    AgentEvent,
    BaseEvent,
    EvaluationEvent,
    GateEvent,
    LLMEvent,
    NodeEvent,
    ToolEvent,
    WorkflowEvent,
)


def test_base_event_as_dict():
    e = BaseEvent(event_type="custom.event", trace_id="abc", payload={"x": 1})
    d = e.as_dict()
    assert d["event_type"] == "custom.event"
    assert d["trace_id"] == "abc"
    assert d["payload"]["x"] == 1


def test_agent_event_start():
    e = AgentEvent.start("tid-1", request="hello", metadata={"env": "dev"})
    assert e.event_type == "agent.run.start"
    assert e.trace_id == "tid-1"
    assert e.payload["request"] == "hello"


def test_agent_event_end():
    e = AgentEvent.end("tid-1", status="succeeded", duration_ms=100.0)
    assert e.event_type == "agent.run.end"
    assert e.payload["status"] == "succeeded"
    assert e.payload["duration_ms"] == 100.0


def test_agent_event_error():
    e = AgentEvent.error("tid-1", error_type="ValueError", message="bad input")
    assert e.event_type == "agent.error"
    assert e.payload["error_type"] == "ValueError"


def test_node_event_lifecycle():
    start = NodeEvent.start("tid-1", "span-1", node_name="planner", metadata={"mode": "rule"})
    assert start.event_type == "node.start"
    assert start.payload["node_name"] == "planner"

    end = NodeEvent.end("tid-1", "span-1", node_name="planner", duration_ms=50.0, status="ok")
    assert end.event_type == "node.end"
    assert end.payload["duration_ms"] == 50.0


def test_tool_event_call_and_result():
    call = ToolEvent.call("tid-1", "span-2", tool_name="query_order", params={"id": "A1"})
    assert call.event_type == "tool.call"
    assert call.payload["tool_name"] == "query_order"

    result = ToolEvent.result("tid-1", "span-2", tool_name="query_order", ok=True, duration_ms=30.0)
    assert result.event_type == "tool.result"
    assert result.payload["ok"] is True


def test_llm_event_response():
    resp = LLMEvent.response(
        "tid-1", "span-llm",
        provider="ollama", model="qwen2.5:7b",
        duration_ms=800.0, total_tokens=500,
    )
    assert resp.event_type == "llm.response"
    assert resp.payload["total_tokens"] == 500
    assert resp.payload["model"] == "qwen2.5:7b"


def test_llm_event_error():
    err = LLMEvent.error(
        "tid-1", "span-llm",
        provider="ollama", model="qwen",
        error_type="timeout", message="request timed out",
    )
    assert err.event_type == "llm.error"
    assert err.payload["error_type"] == "timeout"


def test_evaluation_event():
    start = EvaluationEvent.start("tid-1", evaluators=["score", "judge"])
    assert start.event_type == "evaluation.start"
    assert start.payload["evaluators"] == ["score", "judge"]

    result = EvaluationEvent.result("tid-1", score=0.85, success=True, duration_ms=200.0)
    assert result.event_type == "evaluation.result"
    assert result.payload["score"] == 0.85


def test_gate_event_pass():
    gate = GateEvent.check("tid-1", thresholds={"tool_min": 0.85})
    assert gate.event_type == "gate.check"

    passed = GateEvent.result("tid-1", passed=True, metrics={"tool_acc": 0.9})
    assert passed.event_type == "gate.pass"


def test_gate_event_fail():
    failed = GateEvent.result("tid-1", passed=False, reasons=["acc too low"])
    assert failed.event_type == "gate.fail"
    assert failed.payload["reasons"] == ["acc too low"]


def test_workflow_event():
    start = WorkflowEvent.start("tid-1", node_count=3, node_names=["planner", "tool", "judge"])
    assert start.event_type == "workflow.start"
    assert start.payload["node_count"] == 3

    end = WorkflowEvent.end("tid-1", node_count=3, duration_ms=150.0)
    assert end.event_type == "workflow.end"
    assert end.payload["node_count"] == 3
