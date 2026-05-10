"""
Unified quality gate（P2 + P3）：串联 benchmark + security（quality_gate）、可选 **benchmark_trend**，
与 agent-eval 门禁；写出 `reports/unified_quality_gate_latest.json`（final_decision + reasons + checks）。
"""
from __future__ import annotations

import json
import os
import sys
import time
from pathlib import Path

import quality_gate as qg

ROOT = Path(__file__).resolve().parent
REPORTS_DIR = ROOT / "reports"
OUT_PATH = REPORTS_DIR / "unified_quality_gate_latest.json"
AGENT_EVAL_SCRIPT_DIR = ROOT / "agent-eval" / "scripts"
AGENT_SCORE_PATH = ROOT / "agent-eval" / "reports" / "agent_eval_latest.json"


def _import_agent_gate():
    d = str(AGENT_EVAL_SCRIPT_DIR)
    if d not in sys.path:
        sys.path.insert(0, d)
    import gate_agent_eval as ag  # noqa: PLC0415

    return ag


def run_unified() -> dict:
    """执行全部子检查，返回将写入 JSON 的文档（不根据结果退出进程）。"""
    checks: dict[str, str] = {}
    reasons: list[str] = []

    try:
        qg.run_check_with_retries("benchmark", qg.check_benchmark_gate)
        checks["benchmark"] = "PASS"
    except qg.QualityGateError as e:
        checks["benchmark"] = "FAIL"
        reasons.append(f"benchmark: {e}")

    try:
        sec_ret = qg.run_check_with_retries("security", qg.check_security_gate)
        checks["security"] = sec_ret if sec_ret else "PASS"
    except qg.QualityGateError as e:
        checks["security"] = "FAIL"
        reasons.append(f"security: {e}")

    try:
        trend_ret = qg.run_check_with_retries("benchmark_trend", qg.check_benchmark_trend_gate)
        checks["benchmark_trend"] = trend_ret if trend_ret else "PASS"
    except qg.QualityGateError as e:
        checks["benchmark_trend"] = "FAIL"
        reasons.append(f"benchmark_trend: {e}")

    skip_agent = os.getenv("UNIFIED_GATE_SKIP_AGENT", "0").strip().lower() in (
        "1",
        "true",
        "yes",
        "on",
    )
    if skip_agent:
        checks["agent_eval"] = "SKIPPED"
    elif not AGENT_SCORE_PATH.exists():
        checks["agent_eval"] = "FAIL"
        reasons.append(
            f"agent_eval: missing {AGENT_SCORE_PATH.relative_to(ROOT)} "
            "(run agent-eval score step first)"
        )
    else:
        ag = _import_agent_gate()
        try:
            ag.check_agent_eval_gate(AGENT_SCORE_PATH)
            checks["agent_eval"] = "PASS"
        except ag.AgentGateError as e:
            checks["agent_eval"] = "FAIL"
            reasons.append(f"agent_eval: {e}")

    final = "PASS" if not reasons else "FAIL"
    doc = {
        "final_decision": final,
        "generated_at": int(time.time()),
        "reasons": reasons,
        "checks": checks,
    }
    return doc


def main() -> None:
    REPORTS_DIR.mkdir(parents=True, exist_ok=True)
    doc = run_unified()
    with OUT_PATH.open("w", encoding="utf-8") as f:
        json.dump(doc, f, ensure_ascii=False, indent=2)
    print(f"[UNIFIED_GATE] wrote {OUT_PATH}")
    print(f"[UNIFIED_GATE] final_decision={doc['final_decision']} checks={doc['checks']}")
    if doc["reasons"]:
        for r in doc["reasons"]:
            print(f"[UNIFIED_GATE] FAIL: {r}")
        sys.exit(1)
    print("[UNIFIED_GATE] PASS")


if __name__ == "__main__":
    main()
