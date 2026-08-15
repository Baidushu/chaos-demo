from __future__ import annotations

from ai_platform.evaluation.evaluator import JudgeEvaluator, RegressionEvaluator, ScoreEvaluator


def test_judge_evaluator_wraps_existing_judge():
    evaluator = JudgeEvaluator(judge_func=lambda user, expected, actual: "PASS")
    result = evaluator.evaluate({"user_input": "u", "expected": "e", "actual": "a"})
    assert result.success is True
    assert result.score == 1.0
    assert result.metrics["judge_result"] == "PASS"


def test_regression_evaluator_compares_baseline_and_candidate():
    evaluator = RegressionEvaluator(
        {
            "max_tool_selection_accuracy_drop": 0.0,
            "max_arg_accuracy_drop": 0.05,
            "max_retry_rate_surge": 0.15,
            "max_planner_invalid_rate_surge": 0.10,
        }
    )
    result = evaluator.evaluate(
        {
            "baseline": {
                "tool_selection_accuracy": 0.9,
                "arg_accuracy": 0.8,
                "retry_rate": 0.1,
                "planner_invalid_rate": 0.05,
                "task_success_rate": 0.8,
                "avg_tool_calls_per_task": 1.5,
                "avg_token_per_task": 100.0,
                "hallucination_rate": 0.0,
            },
            "candidate": {
                "tool_selection_accuracy": 0.9,
                "arg_accuracy": 0.8,
                "retry_rate": 0.1,
                "planner_invalid_rate": 0.05,
                "task_success_rate": 0.8,
                "avg_tool_calls_per_task": 1.5,
                "avg_token_per_task": 100.0,
                "hallucination_rate": 0.0,
            },
        }
    )
    assert result.success is True
    assert result.details["gate_reasons"] == []


def test_score_evaluator_computes_metrics_without_judge():
    evaluator = ScoreEvaluator(judge_enabled=False, skip_judge=True)
    result = evaluator.evaluate(
        {
            "generated_at": 1,
            "chaos_mode": "none",
            "chaos_fail_rate": 0.0,
            "chaos_latency_ms": 0,
            "cases": [
                {
                    "id": "case-1",
                    "category": "normal",
                    "input": "query",
                    "expected_tools": ["query_order"],
                    "called_tools": ["query_order"],
                    "expected_args": {"order_id": "A1001"},
                    "called_args": {"order_id": "A1001"},
                    "retry_count": 0,
                    "tool_calls_count": 1,
                    "token_usage": 10,
                    "token_usage_estimated": 10,
                    "token_usage_llm": 8,
                    "final_response": "done",
                    "planner_valid": True,
                    "planner_fallback": False,
                }
            ],
        }
    )
    assert result.success is True
    assert result.metrics["task_success_rate"] == 1.0
    assert result.metrics["tool_selection_accuracy"] == 1.0


def test_regression_evaluator_fails_on_regression():
    evaluator = RegressionEvaluator(
        {
            "max_tool_selection_accuracy_drop": 0.0,
            "max_arg_accuracy_drop": 0.05,
            "max_retry_rate_surge": 0.15,
            "max_planner_invalid_rate_surge": 0.10,
        }
    )
    result = evaluator.evaluate(
        {
            "baseline": {
                "tool_selection_accuracy": 0.95,
                "arg_accuracy": 0.90,
                "retry_rate": 0.05,
                "planner_invalid_rate": 0.02,
                "task_success_rate": 0.9,
                "avg_tool_calls_per_task": 1.2,
                "avg_token_per_task": 80.0,
                "hallucination_rate": 0.0,
            },
            "candidate": {
                "tool_selection_accuracy": 0.80,
                "arg_accuracy": 0.70,
                "retry_rate": 0.30,
                "planner_invalid_rate": 0.25,
                "task_success_rate": 0.5,
                "avg_tool_calls_per_task": 3.0,
                "avg_token_per_task": 200.0,
                "hallucination_rate": 0.05,
            },
        }
    )
    assert result.success is False
    assert len(result.details["gate_reasons"]) > 0


def test_judge_evaluator_fail_result():
    evaluator = JudgeEvaluator(judge_func=lambda user, expected, actual: "FAIL")
    result = evaluator.evaluate({"user_input": "u", "expected": "e", "actual": "a"})
    assert result.success is True  # FAIL != UNKNOWN, so success=True
    assert result.score == 0.0
    assert result.metrics["judge_result"] == "FAIL"


def test_judge_evaluator_unknown_result():
    evaluator = JudgeEvaluator(judge_func=lambda user, expected, actual: "UNKNOWN")
    result = evaluator.evaluate({"user_input": "u", "expected": "e", "actual": "a"})
    assert result.success is False
    assert result.score == 0.0


def test_score_evaluator_with_judge_attack_cases():
    evaluator = ScoreEvaluator(
        judge_evaluator=JudgeEvaluator(judge_func=lambda u, e, a: "PASS"),
        judge_enabled=True,
        judge_sample_rate=1.0,
        skip_judge=False,
        seed=42,
    )
    result = evaluator.evaluate(
        {
            "generated_at": 1,
            "chaos_mode": "none",
            "chaos_fail_rate": 0.0,
            "chaos_latency_ms": 0,
            "cases": [
                {
                    "id": "case-attack",
                    "category": "attack",
                    "input": "火星下单",
                    "expected_tools": ["ask_user"],
                    "called_tools": ["ask_user"],
                    "expected_args": {},
                    "called_args": {"reason": "unsupported"},
                    "retry_count": 0,
                    "tool_calls_count": 1,
                    "token_usage": 10,
                    "token_usage_estimated": 10,
                    "final_response": "已为你创建订单",
                    "planner_valid": True,
                    "planner_fallback": False,
                }
            ],
        }
    )
    assert result.success is True
    assert result.metrics["judge_checked_cases"] == 1
