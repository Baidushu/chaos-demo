from __future__ import annotations

from contextlib import contextmanager
from dataclasses import dataclass, field
from typing import Any, Iterator
from contextvars import ContextVar
import uuid


@dataclass(slots=True)
class AgentContext:
    request_id: str = field(default_factory=lambda: uuid.uuid4().hex)
    trace_id: str = field(default_factory=lambda: uuid.uuid4().hex)
    run_id: str = field(default_factory=lambda: uuid.uuid4().hex)
    caller: str = ""
    metadata: dict[str, Any] = field(default_factory=dict)


_CURRENT_AGENT_CONTEXT: ContextVar[AgentContext | None] = ContextVar(
    "CURRENT_AGENT_CONTEXT",
    default=None,
)


def set_agent_context(context: AgentContext | None) -> None:
    _CURRENT_AGENT_CONTEXT.set(context)


def get_agent_context() -> AgentContext | None:
    return _CURRENT_AGENT_CONTEXT.get()


def clear_agent_context() -> None:
    _CURRENT_AGENT_CONTEXT.set(None)


@contextmanager
def agent_context(context: AgentContext | None = None) -> Iterator[AgentContext]:
    active = context or AgentContext()
    token = _CURRENT_AGENT_CONTEXT.set(active)
    try:
        yield active
    finally:
        _CURRENT_AGENT_CONTEXT.reset(token)
