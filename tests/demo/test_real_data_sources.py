"""真实数据源测试：Prometheus 解析、JSONL 日志读取、工具真实/降级两路径。"""

from __future__ import annotations

import json
import time
from pathlib import Path

import pytest

from demo.scenarios.incident_analysis import data_sources
from demo.scenarios.incident_analysis import runner
from demo.scenarios.incident_analysis.runner import QueryLogsTool, QueryMetricsTool

PROM_TEXT = """\
# HELP http_requests_total Total HTTP requests
# TYPE http_requests_total counter
http_requests_total{method="POST",route="/order",status="201"} 180
http_requests_total{method="GET",route="/order",status="200"} 20
# HELP http_request_errors_total Total HTTP 5xx responses
# TYPE http_request_errors_total counter
http_request_errors_total{method="POST",route="/order"} 10
# HELP http_request_duration_seconds HTTP request duration in seconds
# TYPE http_request_duration_seconds histogram
http_request_duration_seconds_bucket{method="POST",route="/order",le="0.1"} 100
http_request_duration_seconds_bucket{method="POST",route="/order",le="0.5"} 150
http_request_duration_seconds_bucket{method="POST",route="/order",le="1"} 180
http_request_duration_seconds_bucket{method="POST",route="/order",le="2"} 200
http_request_duration_seconds_bucket{method="POST",route="/order",le="+Inf"} 200
http_request_duration_seconds_count{method="POST",route="/order"} 200
http_request_duration_seconds_sum{method="POST",route="/order"} 96
orders_rate_limited_total 7
orders_circuit_open_total 3
chaos_active_experiment{fault_type="latency",target="order"} 1
circuit_breaker_state{resource="order"} 1
"""


class TestPrometheusParsing:
    def test_parse_prometheus_text(self):
        parsed = data_sources.parse_prometheus_text(PROM_TEXT)
        assert parsed["http_requests_total"][("method=POST", "route=/order", "status=201")] == 180
        assert parsed["orders_rate_limited_total"][()] == 7
        assert parsed["circuit_breaker_state"][("resource=order",)] == 1

    def test_compute_service_metrics_aggregates(self):
        parsed = data_sources.parse_prometheus_text(PROM_TEXT)
        m = data_sources.compute_service_metrics(parsed)
        assert m["requests_total"] == 200
        assert m["errors_total"] == 10
        assert m["error_rate"] == pytest.approx(0.05)
        # p50: target=100 → 命中 le=0.1 桶（100 条）
        assert m["latency_p50_ms"] == pytest.approx(100.0)
        # p99: target=198 → 在 le=1(180) 与 le=2(200) 之间线性插值
        assert m["latency_p99_ms"] == pytest.approx(1900.0)
        assert m["rate_limited_total"] == 7
        assert m["circuit_open_total"] == 3
        assert m["active_experiments"] == 1
        assert m["breaker_state"] == 1
        assert m["source"] == "prometheus"

    def test_compute_service_metrics_empty_input(self):
        m = data_sources.compute_service_metrics({})
        assert m["error_rate"] == 0.0
        assert m["latency_p99_ms"] is None
        assert m["requests_total"] == 0


class TestFetchMetrics:
    def test_fetch_metrics_returns_none_on_network_error(self, monkeypatch):
        def boom(*args, **kwargs):
            raise OSError("connection refused")

        monkeypatch.setattr(data_sources.urllib.request, "urlopen", boom)
        assert data_sources.fetch_metrics("http://127.0.0.1:5000") is None

    def test_fetch_metrics_returns_none_on_empty_body(self, monkeypatch):
        class FakeResp:
            def __enter__(self):
                return self

            def __exit__(self, *exc):
                return False

            def read(self):
                return b"# no samples\n"

        monkeypatch.setattr(data_sources.urllib.request, "urlopen", lambda url, timeout: FakeResp())
        assert data_sources.fetch_metrics("http://127.0.0.1:5000") is None


class TestQueryMetricsTool:
    def test_real_source_when_fetch_succeeds(self, monkeypatch):
        canned = {"error_rate": 0.5, "latency_p99_ms": 300.0, "requests_total": 100, "source": "prometheus"}
        monkeypatch.setattr(runner, "fetch_metrics", lambda base_url: dict(canned))
        result = QueryMetricsTool().execute({"service": "order-api"})
        assert result.ok
        assert result.result["metrics"]["source"] == "prometheus"
        assert result.result["metrics"]["error_rate"] == 0.5
        assert result.metadata["source"] == "prometheus"

    def test_fallback_to_simulated_when_fetch_fails(self, monkeypatch):
        monkeypatch.setattr(runner, "fetch_metrics", lambda base_url: None)
        result = QueryMetricsTool().execute({"service": "order-api"})
        assert result.ok
        assert result.result["metrics"]["source"] == "simulated"
        assert result.result["metrics"]["error_rate"] == 0.35
        assert result.metadata["source"] == "simulated"


class TestReadRecentLogs:
    def _write_records(self, path: Path, records: list[dict]) -> None:
        path.write_text("".join(json.dumps(r, ensure_ascii=False) + "\n" for r in records), encoding="utf-8")

    def test_reads_and_formats_jsonl(self, tmp_path):
        now = int(time.time())
        recs = [
            {"ts": now - 10, "method": "POST", "path": "/order", "query": "", "headers": {},
             "body": {"item_id": "sku-ok"}, "status": 201},
            {"ts": now - 5, "method": "POST", "path": "/order", "query": "", "headers": {},
             "body": {"item_id": "sku-findme"}, "status": 201},
        ]
        log_file = tmp_path / "traffic.jsonl"
        self._write_records(log_file, recs)
        lines = data_sources.read_recent_logs(log_file, limit=50)
        assert lines is not None and len(lines) == 2
        assert all("POST /order -> 201" in line for line in lines)
        assert "sku-ok" in lines[0]

    def test_keyword_filter(self, tmp_path):
        now = int(time.time())
        recs = [
            {"ts": now, "method": "POST", "path": "/order", "body": {"item_id": "sku-keep"}, "status": 201},
            {"ts": now, "method": "GET", "path": "/order", "body": {}, "status": 200},
        ]
        log_file = tmp_path / "traffic.jsonl"
        self._write_records(log_file, recs)
        lines = data_sources.read_recent_logs(log_file, limit=50, keyword="sku-keep")
        assert lines is not None and len(lines) == 1

    def test_time_range_filters_old_records(self, tmp_path):
        now = int(time.time())
        recs = [
            {"ts": now - 3600, "method": "POST", "path": "/order", "body": {}, "status": 201},
            {"ts": now - 10, "method": "POST", "path": "/order", "body": {}, "status": 201},
        ]
        log_file = tmp_path / "traffic.jsonl"
        self._write_records(log_file, recs)
        lines = data_sources.read_recent_logs(log_file, limit=50, time_range="5m")
        assert lines is not None and len(lines) == 1

    def test_missing_file_returns_none(self, tmp_path):
        assert data_sources.read_recent_logs(tmp_path / "nope.jsonl") is None


class TestQueryLogsTool:
    def test_real_source_reads_jsonl(self, tmp_path, monkeypatch):
        now = int(time.time())
        recs = [
            {"ts": now, "method": "POST", "path": "/order", "body": {"item_id": "sku-keep"}, "status": 201},
            {"ts": now, "method": "POST", "path": "/order", "body": {"item_id": "sku-drop"}, "status": 201},
        ]
        log_file = tmp_path / "traffic.jsonl"
        log_file.write_text(
            "".join(json.dumps(r, ensure_ascii=False) + "\n" for r in recs), encoding="utf-8"
        )
        monkeypatch.setenv("CHAOS_LOG_FILE", str(log_file))
        result = QueryLogsTool().execute({"service": "order-api", "keyword": "sku-keep"})
        assert result.ok
        assert result.result["count"] == 1
        assert result.metadata["source"] == "traffic_record"

    def test_fallback_when_file_missing(self, tmp_path, monkeypatch):
        monkeypatch.setenv("CHAOS_LOG_FILE", str(tmp_path / "missing.jsonl"))
        result = QueryLogsTool().execute({"service": "order-api"})
        assert result.ok
        assert result.result["count"] == len(runner._SIMULATED_LOGS["order-api"])
        assert result.metadata["source"] == "simulated"


class TestDiagnosisReportSources:
    def test_report_carries_sources_with_simulated_fallback(self, monkeypatch):
        """离线环境跑完整诊断：报告标注 simulated 来源且结构完整。"""
        monkeypatch.setattr(runner, "fetch_metrics", lambda base_url: None)
        monkeypatch.setenv("CHAOS_LOG_FILE", str(Path(".") / "definitely_missing.jsonl"))
        out = runner.run_incident_diagnosis("incident-001")
        report = out["results"][0]["report"]
        assert report["log_source"] == "simulated"
        assert report["metrics_source"] == "simulated"
        assert report["called_tools"] == ["query_logs", "query_metrics", "analyze_incident"]
