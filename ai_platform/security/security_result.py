"""Unified security check result.

Represents the outcome of any security check:
  - Input validation
  - Prompt injection guard
  - Tool permission check
  - Output safety check
"""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from typing import Any


@dataclass(slots=True)
class SecurityResult:
    passed: bool = True
    risk_level: str = "none"  # none | low | medium | high | critical
    violations: list[str] = field(default_factory=list)
    metadata: dict[str, Any] = field(default_factory=dict)
    timestamp: float = field(default_factory=time.time)
    check_name: str = ""

    @classmethod
    def pass_(cls, *, check_name: str = "", metadata: dict[str, Any] | None = None) -> "SecurityResult":
        return cls(
            passed=True,
            risk_level="none",
            check_name=check_name,
            metadata=metadata or {},
        )

    @classmethod
    def block(
        cls,
        *,
        risk_level: str = "high",
        violations: list[str] | None = None,
        check_name: str = "",
        metadata: dict[str, Any] | None = None,
    ) -> "SecurityResult":
        return cls(
            passed=False,
            risk_level=risk_level,
            violations=violations or [],
            check_name=check_name,
            metadata=metadata or {},
        )

    def as_dict(self) -> dict[str, Any]:
        return {
            "passed": self.passed,
            "risk_level": self.risk_level,
            "violations": list(self.violations),
            "check_name": self.check_name,
            "timestamp": self.timestamp,
            "metadata": dict(self.metadata),
        }

    @staticmethod
    def worst(a: "SecurityResult", b: "SecurityResult") -> "SecurityResult":
        """Return the more severe result (block wins, higher risk wins), with merged violations."""
        a_order = _risk_order(a.risk_level)
        b_order = _risk_order(b.risk_level)

        # Merge violations, deduplicating
        seen = set(a.violations)
        merged = list(a.violations)
        for v in b.violations:
            if v not in seen:
                seen.add(v)
                merged.append(v)

        if not a.passed or not b.passed:
            # At least one block — pick the more severe
            if a_order >= b_order and not a.passed:
                base = a
            elif not b.passed:
                base = b
            else:
                base = a if not a.passed else b
            return SecurityResult(
                passed=False,
                risk_level=base.risk_level,
                violations=merged,
                check_name=base.check_name,
                metadata={**base.metadata, **a.metadata, **b.metadata},
                timestamp=base.timestamp,
            )

        # Both pass — pick higher risk
        base = a if a_order >= b_order else b
        return SecurityResult(
            passed=True,
            risk_level=base.risk_level,
            violations=merged,
            check_name=base.check_name,
            metadata={**base.metadata},
            timestamp=base.timestamp,
        )


def _risk_order(level: str) -> int:
    return {"none": 0, "low": 1, "medium": 2, "high": 3, "critical": 4}.get(level, 0)
