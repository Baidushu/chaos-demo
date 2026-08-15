from __future__ import annotations

import time
from dataclasses import dataclass, field
from typing import Any

from ai_platform.observability.collector import get_collector
from ai_platform.observability.event import ToolEvent
from ai_platform.observability.trace import SpanStatus
from ai_platform.security.permission import PermissionChecker
from ai_platform.security.policy import SecurityPolicy
from ai_platform.security.security_event import SecurityEvent
from ai_platform.tools.base import BaseTool
from ai_platform.tools.registry import ToolRegistry


class ToolExecutionError(Exception):
    """Base tool execution error."""


class ToolNotFoundError(ToolExecutionError):
    """Raised when the requested tool is not registered."""


class ToolValidationError(ToolExecutionError):
    """Raised when tool params do not satisfy the declared schema."""


class ToolPermissionError(ToolExecutionError):
    """Raised when a tool is blocked by security policy."""


@dataclass(slots=True)
class ToolExecutionResult:
    tool: str
    ok: bool
    result: Any = None
    error: str | None = None
    attempts: list[dict[str, Any]] = field(default_factory=list)
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass(slots=True)
class ToolExecutor:
    registry: ToolRegistry
    metadata: dict[str, Any] = field(default_factory=dict)
    security: PermissionChecker | SecurityPolicy | None = None

    def register(self, tool: BaseTool) -> None:
        self.registry.register(tool)

    def get(self, name: str) -> BaseTool | None:
        return self.registry.get(name)

    def list_tools(self) -> list[str]:
        return self.registry.list_tools()

    def execute(
        self,
        tool_name: str,
        params: dict[str, Any] | None,
        *,
        context: Any | None = None,
    ) -> ToolExecutionResult:
        collector = get_collector()
        span = None
        trace_id = ""
        if collector is not None and collector.active_trace is not None:
            trace_id = collector.active_trace.trace_id
            span = collector.create_span(f"tool.{tool_name}", attributes={"tool": tool_name})
            collector.record(
                ToolEvent.call(trace_id, span.span_id, tool_name=tool_name, params=params)
            )
            collector.counter("tool.call.count").inc()
            collector.counter(f"tool.{tool_name}.count").inc()

        # --- Security: permission check ---
        perm_checker = self._resolve_permission()
        if perm_checker is not None:
            perm_result = perm_checker.check(tool_name)
            if not perm_result.passed:
                self._record_permission_block(collector, trace_id, perm_result, tool_name)
                return ToolExecutionResult(
                    tool=tool_name,
                    ok=False,
                    error=f"Tool blocked: {', '.join(perm_result.violations)}",
                    metadata={"security": perm_result.as_dict()},
                )

        start_time = time.perf_counter()
        try:
            tool = self._require_tool(tool_name)
            validated = self._validate_params(tool, params or {})
            raw = tool.execute(validated, context=context)
            duration_ms = (time.perf_counter() - start_time) * 1000
            if isinstance(raw, ToolExecutionResult):
                result = raw
            else:
                result = ToolExecutionResult(
                    tool=tool_name,
                    ok=True,
                    result=raw,
                    attempts=[{"tool": tool_name, "result": raw}],
                )
            if span is not None and collector is not None:
                span.finish(status=SpanStatus.OK if result.ok else SpanStatus.ERROR)
                collector.record(
                    ToolEvent.result(
                        trace_id,
                        span.span_id,
                        tool_name=tool_name,
                        ok=result.ok,
                        duration_ms=duration_ms,
                        result=result.result,
                        error=result.error,
                    )
                )
                if not result.ok:
                    collector.counter("tool.error.count").inc()
            return result
        except ToolExecutionError as exc:
            duration_ms = (time.perf_counter() - start_time) * 1000
            if span is not None and collector is not None:
                span.finish(status=SpanStatus.ERROR)
                collector.record(
                    ToolEvent.result(
                        trace_id,
                        span.span_id,
                        tool_name=tool_name,
                        ok=False,
                        duration_ms=duration_ms,
                        error=str(exc),
                    )
                )
                collector.counter("tool.error.count").inc()
            return ToolExecutionResult(
                tool=tool_name,
                ok=False,
                error=str(exc),
                metadata={"response_text": "参数不足或请求不合理，请补充信息。"},
            )
        except Exception as exc:  # pragma: no cover - defensive path
            duration_ms = (time.perf_counter() - start_time) * 1000
            if span is not None and collector is not None:
                span.finish(status=SpanStatus.ERROR)
                collector.record(
                    ToolEvent.result(
                        trace_id,
                        span.span_id,
                        tool_name=tool_name,
                        ok=False,
                        duration_ms=duration_ms,
                        error=str(exc),
                    )
                )
                collector.counter("tool.error.count").inc()
            return ToolExecutionResult(
                tool=tool_name,
                ok=False,
                error=str(exc),
                metadata={"response_text": "参数不足或请求不合理，请补充信息。"},
            )

    def _require_tool(self, name: str) -> BaseTool:
        tool = self.registry.get(name)
        if tool is None:
            raise ToolNotFoundError(f"Tool not registered: {name}")
        return tool

    def _validate_params(self, tool: BaseTool, params: dict[str, Any]) -> dict[str, Any]:
        if not isinstance(params, dict):
            raise ToolValidationError("Tool params must be a dict")

        for field_name, spec in tool.schema.items():
            required = bool(spec.get("required", False))
            expected_type = spec.get("type")
            if required and field_name not in params:
                raise ToolValidationError(f"Missing required param: {field_name}")
            if field_name in params and expected_type is not None and not isinstance(
                params[field_name], expected_type
            ):
                expected_name = getattr(expected_type, "__name__", str(expected_type))
                actual_name = type(params[field_name]).__name__
                raise ToolValidationError(
                    f"Param '{field_name}' expected {expected_name}, got {actual_name}"
                )
        return params

    def _resolve_permission(self) -> PermissionChecker | None:
        if self.security is None:
            return None
        if isinstance(self.security, PermissionChecker):
            return self.security
        if isinstance(self.security, SecurityPolicy):
            return PermissionChecker(self.security)
        return None

    @staticmethod
    def _record_permission_block(
        collector, trace_id: str, perm_result, tool_name: str,
    ) -> None:
        if collector is None:
            return
        collector.record(
            SecurityEvent.block_event(
                check_name=perm_result.check_name,
                risk_level=perm_result.risk_level,
                violations=perm_result.violations,
                trace_id=trace_id or "",
                metadata={"tool_name": tool_name},
            )
        )
        collector.counter("security.block.count").inc()
        collector.counter(f"security.{perm_result.check_name}.block_count").inc()
        collector.counter("tool.blocked.count").inc()
