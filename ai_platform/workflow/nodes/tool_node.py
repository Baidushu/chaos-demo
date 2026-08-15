from __future__ import annotations

import os
from typing import Any

from ai_platform.agent.context import AgentContext
from ai_platform.agent.state import AgentState
from ai_platform.tools.executor import ToolExecutor
from ai_platform.tools.legacy_tool import build_legacy_registry
from ai_platform.tools.registry import ToolRegistry
from ai_platform.workflow.node import BaseNode


class ToolNode(BaseNode):
    name = "tool"

    def __init__(
        self,
        *,
        executor: ToolExecutor | None = None,
        registry: ToolRegistry | None = None,
        tools_client: Any | None = None,
        max_retry: int | None = None,
    ) -> None:
        retries = max_retry if max_retry is not None else int(os.getenv("AGENT_MAX_RETRY", "2"))
        if executor is not None:
            self._executor = executor
        else:
            active_registry = registry or build_legacy_registry(
                tools_client=tools_client,
                max_retry=retries,
            )
            chaos_mode = getattr(tools_client, "chaos_mode", "none") if tools_client is not None else "none"
            self._executor = ToolExecutor(
                registry=active_registry,
                metadata={"chaos_mode": chaos_mode},
            )

    def execute(self, state: AgentState, context: AgentContext) -> AgentState:
        plan = state.plan
        if not isinstance(plan, dict):
            raise ValueError("AgentState.plan must be a dict before ToolNode executes")

        steps = plan.get("steps") if plan.get("tool") == "workflow" else [plan]
        called_tools: list[str] = []
        called_args: dict[str, Any] = {}
        retry_count = 0
        final_response = "已处理。"

        for step in steps:
            tool = step.get("tool", "ask_user")
            args = step.get("args", {})
            called_tools.append(tool)
            if isinstance(args, dict):
                called_args.update(args)

            execution = self._executor.execute(tool, args if isinstance(args, dict) else {}, context=context)
            if execution.attempts:
                for attempt in execution.attempts:
                    state.add_tool_result(
                        tool=str(attempt.get("tool", tool)),
                        result=attempt.get("result"),
                        error=attempt.get("error"),
                    )
            else:
                state.add_tool_result(tool=tool, result=execution.result, error=execution.error)

            retry_count += int(execution.metadata.get("retry_count", 0) or 0)
            final_response = str(execution.metadata.get("response_text", final_response))

        state.set_answer(final_response)
        llm_meta = state.metadata.get("llm_meta", {})
        llm_total = llm_meta.get("llm_total_tokens")
        token_usage_estimated = max(
            60,
            len(_request_text(state.request)) * 3
            + len(final_response) * 2
            + retry_count * 25
            + len(called_tools) * 30,
        )
        prefer = os.getenv("TOKEN_METRIC", "auto").lower()
        if prefer == "estimated":
            token_usage = token_usage_estimated
            token_usage_source = "estimated"
        elif prefer == "llm":
            token_usage = int(llm_total) if llm_total is not None else token_usage_estimated
            token_usage_source = "ollama" if llm_total is not None else "estimated_fallback"
        else:
            if llm_total is not None:
                token_usage = int(llm_total)
                token_usage_source = "ollama"
            else:
                token_usage = token_usage_estimated
                token_usage_source = "estimated"

        state.metadata.update(
            {
                "called_tools": called_tools,
                "called_args": called_args,
                "retry_count": retry_count,
                "tool_calls_count": len(called_tools),
                "token_usage": token_usage,
                "token_usage_estimated": token_usage_estimated,
                "token_usage_llm": llm_total,
                "token_usage_source": token_usage_source,
                "llm_prompt_tokens": llm_meta.get("llm_prompt_tokens"),
                "llm_completion_tokens": llm_meta.get("llm_completion_tokens"),
                "chaos_mode": self._executor.metadata.get("chaos_mode", "none"),
            }
        )
        return state


def _request_text(request: Any) -> str:
    if isinstance(request, str):
        return request
    if isinstance(request, dict):
        return str(request.get("input", ""))
    return str(request)
