"""Lightweight in-memory metrics for AI Agent Observability.

No external dependencies (no Prometheus). Provides:
- SimpleCounter: cumulative count (tool_call_count, llm_call_count, error_count)
- SimpleGauge: point-in-time value (current_running_agent)
- Histogram: bucketed distribution (latency, token_usage)
- MetricsRegistry: central registry to collect all metrics
"""

from __future__ import annotations

import threading
from dataclasses import dataclass, field
from typing import Any


@dataclass(slots=True)
class SimpleCounter:
    name: str
    description: str = ""
    _value: int = 0
    _lock: threading.Lock = field(default_factory=threading.Lock)
    _labels: dict[str, str] = field(default_factory=dict)

    def inc(self, delta: int = 1) -> None:
        with self._lock:
            self._value += delta

    @property
    def value(self) -> int:
        with self._lock:
            return self._value

    def as_dict(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "type": "counter",
            "value": self.value,
            "labels": dict(self._labels),
        }


@dataclass(slots=True)
class SimpleGauge:
    name: str
    description: str = ""
    _value: float = 0.0
    _lock: threading.Lock = field(default_factory=threading.Lock)
    _labels: dict[str, str] = field(default_factory=dict)

    def set(self, value: float) -> None:
        with self._lock:
            self._value = value

    def inc(self, delta: float = 1.0) -> None:
        with self._lock:
            self._value += delta

    def dec(self, delta: float = 1.0) -> None:
        with self._lock:
            self._value -= delta

    @property
    def value(self) -> float:
        with self._lock:
            return self._value

    def as_dict(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "type": "gauge",
            "value": self.value,
            "labels": dict(self._labels),
        }


@dataclass(slots=True)
class Histogram:
    name: str
    description: str = ""
    buckets: list[float] = field(default_factory=lambda: [1, 5, 10, 25, 50, 100, 250, 500, 1000, 2500, 5000, 10000])
    _values: list[float] = field(default_factory=list)
    _lock: threading.Lock = field(default_factory=threading.Lock)

    def record(self, value: float) -> None:
        with self._lock:
            self._values.append(value)

    def _compute_buckets(self) -> dict[str, int]:
        counts: dict[str, int] = {}
        sorted_buckets = sorted(self.buckets)
        for v in self._values:
            placed = False
            for b in sorted_buckets:
                if v <= b:
                    label = f"le_{b}"
                    counts[label] = counts.get(label, 0) + 1
                    placed = True
                    break
            if not placed:
                counts["le_inf"] = counts.get("le_inf", 0) + 1
        for b in sorted_buckets:
            label = f"le_{b}"
            if label not in counts:
                counts[label] = 0
        if "le_inf" not in counts:
            counts["le_inf"] = 0
        return counts

    @property
    def count(self) -> int:
        with self._lock:
            return len(self._values)

    @property
    def sum(self) -> float:
        with self._lock:
            return sum(self._values) if self._values else 0.0

    @property
    def avg(self) -> float | None:
        with self._lock:
            return sum(self._values) / len(self._values) if self._values else None

    @property
    def p50(self) -> float | None:
        return self._percentile(50)

    @property
    def p99(self) -> float | None:
        return self._percentile(99)

    def _percentile(self, p: float) -> float | None:
        with self._lock:
            if not self._values:
                return None
            arr = sorted(self._values)
            n = len(arr)
            rank = int(round((p / 100.0) * (n - 1)))
            rank = max(0, min(rank, n - 1))
            return arr[rank]

    def as_dict(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "type": "histogram",
            "count": self.count,
            "sum": round(self.sum, 3),
            "avg": round(self.avg, 3) if self.avg is not None else None,
            "p50": round(self.p50, 3) if self.p50 is not None else None,
            "p99": round(self.p99, 3) if self.p99 is not None else None,
            "buckets": self._compute_buckets(),
        }


@dataclass(slots=True)
class MetricsRegistry:
    _counters: dict[str, SimpleCounter] = field(default_factory=dict)
    _gauges: dict[str, SimpleGauge] = field(default_factory=dict)
    _histograms: dict[str, Histogram] = field(default_factory=dict)

    def counter(self, name: str, description: str = "") -> SimpleCounter:
        if name not in self._counters:
            self._counters[name] = SimpleCounter(name=name, description=description)
        return self._counters[name]

    def gauge(self, name: str, description: str = "") -> SimpleGauge:
        if name not in self._gauges:
            self._gauges[name] = SimpleGauge(name=name, description=description)
        return self._gauges[name]

    def histogram(self, name: str, description: str = "", buckets: list[float] | None = None) -> Histogram:
        if name not in self._histograms:
            self._histograms[name] = Histogram(
                name=name,
                description=description,
                buckets=buckets or [1, 5, 10, 25, 50, 100, 250, 500, 1000, 2500, 5000, 10000],
            )
        return self._histograms[name]

    def snapshot(self) -> dict[str, Any]:
        return {
            "counters": {n: c.as_dict() for n, c in self._counters.items()},
            "gauges": {n: g.as_dict() for n, g in self._gauges.items()},
            "histograms": {n: h.as_dict() for n, h in self._histograms.items()},
        }

    def reset(self) -> None:
        self._counters.clear()
        self._gauges.clear()
        self._histograms.clear()
