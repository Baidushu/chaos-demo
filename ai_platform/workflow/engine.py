from __future__ import annotations

from dataclasses import dataclass, field

from ai_platform.agent.context import AgentContext
from ai_platform.agent.state import AgentState
from ai_platform.observability.collector import get_collector
from ai_platform.observability.event import NodeEvent, WorkflowEvent
from ai_platform.observability.trace import SpanStatus
from ai_platform.workflow.node import Node
from ai_platform.workflow.router import WorkflowRouter


@dataclass(slots=True)
class WorkflowEngine:
    router: WorkflowRouter | None = None
    _nodes: list[Node] = field(default_factory=list)

    def register(self, node: Node) -> None:
        self._nodes.append(node)

    def get_node(self, name: str) -> Node | None:
        for node in self._nodes:
            if node.name == name:
                return node
        return None

    def run(self, state: AgentState, context: AgentContext) -> AgentState:
        ordered = self._ordered_nodes(state, context)
        collector = get_collector()
        recorded_workflow = False
        current = state

        if collector is not None and collector.active_trace is not None:
            trace_id = collector.active_trace.trace_id
            collector.record(
                WorkflowEvent.start(
                    trace_id,
                    node_count=len(ordered),
                    node_names=[n.name for n in ordered],
                )
            )
            recorded_workflow = True

        for node in ordered:
            span = None
            if collector is not None and collector.active_trace is not None:
                trace_id = collector.active_trace.trace_id
                span = collector.create_span(f"node.{node.name}", attributes={"node": node.name})
                collector.record(
                    NodeEvent.start(trace_id, span.span_id, node_name=node.name)
                )
                collector.counter(f"node.{node.name}.count").inc()

            try:
                result = node.execute(current, context)
                if isinstance(result, AgentState):
                    current = result
                if span is not None:
                    span.finish(status=SpanStatus.OK)
                    if collector is not None and collector.active_trace is not None:
                        collector.record(
                            NodeEvent.end(
                                trace_id,
                                span.span_id,
                                node_name=node.name,
                                duration_ms=span.duration,
                                status="ok",
                            )
                        )
            except Exception:
                if span is not None:
                    span.finish(status=SpanStatus.ERROR)
                    if collector is not None and collector.active_trace is not None:
                        collector.record(
                            NodeEvent.end(
                                trace_id,
                                span.span_id,
                                node_name=node.name,
                                duration_ms=span.duration,
                                status="error",
                            )
                        )
                raise

        if recorded_workflow and collector.active_trace is not None:
            collector.record(
                WorkflowEvent.end(
                    trace_id,
                    node_count=len(ordered),
                )
            )

        return current

    def _ordered_nodes(self, state: AgentState, context: AgentContext) -> list[Node]:
        if self.router is None:
            return list(self._nodes)
        return self.router.order(list(self._nodes), state, context)
