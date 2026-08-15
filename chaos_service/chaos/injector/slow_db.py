"""Slow DB injector."""

from __future__ import annotations

import time

import redis

from ..observer import ChaosObserver
from .base import FaultInjector


class SlowDBInjector(FaultInjector):
    fault_type = "slow_db"

    def before_store_call(self, ctx, experiment, *, operation: str, request_obj) -> None:
        target_phase = str(experiment.target.get("phase", "store"))
        if target_phase != "store":
            return
        target_operation = experiment.target.get("operation")
        if target_operation and target_operation != operation:
            return
        params = experiment.params
        base_ms = float(params.get("base_ms", 0.0))
        jitter_ms = float(params.get("jitter_ms", 0.0))
        timeout_rate = float(params.get("timeout_rate", 0.0))
        source = self.random_source(ctx)
        jitter = float(source.uniform(0.0, max(jitter_ms, 0.0))) if jitter_ms > 0 else 0.0
        total_ms = base_ms + jitter
        if total_ms > 0:
            ChaosObserver(ctx).record_injected(experiment, phase="store")
            time.sleep(total_ms / 1000.0)
        sample = float(source.random()) if hasattr(source, "random") else 1.0
        if sample < timeout_rate:
            ChaosObserver(ctx).record_injected(experiment, phase="store_timeout")
            raise redis.TimeoutError("fault injected: slow_db timeout")

    def legacy_apply(self, ctx, experiment, request_obj) -> str | None:
        params = experiment.params
        base_ms = float(params.get("base_ms", 0.0))
        jitter_ms = float(params.get("jitter_ms", 0.0))
        source = self.random_source(ctx)
        total_ms = base_ms + (
            float(source.uniform(0.0, max(jitter_ms, 0.0))) if jitter_ms > 0 else 0.0
        )
        if total_ms > 0:
            ChaosObserver(ctx).record_injected(experiment, phase="pre_request")
            time.sleep(total_ms / 1000.0)
        sample = float(source.random()) if hasattr(source, "random") else 1.0
        if sample < float(params.get("timeout_rate", 0.0)):
            return "drop"
        return "latency" if total_ms > 0 else None
