"""Tests for PermissionChecker — tool-level allowlist/blocklist enforcement."""

import pytest

from ai_platform.security.permission import PermissionChecker
from ai_platform.security.policy import SecurityPolicy


class TestPermissionCheckerBasic:
    def test_default_policy_allows_any_tool(self):
        checker = PermissionChecker(SecurityPolicy())
        result = checker.check("any_tool_name")
        assert result.passed is True

    def test_permissive_policy_allows_all(self):
        checker = PermissionChecker(SecurityPolicy.permissive())
        result = checker.check("delete_everything")
        assert result.passed is True


class TestPermissionCheckerAllowlist:
    def test_allowed_tool_passes(self):
        policy = SecurityPolicy(allowed_tools=["search", "calc", "translate"])
        checker = PermissionChecker(policy)
        result = checker.check("search")
        assert result.passed is True

    def test_not_in_allowlist_blocked(self):
        policy = SecurityPolicy(allowed_tools=["search", "calc"])
        checker = PermissionChecker(policy)
        result = checker.check("delete")
        assert result.passed is False
        assert "tool_not_allowed" in " ".join(result.violations)
        assert "delete" in " ".join(result.violations)

    def test_empty_allowlist_allows_all(self):
        # empty allowed_tools means "allow everything (unless blocked)"
        policy = SecurityPolicy(allowed_tools=[])
        checker = PermissionChecker(policy)
        result = checker.check("any_tool")
        assert result.passed is True


class TestPermissionCheckerBlocklist:
    def test_blocked_tool_rejected(self):
        policy = SecurityPolicy(blocked_tools=["dangerous_tool", "unsafe"])
        checker = PermissionChecker(policy)
        result = checker.check("dangerous_tool")
        assert result.passed is False
        assert "tool_blocked" in " ".join(result.violations)

    def test_blocklist_takes_priority_over_allowlist(self):
        # If tool is in both lists, blocklist wins
        policy = SecurityPolicy(
            allowed_tools=["search", "dangerous_tool"],
            blocked_tools=["dangerous_tool"],
        )
        checker = PermissionChecker(policy)
        result = checker.check("dangerous_tool")
        assert result.passed is False
        assert "tool_blocked" in " ".join(result.violations)

    def test_not_blocked_tool_passes(self):
        policy = SecurityPolicy(blocked_tools=["dangerous"])
        checker = PermissionChecker(policy)
        result = checker.check("safe_tool")
        assert result.passed is True


class TestPermissionCheckerDisabled:
    def test_disabled_permission_allows_all(self):
        policy = SecurityPolicy(tool_permission_enabled=False, blocked_tools=["bad"])
        checker = PermissionChecker(policy)
        result = checker.check("bad")
        assert result.passed is True

    def test_security_disabled_allows_all(self):
        policy = SecurityPolicy(security_enabled=False, blocked_tools=["bad"])
        checker = PermissionChecker(policy)
        result = checker.check("bad")
        assert result.passed is True


class TestPermissionCheckerResultMetadata:
    def test_block_result_includes_tool_name(self):
        policy = SecurityPolicy(blocked_tools=["blocked_tool"])
        checker = PermissionChecker(policy)
        result = checker.check("blocked_tool")
        assert result.metadata.get("tool_name") == "blocked_tool"

    def test_not_in_allowlist_result_includes_allowed_list(self):
        policy = SecurityPolicy(allowed_tools=["a", "b"])
        checker = PermissionChecker(policy)
        result = checker.check("c")
        assert result.metadata.get("allowed_tools") == ["a", "b"]

    def test_pass_result_includes_tool_name(self):
        checker = PermissionChecker(SecurityPolicy())
        result = checker.check("my_tool")
        assert result.metadata.get("tool_name") == "my_tool"
