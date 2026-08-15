from __future__ import annotations

import importlib.util
import sys
from functools import lru_cache
from pathlib import Path
from typing import Any, Callable

from ai_platform.agent.context import AgentContext
from ai_platform.agent.state import AgentState
from ai_platform.workflow.node import BaseNode


JudgeFunc = Callable[[str, str, str], str]


class JudgeNode(BaseNode):
    name = "judge"

    def __init__(self, *, judge: JudgeFunc | None = None, enabled: bool = True) -> None:
        legacy = _load_legacy_judge_module()
        self._judge = judge or legacy.local_llm_judge
        self._enabled = enabled

    def execute(self, state: AgentState, context: AgentContext) -> AgentState:
        if not self._enabled:
            state.metadata["judge_enabled"] = False
            return state

        user_input = _request_text(state.request)
        expected = _expected_text(state.request)
        actual = _actual_text(state.answer)
        result = self._judge(user_input, expected, actual)
        state.metadata["judge_enabled"] = True
        state.metadata["judge_result"] = result
        return state


def _request_text(request: Any) -> str:
    if isinstance(request, str):
        return request
    if isinstance(request, dict):
        return str(request.get("input", ""))
    return str(request)


def _expected_text(request: Any) -> str:
    if isinstance(request, dict):
        if "judge_expected" in request:
            return str(request["judge_expected"])
        expected_tools = request.get("expected_tools")
        expected_args = request.get("expected_args")
        if expected_tools is not None or expected_args is not None:
            return f"expected_tools={expected_tools}, expected_args={expected_args}"
    return ""


def _actual_text(answer: Any) -> str:
    if answer is None:
        return ""
    return str(answer)


@lru_cache(maxsize=1)
def _load_legacy_judge_module():
    repo_root = Path(__file__).resolve().parents[3]
    script_path = repo_root / "agent-eval" / "scripts" / "judge_local.py"
    scripts_dir = script_path.parent
    if str(scripts_dir) not in sys.path:
        sys.path.insert(0, str(scripts_dir))
    spec = importlib.util.spec_from_file_location("phase2_judge_local", script_path)
    if spec is None or spec.loader is None:  # pragma: no cover - defensive load path
        raise RuntimeError(f"Cannot load legacy judge module: {script_path}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module
