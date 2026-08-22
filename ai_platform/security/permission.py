"""PermissionChecker — controls which tools an agent is allowed to call.

Supports:
  - allowlist: only these tools are allowed
  - blocklist: these tools are explicitly blocked
  - allow-all: empty allowlist means all tools are allowed (unless blocked)
  - role-based checks (policy-as-code): each call may carry a role name;
    the effective permission = 全局约束 ∩ 角色约束, unknown roles are
    rejected fail-closed（宁拒勿漏）.
"""

from __future__ import annotations

from ai_platform.security.policy import SecurityPolicy
from ai_platform.security.security_result import SecurityResult


class PermissionChecker:
    def __init__(self, policy: SecurityPolicy) -> None:
        self._policy = policy

    def check(self, tool_name: str, role: str | None = None) -> SecurityResult:
        if not self._policy.security_enabled or not self._policy.tool_permission_enabled:
            return SecurityResult.pass_(check_name="permission_checker")

        # 角色解析：显式传入优先，未传时回落 default_role（若配置）。
        effective_role = role if role is not None else (self._policy.default_role or None)

        blocked: set[str] = set(self._policy.blocked_tools)
        global_allowed = list(self._policy.allowed_tools)

        if effective_role is not None:
            tool_role = self._policy.roles.get(effective_role)
            if tool_role is None:
                # fail-closed：未知角色一律拒绝——权限系统宁拒勿漏。
                return SecurityResult.block(
                    risk_level="high",
                    violations=[f"unknown_role: {effective_role}"],
                    check_name="permission_checker",
                    metadata={
                        "tool_name": tool_name,
                        "role": effective_role,
                        "reason": "fail_closed_unknown_role",
                    },
                )
            blocked |= set(tool_role.blocked_tools)
            if tool_role.allowed_tools:
                if global_allowed:
                    # 全局与角色允许集取交集
                    role_set = set(tool_role.allowed_tools)
                    global_allowed = [t for t in global_allowed if t in role_set]
                else:
                    global_allowed = list(tool_role.allowed_tools)

        # Blocklist check (higher priority)
        if tool_name in blocked:
            return SecurityResult.block(
                risk_level="high",
                violations=[f"tool_blocked: {tool_name}"],
                check_name="permission_checker",
                metadata={"tool_name": tool_name, "reason": "blocklisted"},
            )

        # Allowlist check
        allowed = global_allowed
        if allowed and tool_name not in allowed:
            return SecurityResult.block(
                risk_level="high",
                violations=[f"tool_not_allowed: {tool_name}"],
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
