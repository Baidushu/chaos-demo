from __future__ import annotations

from pathlib import Path

from ai_platform.evaluation.report import evaluate_prompt_regression, score_agent_eval


def test_evaluate_prompt_regression_builds_doc_and_markdown():
    result, doc, markdown = evaluate_prompt_regression(
        baseline={
            "tool_selection_accuracy": 0.9,
            "arg_accuracy": 0.85,
            "task_success_rate": 0.8,
            "retry_rate": 0.1,
            "avg_tool_calls_per_task": 1.5,
            "avg_token_per_task": 100.0,
            "hallucination_rate": 0.0,
            "planner_invalid_rate": 0.05,
        },
        candidate={
            "tool_selection_accuracy": 0.9,
            "arg_accuracy": 0.85,
            "task_success_rate": 0.8,
            "retry_rate": 0.1,
            "avg_tool_calls_per_task": 1.5,
            "avg_token_per_task": 100.0,
            "hallucination_rate": 0.0,
            "planner_invalid_rate": 0.05,
        },
        thresholds={
            "max_tool_selection_accuracy_drop": 0.0,
            "max_arg_accuracy_drop": 0.05,
            "max_retry_rate_surge": 0.15,
            "max_planner_invalid_rate_surge": 0.10,
        },
        metadata={
            "generated_at": 1,
            "chaos_mode": "none",
            "chaos_fail_rate": 0.0,
            "chaos_latency_ms": 0,
            "baseline_variant": "baseline",
            "candidate_variant": "candidate",
            "paths": {"baseline_score": "b.json", "candidate_score": "c.json"},
        },
    )
    assert result.success is True
    assert doc["gate_pass"] is True
    assert "Prompt regression" in markdown


def test_score_agent_eval_writes_outputs(tmp_path: Path):
    raw_path = tmp_path / "raw.json"
    raw_path.write_text(
        '{"generated_at":1,"chaos_mode":"none","chaos_fail_rate":0.0,"chaos_latency_ms":0,'
        '"cases":[{"id":"case-1","category":"normal","input":"query",'
        '"expected_tools":["query_order"],"called_tools":["query_order"],'
        '"expected_args":{"order_id":"A1001"},"called_args":{"order_id":"A1001"},'
        '"retry_count":0,"tool_calls_count":1,"token_usage":10,"token_usage_estimated":10,'
        '"token_usage_llm":8,"final_response":"done","planner_valid":true,"planner_fallback":false}]}',
        encoding="utf-8",
    )
    score_path = tmp_path / "score.json"
    md_path = tmp_path / "score.md"
    review_path = tmp_path / "review.jsonl"

    result = score_agent_eval(
        raw_path=raw_path,
        score_path=score_path,
        md_path=md_path,
        review_path=review_path,
        judge_enabled=False,
        judge_sample_rate=0.0,
        skip_judge=True,
        seed=42,
    )
    assert result.success is True
    assert score_path.exists()
    assert md_path.exists()
    assert review_path.exists()
