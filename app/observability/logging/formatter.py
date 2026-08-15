from __future__ import annotations

import json
import logging
from datetime import datetime, timezone

from .context import get_context


class JSONFormatter(logging.Formatter):
    """Single-line JSON formatter for structured application logs."""

    def format(self, record: logging.LogRecord) -> str:
        entry: dict[str, object] = {
            "timestamp": datetime.fromtimestamp(record.created, tz=timezone.utc).isoformat(),
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
        }
        entry.update(get_context())

        payload = getattr(record, "event_payload", None)
        if isinstance(payload, dict):
            entry.update(payload)
            entry["message"] = str(
                payload.get("message") or payload.get("event") or entry["message"]
            )
        else:
            message = record.getMessage()
            if message.startswith("{"):
                try:
                    decoded = json.loads(message)
                except (json.JSONDecodeError, TypeError):
                    decoded = None
                if isinstance(decoded, dict):
                    entry.update(decoded)
                    entry["message"] = str(decoded.get("event", message))

        if record.exc_info and record.exc_info[1]:
            exception = record.exc_info[1]
            entry["exception"] = self.formatException(record.exc_info)
            entry.setdefault("exception_type", exception.__class__.__name__)
        return json.dumps(entry, ensure_ascii=False, default=str)
