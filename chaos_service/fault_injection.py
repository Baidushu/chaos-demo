"""Compatibility facade for chaos experiments and legacy fault APIs."""

from __future__ import annotations

import json
import random as _random

from flask import has_request_context, request
from app.infrastructure import register_metrics

from . import chaos
from .chaos.experiment import (
    CHAOS_STATUS_RUNNING,
    ChaosDropTriggered,
    ChaosExperiment,
    ChaosFaultTriggered,
)
from .chaos.reporter import build_report

FAULT_INJECTION_ENABLED = True
FAULT_KEY_PREFIX = "fault:"
FAULT_DEFAULT_TTL_SEC = 60
FAULT_MAX_LATENCY_MS = 5000
FAULT_MAX_DROP_RATE = 1.0


def _ctx_from_redis(redis_conn):
    ctx = type(
        "FaultCtx",
        (),
        {
            "redis_client": redis_conn,
            "FAULT_DEFAULT_TTL_SEC": FAULT_DEFAULT_TTL_SEC,
            "FAULT_MAX_LATENCY_MS": FAULT_MAX_LATENCY_MS,
            "FAULT_MAX_DROP_RATE": FAULT_MAX_DROP_RATE,
            "FAULT_INJECTION_ENABLED": FAULT_INJECTION_ENABLED,
            "_chaos_random": _random,
        },
    )()
    _attach_chaos_metrics(ctx)
    return ctx


def _attach_chaos_metrics(ctx) -> None:
    metrics = register_metrics()
    ctx.CHAOS_EXPERIMENT_TOTAL = metrics.chaos_experiment_total
    ctx.CHAOS_EXPERIMENT_SUCCESS_TOTAL = metrics.chaos_experiment_success_total
    ctx.CHAOS_EXPERIMENT_FAILED_TOTAL = metrics.chaos_experiment_failed_total
    ctx.CHAOS_ACTIVE_EXPERIMENT = metrics.chaos_active_experiment
    ctx.CHAOS_RECOVERY_DURATION_SECONDS = metrics.chaos_recovery_duration_seconds
    ctx.CHAOS_FAULT_INJECTED_TOTAL = metrics.chaos_fault_injected_total
    ctx.CHAOS_FAULT_RECOVERED_TOTAL = metrics.chaos_fault_recovered_total
    ctx.CHAOS_EXPERIMENT_DURATION_SECONDS = metrics.chaos_experiment_duration_seconds


def _fault_key(fault_type: str) -> str:
    return f"{FAULT_KEY_PREFIX}{fault_type}"


def _validate_fault_params(fault_type: str, params: dict) -> str | None:
    if fault_type == "latency":
        ms = params.get("latency_ms", 0)
        if not isinstance(ms, (int, float)) or ms < 0:
            return "latency_ms must be >= 0"
        if ms > FAULT_MAX_LATENCY_MS:
            return f"latency_ms exceeds max {FAULT_MAX_LATENCY_MS}"
    elif fault_type == "exception":
        error_type = params.get("error_type", "")
        if not error_type or not isinstance(error_type, str):
            return "error_type is required"
    elif fault_type == "drop":
        rate = params.get("drop_rate", 0)
        if not isinstance(rate, (int, float)) or not (0 <= rate <= FAULT_MAX_DROP_RATE):
            return f"drop_rate must be in [0, {FAULT_MAX_DROP_RATE}]"
    elif fault_type == "slow_db":
        base_ms = params.get("base_ms", 0)
        jitter_ms = params.get("jitter_ms", 0)
        timeout_rate = params.get("timeout_rate", 0)
        if not isinstance(base_ms, (int, float)) or base_ms < 0:
            return "base_ms must be >= 0"
        if not isinstance(jitter_ms, (int, float)) or jitter_ms < 0:
            return "jitter_ms must be >= 0"
        if not isinstance(timeout_rate, (int, float)) or not (0 <= timeout_rate <= 1):
            return "timeout_rate must be in [0, 1]"
    else:
        return f"unknown fault type: {fault_type}"
    return None


def inject_fault(redis_conn, fault_type: str, params: dict, ttl_sec: int | None = None) -> dict:
    err = _validate_fault_params(fault_type, params)
    if err:
        raise ValueError(err)
    ctx = _ctx_from_redis(redis_conn)
    experiment = chaos.create_legacy_experiment(ctx, fault_type, params, ttl_sec)
    record = {
        "type": experiment.fault_type,
        "params": experiment.params,
        "injected_at": experiment.created_at,
        "ttl_sec": experiment.duration,
        "experiment_id": experiment.id,
    }
    redis_conn.setex(
        _fault_key(fault_type),
        experiment.duration,
        json.dumps(record, ensure_ascii=False, separators=(",", ":"), sort_keys=True),
    )
    return record


def clear_fault(redis_conn, fault_type: str) -> bool:
    existed = bool(redis_conn.delete(_fault_key(fault_type)))
    return chaos.stop_legacy_fault(_ctx_from_redis(redis_conn), fault_type) or existed


def clear_all_faults(redis_conn) -> int:
    keys = redis_conn.keys(f"{FAULT_KEY_PREFIX}*")
    deleted = redis_conn.delete(*keys) if keys else 0
    stopped = chaos.stop_all_experiments(_ctx_from_redis(redis_conn))
    return max(int(deleted), int(stopped))


def list_faults(redis_conn) -> list[dict]:
    faults = []
    for key in sorted(redis_conn.keys(f"{FAULT_KEY_PREFIX}*")):
        raw = redis_conn.get(key)
        if not raw:
            continue
        try:
            faults.append(json.loads(raw))
        except (TypeError, json.JSONDecodeError):
            continue
    if faults:
        return faults
    return chaos.list_legacy_faults(_ctx_from_redis(redis_conn))


def get_fault(redis_conn, fault_type: str) -> dict | None:
    raw = redis_conn.get(_fault_key(fault_type))
    if raw:
        try:
            return json.loads(raw)
        except (TypeError, json.JSONDecodeError):
            return None
    chaos.stop_legacy_fault(_ctx_from_redis(redis_conn), fault_type)
    return None


def build_fault_api_response(faults: list[dict]) -> dict:
    return {
        "enabled": FAULT_INJECTION_ENABLED,
        "active_faults": len(faults),
        "faults": faults,
        "defaults": {
            "ttl_sec": FAULT_DEFAULT_TTL_SEC,
            "max_latency_ms": FAULT_MAX_LATENCY_MS,
            "max_drop_rate": FAULT_MAX_DROP_RATE,
        },
    }


def prepare_request_experiments(ctx, req=None):
    _sync_ctx_settings(ctx)
    if req is None:
        req = (
            request if has_request_context() else type("Req", (), {"path": "*", "method": "POST"})()
        )
    if not getattr(ctx, "FAULT_INJECTION_ENABLED", True):
        setattr(req, "_chaos_experiments", [])
        return []
    return chaos.prepare_request_experiments(ctx, req)


def apply_faults(ctx, req=None) -> str | None:
    _sync_ctx_settings(ctx)
    if req is None:
        req = (
            request if has_request_context() else type("Req", (), {"path": "*", "method": "POST"})()
        )
    if not getattr(ctx, "FAULT_INJECTION_ENABLED", True):
        return None
    return chaos.apply_legacy_faults(ctx, req)


def before_service_operation(ctx, req=None, *, stage: str = "service") -> None:
    _sync_ctx_settings(ctx)
    if not getattr(ctx, "FAULT_INJECTION_ENABLED", True):
        return
    chaos.inject_service_faults(ctx, req=req or request, stage=stage)


def before_store_operation(ctx, operation: str) -> None:
    _sync_ctx_settings(ctx)
    if not getattr(ctx, "FAULT_INJECTION_ENABLED", True):
        return
    if not has_request_context():
        return
    chaos.inject_store_faults(ctx, operation, req=request)


def record_response(ctx, response, req=None) -> None:
    if not has_request_context() and req is None:
        return
    chaos.record_response(ctx, response, req=req or request)


def record_fallback(ctx, req=None) -> None:
    from .chaos.observer import ChaosObserver

    if not has_request_context() and req is None:
        return
    req = req or request
    ChaosObserver(ctx).record_fallback(getattr(req, "_chaos_experiments", []))


def create_experiment(
    ctx,
    *,
    name: str,
    hypothesis: str,
    target: dict,
    fault_type: str,
    params: dict,
    duration: int,
) -> ChaosExperiment:
    _sync_ctx_settings(ctx)
    err = _validate_fault_params(fault_type, params)
    if err:
        raise ValueError(err)
    return chaos.create_experiment(
        ctx,
        name=name,
        hypothesis=hypothesis,
        target=target,
        fault_type=fault_type,
        params=params,
        duration=duration,
    )


def list_experiments(ctx) -> list[ChaosExperiment]:
    _sync_ctx_settings(ctx)
    return chaos.list_experiments(ctx)


def get_experiment(ctx, experiment_id: str) -> ChaosExperiment | None:
    _sync_ctx_settings(ctx)
    return chaos.get_experiment(ctx, experiment_id)


def stop_experiment(ctx, experiment_id: str) -> bool:
    _sync_ctx_settings(ctx)
    return chaos.stop_experiment(ctx, experiment_id)


def get_report(ctx, experiment_id: str) -> dict | None:
    return build_report(ctx, experiment_id)


def _sync_ctx_settings(ctx) -> None:
    global FAULT_INJECTION_ENABLED, FAULT_DEFAULT_TTL_SEC, FAULT_MAX_LATENCY_MS, FAULT_MAX_DROP_RATE
    FAULT_INJECTION_ENABLED = bool(getattr(ctx, "FAULT_INJECTION_ENABLED", FAULT_INJECTION_ENABLED))
    FAULT_DEFAULT_TTL_SEC = int(getattr(ctx, "FAULT_DEFAULT_TTL_SEC", FAULT_DEFAULT_TTL_SEC))
    FAULT_MAX_LATENCY_MS = int(getattr(ctx, "FAULT_MAX_LATENCY_MS", FAULT_MAX_LATENCY_MS))
    FAULT_MAX_DROP_RATE = float(getattr(ctx, "FAULT_MAX_DROP_RATE", FAULT_MAX_DROP_RATE))
    try:
        _attach_chaos_metrics(ctx)
        setattr(ctx, "_chaos_random", _random)
        setattr(ctx, "FAULT_INJECTION_ENABLED", FAULT_INJECTION_ENABLED)
        setattr(ctx, "FAULT_DEFAULT_TTL_SEC", FAULT_DEFAULT_TTL_SEC)
        setattr(ctx, "FAULT_MAX_LATENCY_MS", FAULT_MAX_LATENCY_MS)
        setattr(ctx, "FAULT_MAX_DROP_RATE", FAULT_MAX_DROP_RATE)
    except Exception:
        pass


__all__ = [
    "CHAOS_STATUS_RUNNING",
    "ChaosDropTriggered",
    "ChaosExperiment",
    "ChaosFaultTriggered",
    "FAULT_DEFAULT_TTL_SEC",
    "FAULT_INJECTION_ENABLED",
    "FAULT_KEY_PREFIX",
    "FAULT_MAX_DROP_RATE",
    "FAULT_MAX_LATENCY_MS",
    "_fault_key",
    "_validate_fault_params",
    "apply_faults",
    "before_service_operation",
    "before_store_operation",
    "build_fault_api_response",
    "clear_all_faults",
    "clear_fault",
    "create_experiment",
    "get_experiment",
    "get_fault",
    "get_report",
    "inject_fault",
    "list_experiments",
    "list_faults",
    "prepare_request_experiments",
    "record_fallback",
    "record_response",
    "stop_experiment",
]
