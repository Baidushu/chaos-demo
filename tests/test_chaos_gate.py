"""Token 黑洞门禁单测：覆盖实测通过/病态放大/小样本跳过/主门禁四类场景。"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "agent-eval" / "scripts"))

from chaos_compare import evaluate_token_black_hole_gate  # noqa: E402

# 与默认阈值一致（chaos_compare.main 中 os.getenv 的默认值）
DEFAULTS = dict(
    token_surge_max=0.30,
    token_max_per_task_max=500.0,
    token_p99_per_task_max=300.0,
    retry_surge_max=0.25,
    fail_path_surge_max=0.50,
    retry_path_surge_max=0.60,
    retry_tax_max=1.50,
)


def _runs(**chaos_overrides):
    """构造一次真实评测的 baseline/chaos 摘要（数值取自实测报告）。"""
    baseline = {
        "avg_token_per_task": 109.36,
        "max_token_per_task": 199,
        "p99_token_per_task": 187.0,
        "retry_rate": 0.0,
        "retry_case_count": 0,
        "avg_token_rule_fail": None,
        "avg_token_with_retry": None,
        "avg_token_no_retry": 109.36,
    }
    chaos = {
        "avg_token_per_task": 113.63,
        "max_token_per_task": 207,
        "p99_token_per_task": 196.0,
        "retry_rate": 0.125,
        "retry_case_count": 7,
        "avg_token_rule_fail": None,
        "avg_token_with_retry": 174.71,
        "avg_token_no_retry": 104.90,
    }
    chaos.update(chaos_overrides)
    return baseline, chaos


def test_real_observed_run_passes_with_new_defaults():
    """实测 ~66.56% 重试税在新默认阈值 1.50 下通过（旧值 0.60 会误杀）。"""
    gate = evaluate_token_black_hole_gate(*_runs(), **DEFAULTS)
    assert gate["chaos_retry_tax_ratio"] == pytest.approx(0.6656, abs=1e-3)
    assert gate["retry_tax_pass"] is True
    assert gate["pass"] is True


def test_pathological_retry_tax_fails():
    """无界重试的病态放大（+200%）必须被拦截。"""
    baseline, chaos = _runs(
        avg_token_with_retry=314.7,  # (314.7-104.9)/104.9 ≈ 200%
    )
    gate = evaluate_token_black_hole_gate(baseline, chaos, **DEFAULTS)
    assert gate["retry_tax_pass"] is False
    assert gate["pass"] is False


def test_small_retry_sample_skips_tax_gate():
    """重试样本 < 5 条时比值方差大，跳过税门禁避免小样本误杀。"""
    baseline, chaos = _runs(retry_case_count=3)
    gate = evaluate_token_black_hole_gate(baseline, chaos, **DEFAULTS)
    assert gate["retry_tax_pass"] is True
    assert gate["retry_tax_skipped"] == "insufficient_samples(3<5)"
    assert gate["pass"] is True


def test_primary_token_surge_gate_enforced():
    """主门禁：混沌 vs 基线的平均 token 增幅超过 30% 必须 FAIL。"""
    baseline, chaos = _runs(avg_token_per_task=200.0)
    gate = evaluate_token_black_hole_gate(baseline, chaos, **DEFAULTS)
    assert gate["token_surge_ratio"] > 0.30
    assert gate["token_surge_pass"] is False
    assert gate["pass"] is False


def test_retry_tax_max_still_configurable():
    """阈值仍可收紧：自定义 0.50 时实测 66.56% 应失败（CI 可调严）。"""
    gate = evaluate_token_black_hole_gate(*_runs(), **{**DEFAULTS, "retry_tax_max": 0.50})
    assert gate["retry_tax_pass"] is False
    assert gate["pass"] is False
