import argparse
import json
import os
import subprocess
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
REPO_ROOT = ROOT.parent
RUN_SCRIPT = ROOT / "scripts" / "run_agent_eval.py"
SCORE_SCRIPT = ROOT / "scripts" / "score_agent_eval.py"
GATE_SCRIPT = ROOT / "scripts" / "gate_agent_eval.py"
REPORT_PATH = ROOT / "reports" / "agent_eval_latest.json"
RAW_REPORT_PATH = ROOT / "reports" / "agent_raw_latest.json"
COMPARE_JSON = ROOT / "reports" / "chaos_compare_latest.json"
COMPARE_MD = ROOT / "reports" / "chaos_compare_latest.md"
TRACE_BASELINE_PATH = ROOT / "reports" / "agent_trace_baseline.json"
TRACE_CHAOS_PATH = ROOT / "reports" / "agent_trace_chaos.json"

# 子进程防挂起（大模型/网络异常时仍可在 CI 内失败，默认 20 分钟）
_CHAOS_SUBPROC_TIMEOUT = int(os.environ.get("CHAOS_SUBPROC_TIMEOUT_SEC", "1200"))


def run_cmd(args, extra_env=None):
    try:
        env = os.environ.copy()
        if extra_env:
            env.update(extra_env)
        proc = subprocess.run(
            args,
            capture_output=True,
            text=True,
            cwd=str(REPO_ROOT),
            env=env,
            timeout=_CHAOS_SUBPROC_TIMEOUT,
        )
    except subprocess.TimeoutExpired as e:
        print(getattr(e, "stdout", "") or "", file=sys.stderr)
        print(getattr(e, "stderr", "") or "", file=sys.stderr)
        raise RuntimeError(
            f"Command timed out after {_CHAOS_SUBPROC_TIMEOUT}s (set CHAOS_SUBPROC_TIMEOUT_SEC): "
            f"{' '.join(args)}"
        ) from e
    if proc.returncode != 0:
        print(proc.stdout)
        print(proc.stderr)
        raise RuntimeError(f"Command failed (exit {proc.returncode}): {' '.join(args)}")
    return proc.stdout.strip()


def run_one(mode: str, fail_rate: float = 0.0, latency_ms: int = 0, trace_file: str | None = None):
    #运行一次评测，mode：故障模式，fail_rate：失败率，latency_ms：延迟毫秒
    extra_env = {"AGENT_TRACE_FILE": trace_file} if trace_file else None
    run_cmd(
        [
            sys.executable,
            str(RUN_SCRIPT),
            "--chaos",
            mode,
            "--fail-rate",
            str(fail_rate),
            "--latency-ms",
            str(latency_ms),
        ],
        extra_env=extra_env,
    )
    #评分
    run_cmd([sys.executable, str(SCORE_SCRIPT)])

    gate_ok = True
    #门禁
    try:
        run_cmd([sys.executable, str(GATE_SCRIPT)])
    except Exception:
        gate_ok = False

    with REPORT_PATH.open("r", encoding="utf-8") as f:
        data = json.load(f)
    top_k = int(os.getenv("CHAOS_TOP_TOKEN_CASES", "3"))
    data["top_token_cases"] = load_top_token_cases(top_k=top_k)
    data["gate_pass"] = gate_ok
    return data


def pct(v):
    return f"{v * 100:.2f}%"

#Token 监控
def token_surge_ratio(baseline_tokens: float, chaos_tokens: float) -> float:
    if baseline_tokens <= 0:
        return 0.0
    return (chaos_tokens - baseline_tokens) / baseline_tokens


def fail_path_surge_ratio(baseline_avg, chaos_avg):
    """规则失败样本上的平均 token 增幅；任一侧无数据时返回 None。"""
    if baseline_avg is None or chaos_avg is None:
        return None
    if baseline_avg <= 0:
        return None
    return (chaos_avg - baseline_avg) / baseline_avg


def retry_tax_ratio(run):
    """同一轮评测内：有重试样本相对无重试样本的 token 增幅（重试税）。无重试样本时返回 None。"""
    if int(run.get("retry_case_count") or 0) <= 0:
        return None
    ar = run.get("avg_token_with_retry")
    an = run.get("avg_token_no_retry")
    if ar is None or an is None:
        return None
    try:
        ar_f, an_f = float(ar), float(an)
    except (TypeError, ValueError):
        return None
    if an_f <= 0:
        return None
    return (ar_f - an_f) / an_f


def _delta_optional(chaos_val, baseline_val):
    if chaos_val is None or baseline_val is None:
        return None
    try:
        return float(chaos_val) - float(baseline_val)
    except (TypeError, ValueError):
        return None


def _row_opt(name, baseline_val, chaos_val, delta_val):
    def fmt_cell(v):
        if v is None:
            return "N/A"
        try:
            return f"{float(v):.1f}"
        except (TypeError, ValueError):
            return "N/A"

    def fmt_delta(v):
        if v is None:
            return "N/A"
        try:
            return f"{float(v):+.1f}"
        except (TypeError, ValueError):
            return "N/A"

    return f"| {name} | {fmt_cell(baseline_val)} | {fmt_cell(chaos_val)} | {fmt_delta(delta_val)} |"


def _trim_text(s: str, max_len: int = 80):
    s = str(s or "").replace("\n", " ")
    if len(s) <= max_len:
        return s
    return s[: max_len - 1] + "…"


def load_top_token_cases(top_k: int = 3):
    if top_k <= 0:
        return []
    try:
        with RAW_REPORT_PATH.open("r", encoding="utf-8") as f:
            raw = json.load(f)
    except Exception:
        return []
    cases = raw.get("cases", [])
    if not isinstance(cases, list):
        return []
    ranked = sorted(cases, key=lambda c: float(c.get("token_usage", 0) or 0), reverse=True)
    out = []
    for c in ranked[:top_k]:
        out.append(
            {
                "id": c.get("id"),
                "category": c.get("category"),
                "token_usage": float(c.get("token_usage", 0) or 0),
                "retry_count": int(c.get("retry_count", 0) or 0),
                "called_tools": c.get("called_tools", []),
                "input": _trim_text(c.get("input", ""), 120),
                "final_response": _trim_text(c.get("final_response", ""), 120),
            }
        )
    return out


def main():
    parser = argparse.ArgumentParser(description="Compare no-chaos vs mixed-chaos agent eval.")
    parser.add_argument(
        "--strict",
        action="store_true",
        help="Exit with code 1 if token surge gate fails (default: only write report).",
    )
    args = parser.parse_args()

    token_surge_max = float(os.getenv("CHAOS_TOKEN_SURGE_MAX", "0.30"))
    token_max_per_task_max = float(os.getenv("CHAOS_TOKEN_MAX_PER_TASK_MAX", "500"))
    token_p99_per_task_max = float(os.getenv("CHAOS_TOKEN_P99_PER_TASK_MAX", "300"))
    retry_surge_max = float(os.getenv("CHAOS_RETRY_SURGE_MAX", "0.25"))
    fail_path_surge_max = float(os.getenv("CHAOS_FAIL_PATH_TOKEN_SURGE_MAX", "0.50"))
    retry_path_surge_max = float(os.getenv("CHAOS_RETRY_PATH_TOKEN_SURGE_MAX", "0.60"))
    # 小样本（如 10 条）下仅 1 条重试时重试税方差大，默认 0.60 减少误杀；可收紧为 0.50
    retry_tax_max = float(os.getenv("CHAOS_RETRY_TAX_MAX", "0.60"))
    #运行基线和混合故障场景（各写到独立 trace 文件，避免后一轮覆盖前一轮）
    baseline = run_one("none", 0.0, 0, trace_file=str(TRACE_BASELINE_PATH))
    #混沌组：混合麻烦（mixed），45%的请求会失败，每个请求延迟 180ms
    chaos = run_one("mixed", 0.45, 180, trace_file=str(TRACE_CHAOS_PATH))

    t_ratio = token_surge_ratio(baseline["avg_token_per_task"], chaos["avg_token_per_task"])
    chaos_max_token = float(chaos.get("max_token_per_task") or 0.0)
    chaos_p99_token = float(chaos.get("p99_token_per_task") or 0.0)
    r_surge = chaos["retry_rate"] - baseline["retry_rate"]
    token_gate_pass = t_ratio <= token_surge_max
    token_max_gate_pass = chaos_max_token <= token_max_per_task_max
    token_p99_gate_pass = chaos_p99_token <= token_p99_per_task_max
    retry_gate_pass = r_surge <= retry_surge_max

    bf = baseline.get("avg_token_rule_fail")
    cf = chaos.get("avg_token_rule_fail")
    try:
        bf_f = float(bf) if bf is not None else None
        cf_f = float(cf) if cf is not None else None
    except (TypeError, ValueError):
        bf_f, cf_f = None, None
    fp_ratio = fail_path_surge_ratio(bf_f, cf_f)
    if fp_ratio is None:
        fail_path_gate_pass = True
    else:
        fail_path_gate_pass = fp_ratio <= fail_path_surge_max

    br = baseline.get("avg_token_with_retry")
    cr = chaos.get("avg_token_with_retry")
    try:
        br_r = float(br) if br is not None else None
        cr_r = float(cr) if cr is not None else None
    except (TypeError, ValueError):
        br_r, cr_r = None, None
    rp_ratio = fail_path_surge_ratio(br_r, cr_r)
    # 仅当两侧都有「重试样本」时的均值才校验（否则无对照意义，跳过）
    base_retry_n = int(baseline.get("retry_case_count") or 0)
    chaos_retry_n = int(chaos.get("retry_case_count") or 0)
    if rp_ratio is None or base_retry_n == 0 or chaos_retry_n == 0:
        retry_path_gate_pass = True
    else:
        retry_path_gate_pass = rp_ratio <= retry_path_surge_max

    chaos_retry_tax = retry_tax_ratio(chaos)
    baseline_retry_tax = retry_tax_ratio(baseline)
    if chaos_retry_tax is None:
        retry_tax_gate_pass = True
    else:
        retry_tax_gate_pass = chaos_retry_tax <= retry_tax_max

    token_black_hole_gate_pass = (
        token_gate_pass
        and token_max_gate_pass
        and token_p99_gate_pass
        and retry_gate_pass
        and fail_path_gate_pass
        and retry_path_gate_pass
        and retry_tax_gate_pass
    )

    result = {
        "baseline": baseline,
        "chaos": chaos,
        "agent_trace_files": {
            "baseline": str(TRACE_BASELINE_PATH),
            "chaos": str(TRACE_CHAOS_PATH),
        },
        "delta": {
            "tool_selection_accuracy": chaos["tool_selection_accuracy"] - baseline["tool_selection_accuracy"],
            "arg_accuracy": chaos["arg_accuracy"] - baseline["arg_accuracy"],
            "task_success_rate": chaos["task_success_rate"] - baseline["task_success_rate"],
            "retry_rate": chaos["retry_rate"] - baseline["retry_rate"],
            "avg_tool_calls_per_task": chaos["avg_tool_calls_per_task"] - baseline["avg_tool_calls_per_task"],
            "avg_token_per_task": chaos["avg_token_per_task"] - baseline["avg_token_per_task"],
            "avg_token_rule_pass": _delta_optional(
                chaos.get("avg_token_rule_pass"), baseline.get("avg_token_rule_pass")
            ),
            "avg_token_rule_fail": _delta_optional(
                chaos.get("avg_token_rule_fail"), baseline.get("avg_token_rule_fail")
            ),
            "avg_token_with_retry": _delta_optional(
                chaos.get("avg_token_with_retry"), baseline.get("avg_token_with_retry")
            ),
            "hallucination_rate": chaos["hallucination_rate"] - baseline["hallucination_rate"],
            "planner_invalid_rate": chaos.get("planner_invalid_rate", 0) - baseline.get("planner_invalid_rate", 0),
        },
        "token_black_hole_gate": {
            "token_surge_ratio": t_ratio,
            "token_surge_max": token_surge_max,
            "token_surge_pass": token_gate_pass,
            "chaos_max_token_per_task": chaos_max_token,
            "token_max_per_task_max": token_max_per_task_max,
            "token_max_per_task_pass": token_max_gate_pass,
            "chaos_p99_token_per_task": chaos_p99_token,
            "token_p99_per_task_max": token_p99_per_task_max,
            "token_p99_per_task_pass": token_p99_gate_pass,
            "retry_rate_surge": r_surge,
            "retry_surge_max": retry_surge_max,
            "retry_surge_pass": retry_gate_pass,
            "fail_path_token_surge_ratio": fp_ratio,
            "fail_path_token_surge_max": fail_path_surge_max,
            "fail_path_surge_pass": fail_path_gate_pass,
            "retry_path_token_surge_ratio": rp_ratio,
            "retry_path_token_surge_max": retry_path_surge_max,
            "retry_path_surge_pass": retry_path_gate_pass,
            "baseline_retry_case_count": base_retry_n,
            "chaos_retry_case_count": chaos_retry_n,
            "chaos_retry_tax_ratio": chaos_retry_tax,
            "retry_tax_max": retry_tax_max,
            "retry_tax_pass": retry_tax_gate_pass,
            "baseline_retry_tax_ratio": baseline_retry_tax,
            "pass": token_black_hole_gate_pass,
        },
    }

    with COMPARE_JSON.open("w", encoding="utf-8") as f:
        json.dump(result, f, ensure_ascii=False, indent=2)

    md = [
        "# Chaos Compare Report",
        "",
        "| Metric | No Chaos | Mixed Chaos | Delta (Chaos-Baseline) |",
        "|---|---:|---:|---:|",
        f"| Tool Selection Acc | {pct(baseline['tool_selection_accuracy'])} | {pct(chaos['tool_selection_accuracy'])} | {pct(result['delta']['tool_selection_accuracy'])} |",
        f"| Arg Acc | {pct(baseline['arg_accuracy'])} | {pct(chaos['arg_accuracy'])} | {pct(result['delta']['arg_accuracy'])} |",
        f"| Task Success | {pct(baseline['task_success_rate'])} | {pct(chaos['task_success_rate'])} | {pct(result['delta']['task_success_rate'])} |",
        f"| Retry Rate | {pct(baseline['retry_rate'])} | {pct(chaos['retry_rate'])} | {pct(result['delta']['retry_rate'])} |",
        f"| Avg Tool Calls | {baseline['avg_tool_calls_per_task']:.2f} | {chaos['avg_tool_calls_per_task']:.2f} | {result['delta']['avg_tool_calls_per_task']:+.2f} |",
        f"| Avg Token/Task | {baseline['avg_token_per_task']:.1f} | {chaos['avg_token_per_task']:.1f} | {result['delta']['avg_token_per_task']:+.1f} |",
        f"| Max Token/Task | {float(baseline.get('max_token_per_task') or 0):.1f} | {chaos_max_token:.1f} | "
        f"{(chaos_max_token - float(baseline.get('max_token_per_task') or 0)):+.1f} |",
        f"| P99 Token/Task | {float(baseline.get('p99_token_per_task') or 0):.1f} | {chaos_p99_token:.1f} | "
        f"{(chaos_p99_token - float(baseline.get('p99_token_per_task') or 0)):+.1f} |",
        f"| Hallucination Rate | {pct(baseline['hallucination_rate'])} | {pct(chaos['hallucination_rate'])} | {pct(result['delta']['hallucination_rate'])} |",
        f"| Planner Invalid Rate | {pct(baseline.get('planner_invalid_rate', 0))} | {pct(chaos.get('planner_invalid_rate', 0))} | {pct(result['delta']['planner_invalid_rate'])} |",
        "",
        f"- Gate pass (no chaos): {baseline['gate_pass']}",
        f"- Gate pass (mixed chaos): {chaos['gate_pass']}",
        "",
        "## Token by outcome (avg token_usage)",
        "",
        "| Metric | No Chaos | Mixed Chaos | Delta |",
        "|---|---:|---:|---:|",
        _row_opt(
            "avg_token_rule_pass",
            baseline.get("avg_token_rule_pass"),
            chaos.get("avg_token_rule_pass"),
            result["delta"].get("avg_token_rule_pass"),
        ),
        _row_opt(
            "avg_token_rule_fail",
            baseline.get("avg_token_rule_fail"),
            chaos.get("avg_token_rule_fail"),
            result["delta"].get("avg_token_rule_fail"),
        ),
        _row_opt(
            "avg_token_with_retry",
            baseline.get("avg_token_with_retry"),
            chaos.get("avg_token_with_retry"),
            result["delta"].get("avg_token_with_retry"),
        ),
        "",
        "## Token black hole gate (chaos vs baseline)",
        "",
        f"- token_surge_ratio: {t_ratio:.2%} (max allowed: {pct(token_surge_max)})",
        f"- token_surge_pass: {token_gate_pass}",
        f"- chaos_max_token_per_task: {chaos_max_token:.1f} (max allowed: {token_max_per_task_max:.1f})",
        f"- token_max_per_task_pass: {token_max_gate_pass}",
        f"- chaos_p99_token_per_task: {chaos_p99_token:.1f} (max allowed: {token_p99_per_task_max:.1f})",
        f"- token_p99_per_task_pass: {token_p99_gate_pass}",
        f"- retry_rate_surge: {pct(r_surge)} (max allowed: {pct(retry_surge_max)})",
        f"- retry_surge_pass: {retry_gate_pass}",
        f"- fail_path_token_surge_ratio: "
        f"{('N/A' if fp_ratio is None else f'{fp_ratio:.2%}')} "
        f"(max allowed: {pct(fail_path_surge_max)})",
        f"- fail_path_surge_pass: {fail_path_gate_pass}",
        f"- retry_path_token_surge_ratio: "
        f"{('N/A' if rp_ratio is None else f'{rp_ratio:.2%}')} "
        f"(max allowed: {pct(retry_path_surge_max)}; "
        f"baseline_retry_n={base_retry_n}, chaos_retry_n={chaos_retry_n})",
        f"- retry_path_surge_pass: {retry_path_gate_pass}",
        f"- chaos_retry_tax_ratio: "
        f"{('N/A' if chaos_retry_tax is None else f'{chaos_retry_tax:.2%}')} "
        f"(max allowed: {pct(retry_tax_max)}; 有重试时相对无重试样本的 token 增幅)",
        f"- baseline_retry_tax_ratio: "
        f"{('N/A' if baseline_retry_tax is None else f'{baseline_retry_tax:.2%}')}",
        f"- retry_tax_pass: {retry_tax_gate_pass}",
        f"- **token_black_hole_gate_pass: {token_black_hole_gate_pass}**",
        "",
        "## Runtime trace (HTTP tool calls)",
        "",
        f"- Baseline trace JSON: `{TRACE_BASELINE_PATH}`",
        f"- Mixed chaos trace JSON: `{TRACE_CHAOS_PATH}`",
        "",
        "## Top token cases (for debugging)",
        "",
        "### No Chaos",
    ]
    base_top = baseline.get("top_token_cases", [])
    chaos_top = chaos.get("top_token_cases", [])
    if not base_top:
        md.append("- No cases.")
    else:
        md.append("| # | case_id | token | retry | tools | input |")
        md.append("|---:|---|---:|---:|---|---|")
        for i, c in enumerate(base_top, start=1):
            tools = ",".join(c.get("called_tools", []))
            md.append(
                f"| {i} | {c.get('id','')} | {float(c.get('token_usage', 0)):.1f} | "
                f"{int(c.get('retry_count', 0))} | {tools} | {c.get('input','')} |"
            )
    md.extend(["", "### Mixed Chaos"])
    if not chaos_top:
        md.append("- No cases.")
    else:
        md.append("| # | case_id | token | retry | tools | input |")
        md.append("|---:|---|---:|---:|---|---|")
        for i, c in enumerate(chaos_top, start=1):
            tools = ",".join(c.get("called_tools", []))
            md.append(
                f"| {i} | {c.get('id','')} | {float(c.get('token_usage', 0)):.1f} | "
                f"{int(c.get('retry_count', 0))} | {tools} | {c.get('input','')} |"
            )
    with COMPARE_MD.open("w", encoding="utf-8") as f:
        f.write("\n".join(md))

    print(f"Saved compare json: {COMPARE_JSON}")
    print(f"Saved compare md: {COMPARE_MD}")
    fp_txt = "N/A" if fp_ratio is None else f"{fp_ratio:.2%}"
    rp_txt = "N/A" if rp_ratio is None else f"{rp_ratio:.2%}"
    tax_txt = "N/A" if chaos_retry_tax is None else f"{chaos_retry_tax:.2%}"
    print(
        f"[TOKEN_BLACK_HOLE_GATE] pass={token_black_hole_gate_pass} "
        f"token_surge={t_ratio:.2%} retry_surge={r_surge:.2%} "
        f"fail_path_surge={fp_txt} retry_path_surge={rp_txt} "
        f"chaos_retry_tax={tax_txt}"
    )
    if args.strict and not token_black_hole_gate_pass:
        print("[TOKEN_BLACK_HOLE_GATE] FAIL under --strict, exiting 1", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
