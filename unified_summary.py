"""
统一平台报告（单页入口）：聚合 gate / benchmark / trend / agent-eval / chaos / prompt / trace 产物路径与关键信号，
写出 `reports/unified_summary_latest.json` 与 `.md`。不改变既有子报告格式，仅只读汇总。

环境变量（可选）：
  UNIFIED_SUMMARY_P95_REGRESSION_WARN — protected/baseline P95 比值超过该值写入 signals（默认 1.10）
  UNIFIED_SUMMARY_RETRY_SURGE_WARN    — chaos_compare delta.retry_rate 超过该值标注 retry 风险（默认 0.12）
"""
from __future__ import annotations

import json
import os
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent
OUT_JSON = ROOT / "reports" / "unified_summary_latest.json"
OUT_MD = ROOT / "reports" / "unified_summary_latest.md"
SCHEMA_VERSION = 1

PATHS: dict[str, Path] = {
    "unified_gate": ROOT / "reports" / "unified_quality_gate_latest.json",
    "benchmark": ROOT / "reports" / "benchmark_latest.json",
    "benchmark_trend": ROOT / "reports" / "benchmark_trend_latest.json",
    "security_scan": ROOT / "reports" / "security_scan_latest.json",
    "chaos_compare": ROOT / "agent-eval" / "reports" / "chaos_compare_latest.json",
    "agent_eval": ROOT / "agent-eval" / "reports" / "agent_eval_latest.json",
    "agent_raw": ROOT / "agent-eval" / "reports" / "agent_raw_latest.json",
    "prompt_regression": ROOT / "agent-eval" / "reports" / "prompt_regression_latest.json",
    "trace_default": ROOT / "agent-eval" / "reports" / "agent_eval_trace_latest.json",
}


def _read_json(path: Path) -> dict | None:
    try:
        if path.is_file():
            return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        pass
    return None


def _rel(p: Path) -> str:
    try:
        return str(p.relative_to(ROOT))
    except ValueError:
        return str(p)


def _artifact_rows() -> list[dict]:
    rows = []
    for key, path in sorted(PATHS.items(), key=lambda x: x[0]):
        rows.append(
            {
                "id": key,
                "path": _rel(path),
                "present": path.is_file(),
                "category": _category(key),
            }
        )
    chaos = _read_json(PATHS["chaos_compare"])
    if chaos and isinstance(chaos.get("agent_trace_files"), dict):
        for label, tpath in chaos["agent_trace_files"].items():
            tp = Path(tpath) if Path(tpath).is_absolute() else ROOT / str(tpath).replace("\\", "/")
            rows.append(
                {
                    "id": f"trace_chaos_{label}",
                    "path": _rel(tp),
                    "present": tp.is_file(),
                    "category": "trace",
                }
            )
    return rows


def _category(key: str) -> str:
    if key in ("unified_gate",):
        return "gate"
    if key in ("benchmark", "benchmark_trend"):
        return "benchmark"
    if key in ("security_scan",):
        return "security"
    if key in ("chaos_compare", "agent_eval", "agent_raw", "prompt_regression"):
        return "eval"
    if key.startswith("trace"):
        return "trace"
    return "other"


def _p95_ratio(bench: dict | None) -> tuple[float | None, float | None, float | None]:
    if not bench:
        return None, None, None
    try:
        bp = float(bench["baseline"]["p95_ms"])
        pp = float(bench["protected"]["p95_ms"])
        if bp <= 0:
            return pp, bp, None
        return pp, bp, pp / bp
    except (KeyError, TypeError, ValueError, ZeroDivisionError):
        return None, None, None


def build_summary() -> dict:
    gate = _read_json(PATHS["unified_gate"])
    bench = _read_json(PATHS["benchmark"])
    trend = _read_json(PATHS["benchmark_trend"])
    chaos = _read_json(PATHS["chaos_compare"])
    agent = _read_json(PATHS["agent_eval"])
    prompt = _read_json(PATHS["prompt_regression"])

    pp95, bp95, p95_ratio = _p95_ratio(bench)
    p95_warn = float(os.getenv("UNIFIED_SUMMARY_P95_REGRESSION_WARN", "1.10"))
    retry_warn = float(os.getenv("UNIFIED_SUMMARY_RETRY_SURGE_WARN", "0.12"))

    reasons: list[str] = []
    signals: list[str] = []

    if gate:
        reasons.extend(str(x) for x in gate.get("reasons") or [])

    final = str(gate.get("final_decision", "PASS")) if gate else "PASS"
    if final not in ("PASS", "FAIL"):
        final = "PASS"

    if chaos:
        tb = chaos.get("token_black_hole_gate") or {}
        if tb.get("pass") is False:
            final = "FAIL"
            detail = (
                "token_black_hole_gate: FAIL "
                f"(token_surge_ratio={tb.get('token_surge_ratio')}, "
                f"retry_surge={tb.get('retry_rate_surge')})"
            )
            if not any("token_black_hole" in r for r in reasons):
                reasons.append(detail)
        d_retry = (chaos.get("delta") or {}).get("retry_rate")
        if d_retry is not None and float(d_retry) > retry_warn:
            signals.append(
                f"retry_explosion_signal: chaos vs baseline retry_rate delta {float(d_retry):.2%} "
                f"(warn>{retry_warn:.2%})"
            )
        t_ratio = tb.get("token_surge_ratio")
        if t_ratio is not None and not tb.get("token_surge_pass", True):
            signals.append(f"token_surge: {float(t_ratio):.2%} (gate threshold exceeded)")

    if prompt and prompt.get("gate_pass") is False:
        final = "FAIL"
        for r in prompt.get("gate_reasons") or []:
            reasons.append(f"prompt_regression: {r}")

    if p95_ratio is not None and p95_ratio > p95_warn:
        signals.append(f"p95_regression: protected/baseline = {p95_ratio:.2f}x (warn>{p95_warn:.2f}x)")

    if agent:
        hr = float(agent.get("hallucination_rate", 0) or 0)
        rr = float(agent.get("retry_rate", 0) or 0)
        if hr >= 0.05:
            signals.append(f"hallucination_rate: {hr:.2%} (latest agent_eval, chaos arm)")
        if rr >= 0.15:
            signals.append(f"retry_rate elevated: {rr:.2%} on scored eval")

    def _dedup(seq: list[str]) -> list[str]:
        seen: set[str] = set()
        out: list[str] = []
        for x in seq:
            if x not in seen:
                seen.add(x)
                out.append(x)
        return out

    reasons = _dedup(reasons)
    signals = _dedup(signals)

    doc = {
        "schema_version": SCHEMA_VERSION,
        "generated_at": int(time.time()),
        "final_decision": final,
        "reasons": reasons,
        "signals": signals,
        "artifacts": _artifact_rows(),
        "metrics_snapshot": {
            "benchmark_protected_p95_ms": pp95,
            "benchmark_baseline_p95_ms": bp95,
            "benchmark_p95_ratio_protected_over_baseline": p95_ratio,
            "benchmark_trend_delta_p95_ms": (trend or {}).get("delta_vs_history_median", {}).get(
                "protected_p95_ms"
            )
            if trend
            else None,
            "agent_eval_hallucination_rate": agent.get("hallucination_rate") if agent else None,
            "agent_eval_retry_rate": agent.get("retry_rate") if agent else None,
            "chaos_token_surge_ratio": ((chaos or {}).get("token_black_hole_gate") or {}).get(
                "token_surge_ratio"
            ),
            "chaos_retry_rate_delta": ((chaos or {}).get("delta") or {}).get("retry_rate"),
        },
        "gate_checks": gate.get("checks") if gate else None,
    }
    return doc


def _write_markdown(doc: dict) -> str:
    lines = [
        "# Unified Platform Summary",
        "",
        f"- schema_version: `{doc['schema_version']}`",
        f"- generated_at: `{doc['generated_at']}`",
        "",
        "## Final decision",
        "",
        f"**{doc['final_decision']}**",
        "",
        "## Reasons",
        "",
    ]
    if doc["reasons"]:
        for r in doc["reasons"]:
            lines.append(f"- {r}")
    else:
        lines.append("- (none)")
    lines.extend(["", "## Signals (read-only hints)", ""])
    if doc["signals"]:
        for s in doc["signals"]:
            lines.append(f"- {s}")
    else:
        lines.append("- (none)")
    lines.extend(["", "## Metrics snapshot", "", "```json", json.dumps(doc["metrics_snapshot"], indent=2, ensure_ascii=False), "```", ""])

    lines.extend(["## Artifacts", "", "| id | category | present | path |", "|---|----|----|---|"])
    for a in doc["artifacts"]:
        pr = "yes" if a["present"] else "no"
        lines.append(f"| {a['id']} | {a['category']} | {pr} | `{a['path']}` |")
    return "\n".join(lines)


def main() -> None:
    OUT_JSON.parent.mkdir(parents=True, exist_ok=True)
    doc = build_summary()
    OUT_JSON.write_text(json.dumps(doc, ensure_ascii=False, indent=2), encoding="utf-8")
    OUT_MD.write_text(_write_markdown(doc), encoding="utf-8")
    print(f"[UNIFIED_SUMMARY] wrote {OUT_JSON}")
    print(f"[UNIFIED_SUMMARY] wrote {OUT_MD}")
    print(f"[UNIFIED_SUMMARY] final_decision={doc['final_decision']} reasons={len(doc['reasons'])} signals={len(doc['signals'])}")


if __name__ == "__main__":
    main()
