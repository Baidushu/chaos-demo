"""SecurityPolicy — unified security rule configuration.

Defines all configurable security rules in one place.
Supports to_dict/from_dict for file-based configuration.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass(slots=True)
class ToolRole:
    """角色级工具权限——policy-as-code 的角色条目。

    语义与全局字段一致：allowed_tools 为空 = 不限制（仍受 blocked
    与全局约束）；非空 = 仅允许其中列出的工具。
    """

    description: str = ""
    allowed_tools: list[str] = field(default_factory=list)
    blocked_tools: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "description": self.description,
            "allowed_tools": list(self.allowed_tools),
            "blocked_tools": list(self.blocked_tools),
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "ToolRole":
        return cls(
            description=str(data.get("description", "")),
            allowed_tools=[str(t) for t in data.get("allowed_tools", [])],
            blocked_tools=[str(t) for t in data.get("blocked_tools", [])],
        )


@dataclass(slots=True)
class SecurityPolicy:
    # -- Input validation --
    max_input_length: int = 4096
    min_input_length: int = 1
    blocked_keywords: list[str] = field(default_factory=list)
    blocked_patterns: list[str] = field(default_factory=list)

    # -- Prompt injection guard --
    prompt_injection_enabled: bool = True
    prompt_injection_patterns: list[str] = field(
        default_factory=lambda: [
            "ignore previous instruction",
            "ignore all previous instructions",
            "ignore the above",
            "disregard previous",
            "forget previous instructions",
            "system prompt",
            "system message",
            "developer message",
            "you are now",
            "you are a new",
            "new personality",
            "pretend you are",
            "act as if",
            "jailbreak",
            "dan mode",
            "developer mode",
            "override",
            "bypass",
            "ignore your programming",
            "ignore your training",
            "ignore all rules",
            "do not follow your",
        ]
    )

    # -- Tool permission --
    tool_permission_enabled: bool = True
    allowed_tools: list[str] = field(default_factory=list)
    blocked_tools: list[str] = field(default_factory=list)

    # -- Role-based tool permission（policy-as-code 扩展）--
    # roles: 角色名 -> ToolRole；default_role 非空时，未显式传角色的
    # check() 调用按该角色裁决。两者默认为空 = 行为与旧版完全一致。
    roles: dict[str, ToolRole] = field(default_factory=dict)
    default_role: str = ""
    policy_version: str = ""

    # -- Output checking --
    output_check_enabled: bool = True
    max_output_length: int = 8192
    sensitive_keywords: list[str] = field(default_factory=list)
    output_required: bool = False

    # -- Enforcement --
    security_enabled: bool = True
    block_on_input_violation: bool = True
    block_on_injection: bool = True
    block_on_permission_denied: bool = True
    block_on_output_violation: bool = True

    def to_dict(self) -> dict[str, Any]:
        return {
            "max_input_length": self.max_input_length,
            "min_input_length": self.min_input_length,
            "blocked_keywords": list(self.blocked_keywords),
            "blocked_patterns": list(self.blocked_patterns),
            "prompt_injection_enabled": self.prompt_injection_enabled,
            "prompt_injection_patterns": list(self.prompt_injection_patterns),
            "tool_permission_enabled": self.tool_permission_enabled,
            "allowed_tools": list(self.allowed_tools),
            "blocked_tools": list(self.blocked_tools),
            "roles": {name: role.to_dict() for name, role in self.roles.items()},
            "default_role": self.default_role,
            "policy_version": self.policy_version,
            "output_check_enabled": self.output_check_enabled,
            "max_output_length": self.max_output_length,
            "sensitive_keywords": list(self.sensitive_keywords),
            "output_required": self.output_required,
            "security_enabled": self.security_enabled,
            "block_on_input_violation": self.block_on_input_violation,
            "block_on_injection": self.block_on_injection,
            "block_on_permission_denied": self.block_on_permission_denied,
            "block_on_output_violation": self.block_on_output_violation,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "SecurityPolicy":
        _default = cls.__dataclass_fields__["prompt_injection_patterns"].default_factory()
        return cls(
            max_input_length=int(data.get("max_input_length", 4096)),
            min_input_length=int(data.get("min_input_length", 1)),
            blocked_keywords=list(data.get("blocked_keywords", [])),
            blocked_patterns=list(data.get("blocked_patterns", [])),
            prompt_injection_enabled=bool(data.get("prompt_injection_enabled", True)),
            prompt_injection_patterns=list(
                data.get("prompt_injection_patterns", _default)
            ),
            tool_permission_enabled=bool(data.get("tool_permission_enabled", True)),
            allowed_tools=list(data.get("allowed_tools", [])),
            blocked_tools=list(data.get("blocked_tools", [])),
            roles={
                str(name): ToolRole.from_dict(role_data)
                for name, role_data in dict(data.get("roles", {})).items()
                if isinstance(role_data, dict)
            },
            default_role=str(data.get("default_role", "")),
            policy_version=str(data.get("policy_version", "")),
            output_check_enabled=bool(data.get("output_check_enabled", True)),
            max_output_length=int(data.get("max_output_length", 8192)),
            sensitive_keywords=list(data.get("sensitive_keywords", [])),
            output_required=bool(data.get("output_required", False)),
            security_enabled=bool(data.get("security_enabled", True)),
            block_on_input_violation=bool(data.get("block_on_input_violation", True)),
            block_on_injection=bool(data.get("block_on_injection", True)),
            block_on_permission_denied=bool(data.get("block_on_permission_denied", True)),
            block_on_output_violation=bool(data.get("block_on_output_violation", True)),
        )

    @classmethod
    def default(cls) -> "SecurityPolicy":
        return cls()

    @classmethod
    def permissive(cls) -> "SecurityPolicy":
        """All security disabled — useful for testing."""
        return cls(
            security_enabled=False,
            prompt_injection_enabled=False,
            tool_permission_enabled=False,
            output_check_enabled=False,
            block_on_input_violation=False,
            block_on_injection=False,
            block_on_permission_denied=False,
            block_on_output_violation=False,
        )
