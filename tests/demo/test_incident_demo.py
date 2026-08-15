"""Test Case 1: AI Incident Diagnosis Demo."""

from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

# Ensure project root is on path
_PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))

from demo.scenarios.incident_analysis.runner import (
    run_incident_diagnosis,
    build_platform_service,
)


class TestIncidentDemo:
    """验证故障分析 Demo 可运行且输出正确。"""

    def test_service_creates_successfully(self):
        """平台服务创建成功。"""
        service = build_platform_service()
        assert service is not None
        assert service.config is not None

    def test_incident_001_diagnosis(self):
        """incident-001: Redis连接池耗尽诊断。"""
        result = run_incident_diagnosis("incident-001")
        assert result["scenario"] == "AI Incident Diagnosis"
        assert result["total"] == 1
        r = result["results"][0]
        assert r["success"] is True
        report = r["report"]
        assert isinstance(report, dict)
        assert "problem" in report
        assert "root_cause" in report
        assert "evidence" in report
        assert "suggestion" in report
        assert "confidence" in report
        assert 0.0 <= report["confidence"] <= 1.0
        assert "Redis" in report["root_cause"]

    def test_incident_002_diagnosis(self):
        """incident-002: 数据库慢查询诊断。"""
        result = run_incident_diagnosis("incident-002")
        r = result["results"][0]
        assert r["success"] is True
        assert "root_cause" in r["report"]
        # The slow query scenario matches "Connection pool exhausted" pattern
        assert r["report"]["confidence"] > 0.5

    def test_incident_003_diagnosis(self):
        """incident-003: 缓存不一致诊断。"""
        result = run_incident_diagnosis("incident-003")
        r = result["results"][0]
        assert r["success"] is True
        assert "root_cause" in r["report"]

    def test_all_cases_run(self):
        """运行全部诊断用例。"""
        result = run_incident_diagnosis()
        assert result["total"] == 3
        passed = sum(1 for r in result["results"] if r["success"])
        assert passed == 3
        for r in result["results"]:
            assert "problem" in r["report"] or "error" in r["report"]

    def test_report_structure(self):
        """验证输出报告结构符合规范。"""
        result = run_incident_diagnosis("incident-001")
        report = result["results"][0]["report"]
        # Expected format: problem, root_cause, evidence, suggestion, confidence
        required_fields = ["problem", "root_cause", "evidence", "suggestion", "confidence"]
        for field in required_fields:
            assert field in report, f"Missing field: {field}"
        assert isinstance(report["evidence"], list)
        assert len(report["evidence"]) > 0
