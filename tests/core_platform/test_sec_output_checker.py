"""Tests for OutputChecker — output safety validation."""

import pytest

from ai_platform.security.output_checker import OutputChecker
from ai_platform.security.policy import SecurityPolicy


class TestOutputCheckerBasic:
    def test_normal_output_passes(self):
        checker = OutputChecker(SecurityPolicy())
        result = checker.check("The capital of France is Paris.")
        assert result.passed is True

    def test_numeric_output_passes(self):
        checker = OutputChecker(SecurityPolicy())
        result = checker.check("42")
        assert result.passed is True

    def test_dict_output_passes(self):
        checker = OutputChecker(SecurityPolicy())
        result = checker.check({"answer": "Paris"})
        assert result.passed is True


class TestOutputCheckerEmpty:
    def test_rejects_empty_when_required(self):
        policy = SecurityPolicy(output_required=True)
        checker = OutputChecker(policy)
        result = checker.check("")
        assert result.passed is False
        assert "output_empty" in result.violations

    def test_rejects_whitespace_when_required(self):
        policy = SecurityPolicy(output_required=True)
        checker = OutputChecker(policy)
        result = checker.check("   \n  \t  ")
        assert result.passed is False
        assert "output_empty" in result.violations

    def test_accepts_empty_when_not_required(self):
        checker = OutputChecker(SecurityPolicy(output_required=False))
        result = checker.check("")
        assert result.passed is True

    def test_rejects_none_when_required(self):
        policy = SecurityPolicy(output_required=True)
        checker = OutputChecker(policy)
        result = checker.check(None)
        assert result.passed is False


class TestOutputCheckerLength:
    def test_rejects_over_max_length(self):
        policy = SecurityPolicy(max_output_length=100)
        checker = OutputChecker(policy)
        result = checker.check("x" * 101)
        assert result.passed is False
        assert "output_too_long" in " ".join(result.violations)

    def test_accepts_exact_max_length(self):
        policy = SecurityPolicy(max_output_length=100)
        checker = OutputChecker(policy)
        result = checker.check("x" * 100)
        assert result.passed is True

    def test_accepts_under_max_length(self):
        policy = SecurityPolicy(max_output_length=100)
        checker = OutputChecker(policy)
        result = checker.check("short")
        assert result.passed is True

    def test_default_max_length_is_8192(self):
        checker = OutputChecker(SecurityPolicy())
        result = checker.check("x" * 8192)
        assert result.passed is True


class TestOutputCheckerSensitiveKeywords:
    def test_sensitive_keyword_detected(self):
        policy = SecurityPolicy(sensitive_keywords=["password", "secret", "api_key"])
        checker = OutputChecker(policy)
        result = checker.check("My password is hunter2")
        assert result.passed is False
        assert "sensitive_keyword" in " ".join(result.violations)

    def test_case_insensitive_sensitive_keyword(self):
        policy = SecurityPolicy(sensitive_keywords=["Secret"])
        checker = OutputChecker(policy)
        result = checker.check("this is a SECRET message")
        assert result.passed is False

    def test_no_sensitive_keyword_passes(self):
        policy = SecurityPolicy(sensitive_keywords=["password"])
        checker = OutputChecker(policy)
        result = checker.check("The weather today is nice.")
        assert result.passed is True

    def test_multiple_sensitive_keywords_detected(self):
        policy = SecurityPolicy(sensitive_keywords=["password", "token", "key"])
        checker = OutputChecker(policy)
        result = checker.check("password=abc, token=xyz, key=123")
        assert result.passed is False
        assert len(result.violations) >= 3


class TestOutputCheckerDisabled:
    def test_output_check_disabled_passes(self):
        policy = SecurityPolicy(
            output_check_enabled=False,
            max_output_length=1,
            sensitive_keywords=["secret"],
            output_required=True,
        )
        checker = OutputChecker(policy)
        result = checker.check("")  # would fail if enabled
        assert result.passed is True

    def test_security_disabled_passes(self):
        policy = SecurityPolicy(
            security_enabled=False,
            sensitive_keywords=["secret"],
        )
        checker = OutputChecker(policy)
        result = checker.check("my secret is exposed")
        assert result.passed is True

    def test_permissive_passes_all(self):
        checker = OutputChecker(SecurityPolicy.permissive())
        result = checker.check("")  # empty when required would fail normally
        assert result.passed is True


class TestOutputCheckerMetadata:
    def test_pass_result_includes_output_length(self):
        checker = OutputChecker(SecurityPolicy())
        result = checker.check("hello")
        assert result.metadata.get("output_length") == 5

    def test_block_result_includes_output_length(self):
        policy = SecurityPolicy(max_output_length=5)
        checker = OutputChecker(policy)
        result = checker.check("hello world")  # 11 chars
        assert result.metadata.get("output_length") == 11


class TestOutputCheckerCustomObjects:
    def test_custom_object_with_str(self):
        class MyAnswer:
            def __str__(self):
                return "This is the answer"

        checker = OutputChecker(SecurityPolicy())
        result = checker.check(MyAnswer())
        assert result.passed is True

    def test_custom_object_with_sensitive_content(self):
        class MyAnswer:
            def __str__(self):
                return "Password is admin123"

        policy = SecurityPolicy(sensitive_keywords=["password"])
        checker = OutputChecker(policy)
        result = checker.check(MyAnswer())
        assert result.passed is False
