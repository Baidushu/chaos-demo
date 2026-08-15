"""Chaos-specific metrics and observation helpers."""

from __future__ import annotations

import logging
import time

from app.infrastructure.logging import log_event

from .store import ChaosExperimentStore


def _target_label(target: dict | None) -> str:
    target = dict(target or {})
    endpoint = target.get("endpoint", "*")
    method = str(target.get("method", "*")).upper()
    percentage = target.get("percentage", "*")
    return f"{method}:{endpoint}:{percentage}"


class ChaosObserver:
    def __init__(self, ctx) -> None:
        self._ctx = ctx
        self._store = ChaosExperimentStore(ctx.redis_client)

    def record_created(self, experiment) -> None:
        labels = self._labels(experiment)
        self._ctx.CHAOS_EXPERIMENT_TOTAL.labels(**labels).inc()
        self._ctx.CHAOS_ACTIVE_EXPERIMENT.labels(**labels).inc()
        self._ctx.CHAOS_EXPERIMENT_DURATION_SECONDS.labels(**labels).observe(
            max(float(experiment.duration), 0.0)
        )
        self._log(
            "chaos_experiment_start",
            experiment,
            result="running",
            duration=experiment.duration,
        )

    def record_injected(self, experiment, *, phase: str) -> None:
        self._ctx.CHAOS_FAULT_INJECTED_TOTAL.labels(
            phase=phase,
            **self._labels(experiment),
        ).inc()
        self._log(
            "fault_injection",
            experiment,
            result="injected",
            phase=phase,
            params=dict(getattr(experiment, "params", {}) or {}),
        )
        report = self._store.get_report(experiment.id)
        if report is None:
            return
        report["fault_injected_count"] = int(report.get("fault_injected_count", 0)) + 1
        self._store.save_report(experiment.id, report)

    def record_response(self, experiments, response) -> None:
        for experiment in experiments:
            report = self._store.get_report(experiment.id)
            if report is None:
                continue
            report["after_request_count"] = int(report.get("after_request_count", 0)) + 1
            if int(getattr(response, "status_code", 200)) >= 500:
                report["after_error_count"] = int(report.get("after_error_count", 0)) + 1
            duration_ms = float(getattr(response, "_chaos_duration_ms", 0.0) or 0.0)
            report["after_latency_ms"] = float(report.get("after_latency_ms", 0.0)) + duration_ms
            self._store.save_report(experiment.id, report)

    def record_fallback(self, experiments) -> None:
        for experiment in experiments:
            report = self._store.get_report(experiment.id)
            if report is None:
                continue
            report["fallback_count"] = int(report.get("fallback_count", 0)) + 1
            self._store.save_report(experiment.id, report)

    def record_recovered(self, experiment) -> None:
        report = self._store.get_report(experiment.id)
        if report is None:
            return
        record_report_recovered_metrics(self._ctx, report)
        self._log("chaos_experiment_end", experiment, result="stopped")
        report["recovered"] = True
        report["status"] = getattr(experiment, "status", "stopped")
        self._store.save_report(experiment.id, report)

    def _labels(self, experiment) -> dict:
        return {
            "fault_type": str(experiment.fault_type),
            "target": _target_label(getattr(experiment, "target", {})),
        }

    def _log(self, event: str, experiment, *, result: str, **fields) -> None:
        app = getattr(self._ctx, "app", None)
        logger = getattr(app, "logger", None) or getattr(self._ctx, "logger", None)
        if logger is None:
            logger = logging.getLogger(__name__)
        log_event(
            logger,
            event,
            component="chaos",
            operation="experiment",
            result=result,
            experiment_id=getattr(experiment, "id", None),
            fault_type=getattr(experiment, "fault_type", None),
            target=_target_label(getattr(experiment, "target", {})),
            **fields,
        )


def record_report_recovered_metrics(ctx, report: dict) -> None:
    labels = {
        "fault_type": str(report.get("fault_type", "unknown")),
        "target": _target_label(report.get("target")),
    }
    ctx.CHAOS_FAULT_RECOVERED_TOTAL.labels(**labels).inc()
    ctx.CHAOS_ACTIVE_EXPERIMENT.labels(**labels).dec()
    success_counter = ctx.CHAOS_EXPERIMENT_SUCCESS_TOTAL
    failed_counter = ctx.CHAOS_EXPERIMENT_FAILED_TOTAL
    if int(report.get("after_error_count", 0)) == 0:
        success_counter.labels(**labels).inc()
    else:
        failed_counter.labels(**labels).inc()
    duration_s = max(time.time() - float(report.get("created_at", 0.0)), 0.0)
    ctx.CHAOS_RECOVERY_DURATION_SECONDS.labels(**labels).observe(duration_s)
