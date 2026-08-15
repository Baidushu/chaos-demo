import threading
import time

import pytest

import app as app_module


def test_concurrent_sliding_window_rejects_above_limit(
    rate_limiter_backend, rate_limit_rule_factory
):
    rule = rate_limit_rule_factory(
        resource="order",
        algorithm="sliding",
        limit=3,
        window=1.0,
        dimension="client_ip",
    )

    results = []
    errors = []
    start_barrier = threading.Barrier(10)

    def worker():
        try:
            start_barrier.wait(timeout=1.0)
            results.append(rate_limiter_backend.allow(rule, "127.0.0.1").allowed)
        except Exception as exc:  # pragma: no cover - only used to surface thread failures
            errors.append(exc)

    threads = [threading.Thread(target=worker) for _ in range(10)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join()

    assert not errors
    assert sum(1 for allowed in results if allowed) == 3
    assert sum(1 for allowed in results if not allowed) == 7


def test_fixed_window_lua_sets_expiry_on_first_hit(
    fake_redis,
    rate_limiter_backend,
    rate_limit_rule_factory,
):
    rule = rate_limit_rule_factory(
        resource="order",
        algorithm="fixed",
        limit=2,
        window=1.0,
        dimension="client_ip",
    )

    decision = rate_limiter_backend.allow(rule, "user-1")

    assert decision.allowed is True
    keys = fake_redis.keys(f"{app_module.SERVICE_NAME}:rate:order:client_ip:user-1:*")
    assert len(keys) == 1
    key = keys[0]
    assert key in fake_redis.expiry
    assert fake_redis.expiry[key] > time.time()


def test_rate_limit_isolation_across_users(rate_limiter_backend, rate_limit_rule_factory):
    rule = rate_limit_rule_factory(
        resource="order",
        algorithm="sliding",
        limit=1,
        window=1.0,
        dimension="client_ip",
    )

    assert rate_limiter_backend.allow(rule, "user-a").allowed is True
    assert rate_limiter_backend.allow(rule, "user-b").allowed is True
    assert rate_limiter_backend.allow(rule, "user-a").allowed is False


def test_rate_limit_isolation_across_resources(rate_limiter_backend, rate_limit_rule_factory):
    order_rule = rate_limit_rule_factory(
        resource="order",
        algorithm="fixed",
        limit=1,
        window=1.0,
        dimension="client_ip",
    )
    inventory_rule = rate_limit_rule_factory(
        resource="inventory",
        algorithm="fixed",
        limit=1,
        window=1.0,
        dimension="client_ip",
    )

    assert rate_limiter_backend.allow(order_rule, "user-a").allowed is True
    assert rate_limiter_backend.allow(order_rule, "user-a").allowed is False
    assert rate_limiter_backend.allow(inventory_rule, "user-a").allowed is True


@pytest.mark.parametrize(
    ("algorithm", "limit", "expected"),
    [
        ("sliding", 0, [False]),
        ("sliding", 1, [True, False]),
        ("sliding", 2, [True, True, False]),
        ("fixed", 0, [False]),
        ("fixed", 1, [True, False]),
        ("fixed", 2, [True, True, False]),
    ],
)
def test_rate_limit_boundary_matrix(
    rate_limiter_backend,
    rate_limit_rule_factory,
    algorithm,
    limit,
    expected,
):
    rule = rate_limit_rule_factory(
        resource=f"boundary-{algorithm}-{limit}",
        algorithm=algorithm,
        limit=limit,
        window=1.0,
        dimension="client_ip",
    )

    decisions = [
        rate_limiter_backend.allow(rule, "user-boundary").allowed for _ in range(len(expected))
    ]

    assert decisions == expected
