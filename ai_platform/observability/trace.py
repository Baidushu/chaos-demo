"""Span and TraceContext — AI Agent trace primitives.

TraceContext records a complete agent run.
Span records a single operation within a trace (Node, Tool, LLM call).
"""

from __future__ import annotations

import time
import uuid
from dataclasses import dataclass, field
from enum import Enum
from typing import Any


class SpanStatus(str, Enum):
    OK = "ok"
    ERROR = "error"


@dataclass(slots=True)
class Span:
    span_id: str = field(default_factory=lambda: uuid.uuid4().hex[:12])
    name: str = ""
    start_time: float = field(default_factory=time.perf_counter)
    end_time: float | None = None
    duration: float | None = None
    status: SpanStatus = SpanStatus.OK
    attributes: dict[str, Any] = field(default_factory=dict)
    events: list[dict[str, Any]] = field(default_factory=list)

    def finish(self, *, status: SpanStatus | None = None, attributes: dict[str, Any] | None = None) -> "Span":
        self.end_time = time.perf_counter()
        self.duration = (self.end_time - self.start_time) * 1000  # ms
        if status is not None:
            self.status = status
        if attributes is not None:
            self.attributes.update(attributes)
        return self

    def add_event(self, name: str, attributes: dict[str, Any] | None = None) -> None:
        self.events.append(
            {
                "name": name,
                "timestamp": time.time(),
                "attributes": attributes or {},
            }
        )

    def as_dict(self) -> dict[str, Any]:
        return {
            "span_id": self.span_id,
            "name": self.name,
            "start_time": self.start_time,
            "end_time": self.end_time,
            "duration_ms": round(self.duration, 3) if self.duration is not None else None,
            "status": self.status.value,
            "attributes": dict(self.attributes),
            "events": list(self.events),
        }


@dataclass(slots=True)
class TraceContext:
    trace_id: str = field(default_factory=lambda: uuid.uuid4().hex[:16])
    run_id: str = field(default_factory=lambda: uuid.uuid4().hex[:16])
    start_time: float = field(default_factory=time.perf_counter)
    end_time: float | None = None
    duration: float | None = None
    spans: list[Span] = field(default_factory=list)
    metadata: dict[str, Any] = field(default_factory=dict)

    def create_span(self, name: str, *, attributes: dict[str, Any] | None = None) -> Span:
        span = Span(name=name, attributes=attributes or {})
        self.spans.append(span)
        return span

    def finish(self) -> "TraceContext":
        self.end_time = time.perf_counter()
        self.duration = (self.end_time - self.start_time) * 1000  # ms
        return self

    @property
    def span_count(self) -> int:
        return len(self.spans)

    @property
    def error_spans(self) -> list[Span]:
        return [s for s in self.spans if s.status == SpanStatus.ERROR]

    def as_dict(self) -> dict[str, Any]:
        return {
            "trace_id": self.trace_id,
            "run_id": self.run_id,
            "start_time": self.start_time,
            "end_time": self.end_time,
            "duration_ms": round(self.duration, 3) if self.duration is not None else None,
            "span_count": len(self.spans),
            "error_count": len(self.error_spans),
            "spans": [s.as_dict() for s in self.spans],
            "metadata": dict(self.metadata),
        }
