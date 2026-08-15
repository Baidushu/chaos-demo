"""Resilience helpers: rate limit, circuit breaker, retry, and structured logging."""

from __future__ import annotations

from pathlib import Path

from flask import jsonify

from app.infrastructure.logging import log_event
from chaos_service import rate_limiter

from .breaker import (
    CircuitBreaker,
    CircuitBreakerRule,
    CircuitState,
    build_circuit_breaker,
)
from .breaker import (
    build_default_rule as build_default_breaker_rule,
)

_sliding_rate_scripts: dict[int, object] = {}
_fixed_rate_scripts: dict[int, object] = {}
_LUA_DIR = Path(__file__).resolve().parent.parent.parent / "lua"


def validate_resilience_config(ctx) -> None:
    rate_limiter.build_default_rule(ctx)
    build_default_breaker_rule(ctx)
    if ctx.BUSINESS_TIMEOUT_MS < 0:
        raise ValueError("BUSINESS_TIMEOUT_MS must be >= 0")
    if not 0.0 <= ctx.INVENTORY_BUSY_PROB <= 1.0:
        raise ValueError("INVENTORY_BUSY_PROB must be in [0, 1]")
    if ctx.BREAKER_FAIL_THRESHOLD < 1 or ctx.BREAKER_WINDOW_SEC < 1 or ctx.BREAKER_OPEN_SEC < 1:
        raise ValueError("BREAKER_* must be >= 1 where applicable")
    if not 0.0 <= ctx.BREAKER_FAILURE_RATE_THRESHOLD <= 1.0:
        raise ValueError("BREAKER_FAILURE_RATE_THRESHOLD must be in [0, 1]")
    if ctx.MIN_REQUEST_AMOUNT < 1:
        raise ValueError("MIN_REQUEST_AMOUNT must be >= 1")
    if ctx.ORDER_TTL_SEC < 60:
        raise ValueError("ORDER_TTL_SEC must be >= 60 (seconds)")
    if ctx.IDEM_TTL_SEC < 1 or ctx.IDEM_PENDING_TTL_SEC < 1:
        raise ValueError("IDEM_*_TTL_SEC must be >= 1")
    if ctx.IDEM_WAIT_TIMEOUT_MS < 0 or ctx.IDEM_WAIT_POLL_MS < 1:
        raise ValueError("IDEM_WAIT_TIMEOUT_MS must be >= 0 and IDEM_WAIT_POLL_MS >= 1")
    if ctx.CIRCUIT_PROBE_TTL_SEC < 1:
        raise ValueError("CIRCUIT_PROBE_TTL_SEC must be >= 1")
    if ctx.RETRY_MAX_ATTEMPTS < 1:
        raise ValueError("RETRY_MAX_ATTEMPTS must be >= 1")
    if ctx.RETRY_BASE_DELAY_MS < 0 or ctx.RETRY_MAX_DELAY_MS < 0:
        raise ValueError("RETRY_*_DELAY_MS must be >= 0")


def order_deadline_exceeded(elapsed_s: float, processing_planned_s: float, budget_ms: int) -> bool:
    return elapsed_s + processing_planned_s > (budget_ms / 1000.0)


def log_json_event(ctx, request, event: str, **fields) -> None:
    log_event(
        ctx.app.logger,
        event,
        component="resilience",
        operation=getattr(request, "path", "request"),
        **fields,
    )


def sliding_rate_script(redis_conn):
    sid = id(redis_conn)
    if sid not in _sliding_rate_scripts:
        _sliding_rate_scripts[sid] = redis_conn.register_script(
            (_LUA_DIR / "sliding_window.lua").read_text(encoding="utf-8")
        )
    return _sliding_rate_scripts[sid]


def fixed_rate_script(redis_conn):
    sid = id(redis_conn)
    if sid not in _fixed_rate_scripts:
        _fixed_rate_scripts[sid] = redis_conn.register_script(
            (_LUA_DIR / "fixed_window.lua").read_text(encoding="utf-8")
        )
    return _fixed_rate_scripts[sid]


def allow_request_by_rate_limit(ctx, client_ip):
    limiter = rate_limiter.build_rate_limiter(ctx)
    decision = limiter.allow(client_ip)
    return decision.allowed


def rate_limit_request(ctx, request):
    """Enforces rate limiting for the supported HTTP entry points."""
    if not getattr(ctx, "ENABLE_RESILIENCE", False):
        return None
    if request.method != "POST" or request.path != "/order":
        return None

    subject_id = rate_limiter.resolve_subject_id(
        request,
        getattr(ctx, "RATE_LIMIT_DIMENSION", "client_ip"),
    )
    limiter = rate_limiter.build_rate_limiter(ctx)
    decision = limiter.allow(subject_id)
    if decision.allowed:
        return None

    ctx.ORDER_RATE_LIMITED.inc()
    log_event(
        ctx.app.logger,
        "rate_limited",
        component="rate_limiter",
        operation="allow_request",
        result="rejected",
        path=request.path,
        client_ip=subject_id,
        algorithm=getattr(limiter.rule, "algorithm", None),
        resource=getattr(limiter.rule, "resource", None),
        dimension=getattr(limiter.rule, "dimension", None),
        level="WARNING",
    )
    return jsonify({"error": "rate limit exceeded"}), 429


def cb_parse_open_until(raw) -> float:
    return build_circuit_breaker_cb_open_until(raw)


def build_circuit_breaker_cb_open_until(raw) -> float:
    if raw is None or raw == "":
        return 0.0
    try:
        return float(raw)
    except (TypeError, ValueError):
        return 0.0


def is_circuit_open(ctx):
    breaker = build_circuit_breaker(ctx)
    return not breaker.allow_request()


def record_request(ctx) -> tuple[int, int, float]:
    breaker = build_circuit_breaker(ctx)
    snapshot = breaker.snapshot()
    return (
        snapshot.failure_count,
        snapshot.total_request_count,
        snapshot.failure_rate,
    )


def record_failure_and_maybe_open(ctx):
    breaker = build_circuit_breaker(ctx)
    breaker.record_failure()


def record_success(ctx):
    breaker = build_circuit_breaker(ctx)
    breaker.record_success()


__all__ = [
    "CircuitBreaker",
    "CircuitBreakerRule",
    "CircuitState",
    "allow_request_by_rate_limit",
    "build_circuit_breaker",
    "build_default_breaker_rule",
    "cb_parse_open_until",
    "fixed_rate_script",
    "is_circuit_open",
    "log_json_event",
    "order_deadline_exceeded",
    "rate_limit_request",
    "record_failure_and_maybe_open",
    "record_request",
    "record_success",
    "sliding_rate_script",
    "validate_resilience_config",
]
