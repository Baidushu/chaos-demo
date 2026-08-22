"""声明式混沌实验定义的加载校验与稳态裁决测试（不起服务、不跑实验）。

守护三条线：
1. 仓库内置 agent-eval/experiments/mixed_fault.yaml 始终合法（防漂移进 CI）；
2. 加载器对未知键/缺段/非法值 fail-fast；
3. evaluate_steady_state 的裁决语义（底线越界即 FAIL）。
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

_SCRIPTS = Path(__file__).resolve().parents[2] / "agent-eval" / "scripts"
if str(_SCRIPTS) not in sys.path:
    sys.path.insert(0, str(_SCRIPTS))

from run_experiment import (  # noqa: E402
    ExperimentDefinitionError,
    evaluate_steady_state,
    load_experiment,
)

REPO_EXPERIMENT = _SCRIPTS.parent / "experiments" / "mixed_fault.yaml"


# ---------------------------------------------------------------------------
# 1. 内置实验定义合法性（CI 漂移守护）
# ---------------------------------------------------------------------------
def test_repo_experiment_definition_is_valid():
    exp = load_experiment(REPO_EXPERIMENT)
    assert exp["name"] == "mixed-fault-tool-stability"
    assert exp["version"] == 1
    assert exp["method"]["mode"] == "rule"
    assert exp["method"]["experiment"]["chaos"] == "mixed"
    assert exp["steady_state"]["tool_selection_accuracy_min"] == 0.95
    assert "token_surge_max" in exp["tolerance"]


def test_bad_mode_rejected(tmp_path):
    content = VALID_MINIMAL.replace("method:", "method:\n  mode: psychic\n")
    with pytest.raises(ExperimentDefinitionError, match="method.mode"):
        load_experiment(_write(tmp_path, content))


# ---------------------------------------------------------------------------
# 2. 加载与校验
# ---------------------------------------------------------------------------
def _write(tmp_path: Path, content: str) -> Path:
    path = tmp_path / "exp.yaml"
    path.write_text(content, encoding="utf-8")
    return path


VALID_MINIMAL = """
version: 1
name: minimal
steady_state:
  tool_selection_accuracy_min: 0.9
  arg_accuracy_min: 0.9
  retry_rate_max: 0.1
method:
  experiment:
    chaos: latency
    fail_rate: 0.1
    latency_ms: 50
tolerance:
  token_surge_max: 0.3
"""


def test_load_minimal_definition(tmp_path):
    exp = load_experiment(_write(tmp_path, VALID_MINIMAL))
    assert exp["method"]["experiment"]["chaos"] == "latency"
    assert exp["tolerance"] == {"token_surge_max": 0.3}


def test_missing_file_raises(tmp_path):
    with pytest.raises(ExperimentDefinitionError, match="not found"):
        load_experiment(tmp_path / "nope.yaml")


def test_unknown_top_level_key_rejected(tmp_path):
    path = _write(tmp_path, VALID_MINIMAL + "\nunknown_section: 1\n")
    with pytest.raises(ExperimentDefinitionError, match="unknown top-level keys"):
        load_experiment(path)


def test_missing_steady_state_rejected(tmp_path):
    content = VALID_MINIMAL.replace("steady_state:\n  tool_selection_accuracy_min: 0.9\n  arg_accuracy_min: 0.9\n  retry_rate_max: 0.1\n", "")
    with pytest.raises(ExperimentDefinitionError, match="steady_state"):
        load_experiment(_write(tmp_path, content))


def test_missing_steady_state_threshold_rejected(tmp_path):
    content = VALID_MINIMAL.replace("  retry_rate_max: 0.1\n", "")
    with pytest.raises(ExperimentDefinitionError, match="retry_rate_max is required"):
        load_experiment(_write(tmp_path, content))


def test_unknown_tolerance_key_rejected(tmp_path):
    path = _write(tmp_path, VALID_MINIMAL + "  retry_tax_maxx: 1.0\n")
    with pytest.raises(ExperimentDefinitionError, match="unknown keys in tolerance"):
        load_experiment(path)


def test_bad_chaos_mode_rejected(tmp_path):
    content = VALID_MINIMAL.replace("chaos: latency", "chaos: nuclear")
    with pytest.raises(ExperimentDefinitionError, match="latency\\|error\\|mixed"):
        load_experiment(_write(tmp_path, content))


def test_non_numeric_threshold_rejected(tmp_path):
    content = VALID_MINIMAL.replace("token_surge_max: 0.3", "token_surge_max: lots")
    with pytest.raises(ExperimentDefinitionError, match="must be numeric"):
        load_experiment(_write(tmp_path, content))


def test_unsupported_version_rejected(tmp_path):
    content = VALID_MINIMAL.replace("version: 1", "version: 2")
    with pytest.raises(ExperimentDefinitionError, match="unsupported version"):
        load_experiment(_write(tmp_path, content))


# ---------------------------------------------------------------------------
# 3. 稳态裁决语义
# ---------------------------------------------------------------------------
def test_steady_state_pass_when_all_thresholds_met():
    baseline = {"tool_selection_accuracy": 1.0, "arg_accuracy": 0.99, "retry_rate": 0.0}
    steady = {"tool_selection_accuracy_min": 0.95, "arg_accuracy_min": 0.95, "retry_rate_max": 0.05}
    ok, reasons = evaluate_steady_state(baseline, steady)
    assert ok and reasons == []


def test_steady_state_fails_when_accuracy_below_floor():
    baseline = {"tool_selection_accuracy": 0.90, "arg_accuracy": 0.99, "retry_rate": 0.0}
    steady = {"tool_selection_accuracy_min": 0.95}
    ok, reasons = evaluate_steady_state(baseline, steady)
    assert not ok
    assert any("tool_selection_accuracy" in r for r in reasons)


def test_steady_state_fails_when_retry_above_ceiling():
    baseline = {"retry_rate": 0.12}
    steady = {"retry_rate_max": 0.05}
    ok, reasons = evaluate_steady_state(baseline, steady)
    assert not ok
    assert any("retry_rate" in r for r in reasons)


def test_steady_state_missing_metric_reported():
    ok, reasons = evaluate_steady_state({}, {"tool_selection_accuracy_min": 0.95})
    assert not ok
    assert any("缺少指标" in r for r in reasons)
