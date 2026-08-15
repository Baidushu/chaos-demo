"""Redis-backed storage abstractions for the circuit breaker."""

from __future__ import annotations

import time
import uuid
from dataclasses import dataclass
from pathlib import Path
from typing import Protocol

import redis

from chaos_service import retry

from .rule import CircuitBreakerRule
from .state import CircuitState


@dataclass(frozen=True)
class CircuitWindowSnapshot:
    failure_count: int
    total_request_count: int
    failure_rate: float


@dataclass(frozen=True)
class CircuitRecordResult:
    opened: bool
    open_until: float
    snapshot: CircuitWindowSnapshot


@dataclass(frozen=True)
class CircuitBreakerKeys:
    open_until: str
    failures: str
    totals: str
    probe: str


class CircuitBreakerStorage(Protocol):
    def get_state(self, rule: CircuitBreakerRule) -> CircuitState: ...

    def get_open_until(self, rule: CircuitBreakerRule) -> float: ...

    def try_acquire_probe(self, rule: CircuitBreakerRule) -> bool: ...

    def record_success(self, rule: CircuitBreakerRule) -> CircuitRecordResult: ...

    def record_failure(self, rule: CircuitBreakerRule) -> CircuitRecordResult: ...

    def close(self, rule: CircuitBreakerRule) -> None: ...

    def reopen(self, rule: CircuitBreakerRule) -> float: ...

    def is_probe_active(self, rule: CircuitBreakerRule) -> bool: ...

    def snapshot(self, rule: CircuitBreakerRule) -> CircuitWindowSnapshot: ...


class _LuaScriptManager:
    def __init__(self, redis_client, script_dir: Path) -> None:
        self._redis_client = redis_client
        self._script_dir = script_dir
        self._scripts: dict[str, object] = {}

    def get(self, filename: str):
        script = self._scripts.get(filename)
        if script is None:
            content = (self._script_dir / filename).read_text(encoding="utf-8")
            script = self._redis_client.register_script(content)
            self._scripts[filename] = script
        return script


class RedisCircuitBreakerStorage:
    def __init__(self, ctx, *, clock=time.time) -> None:
        self._ctx = ctx
        self._clock = clock
        self._redis_client = getattr(ctx, "redis_client")
        script_dir = Path(__file__).resolve().parent / "lua"
        self._scripts = _LuaScriptManager(self._redis_client, script_dir)

    def get_state(self, rule: CircuitBreakerRule) -> CircuitState:
        now = self._clock()
        open_until = self.get_open_until(rule)
        if open_until > now:
            return CircuitState.OPEN
        if open_until > 0.0:
            return CircuitState.HALF_OPEN
        if self.is_probe_active(rule):
            return CircuitState.HALF_OPEN
        return CircuitState.CLOSED

    def try_acquire_probe(self, rule: CircuitBreakerRule) -> bool:
        keys = self._keys(rule)
        ok = self._redis_client.set(
            keys.probe,
            "1",
            nx=True,
            ex=int(getattr(self._ctx, "CIRCUIT_PROBE_TTL_SEC", 30)),
        )
        return bool(ok)

    def record_success(self, rule: CircuitBreakerRule) -> CircuitRecordResult:
        return self._record_outcome(rule, action="success")

    def record_failure(self, rule: CircuitBreakerRule) -> CircuitRecordResult:
        return self._record_outcome(rule, action="failure")

    def close(self, rule: CircuitBreakerRule) -> None:
        keys = self._keys(rule)
        self._redis_client.delete(keys.probe, keys.failures, keys.totals)
        self._redis_client.set(keys.open_until, "0")

    def reopen(self, rule: CircuitBreakerRule) -> float:
        keys = self._keys(rule)
        open_until = self._clock() + float(rule.open_timeout_seconds)
        self._redis_client.delete(keys.probe)
        self._redis_client.set(keys.open_until, str(open_until))
        return open_until

    def is_probe_active(self, rule: CircuitBreakerRule) -> bool:
        keys = self._keys(rule)
        return bool(
            self._read(lambda: self._redis_client.get(keys.probe), operation="circuit_get_probe")
        )

    def snapshot(self, rule: CircuitBreakerRule) -> CircuitWindowSnapshot:
        keys = self._keys(rule)
        now = self._clock()
        cutoff = now - float(rule.window_seconds)
        self._redis_client.zremrangebyscore(keys.failures, float("-inf"), cutoff)
        self._redis_client.zremrangebyscore(keys.totals, float("-inf"), cutoff)
        failure_count = int(self._redis_client.zcard(keys.failures))
        total_request_count = int(self._redis_client.zcard(keys.totals))
        failure_rate = (failure_count / total_request_count) if total_request_count > 0 else 0.0
        return CircuitWindowSnapshot(
            failure_count=failure_count,
            total_request_count=total_request_count,
            failure_rate=failure_rate,
        )

    def _record_outcome(self, rule: CircuitBreakerRule, *, action: str) -> CircuitRecordResult:
        keys = self._keys(rule)
        now = self._clock()
        ttl = int(rule.window_seconds) + 2
        total_member = f"total:{now:.6f}:{uuid.uuid4().hex}"
        failure_member = ""
        if action == "failure":
            failure_member = f"failure:{now:.6f}:{uuid.uuid4().hex}"
        script = self._scripts.get("circuit_breaker.lua")
        raw_result = script(
            keys=[keys.failures, keys.totals, keys.open_until],
            args=[
                action,
                str(now),
                str(rule.window_seconds),
                str(ttl),
                str(rule.min_request_count),
                str(rule.failure_rate_threshold),
                str(rule.open_timeout_seconds),
                total_member,
                failure_member,
            ],
        )
        opened = bool(int(raw_result[0]))
        failure_count = int(raw_result[1])
        total_request_count = int(raw_result[2])
        failure_rate = float(raw_result[3])
        open_until = float(raw_result[4])
        return CircuitRecordResult(
            opened=opened,
            open_until=open_until,
            snapshot=CircuitWindowSnapshot(
                failure_count=failure_count,
                total_request_count=total_request_count,
                failure_rate=failure_rate,
            ),
        )

    def _get_open_until(self, rule: CircuitBreakerRule) -> float:
        keys = self._keys(rule)
        raw = self._read(
            lambda: self._redis_client.get(keys.open_until),
            operation="circuit_get_open_until",
        )
        if raw is None or raw == "":
            return 0.0
        try:
            return float(raw)
        except (TypeError, ValueError):
            return 0.0

    def get_open_until(self, rule: CircuitBreakerRule) -> float:
        return self._get_open_until(rule)

    def _read(self, func, *, operation: str):
        policy = retry.build_retry_policy(self._ctx)
        return policy.execute(func, operation=operation)

    def _keys(self, rule: CircuitBreakerRule) -> CircuitBreakerKeys:
        legacy_resource = str(getattr(self._ctx, "BREAKER_RESOURCE", "order")).strip() or "order"
        if rule.resource == legacy_resource:
            return CircuitBreakerKeys(
                open_until=str(getattr(self._ctx, "CB_KEY_OPEN_UNTIL")),
                failures=str(getattr(self._ctx, "CB_KEY_FAILURES")),
                totals=str(getattr(self._ctx, "CB_KEY_TOTAL_REQUESTS")),
                probe=str(getattr(self._ctx, "CB_KEY_PROBE")),
            )

        resource = self._normalize(rule.resource)
        return CircuitBreakerKeys(
            open_until=f"cb:open_until:{resource}",
            failures=f"cb:failures:{resource}",
            totals=f"cb:total_requests:{resource}",
            probe=f"cb:probe:{resource}",
        )

    @staticmethod
    def _normalize(value: object) -> str:
        return str(value).strip().replace(" ", "_").replace("/", "_").replace(":", "_") or "unknown"
