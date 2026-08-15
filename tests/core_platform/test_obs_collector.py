from __future__ import annotations

from ai_platform.observability.collector import Collector, get_collector, reset_collector
from ai_platform.observability.event import AgentEvent, NodeEvent, ToolEvent
from ai_platform.observability.trace import SpanStatus


def test_collector_start_and_finish_trace():
    reset_collector()
    c = Collector()
    trace = c.start_trace(metadata={"env": "test"})
    assert trace.trace_id
    assert c.active_trace is trace

    span = c.create_span("planner")
    span.finish(status=SpanStatus.OK)

    finished = c.finish_trace(trace)
    assert finished.end_time is not None
    assert finished.duration is not None


def test_collector_record_event():
    reset_collector()
    c = Collector()
    trace = c.start_trace()
    c.record(AgentEvent.start(trace.trace_id, request="test"))
    c.record(AgentEvent.end(trace.trace_id, status="succeeded"))

    assert len(c.events) == 2
    agent_events = c.events_by_type("agent.run.start")
    assert len(agent_events) == 1


def test_collector_auto_trace_id():
    reset_collector()
    c = Collector()
    trace = c.start_trace()
    # event without explicit trace_id uses active trace
    e = AgentEvent.start("", request="auto")
    c.record(e)
    assert e.trace_id == trace.trace_id


def test_collector_metrics_helpers():
    reset_collector()
    c = Collector()
    c.counter("tool.calls").inc(3)
    c.gauge("active").set(2)
    c.histogram("latency").record(100)

    snap = c.snapshot()
    assert snap["metrics"]["counters"]["tool.calls"]["value"] == 3
    assert snap["metrics"]["gauges"]["active"]["value"] == 2
    assert snap["metrics"]["histograms"]["latency"]["count"] == 1


def test_collector_snapshot():
    reset_collector()
    c = Collector()
    c.start_trace(metadata={"kind": "test"})
    c.record(AgentEvent.start("tid", request="snapshot test"))
    c.record(NodeEvent.start("tid", "sp1", node_name="planner"))
    c.finish_trace()

    snap = c.snapshot()
    assert snap["total_traces"] == 1
    assert snap["total_events"] == 2
    assert snap["active_trace_id"] is not None


def test_collector_reset():
    reset_collector()
    c = Collector()
    c.start_trace()
    c.record(AgentEvent.start("tid", request="pre-reset"))
    c.reset()
    assert len(c.events) == 0
    assert len(c.traces) == 0
    assert c.active_trace is None


def test_collector_node_and_tool_events():
    reset_collector()
    c = Collector()
    trace = c.start_trace()

    planner_span = c.create_span("node.planner")
    c.record(NodeEvent.start(trace.trace_id, planner_span.span_id, node_name="planner"))
    planner_span.finish(status=SpanStatus.OK)
    c.record(NodeEvent.end(trace.trace_id, planner_span.span_id, node_name="planner", duration_ms=50.0))

    tool_span = c.create_span("tool.query_order")
    c.record(ToolEvent.call(trace.trace_id, tool_span.span_id, tool_name="query_order"))
    tool_span.finish(status=SpanStatus.OK)
    c.record(ToolEvent.result(trace.trace_id, tool_span.span_id, tool_name="query_order", ok=True, duration_ms=200.0))

    c.finish_trace()
    assert len(c.events) == 4
    assert len(c.traces[0].spans) == 2


def test_get_collector_singleton():
    reset_collector()
    c1 = get_collector()
    c2 = get_collector()
    assert c1 is c2
    c1.counter("x").inc()
    assert c2.counter("x").value == 1
