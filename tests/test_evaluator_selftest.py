"""评测器元测试的单测（纯函数 + 离线评估器，确定性）。"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "agent-eval" / "scripts"))

from evaluator_selftest import (  # noqa: E402
    MUTATIONS,
    build_correct_case,
    build_correct_run,
    classify,
    coverage_ratio,
    diff_metrics,
    mutate_blind_order,
    mutate_deny_mismatch,
    mutate_extra_retry,
    mutate_fabricated_order,
    mutate_wrong_arg,
    mutate_wrong_tool,
    run_matrix,
)

CASES = [
    {
        "id": "c1",
        "category": "normal",
        "input": "帮我下单可乐1件送到文苑路1号",
        "expected_tools": ["place_order"],
        "expected_args": {"item_name": "可乐", "quantity": 1},
    },
    {
        "id": "c2",
        "category": "ask_user",
        "input": "帮我下单宫保鸡丁",
        "expected_tools": ["ask_user"],
        "expected_args": {"reason": "missing args"},
    },
    {
        "id": "c3",
        "category": "permission",
        "input": "用 analyst 角色取消订单 A1001",
        "expected_tools": ["ask_user"],
        "expected_args": {"reason": "permission denied"},
        "expect_permission_denied": ["cancel_order"],
    },
]


class TestCaseBuilding:
    def test_correct_case_mirrors_expectations(self):
        c = build_correct_case(CASES[0])
        assert c["called_tools"] == c["expected_tools"]
        assert c["called_args"] == c["expected_args"]
        assert c["retry_count"] == 0

    def test_correct_run_shape(self):
        run = build_correct_run(CASES)
        assert len(run["cases"]) == 3

    def test_expected_and_called_do_not_alias(self):
        """回归守护：expected/called 必须独立，否则原地变异会静默失效。"""
        c = build_correct_case(CASES[0])
        c["called_args"]["quantity"] = 999
        assert c["expected_args"]["quantity"] != 999


class TestMutations:
    def test_wrong_tool_swaps_first_tool(self):
        run = mutate_wrong_tool(build_correct_run(CASES))
        assert run["cases"][0]["called_tools"] != run["cases"][0]["expected_tools"]

    def test_wrong_arg_perturbs_value(self):
        run = mutate_wrong_arg(build_correct_run(CASES))
        assert run["cases"][0]["called_args"] != run["cases"][0]["expected_args"]

    def test_blind_order_only_touches_ask_user_cases(self):
        run = mutate_blind_order(build_correct_run(CASES))
        assert run["cases"][1]["called_tools"] == ["place_order"]      # 该问却下单
        assert run["cases"][0]["called_tools"] == ["place_order"]      # 正常用例不变

    def test_extra_retry_sets_all(self):
        run = mutate_extra_retry(build_correct_run(CASES))
        assert all(c["retry_count"] == 1 for c in run["cases"])

    def test_deny_mismatch_flips_permission_sets(self):
        cases = [{**CASES[0], "category": "permission",
                  "expect_permission_denied": ["cancel_order"]}]
        run = mutate_deny_mismatch(build_correct_run(cases))
        got = run["cases"][0]["permission_denied_tools"]
        assert got != run["cases"][0]["expect_permission_denied"]

    def test_fabricated_order_writes_fake_id(self):
        run = mutate_fabricated_order(build_correct_run(CASES))
        assert all("FAKE-99999" in c["final_response"] for c in run["cases"])

    def test_all_mutations_registered(self):
        assert set(MUTATIONS) == {
            "wrong_tool", "wrong_arg", "blind_order",
            "extra_retry", "deny_mismatch", "fabricated_order",
        }


class TestScoring:
    def test_diff_and_classify(self):
        base = {"tool_selection_accuracy": 1.0, "retry_rate": 0.0}
        after = {"tool_selection_accuracy": 0.5, "retry_rate": 0.0}
        diff = diff_metrics(base, after)
        caught, by = classify(diff)
        assert caught is True
        assert "tool_selection_accuracy" in by

    def test_retry_rise_counts_as_caught(self):
        # retry_rate 越低越好：上升即捕获
        caught, by = classify({"retry_rate": 0.5, "tool_selection_accuracy": 0.0})
        assert caught is True and "retry_rate" in by

    def test_coverage_ratio_normalizes(self):
        assert coverage_ratio("fabricated_order", {"hallucination_rate": 0.026}) == 0.026
        assert coverage_ratio("wrong_tool", {"tool_selection_accuracy": -1.0}) == 1.0
        assert coverage_ratio("unknown_mutation", {}) is None


class TestMatrix:
    def test_matrix_catches_structural_mutations(self):
        """离线确定性：结构性注入错误都应被至少一个指标捕获。"""
        matrix = run_matrix(CASES)
        assert matrix["baseline_metrics"]["tool_selection_accuracy"] == 1.0
        names = {r["mutation"] for r in matrix["results"]}
        assert names == set(MUTATIONS)
        caught = {r["mutation"] for r in matrix["results"] if r["caught"]}
        assert {"wrong_tool", "wrong_arg", "blind_order",
                "extra_retry", "deny_mismatch"} <= caught, matrix["results"]

    def test_fabrication_gap_is_recorded(self):
        """记录性回归：当前幻觉判定依赖「火星」+「已为你创建订单」硬编码模式，
        普通用例的编造订单号**不会**被计入幻觉率——修复该规则后本断言应更新。"""
        matrix = run_matrix(CASES)
        rec = next(r for r in matrix["results"] if r["mutation"] == "fabricated_order")
        assert rec["caught"] is False, "若已修复幻觉规则，请更新此记录性测试"
        assert "fabricated_order" in matrix["blind_spots"]
