"""Platform configuration — centralized, no hardcoding.

All configuration defaults can be overridden via constructor params
or loaded from environment / dict.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from ai_platform.security.policy import SecurityPolicy


@dataclass(slots=True)
class ModelConfig:
    """LLM model configuration for the platform."""
    provider: str = "mock"
    model: str = "default"
    temperature: float = 0.1
    max_tokens: int = 2048
    timeout_seconds: float = 30.0

    def to_dict(self) -> dict[str, Any]:
        return {
            "provider": self.provider,
            "model": self.model,
            "temperature": self.temperature,
            "max_tokens": self.max_tokens,
            "timeout_seconds": self.timeout_seconds,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "ModelConfig":
        return cls(
            provider=str(data.get("provider", "mock")),
            model=str(data.get("model", "default")),
            temperature=float(data.get("temperature", 0.1)),
            max_tokens=int(data.get("max_tokens", 2048)),
            timeout_seconds=float(data.get("timeout_seconds", 30.0)),
        )


@dataclass(slots=True)
class EvaluationConfig:
    """Evaluation thresholds for quality gate."""
    tool_selection_accuracy_min: float = 0.7
    arg_accuracy_min: float = 0.7
    avg_tool_calls_per_task_max: float = 10.0
    retry_rate_max: float = 0.3
    hallucination_rate_max: float = 0.1
    planner_invalid_rate_max: float = 0.1

    def to_dict(self) -> dict[str, Any]:
        return {
            "tool_selection_accuracy_min": self.tool_selection_accuracy_min,
            "arg_accuracy_min": self.arg_accuracy_min,
            "avg_tool_calls_per_task_max": self.avg_tool_calls_per_task_max,
            "retry_rate_max": self.retry_rate_max,
            "hallucination_rate_max": self.hallucination_rate_max,
            "planner_invalid_rate_max": self.planner_invalid_rate_max,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "EvaluationConfig":
        return cls(
            tool_selection_accuracy_min=float(data.get("tool_selection_accuracy_min", 0.7)),
            arg_accuracy_min=float(data.get("arg_accuracy_min", 0.7)),
            avg_tool_calls_per_task_max=float(data.get("avg_tool_calls_per_task_max", 10.0)),
            retry_rate_max=float(data.get("retry_rate_max", 0.3)),
            hallucination_rate_max=float(data.get("hallucination_rate_max", 0.1)),
            planner_invalid_rate_max=float(data.get("planner_invalid_rate_max", 0.1)),
        )


@dataclass(slots=True)
class PlatformConfig:
    """Top-level platform configuration.

    Usage:
        config = PlatformConfig()
        config = PlatformConfig.from_dict({"model": {"provider": "ollama"}, "mode": "rule"})

        # Environment-driven:
        config = PlatformConfig.from_env()
    """

    model: ModelConfig = field(default_factory=ModelConfig)
    evaluation: EvaluationConfig = field(default_factory=EvaluationConfig)
    security: SecurityPolicy = field(default_factory=SecurityPolicy)
    mode: str = "rule"  # "rule" | "ollama" | "auto"
    observability_enabled: bool = True
    evaluation_enabled: bool = False  # disabled by default — requires batch-mode evaluators
    quality_gate_enabled: bool = False  # disabled by default — requires evaluation metrics
    timeout_seconds: float = 60.0

    def to_dict(self) -> dict[str, Any]:
        return {
            "model": self.model.to_dict(),
            "evaluation": self.evaluation.to_dict(),
            "security": self.security.to_dict(),
            "mode": self.mode,
            "observability_enabled": self.observability_enabled,
            "evaluation_enabled": self.evaluation_enabled,
            "quality_gate_enabled": self.quality_gate_enabled,
            "timeout_seconds": self.timeout_seconds,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "PlatformConfig":
        return cls(
            model=ModelConfig.from_dict(data.get("model", {})),
            evaluation=EvaluationConfig.from_dict(data.get("evaluation", {})),
            security=SecurityPolicy.from_dict(data.get("security", {})),
            mode=str(data.get("mode", "rule")),
            observability_enabled=bool(data.get("observability_enabled", True)),
            evaluation_enabled=bool(data.get("evaluation_enabled", True)),
            quality_gate_enabled=bool(data.get("quality_gate_enabled", True)),
            timeout_seconds=float(data.get("timeout_seconds", 60.0)),
        )

    @classmethod
    def from_env(cls) -> "PlatformConfig":
        """Load configuration from AGENT_* and PLATFORM_* environment variables."""
        import os
        return cls(
            model=ModelConfig(
                provider=os.environ.get("AGENT_LLM_PROVIDER", "mock"),
                model=os.environ.get("AGENT_LLM_MODEL", "default"),
                temperature=float(os.environ.get("AGENT_LLM_TEMPERATURE", "0.1")),
                max_tokens=int(os.environ.get("AGENT_LLM_MAX_TOKENS", "2048")),
                timeout_seconds=float(os.environ.get("AGENT_LLM_TIMEOUT", "30.0")),
            ),
            mode=os.environ.get("AGENT_MODE", "rule"),
            observability_enabled=os.environ.get("PLATFORM_OBSERVABILITY", "1") not in ("0", "false", "no"),
            evaluation_enabled=os.environ.get("PLATFORM_EVALUATION", "1") not in ("0", "false", "no"),
            quality_gate_enabled=os.environ.get("PLATFORM_QUALITY_GATE", "1") not in ("0", "false", "no"),
            timeout_seconds=float(os.environ.get("PLATFORM_TIMEOUT", "60.0")),
        )

    @classmethod
    def default(cls) -> "PlatformConfig":
        return cls()
