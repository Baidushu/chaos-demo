from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Literal


ResponseFormat = Literal["text", "json"]


@dataclass(slots=True)
class LLMRequest:
    prompt: str
    system: str = ""
    model: str | None = None
    provider: str | None = None
    response_format: ResponseFormat = "text"
    timeout_sec: float | None = None
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass(slots=True)
class LLMResponse:
    content: str
    parsed_json: dict[str, Any] | list[Any] | None
    provider: str
    model: str
    latency_ms: float
    raw: Any = None
    prompt_tokens: int | None = None
    completion_tokens: int | None = None
    total_tokens: int | None = None


class LLMError(Exception):
    """LLM Gateway error with structured fields.

    Does NOT use ``@dataclass(slots=True)`` because CPython's ``Exception``
    base class stores its arguments in ``self.args``, which is incompatible
    with ``__slots__``.  ``__post_init__`` → ``super().__init__()`` triggers
    a C-level ``TypeError`` when the base class tries to write to ``args``.
    """

    def __init__(
        self,
        *,
        provider: str,
        model: str,
        error_type: str,
        retryable: bool,
        message: str,
        raw: Any = None,
    ) -> None:
        super().__init__(message)
        self.provider = provider
        self.model = model
        self.error_type = error_type
        self.retryable = retryable
        self.message = message
        self.raw = raw

    def __repr__(self) -> str:
        return (
            f"LLMError(provider={self.provider!r}, model={self.model!r}, "
            f"error_type={self.error_type!r}, retryable={self.retryable}, "
            f"message={self.message!r})"
        )
