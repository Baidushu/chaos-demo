"""Circuit breaker rule definitions."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class CircuitBreakerRule:
    resource: str
    failure_rate_threshold: float
    min_request_count: int
    window_seconds: int
    open_timeout_seconds: int

    def __post_init__(self) -> None:
        if not self.resource:
            raise ValueError("resource must not be empty")
        if not 0.0 <= self.failure_rate_threshold <= 1.0:
            raise ValueError("failure_rate_threshold must be in [0, 1]")
        if self.min_request_count < 1:
            raise ValueError("min_request_count must be >= 1")
        if self.window_seconds < 1:
            raise ValueError("window_seconds must be >= 1")
        if self.open_timeout_seconds < 1:
            raise ValueError("open_timeout_seconds must be >= 1")


def build_default_rule(ctx) -> CircuitBreakerRule:
    return CircuitBreakerRule(
        resource=str(getattr(ctx, "BREAKER_RESOURCE", "order")).strip() or "order",
        failure_rate_threshold=float(getattr(ctx, "BREAKER_FAILURE_RATE_THRESHOLD", 0.5)),
        min_request_count=int(getattr(ctx, "MIN_REQUEST_AMOUNT", 100)),
        window_seconds=int(getattr(ctx, "BREAKER_WINDOW_SEC", 10)),
        open_timeout_seconds=int(getattr(ctx, "BREAKER_OPEN_SEC", 8)),
    )
