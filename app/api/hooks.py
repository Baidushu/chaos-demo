from __future__ import annotations

import time
import uuid
from typing import Any, cast

import redis
from flask import jsonify, request

from app.infrastructure.logging import log_event
from app.observability.logging import clear_context, set_context
from chaos_service import fault_injection, resilience, traffic


def register_hooks(flask_app, runtime) -> None:
    @flask_app.before_request
    def before_request():
        req = cast(Any, request)
        req._start_time = time.time()
        req._request_id = _resolve_request_id()
        req._trace_id = _resolve_trace_id(req._request_id)
        req._request_context = runtime.build_request_context(
            req,
            request_id=req._request_id,
            trace_id=req._trace_id,
            user_id=request.headers.get("X-User-Id"),
        )
        set_context(
            request_id=req._request_id,
            trace_id=req._trace_id,
            user_id=request.headers.get("X-User-Id"),
            service=getattr(runtime, "SERVICE_NAME", None),
            environment=getattr(runtime, "APP_ENV", None),
        )

        if req.path.startswith("/fault") or req.path.startswith("/chaos"):
            return None
        if not req.path.startswith(("/healthz", "/live", "/ready", "/metrics")):
            try:
                req._chaos_experiments = fault_injection.prepare_request_experiments(
                    runtime,
                    req,
                )
                fault_action = fault_injection.apply_faults(runtime, req)
                if fault_action == "drop":
                    runtime.ORDER_DEGRADED.inc()
                    return jsonify({"error": "fault injected: drop", "fault": True}), 503
                if fault_action == "exception":
                    error_type = (
                        (fault_injection.get_fault(runtime.redis_client, "exception") or {})
                        .get("params", {})
                        .get("error_type", "runtime")
                    )
                    raise RuntimeError(f"fault injected: {error_type}")
            except RuntimeError:
                raise
            except Exception as exc:
                log_event(
                    runtime.app.logger,
                    "chaos_prepare_failed",
                    component="chaos",
                    operation="prepare_request_experiments",
                    result="error",
                    error=str(exc),
                    level="ERROR",
                )

        rate_limited = resilience.rate_limit_request(runtime, req)
        if rate_limited is not None:
            return rate_limited
        return None

    @flask_app.after_request
    def after_request(response):
        req = cast(Any, request)
        duration = time.time() - getattr(req, "_start_time", time.time())
        response._chaos_duration_ms = duration * 1000.0
        traffic.record_success_traffic(runtime, req, response.status_code)
        fault_injection.record_response(runtime, response, req)
        rid = getattr(req, "_request_id", None)
        if rid:
            response.headers["X-Request-Id"] = rid
        tid = getattr(req, "_trace_id", None)
        if tid:
            response.headers["X-Trace-Id"] = tid
        return response

    @flask_app.teardown_request
    def teardown_request(_exc):
        clear_context()


def _resolve_request_id() -> str:
    raw = request.headers.get("X-Request-Id", "")
    cleaned = (raw or "").strip()
    if not cleaned or len(cleaned) > 256:
        return str(uuid.uuid4())
    return cleaned[:128]


def _resolve_trace_id(default: str) -> str:
    raw = request.headers.get("X-Trace-Id", "")
    cleaned = (raw or "").strip()
    if not cleaned or len(cleaned) > 256:
        return default
    return cleaned[:128]


def register_error_handlers(flask_app) -> None:
    from app.exceptions import BusinessException

    @flask_app.errorhandler(BusinessException)
    def handle_business_exception(exc: BusinessException):
        return jsonify(exc.to_response()), exc.status_code

    @flask_app.errorhandler(PermissionError)
    def handle_permission_error(exc: PermissionError):
        return jsonify({"error": str(exc), "code": "forbidden"}), 403

    @flask_app.errorhandler(redis.RedisError)
    def handle_redis_error(exc: redis.RedisError):
        return jsonify({"error": "redis unavailable", "code": "redis_error"}), 503
