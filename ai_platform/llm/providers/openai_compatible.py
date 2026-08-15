from __future__ import annotations

import json
import socket
import time
import urllib.error
import urllib.request
from typing import Any

from ai_platform.llm.base import BaseLLM, extract_json_payload
from ai_platform.llm.types import LLMError, LLMRequest, LLMResponse


class OpenAICompatibleProvider(BaseLLM):
    def __init__(
        self,
        *,
        endpoint: str | None = None,
        api_key: str = "",
        model: str = "qwen-plus",
        timeout_sec: float = 120.0,
    ) -> None:
        self._endpoint = endpoint or "https://dashscope.aliyuncs.com/compatible-mode/v1"
        self._api_key = api_key
        self._model = model
        self._timeout_sec = timeout_sec

    def generate(self, request: LLMRequest) -> LLMResponse:
        provider = request.provider or "openai_compatible"
        model = request.model or self._model
        timeout_sec = request.timeout_sec if request.timeout_sec is not None else self._timeout_sec
        api_key = self._api_key
        if not api_key:
            raise LLMError(
                provider=provider,
                model=model,
                error_type="missing_api_key",
                retryable=False,
                message="LLM_API_KEY is required for openai_compatible provider",
            )

        messages = []
        if request.system:
            messages.append({"role": "system", "content": request.system})
        messages.append({"role": "user", "content": request.prompt})

        payload = json.dumps(
            {
                "model": model,
                "messages": messages,
            }
        ).encode("utf-8")

        req = urllib.request.Request(self._build_url(self._endpoint), data=payload, method="POST")
        req.add_header("Content-Type", "application/json")
        req.add_header("Authorization", f"Bearer {api_key}")

        started = time.perf_counter()
        try:
            with urllib.request.urlopen(req, timeout=timeout_sec) as resp:
                raw = json.loads(resp.read().decode("utf-8"))
        except (TimeoutError, socket.timeout) as exc:
            raise LLMError(
                provider=provider,
                model=model,
                error_type="timeout",
                retryable=True,
                message=f"OpenAI-compatible request timed out after {timeout_sec}s",
                raw=exc,
            ) from exc
        except urllib.error.HTTPError as exc:
            body = exc.read().decode("utf-8", errors="ignore")
            raise LLMError(
                provider=provider,
                model=model,
                error_type="http_error",
                retryable=False,
                message=f"OpenAI-compatible API error {exc.code}: {body}",
                raw=body,
            ) from exc
        except Exception as exc:
            raise LLMError(
                provider=provider,
                model=model,
                error_type=type(exc).__name__,
                retryable=False,
                message=str(exc),
                raw=exc,
            ) from exc

        latency_ms = (time.perf_counter() - started) * 1000
        choices = raw.get("choices", [])
        message = choices[0]["message"]["content"] if choices else ""
        parsed_json = extract_json_payload(message) if request.response_format == "json" else None
        usage = raw.get("usage", {})
        return LLMResponse(
            content=message,
            parsed_json=parsed_json,
            provider=provider,
            model=model,
            latency_ms=latency_ms,
            raw=raw,
            prompt_tokens=_coerce_int(usage.get("prompt_tokens")),
            completion_tokens=_coerce_int(usage.get("completion_tokens")),
            total_tokens=_coerce_int(usage.get("total_tokens")),
        )

    @staticmethod
    def _build_url(endpoint: str) -> str:
        if endpoint.endswith("/chat/completions"):
            return endpoint
        return endpoint.rstrip("/") + "/chat/completions"


def _coerce_int(value: Any) -> int | None:
    try:
        return int(value)
    except (TypeError, ValueError):
        return None
