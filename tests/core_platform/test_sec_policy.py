"""Tests for SecurityPolicy — unified security configuration."""

import pytest

from ai_platform.security.policy import SecurityPolicy


class TestSecurityPolicyDefaults:
    def test_default_policy_has_security_enabled(self):
        p = SecurityPolicy()
        assert p.security_enabled is True

    def test_default_max_input_length(self):
        p = SecurityPolicy()
        assert p.max_input_length == 4096

    def test_default_output_check_enabled(self):
        p = SecurityPolicy()
        assert p.output_check_enabled is True

    def test_default_block_flags(self):
        p = SecurityPolicy()
        assert p.block_on_input_violation is True
        assert p.block_on_injection is True
        assert p.block_on_permission_denied is True
        assert p.block_on_output_violation is True

    def test_default_lists_are_empty(self):
        p = SecurityPolicy()
        assert p.blocked_keywords == []
        assert p.blocked_patterns == []
        assert p.allowed_tools == []
        assert p.blocked_tools == []
        assert p.sensitive_keywords == []

    def test_injection_patterns_have_defaults(self):
        p = SecurityPolicy()
        assert len(p.prompt_injection_patterns) == 22
        assert "jailbreak" in p.prompt_injection_patterns
        assert "ignore previous instruction" in p.prompt_injection_patterns


class TestSecurityPolicyFactoryMethods:
    def test_default_classmethod(self):
        p = SecurityPolicy.default()
        assert p.security_enabled is True

    def test_permissive_disables_all_security(self):
        p = SecurityPolicy.permissive()
        assert p.security_enabled is False
        assert p.prompt_injection_enabled is False
        assert p.tool_permission_enabled is False
        assert p.output_check_enabled is False

    def test_permissive_policy_does_not_block(self):
        p = SecurityPolicy.permissive()
        assert p.block_on_input_violation is False
        assert p.block_on_injection is False


class TestSecurityPolicySerialization:
    def test_to_dict_roundtrip(self):
        p = SecurityPolicy(
            max_input_length=1024,
            allowed_tools=["search", "calc"],
            blocked_tools=["delete"],
            sensitive_keywords=["password", "secret"],
        )
        d = p.to_dict()
        restored = SecurityPolicy.from_dict(d)
        assert restored.max_input_length == 1024
        assert restored.allowed_tools == ["search", "calc"]
        assert restored.blocked_tools == ["delete"]
        assert restored.sensitive_keywords == ["password", "secret"]

    def test_to_dict_includes_all_fields(self):
        p = SecurityPolicy()
        d = p.to_dict()
        assert "max_input_length" in d
        assert "max_output_length" in d
        assert "security_enabled" in d
        assert "prompt_injection_enabled" in d
        assert "tool_permission_enabled" in d
        assert "output_check_enabled" in d
        assert "prompt_injection_patterns" in d

    def test_from_dict_missing_keys_use_defaults(self):
        restored = SecurityPolicy.from_dict({})
        assert restored.max_input_length == 4096
        assert restored.security_enabled is True


class TestSecurityPolicyCustomization:
    def test_custom_blocked_keywords(self):
        p = SecurityPolicy(blocked_keywords=["badword", "forbidden"])
        assert "badword" in p.blocked_keywords
        assert "forbidden" in p.blocked_keywords

    def test_custom_input_length(self):
        p = SecurityPolicy(max_input_length=500, min_input_length=5)
        assert p.max_input_length == 500
        assert p.min_input_length == 5

    def test_tool_permission_toggle(self):
        p = SecurityPolicy(tool_permission_enabled=False)
        assert p.tool_permission_enabled is False

    def test_output_required(self):
        p = SecurityPolicy(output_required=True)
        assert p.output_required is True
