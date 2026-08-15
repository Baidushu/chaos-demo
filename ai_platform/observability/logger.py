"""Structured JSON logger for AI Agent Observability.

Replaces print() with consistent JSON log entries.
Each log entry includes: time, level, trace_id, event, and contextual fields.
"""

from __future__ import annotations

import json
import logging
import os
import sys
import threading
import time
from typing import Any


class ObservabilityLogger:
    _instance: "ObservabilityLogger | None" = None
    _lock: threading.Lock = threading.Lock()

    def __init__(self, *, name: str = "ai.observability", level: int = logging.INFO) -> None:
        self._name = name
        self._level = level
        self._default_trace_id: str | None = None

    @classmethod
    def get(cls) -> "ObservabilityLogger":
        if cls._instance is None:
            with cls._lock:
                if cls._instance is None:
                    cls._instance = cls._create_from_env()
        return cls._instance

    @classmethod
    def reset(cls) -> None:
        with cls._lock:
            cls._instance = None

    def set_trace_id(self, trace_id: str | None) -> None:
        self._default_trace_id = trace_id

    @staticmethod
    def _create_from_env() -> "ObservabilityLogger":
        level_str = os.getenv("OBSERVABILITY_LOG_LEVEL", "INFO").upper()
        level = getattr(logging, level_str, logging.INFO)
        return ObservabilityLogger(level=level)

    def _emit(self, level: str, event: str, trace_id: str | None = None, **fields: Any) -> None:
        log_level = getattr(logging, level, logging.INFO)
        if log_level < self._level:
            return
        entry: dict[str, Any] = {
            "time": time.strftime("%Y-%m-%dT%H:%M:%S", time.localtime()),
            "level": level,
            "trace_id": trace_id or self._default_trace_id or "",
            "event": event,
            **fields,
        }
        line = json.dumps(entry, ensure_ascii=False, default=str)
        if level in ("ERROR", "CRITICAL"):
            print(line, file=sys.stderr)
        else:
            print(line, file=sys.stdout)

    def info(self, event: str, trace_id: str | None = None, **fields: Any) -> None:
        self._emit("INFO", event, trace_id, **fields)

    def warn(self, event: str, trace_id: str | None = None, **fields: Any) -> None:
        self._emit("WARNING", event, trace_id, **fields)

    def error(self, event: str, trace_id: str | None = None, **fields: Any) -> None:
        self._emit("ERROR", event, trace_id, **fields)

    def debug(self, event: str, trace_id: str | None = None, **fields: Any) -> None:
        self._emit("DEBUG", event, trace_id, **fields)


def get_logger() -> ObservabilityLogger:
    return ObservabilityLogger.get()
