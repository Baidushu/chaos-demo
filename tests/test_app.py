import json
import threading
import time

import pytest

import app as app_module
from conftest import FakeRedis


def test_order_deadline_exceeded_uses_end_to_end_budget():
    assert not app_module._order_deadline_exceeded(0, 0.01, 50)
    assert not app_module._order_deadline_exceeded(0, 0.05, 50)
    assert app_module._order_deadline_exceeded(0, 0.06, 50)
    assert app_module._order_deadline_exceeded(0.04, 0.02, 50)


@pytest.mark.smoke
def test_x_request_id_echo_and_generated(client):
    r1 = client.get("/healthz", headers={"X-Request-Id": "  trace-abc-1  "})
    assert r1.headers.get("X-Request-Id") == "trace-abc-1"
    r2 = client.get("/healthz")
    assert r2.headers.get("X-Request-Id")
    assert "trace-abc-1" not in (r2.headers.get("X-Request-Id") or "")

#创建订单成功测试，用于测试创建订单是否成功
#测试过程：
#1. 创建客户端：创建客户端
#2. 发送请求：发送请求
#3. 返回请求结果：返回请求结果
@pytest.mark.smoke
def test_create_order_success(app_state, client):
    # 避免库存随机 503 使烟测非确定（与契约用例中“成功路径重试”策略区分）
    app_state.INVENTORY_BUSY_PROB = 0.0
    resp = client.post("/order", json={"item_id": "sku-1", "quantity": 1})
    assert resp.status_code in (201, 202)

#幂等测试，用于测试幂等性
#测试过程：
#1. 创建客户端：创建客户端
#2. 发送请求：发送请求
#3. 返回请求结果：返回请求结果
def test_idempotency_returns_same_order(client):
    headers = {"X-Idempotency-Key": "same-key"}#幂等键，用于测试幂等性

    first = client.post("/order", json={"item_id": "sku-2", "quantity": 1}, headers=headers)
    second = client.post("/order", json={"item_id": "sku-2", "quantity": 1}, headers=headers)

    assert first.status_code in (201, 202)
    if first.status_code == 201:
        assert second.status_code == 200
        assert first.get_json()["order_id"] == second.get_json()["order_id"]


def test_idempotency_key_conflict_returns_409(app_state, client):
    # 避免库存 503 / 截止预算触发 202 时释放幂等预留，导致第二次被当成全新预订而得到 201（虚绿）
    app_state.INVENTORY_BUSY_PROB = 0.0
    app_state.BUSINESS_TIMEOUT_MS = 999

    headers = {"X-Idempotency-Key": "same-key-conflict"}

    first = client.post("/order", json={"item_id": "sku-2", "quantity": 1}, headers=headers)
    assert first.status_code in (201, 202)

    second = client.post("/order", json={"item_id": "sku-2", "quantity": 2}, headers=headers)
    assert second.status_code == 409


def test_legacy_plain_idempotency_value_still_replays(app_state, client):
    app_state.redis_client.setex("idem:legacy-key", 300, "OID-LEGACY")
    resp = client.post(
        "/order",
        json={"item_id": "sku-legacy", "quantity": 1},
        headers={"X-Idempotency-Key": "legacy-key"},
    )
    body = resp.get_json()
    assert resp.status_code == 200
    assert body["idempotent"] is True
    assert body["order_id"] == "OID-LEGACY"


def test_concurrent_same_idempotency_key_does_not_duplicate_order(app_state, monkeypatch):
    app_state.INVENTORY_BUSY_PROB = 0.0
    app_state.IDEM_WAIT_TIMEOUT_MS = 300
    monkeypatch.setattr(app_state.random, "uniform", lambda a, b: 0.03)
    monkeypatch.setattr(app_state.random, "random", lambda: 1.0)

    headers = {"X-Idempotency-Key": "same-key-concurrent"}
    results = []
    errors = []
    start_barrier = threading.Barrier(2)

    def worker():
        try:
            with app_state.app.test_client() as local_client:
                start_barrier.wait(timeout=1.0)
                resp = local_client.post(
                    "/order", json={"item_id": "sku-cc", "quantity": 1}, headers=headers
                )
                results.append((resp.status_code, resp.get_json()))
        except Exception as e:  # pragma: no cover - only used to surface thread failures
            errors.append(e)

    threads = [threading.Thread(target=worker) for _ in range(2)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()

    assert not errors
    assert len(results) == 2
    order_ids = [body.get("order_id") for _, body in results if body.get("order_id")]
    assert len(order_ids) == 2
    assert len(set(order_ids)) == 1
    assert sorted(status for status, _ in results) == [200, 201]

#限流测试，用于测试限流是否生效
#测试过程：
#1. 设置限流：设置限流
#2. 创建客户端：创建客户端
#3. 发送请求：发送请求
#4. 返回请求结果：返回请求结果
def test_rate_limit_can_reject(app_state, client):
    app_state.RATE_LIMIT_PER_SEC = 2#设置限流，用于测试限流是否生效
    app_state.RATE_LIMIT_ALGORITHM = "sliding"
    statuses = []
    for _ in range(6):
        resp = client.post("/order", json={"item_id": "sku-3", "quantity": 1})
        statuses.append(resp.status_code)
    assert 429 in statuses


def test_rate_limit_fixed_algorithm_still_rejects(app_state, client):
    app_state.RATE_LIMIT_PER_SEC = 2
    app_state.RATE_LIMIT_ALGORITHM = "fixed"
    statuses = []
    for _ in range(6):
        resp = client.post("/order", json={"item_id": "sku-3b", "quantity": 1})
        statuses.append(resp.status_code)
    assert 429 in statuses


def test_fake_redis_sliding_window_enforces_cap():
    r = FakeRedis()
    t0 = 1_000_000.0
    assert r.rate_limit_sliding_allow("rl:sw:test", t0, 1.0, 2, "m1", 3)
    assert r.rate_limit_sliding_allow("rl:sw:test", t0 + 0.01, 1.0, 2, "m2", 3)
    assert not r.rate_limit_sliding_allow("rl:sw:test", t0 + 0.02, 1.0, 2, "m3", 3)
    assert r.rate_limit_sliding_allow("rl:sw:test", t0 + 1.5, 1.0, 2, "m4", 3)

#健康检查测试，用于测试健康检查是否成功
#测试过程：
#1. 创建客户端：创建客户端
#2. 发送请求：发送请求
#3. 返回请求结果：返回请求结果
@pytest.mark.smoke
def test_healthz(client):
    resp = client.get("/healthz")
    body = resp.get_json()
    assert resp.status_code == 200
    assert "redis" in body
    assert "resilience" in body


@pytest.mark.parametrize(
    "payload",
    [
        {},
        {"item_id": "", "quantity": 1},
        {"item_id": "sku-1", "quantity": 0},
        {"item_id": "sku-1", "quantity": "bad"},
    ],
)
def test_create_order_invalid_payload_returns_400(client, payload):
    resp = client.post("/order", json=payload)
    assert resp.status_code == 400


def test_healthz_degraded_when_redis_unavailable(app_state, client):
    app_state.redis_client = FakeRedis(broken=True)
    resp = client.get("/healthz")
    body = resp.get_json()
    assert resp.status_code == 200
    assert body["status"] == "degraded"
    assert body["redis"] is False


def test_live_ok_even_when_redis_unavailable(app_state, client):
    app_state.redis_client = FakeRedis(broken=True)
    resp = client.get("/live")
    body = resp.get_json()
    assert resp.status_code == 200
    assert body["check"] == "liveness"
    assert body["status"] == "ok"


def test_ready_ok_when_redis_available(client):
    resp = client.get("/ready")
    body = resp.get_json()
    assert resp.status_code == 200
    assert body["check"] == "readiness"
    assert body["status"] == "ready"
    assert body["redis"] is True


def test_ready_not_ready_when_redis_unavailable(app_state, client):
    app_state.redis_client = FakeRedis(broken=True)
    resp = client.get("/ready")
    body = resp.get_json()
    assert resp.status_code == 503
    assert body["check"] == "readiness"
    assert body["status"] == "not_ready"
    assert body["redis"] is False


def test_rate_limit_fails_open_when_redis_unavailable(app_state, client):
    app_state.RATE_LIMIT_PER_SEC = 1
    app_state.redis_client = FakeRedis(broken=True)

    statuses = []
    for _ in range(5):
        resp = client.post("/order", json={"item_id": "sku-4", "quantity": 1})
        statuses.append(resp.status_code)

    # Redis 异常时当前实现是 fail-open，不会因为限流直接 429
    assert 429 not in statuses


def test_half_open_probe_success_closes_circuit(app_state, client, monkeypatch):
    r = app_state.redis_client
    r.set(app_state.CB_KEY_OPEN_UNTIL, str(time.time() - 10.0))
    r.delete(app_state.CB_KEY_PROBE, app_state.CB_KEY_FAILURES)
    app_state.BUSINESS_TIMEOUT_MS = 999
    monkeypatch.setattr(app_state.random, "uniform", lambda a, b: 0.01)
    monkeypatch.setattr(app_state.random, "random", lambda: 1.0)

    resp = client.post("/order", json={"item_id": "sku-5", "quantity": 1})
    assert resp.status_code == 201
    assert _cb_get_open_until(r, app_state) == 0.0
    assert r.get(app_state.CB_KEY_PROBE) is None


def test_half_open_probe_failure_reopens_circuit(app_state, client, monkeypatch):
    r = app_state.redis_client
    r.set(app_state.CB_KEY_OPEN_UNTIL, str(time.time() - 10.0))
    r.delete(app_state.CB_KEY_PROBE, app_state.CB_KEY_FAILURES)
    app_state.BUSINESS_TIMEOUT_MS = 999
    monkeypatch.setattr(app_state.random, "uniform", lambda a, b: 0.01)
    monkeypatch.setattr(app_state.random, "random", lambda: 0.0)

    resp = client.post("/order", json={"item_id": "sku-6", "quantity": 1})
    assert resp.status_code == 503
    assert float(r.get(app_state.CB_KEY_OPEN_UNTIL) or 0) > time.time()
    assert r.get(app_state.CB_KEY_PROBE) is None


def test_half_open_blocks_when_probe_in_flight(app_state, client):
    r = app_state.redis_client
    r.set(app_state.CB_KEY_OPEN_UNTIL, str(time.time() - 5.0))
    r.setex(app_state.CB_KEY_PROBE, 30, "1")

    resp = client.post("/order", json={"item_id": "sku-7", "quantity": 1})
    assert resp.status_code == 202


def _cb_get_open_until(r, app_state):
    raw = r.get(app_state.CB_KEY_OPEN_UNTIL)
    if not raw:
        return 0.0
    return float(raw)


def test_get_order_response_uses_whitelist(app_state, client):
    app_state.redis_client.setex(
        "order:OID-1",
        3600,
        json.dumps(
            {
                "item_id": "sku-8",
                "quantity": 2,
                "status": "created",
                "internal_note": "should_not_leak",
            }
        ),
    )
    resp = client.get("/order/OID-1")
    body = resp.get_json()
    assert resp.status_code == 200
    assert body["order_id"] == "OID-1"
    assert body["item_id"] == "sku-8"
    assert body["quantity"] == 2
    assert body["status"] == "created"
    assert "internal_note" not in body


def test_cancel_order_is_idempotent(client):
    create = client.post("/order", json={"item_id": "sku-9", "quantity": 1})
    if create.status_code != 201:
        pytest.skip("order creation degraded/limited in this run")
    order_id = create.get_json()["order_id"]

    first = client.post(f"/order/{order_id}/cancel")
    second = client.post(f"/order/{order_id}/cancel")

    assert first.status_code == 200
    assert first.get_json().get("cancelled") is True
    assert second.status_code == 200
    assert second.get_json().get("already_cancelled") is True
