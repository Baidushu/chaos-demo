"""Latency injector."""

from __future__ import annotations

import time

from ..observer import ChaosObserver
from .base import FaultInjector


class LatencyInjector(FaultInjector):
    fault_type = "latency"

    def before_request(self, ctx, experiment, request_obj) -> None:
        ms = float(experiment.params.get("latency_ms", 0))
        if ms <= 0:
            return
        ChaosObserver(ctx).record_injected(experiment, phase="before_request")
        time.sleep(ms / 1000.0)

    def legacy_apply(self, ctx, experiment, request_obj) -> str | None:
        self.before_request(ctx, experiment, request_obj)
        return "latency"
