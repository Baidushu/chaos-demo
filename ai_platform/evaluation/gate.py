from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from ai_platform.evaluation.result import EvaluationResult
from ai_platform.observability.collector import get_collector
from ai_platform.observability.event import GateEvent


class AgentGateError(Exception):
    """Raised when an evaluation report violates quality gate thresholds."""


@dataclass(slots=True)
class QualityGate:
    thresholds: dict[str, float]

    def check(self, evaluation_result: EvaluationResult | dict[str, Any]) -> bool:
        collector = get_collector()
        trace_id = ""
        if collector is not None and collector.active_trace is not None:
            trace_id = collector.active_trace.trace_id
            collector.record(GateEvent.check(trace_id, thresholds=dict(self.thresholds)))

        try:
            report = self._metrics(evaluation_result)
            self._assert(report)
            if collector is not None and collector.active_trace is not None:
                collector.record(
                    GateEvent.result(trace_id, passed=True, metrics=report)
                )
            return True
        except AgentGateError as exc:
            if collector is not None and collector.active_trace is not None:
                collector.record(
                    GateEvent.result(trace_id, passed=False, reasons=[str(exc)])
                )
            raise

    def assert_pass(self, evaluation_result: EvaluationResult | dict[str, Any]) -> dict[str, Any]:
        report = self._metrics(evaluation_result)
        self._assert(report)
        return report

    def _metrics(self, evaluation_result: EvaluationResult | dict[str, Any]) -> dict[str, Any]:
        if isinstance(evaluation_result, EvaluationResult):
            return dict(evaluation_result.metrics)
        return dict(evaluation_result)

    def _assert(self, report: dict[str, Any]) -> None:
        g = self.thresholds
        if report["tool_selection_accuracy"] < g["tool_selection_accuracy_min"]:
            raise AgentGateError(
                f"tool_selection_accuracy too low: {report['tool_selection_accuracy']:.2%} "
                f"(min {g['tool_selection_accuracy_min']:.2%})"
            )
        if report["arg_accuracy"] < g["arg_accuracy_min"]:
            raise AgentGateError(
                f"arg_accuracy too low: {report['arg_accuracy']:.2%} "
                f"(min {g['arg_accuracy_min']:.2%})"
            )
        if report["avg_tool_calls_per_task"] > g["avg_tool_calls_per_task_max"]:
            raise AgentGateError(
                f"avg_tool_calls_per_task too high: {report['avg_tool_calls_per_task']:.2f} "
                f"(max {g['avg_tool_calls_per_task_max']:.2f})"
            )
        if report["retry_rate"] > g["retry_rate_max"]:
            raise AgentGateError(
                f"retry_rate too high: {report['retry_rate']:.2%} "
                f"(max {g['retry_rate_max']:.2%})"
            )
        if report["hallucination_rate"] > g["hallucination_rate_max"]:
            raise AgentGateError(
                f"hallucination_rate too high: {report['hallucination_rate']:.2%} "
                f"(max {g['hallucination_rate_max']:.2%})"
            )
        if report.get("planner_invalid_rate", 0) > g["planner_invalid_rate_max"]:
            piv = report.get("planner_invalid_rate", 0)
            raise AgentGateError(
                f"planner_invalid_rate too high: {piv:.2%} "
                f"(max {g['planner_invalid_rate_max']:.2%})"
            )
