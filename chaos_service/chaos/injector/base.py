"""Base fault injector primitives."""

from __future__ import annotations

import random
from abc import ABC


class FaultInjector(ABC):
    fault_type = ""

    def before_request(self, ctx, experiment, request_obj) -> None:
        return None

    def before_service(self, ctx, experiment, request_obj, *, stage: str) -> None:
        return None

    def before_store_call(self, ctx, experiment, *, operation: str, request_obj) -> None:
        return None

    def legacy_apply(self, ctx, experiment, request_obj) -> str | None:
        self.before_request(ctx, experiment, request_obj)
        return None

    @staticmethod
    def random_source(ctx):
        return getattr(ctx, "_chaos_random", getattr(ctx, "random", random))


def build_injector(fault_type: str) -> FaultInjector:
    from .drop import DropInjector
    from .exception import ExceptionInjector
    from .latency import LatencyInjector
    from .slow_db import SlowDBInjector

    registry = {
        "latency": LatencyInjector(),
        "exception": ExceptionInjector(),
        "drop": DropInjector(),
        "slow_db": SlowDBInjector(),
    }
    return registry[fault_type]
