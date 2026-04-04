import app as app_module


class FakeRedis:
    def __init__(self):
        self.store = {}
        self.counters = {}

    def ping(self):
        return True

    def get(self, key):
        return self.store.get(key)

    def setex(self, key, _seconds, value):
        self.store[key] = value

    def incr(self, key):
        self.counters[key] = self.counters.get(key, 0) + 1
        return self.counters[key]

    def expire(self, _key, _seconds):
        return True


def setup_function():
    app_module.orders.clear()
    app_module.breaker_failures.clear()
    app_module.breaker_open_until = 0.0
    app_module.redis_client = FakeRedis()
    app_module.ENABLE_RESILIENCE = True
    app_module.RATE_LIMIT_PER_SEC = 80


def test_create_order_success():
    client = app_module.app.test_client()
    resp = client.post("/order", json={"item_id": "sku-1", "quantity": 1})
    assert resp.status_code in (201, 202)


def test_idempotency_returns_same_order():
    client = app_module.app.test_client()
    headers = {"X-Idempotency-Key": "same-key"}

    first = client.post("/order", json={"item_id": "sku-2", "quantity": 1}, headers=headers)
    second = client.post("/order", json={"item_id": "sku-2", "quantity": 1}, headers=headers)

    assert first.status_code in (201, 202)
    if first.status_code == 201:
        assert second.status_code == 200
        assert first.get_json()["order_id"] == second.get_json()["order_id"]


def test_rate_limit_can_reject():
    app_module.RATE_LIMIT_PER_SEC = 2
    client = app_module.app.test_client()
    statuses = []
    for _ in range(6):
        resp = client.post("/order", json={"item_id": "sku-3", "quantity": 1})
        statuses.append(resp.status_code)
    assert 429 in statuses


def test_healthz():
    client = app_module.app.test_client()
    resp = client.get("/healthz")
    body = resp.get_json()
    assert resp.status_code == 200
    assert "redis" in body
    assert "resilience" in body
