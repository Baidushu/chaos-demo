from __future__ import annotations

import threading
import time
from collections.abc import Callable, Iterator
from pathlib import Path
from types import SimpleNamespace

import pytest
import redis

import app as app_module
from chaos_service import fault_injection, rate_limiter
from chaos_service.resilience import build_circuit_breaker

try:  # ai_platform 为可选依赖时测试仍可收集
    from ai_platform.llm.config import isolate_repo_env_for_tests
except Exception:  # pragma: no cover - 依赖缺失时跳过隔离
    isolate_repo_env_for_tests = None


@pytest.fixture(autouse=True)
def _isolate_repo_env(monkeypatch):
    """隔离本地环境里的真实 LLM 凭据，保证测试确定性。

    1) 仓库根 .env 的 LLM_GATEWAY_*（DeepSeek key 等）不得污染
       断言 legacy 变量/YAML 默认值的测试；
    2) 遗留 llm_client 的 LLM_API_KEY / LLM_BACKEND 等（可能来自
       local_llm_env.ps1 或会话环境变量）同理——否则「无 key 应报错」
       类测试在配了真 key 的开发机上会 DID NOT RAISE。

    置空而非删除：dotenv/客户端按「falsy 走默认值」处理空串，
    测试内部仍可用 monkeypatch.setenv 覆盖。
    """
    if isolate_repo_env_for_tests is not None:
        isolate_repo_env_for_tests()
    # delenv 而非 setenv("")：llm_client 用 `os.getenv("LLM_BACKEND", "auto")`
    # 读默认值，变量「存在但为空」会让默认值不生效、跳过 auto 后端检测。
    for name in ("LLM_API_KEY", "LLM_BACKEND", "LLM_BASE_URL", "LLM_MODEL", "LLM_TIMEOUT_SEC"):
        monkeypatch.delenv(name, raising=False)
    yield


class FakeRedis:
    def __init__(self, broken: bool = False):
        self.store = {}
        self.counters = {}
        self.zsets = {}
        self.expiry = {}
        self._lock = threading.Lock()
        self.broken = broken

    def _ensure_available(self):
        if self.broken:
            raise redis.ConnectionError("fake redis unavailable")

    def _is_expired(self, key: str) -> bool:
        expire_at = self.expiry.get(key)
        return expire_at is not None and time.time() > expire_at

    def _cleanup_if_expired(self, key: str):
        if self._is_expired(key):
            self.store.pop(key, None)
            self.counters.pop(key, None)
            self.zsets.pop(key, None)
            self.expiry.pop(key, None)

    def ping(self):
        self._ensure_available()
        return True

    def get(self, key):
        self._ensure_available()
        with self._lock:
            self._cleanup_if_expired(key)
            return self.store.get(key)

    def setex(self, key, seconds, value):
        self._ensure_available()
        with self._lock:
            self.store[key] = value
            self.expiry[key] = time.time() + float(seconds)

    def set(self, name, value, ex=None, px=None, nx=False, xx=False, keepttl=False):
        self._ensure_available()
        with self._lock:
            self._cleanup_if_expired(name)
            exists = name in self.store
            if nx and exists:
                return None
            if xx and not exists:
                return None
            self.store[name] = value
            if ex is not None:
                self.expiry[name] = time.time() + float(ex)
            elif px is not None:
                self.expiry[name] = time.time() + float(px) / 1000.0
            return True

    def delete(self, *names):
        self._ensure_available()
        n = 0
        with self._lock:
            for k in names:
                if k in self.store:
                    self.store.pop(k, None)
                    self.expiry.pop(k, None)
                    n += 1
                if k in self.counters:
                    self.counters.pop(k, None)
                if k in self.zsets:
                    self.zsets.pop(k, None)
                    n += 1
        return n

    def zadd(self, name, mapping):
        self._ensure_available()
        with self._lock:
            z = self.zsets.setdefault(name, {})
            for m, s in mapping.items():
                z[m] = float(s)
            return len(mapping)

    def zremrangebyscore(self, name, min_v, max_v):
        self._ensure_available()
        mmin = float("-inf") if min_v == float("-inf") else float(min_v)
        mmax = float("inf") if max_v == float("inf") else float(max_v)
        with self._lock:
            z = self.zsets.get(name) or {}
            removed = 0
            for m in list(z.keys()):
                sc = z[m]
                if mmin <= sc <= mmax:
                    del z[m]
                    removed += 1
            return removed

    def zcard(self, name):
        self._ensure_available()
        with self._lock:
            return len(self.zsets.get(name) or {})

    def incr(self, key):
        self._ensure_available()
        with self._lock:
            self._cleanup_if_expired(key)
            self.counters[key] = self.counters.get(key, 0) + 1
            return self.counters[key]

    def expire(self, key, seconds):
        self._ensure_available()
        with self._lock:
            if key not in self.store and key not in self.counters and key not in self.zsets:
                return False
            self.expiry[key] = time.time() + float(seconds)
            return True

    def keys(self, pattern="*"):
        self._ensure_available()
        with self._lock:
            import fnmatch

            result = []
            all_keys = set(self.store.keys()) | set(self.counters.keys()) | set(self.zsets.keys())
            for k in all_keys:
                self._cleanup_if_expired(k)
                if k in self.store or k in self.counters or k in self.zsets:
                    if fnmatch.fnmatch(k, pattern):
                        result.append(k)
            return result

    def rate_limit_sliding_allow(self, key, now, window, limit, member, ttl):
        self._ensure_available()
        with self._lock:
            self._cleanup_if_expired(key)
            z = self.zsets.setdefault(key, {})
            cutoff = now - window
            for m in list(z.keys()):
                if z[m] <= cutoff:
                    del z[m]
            lim = max(int(limit), 0)
            if len(z) >= lim:
                return False
            z[member] = now
            self.expiry[key] = time.time() + float(ttl)
            return True

    def register_script(self, _lua):
        lua = str(_lua or "")

        def _runner(keys=None, args=None):
            self._ensure_available()
            keys = keys or []
            args = args or []
            if not keys:
                return 0
            if (
                len(keys) == 3
                and len(args) >= 9
                and "ZREMRANGEBYSCORE" in lua
                and "ZCARD" in lua
                and "ZADD" in lua
            ):
                failures_key = keys[0]
                totals_key = keys[1]
                open_until_key = keys[2]
                action = args[0]
                now = float(args[1])
                window = float(args[2])
                ttl = int(args[3])
                min_request_count = int(args[4])
                failure_rate_threshold = float(args[5])
                open_timeout = float(args[6])
                total_member = args[7]
                failure_member = args[8]

                with self._lock:
                    self._cleanup_if_expired(failures_key)
                    self._cleanup_if_expired(totals_key)
                    failures = self.zsets.setdefault(failures_key, {})
                    totals = self.zsets.setdefault(totals_key, {})
                    cutoff = now - window
                    for member in list(failures.keys()):
                        if failures[member] <= cutoff:
                            del failures[member]
                    for member in list(totals.keys()):
                        if totals[member] <= cutoff:
                            del totals[member]

                    totals[total_member] = now
                    self.expiry[totals_key] = time.time() + float(ttl)
                    if action == "failure":
                        failures[failure_member] = now
                        self.expiry[failures_key] = time.time() + float(ttl)

                    failure_count = len(failures)
                    total_count = len(totals)
                    failure_rate = (failure_count / total_count) if total_count else 0.0

                    raw_open_until = self.store.get(open_until_key)
                    current_open_until = float(raw_open_until) if raw_open_until else 0.0
                    if (
                        total_count >= min_request_count
                        and failure_rate >= failure_rate_threshold
                        and current_open_until <= now
                    ):
                        next_open_until = now + open_timeout
                        self.store[open_until_key] = str(next_open_until)
                        return [1, failure_count, total_count, failure_rate, next_open_until]
                    return [0, failure_count, total_count, failure_rate, current_open_until]

            key = keys[0]
            if "ZREMRANGEBYSCORE" in lua and "ZCARD" in lua and "ZADD" in lua:
                now = float(args[0])
                window = float(args[1])
                limit = int(args[2])
                member = args[3]
                ttl = int(args[4])
                return (
                    1 if self.rate_limit_sliding_allow(key, now, window, limit, member, ttl) else 0
                )
            if "INCR" in lua and "EXPIRE" in lua:
                ttl = int(args[0]) if args else 0
                with self._lock:
                    self._cleanup_if_expired(key)
                    self.counters[key] = self.counters.get(key, 0) + 1
                    current = self.counters[key]
                    if current == 1:
                        self.expiry[key] = time.time() + float(ttl)
                    return current

            expected = args[0] if args else None
            with self._lock:
                self._cleanup_if_expired(key)
                if self.store.get(key) != expected:
                    return 0
                self.store.pop(key, None)
                self.expiry.pop(key, None)
                return 1

        return _runner


class FlakyRedis(FakeRedis):
    def __init__(self, failures: dict[str, int] | None = None, broken: bool = False):
        super().__init__(broken=broken)
        self.failures = failures or {}

    def _maybe_fail(self, operation: str):
        remaining = int(self.failures.get(operation, 0))
        if remaining > 0:
            self.failures[operation] = remaining - 1
            raise redis.ConnectionError(f"transient failure on {operation}")

    def get(self, key):
        self._maybe_fail("get")
        return super().get(key)

    def setex(self, key, seconds, value):
        self._maybe_fail("setex")
        return super().setex(key, seconds, value)

    def set(self, name, value, ex=None, px=None, nx=False, xx=False, keepttl=False):
        self._maybe_fail("set")
        return super().set(name, value, ex=ex, px=px, nx=nx, xx=xx, keepttl=keepttl)

    def delete(self, *names):
        self._maybe_fail("delete")
        return super().delete(*names)

    def incr(self, key):
        self._maybe_fail("incr")
        return super().incr(key)

    def expire(self, key, seconds):
        self._maybe_fail("expire")
        return super().expire(key, seconds)

    def rate_limit_sliding_allow(self, key, now, window, limit, member, ttl):
        self._maybe_fail("rate_limit_sliding_allow")
        return super().rate_limit_sliding_allow(key, now, window, limit, member, ttl)


@pytest.fixture(scope="session")
def test_config_defaults() -> dict[str, object]:
    return {
        "ENABLE_RESILIENCE": True,
        "RATE_LIMIT_PER_SEC": 80,
        "RATE_LIMIT_ALGORITHM": "sliding",
        "BUSINESS_TIMEOUT_MS": 45,
        "INVENTORY_BUSY_PROB": 0.03,
        "ORDER_TTL_SEC": 604800,
        "IDEM_TTL_SEC": 300,
        "IDEM_PENDING_TTL_SEC": 15,
        "IDEM_WAIT_TIMEOUT_MS": 120,
        "IDEM_WAIT_POLL_MS": 10,
        "RETRY_MAX_ATTEMPTS": 3,
        "RETRY_BASE_DELAY_MS": 5.0,
        "RETRY_MAX_DELAY_MS": 50.0,
        "FAULT_INJECTION_ENABLED": True,
        "FAULT_DEFAULT_TTL_SEC": 60,
        "FAULT_MAX_LATENCY_MS": 5000,
        "FAULT_MAX_DROP_RATE": 1.0,
        "CIRCUIT_PROBE_TTL_SEC": 30,
        "BREAKER_FAILURE_RATE_THRESHOLD": 0.5,
        "BREAKER_RESOURCE": "order",
        "MIN_REQUEST_AMOUNT": 100,
    }


@pytest.fixture
def fake_redis() -> Iterator[FakeRedis]:
    client = FakeRedis()
    try:
        yield client
    finally:
        keys = client.keys("*")
        if keys:
            client.delete(*keys)
        client.expiry.clear()


@pytest.fixture
def flaky_redis_factory() -> Callable[[dict[str, int] | None, bool], FlakyRedis]:
    def _factory(failures: dict[str, int] | None = None, broken: bool = False) -> FlakyRedis:
        return FlakyRedis(failures=failures, broken=broken)

    return _factory


@pytest.fixture
def app_state(
    fake_redis: FakeRedis,
    test_config_defaults: dict[str, object],
) -> Iterator[object]:
    previous_state = {
        "redis_client": getattr(app_module, "redis_client", None),
        **{name: getattr(app_module, name, None) for name in test_config_defaults},
    }

    app_module.redis_client = fake_redis
    for name, value in test_config_defaults.items():
        setattr(app_module, name, value)

    try:
        yield app_module
    finally:
        keys = fake_redis.keys("*")
        if keys:
            fake_redis.delete(*keys)
        for name, value in previous_state.items():
            setattr(app_module, name, value)


@pytest.fixture
def client(app_state) -> Iterator[object]:
    with app_state.app.test_client() as test_client:
        yield test_client


@pytest.fixture
def stable_order_env(app_state, monkeypatch):
    app_state.INVENTORY_BUSY_PROB = 0.0
    app_state.BUSINESS_TIMEOUT_MS = 999
    app_state.RATE_LIMIT_PER_SEC = 1000
    monkeypatch.setattr(app_state.random, "uniform", lambda _a, _b: 0.01)
    monkeypatch.setattr(app_state.random, "random", lambda: 1.0)
    return app_state


@pytest.fixture
def breaker_factory(app_state, fake_redis: FakeRedis):
    def _factory(**overrides):
        for name, value in overrides.items():
            setattr(app_state, name, value)
        fake_redis.delete(
            app_state.CB_KEY_OPEN_UNTIL,
            app_state.CB_KEY_FAILURES,
            app_state.CB_KEY_TOTAL_REQUESTS,
            app_state.CB_KEY_PROBE,
        )
        return build_circuit_breaker(app_state)

    return _factory


@pytest.fixture
def breaker(breaker_factory):
    return breaker_factory()


@pytest.fixture
def rate_limiter_backend(app_state, fake_redis: FakeRedis) -> rate_limiter.RedisBackend:
    return rate_limiter.RedisBackend(
        fake_redis,
        service_name=app_state.SERVICE_NAME,
        script_dir=Path(app_state.RATE_LIMIT_LUA_DIR),
    )


@pytest.fixture
def rate_limit_rule_factory():
    def _factory(
        *,
        resource: str = "order",
        algorithm: str = "sliding",
        limit: int = 1,
        window: float = 1.0,
        dimension: str = "client_ip",
    ) -> rate_limiter.RateLimitRule:
        return rate_limiter.RateLimitRule(
            resource=resource,
            algorithm=algorithm,
            limit=limit,
            window=window,
            dimension=dimension,
        )

    return _factory


@pytest.fixture
def fault_ctx(fake_redis: FakeRedis):
    return SimpleNamespace(
        redis_client=fake_redis,
        FAULT_INJECTION_ENABLED=True,
        FAULT_DEFAULT_TTL_SEC=60,
        FAULT_MAX_LATENCY_MS=5000,
        FAULT_MAX_DROP_RATE=1.0,
    )


@pytest.fixture
def request_context_factory(app_state):
    def _factory(
        *,
        path: str = "/order",
        method: str = "POST",
        request_id: str = "req-test",
        trace_id: str = "trace-test",
        user_id: str | None = None,
        started_at: float | None = None,
    ):
        started = time.time() if started_at is None else started_at
        request_obj = SimpleNamespace(
            path=path,
            method=method,
            headers={},
            remote_addr="127.0.0.1",
            _start_time=started,
        )
        return app_state.build_request_context(
            request_obj,
            request_id=request_id,
            trace_id=trace_id,
            user_id=user_id,
        )

    return _factory


@pytest.fixture
def chaos_experiment_factory(app_state):
    def _factory(**overrides):
        payload = {
            "name": "test-chaos-experiment",
            "hypothesis": "test hypothesis",
            "target": {"endpoint": "/order", "method": "POST", "phase": "pre_request"},
            "fault_type": "latency",
            "params": {"latency_ms": 10},
            "duration": 30,
        }
        payload.update(overrides)
        return fault_injection.create_experiment(app_state, **payload)

    return _factory


def pytest_collection_modifyitems(items) -> None:
    for item in items:
        path = Path(str(item.fspath))
        path_parts = {part.lower() for part in path.parts}
        stem = path.stem.lower()

        if "unit" in path_parts or path.parent.name == "tests":
            item.add_marker(pytest.mark.unit)
        elif "integration" in path_parts:
            item.add_marker(pytest.mark.integration)
        elif "e2e" in path_parts:
            item.add_marker(pytest.mark.e2e)

        if any(token in stem for token in ("chaos", "fault_injection", "perf_regression")):
            item.add_marker(pytest.mark.chaos)

        if any(
            token in stem
            for token in (
                "retry",
                "circuit_breaker",
                "rate_limiter",
                "fault_injection",
                "redis_integration",
            )
        ):
            item.add_marker(pytest.mark.resilience)

        if "redis" in stem:
            item.add_marker(pytest.mark.redis)

        if "perf" in stem:
            item.add_marker(pytest.mark.slow)
