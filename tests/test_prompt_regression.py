"""P4 prompt 回归对比逻辑（不跑 subprocess、不依赖服务）。"""

import sys
from pathlib import Path

_SCRIPTS = Path(__file__).resolve().parents[1] / "agent-eval" / "scripts"
if str(_SCRIPTS) not in sys.path:
    sys.path.insert(0, str(_SCRIPTS))

from prompt_regression import compare_prompt_regression_scores  # noqa: E402


def _full_metrics(**overrides):
    base = {
        "tool_selection_accuracy": 0.9,
        "arg_accuracy": 0.85,
        "task_success_rate": 0.8,
        "retry_rate": 0.1,
        "avg_tool_calls_per_task": 1.5,
        "avg_token_per_task": 100.0,
        "hallucination_rate": 0.0,
        "planner_invalid_rate": 0.05,
    }
    base.update(overrides)
    return base


def test_compare_passes_when_identical():
    th = {
        "max_tool_selection_accuracy_drop": 0.0,
        "max_arg_accuracy_drop": 0.05,
        "max_retry_rate_surge": 0.15,
        "max_planner_invalid_rate_surge": 0.10,
    }
    b = _full_metrics()
    ok, reasons, delta = compare_prompt_regression_scores(b, dict(b), th)
    assert ok
    assert not reasons
    for k, v in delta.items():
        assert v == 0.0


def test_compare_fails_on_tool_accuracy_drop():
    th = {
        "max_tool_selection_accuracy_drop": 0.02,
        "max_arg_accuracy_drop": 0.05,
        "max_retry_rate_surge": 0.15,
        "max_planner_invalid_rate_surge": 0.10,
    }
    b = _full_metrics(tool_selection_accuracy=0.9)
    c = _full_metrics(tool_selection_accuracy=0.85)
    ok, reasons, _ = compare_prompt_regression_scores(b, c, th)
    assert not ok
    assert any("tool_selection_accuracy" in r for r in reasons)


def test_compare_fails_on_retry_surge():
    th = {
        "max_tool_selection_accuracy_drop": 0.0,
        "max_arg_accuracy_drop": 0.05,
        "max_retry_rate_surge": 0.05,
        "max_planner_invalid_rate_surge": 0.10,
    }
    b = _full_metrics(retry_rate=0.1)
    c = _full_metrics(retry_rate=0.2)
    ok, reasons, _ = compare_prompt_regression_scores(b, c, th)
    assert not ok
    assert any("retry_rate" in r for r in reasons)
