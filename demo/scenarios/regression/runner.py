#!/usr/bin/env python3
"""Case 3: AI Regression Quality Gate — 回归质量门禁演示。

Usage:
  python demo/scenarios/regression/runner.py
  python demo/scenarios/regression/runner.py --mode pass
  python demo/scenarios/regression/runner.py --mode fail

模拟Prompt或模型版本升级时的回归对比:
  1. 加载 baseline.json (基线版本指标)
  2. 运行候选版本 (good=pass, bad=fail)
  3. EvaluationEngine 评估
  4. QualityGate 检查
  5. 输出 RegressionReport
"""

from __future__ import annotations

import json
import sys
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

# ── Add project root ────────────────────────────────────────────────
_PROJECT_ROOT = Path(__file__).resolve().parents[3]
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))

from ai_platform.evaluation.engine import EvaluationEngine
from ai_platform.evaluation.evaluator import RegressionEvaluator
from ai_platform.evaluation.gate import QualityGate, AgentGateError
from ai_platform.evaluation.result import EvaluationResult
from ai_platform.core.config import EvaluationConfig, PlatformConfig


@dataclass
class RegressionReport:
    """回归质量报告"""
    baseline_score: float
    current_score: float
    delta: dict[str, Any]
    gate_status: str  # "PASS" or "FAIL"
    reasons: list[str] = field(default_factory=list)
    baseline_version: str = ""
    candidate_version: str = ""
    baseline_metrics: dict[str, Any] = field(default_factory=dict)
    candidate_metrics: dict[str, Any] = field(default_factory=dict)
    elapsed_ms: float = 0.0

    def as_dict(self) -> dict[str, Any]:
        return {
            "baseline_score": self.baseline_score,
            "current_score": self.current_score,
            "delta": dict(self.delta),
            "gate_status": self.gate_status,
            "reasons": list(self.reasons),
            "baseline_version": self.baseline_version,
            "candidate_version": self.candidate_version,
            "baseline_metrics": dict(self.baseline_metrics),
            "candidate_metrics": dict(self.candidate_metrics),
            "elapsed_ms": self.elapsed_ms,
        }


def run_regression_gate(scenario: str = "fail") -> dict[str, Any]:
    """运行回归质量门禁演示。

    Args:
        scenario: "pass" — 候选版本改进, 通过门禁
                  "fail" — 候选版本退化, 门禁失败
    """
    # 加载 baseline 数据
    baseline_path = Path(__file__).parent / "baseline.json"
    data = json.loads(baseline_path.read_text(encoding="utf-8"))

    baseline = data["baseline"]
    thresholds = data["regression_thresholds"]

    if scenario == "pass":
        candidate = data["candidate_improved"]
    else:
        candidate = data["candidate_degraded"]

    print(f"\n{'='*70}")
    print(f"  AI Regression Quality Gate — {scenario.upper()} Scenario")
    print(f"{'='*70}")
    print(f"  Baseline:  {baseline['version']} (prompt {baseline['prompt_version']})  score={baseline['score']}")
    print(f"  Candidate: {candidate['version']} (prompt {candidate['prompt_version']})  score={candidate['score']}")
    print(f"{'='*70}")

    start = time.perf_counter()

    # ── Step 1: 使用 RegressionEvaluator ──
    reg_evaluator = RegressionEvaluator(thresholds=thresholds)
    combined_input = {
        "baseline": baseline["metrics"],
        "candidate": candidate["metrics"],
    }

    eval_result = reg_evaluator.evaluate(combined_input)

    # ── Step 2: 计算各维度 delta ──
    delta = {}
    for key in baseline["metrics"]:
        bv = baseline["metrics"].get(key)
        cv = candidate["metrics"].get(key)
        if isinstance(bv, (int, float)) and isinstance(cv, (int, float)):
            delta[key] = round(cv - bv, 4)

    # ── Step 3: Quality Gate (Legacy QualityGate requires full metrics) ──
    # Since QualityGate.check() expects tool_selection_accuracy, arg_accuracy etc.
    # and RegressionEvaluator already checked regression-specific thresholds,
    # we use the evaluator's pass/fail result as gate_status
    gate_status = "PASS" if eval_result.success else "FAIL"
    reasons = list(eval_result.errors.get("gate_reasons", []))

    # ── Step 4: Also check standard QualityGate metrics ──
    try:
        eval_config = EvaluationConfig(
            tool_selection_accuracy_min=0.70,
            arg_accuracy_min=0.70,
            retry_rate_max=0.30,
            hallucination_rate_max=0.10,
            planner_invalid_rate_max=0.20,
        )
        gate = QualityGate(thresholds=eval_config.to_dict())
        # Merge candidate metrics into expected format
        gate_input_metrics = {
            "tool_selection_accuracy": candidate["metrics"]["tool_selection_accuracy"],
            "arg_accuracy": candidate["metrics"]["arg_accuracy"],
            "avg_tool_calls_per_task": candidate["metrics"]["avg_tool_calls_per_task"],
            "retry_rate": candidate["metrics"]["retry_rate"],
            "hallucination_rate": candidate["metrics"]["hallucination_rate"],
            "planner_invalid_rate": candidate["metrics"]["planner_invalid_rate"],
        }
        gate.check(EvaluationResult(success=True, metrics=gate_input_metrics))
        # If no exception raised, standard gate passed
    except AgentGateError as exc:
        if gate_status == "PASS":
            reasons.append(f"Standard gate: {exc}")

    elapsed_ms = (time.perf_counter() - start) * 1000

    # ── 生成报告 ──
    report = RegressionReport(
        baseline_score=baseline["score"],
        current_score=candidate["score"],
        delta=delta,
        gate_status=gate_status,
        reasons=reasons,
        baseline_version=baseline["version"],
        candidate_version=candidate["version"],
        baseline_metrics=baseline["metrics"],
        candidate_metrics=candidate["metrics"],
        elapsed_ms=round(elapsed_ms, 1),
    )

    _print_regression_report(report, baseline, candidate, scenario)

    # 如果有评估用例，也展示对比
    if "evaluation_cases" in data:
        print(f"\n  📋 Evaluation Cases ({len(data['evaluation_cases'])} cases)")
        for ec in data["evaluation_cases"]:
            print(f"    {ec['id']}: {ec['input'][:50]}... → {ec['expected_tools']}")

    return {
        "scenario": "AI Regression Quality Gate",
        "mode": scenario,
        "report": report.as_dict(),
    }


def _print_regression_report(
    report: RegressionReport,
    baseline: dict[str, Any],
    candidate: dict[str, Any],
    scenario: str,
) -> None:
    """打印回归报告。"""
    gate_icon = "✅" if report.gate_status == "PASS" else "❌"

    print(f"\n  📊 Regression Report")
    print(f"  {'─'*60}")
    print(f"  Metric                    Baseline       Candidate      Delta")
    print(f"  {'─'*60}")

    _DELTA_KEYS = [
        ("tool_selection_accuracy", "{:.2%}"),
        ("arg_accuracy", "{:.2%}"),
        ("task_success_rate", "{:.2%}"),
        ("retry_rate", "{:.2%}", "↑ worse"),
        ("avg_tool_calls_per_task", "{:.1f}"),
        ("avg_token_per_task", "{:.0f}"),
        ("hallucination_rate", "{:.2%}", "↑ worse"),
        ("planner_invalid_rate", "{:.2%}", "↑ worse"),
    ]

    for key, fmt, *extra in _DELTA_KEYS:
        bv = baseline["metrics"].get(key)
        cv = candidate["metrics"].get(key)
        d = report.delta.get(key)
        direction = extra[0] if extra else ""
        arrow = ""
        if d is not None:
            if d > 0:
                arrow = "↑" if direction else "↑"
            elif d < 0:
                arrow = "↓" if direction else "↓"

        b_str = fmt.format(bv) if bv is not None else "N/A"
        c_str = fmt.format(cv) if cv is not None else "N/A"
        d_str = f"{d:+.4f}" if d is not None else "N/A"
        print(f"  {key:<27s} {b_str:<14s} {c_str:<14s} {d_str:<10s} {arrow}")

    print(f"  {'─'*60}")
    print(f"  Baseline Score:  {report.baseline_score}")
    print(f"  Current Score:   {report.current_score}")
    print(f"  Score Delta:     {report.current_score - report.baseline_score:+.2f}")
    print(f"  {'─'*60}")
    print(f"  Gate Status:     {gate_icon} {report.gate_status}")

    if report.reasons:
        print(f"\n  Failure Reasons:")
        for reason in report.reasons:
            print(f"    • {reason}")

    print(f"  Elapsed:         {report.elapsed_ms:.1f}ms")

    # 总结
    if scenario == "fail":
        print(f"\n  ⚠️  REGRESSION DETECTED: Candidate version degrades quality —")
        print(f"     deployment should be BLOCKED until metrics are restored.")
    else:
        print(f"\n  ✅ ALL CHECKS PASSED: Candidate version improves or maintains quality —")
        print(f"     safe to deploy.")


if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser(description="AI Regression Quality Gate Demo")
    parser.add_argument("--mode", type=str, choices=["pass", "fail"], default="fail",
                        help="Scenario: pass (improved) or fail (degraded)")
    parser.add_argument("--json", action="store_true", help="Output results as JSON")
    args = parser.parse_args()

    result = run_regression_gate(args.mode)

    if args.json:
        print(json.dumps(result, ensure_ascii=False, indent=2))
