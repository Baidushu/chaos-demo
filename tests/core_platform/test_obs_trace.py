from __future__ import annotations

from ai_platform.observability.trace import Span, SpanStatus, TraceContext


def test_trace_creation():
    trace = TraceContext()
    assert trace.trace_id
    assert trace.run_id
    assert trace.start_time > 0
    assert trace.span_count == 0
    assert trace.end_time is None


def test_trace_finish():
    trace = TraceContext()
    trace.finish()
    assert trace.end_time is not None
    assert trace.duration is not None
    assert trace.duration >= 0
    assert trace.duration < 5000  # shouldn't take 5 seconds


def test_trace_create_span():
    trace = TraceContext()
    span = trace.create_span("planner", attributes={"mode": "rule"})
    assert span.name == "planner"
    assert span.span_id
    assert trace.span_count == 1


def test_trace_as_dict():
    trace = TraceContext()
    span = trace.create_span("test", attributes={"key": "val"})
    span.finish(status=SpanStatus.OK)
    trace.finish()
    data = trace.as_dict()
    assert data["trace_id"] == trace.trace_id
    assert data["span_count"] == 1
    assert data["error_count"] == 0
    assert len(data["spans"]) == 1
    assert data["spans"][0]["name"] == "test"
    assert data["spans"][0]["duration_ms"] is not None


def test_trace_error_spans():
    trace = TraceContext()
    ok_span = trace.create_span("ok_node")
    ok_span.finish(status=SpanStatus.OK)
    err_span = trace.create_span("err_node")
    err_span.finish(status=SpanStatus.ERROR)
    assert trace.error_spans == [err_span]


def test_trace_with_metadata():
    trace = TraceContext(metadata={"env": "test", "user": "qa"})
    assert trace.metadata["env"] == "test"
    assert trace.metadata["user"] == "qa"
