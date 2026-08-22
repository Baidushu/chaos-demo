"""密钥脱敏工具——安全边界的最后一道防线。

设计意图（纵深防御）：
  1. 第一道防线：密钥只在 GatewayConfig / Provider 内部持有，
     不进入日志、trace、HTTP 响应（GatewayConfig 已将 api_key
     排除出 repr）；
  2. 第二道防线（本模块）：任何「异常消息 / 错误响应」在离开
     平台边界前，一律经过 redact() 清洗——即使上游组件失误把
     密钥拼进了消息，也不会外泄。

用法：
    from ai_platform.security.redaction import redact
    safe_message = redact(f"provider failed: {exc}")
"""

from __future__ import annotations

import os
import re
from typing import Iterable

REDACTED = "***REDACTED***"

#: 平台已知承载真实密钥的环境变量（用于精确匹配脱敏）。
SECRET_ENV_VARS: tuple[str, ...] = (
    "LLM_GATEWAY_API_KEY",
    "LLM_API_KEY",
)

# 已知密钥形态的模式匹配（不依赖环境变量也能兜底）：
# - OpenAI 风格 sk-xxx
# - Authorization: Bearer xxx
# - api_key=xxx / token: xxx 等键值对形态
_SECRET_PATTERNS: tuple[re.Pattern[str], ...] = (
    re.compile(r"sk-[A-Za-z0-9_\-]{8,}"),
    re.compile(r"(?i)bearer\s+[A-Za-z0-9._\-]{8,}"),
    re.compile(r"(?i)\b(api[_-]?key|token|secret|password)\b\s*[=:]\s*[^\s,;\"']+"),
)


def active_secrets() -> list[str]:
    """收集当前进程中已配置的真实密钥值（仅用于脱敏，绝不外传）。"""
    secrets: list[str] = []
    for name in SECRET_ENV_VARS:
        value = os.environ.get(name, "").strip()
        if value:
            secrets.append(value)
    return secrets


def mask_secret(value: str, keep: int = 4) -> str:
    """把密钥值遮蔽为安全展示形式（如 sk-ab****）。"""
    value = str(value)
    if len(value) <= keep * 2:
        return REDACTED
    return f"{value[:keep]}****"


def redact(text: str, secrets: Iterable[str] | None = None) -> str:
    """清洗文本：先精确替换已知密钥值，再按模式兜底。

    Args:
        text: 待清洗的异常消息 / 错误文本。
        secrets: 需要精确脱敏的密钥值列表；None 时自动收集
            ``active_secrets()``。
    """
    if not text:
        return text

    cleaned = str(text)
    target_secrets = list(secrets) if secrets is not None else active_secrets()
    for secret in target_secrets:
        if secret:
            cleaned = cleaned.replace(secret, REDACTED)

    for pattern in _SECRET_PATTERNS:
        cleaned = pattern.sub(REDACTED, cleaned)
    return cleaned
