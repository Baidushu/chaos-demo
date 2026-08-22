"""Security policy 文件加载器（policy-as-code 入口）。

把 ``config/security_policy.yaml`` 加载为 SecurityPolicy，并对 schema
做严格校验：未知键、结构错误、未知角色引用一律在加载期报错
（fail-fast），绝不静默忽略——策略文件进 git 评审，配置漂移在
CI 的 ``tests/core_platform/test_sec_policy_file.py`` 里被拦截。

文件结构::

    version: 1                      # 必填，当前仅支持 1
    name: chaos-demo-ai-platform    # 可选，策略名
    default_role: ""                # 可选，未传角色时的回落角色
    roles:                          # 可选，角色 -> 工具权限
      analyst:
        description: 只读分析
        allowed_tools: [query_order]
        blocked_tools: []
    security:                       # 可选，SecurityPolicy 其余字段
      blocked_keywords: [...]
"""

from __future__ import annotations

from dataclasses import replace
from pathlib import Path
from typing import Any

import yaml

from ai_platform.security.policy import SecurityPolicy, ToolRole

SUPPORTED_VERSIONS = (1,)
DEFAULT_POLICY_PATH = Path(__file__).resolve().parents[2] / "config" / "security_policy.yaml"

_ALLOWED_TOP_LEVEL_KEYS = {"version", "name", "roles", "default_role", "security"}
_ALLOWED_ROLE_KEYS = {"description", "allowed_tools", "blocked_tools"}


class PolicyFileError(ValueError):
    """策略文件不合法——加载期 fail-fast。"""


def load_policy_file(path: Path | str) -> SecurityPolicy:
    """加载并严格校验策略文件，返回 SecurityPolicy。

    Raises:
        PolicyFileError: 文件不存在 / YAML 不合法 / schema 不符。
    """
    file_path = Path(path)
    if not file_path.is_file():
        raise PolicyFileError(f"security policy file not found: {file_path}")

    try:
        raw = yaml.safe_load(file_path.read_text(encoding="utf-8"))
    except yaml.YAMLError as exc:
        raise PolicyFileError(f"invalid YAML in policy file {file_path}: {exc}") from exc

    if not isinstance(raw, dict):
        raise PolicyFileError(f"policy file {file_path} must be a YAML mapping")

    unknown_keys = set(raw) - _ALLOWED_TOP_LEVEL_KEYS
    if unknown_keys:
        raise PolicyFileError(
            f"unknown top-level keys in policy file {file_path}: {sorted(unknown_keys)}"
        )

    version = raw.get("version")
    if version not in SUPPORTED_VERSIONS:
        raise PolicyFileError(
            f"unsupported policy version {version!r} in {file_path}; "
            f"supported: {list(SUPPORTED_VERSIONS)}"
        )

    roles = _parse_roles(raw.get("roles", {}), file_path)
    default_role = str(raw.get("default_role", "") or "")
    if default_role and default_role not in roles:
        raise PolicyFileError(
            f"default_role {default_role!r} is not defined in roles of {file_path}"
        )

    security_section = raw.get("security", {})
    if not isinstance(security_section, dict):
        raise PolicyFileError(f"security section of {file_path} must be a mapping")
    _validate_security_keys(security_section, file_path)

    policy = SecurityPolicy.from_dict(security_section)
    return replace(
        policy,
        roles=roles,
        default_role=default_role,
        policy_version=str(version),
    )


def resolve_policy_path() -> Path:
    """解析生效的策略文件路径：环境变量覆盖 > 仓库默认路径。"""
    import os

    override = os.environ.get("PLATFORM_SECURITY_POLICY", "").strip()
    return Path(override) if override else DEFAULT_POLICY_PATH


def _parse_roles(raw_roles: Any, file_path: Path) -> dict[str, ToolRole]:
    if not isinstance(raw_roles, dict):
        raise PolicyFileError(f"roles section of {file_path} must be a mapping")

    roles: dict[str, ToolRole] = {}
    for name, entry in raw_roles.items():
        role_name = str(name)
        if not role_name:
            raise PolicyFileError(f"empty role name in {file_path}")
        if not isinstance(entry, dict):
            raise PolicyFileError(f"role {role_name!r} in {file_path} must be a mapping")
        unknown = set(entry) - _ALLOWED_ROLE_KEYS
        if unknown:
            raise PolicyFileError(
                f"unknown keys in role {role_name!r} of {file_path}: {sorted(unknown)}"
            )
        allowed = entry.get("allowed_tools", [])
        blocked = entry.get("blocked_tools", [])
        if not isinstance(allowed, list) or not isinstance(blocked, list):
            raise PolicyFileError(
                f"allowed_tools/blocked_tools of role {role_name!r} in {file_path} must be lists"
            )
        if any(not isinstance(t, str) or not t for t in allowed + blocked):
            raise PolicyFileError(
                f"role {role_name!r} of {file_path} contains non-string tool names"
            )
        roles[role_name] = ToolRole(
            description=str(entry.get("description", "")),
            allowed_tools=list(allowed),
            blocked_tools=list(blocked),
        )
    return roles


def _validate_security_keys(section: dict[str, Any], file_path: Path) -> None:
    """security 小节只接受 SecurityPolicy 已知字段（防拼写漂移）。"""
    known_keys = set(SecurityPolicy().to_dict())
    unknown = set(section) - known_keys
    if unknown:
        raise PolicyFileError(
            f"unknown keys in security section of {file_path}: {sorted(unknown)}"
        )
