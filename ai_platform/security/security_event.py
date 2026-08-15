"""Observability integration for AI Security.

SecurityEvent records all security-related events into the observability collector.
"""

from __future__ import annotations

import time
import uuid
from dataclasses import dataclass, field
from typing import Any


@dataclass(slots=True)
class SecurityEvent:
    event_type: str = "security"
    timestamp: float = field(default_factory=time.time)
    trace_id: str = field(default_factory=lambda: uuid.uuid4().hex[:16])
    check_name: str = ""
    passed: bool = True
    risk_level: str = "none"
    violations: list[str] = field(default_factory=list)
    metadata: dict[str, Any] = field(default_factory=dict)

    @classmethod
    def block_event(
        cls,
        *,
        check_name: str = "",
        risk_level: str = "high",
        violations: list[str] | None = None,
        trace_id: str = "",
        metadata: dict[str, Any] | None = None,
    ) -> "SecurityEvent":
        return cls(
            event_type="security.block",
            check_name=check_name,
            passed=False,
            risk_level=risk_level,
            violations=violations or [],
            trace_id=trace_id,
            metadata=metadata or {},
        )

    @classmethod
    def pass_event(
        cls,
        *,
        check_name: str = "",
        trace_id: str = "",
        metadata: dict[str, Any] | None = None,
    ) -> "SecurityEvent":
        return cls(
            event_type="security.pass",
            check_name=check_name,
            passed=True,
            risk_level="none",
            trace_id=trace_id,
            metadata=metadata or {},
        )

    def as_dict(self) -> dict[str, Any]:
        return {
            "event_type": self.event_type,
            "timestamp": self.timestamp,
            "trace_id": self.trace_id,
            "check_name": self.check_name,
            "passed": self.passed,
            "risk_level": self.risk_level,
            "violations": list(self.violations),
            "metadata": dict(self.metadata),
        }
