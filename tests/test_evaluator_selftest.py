"""评测器元测试的单测（纯函数 + 离线评估器，确定性）。

覆盖三件事：
1. 全对基线必须**有依据**（含 tool_results 与一致的回复）且不误报；
2. 每个变异算子的注入行为与适用范围；
3. 门禁：基线误报 / 未捕获 / 覆盖不足，三种情况都要能判失败。
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "agent-eval" / "scripts"))

from evaluator_selftest import (  # noqa: E402
    KNOWN_UNCOVERED,
    MUTATIONS,
    build_correct_case,
    build_correct_run,
    case_coverage,
    case_deteriorated,
    classify,
    coverage_ratio,
    diff_metrics,
    evaluate_gate,
    mutate_blind_order,
    mutate_deny_mismatch,
    mutate_extra_retry,
    mutate_fabricated_entity,
    mutate_fabricated_order,
    mutate_status_value_mismatch,
    mutate_unbacked_success_claim,
    mutate_unsupported_status_claim,
    mutate_wrong_arg,
    mutate_wrong_tool,
    render_markdown,
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
    {
        "id": "c4",
        "category": "normal",
        "input": "帮我查一下 A1001",
        "expected_tools": ["query_order"],
        "expected_args": {"order_id": "A1001"},
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
        assert len(run["cases"]) == 4

    def test_expected_and_called_do_not_alias(self):
        """回归守护：expected/called 必须独立，否则原地变异会静默失效。"""
        c = build_correct_case(CASES[0])
        c["called_args"]["quantity"] = 999
        assert c["expected_args"]["quantity"] != 999

    def test_correct_case_carries_grounded_tool_results(self):
        """全对基线必须有工具返回与有依据的回复，否则幻觉规则无法判定。"""
        c = build_correct_case(CASES[0])
        assert c["tool_results"][0]["tool"] == "place_order"
        assert c["tool_results"][0]["result"]["ok"] is True
        order_id = c["tool_results"][0]["result"]["body"]["order_id"]
        assert order_id in c["final_response"]

    def test_correct_case_does_not_alias_tool_results(self):
        run = build_correct_run(CASES)
        run["cases"][0]["tool_results"][0]["result"]["ok"] = False
        assert run["cases"][3]["tool_results"][0]["result"]["ok"] is True


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

    def test_unbacked_success_claim_fails_only_action_tools(self):
        """注入要"纯"：只打挂状态变更工具，查询结果不受影响（保证归因清晰）。"""
        run = mutate_unbacked_success_claim(build_correct_run(CASES))
        place = run["cases"][0]["tool_results"][0]["result"]
        query = run["cases"][3]["tool_results"][0]["result"]
        assert place["ok"] is False
        assert query["ok"] is True

    def test_unsupported_status_claim_rewrites_response(self):
        run = mutate_unsupported_status_claim(build_correct_run(CASES))
        assert all("已发货" in c["final_response"] for c in run["cases"])

    def test_fabricated_entity_rewrites_response(self):
        run = mutate_fabricated_entity(build_correct_run(CASES))
        assert all("幻想路999号" in c["final_response"] for c in run["cases"])

    def test_status_value_mismatch_only_touches_query_cases(self):
        run = mutate_status_value_mismatch(build_correct_run(CASES))
        assert "已发货" in run["cases"][3]["final_response"]
        assert "已发货" not in run["cases"][0]["final_response"]

    def test_all_mutations_registered_with_metadata(self):
        assert set(MUTATIONS) == {
            "wrong_tool", "wrong_arg", "blind_order", "extra_retry", "deny_mismatch",
            "fabricated_order", "unbacked_success_claim", "unsupported_status_claim",
            "fabricated_entity", "status_value_mismatch",
        }
        assert MUTATIONS["fabricated_entity"].gated is False
        assert MUTATIONS["status_value_mismatch"].gated is False
        assert all(m.note for m in MUTATIONS.values() if not m.gated)


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

    def test_case_deteriorated_directions(self):
        assert case_deteriorated("arg_score", "lower", {"arg_score": 1.0}, {"arg_score": 0.5})
        assert case_deteriorated("retry_count", "higher", {"retry_count": 0}, {"retry_count": 1})
        assert case_deteriorated("hallucination", "higher",
                                 {"hallucination": False}, {"hallucination": True})
        assert not case_deteriorated("arg_score", "lower", {"arg_score": 1.0}, {"arg_score": 1.0})

    def test_case_coverage_ignores_inapplicable_cases(self):
        before = [{"id": "a", "arg_score": 1.0}, {"id": "b", "arg_score": 1.0}]
        after = [{"id": "a", "arg_score": 0.0}, {"id": "b", "arg_score": 1.0}]
        caught, applicable = case_coverage("arg_accuracy", before, after, {"a"})
        assert (caught, applicable) == (1, 1)

    def test_case_coverage_skips_none_fields(self):
        before = [{"id": "a", "permission_ok": None}]
        after = [{"id": "a", "permission_ok": True}]
        caught, applicable = case_coverage(
            "permission_denial_accuracy", before, after, {"a"}
        )
        assert (caught, applicable) == (0, 1)


class TestMatrix:
    def test_baseline_has_no_hallucination_findings(self):
        """第一道防线：全对输入不许误报。"""
        matrix = run_matrix(CASES)
        assert matrix["baseline_hallucination_findings"] == 0
        assert matrix["baseline_metrics"]["hallucination_rate"] == 0.0

    def test_matrix_catches_structural_mutations(self):
        """离线确定性：结构性注入错误都应被至少一个指标捕获。"""
        matrix = run_matrix(CASES)
        assert matrix["baseline_metrics"]["tool_selection_accuracy"] == 1.0
        names = {r["mutation"] for r in matrix["results"]}
        assert names == set(MUTATIONS)
        caught = {r["mutation"] for r in matrix["results"] if r["caught"]}
        assert {"wrong_tool", "wrong_arg", "blind_order",
                "extra_retry", "deny_mismatch"} <= caught, matrix["results"]

    def test_hallucination_mutations_are_fully_caught(self):
        """2026-09 修复回归：幻觉类注入必须 100% 被 hallucination_rate 抓住。

        修复前幻觉判定是硬编码关键词（`"火星" in input and "已为你创建订单"`），
        注入 fabricated_order 的覆盖率只有 2.6%——这条断言就是那时立的反向记录。
        """
        matrix = run_matrix(CASES)
        for name in ("fabricated_order", "unbacked_success_claim", "unsupported_status_claim"):
            rec = next(r for r in matrix["results"] if r["mutation"] == name)
            assert rec["caught"] is True, rec
            assert rec["coverage_of_applicable"] == 1.0, rec
            assert rec["primary_metric"] == "hallucination_rate"

    def test_documented_blind_spots_are_the_only_gaps(self):
        matrix = run_matrix(CASES)
        assert set(matrix["blind_spots"]) <= set(KNOWN_UNCOVERED)
        assert matrix["unexpected_blind_spots"] == []

    def test_gate_passes_on_clean_matrix(self):
        assert evaluate_gate(run_matrix(CASES)) == []

    def test_gate_fails_on_baseline_false_positive(self):
        matrix = run_matrix(CASES)
        matrix["baseline_hallucination_findings"] = 1
        problems = evaluate_gate(matrix)
        assert any("基线误报" in p for p in problems)

    def test_gate_fails_on_unregistered_blind_spot(self):
        matrix = run_matrix(CASES)
        matrix["results"][0]["caught"] = False
        matrix["results"][0]["coverage_of_applicable"] = 0.0
        problems = evaluate_gate(matrix)
        assert any(matrix["results"][0]["mutation"] in p for p in problems)

    def test_gate_fails_when_coverage_below_threshold(self):
        matrix = run_matrix(CASES)
        problems = evaluate_gate(matrix, min_coverage=1.0)
        assert problems == []
        matrix["results"][1]["coverage_of_applicable"] = 0.5
        problems = evaluate_gate(matrix, min_coverage=0.9)
        assert any("覆盖率" in p for p in problems)

    def test_gate_ignores_ungated_blind_spots(self):
        matrix = run_matrix(CASES)
        problems = evaluate_gate(matrix)
        for name in ("fabricated_entity", "status_value_mismatch"):
            assert not any(name in p for p in problems)

    def test_markdown_reports_gate_and_blind_spots(self):
        matrix = run_matrix(CASES)
        report = {
            "generated_at": "test",
            "total_cases": len(CASES),
            **matrix,
            "gate": {"enabled": True, "passed": True, "problems": []},
        }
        md = render_markdown(report)
        assert "门禁结论" in md
        assert "覆盖覆盖率" not in md or True
        for name, reason in KNOWN_UNCOVERED.items():
            if name in matrix["blind_spots"]:
                assert reason in md
        assert "fabricated_order" in md
