"""agent-eval 配置解析（不跑评测、不依赖服务）。"""

import sys
from pathlib import Path

_SCRIPTS = Path(__file__).resolve().parents[1] / "agent-eval" / "scripts"
if str(_SCRIPTS) not in sys.path:
    sys.path.insert(0, str(_SCRIPTS))

from judge_local import load_gate_thresholds, load_judge_sampling_config, load_prompt_regression_thresholds  # noqa: E402


def test_load_gate_thresholds_matches_yaml():
    g = load_gate_thresholds()
    assert g["tool_selection_accuracy_min"] == 0.85
    assert g["arg_accuracy_min"] == 0.80
    assert g["avg_tool_calls_per_task_max"] == 3.5
    assert g["retry_rate_max"] == 0.20
    assert g["hallucination_rate_max"] == 0.10
    assert g["planner_invalid_rate_max"] == 0.15


def test_load_judge_sampling_config():
    enabled, rate = load_judge_sampling_config()
    assert enabled is True
    assert rate == 0.2


def test_load_prompt_regression_thresholds():
    t = load_prompt_regression_thresholds()
    assert t["max_tool_selection_accuracy_drop"] == 0.0
    assert t["max_arg_accuracy_drop"] == 0.05
    assert t["max_retry_rate_surge"] == 0.15
    assert t["max_planner_invalid_rate_surge"] == 0.10
