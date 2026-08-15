"""Prometheus metrics adapter for the circuit breaker."""

from __future__ import annotations

import time

from .state import CircuitState


class CircuitBreakerMetrics:
    def __init__(self, ctx) -> None:
        self._ctx = ctx

    def record_request(self, resource: str, state: CircuitState) -> None:
        counter = getattr(self._ctx, "CIRCUIT_BREAKER_REQUESTS_TOTAL", None)
        if counter is not None:
            counter.labels(resource=resource, state=state.value).inc()
        self.set_state(resource, state)

    def record_failure(self, resource: str, state: CircuitState) -> None:
        counter = getattr(self._ctx, "CIRCUIT_BREAKER_FAILURES_TOTAL", None)
        if counter is not None:
            counter.labels(resource=resource, state=state.value).inc()

    def record_state_change(self, resource: str, state: CircuitState) -> None:
        counter = getattr(self._ctx, "CIRCUIT_BREAKER_STATE_CHANGE_TOTAL", None)
        if counter is not None:
            counter.labels(resource=resource, state=state.value).inc()

    def record_open(self, resource: str) -> None:
        counter = getattr(self._ctx, "CIRCUIT_BREAKER_OPEN_TOTAL", None)
        if counter is not None:
            counter.labels(resource=resource, state=CircuitState.OPEN.value).inc()

    def record_fallback(self, resource: str, state: CircuitState) -> None:
        counter = getattr(self._ctx, "CIRCUIT_BREAKER_FALLBACK_TOTAL", None)
        if counter is not None:
            counter.labels(resource=resource, state=state.value).inc()

    def record_timeout(self, resource: str) -> None:
        counter = getattr(self._ctx, "CIRCUIT_BREAKER_TIMEOUT_TOTAL", None)
        if counter is not None:
            counter.labels(resource=resource).inc()

    def record_rejected(self, resource: str, state: CircuitState) -> None:
        counter = getattr(self._ctx, "CIRCUIT_BREAKER_REJECTED_TOTAL", None)
        if counter is not None:
            counter.labels(resource=resource, state=state.value).inc()

    def set_state(self, resource: str, state: CircuitState) -> None:
        gauge = getattr(self._ctx, "CIRCUIT_BREAKER_STATE", None)
        if gauge is not None:
            gauge.labels(resource=resource).set(self._state_value(state))

    def record_recovery(self, resource: str, open_until: float, timeout_seconds: int) -> None:
        if open_until <= 0:
            return
        recovery_seconds = max(time.time() - (open_until - float(timeout_seconds)), 0.0)
        histogram = getattr(self._ctx, "CIRCUIT_BREAKER_RECOVERY_SECONDS", None)
        if histogram is not None:
            histogram.labels(resource=resource).observe(recovery_seconds)

    @staticmethod
    def _state_value(state: CircuitState) -> int:
        if state is CircuitState.CLOSED:
            return 0
        if state is CircuitState.OPEN:
            return 1
        return 2
