"""Circuit breaker orchestration."""

from __future__ import annotations

import logging

from app.infrastructure.logging import log_event

from .fallback import DefaultCircuitOpenFallback, FallbackHandler
from .metrics import CircuitBreakerMetrics
from .rule import CircuitBreakerRule, build_default_rule
from .state import CircuitState
from .storage import (
    CircuitBreakerStorage,
    CircuitRecordResult,
    CircuitWindowSnapshot,
    RedisCircuitBreakerStorage,
)


class CircuitBreaker:
    def __init__(
        self,
        rule: CircuitBreakerRule,
        storage: CircuitBreakerStorage,
        metrics: CircuitBreakerMetrics,
        fallback_handler: FallbackHandler | None = None,
        ctx=None,
    ) -> None:
        self._rule = rule
        self._storage = storage
        self._metrics = metrics
        self._fallback_handler = fallback_handler or DefaultCircuitOpenFallback()
        self._ctx = ctx
        self._last_state = CircuitState.CLOSED
        self._probe_acquired = False

    def allow_request(self) -> bool:
        current_state = self.state()
        self._last_state = current_state
        self._metrics.record_request(self._rule.resource, current_state)

        if current_state is CircuitState.CLOSED:
            return True
        if current_state is CircuitState.OPEN:
            self._metrics.record_rejected(self._rule.resource, current_state)
            return False

        acquired = self._storage.try_acquire_probe(self._rule)
        self._probe_acquired = acquired
        if acquired:
            self._emit_state_change(CircuitState.OPEN, CircuitState.HALF_OPEN)
            self._last_state = CircuitState.HALF_OPEN
            self._metrics.set_state(self._rule.resource, CircuitState.HALF_OPEN)
            return True
        self._metrics.record_rejected(self._rule.resource, CircuitState.HALF_OPEN)
        return False

    def record_success(self) -> CircuitRecordResult | None:
        if self._probe_acquired:
            open_until = self._storage.get_open_until(self._rule)
            self._storage.close(self._rule)
            self._probe_acquired = False
            self._emit_state_change(CircuitState.HALF_OPEN, CircuitState.CLOSED)
            self._last_state = CircuitState.CLOSED
            self._metrics.record_state_change(self._rule.resource, CircuitState.CLOSED)
            self._metrics.set_state(self._rule.resource, CircuitState.CLOSED)
            self._metrics.record_recovery(
                self._rule.resource,
                open_until,
                self._rule.open_timeout_seconds,
            )
            return None

        result = self._storage.record_success(self._rule)
        if result.opened:
            self._emit_state_change(self._last_state, CircuitState.OPEN)
            self._last_state = CircuitState.OPEN
            self._metrics.record_state_change(self._rule.resource, CircuitState.OPEN)
            self._metrics.record_open(self._rule.resource)
            self._metrics.set_state(self._rule.resource, CircuitState.OPEN)
        else:
            self._last_state = CircuitState.CLOSED
            self._metrics.set_state(self._rule.resource, CircuitState.CLOSED)
        return result

    def record_failure(self) -> CircuitRecordResult | None:
        self._metrics.record_failure(self._rule.resource, self._last_state)

        if self._probe_acquired:
            open_until = self._storage.reopen(self._rule)
            self._probe_acquired = False
            self._emit_state_change(CircuitState.HALF_OPEN, CircuitState.OPEN)
            self._last_state = CircuitState.OPEN
            self._metrics.record_state_change(self._rule.resource, CircuitState.OPEN)
            self._metrics.record_open(self._rule.resource)
            self._metrics.set_state(self._rule.resource, CircuitState.OPEN)
            return CircuitRecordResult(
                opened=True,
                open_until=open_until,
                snapshot=self._storage.snapshot(self._rule),
            )

        result = self._storage.record_failure(self._rule)
        if result.opened:
            self._emit_state_change(self._last_state, CircuitState.OPEN)
            self._last_state = CircuitState.OPEN
            self._metrics.record_state_change(self._rule.resource, CircuitState.OPEN)
            self._metrics.record_open(self._rule.resource)
            self._metrics.set_state(self._rule.resource, CircuitState.OPEN)
        else:
            self._last_state = CircuitState.CLOSED
            self._metrics.set_state(self._rule.resource, CircuitState.CLOSED)
        return result

    def state(self) -> CircuitState:
        return self._storage.get_state(self._rule)

    def snapshot(self) -> CircuitWindowSnapshot:
        return self._storage.snapshot(self._rule)

    def execute_fallback(self):
        self._metrics.record_fallback(self._rule.resource, self._last_state)
        return self._fallback_handler.execute()

    def record_timeout(self) -> None:
        self._metrics.record_timeout(self._rule.resource)

    def _emit_state_change(self, old_state: CircuitState, new_state: CircuitState) -> None:
        app = getattr(self._ctx, "app", None)
        logger = getattr(app, "logger", None) or getattr(self._ctx, "logger", None)
        if logger is None:
            logger = logging.getLogger(__name__)
        log_event(
            logger,
            "breaker_state_change",
            component="circuit_breaker",
            operation="state_transition",
            result=new_state.value,
            resource=self._rule.resource,
            old_state=old_state.value,
            new_state=new_state.value,
        )


def build_circuit_breaker(ctx, rule: CircuitBreakerRule | None = None) -> CircuitBreaker:
    active_rule = rule or build_default_rule(ctx)
    storage = RedisCircuitBreakerStorage(ctx)
    metrics = CircuitBreakerMetrics(ctx)
    return CircuitBreaker(active_rule, storage, metrics, ctx=ctx)
