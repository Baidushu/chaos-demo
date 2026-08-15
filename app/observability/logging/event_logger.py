from __future__ import annotations

import json
import logging
from typing import Any


def _coerce_level(level: str | int) -> int:
    if isinstance(level, int):
        return level
    return int(getattr(logging, str(level).upper(), logging.INFO))


def emit_structured_event(
    logger: logging.Logger,
    *,
    event: str,
    component: str | None = None,
    operation: str | None = None,
    result: str | None = None,
    extra_fields: dict[str, Any] | None = None,
    level: str | int = logging.INFO,
    **fields: Any,
) -> None:
    payload: dict[str, Any] = {"event": event}
    if component:
        payload["component"] = component
    if operation:
        payload["operation"] = operation
    if result:
        payload["result"] = result
    payload.update(extra_fields or {})
    payload.update(fields)
    logger.log(
        _coerce_level(level),
        payload.get("message", event),
        extra={"event_payload": payload},
    )


def log_event(*args: Any, **kwargs: Any) -> None:
    if args and isinstance(args[0], logging.Logger):
        logger = args[0]
        event = str(args[1]) if len(args) > 1 else str(kwargs.pop("event"))
        emit_structured_event(logger, event=event, **kwargs)
        return

    logger = kwargs.pop("logger", logging.getLogger("chaos-demo"))
    event = kwargs.pop("event", args[0] if args else None)
    if event is None:
        raise TypeError("event is required")
    component = kwargs.pop("component", None)
    operation = kwargs.pop("operation", None)
    result = kwargs.pop("result", None)
    extra_fields = kwargs.pop("extra_fields", None)
    level = kwargs.pop("level", logging.INFO)
    emit_structured_event(
        logger,
        event=str(event),
        component=component,
        operation=operation,
        result=result,
        extra_fields=extra_fields,
        level=level,
        **kwargs,
    )


def serialize_event_payload(payload: dict[str, Any]) -> str:
    return json.dumps(payload, ensure_ascii=False, default=str)
