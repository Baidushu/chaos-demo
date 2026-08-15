import json
import threading
import time

import pytest

import app as app_module
from chaos_service import store as store_module
from tests.conftest import FakeRedis, FlakyRedis

# 单元：order_deadline_exceeded（不经 HTTP；实现见 chaos_service.resilience）
# 断言：budget_ms=50 时 elapsed_s + planned_s 相对毫秒预算的未超/已超边界
def test_order_deadline_exceeded_uses_end_to_end_budget():
    assert not app_module._order_deadline_exceeded(0, 0.01, 50)
    assert not app_module._order_deadline_exceeded(0, 0.05, 50)
    assert app_module._order_deadline_exceeded(0, 0.06, 50)
    assert app_module._order_deadline_exceeded(0.04, 0.02, 50)

# 冒烟：X-Request-Id 回显与自动生成（before_request）；先带脏值再不带头，断言规范化与新生成不串用
@pytest.mark.smoke
def test_x_request_id_echo_and_generated(client):
    r1 = client.get("/healthz", headers={"X-Request-Id": "  trace-abc-1  "})
    assert r1.headers.get("X-Request-Id") == "trace-abc-1"
    r2 = client.get("/healthz")
    assert r2.headers.get("X-Request-Id")
    assert "trace-abc-1" not in (r2.headers.get("X-Request-Id") or "")

# 冒烟：POST /order 主路径 201/202；INVENTORY_BUSY_PROB=0 避免烟测抖动
@pytest.mark.smoke
def test_create_order_success(app_state, client, monkeypatch):
    # 关随机库存 503，与契约用例「重试覆盖成功路径」分工
    app_state.INVENTORY_BUSY_PROB = 0.0
    app_state.BUSINESS_TIMEOUT_MS = 999
    app_state.RATE_LIMIT_PER_SEC = 1000
    monkeypatch.setattr(app_state.random, "uniform", lambda a, b: 0.01)
    monkeypatch.setattr(app_state.random, "random", lambda: 1.0)
    resp = client.post("/order", json={"item_id": "sku-1", "quantity": 1})
    assert resp.status_code == 201
    assert resp.get_json()["status"] == "ok"

# 行为：幂等重放——同 X-Idempotency-Key + 同 body 第二次应 200 且同 order_id（首次须 201）
def test_idempotency_returns_same_order(app_state, client, monkeypatch):
    app_state.INVENTORY_BUSY_PROB = 0.0
    app_state.BUSINESS_TIMEOUT_MS = 999
    app_state.RATE_LIMIT_PER_SEC = 1000
    monkeypatch.setattr(app_state.random, "uniform", lambda a, b: 0.01)
    monkeypatch.setattr(app_state.random, "random", lambda: 1.0)
    headers = {"X-Idempotency-Key": "same-key"}

    first = client.post("/order", json={"item_id": "sku-2", "quantity": 1}, headers=headers)
    second = client.post("/order", json={"item_id": "sku-2", "quantity": 1}, headers=headers)

    assert first.status_code == 201
    assert second.status_code == 200
    assert first.get_json()["order_id"] == second.get_json()["order_id"]
    record = store_module.load_idempotency_record(app_state, "same-key")
    assert record["state"] == store_module.IDEM_STATE_SUCCESS
    assert record["response_status"] == 201
    assert record["response_body"]["order_id"] == first.get_json()["order_id"]
    assert isinstance(record["timestamp"], int)

# 行为：幂等冲突——同 Key、不同 body 应 409；需稳定首请求（关随机忙、放宽截止）以免 release 预留后虚绿
def test_idempotency_key_conflict_returns_409(app_state, client):
    app_state.INVENTORY_BUSY_PROB = 0.0
    app_state.BUSINESS_TIMEOUT_MS = 999

    headers = {"X-Idempotency-Key": "same-key-conflict"}

    first = client.post("/order", json={"item_id": "sku-2", "quantity": 1}, headers=headers)
    assert first.status_code in (201, 202)

    second = client.post("/order", json={"item_id": "sku-2", "quantity": 2}, headers=headers)
    assert second.status_code == 409

# 兼容：Redis 中 idem: 值为纯字符串 order_id 时仍能 200 重放（旧数据形态）
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


def test_failed_idempotency_replays_saved_failure(app_state, client, monkeypatch):
    app_state.INVENTORY_BUSY_PROB = 1.0
    app_state.BUSINESS_TIMEOUT_MS = 999
    app_state.RATE_LIMIT_PER_SEC = 1000
    monkeypatch.setattr(app_state.random, "uniform", lambda a, b: 0.01)
    monkeypatch.setattr(app_state.random, "random", lambda: 0.0)
    headers = {"X-Idempotency-Key": "failed-key"}

    first = client.post("/order", json={"item_id": "sku-failed", "quantity": 1}, headers=headers)
    second = client.post("/order", json={"item_id": "sku-failed", "quantity": 1}, headers=headers)

    assert first.status_code == 503
    assert second.status_code == 503
    assert second.get_json()["error"] == "inventory busy"
    assert second.get_json()["idempotent"] is True
    record = store_module.load_idempotency_record(app_state, "failed-key")
    assert record["state"] == store_module.IDEM_STATE_FAILED
    assert record["response_status"] == 503
    assert record["response_body"]["error"] == "inventory busy"


def test_processing_timeout_returns_202_when_owner_still_running(app_state, monkeypatch):
    app_state.INVENTORY_BUSY_PROB = 0.0
    app_state.BUSINESS_TIMEOUT_MS = 999
    app_state.IDEM_WAIT_TIMEOUT_MS = 20
    app_state.IDEM_WAIT_POLL_MS = 5
    monkeypatch.setattr(app_state.random, "uniform", lambda a, b: 0.08)
    monkeypatch.setattr(app_state.random, "random", lambda: 1.0)

    headers = {"X-Idempotency-Key": "same-key-processing"}
    results = []
    errors = []
    start_barrier = threading.Barrier(2)

    def worker():
        try:
            with app_state.app.test_client() as local_client:
                start_barrier.wait(timeout=1.0)
                resp = local_client.post(
                    "/order", json={"item_id": "sku-processing", "quantity": 1}, headers=headers
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
    assert sorted(status for status, _ in results) == [201, 202]
    assert any(body.get("status") == "processing" for _, body in results)


def test_idempotency_release_uses_owner_token_safely(app_state):
    state, owner_record = store_module.reserve_idempotency_key(
        app_state,
        "safe-release-key",
        store_module.idem_payload_fingerprint("sku-safe", 1),
    )
    assert state == "owner"

    deleted = store_module.release_idempotency_reservation(
        app_state,
        "safe-release-key",
        {**owner_record, "_raw": owner_record["_raw"].replace(owner_record["owner_token"], "other-owner")},
    )
    assert deleted is False
    assert store_module.load_idempotency_record(app_state, "safe-release-key")["state"] == store_module.IDEM_STATE_PROCESSING

    deleted = store_module.release_idempotency_reservation(app_state, "safe-release-key", owner_record)
    assert deleted is True
    assert store_module.load_idempotency_record(app_state, "safe-release-key") is None


# 并发：同 Key 同 body 双线程——应仅一单，状态码为 200+201，order_id 唯一
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

# 限流：滑动窗口——压低阈值后连续 POST 应出现 429
def test_rate_limit_can_reject(app_state, client):
    app_state.RATE_LIMIT_PER_SEC = 2
    app_state.RATE_LIMIT_ALGORITHM = "sliding"
    statuses = []
    for _ in range(6):
        resp = client.post("/order", json={"item_id": "sku-3", "quantity": 1})
        statuses.append(resp.status_code)
    assert 429 in statuses


# 限流：固定窗口——同上，换算法与 sku 避免键冲突
def test_rate_limit_fixed_algorithm_still_rejects(app_state, client):
    app_state.RATE_LIMIT_PER_SEC = 2
    app_state.RATE_LIMIT_ALGORITHM = "fixed"
    statuses = []
    for _ in range(6):
        resp = client.post("/order", json={"item_id": "sku-3b", "quantity": 1})
        statuses.append(resp.status_code)
    assert 429 in statuses


def test_circuit_does_not_open_below_min_sample(app_state, client, monkeypatch):
    app_state.RATE_LIMIT_PER_SEC = 1000
    app_state.INVENTORY_BUSY_PROB = 1.0
    app_state.MIN_REQUEST_AMOUNT = 100
    app_state.BREAKER_FAILURE_RATE_THRESHOLD = 0.5
    app_state.BUSINESS_TIMEOUT_MS = 999
    monkeypatch.setattr(app_state.random, "uniform", lambda a, b: 0.0)
    monkeypatch.setattr(app_state.random, "random", lambda: 0.0)

    for _ in range(20):
        client.post("/order", json={"item_id": "sku-min", "quantity": 1})

    resp = client.post("/order", json={"item_id": "sku-min-2", "quantity": 1})
    assert resp.status_code == 503
    assert not app_state.redis_client.get(app_state.CB_KEY_OPEN_UNTIL)


def test_circuit_opens_by_failure_rate(app_state, client, monkeypatch):
    app_state.RATE_LIMIT_PER_SEC = 1000
    app_state.MIN_REQUEST_AMOUNT = 100
    app_state.BREAKER_FAILURE_RATE_THRESHOLD = 0.5
    app_state.BUSINESS_TIMEOUT_MS = 999
    monkeypatch.setattr(app_state.random, "uniform", lambda a, b: 0.0)
    monkeypatch.setattr(app_state.random, "random", lambda: 0.0)

    for i in range(100):
        app_state.INVENTORY_BUSY_PROB = 1.0 if i < 50 else 0.0
        client.post("/order", json={"item_id": f"sku-rate-{i}", "quantity": 1})

    resp = client.post("/order", json={"item_id": "sku-rate-final", "quantity": 1})
    assert resp.status_code == 202
    assert resp.get_json()["reason"] == "circuit open"


# 单元：FakeRedis 滑动窗口上限（不打 HTTP；与生产 Lua 语义对齐）
def test_fake_redis_sliding_window_enforces_cap():
    r = FakeRedis()
    t0 = 1_000_000.0
    assert r.rate_limit_sliding_allow("rl:sw:test", t0, 1.0, 2, "m1", 3)
    assert r.rate_limit_sliding_allow("rl:sw:test", t0 + 0.01, 1.0, 2, "m2", 3)
    assert not r.rate_limit_sliding_allow("rl:sw:test", t0 + 0.02, 1.0, 2, "m3", 3)
    assert r.rate_limit_sliding_allow("rl:sw:test", t0 + 1.5, 1.0, 2, "m4", 3)

# 冒烟：GET /healthz 综合健康；200 且 body 含 redis、resilience（与 /live、/ready 区分）
@pytest.mark.smoke
def test_healthz(client):
    resp = client.get("/healthz")
    body = resp.get_json()
    assert resp.status_code == 200
    assert "redis" in body
    assert "resilience" in body

# 参数化：非法 POST body → 统一期望 400
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


# 探针：Redis 不可用——/healthz 仍 200 但 status=degraded
def test_healthz_degraded_when_redis_unavailable(app_state, client):
    app_state.redis_client = FakeRedis(broken=True)
    resp = client.get("/healthz")
    body = resp.get_json()
    assert resp.status_code == 200
    assert body["status"] == "degraded"
    assert body["redis"] is False


# 探针：Redis 不可用——/live 仍 200（存活不检查强依赖）
def test_live_ok_even_when_redis_unavailable(app_state, client):
    app_state.redis_client = FakeRedis(broken=True)
    resp = client.get("/live")
    body = resp.get_json()
    assert resp.status_code == 200
    assert body["check"] == "liveness"
    assert body["status"] == "ok"


# 探针：Redis 可用——/ready 200 ready
def test_ready_ok_when_redis_available(client):
    resp = client.get("/ready")
    body = resp.get_json()
    assert resp.status_code == 200
    assert body["check"] == "readiness"
    assert body["status"] == "ready"
    assert body["redis"] is True


# 探针：Redis 不可用——/ready 503 not_ready
def test_ready_not_ready_when_redis_unavailable(app_state, client):
    app_state.redis_client = FakeRedis(broken=True)
    resp = client.get("/ready")
    body = resp.get_json()
    assert resp.status_code == 503
    assert body["check"] == "readiness"
    assert body["status"] == "not_ready"
    assert body["redis"] is False


# 韧性：Redis 不可用时限流 fail-open——多次 POST 不应仅因限流出现 429
def test_rate_limit_fails_open_when_redis_unavailable(app_state, client):
    app_state.RATE_LIMIT_PER_SEC = 1
    app_state.redis_client = FakeRedis(broken=True)

    statuses = []
    for _ in range(5):
        resp = client.post("/order", json={"item_id": "sku-4", "quantity": 1})
        statuses.append(resp.status_code)

    assert 429 not in statuses


def test_retry_recovers_transient_store_failure_without_changing_response(app_state, client, monkeypatch):
    flaky = FlakyRedis(failures={"setex": 1})
    app_state.redis_client = flaky
    app_state.INVENTORY_BUSY_PROB = 0.0
    app_state.BUSINESS_TIMEOUT_MS = 999
    monkeypatch.setattr(app_state.random, "uniform", lambda a, b: 0.0)
    monkeypatch.setattr(app_state.random, "random", lambda: 1.0)

    resp = client.post("/order", json={"item_id": "sku-retry-store", "quantity": 1})

    assert resp.status_code == 201
    assert resp.get_json()["status"] == "ok"


def test_retry_recovers_transient_rate_limit_failure(app_state, client, monkeypatch):
    app_state.redis_client = FlakyRedis(failures={"rate_limit_sliding_allow": 1})
    app_state.RATE_LIMIT_PER_SEC = 5
    app_state.INVENTORY_BUSY_PROB = 0.0
    app_state.BUSINESS_TIMEOUT_MS = 999
    monkeypatch.setattr(app_state.random, "uniform", lambda a, b: 0.01)
    monkeypatch.setattr(app_state.random, "random", lambda: 1.0)

    resp = client.post("/order", json={"item_id": "sku-retry-rl", "quantity": 1})

    assert resp.status_code == 201
    assert resp.get_json()["status"] == "ok"


# 熔断：半开探测成功——预置开路将过期 + monkeypatch 随机；期望 201 且关闸
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


# 熔断：半开探测失败——随机走库存忙；期望 503 且延长开路
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


# 熔断：探测进行中——预置 CB_KEY_PROBE；期望 202 不抢探针
def test_half_open_blocks_when_probe_in_flight(app_state, client):
    r = app_state.redis_client
    r.set(app_state.CB_KEY_OPEN_UNTIL, str(time.time() - 5.0))
    r.setex(app_state.CB_KEY_PROBE, 30, "1")

    resp = client.post("/order", json={"item_id": "sku-7", "quantity": 1})
    assert resp.status_code == 202


def _cb_get_open_until(r, app_state):
    """读断路器开路截止时间（秒），辅助熔断相关断言。"""
    raw = r.get(app_state.CB_KEY_OPEN_UNTIL)
    if not raw:
        return 0.0
    return float(raw)


# 出库：GET /order 响应字段白名单——存储含 internal 字段时不得出现在 JSON
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


# 行为：取消幂等——二次 cancel 第二次为 already_cancelled；建单非 201 则 skip
def test_cancel_order_is_idempotent(app_state, client, monkeypatch):
    app_state.INVENTORY_BUSY_PROB = 0.0
    app_state.BUSINESS_TIMEOUT_MS = 999
    app_state.RATE_LIMIT_PER_SEC = 1000
    monkeypatch.setattr(app_state.random, "uniform", lambda a, b: 0.01)
    monkeypatch.setattr(app_state.random, "random", lambda: 1.0)
    create = client.post("/order", json={"item_id": "sku-9", "quantity": 1})
    assert create.status_code == 201
    order_id = create.get_json()["order_id"]

    first = client.post(f"/order/{order_id}/cancel")
    second = client.post(f"/order/{order_id}/cancel")

    assert first.status_code == 200
    assert first.get_json().get("cancelled") is True
    assert second.status_code == 200
    assert second.get_json().get("already_cancelled") is True
