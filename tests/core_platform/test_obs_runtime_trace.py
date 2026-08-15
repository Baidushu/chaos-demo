from __future__ import annotations

from ai_platform.agent.context import AgentContext
from ai_platform.agent.state import AgentState
from ai_platform.observability.collector import Collector, get_collector, reset_collector
from ai_platform.observability.event import AgentEvent, NodeEvent, ToolEvent
from ai_platform.observability.trace import SpanStatus
from ai_platform.workflow.engine import WorkflowEngine
from ai_platform.workflow.node import BaseNode


class _EchoNode(BaseNode):
    name = "echo"

    def execute(self, state: AgentState, context: AgentContext) -> AgentState:
        state.set_answer(f"echo: {state.request}")
        return state


class _FailingNode(BaseNode):
    name = "failer"

    def execute(self, state: AgentState, context: AgentContext) -> AgentState:
        raise RuntimeError("deliberate failure")


def test_runtime_creates_trace():
    reset_collector()
    collector = get_collector()
    assert collector.active_trace is None

    from ai_platform.agent.runtime import AgentRuntime
    node = _EchoNode()
    engine = WorkflowEngine()
    engine.register(node)
    runtime = AgentRuntime(workflow=engine)

    state = runtime.run("hello world")

    assert state.status == "succeeded"
    assert state.answer == "echo: hello world"
    # Check trace was created and finished
    traces = collector.traces
    assert len(traces) >= 1
    trace = traces[-1]
    assert trace.trace_id
    assert trace.end_time is not None
    assert trace.span_count >= 1


def test_runtime_trace_on_error():
    reset_collector()
    collector = get_collector()

    from ai_platform.agent.runtime import AgentRuntime
    node = _FailingNode()
    engine = WorkflowEngine()
    engine.register(node)
    runtime = AgentRuntime(workflow=engine)

    state = runtime.run("will fail")
    assert state.status == "failed"
    assert len(collector.traces) >= 1
    trace = collector.traces[-1]
    assert trace.end_time is not None


def test_runtime_emits_events():
    reset_collector()
    collector = get_collector()

    from ai_platform.agent.runtime import AgentRuntime
    node = _EchoNode()
    engine = WorkflowEngine()
    engine.register(node)
    runtime = AgentRuntime(workflow=engine)

    runtime.run("event test")

    # Should have agent start + node start + node end + agent end events
    start_events = collector.events_by_type("agent.run.start")
    end_events = collector.events_by_type("agent.run.end")
    assert len(start_events) >= 1
    assert len(end_events) >= 1


def test_runtime_metrics_collected():
    reset_collector()
    collector = get_collector()

    from ai_platform.agent.runtime import AgentRuntime
    node = _EchoNode()
    engine = WorkflowEngine()
    engine.register(node)
    runtime = AgentRuntime(workflow=engine)

    runtime.run("metrics test")

    snap = collector.snapshot()
    assert snap["total_traces"] >= 1
    # trace.count counter should be recorded
    assert snap["metrics"]["counters"]["trace.count"]["value"] >= 1


def test_runtime_observability_disabled():
    reset_collector()
    collector = get_collector()

    from ai_platform.agent.runtime import AgentRuntime
    node = _EchoNode()
    engine = WorkflowEngine()
    engine.register(node)
    runtime = AgentRuntime(workflow=engine, observability_enabled=False)

    runtime.run("no trace")
    # No trace should be created (empty collector)
    assert len(collector.traces) == 0
    assert collector.active_trace is None
