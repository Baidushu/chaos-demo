from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class RateLimitConfig:
    service_name: str
    resource: str
    dimension: str
    algorithm: str
    limit: int
    window_sec: float
    lua_dir: Path


@dataclass(frozen=True)
class BreakerConfig:
    resource: str
    fail_threshold: int
    window_sec: int
    open_sec: int
    failure_rate_threshold: float
    min_request_amount: int
    probe_ttl_sec: int
    key_open_until: str
    key_failures: str
    key_total_requests: str
    key_probe: str


@dataclass(frozen=True)
class RetryConfig:
    max_attempts: int
    base_delay_ms: float
    max_delay_ms: float


@dataclass(frozen=True)
class IdempotencyConfig:
    order_ttl_sec: int
    order_key_prefix: str
    ttl_sec: int
    pending_ttl_sec: int
    wait_timeout_ms: int
    wait_poll_ms: int


@dataclass(frozen=True)
class BusinessConfig:
    timeout_ms: int
    inventory_busy_prob: float
    resilience_enabled: bool


def load_rate_limit_config(lua_dir: Path) -> RateLimitConfig:
    return RateLimitConfig(
        service_name=os.getenv("SERVICE_NAME", "chaos-demo").strip() or "chaos-demo",
        resource=os.getenv("RATE_LIMIT_RESOURCE", "order").strip() or "order",
        dimension=os.getenv("RATE_LIMIT_DIMENSION", "client_ip").strip() or "client_ip",
        algorithm=os.getenv("RATE_LIMIT_ALGORITHM", "sliding").strip().lower(),
        limit=int(os.getenv("RATE_LIMIT_PER_SEC", "30")),
        window_sec=float(os.getenv("RATE_LIMIT_WINDOW_SEC", "1")),
        lua_dir=lua_dir,
    )


def load_breaker_config() -> BreakerConfig:
    return BreakerConfig(
        resource=os.getenv("BREAKER_RESOURCE", "order").strip() or "order",
        fail_threshold=int(os.getenv("BREAKER_FAIL_THRESHOLD", "8")),
        window_sec=int(os.getenv("BREAKER_WINDOW_SEC", "10")),
        open_sec=int(os.getenv("BREAKER_OPEN_SEC", "8")),
        failure_rate_threshold=float(os.getenv("BREAKER_FAILURE_RATE_THRESHOLD", "0.5")),
        min_request_amount=int(os.getenv("MIN_REQUEST_AMOUNT", "100")),
        probe_ttl_sec=int(os.getenv("CIRCUIT_PROBE_TTL_SEC", "30")),
        key_open_until="cb:open_until",
        key_failures="cb:failures",
        key_total_requests="cb:total_requests",
        key_probe="cb:probe",
    )


def load_retry_config() -> RetryConfig:
    return RetryConfig(
        max_attempts=int(os.getenv("RETRY_MAX_ATTEMPTS", "3")),
        base_delay_ms=float(os.getenv("RETRY_BASE_DELAY_MS", "5")),
        max_delay_ms=float(os.getenv("RETRY_MAX_DELAY_MS", "50")),
    )


def load_idempotency_config() -> IdempotencyConfig:
    return IdempotencyConfig(
        order_ttl_sec=int(os.getenv("ORDER_TTL_SEC", "604800")),
        order_key_prefix="order:",
        ttl_sec=int(os.getenv("IDEM_TTL_SEC", "300")),
        pending_ttl_sec=int(os.getenv("IDEM_PENDING_TTL_SEC", "15")),
        wait_timeout_ms=int(os.getenv("IDEM_WAIT_TIMEOUT_MS", "120")),
        wait_poll_ms=int(os.getenv("IDEM_WAIT_POLL_MS", "10")),
    )


def load_business_config() -> BusinessConfig:
    return BusinessConfig(
        timeout_ms=int(os.getenv("BUSINESS_TIMEOUT_MS", "45")),
        inventory_busy_prob=float(os.getenv("INVENTORY_BUSY_PROB", "0.03")),
        resilience_enabled=os.getenv("ENABLE_RESILIENCE", "true").strip().lower() == "true",
    )
