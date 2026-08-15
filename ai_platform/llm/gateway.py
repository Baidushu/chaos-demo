from __future__ import annotations

from dataclasses import replace
from typing import Mapping

from ai_platform.llm.base import BaseLLM
from ai_platform.llm.config import GatewayConfig, load_gateway_config
from ai_platform.llm.providers.mock import MockProvider
from ai_platform.llm.providers.ollama_chat import OllamaChatProvider
from ai_platform.llm.providers.ollama_generate import OllamaGenerateProvider
from ai_platform.llm.providers.openai_compatible import OpenAICompatibleProvider
from ai_platform.llm.types import LLMError, LLMRequest, LLMResponse


class LLMGateway:
    def __init__(
        self,
        config: GatewayConfig | None = None,
        providers: Mapping[str, BaseLLM] | None = None,
    ) -> None:
        self._config = config or load_gateway_config()
        self._providers = dict(providers) if providers is not None else self._build_default_providers()

    @property
    def config(self) -> GatewayConfig:
        return self._config

    def generate(self, request: LLMRequest) -> LLMResponse:
        provider_name = request.provider or self._config.provider
        model_name = request.model or self._config.model
        timeout_sec = request.timeout_sec if request.timeout_sec is not None else self._config.timeout_sec
        normalized = replace(
            request,
            provider=provider_name,
            model=model_name,
            timeout_sec=timeout_sec,
        )

        provider = self._providers.get(provider_name)
        if provider is None:
            raise LLMError(
                provider=provider_name,
                model=model_name or "",
                error_type="provider_not_found",
                retryable=False,
                message=f"Unknown LLM provider: {provider_name}",
            )

        try:
            return provider.generate(normalized)
        except LLMError:
            raise
        except Exception as exc:  # pragma: no cover - defensive path
            raise LLMError(
                provider=provider_name,
                model=model_name or "",
                error_type=type(exc).__name__,
                retryable=False,
                message=str(exc),
                raw=exc,
            ) from exc

    def _build_default_providers(self) -> dict[str, BaseLLM]:
        return {
            "mock": MockProvider(),
            "ollama_chat": OllamaChatProvider(
                endpoint=self._config.endpoint if self._config.provider == "ollama_chat" else None,
                model=self._config.model,
                timeout_sec=self._config.timeout_sec,
            ),
            "ollama_generate": OllamaGenerateProvider(
                endpoint=self._config.endpoint if self._config.provider == "ollama_generate" else None,
                model=self._config.model,
                timeout_sec=self._config.timeout_sec,
            ),
            "openai_compatible": OpenAICompatibleProvider(
                endpoint=self._config.endpoint if self._config.provider == "openai_compatible" else None,
                api_key=self._config.api_key,
                model=self._config.model,
                timeout_sec=self._config.timeout_sec,
            ),
        }
