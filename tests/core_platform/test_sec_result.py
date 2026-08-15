"""Tests for SecurityResult — unified security check outcome."""

import time

import pytest

from ai_platform.security.security_result import SecurityResult


class TestSecurityResultCreation:
    def test_default_result_is_pass(self):
        result = SecurityResult()
        assert result.passed is True
        assert result.risk_level == "none"
        assert result.violations == []

    def test_pass_factory(self):
        result = SecurityResult.pass_(check_name="test_check", metadata={"key": "val"})
        assert result.passed is True
        assert result.risk_level == "none"
        assert result.check_name == "test_check"
        assert result.metadata == {"key": "val"}
        assert result.violations == []

    def test_block_factory(self):
        result = SecurityResult.block(
            risk_level="high",
            violations=["bad input detected"],
            check_name="input_validator",
            metadata={"length": 5000},
        )
        assert result.passed is False
        assert result.risk_level == "high"
        assert result.check_name == "input_validator"
        assert result.violations == ["bad input detected"]
        assert result.metadata == {"length": 5000}

    def test_block_factory_defaults(self):
        result = SecurityResult.block()
        assert result.passed is False
        assert result.risk_level == "high"
        assert result.violations == []
        assert result.check_name == ""


class TestSecurityResultWorst:
    def test_pass_and_pass_returns_pass(self):
        a = SecurityResult.pass_()
        b = SecurityResult.pass_()
        worst = SecurityResult.worst(a, b)
        assert worst.passed is True
        assert worst.risk_level == "none"

    def test_pass_and_block_returns_block(self):
        a = SecurityResult.pass_()
        b = SecurityResult.block(risk_level="high", violations=["injection"])
        worst = SecurityResult.worst(a, b)
        assert worst.passed is False
        assert worst.risk_level == "high"
        assert "injection" in worst.violations

    def test_block_and_pass_returns_block(self):
        a = SecurityResult.block(risk_level="medium", violations=["keyword"])
        b = SecurityResult.pass_()
        worst = SecurityResult.worst(a, b)
        assert worst.passed is False
        assert worst.risk_level == "medium"

    def test_two_blocks_returns_most_severe(self):
        # critical > high > medium > low
        a = SecurityResult.block(risk_level="medium", violations=["v1"])
        b = SecurityResult.block(risk_level="high", violations=["v2"])
        worst = SecurityResult.worst(a, b)
        assert worst.passed is False
        assert worst.risk_level == "high"

    def test_critical_overrides_high(self):
        a = SecurityResult.block(risk_level="critical", violations=["very bad"])
        b = SecurityResult.block(risk_level="high", violations=["bad"])
        worst = SecurityResult.worst(a, b)
        assert worst.risk_level == "critical"

    def test_violations_are_merged(self):
        a = SecurityResult.block(risk_level="high", violations=["v1"])
        b = SecurityResult.block(risk_level="medium", violations=["v2", "v3"])
        worst = SecurityResult.worst(a, b)
        assert "v1" in worst.violations
        assert "v2" in worst.violations
        assert "v3" in worst.violations

    def test_duplicate_violations_are_not_duplicated(self):
        a = SecurityResult.block(risk_level="high", violations=["v1", "v2"])
        b = SecurityResult.block(risk_level="high", violations=["v2", "v3"])
        worst = SecurityResult.worst(a, b)
        assert sorted(worst.violations) == ["v1", "v2", "v3"]


class TestSecurityResultSerialization:
    def test_as_dict_pass(self):
        result = SecurityResult.pass_(check_name="test", metadata={"abc": 123})
        d = result.as_dict()
        assert d["passed"] is True
        assert d["risk_level"] == "none"
        assert d["check_name"] == "test"
        assert d["metadata"] == {"abc": 123}
        assert "timestamp" in d

    def test_as_dict_block(self):
        result = SecurityResult.block(
            risk_level="high",
            violations=["injection_detected"],
            check_name="prompt_guard",
            metadata={"pattern": "jailbreak"},
        )
        d = result.as_dict()
        assert d["passed"] is False
        assert d["risk_level"] == "high"
        assert d["check_name"] == "prompt_guard"
        assert d["violations"] == ["injection_detected"]


class TestSecurityResultProperties:
    def test_has_timestamp(self):
        now = time.time()
        result = SecurityResult()
        assert abs(result.timestamp - now) < 1.0

    def test_default_check_name(self):
        result = SecurityResult()
        assert result.check_name == ""
