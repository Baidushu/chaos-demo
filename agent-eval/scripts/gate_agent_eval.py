from __future__ import annotations

import json
import sys
from pathlib import Path

from ai_platform.evaluation.gate import AgentGateError, QualityGate

from judge_local import load_gate_thresholds


ROOT = Path(__file__).resolve().parents[1]
SCORE_RESULT_PATH = ROOT / "reports" / "agent_eval_latest.json"


def fail(msg: str):
    print(f"[AGENT_GATE] FAIL: {msg}")
    raise AgentGateError(msg)


def check_agent_eval_gate(report_path: Path | None = None) -> dict:
    path = report_path or SCORE_RESULT_PATH
    with path.open("r", encoding="utf-8") as handle:
        report = json.load(handle)
    gate = QualityGate(load_gate_thresholds())
    try:
        gate.assert_pass(report)
    except AgentGateError as exc:
        fail(str(exc))
    return report


def main() -> None:
    try:
        report = check_agent_eval_gate()
    except AgentGateError:
        sys.exit(1)
    print("[AGENT_GATE] PASS (thresholds from agent-eval/config/eval_config.yaml)")
    print(
        "[AGENT_GATE] "
        f"tool_acc={report['tool_selection_accuracy']:.2%}, "
        f"arg_acc={report['arg_accuracy']:.2%}, "
        f"retry_rate={report['retry_rate']:.2%}, "
        f"avg_calls={report['avg_tool_calls_per_task']:.2f}, "
        f"planner_invalid={report.get('planner_invalid_rate', 0):.2%}"
    )


if __name__ == "__main__":
    main()
