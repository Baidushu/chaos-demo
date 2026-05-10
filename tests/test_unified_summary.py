"""unified_summary：聚合逻辑单测（不写系统临时目录）。"""

import json
from pathlib import Path

import unified_summary as us

_FIX = Path(__file__).resolve().parent / "fixtures" / "unified_summary"


def _fake_paths() -> dict[str, Path]:
    return {k: _FIX / f"{k}.json" for k in us.PATHS}


def test_build_summary_passes_when_no_reports(monkeypatch):
    monkeypatch.setattr(us, "PATHS", _fake_paths())
    doc = us.build_summary()
    assert doc["final_decision"] == "PASS"
    assert doc["reasons"] == []
    assert isinstance(doc["artifacts"], list)


def test_final_fail_from_gate_file(monkeypatch):
    gate_p = _FIX / "unified_gate.json"
    gate_p.write_text(
        json.dumps({"final_decision": "FAIL", "reasons": ["benchmark: x"]}, ensure_ascii=False),
        encoding="utf-8",
    )
    try:
        paths = _fake_paths()
        paths["unified_gate"] = gate_p
        monkeypatch.setattr(us, "PATHS", paths)
        doc = us.build_summary()
        assert doc["final_decision"] == "FAIL"
        assert any("benchmark" in r for r in doc["reasons"])
    finally:
        if gate_p.exists():
            gate_p.unlink()


def test_token_black_hole_marks_fail(monkeypatch):
    chaos_p = _FIX / "chaos_compare.json"
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
    try:
        paths = _fake_paths()
        paths["chaos_compare"] = chaos_p
        monkeypatch.setattr(us, "PATHS", paths)
        doc = us.build_summary()
        assert doc["final_decision"] == "FAIL"
        assert any("token_black_hole" in r for r in doc["reasons"])
    finally:
        if chaos_p.exists():
            chaos_p.unlink()
