import logging
import socket
from types import SimpleNamespace

import pytest
import redis

from chaos_service import retry as retry_module


class _FakeRandom:
    def __init__(self, values):
        self._values = list(values)

    def uniform(self, _a: float, _b: float) -> float:
        if not self._values:
            raise AssertionError("unexpected random.uniform call")
        return self._values.pop(0)


def _build_policy(
    *,
    max_attempts: int = 3,
    base_delay_s: float = 0.01,
    max_delay_s: float = 0.1,
    deadline=None,
    random_values=None,
    sleeper=None,
):
    return retry_module.RetryPolicy(
        config=retry_module.RetryConfig(
            max_attempts=max_attempts,
            base_delay_s=base_delay_s,
            max_delay_s=max_delay_s,
        ),
        logger=logging.getLogger("retry-test"),
        deadline=deadline,
        random_source=_FakeRandom(random_values or []),
        sleeper=sleeper or (lambda _delay: None),
    )


@pytest.mark.parametrize(
    ("exception_factory", "should_retry", "expected_attempts"),
    [
        (lambda: redis.ConnectionError("transient"), True, 3),
        (lambda: redis.TimeoutError("timeout"), True, 3),
        (lambda: socket.timeout("slow socket"), True, 3),
        (lambda: ValueError("bad request"), False, 1),
    ],
)
def test_retry_policy_exception_matrix(exception_factory, should_retry, expected_attempts):
    policy = _build_policy(random_values=[0.0, 0.0])
    attempts = {"count": 0}

    def flaky():
        attempts["count"] += 1
        if should_retry and attempts["count"] >= expected_attempts:
            return "ok"
        raise exception_factory()

    if should_retry:
        assert policy.execute(flaky, operation="test_operation") == "ok"
    else:
        with pytest.raises(ValueError):
            policy.execute(flaky, operation="business_error")

    assert attempts["count"] == expected_attempts


def test_retry_policy_uses_full_jitter_sleep_values():
    sleeps: list[float] = []
    policy = _build_policy(
        max_attempts=3,
        base_delay_s=0.1,
        max_delay_s=0.4,
        random_values=[0.03, 0.07],
        sleeper=sleeps.append,
    )
    attempts = {"count": 0}

    def flaky():
        attempts["count"] += 1
        if attempts["count"] < 3:
            raise socket.timeout("slow socket")
        return "done"

    assert policy.execute(flaky, operation="full_jitter") == "done"
    assert sleeps == [0.03, 0.07]


def test_retry_policy_stops_when_deadline_cannot_cover_next_sleep():
    clock = {"now": 10.0}
    deadline = retry_module.RetryDeadline(deadline_at=10.05, clock=lambda: clock["now"])
    sleeps: list[float] = []
    policy = _build_policy(
        max_attempts=3,
        base_delay_s=0.1,
        max_delay_s=0.2,
        deadline=deadline,
        random_values=[0.06],
        sleeper=sleeps.append,
    )

    with pytest.raises(redis.TimeoutError):
        policy.execute(
            lambda: (_ for _ in ()).throw(redis.TimeoutError("deadline guard")),
            operation="deadline_guard",
        )

    assert sleeps == []


def test_retry_policy_exhausts_retryable_exception():
    policy = _build_policy(max_attempts=3, random_values=[0.0, 0.0])

    with pytest.raises(redis.ConnectionError):
        policy.execute(
            lambda: (_ for _ in ()).throw(redis.ConnectionError("still failing")),
            operation="retry_exhausted",
        )


def test_build_retry_policy_uses_ctx_random_and_deadline(monkeypatch):
    fake_request = SimpleNamespace(_start_time=100.0)
    monkeypatch.setattr(retry_module, "has_request_context", lambda: True)
    monkeypatch.setattr(retry_module, "request", fake_request)

    ctx = SimpleNamespace(
        RETRY_MAX_ATTEMPTS=4,
        RETRY_BASE_DELAY_MS=10.0,
        RETRY_MAX_DELAY_MS=80.0,
        BUSINESS_TIMEOUT_MS=50,
        app=SimpleNamespace(logger=logging.getLogger("ctx-retry")),
        random=_FakeRandom([0.01]),
    )

    policy = retry_module.build_retry_policy(ctx)

    assert policy._config.max_attempts == 4
    assert policy._config.base_delay_s == 0.01
    assert policy._config.max_delay_s == 0.08
    assert policy._deadline is not None
    assert round(policy._deadline.deadline_at, 3) == 100.05
    assert policy._random is ctx.random
