from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Literal


AgentStatus = Literal["new", "running", "succeeded", "failed"]


@dataclass(slots=True)
class AgentState:
    request: Any = None
    plan: Any = None
    tool_result: list[dict[str, Any]] = field(default_factory=list)
    llm_call: list[dict[str, Any]] = field(default_factory=list)
    answer: Any = None
    error: dict[str, Any] | None = None
    status: AgentStatus = "new"
    metadata: dict[str, Any] = field(default_factory=dict)

    def mark_running(self) -> None:
        self.status = "running"

    def mark_succeeded(self) -> None:
        self.status = "succeeded"

    def mark_failed(self) -> None:
        self.status = "failed"

    def set_plan(self, plan: Any) -> None:
        self.plan = plan
        self.metadata["has_plan"] = True

    def set_answer(self, answer: Any) -> None:
        self.answer = answer
        self.metadata["has_answer"] = True

    def set_error(self, error: Exception | str) -> None:
        if isinstance(error, Exception):
            self.error = {
                "type": type(error).__name__,
                "message": str(error),
            }
        else:
            self.error = {
                "type": "Error",
                "message": str(error),
            }

    def add_llm_call(
        self,
        *,
        provider: str,
        model: str,
        prompt: str | None = None,
        response: str | None = None,
        latency_ms: float | None = None,
        error: str | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> None:
        entry: dict[str, Any] = {
            "provider": provider,
            "model": model,
        }
        if prompt is not None:
            entry["prompt"] = prompt
        if response is not None:
            entry["response"] = response
        if latency_ms is not None:
            entry["latency_ms"] = latency_ms
        if error is not None:
            entry["error"] = error
        if metadata:
            entry["metadata"] = dict(metadata)
        self.llm_call.append(entry)

    def add_tool_result(
        self,
        *,
        tool: str,
        result: Any,
        error: str | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> None:
        entry: dict[str, Any] = {
            "tool": tool,
            "result": result,
        }
        if error is not None:
            entry["error"] = error
        if metadata:
            entry["metadata"] = dict(metadata)
        self.tool_result.append(entry)

    def as_dict(self) -> dict[str, Any]:
        return {
            "request": self.request,
            "plan": self.plan,
            "tool_result": list(self.tool_result),
            "llm_call": list(self.llm_call),
            "answer": self.answer,
            "error": dict(self.error) if self.error is not None else None,
            "status": self.status,
            "metadata": dict(self.metadata),
        }
