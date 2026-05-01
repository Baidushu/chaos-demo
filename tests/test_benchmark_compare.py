import os

import benchmark_compare as bc


def test_idempotency_keys_baseline_protected_differ():
    k1 = bc._idempotency_keys(3, 1, "baseline")
    k2 = bc._idempotency_keys(3, 1, "protected")
    assert k1 != k2
    assert all("baseline" in x for x in k1)
    assert all("protected" in x for x in k2)


def test_warmup_key_space_differs_from_main():
    w = bc._idempotency_keys(2, 1, "baseline-warmup")
    m = bc._idempotency_keys(2, 1, "baseline")
    assert w != m
    assert "warmup" in w[0]


def test_idempotency_keys_no_seed_unique():
    k = bc._idempotency_keys(20, None, "x")
    assert len(set(k)) == 20


def test_resolve_seed_cli_overrides_empty_env(monkeypatch):
    monkeypatch.delenv("BENCHMARK_SEED", raising=False)
    assert bc._resolve_seed("7") == 7
    assert bc._resolve_seed("0") == 0
    assert bc._resolve_seed("") is None


def test_resolve_seed_env_when_cli_absent(monkeypatch):
    monkeypatch.setenv("BENCHMARK_SEED", "9")
    assert bc._resolve_seed(None) == 9


def test_summarize_runs_uses_median_and_aggregate_status():
    summary = bc.summarize_runs(
        [
            {
                "qps": 10.0,
                "p50_ms": 100.0,
                "p95_ms": 200.0,
                "p99_ms": 250.0,
                "success_rate": 0.90,
                "degraded_rate": 0.05,
                "limited_rate": 0.00,
                "error_rate": 0.05,
                "status_count": {201: 9, 503: 1},
                "run_label": "r1",
            },
            {
                "qps": 12.0,
                "p50_ms": 110.0,
                "p95_ms": 220.0,
                "p99_ms": 260.0,
                "success_rate": 0.80,
                "degraded_rate": 0.10,
                "limited_rate": 0.00,
                "error_rate": 0.10,
                "status_count": {201: 8, 202: 1, 503: 1},
                "run_label": "r2",
            },
            {
                "qps": 11.0,
                "p50_ms": 105.0,
                "p95_ms": 210.0,
                "p99_ms": 255.0,
                "success_rate": 0.85,
                "degraded_rate": 0.05,
                "limited_rate": 0.05,
                "error_rate": 0.05,
                "status_count": {201: 8, 429: 1, 503: 1},
                "run_label": "r3",
            },
        ]
    )
    assert summary["run_count"] == 3
    assert summary["median"]["p95_ms"] == 210.0
    assert summary["median"]["qps"] == 11.0
    assert summary["median"]["status_count"][201] == 25
    assert summary["median"]["status_count"][503] == 3
    assert summary["representative_run"]["run_label"] == "r3"


def test_build_trend_report_compares_with_history():
    current = {
        "generated_at": 200,
        "baseline": {"p95_ms": 210.0},
        "protected": {"p95_ms": 180.0, "error_rate": 0.02, "run_count": 3},
    }
    history = [
        {"baseline": {"p95_ms": 220.0}, "protected": {"p95_ms": 190.0, "error_rate": 0.03}},
        {"baseline": {"p95_ms": 230.0}, "protected": {"p95_ms": 200.0, "error_rate": 0.04}},
    ]
    trend = bc.build_trend_report(current, history)
    assert trend["history_window"] == 2
    assert trend["previous_medians"]["protected_p95_ms"] == 195.0
    assert trend["delta_vs_history_median"]["protected_p95_ms"] == -15.0
