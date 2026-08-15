from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Protocol, runtime_checkable

from ai_platform.agent.context import AgentContext, get_agent_context
from ai_platform.agent.state import AgentState


@runtime_checkable
class Node(Protocol):
    name: str

    def execute(self, state: AgentState, context: AgentContext) -> AgentState | None:
        ...


class BaseNode(ABC):
    name: str

    @abstractmethod
    def execute(self, state: AgentState, context: AgentContext) -> AgentState | None:
        raise NotImplementedError

    def run(self, state: AgentState) -> AgentState | None:
        context = get_agent_context() or AgentContext()
        return self.execute(state, context)
