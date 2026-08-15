import time

import pytest

from chaos_service import fault_injection


@pytest.mark.parametrize(
    ("fault_type", "params", "valid"),
    [
        ("latency", {"latency_ms": -1}, False),
        ("latency", {"latency_ms": 100}, True),
        ("latency", {"latency_ms": fault_injection.FAULT_MAX_LATENCY_MS + 1}, False),
        ("exception", {}, False),
        ("exception", {"error_type": "RuntimeError"}, True),
        ("drop", {"drop_rate": -0.1}, False),
        ("drop", {"drop_rate": 0.5}, True),
        ("drop", {"drop_rate": 1.1}, False),
        ("slow_db", {"base_ms": 50, "jitter_ms": 20, "timeout_rate": 0.1}, True),
        ("slow_db", {"base_ms": 50, "jitter_ms": 20, "timeout_rate": 1.5}, False),
        ("timeout", {"timeout_ms": 10}, False),
        ("network_error", {"drop_rate": 1.0}, False),
        ("unknown_type", {}, False),
    ],
)
def test_validate_fault_param_matrix(fault_type, params, valid):
    result = fault_injection._validate_fault_params(fault_type, params)
    if valid:
        assert result is None
    else:
        assert result


def test_build_fault_api_response():
    faults = [{"type": "latency", "params": {"latency_ms": 100}}]
    resp = fault_injection.build_fault_api_response(faults)
    assert resp["enabled"] == fault_injection.FAULT_INJECTION_ENABLED
    assert resp["active_faults"] == 1
    assert resp["faults"] == faults
    assert "defaults" in resp


def test_inject_and_get_fault(fake_redis):
    record = fault_injection.inject_fault(fake_redis, "latency", {"latency_ms": 200}, ttl_sec=30)
    assert record["type"] == "latency"
    assert record["params"]["latency_ms"] == 200
    assert record["ttl_sec"] == 30

    got = fault_injection.get_fault(fake_redis, "latency")
    assert got is not None
    assert got["params"]["latency_ms"] == 200


def test_inject_fault_invalid_params(fake_redis):
    with pytest.raises(ValueError, match="latency_ms must be >= 0"):
        fault_injection.inject_fault(fake_redis, "latency", {"latency_ms": -1})


def test_clear_fault(fake_redis):
    fault_injection.inject_fault(fake_redis, "drop", {"drop_rate": 0.5})
    assert fault_injection.get_fault(fake_redis, "drop") is not None

    existed = fault_injection.clear_fault(fake_redis, "drop")
    assert existed is True
    assert fault_injection.get_fault(fake_redis, "drop") is None


def test_clear_fault_not_exist(fake_redis):
    assert fault_injection.clear_fault(fake_redis, "latency") is False


def test_clear_all_faults(fake_redis):
    fault_injection.inject_fault(fake_redis, "latency", {"latency_ms": 100})
    fault_injection.inject_fault(fake_redis, "drop", {"drop_rate": 0.3})
    fault_injection.inject_fault(fake_redis, "exception", {"error_type": "RuntimeError"})

    count = fault_injection.clear_all_faults(fake_redis)
    assert count == 3
    assert fault_injection.list_faults(fake_redis) == []


def test_list_faults(fake_redis):
    fault_injection.inject_fault(fake_redis, "latency", {"latency_ms": 100})
    fault_injection.inject_fault(fake_redis, "drop", {"drop_rate": 0.3})

    faults = fault_injection.list_faults(fake_redis)
    types = {fault["type"] for fault in faults}
    assert types == {"latency", "drop"}


def test_fault_auto_expiry(fake_redis):
    fault_injection.inject_fault(fake_redis, "latency", {"latency_ms": 100}, ttl_sec=1)
    assert fault_injection.get_fault(fake_redis, "latency") is not None

    fake_redis.expiry["fault:latency"] = time.time() - 1
    assert fault_injection.get_fault(fake_redis, "latency") is None


@pytest.mark.parametrize(
    ("fault_type", "params", "expected_result"),
    [
        ("drop", {"drop_rate": 1.0}, "drop"),
        ("drop", {"drop_rate": 0.0}, "latency"),
        ("exception", {"error_type": "ValueError"}, "exception"),
    ],
)
def test_apply_faults_matrix(fake_redis, fault_ctx, fault_type, params, expected_result):
    fault_injection.inject_fault(fake_redis, fault_type, params)
    result = fault_injection.apply_faults(fault_ctx, None)
    assert result == expected_result


def test_apply_faults_no_faults(fault_ctx):
    result = fault_injection.apply_faults(fault_ctx, None)
    assert result is None


def test_apply_faults_disabled(fake_redis, fault_ctx):
    fault_injection.inject_fault(fake_redis, "drop", {"drop_rate": 1.0})
    original_global = fault_injection.FAULT_INJECTION_ENABLED
    original_ctx = fault_ctx.FAULT_INJECTION_ENABLED
    try:
        fault_injection.FAULT_INJECTION_ENABLED = False
        fault_ctx.FAULT_INJECTION_ENABLED = False
        result = fault_injection.apply_faults(fault_ctx, None)
        assert result is None
    finally:
        fault_injection.FAULT_INJECTION_ENABLED = original_global
        fault_ctx.FAULT_INJECTION_ENABLED = original_ctx


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
    client.post(
        "/fault/inject",
        json={"type": "drop", "params": {"drop_rate": 1.0}},
    )
    resp = client.get("/fault/status")
    assert resp.status_code == 200

    resp = client.post("/fault/clear-all")
    assert resp.status_code == 200


def test_fault_drop_affects_order_api(client, stable_order_env, monkeypatch):
    import chaos_service.fault_injection as fi

    monkeypatch.setattr(
        fi,
        "_random",
        type("R", (), {"random": lambda self: 0.0, "uniform": lambda self, a, b: 0.0})(),
    )

    client.post(
        "/fault/inject",
        json={"type": "drop", "params": {"drop_rate": 1.0}},
    )

    resp = client.post("/order", json={"item_id": "sku-1", "quantity": 1})
    assert resp.status_code == 503
    body = resp.get_json()
    assert body.get("fault") is True

    client.post("/fault/clear-all")
    monkeypatch.setattr(
        fi,
        "_random",
        type("R", (), {"random": lambda self: 1.0, "uniform": lambda self, a, b: 0.5})(),
    )
    resp = client.post("/order", json={"item_id": "sku-1", "quantity": 1})
    assert resp.status_code == 201


def test_fault_exception_affects_order_api(client, stable_order_env):
    client.post(
        "/fault/inject",
        json={"type": "exception", "params": {"error_type": "RuntimeError"}},
    )

    resp = client.post("/order", json={"item_id": "sku-1", "quantity": 1})
    assert resp.status_code == 500
