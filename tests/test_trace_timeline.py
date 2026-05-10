"""trace_timeline：Mermaid 生成与路径解析（无系统临时目录）。"""

import json
from pathlib import Path

import trace_timeline as tt

_FIX = Path(__file__).resolve().parent / "fixtures" / "trace_timeline"
_SAMPLE = _FIX / "sample_trace.json"


def test_iter_cases_steps_reads_aggregate():
    doc = json.loads(_SAMPLE.read_text(encoding="utf-8"))
    blocks = tt.iter_cases_steps(doc)
    assert len(blocks) == 1
    assert blocks[0][0] == "c1"
    assert len(blocks[0][1]) == 2


def test_build_mermaid_contains_steps():
    doc = json.loads(_SAMPLE.read_text(encoding="utf-8"))
    m = tt.build_mermaid(doc, title="unit-test")
    assert "flowchart TD" in m
    assert "place_order" in m
    assert "GET" in m
    assert "c1" in m


def test_build_mermaid_top_level_steps_only():
    doc = {"steps": [{"step": 1, "type": "tool_call", "tool": "t", "method": "GET", "path": "/p", "retry_index": 0, "latency_ms": 1, "http_status": 200, "error": None, "injected_fault": False}]}
    m = tt.build_mermaid(doc, title="x")
    assert "run" in m or "GET" in m


def test_resolve_existing_path_relative_to_repo():
    rel = str(_SAMPLE.relative_to(tt.ROOT)).replace("\\", "/")
    p = tt._resolve_existing_path(rel)
    assert p is not None
    assert p.is_file()


def test_build_mermaid_prefixes_avoid_id_collision():
    doc = json.loads(_SAMPLE.read_text(encoding="utf-8"))
    m_bl = tt.build_mermaid(doc, title="B", chart_id_prefix="bl")
    m_ch = tt.build_mermaid(doc, title="C", chart_id_prefix="ch")
    assert "blsg0" in m_bl and "chsg0" in m_ch
    assert "blb0s0" in m_bl and "chb0s0" in m_ch


def test_dual_mode_two_mermaid_pres_in_html(monkeypatch):
    import sys

    monkeypatch.delenv("TRACE_TIMELINE_INPUT", raising=False)
    gen = _FIX / "_gen_dual"
    gen.mkdir(parents=True, exist_ok=True)
    monkeypatch.setattr(tt, "OUT_DIR", gen)
    monkeypatch.setattr(tt, "OUT_MMD", gen / "trace_timeline_latest.mmd")
    monkeypatch.setattr(tt, "OUT_HTML", gen / "trace_timeline_latest.html")
    monkeypatch.setattr(tt, "CHAOS_COMPARE_JSON", _FIX / "chaos_compare_for_dual.json")
    monkeypatch.setattr(sys, "argv", ["trace_timeline.py"])
    try:
        tt.main()
        html = (gen / "trace_timeline_latest.html").read_text(encoding="utf-8")
        assert html.count('<pre class="mermaid">') == 2
        assert "Baseline" in html and "Chaos" in html
        meta = json.loads((gen / "trace_timeline_meta.json").read_text(encoding="utf-8"))
        assert meta.get("mode") == "dual"
    finally:
        for name in ("trace_timeline_latest.mmd", "trace_timeline_latest.html", "trace_timeline_meta.json"):
            p = gen / name
            if p.exists():
                p.unlink()
