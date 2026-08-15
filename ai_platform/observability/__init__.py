"""Enterprise AI Agent Observability Framework.

Lightweight, self-contained observability layer inspired by OpenTelemetry concepts.
Provides unified trace, span, event, metrics, and structured logging for AI agents.
"""

from ai_platform.observability.trace import Span, SpanStatus, TraceContext
from ai_platform.observability.event import (
    AgentEvent,
    BaseEvent,
    EvaluationEvent,
    GateEvent,
    LLMEvent,
    NodeEvent,
    ToolEvent,
    WorkflowEvent,
)
from ai_platform.observability.metrics import Histogram, MetricsRegistry, SimpleCounter, SimpleGauge
from ai_platform.observability.collector import Collector, get_collector, reset_collector
from ai_platform.observability.logger import ObservabilityLogger, get_logger

__all__ = [
    # Trace
    "Span",
    "SpanStatus",
    "TraceContext",
    # Events
    "AgentEvent",
    "BaseEvent",
    "EvaluationEvent",
    "GateEvent",
    "LLMEvent",
    "NodeEvent",
    "ToolEvent",
    "WorkflowEvent",
    # Metrics
    "Histogram",
    "MetricsRegistry",
    "SimpleCounter",
    "SimpleGauge",
    # Collector
    "Collector",
    "get_collector",
    "reset_collector",
    # Logger
    "ObservabilityLogger",
    "get_logger",
]
