import threading
import time

import pytest
import redis

import app as app_module


class FakeRedis:
    """Lightweight Redis test double with optional failures + TTL support."""

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
        """子集：支持 nx+ex，与 redis-py 行为一致（成功返回 True，未设返回 None）。"""
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
        """与 app 内 Lua 滑动窗口限流语义一致，供单测走 FakeRedis。"""
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

# 测试用例的初始化
#测试过程：
#1. 设置幂等性：设置幂等性
#2. 创建客户端：创建客户端
#3. 发送请求：发送请求
#4. 返回请求结果：返回请求结果
@pytest.fixture
def app_state():
    app_module.redis_client = FakeRedis()
    app_module.ENABLE_RESILIENCE = True
    app_module.RATE_LIMIT_PER_SEC = 80
    app_module.RATE_LIMIT_ALGORITHM = "sliding"
    app_module.BUSINESS_TIMEOUT_MS = 45
    app_module.INVENTORY_BUSY_PROB = 0.03
    app_module.ORDER_TTL_SEC = 604800
    app_module.IDEM_TTL_SEC = 300
    app_module.IDEM_PENDING_TTL_SEC = 15
    app_module.IDEM_WAIT_TIMEOUT_MS = 120
    app_module.IDEM_WAIT_POLL_MS = 10
    app_module.CIRCUIT_PROBE_TTL_SEC = 30
    return app_module

# 测试用例的初始化
@pytest.fixture
def client(app_state):
    return app_state.app.test_client()
