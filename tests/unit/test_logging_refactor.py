from __future__ import annotations

import json
import logging
from io import StringIO

import pytest
import redis

from app.infrastructure.logging import JSONFormatter, log_event
from app.observability.logging import clear_context, set_context
from chaos_service import retry as retry_module
from chaos_service import store as store_module
from chaos_service.chaos.observer import ChaosObserver


class _FakeRandom:
    def __init__(self, values):
        self._values = list(values)

    def uniform(self, _a: float, _b: float) -> float:
        if not self._values:
            raise AssertionError("unexpected random.uniform call")
        return self._values.pop(0)


def _build_retry_policy(logger: logging.Logger, *, max_attempts: int, random_values: list[float]):
    return retry_module.RetryPolicy(
        config=retry_module.RetryConfig(
            max_attempts=max_attempts,
            base_delay_s=0.01,
            max_delay_s=0.1,
        ),
        logger=logger,
        random_source=_FakeRandom(random_values),
        sleeper=lambda _delay: None,
    )


def _parse_lines(stream: StringIO) -> list[dict]:
    lines = [line.strip() for line in stream.getvalue().splitlines() if line.strip()]
    return [json.loads(line) for line in lines]


def _capture_logger(logger: logging.Logger):
    stream = StringIO()
    handler = logging.StreamHandler(stream)
    handler.setFormatter(JSONFormatter())
    previous_handlers = list(logger.handlers)
    previous_propagate = logger.propagate
    logger.handlers = [handler]
    logger.propagate = False
    logger.setLevel(logging.INFO)
    return stream, previous_handlers, previous_propagate


def _restore_logger(logger: logging.Logger, previous_handlers, previous_propagate: bool) -> None:
    logger.handlers = previous_handlers
    logger.propagate = previous_propagate


def test_structured_log_event_includes_context_and_event_fields():
    logger = logging.getLogger("structured-log-test")
    stream, previous_handlers, previous_propagate = _capture_logger(logger)
    try:
        set_context(
            request_id="rid-1",
            trace_id="tid-1",
            service="chaos-demo",
            environment="test",
        )
        log_event(
            logger,
            "sample_event",
            component="unit_test",
            operation="demo_operation",
            result="success",
            answer=42,
        )
    finally:
        clear_context()
        _restore_logger(logger, previous_handlers, previous_propagate)

    entry = _parse_lines(stream)[0]
    assert entry["event"] == "sample_event"
    assert entry["component"] == "unit_test"
    assert entry["operation"] == "demo_operation"
    assert entry["result"] == "success"
    assert entry["request_id"] == "rid-1"
    assert entry["trace_id"] == "tid-1"
    assert entry["service"] == "chaos-demo"
    assert entry["environment"] == "test"
    assert entry["answer"] == 42


def test_request_logging_context_is_injected_automatically(stable_order_env, client):
    logger = stable_order_env.app.logger
    stream, previous_handlers, previous_propagate = _capture_logger(logger)
    try:
        response = client.post(
            "/order",
            json={"item_id": "sku-log", "quantity": 1},
            headers={"X-Request-Id": "req-log-1", "X-Trace-Id": "trace-log-1"},
        )
        assert response.status_code == 201
    finally:
        _restore_logger(logger, previous_handlers, previous_propagate)

    entries = _parse_lines(stream)
    order_created = next(entry for entry in entries if entry.get("event") == "order_created")
    assert order_created["request_id"] == "req-log-1"
    assert order_created["trace_id"] == "trace-log-1"
    assert order_created["service"] == stable_order_env.SERVICE_NAME
    assert order_created["environment"] == stable_order_env.APP_ENV
    assert order_created["component"] == "order_service"


def test_retry_logs_structured_attempt_and_exhausted_events():
    logger = logging.getLogger("retry-structured-test")
    stream, previous_handlers, previous_propagate = _capture_logger(logger)
    try:
        set_context(request_id="rid-retry", trace_id="tid-retry")
        policy = _build_retry_policy(logger, max_attempts=2, random_values=[0.0])
        with pytest.raises(redis.TimeoutError):
            policy.execute(
                lambda: (_ for _ in ()).throw(redis.TimeoutError("retry boom")),
                operation="redis_call",
            )
    finally:
        clear_context()
        _restore_logger(logger, previous_handlers, previous_propagate)

    entries = _parse_lines(stream)
    assert [entry["event"] for entry in entries] == ["retry_attempt", "retry_exhausted"]
    assert entries[0]["component"] == "retry"
    assert entries[0]["request_id"] == "rid-retry"
    assert entries[1]["result"] == "failed"
    assert entries[1]["exception_type"] == "TimeoutError"


def test_breaker_logs_state_change_events(app_state, breaker_factory):
    logger = app_state.app.logger
    stream, previous_handlers, previous_propagate = _capture_logger(logger)
    try:
        set_context(request_id="rid-breaker", trace_id="tid-breaker")
        app_state.MIN_REQUEST_AMOUNT = 3
        app_state.BREAKER_FAILURE_RATE_THRESHOLD = 0.5
        app_state.BREAKER_WINDOW_SEC = 60
        app_state.BREAKER_OPEN_SEC = 30
        breaker = breaker_factory()
        for _ in range(3):
            assert breaker.allow_request() is True
            breaker.record_failure()
    finally:
        clear_context()
        _restore_logger(logger, previous_handlers, previous_propagate)

    entries = _parse_lines(stream)
    state_change = next(entry for entry in entries if entry.get("event") == "breaker_state_change")
    assert state_change["component"] == "circuit_breaker"
    assert state_change["old_state"] == "closed"
    assert state_change["new_state"] == "open"
    assert state_change["request_id"] == "rid-breaker"


def test_idempotency_logs_replay_and_conflict_events(app_state):
    logger = app_state.app.logger
    stream, previous_handlers, previous_propagate = _capture_logger(logger)
    try:
        set_context(request_id="rid-idem", trace_id="tid-idem")
        fp = store_module.idem_payload_fingerprint("sku-idem", 1)
        state, _record = store_module.reserve_idempotency_key(app_state, "idem-log-key", fp)
        assert state == "owner"
        store_module.finalize_idempotency_success(
            app_state,
            "idem-log-key",
            fp,
            "OID-LOG",
        )
        replay_state, _ = store_module.reserve_idempotency_key(app_state, "idem-log-key", fp)
        assert replay_state == "replay"
        conflict_state, _ = store_module.reserve_idempotency_key(
            app_state,
            "idem-log-key",
            store_module.idem_payload_fingerprint("sku-idem", 2),
        )
        assert conflict_state == "conflict"
    finally:
        clear_context()
        _restore_logger(logger, previous_handlers, previous_propagate)

    events = [entry["event"] for entry in _parse_lines(stream)]
    assert "idempotency_reserve" in events
    assert "idempotency_replay" in events
    assert "idempotency_conflict" in events


def test_chaos_observer_logs_lifecycle_events(app_state, chaos_experiment_factory):
    logger = app_state.app.logger
    stream, previous_handlers, previous_propagate = _capture_logger(logger)
    try:
        set_context(request_id="rid-chaos", trace_id="tid-chaos")
        experiment = chaos_experiment_factory()
        observer = ChaosObserver(app_state)
        observer.record_injected(experiment, phase="pre_request")
        observer.record_recovered(experiment)
    finally:
        clear_context()
        _restore_logger(logger, previous_handlers, previous_propagate)

    entries = _parse_lines(stream)
    events = [entry["event"] for entry in entries]
    assert "chaos_experiment_start" in events
    assert "fault_injection" in events
    assert "chaos_experiment_end" in events
