import threading
import time

import pytest

from chaos_service.resilience import build_circuit_breaker
from chaos_service.resilience.breaker.state import CircuitState


@pytest.mark.parametrize(
    ("min_request_amount", "failure_count", "expected_state"),
    [
        (3, 2, CircuitState.CLOSED),
        (3, 3, CircuitState.OPEN),
    ],
)
def test_closed_to_open_transition_matrix(
    app_state,
    breaker_factory,
    min_request_amount,
    failure_count,
    expected_state,
):
    app_state.MIN_REQUEST_AMOUNT = min_request_amount
    app_state.BREAKER_FAILURE_RATE_THRESHOLD = 0.5
    app_state.BREAKER_WINDOW_SEC = 60
    app_state.BREAKER_OPEN_SEC = 30
    breaker = breaker_factory()

    for _ in range(failure_count):
        assert breaker.allow_request() is True
        result = breaker.record_failure()
        assert result is not None

    assert breaker.state() is expected_state
    if expected_state is CircuitState.OPEN:
        assert result.opened is True
    else:
        assert result.opened is False


def test_open_fast_fail(app_state, breaker_factory):
    app_state.redis_client.set(app_state.CB_KEY_OPEN_UNTIL, str(time.time() + 30.0))
    breaker = build_circuit_breaker(app_state)

    assert breaker.allow_request() is False
    with app_state.app.app_context():
        response, status = breaker.execute_fallback()
    assert status == 202
    assert response.get_json()["reason"] == "circuit open"


def test_half_open_probe_lock(app_state):
    app_state.redis_client.set(app_state.CB_KEY_OPEN_UNTIL, str(time.time() - 5.0))
    app_state.redis_client.delete(
        app_state.CB_KEY_PROBE,
        app_state.CB_KEY_FAILURES,
        app_state.CB_KEY_TOTAL_REQUESTS,
    )

    results = []
    errors = []
    start = threading.Barrier(100)

    def worker():
        try:
            breaker = build_circuit_breaker(app_state)
            start.wait(timeout=2.0)
            results.append(breaker.allow_request())
        except Exception as exc:  # pragma: no cover
            errors.append(exc)

    threads = [threading.Thread(target=worker) for _ in range(100)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join()

    assert not errors
    assert results.count(True) == 1
    assert results.count(False) == 99


def test_half_open_success_recover(app_state, breaker_factory):
    app_state.redis_client.set(app_state.CB_KEY_OPEN_UNTIL, str(time.time() - 5.0))
    app_state.redis_client.delete(
        app_state.CB_KEY_PROBE,
        app_state.CB_KEY_FAILURES,
        app_state.CB_KEY_TOTAL_REQUESTS,
    )
    breaker = build_circuit_breaker(app_state)

    assert breaker.allow_request() is True
    breaker.record_success()

    assert breaker.state().value == "closed"
    assert float(app_state.redis_client.get(app_state.CB_KEY_OPEN_UNTIL) or 0.0) == 0.0
    assert app_state.redis_client.get(app_state.CB_KEY_PROBE) is None


def test_half_open_failure_reopen(app_state, breaker_factory):
    app_state.redis_client.set(app_state.CB_KEY_OPEN_UNTIL, str(time.time() - 5.0))
    app_state.redis_client.delete(
        app_state.CB_KEY_PROBE,
        app_state.CB_KEY_FAILURES,
        app_state.CB_KEY_TOTAL_REQUESTS,
    )
    breaker = build_circuit_breaker(app_state)

    assert breaker.allow_request() is True
    result = breaker.record_failure()

    assert result is not None
    assert result.opened is True
    assert breaker.state().value == "open"
    assert float(app_state.redis_client.get(app_state.CB_KEY_OPEN_UNTIL) or 0.0) > time.time()
    assert app_state.redis_client.get(app_state.CB_KEY_PROBE) is None


def test_concurrent_failure_state_transition(app_state):
    app_state.MIN_REQUEST_AMOUNT = 5
    app_state.BREAKER_FAILURE_RATE_THRESHOLD = 0.5
    app_state.BREAKER_WINDOW_SEC = 60
    app_state.BREAKER_OPEN_SEC = 30

    opened_flags = []
    errors = []
    start = threading.Barrier(20)

    def worker():
        try:
            breaker = build_circuit_breaker(app_state)
            start.wait(timeout=2.0)
            result = breaker.record_failure()
            opened_flags.append(result.opened if result is not None else False)
        except Exception as exc:  # pragma: no cover
            errors.append(exc)

    threads = [threading.Thread(target=worker) for _ in range(20)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join()

    assert not errors
    assert sum(1 for opened in opened_flags if opened) <= 1
    breaker_state = build_circuit_breaker(app_state).state().value
    assert breaker_state == "open"
