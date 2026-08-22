"""policy-as-code 测试：策略文件加载、schema 严格校验与角色裁决语义。

守护三条线：
1. 仓库内置 config/security_policy.yaml 始终合法（防配置漂移进 CI）；
2. 加载器对未知键/坏结构/未知角色 fail-fast；
3. PermissionChecker 的角色语义：fail-closed、全局∩角色、default_role。
"""

from __future__ import annotations

from pathlib import Path

import pytest

from ai_platform.security.permission import PermissionChecker
from ai_platform.security.policy import SecurityPolicy, ToolRole
from ai_platform.security.policy_file import (
    DEFAULT_POLICY_PATH,
    PolicyFileError,
    load_policy_file,
)

REPO_POLICY = Path(__file__).resolve().parents[2] / "config" / "security_policy.yaml"


# ---------------------------------------------------------------------------
# 1. 内置策略文件合法性（CI 漂移守护）
# ---------------------------------------------------------------------------
def test_repo_policy_file_is_valid():
    policy = load_policy_file(REPO_POLICY)
    assert policy.policy_version == "1"
    assert {"analyst", "operator", "admin"} <= set(policy.roles)
    # 行为中立性：全局 allowed/blocked 为空，未传角色的调用不受影响
    assert policy.allowed_tools == []
    assert policy.blocked_tools == []


def test_default_policy_path_points_to_repo_file():
    assert DEFAULT_POLICY_PATH == REPO_POLICY


def test_repo_policy_role_semantics():
    policy = load_policy_file(REPO_POLICY)
    checker = PermissionChecker(policy)

    # analyst 只读：查询放行、下单/取消拒绝
    assert checker.check("query_order", role="analyst").passed
    assert not checker.check("place_order", role="analyst").passed
    assert not checker.check("cancel_order", role="analyst").passed

    # operator：可下单，不可取消
    assert checker.check("query_order", role="operator").passed
    assert checker.check("place_order", role="operator").passed
    assert not checker.check("cancel_order", role="operator").passed

    # admin：不限制
    assert checker.check("cancel_order", role="admin").passed
    assert checker.check("anything_else", role="admin").passed

    # 未传角色：全局为空 = 全部放行（行为中立）
    assert checker.check("place_order").passed


# ---------------------------------------------------------------------------
# 2. 加载与校验
# ---------------------------------------------------------------------------
def _write_policy(tmp_path: Path, content: str) -> Path:
    path = tmp_path / "policy.yaml"
    path.write_text(content, encoding="utf-8")
    return path


MINIMAL_VALID = """
version: 1
roles:
  reader:
    allowed_tools: [query_order]
"""


def test_load_minimal_policy(tmp_path):
    policy = load_policy_file(_write_policy(tmp_path, MINIMAL_VALID))
    assert policy.policy_version == "1"
    assert set(policy.roles) == {"reader"}
    assert policy.roles["reader"].allowed_tools == ["query_order"]


def test_missing_file_raises(tmp_path):
    with pytest.raises(PolicyFileError, match="not found"):
        load_policy_file(tmp_path / "nope.yaml")


def test_unknown_top_level_key_rejected(tmp_path):
    path = _write_policy(tmp_path, MINIMAL_VALID + "\nunknown_section: {}\n")
    with pytest.raises(PolicyFileError, match="unknown top-level keys"):
        load_policy_file(path)


def test_unknown_security_key_rejected(tmp_path):
    path = _write_policy(
        tmp_path,
        MINIMAL_VALID + "\nsecurity:\n  allowd_tools: [x]\n",  # 拼写错误
    )
    with pytest.raises(PolicyFileError, match="unknown keys in security section"):
        load_policy_file(path)


def test_unknown_role_key_rejected(tmp_path):
    path = _write_policy(
        tmp_path,
        "version: 1\nroles:\n  reader:\n    alowed_tools: [x]\n",
    )
    with pytest.raises(PolicyFileError, match="unknown keys in role"):
        load_policy_file(path)


@pytest.mark.parametrize("bad_version", ["2", "abc", None])
def test_unsupported_version_rejected(tmp_path, bad_version):
    version_line = f"version: {bad_version if bad_version is not None else ''}"
    path = _write_policy(tmp_path, version_line + "\nroles: {}\n")
    with pytest.raises(PolicyFileError, match="unsupported policy version"):
        load_policy_file(path)


def test_bad_role_structure_rejected(tmp_path):
    path = _write_policy(tmp_path, "version: 1\nroles:\n  reader: [not, a, dict]\n")
    with pytest.raises(PolicyFileError, match="must be a mapping"):
        load_policy_file(path)


def test_non_list_tools_rejected(tmp_path):
    path = _write_policy(
        tmp_path,
        "version: 1\nroles:\n  reader:\n    allowed_tools: query_order\n",
    )
    with pytest.raises(PolicyFileError, match="must be lists"):
        load_policy_file(path)


def test_unknown_default_role_rejected(tmp_path):
    path = _write_policy(tmp_path, MINIMAL_VALID + "\ndefault_role: nobody\n")
    with pytest.raises(PolicyFileError, match="default_role"):
        load_policy_file(path)


def test_invalid_yaml_rejected(tmp_path):
    path = _write_policy(tmp_path, "version: [unclosed\n")
    with pytest.raises(PolicyFileError, match="invalid YAML"):
        load_policy_file(path)


# ---------------------------------------------------------------------------
# 3. 角色裁决语义
# ---------------------------------------------------------------------------
def test_unknown_role_is_fail_closed():
    policy = SecurityPolicy()
    checker = PermissionChecker(policy)
    result = checker.check("query_order", role="ghost")
    assert not result.passed
    assert any("unknown_role" in v for v in result.violations)


def test_global_blocklist_overrides_role_allowlist():
    policy = SecurityPolicy(
        blocked_tools=["danger_tool"],
        roles={"op": ToolRole(allowed_tools=["danger_tool", "safe_tool"])},
    )
    checker = PermissionChecker(policy)
    assert not checker.check("danger_tool", role="op").passed  # 全局禁令最高
    assert checker.check("safe_tool", role="op").passed


def test_role_and_global_allowlists_intersect():
    policy = SecurityPolicy(
        allowed_tools=["tool_a", "tool_b"],
        roles={"r": ToolRole(allowed_tools=["tool_b", "tool_c"])},
    )
    checker = PermissionChecker(policy)
    assert checker.check("tool_b", role="r").passed  # 交集内
    assert not checker.check("tool_a", role="r").passed  # 角色不允许
    assert not checker.check("tool_c", role="r").passed  # 全局不允许


def test_default_role_applies_when_role_omitted():
    policy = SecurityPolicy(
        roles={
            "reader": ToolRole(allowed_tools=["query_order"]),
            "writer": ToolRole(allowed_tools=["place_order"]),
        },
        default_role="reader",
    )
    checker = PermissionChecker(policy)
    assert checker.check("query_order").passed
    assert not checker.check("place_order").passed
    # default_role 只约束未传角色的调用，显式角色仍按自身裁决
    assert checker.check("place_order", role="writer").passed


def test_role_blocked_tools_merge_with_global():
    policy = SecurityPolicy(
        blocked_tools=["global_bad"],
        roles={"r": ToolRole(blocked_tools=["role_bad"])},
    )
    checker = PermissionChecker(policy)
    assert not checker.check("global_bad", role="r").passed
    assert not checker.check("role_bad", role="r").passed
    assert checker.check("fine_tool", role="r").passed


# ---------------------------------------------------------------------------
# 4. 序列化往返
# ---------------------------------------------------------------------------
def test_policy_dict_roundtrip_preserves_roles():
    policy = load_policy_file(REPO_POLICY)
    dumped = policy.to_dict()
    restored = SecurityPolicy.from_dict(dumped)
    assert restored.roles.keys() == policy.roles.keys()
    for name, role in policy.roles.items():
        assert restored.roles[name].allowed_tools == role.allowed_tools
        assert restored.roles[name].blocked_tools == role.blocked_tools
    assert restored.default_role == policy.default_role
    assert restored.policy_version == policy.policy_version
