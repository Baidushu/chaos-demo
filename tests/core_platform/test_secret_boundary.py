"""密钥边界测试（secret boundary）——守护「密钥不出平台」这条不变量。

对标企业级安全实践中「密钥与授权状态只由受信层持有，不暴露给
渲染层/调用方」的原则，本项目对应的不变量是：

1. GatewayConfig 的 repr / str 不包含 api_key（密钥常被无意打进
   日志的第一泄漏点）；
2. 从环境变量加载的真实密钥值不出现在 repr 中；
3. 任何离开平台的错误消息（HTTP 错误响应体）必须经过 redact()
   清洗——即使上游异常消息失误嵌入了密钥；
4. redact() 对已知密钥值与常见密钥形态（sk-xxx / Bearer xxx /
   api_key=xxx）都能兜底。

测试使用显式的哨兵密钥（sk-BOUNDARY-TEST-...），不触碰真实 key。
"""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

import ai_platform_api
from ai_platform.llm.config import GatewayConfig, load_gateway_config
from ai_platform.security.redaction import REDACTED, active_secrets, mask_secret, redact

SECRET = "sk-BOUNDARY-TEST-0123456789abcdef"


# ---------------------------------------------------------------------------
# 1. GatewayConfig repr 边界
# ---------------------------------------------------------------------------
def test_gateway_config_repr_masks_api_key():
    """repr(config) 是日志泄漏的第一现场，密钥必须被排除。"""
    cfg = GatewayConfig(provider="openai_compatible", api_key=SECRET)
    assert SECRET not in repr(cfg)
    assert SECRET not in str(cfg)
    # repr 里不应出现任何密钥位（字段被整体排除而非置空）
    assert "api_key" not in repr(cfg)


def test_load_gateway_config_env_secret_not_in_repr(monkeypatch):
    """从环境变量加载真实密钥后，repr 仍不泄漏。"""
    monkeypatch.setenv("LLM_GATEWAY_API_KEY", SECRET)
    cfg = load_gateway_config(provider="openai_compatible")
    assert cfg.api_key == SECRET  # 密钥本身仍可用于请求
    assert SECRET not in repr(cfg)
    assert SECRET not in str(cfg)


# ---------------------------------------------------------------------------
# 2. redact() 工具行为
# ---------------------------------------------------------------------------
def test_redact_known_secret_value():
    assert redact(f"provider failed with {SECRET}", secrets=[SECRET]) == (
        f"provider failed with {REDACTED}"
    )


def test_redact_collects_secrets_from_env(monkeypatch):
    monkeypatch.setenv("LLM_GATEWAY_API_KEY", SECRET)
    assert SECRET in active_secrets()
    assert redact(f"boom: {SECRET}") == f"boom: {REDACTED}"


def test_redact_masks_common_secret_shapes():
    # sk- 形态
    assert "sk-abcdef1234567890" not in redact("key is sk-abcdef1234567890 ok")
    # Bearer 形态
    assert "Bearer abcdef123456" not in redact("Authorization: Bearer abcdef123456")
    # 键值对形态
    assert "supersecret" not in redact("config api_key=supersecret failed")
    assert "s3cret" not in redact("header token: s3cret rejected")


def test_redact_keeps_normal_error_text():
    """正常错误消息不应被误伤。"""
    msg = "OpenAI-compatible API error 401: invalid api key format"
    assert redact(msg, secrets=[]) == msg


def test_mask_secret_shape():
    assert mask_secret("sk-abcdefghijklmnop") == "sk-a****"
    assert mask_secret("short") == REDACTED


# ---------------------------------------------------------------------------
# 3. HTTP 边界：错误响应绝不回显密钥
# ---------------------------------------------------------------------------
class _LeakyRuntime:
    """模拟一个把密钥拼进异常消息的失误组件（最坏情况）。"""

    def run(self, *_args, **_kwargs):
        raise RuntimeError(f"provider call failed, used key {SECRET}, please check")


def test_api_error_response_never_echoes_secret(monkeypatch):
    monkeypatch.setenv("LLM_GATEWAY_API_KEY", SECRET)
    monkeypatch.setattr(ai_platform_api, "get_service", lambda: _LeakyRuntime())

    client = TestClient(ai_platform_api.app, raise_server_exceptions=False)
    resp = client.post("/api/v1/agent/run", json={"request": "hello", "mode": "rule"})

    assert resp.status_code == 500
    body = resp.json()
    body_text = str(body)
    assert SECRET not in body_text, f"密钥泄漏进 HTTP 响应: {body_text[:200]}"
    assert REDACTED in body["error"], "错误消息应包含 REDACTED 标记以证明脱敏路径生效"


@pytest.mark.parametrize(
    "leak_message",
    [
        f"connection reset while sending Authorization: Bearer {SECRET}",
        f"upstream 401, payload api_key={SECRET}",
        f"repr={GatewayConfig(provider='openai_compatible', api_key=SECRET)!r}",
    ],
)
def test_api_error_redacts_various_leak_shapes(monkeypatch, leak_message):
    """多种泄漏形态（header/键值对/repr）都要在响应前被清洗。"""
    monkeypatch.setenv("LLM_GATEWAY_API_KEY", SECRET)

    class _Leaky:
        def run(self, *_a, **_k):
            raise RuntimeError(leak_message)

    monkeypatch.setattr(ai_platform_api, "get_service", lambda: _Leaky())
    client = TestClient(ai_platform_api.app, raise_server_exceptions=False)
    resp = client.post("/api/v1/agent/run", json={"request": "hello", "mode": "rule"})

    assert resp.status_code == 500
    assert SECRET not in resp.text
