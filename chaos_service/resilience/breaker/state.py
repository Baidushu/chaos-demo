"""Circuit breaker states."""

from __future__ import annotations

from enum import Enum


class CircuitState(Enum):
    CLOSED = "closed"
    OPEN = "open"
    HALF_OPEN = "half_open"
