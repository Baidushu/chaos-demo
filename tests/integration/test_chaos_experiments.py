import threading
import time

from chaos_service import fault_injection


def test_create_experiment(client):
    resp = client.post(
        "/chaos/experiments",
        json={
            "name": "order_latency_test",
            "hypothesis": "order service remains available under request latency",
            "target": {"endpoint": "/order", "method": "POST", "phase": "pre_request"},
            "fault_type": "latency",
            "params": {"latency_ms": 30},
            "duration": 30,
        },
    )

    assert resp.status_code == 201
    experiment = resp.get_json()["experiment"]
    assert experiment["name"] == "order_latency_test"
    assert experiment["fault_type"] == "latency"

    listed = client.get("/chaos/experiments")
    body = listed.get_json()
    assert body["count"] == 1
    assert body["experiments"][0]["id"] == experiment["id"]


def test_target_match(stable_order_env, client):
    create = client.post(
        "/chaos/experiments",
        json={
            "name": "other_endpoint_exception",
            "hypothesis": "non-order endpoint should not affect order",
            "target": {"endpoint": "/other", "method": "POST", "phase": "service"},
            "fault_type": "exception",
            "params": {"error_type": "RuntimeError"},
            "duration": 30,
        },
    )
    assert create.status_code == 201

    resp = client.post("/order", json={"item_id": "sku-target", "quantity": 1})
    assert resp.status_code == 201


def test_latency_injector(stable_order_env, client):
    resp = client.post(
        "/chaos/experiments",
        json={
            "name": "order_latency",
            "hypothesis": "order path tolerates request latency",
            "target": {"endpoint": "/order", "method": "POST", "phase": "pre_request"},
            "fault_type": "latency",
            "params": {"latency_ms": 120},
            "duration": 30,
        },
    )
    assert resp.status_code == 201

    t0 = time.perf_counter()
    order = client.post("/order", json={"item_id": "sku-latency", "quantity": 1})
    elapsed_ms = (time.perf_counter() - t0) * 1000.0

    assert order.status_code == 201
    assert elapsed_ms >= 100.0


def test_exception_injector(stable_order_env, client):
    resp = client.post(
        "/chaos/experiments",
        json={
            "name": "order_exception",
            "hypothesis": "order path surfaces injected exception",
            "target": {"endpoint": "/order", "method": "POST", "phase": "service"},
            "fault_type": "exception",
            "params": {"error_type": "RuntimeError"},
            "duration": 30,
        },
    )
    experiment_id = resp.get_json()["experiment"]["id"]

    order = client.post("/order", json={"item_id": "sku-exc", "quantity": 1})
    body = order.get_json()

    assert order.status_code == 500
    assert body["fault"] is True
    assert body["experiment_id"] == experiment_id


def test_experiment_auto_recover(app_state, client):
    resp = client.post(
        "/chaos/experiments",
        json={
            "name": "short_latency",
            "hypothesis": "short experiment auto-recovers",
            "target": {"endpoint": "/order", "method": "POST", "phase": "pre_request"},
            "fault_type": "latency",
            "params": {"latency_ms": 10},
            "duration": 1,
        },
    )
    experiment_id = resp.get_json()["experiment"]["id"]
    app_state.redis_client.expiry[f"chaos:experiment:{experiment_id}"] = time.time() - 1

    listed = client.get("/chaos/experiments")
    assert listed.get_json()["count"] == 0

    report = fault_injection.get_report(app_state, experiment_id)
    assert report is not None
    assert report["recovered"] is True


def test_chaos_breaker_integration(app_state, client, monkeypatch):
    app_state.RATE_LIMIT_PER_SEC = 1000
    app_state.INVENTORY_BUSY_PROB = 0.0
    app_state.MIN_REQUEST_AMOUNT = 3
    app_state.BREAKER_FAILURE_RATE_THRESHOLD = 0.5
    app_state.BREAKER_OPEN_SEC = 30
    app_state.BREAKER_WINDOW_SEC = 60
    app_state.BUSINESS_TIMEOUT_MS = 999
    monkeypatch.setattr(app_state.random, "uniform", lambda _a, _b: 0.0)
    monkeypatch.setattr(app_state.random, "random", lambda: 1.0)

    created = client.post(
        "/chaos/experiments",
        json={
            "name": "breaker_exception",
            "hypothesis": "service failures should open breaker",
            "target": {"endpoint": "/order", "method": "POST", "phase": "service"},
            "fault_type": "exception",
            "params": {"error_type": "RuntimeError"},
            "duration": 30,
        },
    )
    assert created.status_code == 201

    for _ in range(3):
        resp = client.post("/order", json={"item_id": "sku-breaker", "quantity": 1})
        assert resp.status_code == 500

    final = client.post("/order", json={"item_id": "sku-breaker-final", "quantity": 1})
    assert final.status_code == 202
    assert final.get_json()["reason"] == "circuit open"


def test_chaos_retry_integration(app_state, client, monkeypatch):
    app_state.RATE_LIMIT_PER_SEC = 1000
    app_state.INVENTORY_BUSY_PROB = 0.0
    app_state.BUSINESS_TIMEOUT_MS = 999
    app_state.RETRY_MAX_ATTEMPTS = 3
    monkeypatch.setattr(app_state.random, "uniform", lambda _a, _b: 0.0)

    sequence = iter([1.0, 0.0, 1.0])
    monkeypatch.setattr(app_state.random, "random", lambda: next(sequence))

    created = client.post(
        "/chaos/experiments",
        json={
            "name": "retry_timeout",
            "hypothesis": "redis timeout should be retried and recover",
            "target": {
                "endpoint": "/order",
                "method": "POST",
                "phase": "store",
                "operation": "order_store_set",
            },
            "fault_type": "slow_db",
            "params": {"base_ms": 0, "jitter_ms": 0, "timeout_rate": 0.5},
            "duration": 30,
        },
    )
    assert created.status_code == 201

    resp = client.post("/order", json={"item_id": "sku-retry-chaos", "quantity": 1})
    assert resp.status_code == 201
    assert resp.get_json()["status"] == "ok"


def test_chaos_experiment_factory_fixture(chaos_experiment_factory):
    experiment = chaos_experiment_factory(
        name="fixture-experiment",
        fault_type="latency",
        params={"latency_ms": 15},
    )
    assert experiment.name == "fixture-experiment"
    assert experiment.fault_type == "latency"


def test_concurrent_experiment(app_state):
    results = []
    errors = []
    barrier = threading.Barrier(10)

    def worker(index: int):
        try:
            barrier.wait(timeout=1.0)
            experiment = fault_injection.create_experiment(
                app_state,
                name=f"concurrent-{index}",
                hypothesis="concurrent create remains isolated",
                target={"endpoint": "/order", "method": "POST", "phase": "pre_request"},
                fault_type="latency",
                params={"latency_ms": 5},
                duration=30,
            )
            results.append(experiment.id)
        except Exception as exc:  # pragma: no cover
            errors.append(exc)

    threads = [threading.Thread(target=worker, args=(idx,)) for idx in range(10)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join()

    assert not errors
    assert len(results) == 10
    assert len(set(results)) == 10
    assert len(fault_injection.list_experiments(app_state)) == 10
