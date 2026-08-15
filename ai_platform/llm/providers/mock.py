from __future__ import annotations

import json
from typing import Any

from ai_platform.llm.base import BaseLLM, extract_json_payload
from ai_platform.llm.types import LLMError, LLMRequest, LLMResponse


class MockProvider(BaseLLM):
    def __init__(
        self,
        *,
        response: str | None = None,
        parsed_json: dict[str, Any] | list[Any] | None = None,
        error: Exception | None = None,
        latency_ms: float = 0.0,
        provider_name: str = "mock",
        model_name: str = "mock-model",
    ) -> None:
        self._response = response if response is not None else ""
        self._parsed_json = parsed_json
        self._error = error
        self._latency_ms = latency_ms
        self._provider_name = provider_name
        self._model_name = model_name

    def generate(self, request: LLMRequest) -> LLMResponse:
        provider = request.provider or self._provider_name
        model = request.model or self._model_name
        if self._error is not None:
            if isinstance(self._error, LLMError):
                raise self._error
            raise LLMError(
                provider=provider,
                model=model,
                error_type=type(self._error).__name__,
                retryable=False,
                message=str(self._error),
                raw=self._error,
            ) from self._error

        parsed = self._parsed_json
        if parsed is None and request.response_format == "json":
            if self._response:
                parsed = extract_json_payload(self._response)
            else:
                parsed = json.loads("{}")

        return LLMResponse(
            content=self._response,
            parsed_json=parsed,
            provider=provider,
            model=model,
            latency_ms=self._latency_ms,
            raw={"mock": True, "metadata": dict(request.metadata)},
        )
