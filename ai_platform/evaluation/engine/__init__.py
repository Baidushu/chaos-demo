from __future__ import annotations

import time
from dataclasses import dataclass, field
from typing import Any

from ai_platform.evaluation.evaluator import BaseEvaluator
from ai_platform.evaluation.result import EvaluationResult
from ai_platform.observability.collector import get_collector
from ai_platform.observability.event import EvaluationEvent


@dataclass(slots=True)
class EvaluationEngine:
    evaluators: list[BaseEvaluator] = field(default_factory=list)

    def register(self, evaluator: BaseEvaluator) -> None:
        self.evaluators.append(evaluator)

    def evaluate(self, agent_output: Any) -> EvaluationResult:
        collector = get_collector()
        trace_id = ""
        start_time = time.perf_counter()

        if collector is not None and collector.active_trace is not None:
            trace_id = collector.active_trace.trace_id
            collector.record(
                EvaluationEvent.start(
                    trace_id,
                    evaluators=[e.name for e in self.evaluators],
                )
            )

        combined = EvaluationResult(success=True)
        for evaluator in self.evaluators:
            result = evaluator.evaluate(agent_output)
            combined = combined.merge(result, namespace=evaluator.name)

        # Extract security_score from agent output metadata if present
        sec_score = self._extract_security_score(agent_output)
        if sec_score is not None:
            combined.metrics["security_score"] = sec_score
            combined.security_score = sec_score
            combined.metrics["security_assessed"] = True
        else:
            combined.metrics["security_assessed"] = False

        duration_ms = (time.perf_counter() - start_time) * 1000

        if collector is not None and collector.active_trace is not None:
            collector.record(
                EvaluationEvent.result(
                    trace_id,
                    score=combined.score,
                    success=combined.success,
                    metrics=combined.metrics,
                    duration_ms=duration_ms,
                )
            )

        return combined

    @staticmethod
    def _extract_security_score(agent_output: Any) -> float | None:
        """Extract security score from agent output."""
        # Check if output has security metadata
        if agent_output is None:
            return None
        # AgentState with metadata
        if hasattr(agent_output, "metadata") and isinstance(agent_output.metadata, dict):
            sec_result = agent_output.metadata.get("security_result")
            if sec_result and isinstance(sec_result, dict):
                passed = sec_result.get("passed", True)
                risk_level = sec_result.get("risk_level", "none")
                return _risk_to_score(passed, risk_level)
            sec_score = agent_output.metadata.get("security_score")
            if sec_score is not None:
                return float(sec_score)
        return None


_RISK_SCORES: dict[str, float] = {
    "none": 100.0,
    "low": 85.0,
    "medium": 60.0,
    "high": 30.0,
    "critical": 0.0,
}


def _risk_to_score(passed: bool, risk_level: str) -> float:
    """Convert a security risk level to a 0-100 score."""
    if passed:
        return 100.0
    return _RISK_SCORES.get(risk_level, 50.0)
