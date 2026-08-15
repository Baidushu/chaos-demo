from __future__ import annotations

import os
from dataclasses import dataclass


def _env_flag(name: str, default: str) -> bool:
    return os.getenv(name, default).strip().lower() in ("1", "true", "yes", "on")


@dataclass(frozen=True)
class ChaosConfig:
    enabled: bool
    fault_injection_enabled: bool
    default_ttl_sec: int
    max_latency_ms: int
    max_drop_rate: float


def load_chaos_config() -> ChaosConfig:
    chaos_enabled = _env_flag("CHAOS_ENABLED", "true")
    fault_enabled = _env_flag("ENABLE_FAULT_INJECTION", "true")
    return ChaosConfig(
        enabled=chaos_enabled,
        fault_injection_enabled=chaos_enabled and fault_enabled,
        default_ttl_sec=int(os.getenv("FAULT_DEFAULT_TTL_SEC", "60")),
        max_latency_ms=int(os.getenv("FAULT_MAX_LATENCY_MS", "5000")),
        max_drop_rate=float(os.getenv("FAULT_MAX_DROP_RATE", "1.0")),
    )
