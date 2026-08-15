from __future__ import annotations

import importlib.util
import os
import sys
from functools import lru_cache
from pathlib import Path
from typing import Any, Callable

from ai_platform.agent.context import AgentContext
from ai_platform.agent.state import AgentState
from ai_platform.workflow.node import BaseNode


PlannerFunc = Callable[[str], tuple[dict[str, Any], dict[str, Any]]]
RulePlannerFunc = Callable[[str], dict[str, Any]]
ValidatePlannerFunc = Callable[[dict[str, Any]], dict[str, Any]]


class PlannerNode(BaseNode):
    name = "planner"

    def __init__(
        self,
        *,
        planner: PlannerFunc | None = None,
        rule_planner: RulePlannerFunc | None = None,
        validator: ValidatePlannerFunc | None = None,
        agent_mode: str | None = None,
    ) -> None:
        legacy = _load_legacy_agent_eval_module()
        self._planner = planner or legacy.plan_with_ollama
        self._rule_planner = rule_planner or legacy.rule_plan
        self._validator = validator or legacy.validate_plan
        self._agent_mode = agent_mode
        self._planner_model = os.getenv("LLM_GATEWAY_MODEL", "").strip() or os.getenv(
            "OLLAMA_MODEL", "qwen2.5:7b"
        )

    def execute(self, state: AgentState, context: AgentContext) -> AgentState:
        text = _request_text(state.request)
        selected_mode = self._agent_mode or str(
            state.metadata.get("agent_mode") or os.getenv("AGENT_MODE", "rule")
        )
        planner_fallback = False
        llm_meta = {
            "llm_prompt_tokens": None,
            "llm_completion_tokens": None,
            "llm_total_tokens": None,
        }

        use_llm = selected_mode in ("ollama", "llm")
        if use_llm:
            try:
                plan, llm_meta = self._planner(text)
                state.add_llm_call(
                    provider=os.getenv("LLM_GATEWAY_PROVIDER", "ollama_generate"),
                    model=self._planner_model,
                    prompt=text,
                    metadata={
                        "caller": context.caller or "planner_node",
                        **llm_meta,
                    },
                )
            except Exception:
                plan = self._rule_planner(text)
                planner_fallback = True
        else:
            plan = self._rule_planner(text)

        if use_llm:
            before_valid = bool(plan.get("_planner_valid", True))
            plan = self._validator(plan)
            if not before_valid or not plan.get("_planner_valid", True):
                planner_fallback = True
                plan = {
                    "tool": "ask_user",
                    "args": {"reason": "planner output invalid"},
                    "_planner_valid": False,
                }

        state.set_plan(plan)
        state.metadata["agent_mode"] = selected_mode
        state.metadata["planner_valid"] = bool(plan.get("_planner_valid", True))
        state.metadata["planner_fallback"] = planner_fallback
        state.metadata["llm_meta"] = dict(llm_meta)
        return state


def _request_text(request: Any) -> str:
    if isinstance(request, str):
        return request
    if isinstance(request, dict):
        return str(request.get("input", ""))
    return str(request)


@lru_cache(maxsize=1)
def _load_legacy_agent_eval_module():
    repo_root = Path(__file__).resolve().parents[3]
    script_path = repo_root / "agent-eval" / "scripts" / "run_agent_eval.py"
    scripts_dir = script_path.parent
    if str(scripts_dir) not in sys.path:
        sys.path.insert(0, str(scripts_dir))
    spec = importlib.util.spec_from_file_location("phase2_run_agent_eval", script_path)
    if spec is None or spec.loader is None:  # pragma: no cover - defensive load path
        raise RuntimeError(f"Cannot load legacy agent eval module: {script_path}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module
