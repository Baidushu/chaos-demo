"""Redis-backed storage for chaos experiments and reports."""

from __future__ import annotations

import json
import time

from .experiment import CHAOS_STATUS_RUNNING, CHAOS_STATUS_STOPPED, ChaosExperiment

_EXPERIMENT_PREFIX = "chaos:experiment:"
_REPORT_PREFIX = "chaos:report:"
_REPORT_TTL_BUFFER_SEC = 300


def experiment_key(experiment_id: str) -> str:
    return f"{_EXPERIMENT_PREFIX}{experiment_id}"


def report_key(experiment_id: str) -> str:
    return f"{_REPORT_PREFIX}{experiment_id}"


class ChaosExperimentStore:
    def __init__(self, redis_client) -> None:
        self._redis = redis_client

    def create_experiment(self, experiment: ChaosExperiment) -> ChaosExperiment:
        payload = json.dumps(
            experiment.to_dict(), ensure_ascii=False, separators=(",", ":"), sort_keys=True
        )
        self._redis.setex(experiment_key(experiment.id), experiment.duration, payload)
        report = {
            "experiment_id": experiment.id,
            "experiment": experiment.name,
            "fault_type": experiment.fault_type,
            "target": experiment.target,
            "hypothesis": experiment.hypothesis,
            "created_at": experiment.created_at,
            "duration": experiment.duration,
            "status": experiment.status,
            "before_request_count": 0,
            "before_error_count": 0,
            "before_latency_ms": 0.0,
            "after_request_count": 0,
            "after_error_count": 0,
            "after_latency_ms": 0.0,
            "fallback_count": 0,
            "fault_injected_count": 0,
            "recovered": False,
        }
        self._redis.setex(
            report_key(experiment.id),
            max(experiment.duration + _REPORT_TTL_BUFFER_SEC, _REPORT_TTL_BUFFER_SEC),
            json.dumps(report, ensure_ascii=False, separators=(",", ":"), sort_keys=True),
        )
        return experiment

    def get_experiment(self, experiment_id: str) -> ChaosExperiment | None:
        raw = self._redis.get(experiment_key(experiment_id))
        if not raw:
            return None
        try:
            return ChaosExperiment.from_dict(json.loads(raw))
        except (TypeError, json.JSONDecodeError, KeyError, ValueError):
            return None

    def list_experiments(self, *, include_stopped: bool = False) -> list[ChaosExperiment]:
        experiments = []
        for key in sorted(self._redis.keys(f"{_EXPERIMENT_PREFIX}*")):
            raw = self._redis.get(key)
            if not raw:
                continue
            try:
                experiment = ChaosExperiment.from_dict(json.loads(raw))
            except (TypeError, json.JSONDecodeError, KeyError, ValueError):
                continue
            if include_stopped or experiment.status == CHAOS_STATUS_RUNNING:
                experiments.append(experiment)
        return experiments

    def stop_experiment(self, experiment_id: str) -> ChaosExperiment | None:
        experiment = self.get_experiment(experiment_id)
        if experiment is None:
            return None
        experiment.status = CHAOS_STATUS_STOPPED
        experiment.updated_at = time.time()
        self._redis.setex(
            experiment_key(experiment.id),
            _REPORT_TTL_BUFFER_SEC,
            json.dumps(
                experiment.to_dict(), ensure_ascii=False, separators=(",", ":"), sort_keys=True
            ),
        )
        return experiment

    def get_report(self, experiment_id: str) -> dict | None:
        raw = self._redis.get(report_key(experiment_id))
        if not raw:
            return None
        try:
            return json.loads(raw)
        except (TypeError, json.JSONDecodeError):
            return None

    def save_report(self, experiment_id: str, report: dict) -> dict:
        ttl = max(int(report.get("duration", 0)) + _REPORT_TTL_BUFFER_SEC, _REPORT_TTL_BUFFER_SEC)
        self._redis.setex(
            report_key(experiment_id),
            ttl,
            json.dumps(report, ensure_ascii=False, separators=(",", ":"), sort_keys=True),
        )
        return report
