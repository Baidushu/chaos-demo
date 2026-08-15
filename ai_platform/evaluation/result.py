from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass(slots=True)
class EvaluationResult:
    success: bool
    score: float | None = None
    metrics: dict[str, Any] = field(default_factory=dict)
    details: dict[str, Any] = field(default_factory=dict)
    errors: dict[str, Any] = field(default_factory=dict)
    metadata: dict[str, Any] = field(default_factory=dict)
    security_score: float | None = None  # 0-100, 100 = fully secure, None = not assessed

    def merge(self, other: "EvaluationResult", *, namespace: str | None = None) -> "EvaluationResult":
        merged_metrics = dict(self.metrics)
        merged_details = dict(self.details)
        merged_errors = dict(self.errors)
        merged_metadata = dict(self.metadata)

        if namespace:
            merged_details[namespace] = other.details
            if other.errors:
                merged_errors[namespace] = other.errors
            merged_metadata[namespace] = other.metadata
            for key, value in other.metrics.items():
                merged_metrics[f"{namespace}.{key}"] = value
        else:
            merged_metrics.update(other.metrics)
            merged_details.update(other.details)
            merged_errors.update(other.errors)
            merged_metadata.update(other.metadata)

        score = self.score
        if other.score is not None:
            score = other.score if score is None else (score + other.score) / 2.0

        # Merge security_score: keep the lowest (most conservative)
        sec_score = self.security_score
        if other.security_score is not None:
            sec_score = (
                other.security_score
                if sec_score is None
                else min(sec_score, other.security_score)
            )

        return EvaluationResult(
            success=self.success and other.success,
            score=score,
            metrics=merged_metrics,
            details=merged_details,
            errors=merged_errors,
            metadata=merged_metadata,
            security_score=sec_score,
        )

    def as_dict(self) -> dict[str, Any]:
        return {
            "success": self.success,
            "score": self.score,
            "metrics": dict(self.metrics),
            "details": dict(self.details),
            "errors": dict(self.errors),
            "metadata": dict(self.metadata),
            "security_score": self.security_score,
        }
