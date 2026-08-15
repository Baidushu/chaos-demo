"""Drop injector."""

from __future__ import annotations

from ..experiment import ChaosDropTriggered
from ..observer import ChaosObserver
from .base import FaultInjector


class DropInjector(FaultInjector):
    fault_type = "drop"

    def _should_drop(self, ctx, experiment) -> bool:
        rate = float(experiment.params.get("drop_rate", 0.0))
        source = self.random_source(ctx)
        sample = float(source.random()) if hasattr(source, "random") else 1.0
        return sample < rate

    def before_service(self, ctx, experiment, request_obj, *, stage: str) -> None:
        target_phase = str(experiment.target.get("phase", "service"))
        if target_phase != stage or not self._should_drop(ctx, experiment):
            return
        ChaosObserver(ctx).record_injected(experiment, phase=stage)
        raise ChaosDropTriggered(
            experiment=experiment,
            status_code=503,
            message="fault injected: drop",
        )

    def legacy_apply(self, ctx, experiment, request_obj) -> str | None:
        if not self._should_drop(ctx, experiment):
            return None
        ChaosObserver(ctx).record_injected(experiment, phase="pre_request")
        return "drop"
