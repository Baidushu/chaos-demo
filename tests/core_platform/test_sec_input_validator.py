"""Tests for InputValidator — input validation (empty, length, blocked keywords, patterns)."""

import pytest

from ai_platform.security.input_validator import InputValidator
from ai_platform.security.policy import SecurityPolicy


class TestInputValidatorBasic:
    def test_validates_normal_input(self):
        validator = InputValidator(SecurityPolicy())
        result = validator.validate("Hello, how are you?")
        assert result.passed is True

    def test_validates_list_input(self):
        validator = InputValidator(SecurityPolicy())
        result = validator.validate(["line1", "line2"])
        assert result.passed is True

    def test_validates_dict_input(self):
        validator = InputValidator(SecurityPolicy())
        result = validator.validate({"input": "What is AI?"})
        assert result.passed is True


class TestInputValidatorEmpty:
    def test_rejects_none(self):
        validator = InputValidator(SecurityPolicy(min_input_length=1))
        result = validator.validate(None)
        assert result.passed is False
        assert "input_empty" in result.violations

    def test_rejects_empty_string(self):
        validator = InputValidator(SecurityPolicy(min_input_length=1))
        result = validator.validate("")
        assert result.passed is False
        assert "input_empty" in result.violations

    def test_rejects_whitespace_only(self):
        validator = InputValidator(SecurityPolicy(min_input_length=1))
        result = validator.validate("   ")
        assert result.passed is False

    def test_accepts_any_when_min_length_zero(self):
        validator = InputValidator(SecurityPolicy(min_input_length=0))
        result = validator.validate("")
        assert result.passed is True


class TestInputValidatorLength:
    def test_rejects_over_max_length(self):
        validator = InputValidator(SecurityPolicy(max_input_length=10))
        result = validator.validate("a" * 11)
        assert result.passed is False
        assert any("too_long" in v for v in result.violations)

    def test_accepts_exact_max_length(self):
        validator = InputValidator(SecurityPolicy(max_input_length=10))
        result = validator.validate("a" * 10)
        assert result.passed is True

    def test_accepts_under_max_length(self):
        validator = InputValidator(SecurityPolicy(max_input_length=100))
        result = validator.validate("short")
        assert result.passed is True

    def test_length_check_on_none(self):
        validator = InputValidator(SecurityPolicy(max_input_length=0))
        # None is caught by empty check first, but if min_length=0, it should still fail on none
        validator2 = InputValidator(SecurityPolicy(max_input_length=100, min_input_length=0))
        result = validator2.validate(None)
        # None after min_length=0 should pass empty check
        # But max_input_length check extracts text from None -> ""
        assert result.passed is True


class TestInputValidatorBlockedKeywords:
    def test_rejects_blocked_keyword(self):
        validator = InputValidator(
            SecurityPolicy(blocked_keywords=["badword", "forbidden"])
        )
        result = validator.validate("this contains badword in the text")
        assert result.passed is False
        assert "blocked_keyword" in " ".join(result.violations)

    def test_case_insensitive_keyword_match(self):
        validator = InputValidator(
            SecurityPolicy(blocked_keywords=["BadWord"])
        )
        result = validator.validate("this has BADWORD here")
        assert result.passed is False

    def test_no_keyword_match_passes(self):
        validator = InputValidator(
            SecurityPolicy(blocked_keywords=["badword"])
        )
        result = validator.validate("this is clean text")
        assert result.passed is True


class TestInputValidatorBlockedPatterns:
    def test_rejects_blocked_regex(self):
        validator = InputValidator(
            SecurityPolicy(blocked_patterns=[r"\b\d{16}\b"])  # 16-digit numbers
        )
        result = validator.validate("card: 1234567890123456")
        assert result.passed is False
        assert "blocked_pattern" in " ".join(result.violations)

    def test_pattern_not_matched_passes(self):
        validator = InputValidator(
            SecurityPolicy(blocked_patterns=[r"\b\d{16}\b"])
        )
        result = validator.validate("card: 1234-5678-9012-3456")
        assert result.passed is True

    def test_multiple_patterns_checked(self):
        validator = InputValidator(
            SecurityPolicy(blocked_patterns=[r"password", r"secret", r"token"])
        )
        result = validator.validate("my secret token is exposed")
        assert result.passed is False
        assert len(result.violations) >= 2


class TestInputValidatorDisabled:
    def test_disabled_security_passes(self):
        validator = InputValidator(SecurityPolicy(security_enabled=False, max_input_length=1))
        result = validator.validate("much longer than allowed")
        assert result.passed is True

    def test_permissive_policy_passes(self):
        validator = InputValidator(SecurityPolicy.permissive())
        result = validator.validate("any input at all")
        assert result.passed is True


class TestInputValidatorEdgeCases:
    def test_integer_input(self):
        validator = InputValidator(SecurityPolicy())
        result = validator.validate(42)
        assert result.passed is True

    def test_float_input(self):
        validator = InputValidator(SecurityPolicy())
        result = validator.validate(3.14)
        assert result.passed is True

    def test_bool_input(self):
        validator = InputValidator(SecurityPolicy())
        result = validator.validate(True)
        assert result.passed is True

    def test_list_with_blocked_keyword(self):
        validator = InputValidator(SecurityPolicy(blocked_keywords=["bad"]))
        result = validator.validate(["this is bad"])
        assert result.passed is False

    def test_dict_with_blocked_keyword_in_value(self):
        validator = InputValidator(SecurityPolicy(blocked_keywords=["bad"]))
        result = validator.validate({"text": "this is bad"})
        assert result.passed is False
