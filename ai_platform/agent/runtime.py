from __future__ import annotations

from collections.abc import Callable, Iterable
from dataclasses import dataclass, field
from typing import Any, TypeGuard, cast

from ai_platform.agent.context import AgentContext, agent_context
from ai_platform.agent.state import AgentState
from ai_platform.observability.collector import get_collector
from ai_platform.observability.event import AgentEvent
from ai_platform.observability.logger import get_logger
from ai_platform.observability.trace import SpanStatus, TraceContext
from ai_platform.security.guard import SecurityGuard
from ai_platform.security.policy import SecurityPolicy
from ai_platform.security.security_event import SecurityEvent
from ai_platform.workflow.node import BaseNode, Node
from ai_platform.workflow.engine import WorkflowEngine


WorkflowStep = Node | Callable[[AgentState], AgentState | None]


class SecurityBlockedError(Exception):
    """Raised when a security check blocks the request."""
    def __init__(self, message: str, violations: list[str] | None = None) -> None:
        super().__init__(message)
        self.violations = violations or []


@dataclass(slots=True)
class AgentRuntime:
    workflow: (
        WorkflowEngine | Iterable[WorkflowStep] | Callable[[AgentState], AgentState | None] | None
    ) = None
    context: AgentContext | None = None
    default_metadata: dict[str, Any] = field(default_factory=dict)
    observability_enabled: bool = True
    security: SecurityGuard | SecurityPolicy | None = None

    def run(self, request: Any, *, metadata: dict[str, Any] | None = None) -> AgentState:
        state = AgentState(request=request)
        if self.default_metadata:
            state.metadata.update(self.default_metadata)
        if metadata:
            state.metadata.update(metadata)
        return self.run_state(state)

    def run_state(self, state: AgentState) -> AgentState:
        collector = get_collector() if self.observability_enabled else None
        logger = get_logger() if self.observability_enabled else None
        trace: TraceContext | None = None

        # Resolve security guard
        guard = self._resolve_security()

        if collector is not None:
            trace = collector.start_trace(
                metadata={
                    "workflow_type": type(self.workflow).__name__ if self.workflow else "none",
                    "request": str(state.request)[:200],
                }
            )
            collector.record(AgentEvent.start(trace.trace_id, request=state.request))
            active_gauge = collector.gauge("agent.running", "Currently running agents")
            active_gauge.inc()
            if logger is not None:
                logger.set_trace_id(trace.trace_id)

        # --- Security: input check ---
        if guard is not None and guard.policy.security_enabled:
            sec_result = guard.check_input(state.request)
            if not sec_result.passed:
                self._record_security_block(collector, trace, sec_result, state)
                state.mark_failed()
                state.set_error(SecurityBlockedError(
                    f"Security blocked: {', '.join(sec_result.violations)}",
                    violations=sec_result.violations,
                ))
                state.metadata["security_result"] = sec_result.as_dict()
                if collector is not None and trace is not None:
                    collector.finish_trace(trace)
                return state

        with agent_context(self.context) as active_context:
            try:
                state.mark_running()
                start_time = __import__("time").perf_counter()
                result = self._dispatch(state, active_context)
                elapsed_ms = (__import__("time").perf_counter() - start_time) * 1000
                if isinstance(result, AgentState):
                    state = result
                elif result is not None:
                    state.answer = result
                if state.status != "failed":
                    state.mark_succeeded()
                if collector is not None and trace is not None:
                    collector.record(
                        AgentEvent.end(
                            trace.trace_id,
                            status=state.status,
                            duration_ms=elapsed_ms,
                        )
                    )
                return state
            except Exception as exc:  # pragma: no cover - defensive runtime path
                state.set_error(exc)
                state.mark_failed()
                if collector is not None and trace is not None:
                    collector.record(
                        AgentEvent.error(
                            trace.trace_id,
                            error_type=type(exc).__name__,
                            message=str(exc),
                        )
                    )
                return state
            finally:
                if collector is not None and trace is not None:
                    collector.finish_trace(trace)
                    active_gauge.dec()
                if logger is not None:
                    logger.set_trace_id(None)

    def _resolve_security(self) -> SecurityGuard | None:
        if self.security is None:
            return None
        if isinstance(self.security, SecurityGuard):
            return self.security
        if isinstance(self.security, SecurityPolicy):
            return SecurityGuard(self.security)
        return None

    @staticmethod
    def _record_security_block(
        collector, trace: TraceContext | None, sec_result, state: AgentState,
    ) -> None:
        if collector is None or trace is None:
            return
        collector.record(
            SecurityEvent.block_event(
                check_name=sec_result.check_name,
                risk_level=sec_result.risk_level,
                violations=sec_result.violations,
                trace_id=trace.trace_id,
                metadata={"request": str(state.request)[:200]},
            )
        )
        collector.counter("security.block.count").inc()
        collector.counter(f"security.{sec_result.check_name}.block_count").inc()

    def _dispatch(self, state: AgentState, context: AgentContext) -> AgentState | Any | None:
        workflow = self.workflow
        if workflow is None:
            return state
        if isinstance(workflow, WorkflowEngine):
            return workflow.run(state, context)
        if callable(workflow) and not self._is_node_like(workflow):
            return workflow(state)

        result: AgentState | Any | None = state
        steps = cast("Iterable[WorkflowStep]", workflow)
        for step in steps:
            result = self._run_step(step, state if result is None else result, context)
            if isinstance(result, AgentState):
                state = result
        return result

    def _run_step(
        self,
        step: WorkflowStep,
        state: AgentState,
        context: AgentContext,
    ) -> AgentState | Any | None:
        if self._is_node_like(step):
            if hasattr(step, "execute"):
                return step.execute(state, context)
            return cast("BaseNode", step).run(state)
        # 注：TypeGuard 对 Protocol 不执行负向收窄（结构性类型补集不明确），
        # 此处显式 cast——运行时 _is_node_like 为 False 即纯 callable。
        return cast("Callable[[AgentState], AgentState | None]", step)(state)

    @staticmethod
    def _is_node_like(obj: Any) -> TypeGuard[Node]:
        """Node 判定：带 name 且具备 execute/run 之一（TypeGuard 供 mypy 收窄）。

        对「有 run+name 但无 execute」的对象在类型上视为 Node（Protocol 声明
        execute），运行时由 _run_step 的 hasattr 分支兜底走 run。
        """
        return (hasattr(obj, "execute") or hasattr(obj, "run")) and hasattr(obj, "name")
