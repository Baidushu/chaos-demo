"""Test Case 2: AI Security Testing Demo."""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

_PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))

from demo.scenarios.security_test.runner import run_security_test


class TestSecurityDemo:
    """验证安全测试 Demo 可运行且拦截正确。"""

    def test_security_test_runs(self):
        """安全测试可运行。"""
        result = run_security_test()
        assert result["scenario"] == "AI Security Testing"
        assert result["total"] == 10
        stats = result["stats"]
        assert stats["blocked"] == 8  # 6 injections + 2 tool bypass
        assert stats["passed"] == 2   # 2 benign

    def test_prompt_injection_blocked(self):
        """Prompt注入被拦截。"""
        result = run_security_test("attack-001")
        r = result["results"][0]
        assert r["blocked"] is True
        assert "prompt_injection" in r["violations"][0] if r["violations"] else True
        assert r["attack_type"] == "prompt_injection"

    def test_tool_bypass_blocked(self):
        """工具越权被拦截。"""
        result = run_security_test("attack-006")
        r = result["results"][0]
        assert r["blocked"] is True
        assert r["attack_type"] == "tool_permission_bypass"

    def test_benign_input_passes(self):
        """正常用户输入通过安全检查。"""
        result = run_security_test("attack-008")
        r = result["results"][0]
        assert r["blocked"] is False
        assert r["attack_type"] == "benign"
        assert len(r["violations"]) == 0

    def test_all_injection_attacks_blocked(self):
        """所有Prompt注入攻击都被拦截。"""
        result = run_security_test()
        for r in result["results"]:
            if r["attack_type"] in ("prompt_injection", "system_prompt_leak"):
                assert r["blocked"] is True, f"{r['case_id']} should be blocked"

    def test_security_report_has_trace_id(self):
        """安全报告包含trace_id。"""
        result = run_security_test("attack-001")
        r = result["results"][0]
        assert r["trace_id"] != ""
        assert len(r["trace_id"]) > 0

    def test_security_report_structure(self):
        """验证输出报告结构符合规范。"""
        result = run_security_test("attack-001")
        r = result["results"][0]
        required_fields = ["case_id", "attack_type", "blocked", "reason", "trace_id", "violations", "risk_level"]
        for field in required_fields:
            assert field in r, f"Missing field: {field}"
