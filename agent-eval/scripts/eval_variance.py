"""
多次运行评测并汇总关键指标的均值 / 最小值 / 最大值 / 样本标准差（差分测试「大概意思」版）。

依赖：每次调用会覆盖 `reports/agent_raw_latest.json` 与 `agent_eval_latest.json`。

用法（在仓库根目录）：
  python agent-eval/scripts/eval_variance.py --runs 5 --chaos mixed --fail-rate 0.45 --latency-ms 180

`EVAL_SEED` 在每轮中设为 seed_start, seed_start+1, ...，使故障注入（及 Judge 抽检）序列随轮次变化。
"""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
from pathlib import Path
from statistics import mean, pstdev

ROOT = Path(__file__).resolve().parents[1]
REPO_ROOT = ROOT.parent
RUN_SCRIPT = ROOT / "scripts" / "run_agent_eval.py"
SCORE_SCRIPT = ROOT / "scripts" / "score_agent_eval.py"
SCORE_JSON = ROOT / "reports" / "agent_eval_latest.json"
OUT_JSON = ROOT / "reports" / "eval_variance_latest.json"
OUT_MD = ROOT / "reports" / "eval_variance_latest.md"

METRICS = [
    "tool_selection_accuracy",
    "call_sequence_accuracy",
    "arg_accuracy",
    "task_success_rate",
    "retry_rate",
    "avg_token_per_task",
]


def run_once(chaos: str, fail_rate: float, latency_ms: int, seed: int) -> dict:
    env = os.environ.copy()
    env["EVAL_SEED"] = str(seed)
    subprocess.run(
        [
            sys.executable,
            str(RUN_SCRIPT),
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
        [sys.executable, str(SCORE_SCRIPT)],
        cwd=str(REPO_ROOT),
        env=env,
        check=True,
    )
    with SCORE_JSON.open("r", encoding="utf-8") as f:
        return json.load(f)


def summarize(rows: list[dict]) -> dict:
    out = {}
    for key in METRICS:
        vals = [r[key] for r in rows if key in r and r[key] is not None]
        if not vals:
            continue
        if len(vals) == 1:
            out[key] = {"mean": vals[0], "min": vals[0], "max": vals[0], "stdev": 0.0}
        else:
            out[key] = {
                "mean": mean(vals),
                "min": min(vals),
                "max": max(vals),
                "stdev": pstdev(vals),
            }
    return out


def main():
    parser = argparse.ArgumentParser(description="Multi-run agent eval variance summary.")
    parser.add_argument("--runs", type=int, default=5, help="重复次数（>=2 才有意义）")
    parser.add_argument("--chaos", default="mixed", choices=["none", "latency", "error", "mixed"])
    parser.add_argument("--fail-rate", type=float, default=0.45)
    parser.add_argument("--latency-ms", type=int, default=180)
    parser.add_argument("--seed-start", type=int, default=42, help="EVAL_SEED 起始值，每轮 +1")
    args = parser.parse_args()

    rows_full = []
    rows = []
    seeds = []
    for i in range(args.runs):
        seed = args.seed_start + i
        seeds.append(seed)
        print(f"[eval_variance] {i + 1}/{args.runs} EVAL_SEED={seed}", flush=True)
        full = run_once(args.chaos, args.fail_rate, args.latency_ms, seed)
        rows_full.append(full)
        rows.append({k: full.get(k) for k in METRICS})

    summary = summarize(rows)

    payload = {
        "runs": args.runs,
        "chaos": args.chaos,
        "fail_rate": args.fail_rate,
        "latency_ms": args.latency_ms,
        "seeds": seeds,
        "per_run": rows_full,
        "summary": summary,
    }
    with OUT_JSON.open("w", encoding="utf-8") as f:
        json.dump(payload, f, ensure_ascii=False, indent=2)

    lines = [
        "# Eval Variance Report",
        "",
        f"- runs: {args.runs}",
        f"- chaos: {args.chaos}",
        f"- fail_rate: {args.fail_rate}",
        f"- latency_ms: {args.latency_ms}",
        f"- seeds: {seeds}",
        "",
        "| metric | mean | min | max | stdev |",
        "|---|---:|---:|---:|---:|",
    ]
    for key in METRICS:
        if key not in summary:
            continue
        s = summary[key]
        lines.append(
            f"| {key} | {s['mean']:.6f} | {s['min']:.6f} | {s['max']:.6f} | {s['stdev']:.6f} |"
        )
    with OUT_MD.open("w", encoding="utf-8") as f:
        f.write("\n".join(lines))

    print(f"Saved {OUT_JSON}")
    print(f"Saved {OUT_MD}")


if __name__ == "__main__":
    main()
