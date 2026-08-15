"""llm_assist 纯函数与采样逻辑（不调 LLM）。"""

from pathlib import Path

import llm_assist as la

_FIX = Path(__file__).resolve().parent / "fixtures" / "llm_assist"


def test_read_log_sample_tail():
    p = _FIX / "sample_logs.jsonl"
    text = la.read_log_sample(p, max_lines=2, max_chars=10000)
    assert "503" in text
    assert len(text.splitlines()) <= 2


def test_report_type_from_path_benchmark():
    data = {"baseline": {"p95_ms": 1}, "protected": {"p95_ms": 2}}
    assert la._report_type_from_path(Path("benchmark_latest.json"), data) == "benchmark"


def test_report_type_from_path_security():
    assert la._report_type_from_path(Path("security_scan_latest.json"), {}) == "security"
