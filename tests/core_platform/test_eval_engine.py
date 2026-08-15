from __future__ import annotations

from ai_platform.evaluation.engine import EvaluationEngine
from ai_platform.evaluation.evaluator import BaseEvaluator
from ai_platform.evaluation.result import EvaluationResult


class DummyEvaluator(BaseEvaluator):
    def __init__(self, name: str, value: float) -> None:
        self.name = name
        self._value = value

    def evaluate(self, agent_result):
        return EvaluationResult(
            success=True,
            score=self._value,
            metrics={"score": self._value},
            details={"name": self.name},
        )


def test_engine_dispatches_evaluators():
    engine = EvaluationEngine(evaluators=[DummyEvaluator("a", 0.6), DummyEvaluator("b", 1.0)])
    result = engine.evaluate({"cases": []})
    assert result.success is True
    assert result.metrics["a.score"] == 0.6
    assert result.metrics["b.score"] == 1.0
    assert result.details["a"] == {"name": "a"}
    assert result.details["b"] == {"name": "b"}
