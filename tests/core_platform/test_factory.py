"""Tests for PlatformFactory — component creation and wiring."""

import pytest

from ai_platform.evaluation.engine import EvaluationEngine
from ai_platform.evaluation.evaluator import ScoreEvaluator
from ai_platform.evaluation.gate import QualityGate
from ai_platform.observability.collector import Collector, reset_collector
from ai_platform.core.config import PlatformConfig
from ai_platform.core.factory import PlatformFactory
from ai_platform.security.guard import SecurityGuard
from ai_platform.tools.executor import ToolExecutor
from ai_platform.tools.registry import ToolRegistry
from ai_platform.workflow.engine import WorkflowEngine


@pytest.fixture(autouse=True)
def reset():
    reset_collector()
    yield


class TestPlatformFactoryCreation:
    def test_creates_with_default_config(self):
        f = PlatformFactory()
        assert f.config.mode == "rule"

    def test_creates_with_custom_config(self):
        cfg = PlatformConfig(mode="ollama")
        f = PlatformFactory(cfg)
        assert f.config.mode == "ollama"

    def test_config_property(self):
        cfg = PlatformConfig(timeout_seconds=120)
        f = PlatformFactory(cfg)
        assert f.config.timeout_seconds == 120


class TestPlatformFactoryComponents:
    def test_create_collector(self):
        f = PlatformFactory()
        c = f.create_collector()
        assert isinstance(c, Collector)

    def test_collector_is_singleton(self):
        f = PlatformFactory()
        c1 = f.create_collector()
        c2 = f.create_collector()
        assert c1 is c2

    def test_create_security_guard(self):
        f = PlatformFactory()
        g = f.create_security_guard()
        assert isinstance(g, SecurityGuard)
        assert g.policy.security_enabled is True

    def test_create_security_policy(self):
        f = PlatformFactory()
        p = f.create_security_policy()
        assert p.security_enabled is True

    def test_create_workflow_engine(self):
        f = PlatformFactory()
        engine = f.create_workflow_engine()
        assert isinstance(engine, WorkflowEngine)

    def test_create_workflow_engine_with_nodes(self):
        from ai_platform.workflow.node import BaseNode

        class DummyNode(BaseNode):
            name = "dummy"
            def execute(self, state, context):
                return state

        node = DummyNode()
        f = PlatformFactory()
        engine = f.create_workflow_engine(nodes=[node])
        assert engine.get_node("dummy") is node

    def test_create_tool_registry(self):
        f = PlatformFactory()
        registry = f.create_tool_registry()
        assert isinstance(registry, ToolRegistry)
        assert registry.list_tools() == []

    def test_create_tool_executor(self):
        f = PlatformFactory()
        executor = f.create_tool_executor()
        assert isinstance(executor, ToolExecutor)

    def test_create_evaluation_engine_empty(self):
        f = PlatformFactory()
        engine = f.create_evaluation_engine()
        assert isinstance(engine, EvaluationEngine)
        assert len(engine.evaluators) == 0

    def test_create_evaluation_engine_with_evaluators(self):
        f = PlatformFactory()
        engine = f.create_evaluation_engine(evaluators=[ScoreEvaluator()])
        assert len(engine.evaluators) == 1

    def test_create_quality_gate(self):
        f = PlatformFactory()
        gate = f.create_quality_gate()
        assert isinstance(gate, QualityGate)

    def test_create_agent_runtime(self):
        f = PlatformFactory()
        rt = f.create_agent_runtime()
        from ai_platform.agent.runtime import AgentRuntime
        assert isinstance(rt, AgentRuntime)


class TestPlatformFactoryReset:
    def test_reset_collector(self):
        f = PlatformFactory()
        c1 = f.create_collector()
        f.reset()
        c2 = f.create_collector()
        # After reset, new collector is a different instance
        assert c1 is not c2
