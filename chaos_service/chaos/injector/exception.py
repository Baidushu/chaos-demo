"""Exception injector."""

from __future__ import annotations

from ..experiment import ChaosFaultTriggered
from ..observer import ChaosObserver
from .base import FaultInjector


class ExceptionInjector(FaultInjector):
    fault_type = "exception"

    def before_service(self, ctx, experiment, request_obj, *, stage: str) -> None:
        target_phase = str(experiment.target.get("phase", "service"))
        if target_phase != stage:
            return
        ChaosObserver(ctx).record_injected(experiment, phase=stage)
        error_type = experiment.params.get("error_type", "runtime")
        raise ChaosFaultTriggered(
            experiment=experiment,
            status_code=500,
            message=f"fault injected: {error_type}",
        )

    def legacy_apply(self, ctx, experiment, request_obj) -> str | None:
        ChaosObserver(ctx).record_injected(experiment, phase="pre_request")
        return "exception"
