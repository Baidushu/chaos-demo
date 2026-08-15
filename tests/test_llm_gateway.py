import pytest

from ai_platform.llm.base import BaseLLM
from ai_platform.llm.config import GatewayConfig, load_gateway_config, load_judge_gateway_config
from ai_platform.llm.gateway import LLMGateway
from ai_platform.llm.providers.mock import MockProvider
from ai_platform.llm.types import LLMError, LLMRequest, LLMResponse


class BrokenProvider(BaseLLM):
    def generate(self, request: LLMRequest) -> LLMResponse:
        raise RuntimeError("provider crashed")


def test_gateway_uses_configured_provider():
    gateway = LLMGateway(
        config=GatewayConfig(provider="mock", model="phase11-model", endpoint="mock://local"),
        providers={"mock": MockProvider(response="ok")},
    )
    response = gateway.generate(LLMRequest(prompt="ping"))
    assert response.content == "ok"
    assert response.provider == "mock"
    assert response.model == "phase11-model"


def test_gateway_request_provider_overrides_default():
    gateway = LLMGateway(
        config=GatewayConfig(provider="mock", model="default-model", endpoint="mock://local"),
        providers={
            "mock": MockProvider(response="default", model_name="default-model"),
            "ollama_generate": MockProvider(
                response='{"tool": "ask_user"}',
                provider_name="ollama_generate",
                model_name="judge-model",
            ),
        },
    )
    response = gateway.generate(
        LLMRequest(prompt="judge", provider="ollama_generate", response_format="json")
    )
    assert response.provider == "ollama_generate"
    assert response.model == "default-model"
    assert response.parsed_json == {"tool": "ask_user"}


def test_gateway_wraps_unknown_provider():
    gateway = LLMGateway(
        config=GatewayConfig(provider="mock", model="demo-model", endpoint="mock://local"),
        providers={},
    )
    with pytest.raises(LLMError, match="Unknown LLM provider"):
        gateway.generate(LLMRequest(prompt="x", provider="missing"))


def test_gateway_wraps_unexpected_provider_error():
    gateway = LLMGateway(
        config=GatewayConfig(provider="mock", model="demo-model", endpoint="mock://local"),
        providers={"mock": BrokenProvider()},
    )
    with pytest.raises(LLMError, match="provider crashed") as exc_info:
        gateway.generate(LLMRequest(prompt="x"))
    assert exc_info.value.error_type == "RuntimeError"


def test_load_gateway_config_legacy_openai_env(monkeypatch):
    monkeypatch.setenv("LLM_BACKEND", "openai")
    monkeypatch.setenv("LLM_MODEL", "qwen-plus")
    monkeypatch.setenv("LLM_BASE_URL", "https://example.test/v1")
    monkeypatch.setenv("LLM_API_KEY", "sk-test")
    monkeypatch.setenv("LLM_TIMEOUT_SEC", "45")
    config = load_gateway_config()
    assert config.provider == "openai_compatible"
    assert config.model == "qwen-plus"
    assert config.endpoint == "https://example.test/v1"
    assert config.api_key == "sk-test"
    assert config.timeout_sec == 45.0


def test_load_judge_gateway_config_uses_eval_yaml():
    config = load_judge_gateway_config()
    assert config.provider == "ollama_chat"
    assert config.model == "qwen2.5:7b"
    assert config.endpoint == "http://localhost:11434/api/generate"
