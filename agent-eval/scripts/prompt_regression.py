"""
P4：同一数据集下 Prompt / 规划器 A/B —— baseline 与 candidate 各跑一轮 eval+score，
对比关键指标并可选门禁（阈值见 agent-eval/config/eval_config.yaml 的 prompt_regression）。

- Ollama 模式：用环境变量 AGENT_PROMPT_SUFFIX 区分 candidate 与 baseline 的系统补充说明。
- 规则模式：两遍通常完全一致（用于验证流水线）；真实 A/B 请使用 AGENT_MODE=ollama。
"""
from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
import time
from pathlib import Path

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


def _pick_metrics(d: dict) -> dict:
    return {k: d.get(k) for k in DELTA_KEYS if k in d}


def compare_prompt_regression_scores(
    baseline: dict,
    candidate: dict,
    th: dict,
) -> tuple[bool, list[str], dict]:
    reasons: list[str] = []
    delta: dict = {}
    for k in DELTA_KEYS:
        if k not in baseline or k not in candidate:
            continue
        try:
            delta[k] = float(candidate[k]) - float(baseline[k])
        except (TypeError, ValueError):
            delta[k] = None

    bt = float(baseline["tool_selection_accuracy"])
    ct = float(candidate["tool_selection_accuracy"])
    if ct < bt - th["max_tool_selection_accuracy_drop"]:
        reasons.append(
            "tool_selection_accuracy dropped too much: "
            f"candidate={ct:.2%} baseline={bt:.2%} "
            f"(max_drop={th['max_tool_selection_accuracy_drop']:.2%})"
        )

    ba = float(baseline["arg_accuracy"])
    ca = float(candidate["arg_accuracy"])
    if ca < ba - th["max_arg_accuracy_drop"]:
        reasons.append(
            f"arg_accuracy dropped too much: candidate={ca:.2%} baseline={ba:.2%} "
            f"(max_drop={th['max_arg_accuracy_drop']:.2%})"
        )

    br = float(baseline["retry_rate"])
    cr = float(candidate["retry_rate"])
    if cr > br + th["max_retry_rate_surge"]:
        reasons.append(
            f"retry_rate surged too much: candidate={cr:.2%} baseline={br:.2%} "
            f"(max_surge={th['max_retry_rate_surge']:.2%})"
        )

    bip = float(baseline.get("planner_invalid_rate", 0) or 0)
    cip = float(candidate.get("planner_invalid_rate", 0) or 0)
    if cip > bip + th["max_planner_invalid_rate_surge"]:
        reasons.append(
            f"planner_invalid_rate surged too much: candidate={cip:.2%} baseline={bip:.2%} "
            f"(max_surge={th['max_planner_invalid_rate_surge']:.2%})"
        )

    return (len(reasons) == 0), reasons, delta


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
    parser.add_argument(
        "--baseline-suffix",
        default="",
        help="AGENT_PROMPT_SUFFIX for baseline run (Ollama only; appended to router prompt).",
    )
    parser.add_argument(
        "--candidate-suffix",
        default="",
        help="AGENT_PROMPT_SUFFIX for candidate run.",
    )
    parser.add_argument(
        "--baseline-variant",
        default="baseline",
        help="Metadata label stored in raw JSON (AGENT_PROMPT_VARIANT).",
    )
    parser.add_argument(
        "--candidate-variant",
        default="candidate",
        help="Metadata label for candidate run.",
    )
    parser.add_argument(
        "--strict",
        action="store_true",
        help="Exit 1 if regression gate fails.",
    )
    parser.add_argument(
        "--baseline-score",
        type=Path,
        default=None,
        help="Skip eval; load existing score JSON (for tests / replay).",
    )
    parser.add_argument(
        "--candidate-score",
        type=Path,
        default=None,
        help="Skip eval; load existing score JSON.",
    )
    args = parser.parse_args()

    sys.path.insert(0, str(SCRIPTS))
    from judge_local import load_prompt_regression_thresholds  # noqa: PLC0415

    th = load_prompt_regression_thresholds()

    if args.baseline_score and args.candidate_score:
        baseline = json.loads(args.baseline_score.read_text(encoding="utf-8"))
        candidate = json.loads(args.candidate_score.read_text(encoding="utf-8"))
        b_score_path = args.baseline_score
        c_score_path = args.candidate_score
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
        b_score_path = AGENT_ROOT / "reports" / "agent_eval_prompt_baseline.json"
        c_score_path = AGENT_ROOT / "reports" / "agent_eval_prompt_candidate.json"
        baseline = json.loads(b_score_path.read_text(encoding="utf-8"))
        candidate = json.loads(c_score_path.read_text(encoding="utf-8"))

    ok, reasons, delta = compare_prompt_regression_scores(baseline, candidate, th)
    doc = {
        "generated_at": int(time.time()),
        "chaos_mode": args.chaos,
        "chaos_fail_rate": args.fail_rate,
        "chaos_latency_ms": args.latency_ms,
        "baseline_variant": args.baseline_variant,
        "candidate_variant": args.candidate_variant,
        "paths": {
            "baseline_score": str(b_score_path),
            "candidate_score": str(c_score_path),
        },
        "baseline_metrics": _pick_metrics(baseline),
        "candidate_metrics": _pick_metrics(candidate),
        "delta": delta,
        "thresholds": th,
        "gate_pass": ok,
        "gate_reasons": reasons,
    }
    OUT_JSON.parent.mkdir(parents=True, exist_ok=True)
    OUT_JSON.write_text(json.dumps(doc, ensure_ascii=False, indent=2), encoding="utf-8")

    md = [
        "# Prompt regression (P4)",
        "",
        f"- gate_pass: **{ok}**",
        f"- chaos: {args.chaos} fail_rate={args.fail_rate} latency_ms={args.latency_ms}",
        "",
        "## Delta (candidate - baseline)",
        "",
        "| Metric | Baseline | Candidate | Delta |",
        "|---|---:|---:|---:|",
    ]
    bm = doc["baseline_metrics"]
    cm = doc["candidate_metrics"]
    for k in DELTA_KEYS:
        if k not in bm or k not in cm:
            continue
        b, c, dv = bm[k], cm[k], delta.get(k)
        dtxt = "N/A" if dv is None else f"{dv:+.4f}"
        md.append(f"| {k} | {float(b):.4f} | {float(c):.4f} | {dtxt} |")
    md.extend(["", "## Gate reasons", ""])
    if reasons:
        for r in reasons:
            md.append(f"- FAIL: {r}")
    else:
        md.append("- (none)")
    OUT_MD.write_text("\n".join(md), encoding="utf-8")

    print(f"[PROMPT_REGRESSION] wrote {OUT_JSON} / {OUT_MD}")
    print(f"[PROMPT_REGRESSION] gate_pass={ok}")
    if reasons:
        for r in reasons:
            print(f"[PROMPT_REGRESSION] FAIL: {r}")
    if args.strict and not ok:
        sys.exit(1)


if __name__ == "__main__":
    main()
