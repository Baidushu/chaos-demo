import os
import threading

import pytest
import redis

import app as app_module


pytestmark = pytest.mark.integration


def _build_real_redis_client():
    url = os.getenv("TEST_REDIS_URL", "").strip()
    if url:
        client = redis.from_url(url, decode_responses=True)
    else:
        client = redis.Redis(
            host=os.getenv("TEST_REDIS_HOST", "127.0.0.1"),
            port=int(os.getenv("TEST_REDIS_PORT", "6379")),
            db=int(os.getenv("TEST_REDIS_DB", "15")),
            decode_responses=True,
        )
    try:
        client.ping()
    except redis.RedisError as e:
        pytest.skip(f"real redis not available: {e}")
    return client


@pytest.fixture
def real_redis_state():
    client = _build_real_redis_client()
    old_client = app_module.redis_client
    old_rate_limit = app_module.RATE_LIMIT_PER_SEC
    old_algorithm = app_module.RATE_LIMIT_ALGORITHM
    old_busy = app_module.INVENTORY_BUSY_PROB
    old_wait_timeout = app_module.IDEM_WAIT_TIMEOUT_MS
    client.flushdb()
    app_module.redis_client = client
    app_module.RATE_LIMIT_PER_SEC = 2
    app_module.RATE_LIMIT_ALGORITHM = "sliding"
    app_module.INVENTORY_BUSY_PROB = 0.0
    app_module.IDEM_WAIT_TIMEOUT_MS = 300
    try:
        yield app_module
    finally:
        client.flushdb()
        app_module.redis_client = old_client
        app_module.RATE_LIMIT_PER_SEC = old_rate_limit
        app_module.RATE_LIMIT_ALGORITHM = old_algorithm
        app_module.INVENTORY_BUSY_PROB = old_busy
        app_module.IDEM_WAIT_TIMEOUT_MS = old_wait_timeout


def test_real_redis_sliding_window_rejects(real_redis_state):
    app_module.redis_client.flushdb()
    assert app_module.allow_request_by_rate_limit("127.0.0.1")
    assert app_module.allow_request_by_rate_limit("127.0.0.1")
    assert not app_module.allow_request_by_rate_limit("127.0.0.1")


def test_real_redis_concurrent_idempotency_no_duplicate(real_redis_state, monkeypatch):
    monkeypatch.setattr(real_redis_state.random, "uniform", lambda a, b: 0.03)
    monkeypatch.setattr(real_redis_state.random, "random", lambda: 1.0)
    # 本机 Docker-Windows 网络路径慢（实测单请求 ~52ms），默认 45ms 业务预算
    # 会误触发 timeout-protected 202；本用例关注幂等语义而非超时保护，
    # 放宽预算让断言聚焦「并发同 key → 201 + 200 且 order_id 一致」。
    monkeypatch.setattr(real_redis_state, "BUSINESS_TIMEOUT_MS", 1000)

    results = []
    errors = []
    headers = {"X-Idempotency-Key": "real-redis-same-key"}
    start_barrier = threading.Barrier(2)

    def worker():
        try:
            with real_redis_state.app.test_client() as client:
                start_barrier.wait(timeout=1.0)
                resp = client.post("/order", json={"item_id": "sku-real", "quantity": 1}, headers=headers)
                results.append((resp.status_code, resp.get_json()))
        except Exception as e:
            errors.append(e)

    t1 = threading.Thread(target=worker)
    t2 = threading.Thread(target=worker)
    t1.start(); t2.start(); t1.join(); t2.join()

    assert not errors
    assert sorted(status for status, _ in results) == [200, 201]
    order_ids = [body["order_id"] for _, body in results]
    assert len(set(order_ids)) == 1
