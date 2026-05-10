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

import trace_timeline as tt

ROOT = Path(__file__).resolve().parent
OUT_JSON = ROOT / "reports" / "unified_summary_latest.json"
OUT_MD = ROOT / "reports" / "unified_summary_latest.md"
SCHEMA_VERSION = 1
BENCHMARK_HISTORY_DIR = ROOT / "reports" / "benchmark_history"

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
    "trace_timeline_mmd": ROOT / "reports" / "trace_timeline_latest.mmd",
    "trace_timeline_html": ROOT / "reports" / "trace_timeline_latest.html",
    "trace_timeline_meta": ROOT / "reports" / "trace_timeline_meta.json",
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


def _protected_p95_history_series() -> list[float]:
    if not BENCHMARK_HISTORY_DIR.is_dir():
        return []
    files = sorted(BENCHMARK_HISTORY_DIR.glob("benchmark_*.json"))
    vals: list[float] = []
    for path in files:
        rep = _read_json(path)
        if not rep:
            continue
        try:
            vals.append(float(rep["protected"]["p95_ms"]))
        except (KeyError, TypeError, ValueError):
            continue
    return vals


def _consecutive_p95_regressions(vals: list[float]) -> int:
    """从最新一次往回数：连续几次「比上一轮更差」（protected P95 升高）。"""
    if len(vals) < 2:
        return 0
    streak = 0
    for i in range(len(vals) - 1, 0, -1):
        if vals[i] > vals[i - 1]:
            streak += 1
        else:
            break
    return streak


def _semantic_eval_status(gate_checks: dict | None, prompt: dict | None) -> str:
    """合并 agent_eval 门禁与 prompt 回归，展示为 semantic_eval。"""
    gc = gate_checks or {}
    agent = str(gc.get("agent_eval", "SKIPPED"))
    prompt_fail = bool(prompt and prompt.get("gate_pass") is False)
    if agent == "FAIL" or prompt_fail:
        return "FAIL"
    return "PASS"


def _chaos_trace_path(chaos_doc: dict | None) -> Path | None:
    if not chaos_doc or not isinstance(chaos_doc.get("agent_trace_files"), dict):
        return None
    raw = chaos_doc["agent_trace_files"].get("chaos")
    if not raw:
        return None
    p = Path(str(raw).replace("\\", "/"))
    if p.is_file():
        return p
    q = ROOT / str(raw).replace("\\", "/")
    if q.is_file():
        return q
    return None


def _trace_retry_highlights(trace_path: Path | None) -> tuple[list[str], str | None]:
    """Returns (highlights, worst_tool_name)."""
    doc = _read_json(trace_path) if trace_path and trace_path.is_file() else None
    if not doc:
        return [], None
    max_ri = -1
    worst_tool: str | None = None
    inj = 0
    ask_user_http = 0
    for _cid, steps in tt.iter_cases_steps(doc):
        for st in steps:
            try:
                ri = int(st.get("retry_index") or 0)
            except (TypeError, ValueError):
                ri = 0
            if ri > max_ri:
                max_ri = ri
                worst_tool = str(st.get("tool") or "?")
            if st.get("injected_fault"):
                inj += 1
            if str(st.get("tool") or "") == "ask_user":
                ask_user_http += 1
    out: list[str] = []
    if max_ri >= 1 and worst_tool:
        out.append(f"HTTP 工具链路上重试最高达 {max_ri}×（峰值工具 `{worst_tool}`）。")
    if inj:
        out.append(f"混沌注入在 {inj} 个 HTTP step 上命中。")
    if ask_user_http:
        out.append(f"观测到 `ask_user` 相关 HTTP step ×{ask_user_http}（多为澄清/降级路径）。")
    return out, worst_tool


def _planner_fallback_bullets(raw: dict | None) -> list[str]:
    if not raw:
        return []
    n = sum(1 for c in raw.get("cases") or [] if c.get("planner_fallback"))
    if n <= 0:
        return []
    return [f"规划降级（planner_fallback）在 {n} 个 case 上触发。"]


def _build_key_regressions(
    *,
    gate: dict | None,
    bench: dict | None,
    chaos: dict | None,
    prompt: dict | None,
    pp95: float | None,
    bp95: float | None,
    p95_ratio: float | None,
    retry_warn: float,
    worst_retry_tool: str | None,
) -> list[str]:
    kr: list[str] = []
    checks = (gate or {}).get("checks") or {}
    if checks.get("benchmark") == "FAIL":
        if p95_ratio is not None and p95_ratio >= 1 and bp95 and pp95:
            pct = (p95_ratio - 1.0) * 100.0
            kr.append(f"Benchmark：本轮 protected P95 较 baseline 高约 **+{pct:.0f}%**（{pp95:.1f} ms vs {bp95:.1f} ms）。")
        else:
            kr.append("Benchmark：**unified_quality_gate** 标记 benchmark 未通过（详见 Reasons）。")

    if checks.get("benchmark_trend") == "FAIL":
        kr.append("Benchmark trend：相对 **历史中位数** 的 protected P95 规则未通过。")

    d_retry = (chaos.get("delta") or {}).get("retry_rate") if chaos else None
    if d_retry is not None and float(d_retry) > retry_warn:
        wt = f"（HTTP 峰值重试工具：`{worst_retry_tool}`）" if worst_retry_tool else ""
        kr.append(f"Chaos vs baseline：`retry_rate` 上升约 **+{float(d_retry) * 100:.0f}%**{wt}。")

    if prompt and prompt.get("gate_pass") is False:
        for r in (prompt.get("gate_reasons") or [])[:3]:
            kr.append(f"Prompt / 语义回归：{r}")

    if checks.get("agent_eval") == "FAIL":
        kr.append("Agent 门禁：**agent_eval** 未通过（见 Reasons）。")

    if chaos and (chaos.get("token_black_hole_gate") or {}).get("pass") is False:
        kr.append("Chaos 对照：**token_black_hole_gate** 未通过（token/重试暴涨类信号）。")

    # 去重保序
    seen: set[str] = set()
    out: list[str] = []
    for x in kr:
        if x not in seen:
            seen.add(x)
            out.append(x)
    return out


def _build_trend_bullets(trend: dict | None, hist_p95: list[float]) -> list[str]:
    bullets: list[str] = []
    streak = _consecutive_p95_regressions(hist_p95)
    if streak >= 3:
        bullets.append(f"Trend：protected P95 已连续 **{streak}** 次压测较上一轮变差（`benchmark_history` 归档序列）。")
        return bullets
    if trend:
        d = (trend.get("delta_vs_history_median") or {}).get("protected_p95_ms")
        try:
            if d is not None and float(d) > 0:
                bullets.append(
                    f"Trend：protected P95 较历史中位数高出 **{float(d):.1f} ms**（`benchmark_trend_latest`）。"
                )
        except (TypeError, ValueError):
            pass
    return bullets


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

    agent_raw = _read_json(PATHS["agent_raw"])
    hist_p95 = _protected_p95_history_series()
    streak_n = _consecutive_p95_regressions(hist_p95)
    chaos_trace_path = _chaos_trace_path(chaos)
    trace_hi, worst_tool = _trace_retry_highlights(chaos_trace_path)
    trace_hi = _dedup(trace_hi + _planner_fallback_bullets(agent_raw))

    gc = gate.get("checks") if gate else None
    checks_summary = {
        "benchmark": str((gc or {}).get("benchmark", "UNKNOWN")),
        "benchmark_trend": str((gc or {}).get("benchmark_trend", "SKIPPED")),
        "security": str((gc or {}).get("security", "UNKNOWN")),
        "semantic_eval": _semantic_eval_status(gc, prompt),
    }

    key_regressions = _build_key_regressions(
        gate=gate,
        bench=bench,
        chaos=chaos,
        prompt=prompt,
        pp95=pp95,
        bp95=bp95,
        p95_ratio=p95_ratio,
        retry_warn=retry_warn,
        worst_retry_tool=worst_tool,
    )

    trend_bullets = _build_trend_bullets(trend, hist_p95)

    doc = {
        "schema_version": SCHEMA_VERSION,
        "generated_at": int(time.time()),
        "final_decision": final,
        "reasons": reasons,
        "signals": signals,
        "checks_summary": checks_summary,
        "key_regressions": key_regressions,
        "trace_highlights": trace_hi,
        "trend_bullets": trend_bullets,
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
            "benchmark_history_consecutive_p95_regressions": streak_n,
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
    lines: list[str] = [
        "# Release Summary",
        "",
        f"_unified_summary schema `{doc['schema_version']}` · generated_at `{doc['generated_at']}`_",
        "",
        "## Decision",
        "",
        f"**{doc['final_decision']}**",
        "",
        "## Checks",
        "",
    ]
    cs = doc.get("checks_summary") or {}
    for k in ("benchmark", "benchmark_trend", "security", "semantic_eval"):
        if k in cs:
            lines.append(f"- **{k}**: {cs[k]}")

    lines.extend(["", "## Key regressions", ""])
    kr = doc.get("key_regressions") or []
    if kr:
        for x in kr:
            lines.append(f"- {x}")
    else:
        lines.append("- (none)")

    lines.extend(["", "## Trace highlights", ""])
    th = doc.get("trace_highlights") or []
    if th:
        for x in th:
            lines.append(f"- {x}")
    else:
        lines.append("- (none)")

    lines.extend(["", "## Trend", ""])
    tb = doc.get("trend_bullets") or []
    if tb:
        for x in tb:
            lines.append(f"- {x}")
    else:
        lines.append("- (no strong trend signal in this run)")

    lines.extend(["", "## Artifacts", "", "| id | category | present | path |", "|---|----|----|---|"])
    for a in doc["artifacts"]:
        pr = "yes" if a["present"] else "no"
        lines.append(f"| {a['id']} | {a['category']} | {pr} | `{a['path']}` |")

    lines.extend(["", "---", "", "## Detail — Reasons", ""])
    if doc["reasons"]:
        for r in doc["reasons"]:
            lines.append(f"- {r}")
    else:
        lines.append("- (none)")

    lines.extend(["", "## Detail — Signals (read-only hints)", ""])
    if doc["signals"]:
        for s in doc["signals"]:
            lines.append(f"- {s}")
    else:
        lines.append("- (none)")

    lines.extend(
        [
            "",
            "## Trace timeline (P6)",
            "",
            "- **HTML**：`reports/trace_timeline_latest.html` — 若存在 baseline/chaos 两份 trace，为 **上下双图**（Baseline → Chaos），便于对照叙事。",
            "- **Mermaid**：`reports/trace_timeline_latest.mmd`（两段图，以 `%% ===` 分隔）。",
            "- 亦支持 `TRACE_TIMELINE_INPUT` / `python trace_timeline.py --input` 单文件模式。",
            "- 契约见 **`docs/plan/TRACE_CONTRACT.md`**。",
            "",
            "## Metrics snapshot",
            "",
            "```json",
            json.dumps(doc["metrics_snapshot"], indent=2, ensure_ascii=False),
            "```",
            "",
        ]
    )

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
