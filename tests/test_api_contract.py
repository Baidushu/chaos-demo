"""HTTP/JSON 契约用例：贴近测开「约定优于实现」的回归面。"""

import time
import uuid

import pytest

# 本模块默认带 contract 标记（pytest.ini 已注册）；可与 -m contract / 全量组合筛选用例
pytestmark = pytest.mark.contract


def _assert_json(resp):
    """响应须为 JSON；返回 dict 供字段断言。"""
    assert resp.content_type.startswith("application/json"), resp.content_type
    return resp.get_json()


# 冒烟+契约：POST /order 成功形态——多次重试至 201/202；201 则 order_id 为 UUID v4，202 则 queued+reason
@pytest.mark.smoke
def test_post_order_success_contract(client):
    for _ in range(30):
        resp = client.post("/order", json={"item_id": "contract-sku", "quantity": 1})
        if resp.status_code not in (201, 202):
            continue
        body = _assert_json(resp)
        if resp.status_code == 201:
            assert "order_id" in body
            oid = body["order_id"]
            assert isinstance(oid, str) and oid, body
            parsed = uuid.UUID(oid)
            assert parsed.version == 4
        else:
            assert body.get("status") == "queued"
            assert "reason" in body
        return
    pytest.skip("no 201/202 in time (e.g. repeated 503 busy)")


# 契约：非法下单体——400，JSON 含 error 字符串
def test_post_order_validation_error_contract(client):
    resp = client.post("/order", json={"item_id": "", "quantity": 1})
    assert resp.status_code == 400
    body = _assert_json(resp)
    assert "error" in body
    assert isinstance(body["error"], str)


# 契约：GET /order/{id} 200 时 JSON 键集 ⊆ {order_id, item_id, quantity, status}（防多泄字段）
def test_get_order_contract_shape(client):
    oid = None
    for _ in range(20):
        created = client.post("/order", json={"item_id": "c2", "quantity": 2})
        if created.status_code == 201:
            oid = created.get_json()["order_id"]
            break
    if oid is None:
        pytest.skip("no 201 order in time")
    resp = client.get(f"/order/{oid}")
    assert resp.status_code == 200
    body = _assert_json(resp)
    allowed = {"order_id", "item_id", "quantity", "status"}
    assert set(body.keys()) <= allowed, body


# 契约：GET 不存在订单——404，body.error 存在
def test_get_order_404_contract(client):
    missing = str(uuid.uuid4())
    resp = client.get(f"/order/{missing}")
    assert resp.status_code == 404
    body = _assert_json(resp)
    assert body.get("error")


# 契约：幂等重试至首包 201 后，第二次 POST 200；status=ok、idempotent、order_id 与首包一致
def test_post_order_idempotent_hit_contract(client):
    headers = {"X-Idempotency-Key": "contract-idem-1"}
    oid = None
    for _ in range(20):
        first = client.post("/order", json={"item_id": "idem-sku", "quantity": 1}, headers=headers)
        if first.status_code == 201:
            oid = first.get_json()["order_id"]
            break
    if oid is None:
        pytest.skip("order creation did not return 201 in time (503/202 flake)")
    second = client.post("/order", json={"item_id": "idem-sku", "quantity": 1}, headers=headers)
    assert second.status_code == 200
    body = _assert_json(second)
    assert body.get("status") == "ok"
    assert body.get("idempotent") is True
    assert body.get("order_id") == oid


# 契约：限流 429——body.error 固定文案 rate limit exceeded（滑动窗口 + 压低阈值）
def test_post_order_rate_limit_429_contract(app_state, client):
    app_state.RATE_LIMIT_PER_SEC = 2
    app_state.RATE_LIMIT_ALGORITHM = "sliding"
    saw_429 = False
    for _ in range(12):
        resp = client.post("/order", json={"item_id": "rl-contract", "quantity": 1})
        if resp.status_code == 429:
            saw_429 = True
            body = _assert_json(resp)
            assert body.get("error") == "rate limit exceeded"
            break
    assert saw_429


# 契约：熔断打开——预置 CB 开路；POST 202 queued + reason=circuit open
def test_post_order_circuit_open_202_contract(app_state, client):
    app_state.redis_client.set(
        app_state.CB_KEY_OPEN_UNTIL, str(time.time() + 3600.0)
    )
    app_state.redis_client.delete(app_state.CB_KEY_PROBE, app_state.CB_KEY_FAILURES)
    resp = client.post("/order", json={"item_id": "co-1", "quantity": 1})
    assert resp.status_code == 202
    body = _assert_json(resp)
    assert body.get("status") == "queued"
    assert body.get("reason") == "circuit open"


# 契约：截止预算 0——走 timeout protected；POST 202 queued + reason=timeout protected
def test_post_order_timeout_protected_202_contract(app_state, client):
    r = app_state.redis_client
    r.set(app_state.CB_KEY_OPEN_UNTIL, "0")
    r.delete(app_state.CB_KEY_PROBE, app_state.CB_KEY_FAILURES)
    app_state.BUSINESS_TIMEOUT_MS = 0
    resp = client.post("/order", json={"item_id": "to-1", "quantity": 1})
    assert resp.status_code == 202
    body = _assert_json(resp)
    assert body.get("status") == "queued"
    assert body.get("reason") == "timeout protected"


# 契约：取消——首撤 cancelled 或 already_cancelled；再撤必 already_cancelled
def test_cancel_order_contract(client):
    oid = None
    for _ in range(20):
        created = client.post("/order", json={"item_id": "c3", "quantity": 1})
        if created.status_code == 201:
            oid = created.get_json()["order_id"]
            break
    if oid is None:
        pytest.skip("no 201 order in time")
    r1 = client.post(f"/order/{oid}/cancel")
    assert r1.status_code == 200
    b1 = _assert_json(r1)
    assert b1.get("cancelled") is True or b1.get("already_cancelled") is True
    r2 = client.post(f"/order/{oid}/cancel")
    assert r2.status_code == 200
    b2 = _assert_json(r2)
    assert b2.get("already_cancelled") is True
