"""Event models for AI Agent Observability.

Hierarchy:
    BaseEvent (abstract)
    ├── AgentEvent   — agent lifecycle (run start/end, error)
    ├── NodeEvent    — workflow node execution (planner, tool, judge)
    ├── ToolEvent    — tool call lifecycle
    ├── LLMEvent     — LLM invocation details
    ├── EvaluationEvent — evaluation engine execution
    ├── GateEvent    — quality gate check result
    └── WorkflowEvent — workflow lifecycle (start/end)
"""

from __future__ import annotations

import time
import uuid
from dataclasses import dataclass, field
from typing import Any


@dataclass(slots=True)
class BaseEvent:
    event_type: str
    timestamp: float = field(default_factory=time.time)
    trace_id: str = field(default_factory=lambda: uuid.uuid4().hex[:16])
    span_id: str | None = None
    payload: dict[str, Any] = field(default_factory=dict)

    def as_dict(self) -> dict[str, Any]:
        return {
            "event_type": self.event_type,
            "timestamp": self.timestamp,
            "trace_id": self.trace_id,
            "span_id": self.span_id,
            "payload": dict(self.payload),
        }


@dataclass(slots=True)
class AgentEvent(BaseEvent):
    """Agent lifecycle events: agent.run.start, agent.run.end, agent.error"""

    event_type: str = "agent"

    @classmethod
    def start(
        cls,
        trace_id: str,
        *,
        request: Any = None,
        metadata: dict[str, Any] | None = None,
    ) -> "AgentEvent":
        return cls(
            event_type="agent.run.start",
            trace_id=trace_id,
            payload={
                "request": str(request)[:500] if request is not None else None,
                "metadata": metadata or {},
            },
        )

    @classmethod
    def end(
        cls,
        trace_id: str,
        *,
        status: str = "succeeded",
        duration_ms: float | None = None,
    ) -> "AgentEvent":
        return cls(
            event_type="agent.run.end",
            trace_id=trace_id,
            payload={"status": status, "duration_ms": duration_ms},
        )

    @classmethod
    def error(
        cls,
        trace_id: str,
        *,
        error_type: str = "",
        message: str = "",
    ) -> "AgentEvent":
        return cls(
            event_type="agent.error",
            trace_id=trace_id,
            payload={"error_type": error_type, "message": message},
        )


@dataclass(slots=True)
class NodeEvent(BaseEvent):
    """Workflow node execution events: node.start, node.end, node.error"""

    event_type: str = "node"

    @classmethod
    def start(
        cls,
        trace_id: str,
        span_id: str,
        *,
        node_name: str,
        metadata: dict[str, Any] | None = None,
    ) -> "NodeEvent":
        return cls(
            event_type="node.start",
            trace_id=trace_id,
            span_id=span_id,
            payload={"node_name": node_name, "metadata": metadata or {}},
        )

    @classmethod
    def end(
        cls,
        trace_id: str,
        span_id: str,
        *,
        node_name: str,
        duration_ms: float | None = None,
        status: str = "ok",
    ) -> "NodeEvent":
        return cls(
            event_type="node.end",
            trace_id=trace_id,
            span_id=span_id,
            payload={
                "node_name": node_name,
                "duration_ms": duration_ms,
                "status": status,
            },
        )


@dataclass(slots=True)
class ToolEvent(BaseEvent):
    """Tool call events: tool.call, tool.result, tool.error"""

    event_type: str = "tool"

    @classmethod
    def call(
        cls,
        trace_id: str,
        span_id: str,
        *,
        tool_name: str,
        params: dict[str, Any] | None = None,
    ) -> "ToolEvent":
        return cls(
            event_type="tool.call",
            trace_id=trace_id,
            span_id=span_id,
            payload={"tool_name": tool_name, "params": params or {}},
        )

    @classmethod
    def result(
        cls,
        trace_id: str,
        span_id: str,
        *,
        tool_name: str,
        ok: bool,
        duration_ms: float | None = None,
        result: Any = None,
        error: str | None = None,
    ) -> "ToolEvent":
        return cls(
            event_type="tool.result",
            trace_id=trace_id,
            span_id=span_id,
            payload={
                "tool_name": tool_name,
                "ok": ok,
                "duration_ms": duration_ms,
                "result": str(result)[:500] if result is not None else None,
                "error": error,
            },
        )


@dataclass(slots=True)
class LLMEvent(BaseEvent):
    """LLM invocation events: llm.call, llm.response, llm.error"""

    event_type: str = "llm"

    @classmethod
    def call(
        cls,
        trace_id: str,
        span_id: str,
        *,
        provider: str,
        model: str,
        prompt: str | None = None,
    ) -> "LLMEvent":
        return cls(
            event_type="llm.call",
            trace_id=trace_id,
            span_id=span_id,
            payload={
                "provider": provider,
                "model": model,
                "prompt_preview": prompt[:200] if prompt else None,
            },
        )

    @classmethod
    def response(
        cls,
        trace_id: str,
        span_id: str,
        *,
        provider: str,
        model: str,
        duration_ms: float | None = None,
        prompt_tokens: int | None = None,
        completion_tokens: int | None = None,
        total_tokens: int | None = None,
    ) -> "LLMEvent":
        return cls(
            event_type="llm.response",
            trace_id=trace_id,
            span_id=span_id,
            payload={
                "provider": provider,
                "model": model,
                "duration_ms": duration_ms,
                "prompt_tokens": prompt_tokens,
                "completion_tokens": completion_tokens,
                "total_tokens": total_tokens,
            },
        )

    @classmethod
    def error(
        cls,
        trace_id: str,
        span_id: str,
        *,
        provider: str,
        model: str,
        error_type: str = "",
        message: str = "",
    ) -> "LLMEvent":
        return cls(
            event_type="llm.error",
            trace_id=trace_id,
            span_id=span_id,
            payload={
                "provider": provider,
                "model": model,
                "error_type": error_type,
                "message": message,
            },
        )


@dataclass(slots=True)
class EvaluationEvent(BaseEvent):
    """Evaluation engine events: evaluation.start, evaluation.result"""

    event_type: str = "evaluation"

    @classmethod
    def start(cls, trace_id: str, *, evaluators: list[str]) -> "EvaluationEvent":
        return cls(
            event_type="evaluation.start",
            trace_id=trace_id,
            payload={"evaluators": evaluators},
        )

    @classmethod
    def result(
        cls,
        trace_id: str,
        *,
        score: float | None = None,
        success: bool = True,
        metrics: dict[str, Any] | None = None,
        duration_ms: float | None = None,
    ) -> "EvaluationEvent":
        return cls(
            event_type="evaluation.result",
            trace_id=trace_id,
            payload={
                "score": score,
                "success": success,
                "duration_ms": duration_ms,
                "metrics": metrics or {},
            },
        )


@dataclass(slots=True)
class GateEvent(BaseEvent):
    """Quality gate events: gate.check, gate.pass, gate.fail"""

    event_type: str = "gate"

    @classmethod
    def check(cls, trace_id: str, *, thresholds: dict[str, float]) -> "GateEvent":
        return cls(
            event_type="gate.check",
            trace_id=trace_id,
            payload={"thresholds": thresholds},
        )

    @classmethod
    def result(
        cls,
        trace_id: str,
        *,
        passed: bool,
        reasons: list[str] | None = None,
        metrics: dict[str, Any] | None = None,
    ) -> "GateEvent":
        return cls(
            event_type="gate.pass" if passed else "gate.fail",
            trace_id=trace_id,
            payload={
                "passed": passed,
                "reasons": reasons or [],
                "metrics": metrics or {},
            },
        )


@dataclass(slots=True)
class WorkflowEvent(BaseEvent):
    """Workflow lifecycle events: workflow.start, workflow.end"""

    event_type: str = "workflow"

    @classmethod
    def start(cls, trace_id: str, *, node_count: int = 0, node_names: list[str] | None = None) -> "WorkflowEvent":
        return cls(
            event_type="workflow.start",
            trace_id=trace_id,
            payload={"node_count": node_count, "node_names": node_names or []},
        )

    @classmethod
    def end(
        cls,
        trace_id: str,
        *,
        node_count: int = 0,
        duration_ms: float | None = None,
    ) -> "WorkflowEvent":
        return cls(
            event_type="workflow.end",
            trace_id=trace_id,
            payload={"node_count": node_count, "duration_ms": duration_ms},
        )
