from __future__ import annotations

import json
import socket
import time
import urllib.error
import urllib.request
from typing import Any

from ai_platform.llm.base import BaseLLM, extract_json_payload
from ai_platform.llm.types import LLMError, LLMRequest, LLMResponse


class OllamaGenerateProvider(BaseLLM):
    def __init__(
        self,
        *,
        endpoint: str | None = None,
        model: str = "qwen2.5:7b",
        timeout_sec: float = 120.0,
    ) -> None:
        self._endpoint = endpoint or "http://localhost:11434/api/generate"
        self._model = model
        self._timeout_sec = timeout_sec

    def generate(self, request: LLMRequest) -> LLMResponse:
        provider = request.provider or "ollama_generate"
        model = request.model or self._model
        timeout_sec = request.timeout_sec if request.timeout_sec is not None else self._timeout_sec
        prompt = self._compose_prompt(request.system, request.prompt)
        payload = json.dumps(
            {
                "model": model,
                "prompt": prompt,
                "stream": False,
            }
        ).encode("utf-8")

        req = urllib.request.Request(self._endpoint, data=payload, method="POST")
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
                message=f"Ollama generate request timed out after {timeout_sec}s",
                raw=exc,
            ) from exc
        except urllib.error.HTTPError as exc:
            body = exc.read().decode("utf-8", errors="ignore")
            raise LLMError(
                provider=provider,
                model=model,
                error_type="http_error",
                retryable=False,
                message=f"Ollama generate API error {exc.code}: {body}",
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
        content = raw.get("response", "").strip()
        parsed_json = extract_json_payload(content) if request.response_format == "json" else None
        prompt_tokens = _coerce_int(raw.get("prompt_eval_count"))
        completion_tokens = _coerce_int(raw.get("eval_count"))
        total_tokens = None
        if prompt_tokens is not None and completion_tokens is not None:
            total_tokens = prompt_tokens + completion_tokens
        return LLMResponse(
            content=content,
            parsed_json=parsed_json,
            provider=provider,
            model=model,
            latency_ms=latency_ms,
            raw=raw,
            prompt_tokens=prompt_tokens,
            completion_tokens=completion_tokens,
            total_tokens=total_tokens,
        )

    @staticmethod
    def _compose_prompt(system: str, prompt: str) -> str:
        if system.strip():
            return f"{system.rstrip()}\n{prompt}"
        return prompt


def _coerce_int(value: Any) -> int | None:
    try:
        return int(value)
    except (TypeError, ValueError):
        return None
