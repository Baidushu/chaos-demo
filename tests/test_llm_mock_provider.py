import pytest

from ai_platform.llm.providers.mock import MockProvider
from ai_platform.llm.types import LLMError, LLMRequest


def test_mock_provider_returns_text():
    provider = MockProvider(response="hello world")
    response = provider.generate(LLMRequest(prompt="hi", provider="mock"))
    assert response.content == "hello world"
    assert response.parsed_json is None
    assert response.provider == "mock"


def test_mock_provider_returns_json_from_text():
    provider = MockProvider(response='{"status": "ok"}')
    response = provider.generate(
        LLMRequest(prompt="hi", provider="mock", response_format="json")
    )
    assert response.content == '{"status": "ok"}'
    assert response.parsed_json == {"status": "ok"}


def test_mock_provider_raises_llm_error():
    provider = MockProvider(error=ValueError("mock failed"))
    with pytest.raises(LLMError, match="mock failed"):
        provider.generate(LLMRequest(prompt="hi", provider="mock"))
