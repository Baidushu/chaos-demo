"""Platform context — shared request-scoped state.

Provides a lightweight context object that flows through the platform pipeline:
  API → Service → Agent → Workflow → Tool → LLM → Evaluation
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass(slots=True)
class PlatformContext:
    """Request-scoped platform context.

    Carries metadata through the entire platform pipeline without
    polluting business domains with infrastructure concerns.
    """

    request_id: str = ""
    trace_id: str = ""
    mode: str = "rule"
    metadata: dict[str, Any] = field(default_factory=dict)
