from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

from .chaos import ChaosConfig, load_chaos_config
from .redis import RedisConfig, load_redis_config
from .resilience import (
    BreakerConfig,
    BusinessConfig,
    IdempotencyConfig,
    RateLimitConfig,
    RetryConfig,
    load_breaker_config,
    load_business_config,
    load_idempotency_config,
    load_rate_limit_config,
    load_retry_config,
)


@dataclass(frozen=True)
class TrafficConfig:
    enabled: bool
    record_file: Path
    max_queue: int


@dataclass(frozen=True)
class AppConfig:
    redis: RedisConfig
    chaos: ChaosConfig
    rate_limit: RateLimitConfig
    breaker: BreakerConfig
    retry: RetryConfig
    idempotency: IdempotencyConfig
    business: BusinessConfig
    traffic: TrafficConfig
    log_json: bool
    app_env: str
    app_host: str
    app_port: int


def load_app_config(project_root: Path) -> AppConfig:
    lua_dir = Path(os.getenv("RATE_LIMIT_LUA_DIR", str(project_root / "lua")))
    traffic_enabled = os.getenv("TRAFFIC_RECORD_ENABLED", "false").strip().lower() == "true"
    return AppConfig(
        redis=load_redis_config(),
        chaos=load_chaos_config(),
        rate_limit=load_rate_limit_config(lua_dir),
        breaker=load_breaker_config(),
        retry=load_retry_config(),
        idempotency=load_idempotency_config(),
        business=load_business_config(),
        traffic=TrafficConfig(
            enabled=traffic_enabled,
            record_file=Path(
                os.getenv("TRAFFIC_RECORD_FILE", "reports/traffic_record_latest.jsonl")
            ),
            max_queue=int(os.getenv("TRAFFIC_RECORD_MAX_QUEUE", "2000")),
        ),
        log_json=os.getenv("LOG_FORMAT", "json").strip().lower() == "json",
        app_env=os.getenv("APP_ENV", "dev").strip() or "dev",
        app_host="0.0.0.0",
        app_port=5000,
    )
