from __future__ import annotations

import sys
from types import ModuleType

from chaos_service import resilience, store, traffic

from .factory import build_application, create_app

app, runtime = build_application()


def _order_key(order_id: str) -> str:
    return store.order_key(runtime, order_id)


def _get_order_from_store(order_id: str):
    return store.get_order_from_store(runtime, order_id)


def _put_order_in_store(order_id: str, doc: dict) -> None:
    return store.put_order_in_store(runtime, order_id, doc)


def _idem_store_key(idem_key: str) -> str:
    return store.idem_store_key(runtime, idem_key)


def _idem_payload_fingerprint(item_id: str, quantity: int) -> str:
    return store.idem_payload_fingerprint(item_id, quantity)


def _load_idempotency_record(idem_key: str) -> dict | None:
    return store.load_idempotency_record(runtime, idem_key)


def _reserve_idempotency_key(idem_key: str, payload_fp: str) -> tuple[str, dict]:
    return store.reserve_idempotency_key(runtime, idem_key, payload_fp)


def _wait_for_idempotency_result(idem_key: str, payload_fp: str) -> tuple[str, dict]:
    return store.wait_for_idempotency_result(runtime, idem_key, payload_fp)


def _build_idempotency_replay_response(record: dict) -> tuple[int, dict]:
    return store.build_replay_response(record)


def _finalize_idempotency_success(
    idem_key: str,
    payload_fp: str,
    order_id: str,
    response_status: int = 201,
    response_body: dict | None = None,
) -> None:
    return store.finalize_idempotency_success(
        runtime,
        idem_key,
        payload_fp,
        order_id,
        response_status=response_status,
        response_body=response_body,
    )


def _save_idempotency_failed(
    idem_key: str,
    payload_fp: str,
    error_message: str,
    response_status: int,
    response_body: dict | None = None,
) -> None:
    return store.save_failed(
        runtime,
        idem_key,
        payload_fp,
        error_message,
        response_status,
        response_body=response_body,
    )


def _release_idempotency_reservation(idem_key: str, record: dict | None = None) -> bool:
    return store.release_idempotency_reservation(runtime, idem_key, record)


def validate_resilience_config() -> None:
    return resilience.validate_resilience_config(runtime)


def _order_deadline_exceeded(elapsed_s: float, processing_planned_s: float, budget_ms: int) -> bool:
    return resilience.order_deadline_exceeded(elapsed_s, processing_planned_s, budget_ms)


def _log_json_event(request, event: str, **fields) -> None:
    return resilience.log_json_event(runtime, request, event, **fields)


def _mask_value(key_name, value):
    return traffic.mask_value(key_name, value)


def _sanitize_headers(headers):
    return traffic.sanitize_headers(headers)


def _traffic_writer():
    return traffic.traffic_writer(runtime)


def _record_success_traffic(response_status):
    from flask import request

    return traffic.record_success_traffic(runtime, request, response_status)


def _sliding_rate_script(redis_conn):
    return resilience.sliding_rate_script(redis_conn)


def _fixed_rate_script(redis_conn):
    return resilience.fixed_rate_script(redis_conn)


def allow_request_by_rate_limit(client_ip):
    return resilience.allow_request_by_rate_limit(runtime, client_ip)


def _cb_parse_open_until(raw) -> float:
    return resilience.cb_parse_open_until(raw)


def is_circuit_open():
    return resilience.is_circuit_open(runtime)


def record_failure_and_maybe_open():
    return resilience.record_failure_and_maybe_open(runtime)


def record_request():
    return resilience.record_request(runtime)


def record_success():
    return resilience.record_success(runtime)


_RUNTIME_ATTRS = {
    "app",
    "redis_client",
    "db_lock",
    "random",
    "logger",
    "request_context_cls",
    "_record_queue",
    "_writer_thread",
    "SERVICE_NAME",
    "APP_ENV",
    "RATE_LIMIT_RESOURCE",
    "RATE_LIMIT_DIMENSION",
    "RATE_LIMIT_ALGORITHM",
    "RATE_LIMIT_PER_SEC",
    "RATE_LIMIT_WINDOW_SEC",
    "RATE_LIMIT_LUA_DIR",
    "BUSINESS_TIMEOUT_MS",
    "ENABLE_RESILIENCE",
    "INVENTORY_BUSY_PROB",
    "BREAKER_RESOURCE",
    "BREAKER_FAIL_THRESHOLD",
    "BREAKER_WINDOW_SEC",
    "BREAKER_OPEN_SEC",
    "BREAKER_FAILURE_RATE_THRESHOLD",
    "MIN_REQUEST_AMOUNT",
    "CIRCUIT_PROBE_TTL_SEC",
    "CB_KEY_OPEN_UNTIL",
    "CB_KEY_FAILURES",
    "CB_KEY_TOTAL_REQUESTS",
    "CB_KEY_PROBE",
    "ORDER_TTL_SEC",
    "ORDER_KEY_PREFIX",
    "IDEM_TTL_SEC",
    "IDEM_PENDING_TTL_SEC",
    "IDEM_WAIT_TIMEOUT_MS",
    "IDEM_WAIT_POLL_MS",
    "RETRY_MAX_ATTEMPTS",
    "RETRY_BASE_DELAY_MS",
    "RETRY_MAX_DELAY_MS",
    "CHAOS_ENABLED",
    "FAULT_INJECTION_ENABLED",
    "FAULT_DEFAULT_TTL_SEC",
    "FAULT_MAX_LATENCY_MS",
    "FAULT_MAX_DROP_RATE",
    "TRAFFIC_RECORD_ENABLED",
    "TRAFFIC_RECORD_FILE",
    "TRAFFIC_RECORD_MAX_QUEUE",
    "REQUEST_COUNT",
    "REQUEST_ERRORS",
    "REQUEST_LATENCY",
    "REQUESTS_IN_PROGRESS",
    "ORDER_COUNT",
    "ORDER_REJECTED",
    "ORDER_RATE_LIMITED",
    "RATE_LIMIT_ALLOWED_TOTAL",
    "RATE_LIMIT_REJECTED_TOTAL",
    "RATE_LIMIT_REDIS_ERROR_TOTAL",
    "ORDER_TIMEOUT",
    "ORDER_DEGRADED",
    "ORDER_CIRCUIT_OPEN",
    "CIRCUIT_BREAKER_REQUESTS_TOTAL",
    "CIRCUIT_BREAKER_FAILURES_TOTAL",
    "CIRCUIT_BREAKER_TIMEOUT_TOTAL",
    "CIRCUIT_BREAKER_REJECTED_TOTAL",
    "CIRCUIT_BREAKER_STATE_CHANGE_TOTAL",
    "CIRCUIT_BREAKER_OPEN_TOTAL",
    "CIRCUIT_BREAKER_FALLBACK_TOTAL",
    "CIRCUIT_BREAKER_STATE",
    "CIRCUIT_BREAKER_RECOVERY_SECONDS",
    "ORDER_IDEMPOTENT_HIT",
    "ORDER_IDEMPOTENT_PROCESSING",
    "ORDER_IDEMPOTENT_CONFLICT",
    "IDEMPOTENCY_REQUEST_TOTAL",
    "IDEMPOTENCY_REPLAY_TOTAL",
    "IDEMPOTENCY_CONFLICT_TOTAL",
    "IDEMPOTENCY_PROCESSING_TOTAL",
    "IDEMPOTENCY_FAILED_TOTAL",
    "IDEMPOTENCY_LOCK_FAILURE_TOTAL",
    "RETRY_ATTEMPT_TOTAL",
    "RETRY_SUCCESS_TOTAL",
    "RETRY_FAILURE_TOTAL",
    "RETRY_DURATION_SECONDS",
    "CHAOS_EXPERIMENT_TOTAL",
    "CHAOS_EXPERIMENT_SUCCESS_TOTAL",
    "CHAOS_EXPERIMENT_FAILED_TOTAL",
    "CHAOS_ACTIVE_EXPERIMENT",
    "CHAOS_RECOVERY_DURATION_SECONDS",
    "CHAOS_FAULT_INJECTED_TOTAL",
    "CHAOS_FAULT_RECOVERED_TOTAL",
    "CHAOS_EXPERIMENT_DURATION_SECONDS",
}


class _AppModule(ModuleType):
    def __getattr__(self, name: str):
        if name in _RUNTIME_ATTRS:
            if name == "app":
                return app
            return getattr(runtime, name)
        raise AttributeError(name)

    def __setattr__(self, name: str, value):
        if name in _RUNTIME_ATTRS:
            if name == "app":
                raise AttributeError("app is managed by the application factory")
            setattr(runtime, name, value)
            return
        super().__setattr__(name, value)


sys.modules[__name__].__class__ = _AppModule

__all__ = [
    "app",
    "runtime",
    "_cb_parse_open_until",
    "_fixed_rate_script",
    "_get_order_from_store",
    "_idem_payload_fingerprint",
    "_idem_store_key",
    "_load_idempotency_record",
    "_log_json_event",
    "_mask_value",
    "_order_deadline_exceeded",
    "_order_key",
    "_put_order_in_store",
    "_record_success_traffic",
    "_release_idempotency_reservation",
    "_reserve_idempotency_key",
    "_sanitize_headers",
    "_save_idempotency_failed",
    "_sliding_rate_script",
    "_traffic_writer",
    "_wait_for_idempotency_result",
    "allow_request_by_rate_limit",
    "create_app",
    "is_circuit_open",
    "record_failure_and_maybe_open",
    "record_request",
    "record_success",
    "validate_resilience_config",
]
