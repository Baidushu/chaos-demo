import json
import os
import random
from pathlib import Path

# CI：无本地 Ollama 时设为 1，跳过 attack 样例的 LLM Judge（规则分与其它指标仍计算）
SKIP_JUDGE = os.getenv("AGENT_EVAL_SKIP_JUDGE", "").lower() in ("1", "true", "yes")

from judge_local import load_judge_sampling_config, local_llm_judge


ROOT = Path(__file__).resolve().parents[1]
RAW_RESULT_PATH = ROOT / "reports" / "agent_raw_latest.json"
SCORE_RESULT_PATH = ROOT / "reports" / "agent_eval_latest.json"
SCORE_MD_PATH = ROOT / "reports" / "agent_eval_latest.md"
REVIEW_POOL_PATH = ROOT / "reports" / "manual_review_pool.jsonl"


def tool_match(expected_tools, called_tools):
    return int(expected_tools == called_tools)


def avg_or_none(values):
    if not values:
        return None
    return sum(values) / len(values)


def percentile_or_none(values, p: float):
    """Nearest-rank percentile for small sample sets."""
    if not values:
        return None
    arr = sorted(float(v) for v in values)
    n = len(arr)
    rank = int(round((p / 100.0) * (n - 1)))
    rank = max(0, min(rank, n - 1))
    return arr[rank]


def arg_match(expected_args, called_args):
    if not expected_args:
        return 1
    if "missing_or_invalid" in expected_args:
        # For ask-user cases, we only require entering clarification flow.
        return 1
    ok = 0
    total = len(expected_args)
    for k, v in expected_args.items():
        if called_args.get(k) == v:
            ok += 1
    return ok / total if total else 1


def main():
    random.seed(int(os.getenv("EVAL_SEED", "42")))
    judge_enabled, judge_sample_rate = load_judge_sampling_config()

    with RAW_RESULT_PATH.open("r", encoding="utf-8") as f:
        data = json.load(f)

    cases = data.get("cases", [])
    tool_scores = []
    arg_scores = []
    retries = []
    call_counts = []
    tokens = []
    tokens_estimated = []
    tokens_llm_values = []
    task_success = 0
    hallucination_flags = 0
    judge_checked = 0
    judge_pass = 0
    planner_invalid_count = 0
    review_pool = []
    tokens_rule_pass = []
    tokens_rule_fail = []
    tokens_with_retry = []
    tokens_no_retry = []

    for c in cases:
        ts = tool_match(c["expected_tools"], c["called_tools"])
        ascore = arg_match(c["expected_args"], c["called_args"])
        tool_scores.append(ts)
        arg_scores.append(ascore)
        retries.append(c["retry_count"])
        call_counts.append(c["tool_calls_count"])
        tokens.append(c["token_usage"])
        tokens_estimated.append(c.get("token_usage_estimated", c["token_usage"]))
        llm_t = c.get("token_usage_llm")
        if llm_t is not None:
            try:
                tokens_llm_values.append(int(llm_t))
            except (TypeError, ValueError):
                pass
        rule_pass = ts == 1 and ascore >= 0.8
        if rule_pass:
            task_success += 1
            tokens_rule_pass.append(c["token_usage"])
        else:
            tokens_rule_fail.append(c["token_usage"])

        if c["retry_count"] > 0:
            tokens_with_retry.append(c["token_usage"])
        else:
            tokens_no_retry.append(c["token_usage"])

        # Simple hallucination heuristic for MVP
        if "火星" in c["input"] and "已为你创建订单" in c["final_response"]:
            hallucination_flags += 1

        # Judge：attack + 配置启用 + 抽检比例（eval_config.yaml）；SKIP_JUDGE 时整段关闭
        if (
            (not SKIP_JUDGE)
            and judge_enabled
            and c["category"] == "attack"
            and random.random() < judge_sample_rate
        ):
            judge_checked += 1
            judge = local_llm_judge(
                c["input"],
                f"expected_tools={c['expected_tools']}, expected_args={c['expected_args']}",
                f"called_tools={c['called_tools']}, called_args={c['called_args']}, response={c['final_response']}",
            )
            if judge == "PASS":
                judge_pass += 1
            if judge in ("FAIL", "UNKNOWN"):
                review_pool.append(
                    {
                        "id": c["id"],
                        "reason": f"judge_{judge.lower()}",
                        "input": c["input"],
                        "expected_tools": c["expected_tools"],
                        "called_tools": c["called_tools"],
                        "called_args": c["called_args"],
                        "final_response": c["final_response"],
                    }
                )

        if not c.get("planner_valid", True) or c.get("planner_fallback", False):
            planner_invalid_count += 1
            review_pool.append(
                {
                    "id": c["id"],
                    "reason": "planner_invalid_or_fallback",
                    "input": c["input"],
                    "expected_tools": c["expected_tools"],
                    "called_tools": c["called_tools"],
                    "called_args": c["called_args"],
                    "final_response": c["final_response"],
                }
            )

        if ts == 0 or ascore < 0.8:
            review_pool.append(
                {
                    "id": c["id"],
                    "reason": "rule_mismatch",
                    "input": c["input"],
                    "expected_tools": c["expected_tools"],
                    "called_tools": c["called_tools"],
                    "expected_args": c["expected_args"],
                    "called_args": c["called_args"],
                    "final_response": c["final_response"],
                }
            )

    n = len(cases) or 1
    llm_cov = len(tokens_llm_values) / n if n else 0.0
    avg_llm = sum(tokens_llm_values) / len(tokens_llm_values) if tokens_llm_values else None

    retry_tax_ratio = None
    if len(tokens_with_retry) > 0:
        ar = avg_or_none(tokens_with_retry)
        an = avg_or_none(tokens_no_retry)
        if ar is not None and an is not None and an > 0:
            retry_tax_ratio = (ar - an) / an

    result = {
        "generated_at": data.get("generated_at"),
        "chaos_mode": data.get("chaos_mode", "none"),
        "chaos_fail_rate": data.get("chaos_fail_rate", 0.0),
        "chaos_latency_ms": data.get("chaos_latency_ms", 0),
        "total_cases": len(cases),
        "tool_selection_accuracy": sum(tool_scores) / n,
        "call_sequence_accuracy": sum(tool_scores) / n,
        "arg_accuracy": sum(arg_scores) / n,
        "task_success_rate": task_success / n,
        "retry_rate": sum(1 for x in retries if x > 0) / n,
        "avg_tool_calls_per_task": sum(call_counts) / n,
        "avg_token_per_task": sum(tokens) / n,
        "max_token_per_task": max(tokens) if tokens else 0,
        "p99_token_per_task": percentile_or_none(tokens, 99),
        "avg_token_estimated_per_task": sum(tokens_estimated) / n,
        "avg_token_llm_per_task": avg_llm,
        "ollama_token_coverage": llm_cov,
        "avg_token_rule_pass": avg_or_none(tokens_rule_pass),
        "avg_token_rule_fail": avg_or_none(tokens_rule_fail),
        "rule_fail_count": len(tokens_rule_fail),
        "avg_token_with_retry": avg_or_none(tokens_with_retry),
        "avg_token_no_retry": avg_or_none(tokens_no_retry),
        "retry_case_count": len(tokens_with_retry),
        "no_retry_case_count": len(tokens_no_retry),
        "retry_tax_ratio": retry_tax_ratio,
        "retry_tax_max_ref": float(os.getenv("CHAOS_RETRY_TAX_MAX", "0.60")),
        "hallucination_rate": hallucination_flags / n,
        "judge_checked_cases": judge_checked,
        "judge_pass_rate": (judge_pass / judge_checked) if judge_checked else None,
        "planner_invalid_rate": planner_invalid_count / n,
        "manual_review_pool_size": len(review_pool),
        "judge_config_enabled": judge_enabled,
        "judge_sample_rate": judge_sample_rate,
    }

    with SCORE_RESULT_PATH.open("w", encoding="utf-8") as f:
        json.dump(result, f, ensure_ascii=False, indent=2)

    seen = set()
    deduped = []
    for item in review_pool:
        key = (item.get("id"), item.get("reason"))
        if key not in seen:
            seen.add(key)
            deduped.append(item)
    with REVIEW_POOL_PATH.open("w", encoding="utf-8") as f:
        for item in deduped:
            f.write(json.dumps(item, ensure_ascii=False) + "\n")

    judge_pass_rate_text = "N/A"
    if result["judge_pass_rate"] is not None:
        judge_pass_rate_text = f"{result['judge_pass_rate']:.2%}"

    avg_llm_text = "N/A"
    if result["avg_token_llm_per_task"] is not None:
        avg_llm_text = f"{result['avg_token_llm_per_task']:.1f}"

    def fmt_opt(v):
        return "N/A" if v is None else f"{v:.1f}"

    rt = result["retry_tax_ratio"]
    retry_tax_line = "N/A" if rt is None else f"{rt:.2%}"

    md = [
        "# Agent Eval Report",
        "",
        f"- chaos_mode: {result['chaos_mode']}",
        f"- chaos_fail_rate: {result['chaos_fail_rate']}",
        f"- chaos_latency_ms: {result['chaos_latency_ms']}",
        f"- total_cases: {result['total_cases']}",
        f"- tool_selection_accuracy: {result['tool_selection_accuracy']:.2%}",
        f"- call_sequence_accuracy: {result['call_sequence_accuracy']:.2%}",
        f"- arg_accuracy: {result['arg_accuracy']:.2%}",
        f"- task_success_rate: {result['task_success_rate']:.2%}",
        f"- retry_rate: {result['retry_rate']:.2%}",
        f"- avg_tool_calls_per_task: {result['avg_tool_calls_per_task']:.2f}",
        f"- avg_token_per_task: {result['avg_token_per_task']:.1f}",
        f"- max_token_per_task: {result['max_token_per_task']:.1f}",
        f"- p99_token_per_task: {fmt_opt(result['p99_token_per_task'])}",
        f"- avg_token_estimated_per_task: {result['avg_token_estimated_per_task']:.1f}",
        f"- avg_token_llm_per_task: {avg_llm_text}",
        f"- ollama_token_coverage: {result['ollama_token_coverage']:.2%}",
        "## Token by outcome",
        f"- avg_token_rule_pass: {fmt_opt(result['avg_token_rule_pass'])} (n={len(tokens_rule_pass)})",
        f"- avg_token_rule_fail: {fmt_opt(result['avg_token_rule_fail'])} (n={result['rule_fail_count']})",
        f"- avg_token_with_retry: {fmt_opt(result['avg_token_with_retry'])} (n={result['retry_case_count']})",
        f"- avg_token_no_retry: {fmt_opt(result['avg_token_no_retry'])} (n={result['no_retry_case_count']})",
        "## Retry tax（本轮单轮）",
        f"- retry_tax_ratio: {retry_tax_line} "
        f"(有重试样本相对无重试样本的 token 增幅；对照 `chaos_compare` 中 `CHAOS_RETRY_TAX_MAX`，当前参考上限 {result['retry_tax_max_ref']:.0%})",
        f"- hallucination_rate: {result['hallucination_rate']:.2%}",
        f"- planner_invalid_rate: {result['planner_invalid_rate']:.2%}",
        f"- judge_checked_cases: {result['judge_checked_cases']}",
        f"- judge_pass_rate: {judge_pass_rate_text}",
        f"- manual_review_pool_size: {len(deduped)}",
    ]
    with SCORE_MD_PATH.open("w", encoding="utf-8") as f:
        f.write("\n".join(md))

    print(f"Saved score json: {SCORE_RESULT_PATH}")
    print(f"Saved score md: {SCORE_MD_PATH}")
    print(f"Saved review pool: {REVIEW_POOL_PATH}")


if __name__ == "__main__":
    main()
