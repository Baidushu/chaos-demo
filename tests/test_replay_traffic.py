from pathlib import Path

import replay_traffic as rt


def test_resolve_input_path_uses_builtin_sample_for_missing_file():
    requested = Path("reports/definitely-missing-traffic.jsonl")
    resolved, used_sample = rt.resolve_input_path(requested, allow_builtin_sample=True)
    assert used_sample is True
    assert resolved == rt.BUILTIN_SAMPLE_PATH


def test_build_path_stats_groups_rows():
    rows = [
        {"path": "/order", "status": 201, "elapsed_ms": 10},
        {"path": "/order", "status": 503, "elapsed_ms": 20},
        {"path": "/order/1", "status": 200, "elapsed_ms": 5},
    ]
    stats = rt.build_path_stats(rows)
    assert stats[0]["path"] == "/order"
    assert stats[0]["count"] == 2
    assert stats[0]["ok"] == 1
