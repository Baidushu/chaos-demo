"""Platform core exceptions."""

from __future__ import annotations

from typing import Any


class PlatformError(Exception):
    """Base platform error."""


class SecurityBlockedError(PlatformError):
    """Raised when security blocks a request."""

    def __init__(self, message: str, violations: list[str] | None = None) -> None:
        super().__init__(message)
        self.violations = violations or []


class AgentExecutionError(PlatformError):
    """Raised when agent execution fails."""

    def __init__(self, message: str, agent_error: dict[str, Any] | None = None) -> None:
        super().__init__(message)
        self.agent_error = agent_error


class EvaluationError(PlatformError):
    """Raised when evaluation or quality gate fails."""

    def __init__(
        self,
        message: str,
        gate_violations: list[str] | None = None,
        eval_result: dict[str, Any] | None = None,
    ) -> None:
        super().__init__(message)
        self.gate_violations = gate_violations or []
        self.eval_result = eval_result
