from __future__ import annotations

from contextvars import ContextVar

_REQUEST_CONTEXT: ContextVar[dict[str, object] | None] = ContextVar(
    "request_logging_context",
    default=None,
)
_DEFAULT_CONTEXT: ContextVar[dict[str, object] | None] = ContextVar(
    "default_logging_context",
    default=None,
)


def configure_default_context(
    *,
    service: str | None = None,
    environment: str | None = None,
) -> None:
    context = dict(_DEFAULT_CONTEXT.get() or {})
    if service:
        context["service"] = service
    if environment:
        context["environment"] = environment
    _DEFAULT_CONTEXT.set(context)


def set_context(**fields: object) -> None:
    clean = {key: value for key, value in fields.items() if value is not None}
    _REQUEST_CONTEXT.set(clean)


def bind_context(**fields: object) -> None:
    context = dict(_REQUEST_CONTEXT.get() or {})
    for key, value in fields.items():
        if value is not None:
            context[key] = value
    _REQUEST_CONTEXT.set(context)


def get_context() -> dict[str, object]:
    context = dict(_DEFAULT_CONTEXT.get() or {})
    context.update(_REQUEST_CONTEXT.get() or {})
    return context


def clear_context() -> None:
    _REQUEST_CONTEXT.set({})
