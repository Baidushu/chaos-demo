"""Judge 位置偏置实验的单测（纯函数，离线确定性）。"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "agent-eval" / "scripts"))

from judge_bias import (  # noqa: E402
    aggregate_runs,
    build_judge_prompt,
    parse_verdict,
    render_markdown,
    summarize,
    verdict_to_side,
)


class TestPromptBuilding:
    def test_order_is_respected(self):
        p1 = build_judge_prompt("Q?", "ANSWER_A", "ANSWER_B")
        assert p1.index("ANSWER_A") < p1.index("ANSWER_B")
        p2 = build_judge_prompt("Q?", "ANSWER_B", "ANSWER_A")
        assert p2.index("ANSWER_B") < p2.index("ANSWER_A")

    def test_question_and_json_contract_present(self):
        prompt = build_judge_prompt("订单404怎么办", "a1", "a2")
        assert "订单404怎么办" in prompt
        assert '"winner"' in prompt and '"tie"' in prompt


class TestVerdictParsing:
    def test_accepts_number_and_word_forms(self):
        assert parse_verdict({"winner": "1"}) == "first"
        assert parse_verdict({"winner": 2}) == "second"
        assert parse_verdict({"winner": "first"}) == "first"
        assert parse_verdict({"winner": "tie"}) == "tie"

    def test_rejects_invalid(self):
        assert parse_verdict({"winner": "maybe"}) == "invalid"
        assert parse_verdict({}) == "invalid"
        assert parse_verdict(None) == "invalid"


class TestSideMapping:
    def test_first_position_maps_to_answer_a_without_swap(self):
        assert verdict_to_side("first", swapped=False) == "a"
        assert verdict_to_side("second", swapped=False) == "b"

    def test_swapped_order_inverts_mapping(self):
        # 交换顺序后，「第一个位置」= 答案 B
        assert verdict_to_side("first", swapped=True) == "b"
        assert verdict_to_side("second", swapped=True) == "a"

    def test_tie_and_invalid(self):
        assert verdict_to_side("tie", swapped=False) == "tie"
        assert verdict_to_side("invalid", swapped=False) is None


class TestSummarize:
    _V1 = {"a": "first", "b": "second", "tie": "tie", None: "invalid"}
    _V2 = {"a": "second", "b": "first", "tie": "tie", None: "invalid"}

    def _rec(self, rid, s1, s2, ref="a"):
        """按「答案侧」反推位置结论，保证 fixture 自洽。"""
        return {
            "id": rid,
            "reference_winner": ref,
            "order1_side": s1,
            "order2_side": s2,
            "order1_verdict": self._V1[s1],
            "order2_verdict": self._V2[s2],
        }

    def test_flip_and_position_rates(self):
        records = [
            self._rec("c1", "a", "b", ref="a"),   # 翻转（位置影响了结论）
            self._rec("c2", "a", "a", ref="a"),   # 稳定
            self._rec("c3", "b", "b", ref="b"),   # 稳定
            self._rec("c4", "a", "b", ref="a"),   # 翻转
        ]
        s = summarize(records)
        assert s["total_pairs"] == 4
        assert s["usable_pairs"] == 4
        assert s["flip_count"] == 2
        assert s["flip_rate"] == 0.5
        # 首位胜率按「位置无关」口径：8 次判定中首位获胜 3 次
        # order1 首位=A：c1 a✓, c2 a✓, c3 b✗, c4 a✓ → 3
        # order2 首位=B：c1 b✓, c2 a✗, c3 b✓, c4 b✓ → 3
        assert s["first_position_judgment_count"] == 8
        assert s["first_position_win_count"] == 6
        assert s["first_position_win_rate"] == 0.75

    def test_reference_accuracy_by_order(self):
        records = [
            self._rec("c1", "a", "a", ref="a"),
            self._rec("c2", "b", "a", ref="a"),   # 顺序1 错、顺序2 对
        ]
        s = summarize(records)
        assert s["reference_accuracy_order1"] == 0.5
        assert s["reference_accuracy_order2"] == 1.0

    def test_invalid_pairs_excluded_from_usable(self):
        records = [
            self._rec("c1", "a", "a", ref="a"),
            self._rec("c2", None, "a", ref="a"),
        ]
        s = summarize(records)
        assert s["total_pairs"] == 2
        assert s["usable_pairs"] == 1
        assert s["invalid_pairs"] == 1
        assert s["flip_rate"] == 0.0


class TestReportRendering:
    def test_markdown_contains_core_metrics(self):
        records = [
            {
                "id": "c1",
                "reference_winner": "a",
                "note": "注释",
                "order1_verdict": "first",
                "order2_verdict": "first",
                "order1_side": "a",
                "order2_side": "b",
            }
        ]
        # 渲染使用多轮聚合结构（aggregate_runs）
        report = {
            "generated_at": "2026-08-25T00:00:00Z",
            "judge": {"provider": "mock", "model": "m"},
            "summary": aggregate_runs([summarize(records)]),
            "records": records,
        }
        md = render_markdown(report)
        assert "flip_rate" in md
        assert "首位胜率" in md
        assert "轮间标准差" in md
        assert "c1" in md

    def test_aggregate_runs_computes_mean_and_stdev(self):
        s1 = {"total_pairs": 8, "flip_rate": 0.0, "first_position_win_rate": 0.5,
              "reference_accuracy_order1": 1.0, "reference_accuracy_order2": 1.0}
        s2 = {"total_pairs": 8, "flip_rate": 0.25, "first_position_win_rate": 0.5625,
              "reference_accuracy_order1": 0.9, "reference_accuracy_order2": 0.8}
        agg = aggregate_runs([s1, s2])
        assert agg["runs"] == 2
        assert agg["flip_rate_mean"] == 0.125
        assert agg["flip_rate_per_run"] == [0.0, 0.25]
        assert agg["first_position_win_rate_mean"] == 0.53125
        # 轮间标准差：两轮 x/y 的样本标准差 = |x-y| / sqrt(2)
        assert abs(agg["flip_rate_stdev"] - 0.25 / (2 ** 0.5)) < 1e-9
