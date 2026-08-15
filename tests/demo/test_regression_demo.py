"""Test Case 3: AI Regression Quality Gate Demo."""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

_PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))

from demo.scenarios.regression.runner import run_regression_gate


class TestRegressionDemo:
    """验证质量回归 Demo 可运行且Gate正确触发。"""

    def test_regression_fail_scenario(self):
        """退化场景: 门禁应FAIL。"""
        result = run_regression_gate("fail")
        report = result["report"]
        assert report["gate_status"] == "FAIL"
        assert report["current_score"] < report["baseline_score"]
        assert len(report["reasons"]) > 0

    def test_regression_pass_scenario(self):
        """改进场景: 门禁应PASS。"""
        result = run_regression_gate("pass")
        report = result["report"]
        assert report["gate_status"] == "PASS"
        assert report["current_score"] > report["baseline_score"]
        assert len(report["reasons"]) == 0

    def test_regression_delta_calculated(self):
        """验证各维度delta计算正确。"""
        result = run_regression_gate("fail")
        report = result["report"]
        delta = report["delta"]
        # Key metrics should have negative deltas in fail scenario
        assert delta["tool_selection_accuracy"] < 0
        assert delta["arg_accuracy"] < 0
        assert delta["task_success_rate"] < 0
        # Worsening metrics should have positive deltas
        assert delta["retry_rate"] > 0
        assert delta["hallucination_rate"] > 0

    def test_regression_report_structure(self):
        """验证输出报告结构符合规范。"""
        result = run_regression_gate("fail")
        report = result["report"]
        required_fields = ["baseline_score", "current_score", "delta", "gate_status",
                          "reasons", "baseline_version", "candidate_version"]
        for field in required_fields:
            assert field in report, f"Missing field: {field}"
        assert isinstance(report["delta"], dict)
        assert isinstance(report["reasons"], list)

    def test_regression_fail_has_reasons(self):
        """退化场景有详细失败原因。"""
        result = run_regression_gate("fail")
        reasons = result["report"]["reasons"]
        assert any("tool_selection_accuracy" in reason for reason in reasons)
        assert any("arg_accuracy" in reason for reason in reasons)
        assert any("retry_rate" in reason for reason in reasons)

    def test_regression_score_delta(self):
        """验证评分变化。"""
        fail_result = run_regression_gate("fail")
        pass_result = run_regression_gate("pass")
        assert fail_result["report"]["current_score"] - fail_result["report"]["baseline_score"] < 0
        assert pass_result["report"]["current_score"] - pass_result["report"]["baseline_score"] > 0

    def test_regression_improved_all_metrics_better(self):
        """改进场景: 所有指标更优。"""
        result = run_regression_gate("pass")
        delta = result["report"]["delta"]
        improved = ["tool_selection_accuracy", "arg_accuracy", "task_success_rate"]
        reduced = ["retry_rate", "hallucination_rate", "planner_invalid_rate"]
        for key in improved:
            assert delta[key] > 0, f"{key} should improve in pass scenario"
        for key in reduced:
            assert delta[key] < 0, f"{key} should decrease in pass scenario"
