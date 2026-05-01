import time
from unittest.mock import patch

import pytest

import app as app_module
from chaos_service import fault_injection
from tests.conftest import FakeRedis


# ---- 单元测试：纯函数 ----


def test_validate_latency_negative():
    assert fault_injection._validate_fault_params("latency", {"latency_ms": -1})


def test_validate_latency_exceeds_max():
    assert fault_injection._validate_fault_params(
        "latency", {"latency_ms": fault_injection.FAULT_MAX_LATENCY_MS + 1}
    )


def test_validate_latency_valid():
    assert fault_injection._validate_fault_params("latency", {"latency_ms": 100}) is None


def test_validate_exception_missing_type():
    assert fault_injection._validate_fault_params("exception", {})


def test_validate_exception_valid():
    assert fault_injection._validate_fault_params(
        "exception", {"error_type": "RuntimeError"}
    ) is None


def test_validate_drop_negative_rate():
    assert fault_injection._validate_fault_params("drop", {"drop_rate": -0.1})


def test_validate_drop_rate_exceeds_max():
    assert fault_injection._validate_fault_params("drop", {"drop_rate": 1.1})


def test_validate_drop_valid():
    assert fault_injection._validate_fault_params("drop", {"drop_rate": 0.5}) is None


def test_validate_slow_db_valid():
    assert fault_injection._validate_fault_params(
        "slow_db", {"base_ms": 50, "jitter_ms": 20, "timeout_rate": 0.1}
    ) is None


def test_validate_slow_db_invalid_timeout_rate():
    assert fault_injection._validate_fault_params(
        "slow_db", {"base_ms": 50, "jitter_ms": 20, "timeout_rate": 1.5}
    )


def test_validate_unknown_type():
    assert fault_injection._validate_fault_params("unknown_type", {})


def test_build_fault_api_response():
    faults = [{"type": "latency", "params": {"latency_ms": 100}}]
    resp = fault_injection.build_fault_api_response(faults)
    assert resp["enabled"] == fault_injection.FAULT_INJECTION_ENABLED
    assert resp["active_faults"] == 1
    assert resp["faults"] == faults
    assert "defaults" in resp


# ---- 集成测试：FakeRedis ----


def test_inject_and_get_fault():
    r = FakeRedis()
    record = fault_injection.inject_fault(r, "latency", {"latency_ms": 200}, ttl_sec=30)
    assert record["type"] == "latency"
    assert record["params"]["latency_ms"] == 200
    assert record["ttl_sec"] == 30

    got = fault_injection.get_fault(r, "latency")
    assert got is not None
    assert got["params"]["latency_ms"] == 200


def test_inject_fault_invalid_params():
    r = FakeRedis()
    with pytest.raises(ValueError, match="latency_ms must be >= 0"):
        fault_injection.inject_fault(r, "latency", {"latency_ms": -1})


def test_clear_fault():
    r = FakeRedis()
    fault_injection.inject_fault(r, "drop", {"drop_rate": 0.5})
    assert fault_injection.get_fault(r, "drop") is not None

    existed = fault_injection.clear_fault(r, "drop")
    assert existed is True
    assert fault_injection.get_fault(r, "drop") is None


def test_clear_fault_not_exist():
    r = FakeRedis()
    assert fault_injection.clear_fault(r, "latency") is False


def test_clear_all_faults():
    r = FakeRedis()
    fault_injection.inject_fault(r, "latency", {"latency_ms": 100})
    fault_injection.inject_fault(r, "drop", {"drop_rate": 0.3})
    fault_injection.inject_fault(r, "exception", {"error_type": "RuntimeError"})

    count = fault_injection.clear_all_faults(r)
    assert count == 3
    assert fault_injection.list_faults(r) == []


def test_list_faults():
    r = FakeRedis()
    fault_injection.inject_fault(r, "latency", {"latency_ms": 100})
    fault_injection.inject_fault(r, "drop", {"drop_rate": 0.3})

    faults = fault_injection.list_faults(r)
    types = {f["type"] for f in faults}
    assert types == {"latency", "drop"}


def test_fault_auto_expiry():
    r = FakeRedis()
    fault_injection.inject_fault(r, "latency", {"latency_ms": 100}, ttl_sec=1)
    assert fault_injection.get_fault(r, "latency") is not None

    # FakeRedis 的 TTL 检查依赖 time.time()，直接清掉 expiry 模拟过期
    r.expiry["fault:latency"] = time.time() - 1
    assert fault_injection.get_fault(r, "latency") is None


# ---- apply_faults 测试 ----


def test_apply_faults_no_faults():
    r = FakeRedis()
    ctx = type("Ctx", (), {"redis_client": r})()
    result = fault_injection.apply_faults(ctx, None)
    assert result is None


def test_apply_faults_drop_always():
    r = FakeRedis()
    fault_injection.inject_fault(r, "drop", {"drop_rate": 1.0})
    ctx = type("Ctx", (), {"redis_client": r})()

    results = {fault_injection.apply_faults(ctx, None) for _ in range(10)}
    assert results == {"drop"}


def test_apply_faults_drop_never():
    r = FakeRedis()
    fault_injection.inject_fault(r, "drop", {"drop_rate": 0.0})
    ctx = type("Ctx", (), {"redis_client": r})()

    results = {fault_injection.apply_faults(ctx, None) for _ in range(10)}
    assert "drop" not in results


def test_apply_faults_exception():
    r = FakeRedis()
    fault_injection.inject_fault(r, "exception", {"error_type": "ValueError"})
    ctx = type("Ctx", (), {"redis_client": r})()

    result = fault_injection.apply_faults(ctx, None)
    assert result == "exception"


def test_apply_faults_disabled():
    r = FakeRedis()
    fault_injection.inject_fault(r, "drop", {"drop_rate": 1.0})
    ctx = type("Ctx", (), {"redis_client": r})()

    # 临时关闭开关
    original = fault_injection.FAULT_INJECTION_ENABLED
    try:
        fault_injection.FAULT_INJECTION_ENABLED = False
        result = fault_injection.apply_faults(ctx, None)
        assert result is None
    finally:
        fault_injection.FAULT_INJECTION_ENABLED = original


# ---- HTTP API 集成测试 ----


@pytest.fixture
def client(app_state):
    return app_state.app.test_client()


def test_fault_status_empty(client):
    resp = client.get("/fault/status")
    assert resp.status_code == 200
    body = resp.get_json()
    assert body["active_faults"] == 0
    assert body["faults"] == []


def test_fault_inject_and_status(client):
    resp = client.post(
        "/fault/inject",
        json={"type": "latency", "params": {"latency_ms": 200}, "ttl_sec": 60},
    )
    assert resp.status_code == 201
    body = resp.get_json()
    assert body["fault"]["type"] == "latency"

    resp = client.get("/fault/status")
    body = resp.get_json()
    assert body["active_faults"] == 1
    assert body["faults"][0]["type"] == "latency"


def test_fault_inject_invalid_type(client):
    resp = client.post("/fault/inject", json={"type": ""})
    assert resp.status_code == 400


def test_fault_inject_invalid_params(client):
    resp = client.post(
        "/fault/inject",
        json={"type": "latency", "params": {"latency_ms": -1}},
    )
    assert resp.status_code == 400


def test_fault_clear(client):
    client.post(
        "/fault/inject",
        json={"type": "drop", "params": {"drop_rate": 0.5}},
    )
    resp = client.post("/fault/clear", json={"type": "drop"})
    assert resp.status_code == 200
    assert resp.get_json()["existed"] is True


def test_fault_clear_not_exist(client):
    resp = client.post("/fault/clear", json={"type": "latency"})
    assert resp.status_code == 200
    assert resp.get_json()["existed"] is False


def test_fault_clear_all(client):
    client.post("/fault/inject", json={"type": "latency", "params": {"latency_ms": 100}})
    client.post("/fault/inject", json={"type": "drop", "params": {"drop_rate": 0.3}})

    resp = client.post("/fault/clear-all")
    assert resp.status_code == 200
    assert resp.get_json()["count"] == 2

    resp = client.get("/fault/status")
    assert resp.get_json()["active_faults"] == 0


def test_fault_delete_by_type(client):
    client.post(
        "/fault/inject",
        json={"type": "exception", "params": {"error_type": "RuntimeError"}},
    )
    resp = client.delete("/fault/inject/exception")
    assert resp.status_code == 200
    assert resp.get_json()["existed"] is True


def test_fault_api_not_affected_by_injected_faults(client):
    """故障注入 API 自身不应被故障影响。"""
    client.post(
        "/fault/inject",
        json={"type": "drop", "params": {"drop_rate": 1.0}},
    )
    # 故障注入 API 应该正常工作
    resp = client.get("/fault/status")
    assert resp.status_code == 200

    resp = client.post("/fault/clear-all")
    assert resp.status_code == 200


def test_fault_drop_affects_order_api(client, app_state, monkeypatch):
    """注入 drop 故障后，业务 API 应返回 503。"""
    app_state.INVENTORY_BUSY_PROB = 0.0
    app_state.BUSINESS_TIMEOUT_MS = 999
    monkeypatch.setattr(app_state.random, "uniform", lambda a, b: 0.01)
    monkeypatch.setattr(app_state.random, "random", lambda: 1.0)
    # 故障注入模块用的是自身的 _random，需要单独 patch
    import chaos_service.fault_injection as fi
    monkeypatch.setattr(fi, "_random", type("R", (), {"random": lambda self: 0.0, "uniform": lambda self, a, b: 0.0})())

    client.post(
        "/fault/inject",
        json={"type": "drop", "params": {"drop_rate": 1.0}},
    )

    resp = client.post("/order", json={"item_id": "sku-1", "quantity": 1})
    assert resp.status_code == 503
    body = resp.get_json()
    assert body.get("fault") is True

    # 清除后应恢复正常
    client.post("/fault/clear-all")
    monkeypatch.setattr(fi, "_random", type("R", (), {"random": lambda self: 1.0, "uniform": lambda self, a, b: 0.5})())
    resp = client.post("/order", json={"item_id": "sku-1", "quantity": 1})
    assert resp.status_code == 201


def test_fault_exception_affects_order_api(client, app_state):
    """注入 exception 故障后，业务 API 应返回 500。"""
    app_state.INVENTORY_BUSY_PROB = 0.0

    client.post(
        "/fault/inject",
        json={"type": "exception", "params": {"error_type": "RuntimeError"}},
    )

    resp = client.post("/order", json={"item_id": "sku-1", "quantity": 1})
    assert resp.status_code == 500
