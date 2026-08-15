"""PermissionChecker — controls which tools an agent is allowed to call.

Supports:
  - allowlist: only these tools are allowed
  - blocklist: these tools are explicitly blocked
  - allow-all: empty allowlist means all tools are allowed (unless blocked)
"""

from __future__ import annotations

from ai_platform.security.policy import SecurityPolicy
from ai_platform.security.security_result import SecurityResult


class PermissionChecker:
    def __init__(self, policy: SecurityPolicy) -> None:
        self._policy = policy

    def check(self, tool_name: str) -> SecurityResult:
        if not self._policy.security_enabled or not self._policy.tool_permission_enabled:
            return SecurityResult.pass_(check_name="permission_checker")

        violations: list[str] = []

        # Blocklist check (higher priority)
        if tool_name in self._policy.blocked_tools:
            violations.append(f"tool_blocked: {tool_name}")
            return SecurityResult.block(
                risk_level="high",
                violations=violations,
                check_name="permission_checker",
                metadata={"tool_name": tool_name, "reason": "blocklisted"},
            )

        # Allowlist check
        allowed = self._policy.allowed_tools
        if allowed and tool_name not in allowed:
            violations.append(f"tool_not_allowed: {tool_name}")
            return SecurityResult.block(
                risk_level="high",
                violations=violations,
                check_name="permission_checker",
                metadata={
                    "tool_name": tool_name,
                    "reason": "not_in_allowlist",
                    "allowed_tools": list(allowed),
                },
            )

        return SecurityResult.pass_(
            check_name="permission_checker",
            metadata={"tool_name": tool_name},
        )
