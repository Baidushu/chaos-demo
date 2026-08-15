from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path
from typing import Any


DEFAULT_OPENAI_BASE_URL = "https://dashscope.aliyuncs.com/compatible-mode/v1"
DEFAULT_OLLAMA_BASE_URL = "http://localhost:11434"
DEFAULT_OLLAMA_GENERATE_URL = "http://localhost:11434/api/generate"
DEFAULT_TIMEOUT_SEC = 120.0
DEFAULT_JUDGE_CONFIG_PATH = Path("agent-eval/config/eval_config.yaml")


@dataclass(slots=True)
class GatewayConfig:
    provider: str = "ollama_chat"
    model: str = "qwen2.5:7b"
    endpoint: str = DEFAULT_OLLAMA_BASE_URL
    api_key: str = ""
    timeout_sec: float = DEFAULT_TIMEOUT_SEC


def _first_non_empty(*values: str | None) -> str | None:
    for value in values:
        if value:
            stripped = value.strip()
            if stripped:
                return stripped
    return None


def _normalize_provider_name(provider: str | None) -> str:
    if not provider:
        return "ollama_chat"

    mapping = {
        "auto": "ollama_chat",
        "ollama": "ollama_chat",
        "openai": "openai_compatible",
        "openai_compatible": "openai_compatible",
        "ollama_chat": "ollama_chat",
        "ollama_generate": "ollama_generate",
        "mock": "mock",
    }
    return mapping.get(provider, provider)


def _legacy_provider_from_env() -> str:
    backend = os.getenv("LLM_BACKEND", "auto").strip().lower()
    return _normalize_provider_name(backend or "auto")


def _default_endpoint_for_provider(provider: str) -> str:
    if provider == "openai_compatible":
        return DEFAULT_OPENAI_BASE_URL
    if provider == "ollama_generate":
        return DEFAULT_OLLAMA_GENERATE_URL
    return DEFAULT_OLLAMA_BASE_URL


def load_gateway_config(
    *,
    provider: str | None = None,
    model: str | None = None,
    endpoint: str | None = None,
    api_key: str | None = None,
    timeout_sec: float | None = None,
) -> GatewayConfig:
    resolved_provider = _normalize_provider_name(
        _first_non_empty(provider, os.getenv("LLM_GATEWAY_PROVIDER"), _legacy_provider_from_env())
    )
    resolved_model = _first_non_empty(
        model,
        os.getenv("LLM_GATEWAY_MODEL"),
        os.getenv("LLM_MODEL"),
        "qwen-plus" if resolved_provider == "openai_compatible" else "qwen2.5:7b",
    )
    resolved_endpoint = _first_non_empty(
        endpoint,
        os.getenv("LLM_GATEWAY_ENDPOINT"),
        os.getenv("LLM_BASE_URL") if resolved_provider == "openai_compatible" else None,
        os.getenv("OLLAMA_ENDPOINT")
        if resolved_provider in {"ollama_chat", "ollama_generate"}
        else None,
        _default_endpoint_for_provider(resolved_provider),
    )
    resolved_api_key = _first_non_empty(
        api_key,
        os.getenv("LLM_GATEWAY_API_KEY"),
        os.getenv("LLM_API_KEY"),
        "",
    )
    raw_timeout = _first_non_empty(
        None if timeout_sec is None else str(timeout_sec),
        os.getenv("LLM_GATEWAY_TIMEOUT_SEC"),
        os.getenv("LLM_TIMEOUT_SEC"),
        str(DEFAULT_TIMEOUT_SEC),
    )
    try:
        resolved_timeout = float(raw_timeout)
    except (TypeError, ValueError):
        resolved_timeout = DEFAULT_TIMEOUT_SEC

    return GatewayConfig(
        provider=resolved_provider,
        model=resolved_model or "",
        endpoint=resolved_endpoint or _default_endpoint_for_provider(resolved_provider),
        api_key=resolved_api_key or "",
        timeout_sec=resolved_timeout,
    )


def parse_simple_yaml(path: Path) -> dict[str, Any]:
    cfg: dict[str, Any] = {}
    current: str | None = None
    with path.open("r", encoding="utf-8") as handle:
        for raw in handle:
            line = raw.rstrip()
            if not line or line.lstrip().startswith("#"):
                continue
            if not line.startswith(" ") and line.endswith(":"):
                current = line[:-1]
                cfg[current] = {}
                continue
            if ":" not in line:
                continue
            key, value = line.split(":", 1)
            key = key.strip()
            value = value.strip().strip('"')
            if current and line.startswith("  "):
                section = cfg.setdefault(current, {})
                if isinstance(section, dict):
                    section[key] = value
            else:
                cfg[key] = value
    return cfg


def load_judge_gateway_config(path: Path | None = None) -> GatewayConfig:
    config_path = path or DEFAULT_JUDGE_CONFIG_PATH
    judge_cfg: dict[str, Any] = {}
    if config_path.is_file():
        parsed = parse_simple_yaml(config_path)
        judge_raw = parsed.get("judge", {})
        if isinstance(judge_raw, dict):
            judge_cfg = judge_raw

    provider = _normalize_provider_name(
        _first_non_empty(
            os.getenv("LLM_GATEWAY_PROVIDER"),
            judge_cfg.get("provider") if isinstance(judge_cfg, dict) else None,
            os.getenv("LLM_BACKEND"),
            "ollama_generate",
        )
    )
    model = _first_non_empty(
        os.getenv("LLM_GATEWAY_MODEL"),
        judge_cfg.get("model") if isinstance(judge_cfg, dict) else None,
        os.getenv("LLM_MODEL"),
        "qwen2.5:7b",
    )
    endpoint = _first_non_empty(
        os.getenv("LLM_GATEWAY_ENDPOINT"),
        judge_cfg.get("endpoint") if isinstance(judge_cfg, dict) else None,
        os.getenv("OLLAMA_ENDPOINT") if provider.startswith("ollama") else None,
        _default_endpoint_for_provider(provider),
    )
    timeout_raw = _first_non_empty(
        os.getenv("LLM_GATEWAY_TIMEOUT_SEC"),
        os.getenv("LLM_TIMEOUT_SEC"),
        str(DEFAULT_TIMEOUT_SEC),
    )
    try:
        timeout = float(timeout_raw)
    except (TypeError, ValueError):
        timeout = DEFAULT_TIMEOUT_SEC

    return GatewayConfig(
        provider=provider,
        model=model or "qwen2.5:7b",
        endpoint=endpoint or _default_endpoint_for_provider(provider),
        api_key=_first_non_empty(os.getenv("LLM_GATEWAY_API_KEY"), os.getenv("LLM_API_KEY"), "")
        or "",
        timeout_sec=timeout,
    )
