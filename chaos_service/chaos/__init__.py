"""Lightweight chaos experiment orchestration helpers."""

from __future__ import annotations

import time
import uuid

from flask import request

from .experiment import (
    CHAOS_STATUS_RUNNING,
    CHAOS_STATUS_STOPPED,
    ChaosDropTriggered,
    ChaosExperiment,
    ChaosFaultTriggered,
    build_legacy_experiment,
)
from .injector.base import build_injector
from .matcher import match_request
from .observer import ChaosObserver
from .reporter import finalize_expired_reports
from .store import ChaosExperimentStore

_REQUEST_ATTR = "_chaos_experiments"


def _build_store(ctx) -> ChaosExperimentStore:
    return ChaosExperimentStore(ctx.redis_client)


def _observer(ctx) -> ChaosObserver:
    return ChaosObserver(ctx)


def create_experiment(
    ctx,
    *,
    name: str,
    hypothesis: str,
    target: dict,
    fault_type: str,
    params: dict,
    duration: int,
    experiment_id: str | None = None,
    status: str = CHAOS_STATUS_RUNNING,
    legacy_api: bool = False,
) -> ChaosExperiment:
    now = time.time()
    experiment = ChaosExperiment(
        id=experiment_id or uuid.uuid4().hex,
        name=name,
        hypothesis=hypothesis,
        target=target,
        fault_type=fault_type,
        params=params,
        duration=int(duration),
        status=status,
        created_at=now,
        updated_at=now,
        legacy_api=legacy_api,
    )
    _build_store(ctx).create_experiment(experiment)
    _observer(ctx).record_created(experiment)
    return experiment


def create_legacy_experiment(
    ctx, fault_type: str, params: dict, ttl_sec: int | None = None
) -> ChaosExperiment:
    duration = int(ttl_sec if ttl_sec is not None else getattr(ctx, "FAULT_DEFAULT_TTL_SEC", 60))
    experiment = build_legacy_experiment(fault_type, params, duration)
    _build_store(ctx).create_experiment(experiment)
    _observer(ctx).record_created(experiment)
    return experiment


def list_experiments(ctx, *, include_stopped: bool = False) -> list[ChaosExperiment]:
    finalize_expired_reports(ctx)
    return _build_store(ctx).list_experiments(include_stopped=include_stopped)


def get_experiment(ctx, experiment_id: str) -> ChaosExperiment | None:
    finalize_expired_reports(ctx)
    return _build_store(ctx).get_experiment(experiment_id)


def stop_experiment(ctx, experiment_id: str) -> bool:
    experiment = _build_store(ctx).stop_experiment(experiment_id)
    if experiment is None:
        return False
    _observer(ctx).record_recovered(experiment)
    return True


def stop_all_experiments(ctx) -> int:
    experiments = _build_store(ctx).list_experiments(include_stopped=False)
    stopped = 0
    for experiment in experiments:
        if stop_experiment(ctx, experiment.id):
            stopped += 1
    return stopped


def stop_legacy_fault(ctx, fault_type: str) -> bool:
    experiments = [
        exp
        for exp in _build_store(ctx).list_experiments(include_stopped=False)
        if exp.fault_type == fault_type
    ]
    if not experiments:
        return False
    for experiment in experiments:
        stop_experiment(ctx, experiment.id)
    return True


def get_legacy_fault(ctx, fault_type: str) -> dict | None:
    for experiment in _build_store(ctx).list_experiments(include_stopped=False):
        if experiment.fault_type == fault_type:
            return {
                "type": experiment.fault_type,
                "params": experiment.params,
                "injected_at": experiment.created_at,
                "ttl_sec": experiment.duration,
                "experiment_id": experiment.id,
            }
    return None


def list_legacy_faults(ctx) -> list[dict]:
    faults = []
    for experiment in _build_store(ctx).list_experiments(include_stopped=False):
        faults.append(
            {
                "type": experiment.fault_type,
                "params": experiment.params,
                "injected_at": experiment.created_at,
                "ttl_sec": experiment.duration,
                "experiment_id": experiment.id,
                "target": experiment.target,
                "status": experiment.status,
            }
        )
    return faults


def prepare_request_experiments(ctx, req=None) -> list[ChaosExperiment]:
    finalize_expired_reports(ctx)
    req = req or request
    active = []
    random_source = getattr(ctx, "random", None)
    for experiment in _build_store(ctx).list_experiments(include_stopped=False):
        if not match_request(experiment, req, random_source=random_source):
            continue
        active.append(experiment)
        build_injector(experiment.fault_type).before_request(ctx, experiment, req)
    setattr(req, _REQUEST_ATTR, active)
    return active


def _request_experiments(req=None) -> list[ChaosExperiment]:
    req = req or request
    return list(getattr(req, _REQUEST_ATTR, []))


def inject_service_faults(ctx, *, req=None, stage: str = "service") -> None:
    req = req or request
    for experiment in _request_experiments(req):
        build_injector(experiment.fault_type).before_service(ctx, experiment, req, stage=stage)


def inject_store_faults(ctx, operation: str, *, req=None) -> None:
    req = req or request
    for experiment in _request_experiments(req):
        build_injector(experiment.fault_type).before_store_call(
            ctx, experiment, operation=operation, request_obj=req
        )


def record_response(ctx, response, *, req=None) -> None:
    req = req or request
    _observer(ctx).record_response(_request_experiments(req), response)


def build_fault_status_response(ctx) -> dict:
    faults = list_legacy_faults(ctx)
    return {
        "enabled": bool(getattr(ctx, "FAULT_INJECTION_ENABLED", True)),
        "active_faults": len(faults),
        "faults": faults,
        "defaults": {
            "ttl_sec": int(getattr(ctx, "FAULT_DEFAULT_TTL_SEC", 60)),
            "max_latency_ms": int(getattr(ctx, "FAULT_MAX_LATENCY_MS", 5000)),
            "max_drop_rate": float(getattr(ctx, "FAULT_MAX_DROP_RATE", 1.0)),
        },
    }


def apply_legacy_faults(ctx, req=None) -> str | None:
    req = req or request
    active = list(getattr(req, _REQUEST_ATTR, []))
    random_source = getattr(ctx, "random", None)
    for experiment in _build_store(ctx).list_experiments(include_stopped=False):
        if not experiment.legacy_api:
            continue
        if not match_request(experiment, req, random_source=random_source):
            continue
        if all(existing.id != experiment.id for existing in active):
            active.append(experiment)
        action = build_injector(experiment.fault_type).legacy_apply(ctx, experiment, req)
        if action in ("drop", "exception"):
            setattr(req, _REQUEST_ATTR, active)
            return action
    setattr(req, _REQUEST_ATTR, active)
    return "latency" if active else None


__all__ = [
    "CHAOS_STATUS_RUNNING",
    "CHAOS_STATUS_STOPPED",
    "ChaosDropTriggered",
    "ChaosExperiment",
    "ChaosFaultTriggered",
    "apply_legacy_faults",
    "build_fault_status_response",
    "create_experiment",
    "create_legacy_experiment",
    "get_experiment",
    "get_legacy_fault",
    "inject_service_faults",
    "inject_store_faults",
    "list_experiments",
    "list_legacy_faults",
    "prepare_request_experiments",
    "record_response",
    "stop_all_experiments",
    "stop_experiment",
    "stop_legacy_fault",
]
