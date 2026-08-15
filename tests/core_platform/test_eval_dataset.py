from __future__ import annotations

import json
from pathlib import Path

from ai_platform.evaluation.dataset import load_json, write_json, write_jsonl


def test_load_json(tmp_path: Path):
    p = tmp_path / "test.json"
    p.write_text('{"a": 1}', encoding="utf-8")
    assert load_json(p) == {"a": 1}


def test_write_json(tmp_path: Path):
    p = tmp_path / "out.json"
    write_json(p, {"b": 2})
    assert json.loads(p.read_text(encoding="utf-8")) == {"b": 2}


def test_write_jsonl(tmp_path: Path):
    p = tmp_path / "out.jsonl"
    write_jsonl(p, [{"x": 1}, {"y": 2}])
    lines = p.read_text(encoding="utf-8").strip().split("\n")
    assert len(lines) == 2
    assert json.loads(lines[0]) == {"x": 1}
    assert json.loads(lines[1]) == {"y": 2}
