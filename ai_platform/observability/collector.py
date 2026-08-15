"""Collector — central observability coordination point.

Collects TraceContext, Events, and Metrics during agent execution.
Provides a single entry point for recording all observability signals.
"""

from __future__ import annotations

import threading
from dataclasses import dataclass, field
from typing import Any

from ai_platform.observability.event import BaseEvent
from ai_platform.observability.metrics import Histogram, MetricsRegistry, SimpleCounter, SimpleGauge
from ai_platform.observability.trace import Span, SpanStatus, TraceContext


@dataclass(slots=True)
class Collector:
    metrics: MetricsRegistry = field(default_factory=MetricsRegistry)
    _events: list[BaseEvent] = field(default_factory=list)
    _traces: list[TraceContext] = field(default_factory=list)
    _lock: threading.Lock = field(default_factory=threading.Lock)
    _active_trace: TraceContext | None = None

    # ---- Trace ----

    def start_trace(self, *, metadata: dict[str, Any] | None = None) -> TraceContext:
        with self._lock:
            trace = TraceContext(metadata=metadata or {})
            self._traces.append(trace)
            self._active_trace = trace
        return trace

    def create_span(self, name: str, *, attributes: dict[str, Any] | None = None) -> Span:
        with self._lock:
            if self._active_trace is None:
                self._active_trace = TraceContext()
                self._traces.append(self._active_trace)
            return self._active_trace.create_span(name, attributes=attributes)

    def finish_trace(self, trace: TraceContext | None = None) -> TraceContext:
        t = trace or self._active_trace
        if t is not None:
            if t.end_time is None:
                t.finish()
            self._record_trace_metrics(t)
        return t if t is not None else TraceContext()

    @property
    def active_trace(self) -> TraceContext | None:
        return self._active_trace

    @property
    def traces(self) -> list[TraceContext]:
        with self._lock:
            return list(self._traces)

    # ---- Events ----

    def record(self, event: BaseEvent) -> None:
        with self._lock:
            if self._active_trace is not None and not event.trace_id:
                event.trace_id = self._active_trace.trace_id
            self._events.append(event)

    @property
    def events(self) -> list[BaseEvent]:
        with self._lock:
            return list(self._events)

    def events_by_type(self, event_type: str) -> list[BaseEvent]:
        with self._lock:
            return [e for e in self._events if e.event_type == event_type]

    # ---- Metrics helpers ----

    def counter(self, name: str, description: str = "") -> SimpleCounter:
        return self.metrics.counter(name, description)

    def gauge(self, name: str, description: str = "") -> SimpleGauge:
        return self.metrics.gauge(name, description)

    def histogram(self, name: str, description: str = "", buckets: list[float] | None = None) -> Histogram:
        return self.metrics.histogram(name, description, buckets)

    # ---- Snapshot ----

    def snapshot(self) -> dict[str, Any]:
        with self._lock:
            return {
                "active_trace_id": self._active_trace.trace_id if self._active_trace else None,
                "total_traces": len(self._traces),
                "total_events": len(self._events),
                "traces": [t.as_dict() for t in self._traces],
                "events": [e.as_dict() for e in self._events[-200:]],  # last 200 events
                "metrics": self.metrics.snapshot(),
            }

    def reset(self) -> None:
        with self._lock:
            self._events.clear()
            self._traces.clear()
            self._active_trace = None
            self.metrics.reset()

    # ---- Internal ----

    def _record_trace_metrics(self, trace: TraceContext) -> None:
        self.counter("trace.count").inc()
        self.histogram("trace.duration_ms").record(trace.duration or 0)
        self.histogram("trace.span_count").record(trace.span_count)
        for span in trace.spans:
            if span.duration is not None:
                self.histogram(f"span.{span.name}.duration_ms").record(span.duration)
            if span.status == SpanStatus.ERROR:
                self.counter(f"span.{span.name}.error_count").inc()


# Global singleton instance
_collector_instance: Collector | None = None
_collector_lock = threading.Lock()


def get_collector() -> Collector:
    global _collector_instance
    if _collector_instance is None:
        with _collector_lock:
            if _collector_instance is None:
                _collector_instance = Collector()
    return _collector_instance


def reset_collector() -> None:
    global _collector_instance
    with _collector_lock:
        if _collector_instance is not None:
            _collector_instance.reset()
        _collector_instance = None
