from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any

from ai_platform.evaluation.dataset import load_json, write_json, write_jsonl
from ai_platform.evaluation.engine import EvaluationEngine
from ai_platform.evaluation.evaluator import JudgeEvaluator, RegressionEvaluator, ScoreEvaluator
from ai_platform.evaluation.result import EvaluationResult


def score_agent_eval(
    *,
    raw_path: Path,
    score_path: Path,
    md_path: Path,
    review_path: Path,
    judge_enabled: bool,
    judge_sample_rate: float,
    skip_judge: bool,
    seed: int,
) -> EvaluationResult:
    raw_data = load_json(raw_path)
    engine = EvaluationEngine(
        evaluators=[
            ScoreEvaluator(
                judge_evaluator=JudgeEvaluator(),
                judge_enabled=judge_enabled,
                judge_sample_rate=judge_sample_rate,
                skip_judge=skip_judge,
                seed=seed,
            )
        ]
    )
    result = engine.evaluate(raw_data)
    report = _extract_namespaced_metrics(result, "score")
    review_pool = result.details.get("score", {}).get("review_pool", [])
    write_json(score_path, report)
    write_jsonl(review_path, review_pool)
    md_path.parent.mkdir(parents=True, exist_ok=True)
    md_path.write_text(_build_score_markdown(report, review_pool), encoding="utf-8")
    return result


def evaluate_prompt_regression(
    *,
    baseline: dict[str, Any],
    candidate: dict[str, Any],
    thresholds: dict[str, float],
    metadata: dict[str, Any],
) -> tuple[EvaluationResult, dict[str, Any], str]:
    engine = EvaluationEngine(evaluators=[RegressionEvaluator(thresholds)])
    result = engine.evaluate({"baseline": baseline, "candidate": candidate})
    reg_details = result.details.get("regression", {})
    reg_metrics = result.metrics.get("regression.delta", {})
    doc = {
        "generated_at": metadata["generated_at"],
        "chaos_mode": metadata["chaos_mode"],
        "chaos_fail_rate": metadata["chaos_fail_rate"],
        "chaos_latency_ms": metadata["chaos_latency_ms"],
        "baseline_variant": metadata["baseline_variant"],
        "candidate_variant": metadata["candidate_variant"],
        "paths": metadata["paths"],
        "baseline_metrics": reg_details.get("baseline_metrics", {}),
        "candidate_metrics": reg_details.get("candidate_metrics", {}),
        "delta": reg_metrics,
        "thresholds": thresholds,
        "gate_pass": result.success,
        "gate_reasons": reg_details.get("gate_reasons", []),
    }
    md = _build_prompt_regression_markdown(doc)
    return result, doc, md


def _extract_namespaced_metrics(result: EvaluationResult, namespace: str) -> dict[str, Any]:
    prefix = f"{namespace}."
    report = {}
    for key, value in result.metrics.items():
        if key.startswith(prefix):
            report[key[len(prefix) :]] = value
    return report


def _build_score_markdown(report: dict[str, Any], review_pool: list[dict[str, Any]]) -> str:
    judge_pass_rate_text = "N/A"
    if report.get("judge_pass_rate") is not None:
        judge_pass_rate_text = f"{report['judge_pass_rate']:.2%}"

    avg_llm_text = "N/A"
    if report.get("avg_token_llm_per_task") is not None:
        avg_llm_text = f"{report['avg_token_llm_per_task']:.1f}"

    def fmt_opt(value):
        return "N/A" if value is None else f"{value:.1f}"

    rt = report.get("retry_tax_ratio")
    retry_tax_line = "N/A" if rt is None else f"{rt:.2%}"

    lines = [
        "# Agent Eval Report",
        "",
        f"- chaos_mode: {report['chaos_mode']}",
        f"- chaos_fail_rate: {report['chaos_fail_rate']}",
        f"- chaos_latency_ms: {report['chaos_latency_ms']}",
        f"- total_cases: {report['total_cases']}",
        f"- tool_selection_accuracy: {report['tool_selection_accuracy']:.2%}",
        f"- call_sequence_accuracy: {report['call_sequence_accuracy']:.2%}",
        f"- arg_accuracy: {report['arg_accuracy']:.2%}",
        f"- task_success_rate: {report['task_success_rate']:.2%}",
        f"- retry_rate: {report['retry_rate']:.2%}",
        f"- avg_tool_calls_per_task: {report['avg_tool_calls_per_task']:.2f}",
        f"- avg_token_per_task: {report['avg_token_per_task']:.1f}",
        f"- max_token_per_task: {report['max_token_per_task']:.1f}",
        f"- p99_token_per_task: {fmt_opt(report['p99_token_per_task'])}",
        f"- avg_token_estimated_per_task: {report['avg_token_estimated_per_task']:.1f}",
        f"- avg_token_llm_per_task: {avg_llm_text}",
        f"- ollama_token_coverage: {report['ollama_token_coverage']:.2%}",
        "## Token by outcome",
        f"- avg_token_rule_pass: {fmt_opt(report['avg_token_rule_pass'])} "
        f"(n={int(report['total_cases']) - int(report['rule_fail_count'])})",
        f"- avg_token_rule_fail: {fmt_opt(report['avg_token_rule_fail'])} "
        f"(n={report['rule_fail_count']})",
        f"- avg_token_with_retry: {fmt_opt(report['avg_token_with_retry'])} "
        f"(n={report['retry_case_count']})",
        f"- avg_token_no_retry: {fmt_opt(report['avg_token_no_retry'])} "
        f"(n={report['no_retry_case_count']})",
        "## Retry tax（本轮单轮）",
        f"- retry_tax_ratio: {retry_tax_line} "
        f"(当前参考上限 {report['retry_tax_max_ref']:.0%})",
        f"- hallucination_rate: {report['hallucination_rate']:.2%}",
        f"- planner_invalid_rate: {report['planner_invalid_rate']:.2%}",
        f"- judge_checked_cases: {report['judge_checked_cases']}",
        f"- judge_pass_rate: {judge_pass_rate_text}",
        f"- manual_review_pool_size: {len(review_pool)}",
    ]
    return "\n".join(lines)


def _build_prompt_regression_markdown(doc: dict[str, Any]) -> str:
    lines = [
        "# Prompt regression (P4)",
        "",
        f"- gate_pass: **{doc['gate_pass']}**",
        (
            f"- chaos: {doc['chaos_mode']} "
            f"fail_rate={doc['chaos_fail_rate']} latency_ms={doc['chaos_latency_ms']}"
        ),
        "",
        "## Delta (candidate - baseline)",
        "",
        "| Metric | Baseline | Candidate | Delta |",
        "|---|---:|---:|---:|",
    ]
    baseline_metrics = doc["baseline_metrics"]
    candidate_metrics = doc["candidate_metrics"]
    for key, baseline_value in baseline_metrics.items():
        if key not in candidate_metrics:
            continue
        candidate_value = candidate_metrics[key]
        delta_value = doc["delta"].get(key)
        delta_text = "N/A" if delta_value is None else f"{float(delta_value):+.4f}"
        lines.append(
            f"| {key} | {float(baseline_value):.4f} | {float(candidate_value):.4f} | {delta_text} |"
        )
    lines.extend(["", "## Gate reasons", ""])
    if doc["gate_reasons"]:
        for reason in doc["gate_reasons"]:
            lines.append(f"- FAIL: {reason}")
    else:
        lines.append("- (none)")
    return "\n".join(lines)
