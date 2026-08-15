"""Retry policy primitives for transient infrastructure failures."""

from __future__ import annotations

import logging
import random
import socket
import time
from dataclasses import dataclass
from typing import Callable, Protocol, TypeVar

import redis
from flask import has_request_context, request

from app.infrastructure.logging import log_event

T = TypeVar("T")


class RandomSource(Protocol):
    def uniform(self, a: float, b: float) -> float: ...


DEFAULT_RETRYABLE_EXCEPTIONS: tuple[type[BaseException], ...] = (
    redis.TimeoutError,
    redis.ConnectionError,
    socket.timeout,
)


@dataclass(frozen=True)
class RetryConfig:
    max_attempts: int
    base_delay_s: float
    max_delay_s: float
    retryable_exceptions: tuple[type[BaseException], ...] = DEFAULT_RETRYABLE_EXCEPTIONS

    def __post_init__(self) -> None:
        if self.max_attempts < 1:
            raise ValueError("max_attempts must be >= 1")
        if self.base_delay_s < 0:
            raise ValueError("base_delay_s must be >= 0")
        if self.max_delay_s < 0:
            raise ValueError("max_delay_s must be >= 0")


@dataclass(frozen=True)
class RetryDeadline:
    deadline_at: float
    clock: Callable[[], float] = time.time

    def remaining_seconds(self) -> float:
        return max(self.deadline_at - self.clock(), 0.0)

    def can_wait(self, delay_s: float) -> bool:
        return self.remaining_seconds() > max(delay_s, 0.0)


class RetryPolicy:
    def __init__(
        self,
        config: RetryConfig,
        logger: logging.Logger,
        *,
        deadline: RetryDeadline | None = None,
        random_source: RandomSource | None = None,
        sleeper: Callable[[float], None] = time.sleep,
        metrics: "RetryMetrics | None" = None,
    ) -> None:
        self._config = config
        self._logger = logger
        self._deadline = deadline
        self._random = random_source or random.Random()
        self._sleep = sleeper
        self._metrics = metrics or RetryMetrics(None)

    def execute(self, func: Callable[[], T], *, operation: str) -> T:
        started_at = time.perf_counter()

        for attempt in range(1, self._config.max_attempts + 1):
            self._metrics.record_attempt(operation)
            try:
                result = func()
            except self._config.retryable_exceptions as exc:
                if attempt >= self._config.max_attempts:
                    self._log_exhausted(operation, attempt, exc, reason="max_attempts")
                    self._metrics.record_failure(
                        operation,
                        exc.__class__.__name__,
                        time.perf_counter() - started_at,
                    )
                    raise

                max_delay_s = self._compute_delay_cap(attempt)
                sleep_s = self._random.uniform(0.0, max_delay_s)
                if self._deadline is not None and not self._deadline.can_wait(sleep_s):
                    self._log_exhausted(
                        operation,
                        attempt,
                        exc,
                        reason="deadline",
                        next_delay_s=sleep_s,
                    )
                    self._metrics.record_failure(
                        operation,
                        exc.__class__.__name__,
                        time.perf_counter() - started_at,
                    )
                    raise

                self._log_attempt(operation, attempt, exc, sleep_s)
                self._sleep(sleep_s)
                continue
            except Exception as exc:
                self._metrics.record_failure(
                    operation,
                    exc.__class__.__name__,
                    time.perf_counter() - started_at,
                )
                raise
            self._metrics.record_success(operation, time.perf_counter() - started_at)
            return result

        raise RuntimeError("retry execution exited unexpectedly")

    def _compute_delay_cap(self, attempt: int) -> float:
        exponential = self._config.base_delay_s * (2 ** (attempt - 1))
        return min(self._config.max_delay_s, exponential)

    def _log_attempt(
        self,
        operation: str,
        attempt: int,
        exc: BaseException,
        sleep_s: float,
    ) -> None:
        remaining_ms = None
        if self._deadline is not None:
            remaining_ms = round(self._deadline.remaining_seconds() * 1000.0, 3)
        log_event(
            self._logger,
            "retry_attempt",
            component="retry",
            operation=operation,
            result="retrying",
            attempt=attempt,
            max_attempts=self._config.max_attempts,
            delay_ms=round(sleep_s * 1000.0, 3),
            exception_type=exc.__class__.__name__,
            deadline_remaining_ms=remaining_ms,
            level="WARNING",
        )

    def _log_exhausted(
        self,
        operation: str,
        attempt: int,
        exc: BaseException,
        *,
        reason: str,
        next_delay_s: float | None = None,
    ) -> None:
        remaining_ms = None
        if self._deadline is not None:
            remaining_ms = round(self._deadline.remaining_seconds() * 1000.0, 3)
        log_event(
            self._logger,
            "retry_exhausted",
            component="retry",
            operation=operation,
            result="failed",
            reason=reason,
            attempt=attempt,
            max_attempts=self._config.max_attempts,
            next_delay_ms=None if next_delay_s is None else round(next_delay_s * 1000.0, 3),
            exception_type=exc.__class__.__name__,
            deadline_remaining_ms=remaining_ms,
            level="ERROR",
        )


def build_request_deadline(ctx) -> RetryDeadline | None:
    if not has_request_context():
        return None
    budget_ms = int(getattr(ctx, "BUSINESS_TIMEOUT_MS", 0))
    if budget_ms <= 0:
        return None
    started_at = getattr(request, "_start_time", None)
    if started_at is None:
        return None
    return RetryDeadline(deadline_at=float(started_at) + (budget_ms / 1000.0))


def build_retry_policy(
    ctx,
    *,
    retryable_exceptions: tuple[type[BaseException], ...] = DEFAULT_RETRYABLE_EXCEPTIONS,
) -> RetryPolicy:
    config = RetryConfig(
        max_attempts=int(getattr(ctx, "RETRY_MAX_ATTEMPTS", 3)),
        base_delay_s=float(getattr(ctx, "RETRY_BASE_DELAY_MS", 5.0)) / 1000.0,
        max_delay_s=float(getattr(ctx, "RETRY_MAX_DELAY_MS", 50.0)) / 1000.0,
        retryable_exceptions=retryable_exceptions,
    )
    app = getattr(ctx, "app", None)
    logger = getattr(app, "logger", logging.getLogger(__name__))
    return RetryPolicy(
        config=config,
        logger=logger,
        deadline=build_request_deadline(ctx),
        random_source=getattr(ctx, "random", None),
        metrics=RetryMetrics(ctx),
    )


class RetryMetrics:
    def __init__(self, ctx) -> None:
        self._ctx = ctx

    def record_attempt(self, operation: str) -> None:
        counter = getattr(self._ctx, "RETRY_ATTEMPT_TOTAL", None)
        if counter is not None:
            counter.labels(operation=operation).inc()

    def record_success(self, operation: str, duration_s: float) -> None:
        counter = getattr(self._ctx, "RETRY_SUCCESS_TOTAL", None)
        if counter is not None:
            counter.labels(operation=operation).inc()
        histogram = getattr(self._ctx, "RETRY_DURATION_SECONDS", None)
        if histogram is not None:
            histogram.labels(operation=operation, result="success").observe(duration_s)

    def record_failure(self, operation: str, exception_type: str, duration_s: float) -> None:
        counter = getattr(self._ctx, "RETRY_FAILURE_TOTAL", None)
        if counter is not None:
            counter.labels(operation=operation, exception_type=exception_type).inc()
        histogram = getattr(self._ctx, "RETRY_DURATION_SECONDS", None)
        if histogram is not None:
            histogram.labels(operation=operation, result="failure").observe(duration_s)
