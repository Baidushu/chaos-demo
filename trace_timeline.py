"""
P6：从 Agent Runtime Trace JSON 生成 **Mermaid** + **极简 HTML**（CDN Mermaid），不写 SPA。

默认（无 --input、无环境变量 TRACE_TIMELINE_INPUT）：
  - chaos_compare_latest 中 baseline/chaos 两份 trace 均存在 → HTML **上下双图** + 拼接 .mmd（%% === 分段）；
  - 否则 chaos arm → agent_eval_trace_latest.json 单图。

显式单文件：--input 或 TRACE_TIMELINE_INPUT（优先于双轨）。

输出：reports/trace_timeline_latest.mmd / .html
"""
from __future__ import annotations

import argparse
import html as html_module
import json
import os
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent
AGENT_REPORTS = ROOT / "agent-eval" / "reports"
CHAOS_COMPARE_JSON = AGENT_REPORTS / "chaos_compare_latest.json"
DEFAULT_TRACE = AGENT_REPORTS / "agent_eval_trace_latest.json"
OUT_DIR = ROOT / "reports"
OUT_MMD = OUT_DIR / "trace_timeline_latest.mmd"
OUT_HTML = OUT_DIR / "trace_timeline_latest.html"


def _read_json(path: Path) -> dict | None:
    try:
        if path.is_file():
            return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        pass
    return None


def _safe_label(s: str, max_len: int = 96) -> str:
    t = str(s).replace('"', "'").replace("\n", " ").strip()
    if len(t) > max_len:
        t = t[: max_len - 1] + "…"
    return t


def _step_mermaid_label(st: dict, fallback_idx: int) -> str:
    n = st.get("step", fallback_idx + 1)
    tool = st.get("tool", "?")
    method = st.get("method", "")
    path = st.get("path", "")
    ri = st.get("retry_index", 0)
    lat = st.get("latency_ms", "")
    http = st.get("http_status", "")
    inj = " ⚡inj" if st.get("injected_fault") else ""
    err = st.get("error")
    err_bit = " err" if err else ""
    return _safe_label(
        f"#{n} {tool} r{ri}<br/>{method} {path}<br/>{lat}ms http={http}{inj}{err_bit}",
        max_len=120,
    )


def iter_cases_steps(doc: dict) -> list[tuple[str, list[dict]]]:
    out: list[tuple[str, list[dict]]] = []
    cases = doc.get("cases")
    if isinstance(cases, list) and cases:
        for i, c in enumerate(cases):
            if not isinstance(c, dict):
                continue
            cid = str(c.get("case_id") or c.get("id") or f"case_{i}")
            steps = c.get("steps") or []
            if isinstance(steps, list):
                out.append((cid, [s for s in steps if isinstance(s, dict)]))
    elif isinstance(doc.get("steps"), list):
        steps = [s for s in doc["steps"] if isinstance(s, dict)]
        out.append(("run", steps))
    return out


def build_mermaid(doc: dict, *, title: str, chart_id_prefix: str = "") -> str:
    """chart_id_prefix：多图同页时避免节点 ID 冲突（如 baseline / chaos 双轨）。"""
    pf = chart_id_prefix.strip() or ""
    lines: list[str] = [f"%% {_safe_label(title)}", "flowchart TD"]

    blocks = iter_cases_steps(doc)
    if not blocks:
        lines.append(f'  {pf}empty["（无 steps：检查 trace JSON 是否为 run_trace 聚合格式）"]')
        return "\n".join(lines)

    for bi, (cid, steps) in enumerate(blocks):
        sid = f"{pf}sg{bi}"
        lines.append(f'  subgraph {sid}["{_safe_label(cid)}"]')
        if not steps:
            lines.append(f'    {pf}e{bi}["（无 HTTP 步骤）"]')
        else:
            prev: str | None = None
            for si, st in enumerate(steps):
                nid = f"{pf}b{bi}s{si}"
                lab = _step_mermaid_label(st, si)
                lines.append(f"    {nid}[\"{lab}\"]")
                if prev:
                    lines.append(f"    {prev} --> {nid}")
                prev = nid
        lines.append("  end")

    return "\n".join(lines)


def build_html(mmd: str, *, page_title: str, source_path: str) -> str:
    # Mermaid 原文放入 <pre class="mermaid">；不经过 HTML 转义
    esc_title = html_module.escape(page_title)
    esc_src = html_module.escape(source_path)
    return f"""<!DOCTYPE html>
<html lang="zh-CN">
<head>
  <meta charset="utf-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1" />
  <title>{esc_title}</title>
  <style>
    body {{ font-family: system-ui, sans-serif; margin: 1rem; max-width: 1200px; }}
    .meta {{ color: #444; font-size: 0.9rem; margin-bottom: 1rem; }}
  </style>
</head>
<body>
  <h1>Agent trace timeline</h1>
  <p class="meta">source: <code>{esc_src}</code> · Mermaid via CDN · 离线请用 .mmd 自行渲染</p>
  <pre class="mermaid">
{mmd}
  </pre>
  <script type="module">
    import mermaid from "https://cdn.jsdelivr.net/npm/mermaid@10/dist/mermaid.esm.min.mjs";
    mermaid.initialize({{ startOnLoad: true, theme: "neutral" }});
  </script>
</body>
</html>
"""


def build_html_dual(
    *,
    mmd_baseline: str,
    mmd_chaos: str,
    baseline_src: str,
    chaos_src: str,
    page_title: str = "Trace timeline (baseline vs chaos)",
) -> str:
    esc_title = html_module.escape(page_title)
    esc_b = html_module.escape(baseline_src)
    esc_c = html_module.escape(chaos_src)
    return f"""<!DOCTYPE html>
<html lang="zh-CN">
<head>
  <meta charset="utf-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1" />
  <title>{esc_title}</title>
  <style>
    body {{ font-family: system-ui, sans-serif; margin: 1rem; max-width: 1200px; }}
    .meta {{ color: #444; font-size: 0.9rem; margin-bottom: 0.5rem; }}
    h2 {{ margin-top: 2rem; border-top: 1px solid #ddd; padding-top: 1rem; }}
    h2:first-of-type {{ border-top: none; padding-top: 0; margin-top: 0.5rem; }}
  </style>
</head>
<body>
  <h1>Agent trace timeline</h1>
  <p class="meta">Baseline / Chaos 上下对照（回归对比）· Mermaid CDN · 离线请将 <code>.mmd</code> 分段复制渲染</p>

  <h2>Baseline</h2>
  <p class="meta">source: <code>{esc_b}</code></p>
  <pre class="mermaid">
{mmd_baseline}
  </pre>

  <h2>Chaos</h2>
  <p class="meta">source: <code>{esc_c}</code></p>
  <pre class="mermaid">
{mmd_chaos}
  </pre>

  <script type="module">
    import mermaid from "https://cdn.jsdelivr.net/npm/mermaid@10/dist/mermaid.esm.min.mjs";
    mermaid.initialize({{ startOnLoad: true, theme: "neutral" }});
  </script>
</body>
</html>
"""


def _resolve_existing_path(raw: str) -> Path | None:
    """支持绝对路径、cwd 相对路径、仓库根相对路径。"""
    p = Path(raw.replace("\\", "/"))
    if p.is_file():
        return p
    if not p.is_absolute():
        q = ROOT / p
        if q.is_file():
            return q
    return None


def resolve_trace_path(args: argparse.Namespace) -> tuple[Path | None, str]:
    if args.input:
        p = _resolve_existing_path(args.input)
        if p is not None:
            return p, str(p)
        return None, str(Path(args.input))

    env = os.getenv("TRACE_TIMELINE_INPUT", "").strip()
    if env:
        p = _resolve_existing_path(env)
        if p is not None:
            return p, str(p)
        return None, env

    cc = _read_json(CHAOS_COMPARE_JSON)
    if cc and isinstance(cc.get("agent_trace_files"), dict):
        chaos = cc["agent_trace_files"].get("chaos")
        if chaos:
            p = _resolve_existing_path(str(chaos))
            if p is not None:
                return p, str(p)

    if DEFAULT_TRACE.is_file():
        return DEFAULT_TRACE, str(DEFAULT_TRACE)

    return None, "(no default trace file found)"


def resolve_chaos_compare_trace_pair() -> tuple[Path | None, Path | None]:
    """若存在 chaos_compare_latest 且两份 trace 均落盘，返回 (baseline_path, chaos_path)。"""
    cc = _read_json(CHAOS_COMPARE_JSON)
    if not cc or not isinstance(cc.get("agent_trace_files"), dict):
        return None, None
    af = cc["agent_trace_files"]
    b_raw, c_raw = af.get("baseline"), af.get("chaos")
    if not b_raw or not c_raw:
        return None, None
    bp = _resolve_existing_path(str(b_raw))
    cp = _resolve_existing_path(str(c_raw))
    if bp and cp and bp.is_file() and cp.is_file():
        return bp, cp
    return None, None


def main() -> None:
    parser = argparse.ArgumentParser(description="Generate Mermaid + HTML from agent trace JSON (P6).")
    parser.add_argument("--input", type=str, default=None, help="Path to trace JSON (run_trace aggregate format)")
    parser.add_argument("--title", type=str, default=None, help="Diagram title prefix")
    args = parser.parse_args()

    OUT_DIR.mkdir(parents=True, exist_ok=True)

    bp: Path | None = None
    cp: Path | None = None
    if not args.input and not os.getenv("TRACE_TIMELINE_INPUT", "").strip():
        bp, cp = resolve_chaos_compare_trace_pair()

    if args.input or os.getenv("TRACE_TIMELINE_INPUT", "").strip() or bp is None or cp is None:
        path, src_note = resolve_trace_path(args)
        if path is None:
            doc = {"cases": []}
            title = args.title or f"no trace input ({src_note})"
            mmd = build_mermaid(doc, title=title)
            meta: dict = {"mode": "single", "generated_at": int(time.time()), "source": None, "source_note": src_note}
        else:
            doc = _read_json(path) or {"cases": []}
            meta_bits = []
            if doc.get("trace_id"):
                meta_bits.append(f"trace_id={doc['trace_id'][:8]}…")
            if doc.get("eval_kind"):
                meta_bits.append(str(doc["eval_kind"]))
            suf = " · ".join(meta_bits) if meta_bits else path.name
            title = args.title or suf
            mmd = build_mermaid(doc, title=title)
            meta = {"mode": "single", "generated_at": int(time.time()), "source": str(path), "source_note": src_note}

        OUT_MMD.write_text(mmd, encoding="utf-8")
        OUT_HTML.write_text(
            build_html(mmd, page_title="Trace timeline", source_path=meta.get("source") or src_note),
            encoding="utf-8",
        )
    else:
        doc_b = _read_json(bp) or {"cases": []}
        doc_c = _read_json(cp) or {"cases": []}
        title_b = f"{args.title} — Baseline" if args.title else "Baseline trace"
        title_c = f"{args.title} — Chaos" if args.title else "Chaos trace"
        mmd_b = build_mermaid(doc_b, title=title_b, chart_id_prefix="bl")
        mmd_c = build_mermaid(doc_c, title=title_c, chart_id_prefix="ch")
        combined_mmd = (
            "%% === Baseline（上半区对应 HTML）===\n"
            f"{mmd_b}\n\n"
            "%% === Chaos ===\n"
            f"{mmd_c}\n"
        )
        OUT_MMD.write_text(combined_mmd, encoding="utf-8")
        OUT_HTML.write_text(
            build_html_dual(
                mmd_baseline=mmd_b,
                mmd_chaos=mmd_c,
                baseline_src=str(bp),
                chaos_src=str(cp),
            ),
            encoding="utf-8",
        )
        meta = {
            "mode": "dual",
            "generated_at": int(time.time()),
            "baseline": str(bp),
            "chaos": str(cp),
        }
        print(f"[TRACE_TIMELINE] dual baseline={bp} chaos={cp}")

    meta_path = OUT_DIR / "trace_timeline_meta.json"
    outs = {
        "mermaid": str(OUT_MMD.relative_to(ROOT)),
        "html": str(OUT_HTML.relative_to(ROOT)),
    }
    meta["outputs"] = outs
    meta_path.write_text(json.dumps(meta, ensure_ascii=False, indent=2), encoding="utf-8")

    if meta.get("mode") == "single":
        print(f"[TRACE_TIMELINE] source={meta.get('source') or meta.get('source_note')}")
    print(f"[TRACE_TIMELINE] wrote {OUT_MMD} / {OUT_HTML}")


if __name__ == "__main__":
    main()
