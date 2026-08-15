from __future__ import annotations

from ai_platform.evaluation.result import EvaluationResult


def test_evaluation_result_creation_and_merge():
    score = EvaluationResult(success=True, score=0.8, metrics={"a": 1}, details={"d": 1})
    judge = EvaluationResult(success=True, score=1.0, metrics={"b": 2}, details={"j": 2})

    merged = score.merge(judge, namespace="judge")
    assert merged.success is True
    assert merged.score == 0.9
    assert merged.metrics["a"] == 1
    assert merged.metrics["judge.b"] == 2
    assert merged.details["judge"] == {"j": 2}


def test_evaluation_result_as_dict():
    result = EvaluationResult(
        success=False,
        score=0.2,
        metrics={"m": 1},
        details={"d": 2},
        errors={"e": "boom"},
        metadata={"x": "y"},
    )
    data = result.as_dict()
    assert data["success"] is False
    assert data["score"] == 0.2
    assert data["metrics"]["m"] == 1
    assert data["errors"]["e"] == "boom"


def test_merge_with_failure():
    a = EvaluationResult(success=True, score=1.0)
    b = EvaluationResult(success=False, score=0.0)
    merged = a.merge(b)
    assert merged.success is False


def test_merge_score_none_propagation():
    a = EvaluationResult(success=True, score=None)
    b = EvaluationResult(success=True, score=0.8)
    merged = a.merge(b)
    assert merged.score == 0.8


def test_merge_both_scores_none():
    a = EvaluationResult(success=True, score=None)
    b = EvaluationResult(success=True, score=None)
    merged = a.merge(b)
    assert merged.score is None


def test_merge_no_namespace_flat_update():
    a = EvaluationResult(success=True, metrics={"a": 1})
    b = EvaluationResult(success=True, metrics={"b": 2})
    merged = a.merge(b)
    assert merged.metrics["a"] == 1
    assert merged.metrics["b"] == 2


def test_merge_namespace_errors():
    a = EvaluationResult(success=True)
    b = EvaluationResult(success=True, errors={"err": "boom"})
    merged = a.merge(b, namespace="n")
    assert merged.errors == {"n": {"err": "boom"}}
