"""代理头信任策略的单测：`X-Forwarded-For` 默认不采信，开启后按可信跳数从右往左取。

覆盖两类要求：
1. **默认安全**：不开启 `TRUST_PROXY_HEADERS` 时，`X-Forwarded-For` 一律被忽略
   （该头调用方可任意伪造，采信它等于让限流维度可被绕过）；
2. **开启后仍防伪造**：只取右起第 `XFF_TRUSTED_HOPS` 跳，最左侧可伪造的值被丢弃，
   跳数不足时退回 `remote_addr`（不猜、不采信）。
"""

from __future__ import annotations

import sys
from pathlib import Path
from types import SimpleNamespace

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from chaos_service import rate_limiter  # noqa: E402


def _request(remote_addr: str | None = "10.0.0.9", forwarded: str | None = None):
    headers = {} if forwarded is None else {"X-Forwarded-For": forwarded}
    return SimpleNamespace(remote_addr=remote_addr, headers=headers)


@pytest.fixture(autouse=True)
def _clean_proxy_env(monkeypatch):
    monkeypatch.delenv("TRUST_PROXY_HEADERS", raising=False)
    monkeypatch.delenv("XFF_TRUSTED_HOPS", raising=False)
    return monkeypatch


# ── 默认不信任 ───────────────────────────────────────────────────────


def test_forwarded_header_ignored_by_default():
    assert rate_limiter.client_ip_from_request(_request(forwarded="1.2.3.4")) == "10.0.0.9"


def test_spoofed_header_cannot_change_subject_by_default():
    """核心回归：默认配置下伪造 XFF 不能改变限流维度。"""
    subject = rate_limiter.resolve_subject_id(
        _request(forwarded="9.9.9.9"), "client_ip"
    )
    assert subject == "10.0.0.9"


def test_trust_proxy_headers_flag_parsing(_clean_proxy_env):
    for value in ("1", "true", "TRUE", "yes", "on"):
        _clean_proxy_env.setenv("TRUST_PROXY_HEADERS", value)
        assert rate_limiter.trust_proxy_headers() is True
    for value in ("", "0", "false", "no", "off"):
        _clean_proxy_env.setenv("TRUST_PROXY_HEADERS", value)
        assert rate_limiter.trust_proxy_headers() is False


# ── 开启信任后：按可信跳数取，忽略可伪造的最左值 ─────────────────────


def test_single_trusted_proxy_takes_rightmost_hop(_clean_proxy_env):
    _clean_proxy_env.setenv("TRUST_PROXY_HEADERS", "1")
    _clean_proxy_env.setenv("XFF_TRUSTED_HOPS", "1")
    assert rate_limiter.client_ip_from_request(_request(forwarded="1.2.3.4")) == "1.2.3.4"


def test_spoofed_leftmost_value_is_discarded(_clean_proxy_env):
    """攻击者自带 `XFF: 9.9.9.9` 直连代理时，真实来源是代理追加的右起第一跳。"""
    _clean_proxy_env.setenv("TRUST_PROXY_HEADERS", "1")
    _clean_proxy_env.setenv("XFF_TRUSTED_HOPS", "1")
    request = _request(forwarded="9.9.9.9, 1.2.3.4")
    assert rate_limiter.client_ip_from_request(request) == "1.2.3.4"


def test_two_trusted_hops(_clean_proxy_env):
    _clean_proxy_env.setenv("TRUST_PROXY_HEADERS", "1")
    _clean_proxy_env.setenv("XFF_TRUSTED_HOPS", "2")
    request = _request(forwarded="1.2.3.4, 203.0.113.7")
    assert rate_limiter.client_ip_from_request(request) == "1.2.3.4"


def test_insufficient_hops_falls_back_to_remote_addr(_clean_proxy_env):
    """声明有 2 层可信代理，却只收到 1 跳 → 不猜，退回 remote_addr。"""
    _clean_proxy_env.setenv("TRUST_PROXY_HEADERS", "1")
    _clean_proxy_env.setenv("XFF_TRUSTED_HOPS", "2")
    assert rate_limiter.client_ip_from_request(_request(forwarded="9.9.9.9")) == "10.0.0.9"


@pytest.mark.parametrize("raw_hops", ["0", "-3", "abc", "", " "])
def test_invalid_hop_count_defaults_to_one(_clean_proxy_env, raw_hops):
    _clean_proxy_env.setenv("TRUST_PROXY_HEADERS", "1")
    _clean_proxy_env.setenv("XFF_TRUSTED_HOPS", raw_hops)
    assert rate_limiter.trusted_hop_count() == 1
    assert rate_limiter.client_ip_from_request(_request(forwarded="1.2.3.4")) == "1.2.3.4"


def test_blank_forwarded_value_falls_back(_clean_proxy_env):
    _clean_proxy_env.setenv("TRUST_PROXY_HEADERS", "1")
    assert rate_limiter.client_ip_from_request(_request(forwarded=" , , ")) == "10.0.0.9"


# ── 其它维度与边界 ───────────────────────────────────────────────────


def test_non_client_ip_dimension_never_reads_forwarded_header(_clean_proxy_env):
    """未实现身份提取的维度退回 remote_addr，不得静默采信可伪造的头。"""
    _clean_proxy_env.setenv("TRUST_PROXY_HEADERS", "1")
    subject = rate_limiter.resolve_subject_id(_request(forwarded="9.9.9.9"), "user_id")
    assert subject == "10.0.0.9"


def test_missing_remote_addr_returns_unknown():
    assert rate_limiter.client_ip_from_request(_request(remote_addr=None)) == "unknown"


def test_trusted_hop_value_returned_verbatim(_clean_proxy_env):
    """取值不做任何改写（IPv6/端口形态原样返回，避免静默归一造成维度漂移）。"""
    _clean_proxy_env.setenv("TRUST_PROXY_HEADERS", "1")
    request = _request(forwarded=" 2001:db8::1 , 1.2.3.4 ")
    assert rate_limiter.client_ip_from_request(request) == "1.2.3.4"
