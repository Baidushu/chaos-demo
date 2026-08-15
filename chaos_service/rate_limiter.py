"""Rate limiting primitives and Redis backend implementations."""

from __future__ import annotations

import math
import time
import uuid
from dataclasses import dataclass
from pathlib import Path
from typing import Protocol

import redis


@dataclass(frozen=True)
class RateLimitRule:
    """Describes a single rate-limit rule."""

    resource: str
    algorithm: str
    limit: int
    window: float
    dimension: str

    def __post_init__(self) -> None:
        if self.algorithm not in ("sliding", "fixed"):
            raise ValueError("algorithm must be sliding|fixed")
        if self.limit < 0:
            raise ValueError("limit must be >= 0")
        if self.window <= 0:
            raise ValueError("window must be > 0")
        if not self.resource:
            raise ValueError("resource must not be empty")
        if not self.dimension:
            raise ValueError("dimension must not be empty")


@dataclass(frozen=True)
class RateLimitDecision:
    """Represents the backend decision for one rate-limit check."""

    allowed: bool
    key: str
    algorithm: str
    resource: str
    dimension: str
    backend_error: bool = False


class RateLimitBackend(Protocol):
    """Backend contract used by the limiter."""

    def allow(self, rule: RateLimitRule, subject_id: str) -> RateLimitDecision: ...


class LuaScriptManager:
    """Loads Redis Lua scripts from the repository and registers them lazily."""

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


class RedisBackend:
    """Redis-backed rate-limit storage."""

    def __init__(
        self,
        redis_client,
        *,
        service_name: str,
        script_dir: Path,
        clock=time.time,
    ) -> None:
        self._redis_client = redis_client
        self._service_name = service_name
        self._clock = clock
        self._scripts = LuaScriptManager(redis_client, script_dir)

    def allow(self, rule: RateLimitRule, subject_id: str) -> RateLimitDecision:
        if rule.algorithm == "fixed":
            return self._allow_fixed(rule, subject_id)
        return self._allow_sliding(rule, subject_id)

    def _allow_fixed(self, rule: RateLimitRule, subject_id: str) -> RateLimitDecision:
        now = self._clock()
        bucket = int(math.floor(now / rule.window))
        key = f"{self._build_base_key(rule, subject_id)}:{bucket}"
        ttl = max(int(math.ceil(rule.window)) + 1, 1)
        script = self._scripts.get("fixed_window.lua")
        current = int(script(keys=[key], args=[str(ttl)]))
        return RateLimitDecision(
            allowed=current <= rule.limit,
            key=key,
            algorithm=rule.algorithm,
            resource=rule.resource,
            dimension=rule.dimension,
        )

    def _allow_sliding(self, rule: RateLimitRule, subject_id: str) -> RateLimitDecision:
        key = self._build_base_key(rule, subject_id)
        now = self._clock()
        member = f"{now:.6f}:{uuid.uuid4().hex}"
        ttl = max(int(math.ceil(rule.window)) + 1, 1)
        script = self._scripts.get("sliding_window.lua")
        allowed = bool(
            int(
                script(
                    keys=[key],
                    args=[str(now), str(rule.window), str(rule.limit), member, str(ttl)],
                )
            )
        )
        return RateLimitDecision(
            allowed=allowed,
            key=key,
            algorithm=rule.algorithm,
            resource=rule.resource,
            dimension=rule.dimension,
        )

    def _build_base_key(self, rule: RateLimitRule, subject_id: str) -> str:
        return ":".join(
            [
                self._normalize_segment(self._service_name),
                "rate",
                self._normalize_segment(rule.resource),
                self._normalize_segment(rule.dimension),
                self._normalize_segment(subject_id),
            ]
        )

    @staticmethod
    def _normalize_segment(value: object) -> str:
        text = str(value).strip()
        if not text:
            return "unknown"
        return text.replace(" ", "_").replace("/", "_").replace(":", "_")


class RateLimitMetrics:
    """Small adapter over Prometheus counters exposed on ctx."""

    def __init__(self, ctx) -> None:
        self._ctx = ctx

    def record_allowed(self, rule: RateLimitRule) -> None:
        counter = getattr(self._ctx, "RATE_LIMIT_ALLOWED_TOTAL", None)
        if counter is not None:
            counter.labels(
                algorithm=rule.algorithm,
                resource=rule.resource,
                dimension=rule.dimension,
            ).inc()

    def record_rejected(self, rule: RateLimitRule) -> None:
        counter = getattr(self._ctx, "RATE_LIMIT_REJECTED_TOTAL", None)
        if counter is not None:
            counter.labels(
                algorithm=rule.algorithm,
                resource=rule.resource,
                dimension=rule.dimension,
            ).inc()

    def record_redis_error(self, rule: RateLimitRule) -> None:
        counter = getattr(self._ctx, "RATE_LIMIT_REDIS_ERROR_TOTAL", None)
        if counter is not None:
            counter.labels(
                algorithm=rule.algorithm,
                resource=rule.resource,
                dimension=rule.dimension,
            ).inc()


class RateLimiter:
    """Applies a rule through a backend and emits metrics."""

    def __init__(
        self, rule: RateLimitRule, backend: RateLimitBackend, metrics: RateLimitMetrics
    ) -> None:
        self._rule = rule
        self._backend = backend
        self._metrics = metrics

    def allow(self, subject_id: str) -> RateLimitDecision:
        try:
            decision = self._backend.allow(self._rule, subject_id)
        except redis.RedisError:
            self._metrics.record_redis_error(self._rule)
            return RateLimitDecision(
                allowed=True,
                key="",
                algorithm=self._rule.algorithm,
                resource=self._rule.resource,
                dimension=self._rule.dimension,
                backend_error=True,
            )

        if decision.allowed:
            self._metrics.record_allowed(self._rule)
        else:
            self._metrics.record_rejected(self._rule)
        return decision

    @property
    def rule(self) -> RateLimitRule:
        return self._rule


def build_default_rule(ctx) -> RateLimitRule:
    """Builds the default rule from the current runtime configuration."""
    return RateLimitRule(
        resource=str(getattr(ctx, "RATE_LIMIT_RESOURCE", "order")),
        algorithm=str(getattr(ctx, "RATE_LIMIT_ALGORITHM", "sliding")).strip().lower(),
        limit=int(getattr(ctx, "RATE_LIMIT_PER_SEC", 30)),
        window=float(getattr(ctx, "RATE_LIMIT_WINDOW_SEC", 1.0)),
        dimension=str(getattr(ctx, "RATE_LIMIT_DIMENSION", "client_ip")),
    )


def build_redis_backend(ctx) -> RedisBackend:
    """Returns a cached Redis backend bound to the current Redis client."""
    redis_client = getattr(ctx, "redis_client")
    service_name = str(getattr(ctx, "SERVICE_NAME", "chaos-demo"))
    script_dir = Path(getattr(ctx, "RATE_LIMIT_LUA_DIR"))
    signature = (id(redis_client), service_name, str(script_dir))
    cached_signature = getattr(ctx, "_rate_limit_backend_signature", None)
    backend = getattr(ctx, "_rate_limit_backend", None)
    if backend is None or cached_signature != signature:
        backend = RedisBackend(
            redis_client,
            service_name=service_name,
            script_dir=script_dir,
        )
        setattr(ctx, "_rate_limit_backend", backend)
        setattr(ctx, "_rate_limit_backend_signature", signature)
    return backend


def build_rate_limiter(ctx, rule: RateLimitRule | None = None) -> RateLimiter:
    """Constructs a limiter using the current default rule and backend."""
    active_rule = rule or build_default_rule(ctx)
    backend = build_redis_backend(ctx)
    metrics = RateLimitMetrics(ctx)
    return RateLimiter(active_rule, backend, metrics)


def resolve_subject_id(request, dimension: str) -> str:
    """Maps the configured dimension to an identifier from the HTTP request."""
    if dimension == "client_ip":
        forwarded = request.headers.get("X-Forwarded-For", "")
        if forwarded:
            return forwarded.split(",")[0].strip() or "unknown"
        return request.remote_addr or "unknown"
    return request.headers.get("X-Forwarded-For", request.remote_addr or "unknown")
