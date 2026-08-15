from __future__ import annotations

from dataclasses import dataclass, field

from ai_platform.agent.context import AgentContext
from ai_platform.agent.state import AgentState
from ai_platform.workflow.node import Node


@dataclass(slots=True)
class WorkflowRouter:
    node_names: list[str] = field(default_factory=list)

    def order(self, nodes: list[Node], state: AgentState, context: AgentContext) -> list[Node]:
        if not self.node_names:
            return list(nodes)

        index = {node.name: node for node in nodes}
        ordered: list[Node] = []
        for name in self.node_names:
            node = index.get(name)
            if node is not None:
                ordered.append(node)
        return ordered
