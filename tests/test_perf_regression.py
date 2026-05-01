"""性能回归断言：量化验证故障注入对延迟/错误率的影响。

测开要点：不仅要测功能正确，还要测性能符合预期。
这些断言确保故障注入"真的生效了"，恢复后"真的恢复了"。
"""

import pytest

from tests.conftest import FakeRedis


@pytest.mark.smoke
def test_latency_injection_increases_response_time(app_state, client, monkeypatch):
    """注入 200ms 延迟后，响应时间应明显增加。"""
    import chaos_service.fault_injection as fi

    app_state.INVENTORY_BUSY_PROB = 0.0
    app_state.BUSINESS_TIMEOUT_MS = 999
    monkeypatch.setattr(app_state.random, "uniform", lambda a, b: 0.01)
    monkeypatch.setattr(app_state.random, "random", lambda: 1.0)

    # 基线延迟
    import time
    durations = []
    for _ in range(5):
        t0 = time.perf_counter()
        client.post("/order", json={"item_id": "sku-perf-1", "quantity": 1})
        durations.append((time.perf_counter() - t0) * 1000)
    baseline_mean = sum(durations) / len(durations)

    # 注入 200ms 延迟
    monkeypatch.setattr(fi, "_random", type("R", (), {"random": lambda self: 0.0, "uniform": lambda self, a, b: 0.0})())
    fi.inject_fault(app_state.redis_client, "latency", {"latency_ms": 200}, ttl_sec=30)

    durations_injected = []
    for _ in range(5):
        t0 = time.perf_counter()
        client.post("/order", json={"item_id": "sku-perf-2", "quantity": 1})
        durations_injected.append((time.perf_counter() - t0) * 1000)
    injected_mean = sum(durations_injected) / len(durations_injected)

    fi.clear_all_faults(app_state.redis_client)

    # 注入后延迟应显著高于基线（至少多 100ms，考虑抖动）
    assert injected_mean > baseline_mean + 100, (
        f"Expected injected latency ({injected_mean:.1f}ms) > baseline ({baseline_mean:.1f}ms) + 100ms"
    )


def test_drop_injection_increases_error_rate(app_state, client, monkeypatch):
    """注入 100% 丢包后，所有请求应返回 503。"""
    import chaos_service.fault_injection as fi

    app_state.INVENTORY_BUSY_PROB = 0.0
    app_state.BUSINESS_TIMEOUT_MS = 999
    monkeypatch.setattr(app_state.random, "uniform", lambda a, b: 0.01)
    monkeypatch.setattr(app_state.random, "random", lambda: 1.0)

    # 注入 100% 丢包
    monkeypatch.setattr(fi, "_random", type("R", (), {"random": lambda self: 0.0, "uniform": lambda self, a, b: 0.0})())
    fi.inject_fault(app_state.redis_client, "drop", {"drop_rate": 1.0}, ttl_sec=30)

    errors = 0
    total = 10
    for _ in range(total):
        resp = client.post("/order", json={"item_id": "sku-drop", "quantity": 1})
        if resp.status_code == 503:
            errors += 1

    fi.clear_all_faults(app_state.redis_client)

    error_rate = errors / total
    assert error_rate >= 0.8, f"Expected error rate >= 80%, got {error_rate:.0%}"


def test_recovery_after_fault_clear(app_state, client, monkeypatch):
    """清除故障后，错误率应恢复正常。"""
    import chaos_service.fault_injection as fi

    app_state.INVENTORY_BUSY_PROB = 0.0
    app_state.BUSINESS_TIMEOUT_MS = 999
    monkeypatch.setattr(app_state.random, "uniform", lambda a, b: 0.01)
    monkeypatch.setattr(app_state.random, "random", lambda: 1.0)

    # 注入丢包
    monkeypatch.setattr(fi, "_random", type("R", (), {"random": lambda self: 0.0, "uniform": lambda self, a, b: 0.0})())
    fi.inject_fault(app_state.redis_client, "drop", {"drop_rate": 1.0}, ttl_sec=30)

    resp = client.post("/order", json={"item_id": "sku-rec-1", "quantity": 1})
    assert resp.status_code == 503

    # 清除故障
    fi.clear_all_faults(app_state.redis_client)
    monkeypatch.setattr(fi, "_random", type("R", (), {"random": lambda self: 1.0, "uniform": lambda self, a, b: 0.5})())

    # 恢复后应正常
    ok_count = 0
    for _ in range(10):
        resp = client.post("/order", json={"item_id": "sku-rec-2", "quantity": 1})
        if resp.status_code in (201, 200, 202):
            ok_count += 1

    assert ok_count >= 8, f"Expected >= 8 successful requests after recovery, got {ok_count}"


def test_circuit_breaker_opens_after_threshold_failures(app_state, client, monkeypatch):
    """连续失败达到阈值后，熔断器应打开，后续请求返回 202。"""
    app_state.INVENTORY_BUSY_PROB = 1.0  # 强制所有请求失败
    app_state.BREAKER_FAIL_THRESHOLD = 3
    app_state.BREAKER_WINDOW_SEC = 60
    app_state.BREAKER_OPEN_SEC = 30

    # 触发足够多的失败
    for _ in range(5):
        client.post("/order", json={"item_id": "sku-cb", "quantity": 1})

    # 熔断器打开后，请求应返回 202（queued）
    resp = client.post("/order", json={"item_id": "sku-cb-2", "quantity": 1})
    assert resp.status_code == 202
    body = resp.get_json()
    assert body.get("reason") == "circuit open"


def test_rate_limit_enforces_threshold(app_state, client):
    """限流应生效：超过阈值的请求返回 429。"""
    app_state.RATE_LIMIT_PER_SEC = 3
    app_state.RATE_LIMIT_ALGORITHM = "sliding"
    app_state.INVENTORY_BUSY_PROB = 0.0

    statuses = []
    for _ in range(10):
        resp = client.post("/order", json={"item_id": "sku-rl", "quantity": 1})
        statuses.append(resp.status_code)

    rate_limited = sum(1 for s in statuses if s == 429)
    assert rate_limited >= 1, f"Expected at least 1 rate-limited request, got {rate_limited}"
