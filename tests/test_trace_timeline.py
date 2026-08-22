"""trace_timeline：Mermaid 生成与路径解析（无系统临时目录）。"""

import json
import shutil
import sys
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


def test_dual_mode_two_mermaid_pres_in_html(monkeypatch, tmp_path):
    """输入与产物全部落在 pytest tmp_path（隔离 + 框架自动清理）。

    main() 的 meta 计算用 OUT.relative_to(ROOT)、输入 fixture 里的
    trace 路径是相对 ROOT 的——因此把 ROOT 一并指向 tmp_path，并把
    只读输入按原相对结构复制进去，做到对仓库零写入。
    （历史版本写共享的 tests/fixtures/_gen_dual/ 并手动 unlink，
    Windows 文件锁会打断 unlink 且残留毒化后续运行。）
    """
    monkeypatch.delenv("TRACE_TIMELINE_INPUT", raising=False)
    monkeypatch.setattr(tt, "ROOT", tmp_path)

    fix_in_tmp = tmp_path / "tests" / "fixtures" / "trace_timeline"
    fix_in_tmp.mkdir(parents=True)
    for name in ("trace_baseline.json", "trace_chaos.json", "chaos_compare_for_dual.json"):
        shutil.copyfile(_FIX / name, fix_in_tmp / name)

    gen = tmp_path / "out"
    gen.mkdir(parents=True)
    monkeypatch.setattr(tt, "OUT_DIR", gen)
    monkeypatch.setattr(tt, "OUT_MMD", gen / "trace_timeline_latest.mmd")
    monkeypatch.setattr(tt, "OUT_HTML", gen / "trace_timeline_latest.html")
    monkeypatch.setattr(tt, "CHAOS_COMPARE_JSON", fix_in_tmp / "chaos_compare_for_dual.json")
    monkeypatch.setattr(sys, "argv", ["trace_timeline.py"])

    tt.main()
    html = (gen / "trace_timeline_latest.html").read_text(encoding="utf-8")
    assert html.count('<pre class="mermaid">') == 2
    assert "Baseline" in html and "Chaos" in html
    meta = json.loads((gen / "trace_timeline_meta.json").read_text(encoding="utf-8"))
    assert meta.get("mode") == "dual"
