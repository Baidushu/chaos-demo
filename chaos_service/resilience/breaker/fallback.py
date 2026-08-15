"""Fallback abstractions for the circuit breaker."""

from __future__ import annotations

from typing import Any, Protocol

from flask import jsonify


class FallbackHandler(Protocol):
    def execute(self) -> Any: ...


class DefaultCircuitOpenFallback:
    def execute(self):
        return jsonify({"status": "queued", "reason": "circuit open"}), 202
