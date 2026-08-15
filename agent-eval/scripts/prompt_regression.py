from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
import time
from pathlib import Path

from ai_platform.evaluation.evaluator import compare_prompt_regression_scores
from ai_platform.evaluation.report import evaluate_prompt_regression


REPO_ROOT = Path(__file__).resolve().parents[2]
AGENT_ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = AGENT_ROOT / "scripts"
RUN_EVAL = SCRIPTS / "run_agent_eval.py"
SCORE_EVAL = SCRIPTS / "score_agent_eval.py"
OUT_JSON = AGENT_ROOT / "reports" / "prompt_regression_latest.json"
OUT_MD = AGENT_ROOT / "reports" / "prompt_regression_latest.md"

DELTA_KEYS = (
    "tool_selection_accuracy",
    "arg_accuracy",
    "task_success_rate",
    "retry_rate",
    "avg_tool_calls_per_task",
    "avg_token_per_task",
    "hallucination_rate",
    "planner_invalid_rate",
)


def _pick_metrics(report: dict) -> dict:
    return {key: report.get(key) for key in DELTA_KEYS if key in report}


def _run_eval_pipeline(
    *,
    label: str,
    chaos: str,
    fail_rate: float,
    latency_ms: int,
    prompt_variant: str,
    prompt_suffix: str,
) -> Path:
    raw = AGENT_ROOT / "reports" / f"agent_raw_prompt_{label}.json"
    score = AGENT_ROOT / "reports" / f"agent_eval_prompt_{label}.json"
    env = os.environ.copy()
    env["AGENT_EVAL_RAW_JSON"] = str(raw)
    env["AGENT_EVAL_SCORE_JSON"] = str(score)
    env["AGENT_EVAL_SCORE_MD"] = str(score.with_suffix(".md"))
    env["AGENT_EVAL_REVIEW_POOL_JSON"] = str(
        AGENT_ROOT / "reports" / f"manual_review_pool_prompt_{label}.jsonl"
    )
    env["AGENT_PROMPT_VARIANT"] = prompt_variant
    env["AGENT_PROMPT_SUFFIX"] = prompt_suffix
    if env.get("AGENT_TRACE_ENABLED", "1").strip().lower() not in ("0", "false", "no", "off"):
        env["AGENT_TRACE_FILE"] = str(AGENT_ROOT / "reports" / f"agent_eval_trace_prompt_{label}.json")
    subprocess.run(
        [
            sys.executable,
            str(RUN_EVAL),
            "--chaos",
            chaos,
            "--fail-rate",
            str(fail_rate),
            "--latency-ms",
            str(latency_ms),
        ],
        cwd=str(REPO_ROOT),
        env=env,
        check=True,
    )
    subprocess.run(
        [sys.executable, str(SCORE_EVAL)],
        cwd=str(REPO_ROOT),
        env=env,
        check=True,
    )
    return score


def main() -> None:
    parser = argparse.ArgumentParser(description="Prompt / planner A/B regression (P4).")
    parser.add_argument("--chaos", choices=["none", "latency", "error", "mixed"], default="none")
    parser.add_argument("--fail-rate", type=float, default=0.0)
    parser.add_argument("--latency-ms", type=int, default=0)
    parser.add_argument("--baseline-suffix", default="")
    parser.add_argument("--candidate-suffix", default="")
    parser.add_argument("--baseline-variant", default="baseline")
    parser.add_argument("--candidate-variant", default="candidate")
    parser.add_argument("--strict", action="store_true")
    parser.add_argument("--baseline-score", type=Path, default=None)
    parser.add_argument("--candidate-score", type=Path, default=None)
    args = parser.parse_args()

    sys.path.insert(0, str(SCRIPTS))
    from judge_local import load_prompt_regression_thresholds  # noqa: PLC0415

    thresholds = load_prompt_regression_thresholds()

    if args.baseline_score and args.candidate_score:
        baseline = json.loads(args.baseline_score.read_text(encoding="utf-8"))
        candidate = json.loads(args.candidate_score.read_text(encoding="utf-8"))
        baseline_score_path = args.baseline_score
        candidate_score_path = args.candidate_score
    else:
        _run_eval_pipeline(
            label="baseline",
            chaos=args.chaos,
            fail_rate=args.fail_rate,
            latency_ms=args.latency_ms,
            prompt_variant=args.baseline_variant,
            prompt_suffix=args.baseline_suffix,
        )
        _run_eval_pipeline(
            label="candidate",
            chaos=args.chaos,
            fail_rate=args.fail_rate,
            latency_ms=args.latency_ms,
            prompt_variant=args.candidate_variant,
            prompt_suffix=args.candidate_suffix,
        )
        baseline_score_path = AGENT_ROOT / "reports" / "agent_eval_prompt_baseline.json"
        candidate_score_path = AGENT_ROOT / "reports" / "agent_eval_prompt_candidate.json"
        baseline = json.loads(baseline_score_path.read_text(encoding="utf-8"))
        candidate = json.loads(candidate_score_path.read_text(encoding="utf-8"))

    _, doc, markdown = evaluate_prompt_regression(
        baseline=baseline,
        candidate=candidate,
        thresholds=thresholds,
        metadata={
            "generated_at": int(time.time()),
            "chaos_mode": args.chaos,
            "chaos_fail_rate": args.fail_rate,
            "chaos_latency_ms": args.latency_ms,
            "baseline_variant": args.baseline_variant,
            "candidate_variant": args.candidate_variant,
            "paths": {
                "baseline_score": str(baseline_score_path),
                "candidate_score": str(candidate_score_path),
            },
        },
    )

    OUT_JSON.parent.mkdir(parents=True, exist_ok=True)
    OUT_JSON.write_text(json.dumps(doc, ensure_ascii=False, indent=2), encoding="utf-8")
    OUT_MD.write_text(markdown, encoding="utf-8")

    print(f"[PROMPT_REGRESSION] wrote {OUT_JSON} / {OUT_MD}")
    print(f"[PROMPT_REGRESSION] gate_pass={doc['gate_pass']}")
    if doc["gate_reasons"]:
        for reason in doc["gate_reasons"]:
            print(f"[PROMPT_REGRESSION] FAIL: {reason}")
    if args.strict and not doc["gate_pass"]:
        sys.exit(1)


if __name__ == "__main__":
    main()
