import json
import sys
from pathlib import Path

from judge_local import load_gate_thresholds


ROOT = Path(__file__).resolve().parents[1]
SCORE_RESULT_PATH = ROOT / "reports" / "agent_eval_latest.json"


class AgentGateError(Exception):
    """供 `unified_quality_gate` 捕获；`main()` 仍会以退出码 1 结束。"""


def fail(msg: str):
    print(f"[AGENT_GATE] FAIL: {msg}")
    raise AgentGateError(msg)


def check_agent_eval_gate(report_path: Path | None = None) -> dict:
    path = report_path or SCORE_RESULT_PATH
    g = load_gate_thresholds()
    with path.open("r", encoding="utf-8") as f:
        r = json.load(f)

    if r["tool_selection_accuracy"] < g["tool_selection_accuracy_min"]:
        fail(
            f"tool_selection_accuracy too low: {r['tool_selection_accuracy']:.2%} "
            f"(min {g['tool_selection_accuracy_min']:.2%})"
        )
    if r["arg_accuracy"] < g["arg_accuracy_min"]:
        fail(f"arg_accuracy too low: {r['arg_accuracy']:.2%} (min {g['arg_accuracy_min']:.2%})")
    if r["avg_tool_calls_per_task"] > g["avg_tool_calls_per_task_max"]:
        fail(
            f"avg_tool_calls_per_task too high: {r['avg_tool_calls_per_task']:.2f} "
            f"(max {g['avg_tool_calls_per_task_max']:.2f})"
        )
    if r["retry_rate"] > g["retry_rate_max"]:
        fail(f"retry_rate too high: {r['retry_rate']:.2%} (max {g['retry_rate_max']:.2%})")
    if r["hallucination_rate"] > g["hallucination_rate_max"]:
        fail(
            f"hallucination_rate too high: {r['hallucination_rate']:.2%} "
            f"(max {g['hallucination_rate_max']:.2%})"
        )
    if r.get("planner_invalid_rate", 0) > g["planner_invalid_rate_max"]:
        piv = r.get("planner_invalid_rate", 0)
        fail(f"planner_invalid_rate too high: {piv:.2%} (max {g['planner_invalid_rate_max']:.2%})")

    return r


def main():
    try:
        r = check_agent_eval_gate()
    except AgentGateError:
        sys.exit(1)
    print("[AGENT_GATE] PASS (thresholds from agent-eval/config/eval_config.yaml)")
    print(
        "[AGENT_GATE] "
        f"tool_acc={r['tool_selection_accuracy']:.2%}, "
        f"arg_acc={r['arg_accuracy']:.2%}, "
        f"retry_rate={r['retry_rate']:.2%}, "
        f"avg_calls={r['avg_tool_calls_per_task']:.2f}, "
        f"planner_invalid={r.get('planner_invalid_rate', 0):.2%}"
    )


if __name__ == "__main__":
    main()
