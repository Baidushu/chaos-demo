"""Chaos experiment models."""

from __future__ import annotations

import time
import uuid
from dataclasses import asdict, dataclass, field

CHAOS_STATUS_RUNNING = "running"
CHAOS_STATUS_STOPPED = "stopped"


@dataclass
class ChaosExperiment:
    id: str
    name: str
    hypothesis: str
    target: dict
    fault_type: str
    params: dict
    duration: int
    status: str
    created_at: float = field(default_factory=time.time)
    updated_at: float = field(default_factory=time.time)
    legacy_api: bool = False

    def to_dict(self) -> dict:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict) -> "ChaosExperiment":
        return cls(
            id=str(data["id"]),
            name=str(data["name"]),
            hypothesis=str(data.get("hypothesis", "")),
            target=dict(data.get("target") or {}),
            fault_type=str(data["fault_type"]),
            params=dict(data.get("params") or {}),
            duration=int(data["duration"]),
            status=str(data.get("status", CHAOS_STATUS_RUNNING)),
            created_at=float(data.get("created_at", time.time())),
            updated_at=float(data.get("updated_at", time.time())),
            legacy_api=bool(data.get("legacy_api", False)),
        )


class ChaosFaultTriggered(Exception):
    def __init__(self, *, experiment: ChaosExperiment, status_code: int, message: str) -> None:
        super().__init__(message)
        self.experiment = experiment
        self.status_code = int(status_code)
        self.message = message

    def to_response(self) -> dict:
        return {
            "error": self.message,
            "fault": True,
            "experiment_id": self.experiment.id,
            "fault_type": self.experiment.fault_type,
        }


class ChaosDropTriggered(ChaosFaultTriggered):
    pass


def build_legacy_experiment(fault_type: str, params: dict, duration: int) -> ChaosExperiment:
    now = time.time()
    return ChaosExperiment(
        id=uuid.uuid4().hex,
        name=f"legacy_{fault_type}",
        hypothesis=f"legacy fault injection for {fault_type}",
        target={"endpoint": "*", "phase": "pre_request"},
        fault_type=fault_type,
        params=dict(params or {}),
        duration=int(duration),
        status=CHAOS_STATUS_RUNNING,
        created_at=now,
        updated_at=now,
        legacy_api=True,
    )
