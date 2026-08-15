from __future__ import annotations

import pytest

from ai_platform.evaluation.gate import AgentGateError, QualityGate
from ai_platform.evaluation.result import EvaluationResult


def _report(**overrides):
    base = {
        "tool_selection_accuracy": 0.9,
        "arg_accuracy": 0.85,
        "avg_tool_calls_per_task": 1.5,
        "retry_rate": 0.1,
        "hallucination_rate": 0.0,
        "planner_invalid_rate": 0.05,
    }
    base.update(overrides)
    return base


def test_quality_gate_passes():
    gate = QualityGate(
        {
            "tool_selection_accuracy_min": 0.85,
            "arg_accuracy_min": 0.80,
            "avg_tool_calls_per_task_max": 3.5,
            "retry_rate_max": 0.20,
            "hallucination_rate_max": 0.10,
            "planner_invalid_rate_max": 0.15,
        }
    )
    assert gate.check(_report()) is True


def test_quality_gate_fails():
    gate = QualityGate(
        {
            "tool_selection_accuracy_min": 0.85,
            "arg_accuracy_min": 0.80,
            "avg_tool_calls_per_task_max": 3.5,
            "retry_rate_max": 0.20,
            "hallucination_rate_max": 0.10,
            "planner_invalid_rate_max": 0.15,
        }
    )
    with pytest.raises(AgentGateError, match="tool_selection_accuracy too low"):
        gate.check(_report(tool_selection_accuracy=0.5))


def test_quality_gate_with_evaluation_result():
    gate = QualityGate(
        {
            "tool_selection_accuracy_min": 0.85,
            "arg_accuracy_min": 0.80,
            "avg_tool_calls_per_task_max": 3.5,
            "retry_rate_max": 0.20,
            "hallucination_rate_max": 0.10,
            "planner_invalid_rate_max": 0.15,
        }
    )
    result = EvaluationResult(
        success=True,
        score=0.9,
        metrics=_report(),
    )
    assert gate.check(result) is True


def test_quality_gate_fails_arg_accuracy():
    gate = QualityGate(
        {
            "tool_selection_accuracy_min": 0.85,
            "arg_accuracy_min": 0.80,
            "avg_tool_calls_per_task_max": 3.5,
            "retry_rate_max": 0.20,
            "hallucination_rate_max": 0.10,
            "planner_invalid_rate_max": 0.15,
        }
    )
    with pytest.raises(AgentGateError, match="arg_accuracy too low"):
        gate.check(_report(arg_accuracy=0.5))


def test_quality_gate_fails_retry_rate():
    gate = QualityGate(
        {
            "tool_selection_accuracy_min": 0.85,
            "arg_accuracy_min": 0.80,
            "avg_tool_calls_per_task_max": 3.5,
            "retry_rate_max": 0.20,
            "hallucination_rate_max": 0.10,
            "planner_invalid_rate_max": 0.15,
        }
    )
    with pytest.raises(AgentGateError, match="retry_rate too high"):
        gate.check(_report(retry_rate=0.5))


def test_quality_gate_fails_avg_tool_calls():
    gate = QualityGate(
        {
            "tool_selection_accuracy_min": 0.85,
            "arg_accuracy_min": 0.80,
            "avg_tool_calls_per_task_max": 3.5,
            "retry_rate_max": 0.20,
            "hallucination_rate_max": 0.10,
            "planner_invalid_rate_max": 0.15,
        }
    )
    with pytest.raises(AgentGateError, match="avg_tool_calls_per_task too high"):
        gate.check(_report(avg_tool_calls_per_task=10.0))


def test_quality_gate_fails_hallucination():
    gate = QualityGate(
        {
            "tool_selection_accuracy_min": 0.85,
            "arg_accuracy_min": 0.80,
            "avg_tool_calls_per_task_max": 3.5,
            "retry_rate_max": 0.20,
            "hallucination_rate_max": 0.10,
            "planner_invalid_rate_max": 0.15,
        }
    )
    with pytest.raises(AgentGateError, match="hallucination_rate too high"):
        gate.check(_report(hallucination_rate=0.5))


def test_quality_gate_fails_planner_invalid():
    gate = QualityGate(
        {
            "tool_selection_accuracy_min": 0.85,
            "arg_accuracy_min": 0.80,
            "avg_tool_calls_per_task_max": 3.5,
            "retry_rate_max": 0.20,
            "hallucination_rate_max": 0.10,
            "planner_invalid_rate_max": 0.15,
        }
    )
    with pytest.raises(AgentGateError, match="planner_invalid_rate too high"):
        gate.check(_report(planner_invalid_rate=0.5))


def test_assert_pass_returns_report():
    gate = QualityGate(
        {
            "tool_selection_accuracy_min": 0.85,
            "arg_accuracy_min": 0.80,
            "avg_tool_calls_per_task_max": 3.5,
            "retry_rate_max": 0.20,
            "hallucination_rate_max": 0.10,
            "planner_invalid_rate_max": 0.15,
        }
    )
    report = gate.assert_pass(_report())
    assert report["tool_selection_accuracy"] == 0.9
