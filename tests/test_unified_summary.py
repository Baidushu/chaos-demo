"""unified_summary：聚合逻辑单测。

fixture 策略：所有报告路径映射到 pytest ``tmp_path``（每用例独立目录，
框架自动清理）——历史版本把 fixture 写进共享的 tests/fixtures/ 目录，
Windows 下 unlink 常被文件锁打断（OSError）且残留文件会毒化后续运行
（"无报告应 PASS"的用例读到上次残留即失败），已按顺序无关原则重写。
"""

import json
from pathlib import Path

import unified_summary as us


def _fake_paths(tmp_path: Path) -> dict[str, Path]:
    """全部报告路径指向隔离目录（默认均不存在 = 无报告场景）。"""
    return {k: tmp_path / f"{k}.json" for k in us.PATHS}


def test_build_summary_passes_when_no_reports(monkeypatch, tmp_path):
    monkeypatch.setattr(us, "PATHS", _fake_paths(tmp_path))
    doc = us.build_summary()
    assert doc["final_decision"] == "PASS"
    assert doc["reasons"] == []
    assert isinstance(doc["artifacts"], list)


def test_final_fail_from_gate_file(monkeypatch, tmp_path):
    gate_p = tmp_path / "unified_gate.json"
    gate_p.write_text(
        json.dumps({"final_decision": "FAIL", "reasons": ["benchmark: x"]}, ensure_ascii=False),
        encoding="utf-8",
    )
    paths = _fake_paths(tmp_path)
    paths["unified_gate"] = gate_p
    monkeypatch.setattr(us, "PATHS", paths)
    doc = us.build_summary()
    assert doc["final_decision"] == "FAIL"
    assert any("benchmark" in r for r in doc["reasons"])


def test_token_black_hole_marks_fail(monkeypatch, tmp_path):
    chaos_p = tmp_path / "chaos_compare.json"
    chaos_p.write_text(
        json.dumps(
            {
                "token_black_hole_gate": {"pass": False, "token_surge_ratio": 0.5},
                "delta": {"retry_rate": 0.01},
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )
    paths = _fake_paths(tmp_path)
    paths["chaos_compare"] = chaos_p
    monkeypatch.setattr(us, "PATHS", paths)
    doc = us.build_summary()
    assert doc["final_decision"] == "FAIL"
    assert any("token_black_hole" in r for r in doc["reasons"])


def test_release_markdown_sections(monkeypatch, tmp_path):
    monkeypatch.setattr(us, "PATHS", _fake_paths(tmp_path))
    doc = us.build_summary()
    md = us._write_markdown(doc)
    assert "# Release Summary" in md
    assert "## Checks" in md and "## Key regressions" in md
    assert "## Trace highlights" in md and "## Trend" in md
    assert "## LLM 辅助草稿" in md
    assert "**semantic_eval**:" in md
    assert "checks_summary" in doc


def test_trend_consecutive_regression_bullet(monkeypatch, tmp_path):
    monkeypatch.setattr(us, "PATHS", _fake_paths(tmp_path))
    monkeypatch.setattr(us, "_protected_p95_history_series", lambda: [100.0, 110.0, 120.0, 130.0])
    doc = us.build_summary()
    assert doc["metrics_snapshot"].get("benchmark_history_consecutive_p95_regressions") == 3
    assert any("连续" in b for b in doc["trend_bullets"])
