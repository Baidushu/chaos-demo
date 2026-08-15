from __future__ import annotations

import json
import socket
import time
import urllib.error
import urllib.request
from typing import Any

from ai_platform.llm.base import BaseLLM, extract_json_payload
from ai_platform.llm.types import LLMError, LLMRequest, LLMResponse


class OllamaChatProvider(BaseLLM):
    def __init__(
        self,
        *,
        endpoint: str | None = None,
        model: str = "qwen2.5:7b",
        timeout_sec: float = 120.0,
    ) -> None:
        self._endpoint = endpoint or "http://localhost:11434"
        self._model = model
        self._timeout_sec = timeout_sec

    def generate(self, request: LLMRequest) -> LLMResponse:
        provider = request.provider or "ollama_chat"
        model = request.model or self._model
        timeout_sec = request.timeout_sec if request.timeout_sec is not None else self._timeout_sec
        messages = []
        if request.system:
            messages.append({"role": "system", "content": request.system})
        messages.append({"role": "user", "content": request.prompt})

        payload = json.dumps(
            {
                "model": model,
                "messages": messages,
                "stream": False,
            }
        ).encode("utf-8")

        url = self._build_url(self._endpoint)
        req = urllib.request.Request(url, data=payload, method="POST")
        req.add_header("Content-Type", "application/json")

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
                message=f"Ollama chat request timed out after {timeout_sec}s",
                raw=exc,
            ) from exc
        except urllib.error.HTTPError as exc:
            body = exc.read().decode("utf-8", errors="ignore")
            raise LLMError(
                provider=provider,
                model=model,
                error_type="http_error",
                retryable=False,
                message=f"Ollama chat API error {exc.code}: {body}",
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
        content = raw.get("message", {}).get("content", "")
        parsed_json = extract_json_payload(content) if request.response_format == "json" else None
        return LLMResponse(
            content=content,
            parsed_json=parsed_json,
            provider=provider,
            model=model,
            latency_ms=latency_ms,
            raw=raw,
            prompt_tokens=_coerce_int(raw.get("prompt_eval_count")),
            completion_tokens=_coerce_int(raw.get("eval_count")),
            total_tokens=_sum_tokens(raw),
        )

    @staticmethod
    def _build_url(endpoint: str) -> str:
        if endpoint.endswith("/api/chat"):
            return endpoint
        return endpoint.rstrip("/") + "/api/chat"


def _coerce_int(value: Any) -> int | None:
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def _sum_tokens(raw: dict[str, Any]) -> int | None:
    prompt_tokens = _coerce_int(raw.get("prompt_eval_count"))
    completion_tokens = _coerce_int(raw.get("eval_count"))
    if prompt_tokens is None or completion_tokens is None:
        return None
    return prompt_tokens + completion_tokens
