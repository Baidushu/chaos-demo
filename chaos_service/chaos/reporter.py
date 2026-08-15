"""Chaos experiment reporting helpers."""

from __future__ import annotations

import time

from .experiment import CHAOS_STATUS_STOPPED
from .store import ChaosExperimentStore


def build_report(ctx, experiment_id: str) -> dict | None:
    store = ChaosExperimentStore(ctx.redis_client)
    report = store.get_report(experiment_id)
    experiment = store.get_experiment(experiment_id)
    if report is None:
        return None
    if experiment is None and not report.get("recovered", False):
        report["recovered"] = True
        report["status"] = CHAOS_STATUS_STOPPED
        store.save_report(experiment_id, report)
    request_count = int(report.get("after_request_count", 0))
    error_count = int(report.get("after_error_count", 0))
    avg_latency = 0.0
    if request_count > 0:
        avg_latency = float(report.get("after_latency_ms", 0.0)) / request_count
    return {
        "experiment": report.get("experiment"),
        "experiment_id": experiment_id,
        "success": error_count == 0,
        "before_error_rate": 0.0,
        "after_error_rate": (error_count / request_count) if request_count else 0.0,
        "before_latency_ms": float(report.get("before_latency_ms", 0.0)),
        "after_latency_ms": avg_latency,
        "fault_injected_count": int(report.get("fault_injected_count", 0)),
        "fallback_count": int(report.get("fallback_count", 0)),
        "recovered": bool(report.get("recovered", False)),
        "status": (
            experiment.status
            if experiment is not None
            else report.get("status", CHAOS_STATUS_STOPPED)
        ),
    }


def finalize_expired_reports(ctx) -> None:
    from .observer import record_report_recovered_metrics

    store = ChaosExperimentStore(ctx.redis_client)
    now = time.time()
    for report_key in sorted(ctx.redis_client.keys("chaos:report:*")):
        report = store.get_report(report_key.split(":")[-1])
        if report is None:
            continue
        if report.get("recovered"):
            continue
        expires_at = float(report.get("created_at", 0.0)) + float(report.get("duration", 0))
        if expires_at <= now:
            record_report_recovered_metrics(ctx, report)
            report["recovered"] = True
            report["status"] = CHAOS_STATUS_STOPPED
            store.save_report(report["experiment_id"], report)
