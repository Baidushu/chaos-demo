from __future__ import annotations

import time

from ai_platform.observability.trace import Span, SpanStatus


def test_span_creation():
    s = Span(name="llm_call")
    assert s.name == "llm_call"
    assert s.span_id
    assert s.start_time > 0
    assert s.end_time is None
    assert s.duration is None
    assert s.status == SpanStatus.OK


def test_span_finish():
    s = Span(name="node_exec")
    s.finish(status=SpanStatus.OK, attributes={"latency": 120})
    assert s.end_time is not None
    assert s.duration is not None
    assert s.attributes["latency"] == 120


def test_span_add_event():
    s = Span(name="tool")
    s.add_event("retry", attributes={"attempt": 1})
    assert len(s.events) == 1
    assert s.events[0]["name"] == "retry"
    assert s.events[0]["attributes"]["attempt"] == 1


def test_span_as_dict():
    s = Span(name="judge", attributes={"model": "qwen"})
    s.add_event("llm_call", attributes={"tokens": 500})
    s.finish(status=SpanStatus.OK)
    d = s.as_dict()
    assert d["name"] == "judge"
    assert d["status"] == "ok"
    assert d["duration_ms"] is not None
    assert d["attributes"]["model"] == "qwen"
    assert len(d["events"]) == 1


def test_span_finish_error():
    s = Span(name="failing_node")
    start = time.perf_counter()
    s.finish(status=SpanStatus.ERROR, attributes={"reason": "timeout"})
    assert s.duration is not None
    assert s.duration >= 0
    assert s.duration < 5000
    assert s.attributes["reason"] == "timeout"
