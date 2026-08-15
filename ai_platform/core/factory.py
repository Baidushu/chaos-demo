"""Platform Factory — creates and wires all platform components.

Avoids direct `new` object creation in business code.
All component wiring is centralized here.
"""

from __future__ import annotations

from typing import Any

from ai_platform.agent.runtime import AgentRuntime
from ai_platform.evaluation.engine import EvaluationEngine
from ai_platform.evaluation.evaluator import BaseEvaluator, JudgeEvaluator, ScoreEvaluator
from ai_platform.evaluation.gate import QualityGate
from ai_platform.observability.collector import Collector, get_collector, reset_collector
from ai_platform.core.config import PlatformConfig
from ai_platform.security.guard import SecurityGuard
from ai_platform.security.policy import SecurityPolicy
from ai_platform.tools.executor import ToolExecutor
from ai_platform.tools.registry import ToolRegistry
from ai_platform.workflow.engine import WorkflowEngine
from ai_platform.workflow.router import WorkflowRouter


class PlatformFactory:
    """Factory that creates and wires all platform components.

    Usage:
        config = PlatformConfig.default()
        factory = PlatformFactory(config)
        service = factory.create_service()
    """

    def __init__(self, config: PlatformConfig | None = None) -> None:
        self._config = config or PlatformConfig.default()

    @property
    def config(self) -> PlatformConfig:
        return self._config

    # ── low-level components ──────────────────────────────────────

    def create_collector(self) -> Collector:
        """Create or reuse the global collector singleton."""
        return get_collector()

    def create_security_guard(self) -> SecurityGuard:
        """Create SecurityGuard from platform security policy."""
        return SecurityGuard(self._config.security)

    def create_security_policy(self) -> SecurityPolicy:
        """Expose the security policy directly."""
        return self._config.security

    def create_workflow_engine(
        self,
        nodes: list[Any] | None = None,
        router: WorkflowRouter | None = None,
    ) -> WorkflowEngine:
        """Create WorkflowEngine with optional pre-built nodes."""
        engine = WorkflowEngine(router=router)
        if nodes:
            for node in nodes:
                engine.register(node)
        return engine

    def create_tool_registry(self, tools: list[Any] | None = None) -> ToolRegistry:
        """Create ToolRegistry with optional pre-built tools."""
        registry = ToolRegistry()
        if tools:
            for tool in tools:
                registry.register(tool)
        return registry

    def create_tool_executor(
        self,
        registry: ToolRegistry | None = None,
    ) -> ToolExecutor:
        """Create ToolExecutor with security integration."""
        return ToolExecutor(
            registry=registry or self.create_tool_registry(),
            security=self._config.security,
        )

    def create_evaluation_engine(
        self,
        evaluators: list[BaseEvaluator] | None = None,
    ) -> EvaluationEngine:
        """Create EvaluationEngine with custom evaluators (empty by default).

        Single-request mode does not auto-register evaluators because
        ScoreEvaluator/JudgeEvaluator expect batch dict input.
        Pass evaluators explicitly for batch evaluation scenarios.
        """
        engine = EvaluationEngine()
        if evaluators is not None:
            for ev in evaluators:
                engine.register(ev)
        return engine

    def create_quality_gate(self) -> QualityGate:
        """Create QualityGate from platform evaluation thresholds."""
        return QualityGate(thresholds=self._config.evaluation.to_dict())

    # ── high-level components ─────────────────────────────────────

    def create_agent_runtime(
        self,
        workflow: Any | None = None,
    ) -> AgentRuntime:
        """Create AgentRuntime with security and observability wired in."""
        return AgentRuntime(
            workflow=workflow,
            security=self._config.security,
            observability_enabled=self._config.observability_enabled,
        )

    def reset(self) -> None:
        """Reset global state (collector singleton). Useful for testing."""
        reset_collector()
