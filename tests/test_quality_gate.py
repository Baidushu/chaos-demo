import time
from pathlib import Path

import pytest

import quality_gate as qg


def test_load_benchmark_thresholds_default(monkeypatch):
    monkeypatch.delenv("QUALITY_GATE_ERROR_RATE_MAX", raising=False)
    monkeypatch.delenv("QUALITY_GATE_P99_MS_MAX", raising=False)
    monkeypatch.delenv("QUALITY_GATE_P95_REGRESSION_FACTOR_MAX", raising=False)
    monkeypatch.delenv("QUALITY_GATE_UNSTABLE_RATE_MAX", raising=False)
    monkeypatch.delenv("QUALITY_GATE_P95_STDEV_MAX", raising=False)
    t = qg.load_benchmark_thresholds()
    assert t["error_rate_max"] == 0.05
    assert t["p99_ms_max"] == 450.0
    assert t["p95_regression_factor_max"] == 1.10
    assert t["unstable_rate_max"] == 0.35
    assert t["p95_stdev_max"] == 0.0


def test_load_benchmark_thresholds_from_env(monkeypatch):
    monkeypatch.setenv("QUALITY_GATE_ERROR_RATE_MAX", "0.02")
    monkeypatch.setenv("QUALITY_GATE_P99_MS_MAX", "300")
    monkeypatch.setenv("QUALITY_GATE_P95_REGRESSION_FACTOR_MAX", "1.05")
    monkeypatch.setenv("QUALITY_GATE_UNSTABLE_RATE_MAX", "0.20")
    monkeypatch.setenv("QUALITY_GATE_P95_STDEV_MAX", "25")
    t = qg.load_benchmark_thresholds()
    assert t["error_rate_max"] == 0.02
    assert t["p99_ms_max"] == 300.0
    assert t["p95_regression_factor_max"] == 1.05
    assert t["unstable_rate_max"] == 0.20
    assert t["p95_stdev_max"] == 25.0


def test_check_report_freshness_pass(monkeypatch):
    monkeypatch.setenv("QUALITY_GATE_CHECK_FRESHNESS", "1")
    monkeypatch.setenv("QUALITY_GATE_MAX_REPORT_AGE_SEC", "60")
    data = {"generated_at": int(time.time()) - 10}
    qg.check_report_freshness(data, "benchmark")


def test_check_report_freshness_fails_when_stale(monkeypatch):
    monkeypatch.setenv("QUALITY_GATE_CHECK_FRESHNESS", "1")
    monkeypatch.setenv("QUALITY_GATE_MAX_REPORT_AGE_SEC", "1")
    data = {"generated_at": int(time.time()) - 10}
    with pytest.raises(qg.QualityGateError):
        qg.check_report_freshness(data, "benchmark")


def test_check_report_freshness_skipped_when_disabled(monkeypatch):
    monkeypatch.setenv("QUALITY_GATE_CHECK_FRESHNESS", "0")
    # Missing generated_at should not fail when freshness check is disabled.
    qg.check_report_freshness({}, "security")


def test_run_check_with_retries_pass_after_one_retry(monkeypatch):
    monkeypatch.setenv("QUALITY_GATE_RETRY_ATTEMPTS", "2")
    monkeypatch.setenv("QUALITY_GATE_RETRY_DELAY_MS", "0")
    state = {"count": 0}

    def flaky_check():
        state["count"] += 1
        if state["count"] == 1:
            raise SystemExit(1)

    qg.run_check_with_retries("benchmark", flaky_check)
    assert state["count"] == 2


def test_security_report_meta_includes_context_and_target():
    s = qg.security_report_meta(
        {"context_aware": True, "base_url": "http://127.0.0.1:5000", "findings": []}
    )
    assert "context_aware=True" in s
    assert "target=http://127.0.0.1:5000" in s


def test_security_report_meta_empty_when_absent():
    assert qg.security_report_meta({"findings": []}) == ""


def test_run_check_with_retries_fail_after_exhausted(monkeypatch):
    monkeypatch.setenv("QUALITY_GATE_RETRY_ATTEMPTS", "2")
    monkeypatch.setenv("QUALITY_GATE_RETRY_DELAY_MS", "0")

    def always_fail():
        raise SystemExit(1)

    with pytest.raises(SystemExit):
        qg.run_check_with_retries("security", always_fail)


_FIX = Path(__file__).resolve().parent / "fixtures"


def test_check_benchmark_trend_gate_skipped_when_disabled(monkeypatch):
    monkeypatch.delenv("UNIFIED_GATE_TREND_ENABLED", raising=False)
    monkeypatch.setattr(qg, "BENCHMARK_TREND_PATH", _FIX / "nonexistent_trend.json")
    assert qg.check_benchmark_trend_gate() == "SKIPPED"


def test_check_benchmark_trend_gate_passes_when_ratio_ok(monkeypatch):
    monkeypatch.setenv("UNIFIED_GATE_TREND_ENABLED", "1")
    monkeypatch.setenv("UNIFIED_GATE_TREND_PROTECTED_P95_RATIO_MAX", "1.2")
    monkeypatch.setattr(qg, "BENCHMARK_TREND_PATH", _FIX / "benchmark_trend_pass.json")
    assert qg.check_benchmark_trend_gate() == "PASS"


def test_check_benchmark_trend_gate_fails_when_ratio_high(monkeypatch):
    monkeypatch.setenv("UNIFIED_GATE_TREND_ENABLED", "1")
    monkeypatch.setenv("UNIFIED_GATE_TREND_PROTECTED_P95_RATIO_MAX", "1.1")
    monkeypatch.setattr(qg, "BENCHMARK_TREND_PATH", _FIX / "benchmark_trend_fail.json")
    with pytest.raises(qg.QualityGateError):
        qg.check_benchmark_trend_gate()


def test_check_benchmark_trend_gate_skipped_no_history(monkeypatch):
    monkeypatch.setenv("UNIFIED_GATE_TREND_ENABLED", "1")
    monkeypatch.setattr(qg, "BENCHMARK_TREND_PATH", _FIX / "benchmark_trend_no_history.json")
    assert qg.check_benchmark_trend_gate() == "SKIPPED"
