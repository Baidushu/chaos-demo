"""AIPlatformService — unified AI Platform entry point.

Orchestrates the complete call chain:
  create trace → security check → runtime execute → evaluation → quality gate → result
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from ai_platform.agent.state import AgentState
from ai_platform.evaluation.engine import EvaluationEngine
from ai_platform.evaluation.gate import QualityGate
from ai_platform.core.config import PlatformConfig
from ai_platform.core.exceptions import (
    AgentExecutionError,
    EvaluationError,
    PlatformError,
    SecurityBlockedError,
)
from ai_platform.core.factory import PlatformFactory


@dataclass(slots=True)
class PlatformResult:
    """Unified result from the AI Platform service."""

    success: bool
    answer: Any = None
    score: float | None = None
    security_score: float | None = None
    trace_id: str = ""
    evaluation: dict[str, Any] | None = None
    gate: dict[str, Any] | None = None
    error: str | None = None
    error_type: str | None = None
    violations: list[str] = field(default_factory=list)
    metadata: dict[str, Any] = field(default_factory=dict)

    def as_dict(self) -> dict[str, Any]:
        return {
            "success": self.success,
            "answer": self.answer,
            "score": self.score,
            "security_score": self.security_score,
            "trace_id": self.trace_id,
            "evaluation": self.evaluation,
            "gate": self.gate,
            "error": self.error,
            "error_type": self.error_type,
            "violations": list(self.violations),
            "metadata": dict(self.metadata),
        }


class AIPlatformService:
    """Unified AI Platform service.

    Usage:
        config = PlatformConfig.default()
        factory = PlatformFactory(config)
        runtime = factory.create_agent_runtime(workflow=my_workflow)
        eval_engine = factory.create_evaluation_engine()

        service = AIPlatformService(
            agent_runtime=runtime,
            evaluation_engine=eval_engine,
            quality_gate=factory.create_quality_gate(),
            config=config,
        )
        result = service.run("What is the capital of France?")
    """

    def __init__(
        self,
        *,
        agent_runtime: Any,  # AgentRuntime
        evaluation_engine: EvaluationEngine | None = None,
        quality_gate: QualityGate | None = None,
        config: PlatformConfig | None = None,
    ) -> None:
        self._runtime = agent_runtime
        self._evaluation = evaluation_engine
        self._gate = quality_gate
        self._config = config or PlatformConfig.default()

    @property
    def config(self) -> PlatformConfig:
        return self._config

    def run(self, request: Any, *, mode: str | None = None) -> PlatformResult:
        """Execute the complete platform pipeline.

        Flow:
          1. Start trace (via AgentRuntime)
          2. Security check (input validation + injection detection)
          3. AgentRuntime execution
          4. Evaluation (if enabled)
          5. Quality gate (if enabled)
          6. Return unified PlatformResult
        """
        effective_mode = mode or self._config.mode

        # Step 1-3: Execute agent (security + runtime is inside AgentRuntime.run_state)
        try:
            state = self._runtime.run(request, metadata={"mode": effective_mode})
        except Exception as exc:
            return PlatformResult(
                success=False,
                error=str(exc),
                error_type=type(exc).__name__,
                metadata={"mode": effective_mode},
            )

        # Handle security block (detected by error type in state)
        if state.status == "failed" and state.error:
            err_data = state.error
            if err_data.get("type") == "SecurityBlockedError":
                violations = []
                sec_result = state.metadata.get("security_result", {})
                if isinstance(sec_result, dict):
                    violations = sec_result.get("violations", [])
                return PlatformResult(
                    success=False,
                    error=err_data.get("message", "Security blocked"),
                    error_type="SecurityBlocked",
                    violations=violations,
                    security_score=state.metadata.get("security_score", 0),
                    metadata={"mode": effective_mode},
                )

        # Handle other execution failures
        if state.status == "failed":
            return PlatformResult(
                success=False,
                error=state.error.get("message", "Agent execution failed") if state.error else "Agent execution failed",
                error_type=state.error.get("type", "AgentError") if state.error else "AgentError",
                metadata={"mode": effective_mode},
            )

        answer = state.answer
        trace_id = ""

        # Extract trace_id from observability if active
        from ai_platform.observability.collector import get_collector
        collector = get_collector()
        if collector is not None and collector.active_trace is not None:
            trace_id = collector.active_trace.trace_id

        # Step 4: Evaluation
        eval_result_dict = None
        score = None
        security_score = None

        if self._config.evaluation_enabled and self._evaluation is not None:
            try:
                eval_result = self._evaluation.evaluate(state)
                eval_result_dict = eval_result.as_dict()
                score = eval_result.score
                security_score = eval_result.security_score

                # Step 5: Quality gate
                if self._config.quality_gate_enabled and self._gate is not None:
                    try:
                        gate_report = self._gate.assert_pass(eval_result)
                    except Exception as gate_exc:
                        return PlatformResult(
                            success=False,
                            answer=answer,
                            score=score,
                            security_score=security_score,
                            trace_id=trace_id,
                            evaluation=eval_result_dict,
                            error=str(gate_exc),
                            error_type="EvaluationFailed",
                            metadata={"mode": effective_mode},
                        )

                    return PlatformResult(
                        success=True,
                        answer=answer,
                        score=score,
                        security_score=security_score,
                        trace_id=trace_id,
                        evaluation=eval_result_dict,
                        gate=gate_report,
                        metadata={"mode": effective_mode},
                    )
            except Exception as eval_exc:
                return PlatformResult(
                    success=False,
                    answer=answer,
                    trace_id=trace_id,
                    error=str(eval_exc),
                    error_type="EvaluationFailed",
                    metadata={"mode": effective_mode},
                )

        # No evaluation — return raw result
        return PlatformResult(
            success=True,
            answer=answer,
            trace_id=trace_id,
            metadata={"mode": effective_mode},
        )


def create_platform_service(
    *,
    config: PlatformConfig | None = None,
    workflow: Any | None = None,
) -> AIPlatformService:
    """One-shot convenience: create a fully wired AIPlatformService.

    Usage:
        service = create_platform_service()
        result = service.run("Hello world")
    """
    cfg = config or PlatformConfig.default()
    factory = PlatformFactory(cfg)

    runtime = factory.create_agent_runtime(workflow=workflow)
    eval_engine = factory.create_evaluation_engine() if cfg.evaluation_enabled else None
    gate = factory.create_quality_gate() if cfg.quality_gate_enabled else None

    return AIPlatformService(
        agent_runtime=runtime,
        evaluation_engine=eval_engine,
        quality_gate=gate,
        config=cfg,
    )
