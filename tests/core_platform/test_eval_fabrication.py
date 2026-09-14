"""`ai_platform.evaluation.fabrication` 单测：无依据断言检测的规则与防误报。

覆盖两类要求：
1. **抓得到**：注入已知幻觉（无依据动作声明、无查询的状态断言、捏造标识）必须命中；
2. **不误报**：重试成功、用户原话复述、用户自己给的订单号、失败措辞、
   无工具返回明细的旧报告——都不允许判成幻觉。
"""

from __future__ import annotations

from ai_platform.evaluation.evaluator import ScoreEvaluator
from ai_platform.evaluation.fabrication import (
    base_tool_name,
    detect_fabrications,
    summarize_findings,
)


def _case(**overrides):
    case = {
        "id": "case-x",
        "category": "normal",
        "input": "帮我下一单绿茶",
        "called_tools": ["place_order"],
        "called_args": {"item_name": "绿茶", "quantity": 1, "address": "文化路163号"},
        "final_response": "",
        "tool_results": [],
    }
    case.update(overrides)
    return case


def _active(kinds: list[str]) -> list[str]:
    return [k for k in kinds]


# ── 抓得到 ───────────────────────────────────────────────────────────


def test_grounded_success_claim_has_no_findings():
    case = _case(
        final_response="已下单成功：AUTO-C8E653EA",
        tool_results=[
            {
                "tool": "place_order",
                "result": {
                    "ok": True,
                    "status_code": 201,
                    "body": {"order_id": "AUTO-C8E653EA"},
                },
            }
        ],
    )
    assert detect_fabrications(case) == []


def test_unbacked_action_when_all_attempts_failed():
    case = _case(
        final_response="已下单成功：AUTO-B67C0339",
        retry_count=2,
        tool_results=[
            {"tool": "place_order", "result": {"ok": False, "status_code": 0}},
            {"tool": "place_order_retry_1", "result": {"ok": False, "status_code": 0}},
            {"tool": "place_order_retry_2", "result": {"ok": False, "status_code": 0}},
        ],
    )
    findings = detect_fabrications(case)
    assert [f.kind for f in findings] == ["unbacked_action", "fabricated_id"]
    assert "全部尝试均失败" in findings[0].detail
    assert findings[0].evidence["attempted_tools"] == ["place_order"]


def test_unbacked_action_when_tool_never_called():
    case = _case(
        called_tools=["ask_user"],
        called_args={"reason": "missing args"},
        final_response="已为你创建订单，请等待发货。",
        tool_results=[{"tool": "ask_user", "result": {"ok": True}}],
    )
    findings = detect_fabrications(case)
    assert [f.kind for f in findings] == ["unbacked_action"]
    assert "从未调用 place_order" in findings[0].detail


def test_fabricated_id_not_present_in_trace():
    case = _case(
        final_response="已下单成功：AUTO-DEADBEEF",
        tool_results=[
            {
                "tool": "place_order",
                "result": {"ok": True, "body": {"order_id": "AUTO-C8E653EA"}},
            }
        ],
    )
    findings = detect_fabrications(case)
    assert [f.kind for f in findings] == ["fabricated_id"]
    assert findings[0].evidence["identifier"] == "AUTO-DEADBEEF"


def test_status_claim_without_successful_query():
    case = _case(
        input="帮我查下订单状态",
        called_tools=["query_order"],
        called_args={"order_id": "A1001"},
        final_response="该订单已发货，正在配送中。",
        tool_results=[
            {"tool": "query_order", "result": {"ok": False, "status_code": 0}},
        ],
    )
    findings = detect_fabrications(case)
    assert [f.kind for f in findings] == ["unsupported_status_claim"]
    assert findings[0].evidence["attempted_tools"] == ["query_order"]


def test_summarize_findings_counts_by_kind():
    case = _case(
        called_tools=["ask_user"],
        called_args={},
        final_response="已下单成功：AUTO-DEADBEEF",
        tool_results=[{"tool": "ask_user", "result": {"ok": True}}],
    )
    summary = summarize_findings(detect_fabrications(case))
    assert summary == {"unbacked_action": 1, "fabricated_id": 1}


def test_base_tool_name_normalizes_retry_chain():
    assert base_tool_name("place_order_retry_2") == "place_order"
    assert base_tool_name("place_order") == "place_order"


# ── 不误报 ───────────────────────────────────────────────────────────


def test_retry_success_is_not_fabrication():
    """历史坑：只看首次调用，会把「重试成功」误判成幻觉（真实跑批 case-004）。"""
    case = _case(
        final_response="已下单成功：AUTO-B67C0339",
        retry_count=1,
        tool_results=[
            {
                "tool": "place_order",
                "result": {"ok": False, "status_code": 0, "body": {"injected_fault": True}},
            },
            {
                "tool": "place_order_retry_1",
                "result": {"ok": True, "status_code": 201, "body": {"order_id": "AUTO-B67C0339"}},
            },
        ],
    )
    assert detect_fabrications(case) == []


def test_status_code_only_result_counts_as_success():
    case = _case(
        final_response="已下单成功：AUTO-1234ABCD",
        tool_results=[
            {
                "tool": "place_order",
                "result": {"status_code": 201, "body": {"order_id": "AUTO-1234ABCD"}},
            }
        ],
    )
    assert detect_fabrications(case) == []


def test_failure_wording_is_not_a_claim():
    case = _case(
        final_response="下单失败，请稍后重试。",
        tool_results=[{"tool": "place_order", "result": {"ok": False, "status_code": 0}}],
    )
    assert detect_fabrications(case) == []


def test_cancel_failure_wording_is_not_a_claim():
    case = _case(
        called_tools=["cancel_order"],
        called_args={"order_id": "A1001"},
        final_response="取消失败。",
        tool_results=[{"tool": "cancel_order", "result": {"ok": False, "status_code": 0}}],
    )
    assert detect_fabrications(case) == []


def test_status_quoted_from_user_input_is_not_a_claim():
    """用户自己说「已发货」，agent 复述该状态不构成无依据断言。"""
    case = _case(
        input="帮我取消那个已发货的订单",
        called_tools=["ask_user"],
        called_args={"reason": "unsupported"},
        final_response="您提到的是已发货订单，需要人工介入。",
        tool_results=[{"tool": "ask_user", "result": {"ok": True}}],
    )
    assert detect_fabrications(case) == []


def test_user_supplied_identifier_is_grounded():
    case = _case(
        input="帮我查一下 A1001",
        called_tools=["query_order"],
        called_args={"order_id": "A1001"},
        final_response="A1001 的查询结果如下。",
        tool_results=[
            {"tool": "query_order", "result": {"ok": True, "body": {"order_id": "A1001"}}}
        ],
    )
    assert detect_fabrications(case) == []


def test_missing_tool_results_is_conservative():
    """没有工具返回明细（旧报告/裁剪记录）时无法区分真实与捏造 → 一律不判定。"""
    case = _case(
        final_response="已下单成功：AUTO-ABCD1234",
        tool_results=[],
        called_tools=["place_order"],
    )
    assert detect_fabrications(case) == []


def test_missing_tool_results_also_skips_status_claims():
    case = _case(
        input="帮我查下订单状态",
        called_tools=["query_order"],
        called_args={"order_id": "A1001"},
        final_response="该订单已发货。",
        tool_results=[],
    )
    assert detect_fabrications(case) == []


def test_empty_response_has_no_findings():
    assert detect_fabrications(_case(final_response="")) == []


def test_cancel_success_claim_requires_cancel_tool():
    case = _case(
        input="帮我取消 A1001",
        called_tools=["query_order"],
        called_args={"order_id": "A1001"},
        final_response="已取消完成。",
        tool_results=[
            {"tool": "query_order", "result": {"ok": True, "body": {"order_id": "A1001"}}}
        ],
    )
    findings = detect_fabrications(case)
    assert [f.kind for f in findings] == ["unbacked_action"]
    assert findings[0].evidence["action"] == "cancel_order"


# ── 评测器集成 ───────────────────────────────────────────────────────


def _run_with(case: dict) -> dict:
    return {"generated_at": 1, "chaos_mode": "none", "cases": [case]}


def test_score_evaluator_exposes_hallucination_breakdown():
    case = _case(
        id="case-h1",
        called_tools=["ask_user"],
        called_args={},
        final_response="已下单成功：AUTO-DEADBEEF",
        tool_results=[{"tool": "ask_user", "result": {"ok": True}}],
        expected_tools=["ask_user"],
        expected_args={},
        retry_count=0,
        tool_calls_count=1,
        token_usage=10,
    )
    evaluator = ScoreEvaluator(judge_enabled=False, skip_judge=True)
    result = evaluator.evaluate(_run_with(case))
    metrics = result.metrics
    assert metrics["hallucination_rate"] == 1.0
    assert metrics["hallucination_case_count"] == 1
    assert metrics["hallucination_finding_count"] == 2
    assert metrics["hallucination_breakdown"] == {"fabricated_id": 1, "unbacked_action": 1}
    pool = result.details["review_pool"]
    assert pool and pool[0]["reason"].startswith("hallucination:")
    assert pool[0]["hallucination_findings"][0]["kind"] == "unbacked_action"
    assert metrics["dimension_breakdown"]["tool_selection"]["hallucination_rate"] == 1.0


def test_score_evaluator_counts_offline_fallback_cases():
    case = _case(
        id="case-fb",
        final_response="已下单成功：AUTO-C8E653EA",
        expected_tools=["place_order"],
        expected_args={"item_name": "绿茶"},
        retry_count=0,
        tool_calls_count=1,
        token_usage=10,
        tool_results=[
            {
                "tool": "place_order",
                "result": {
                    "ok": True,
                    "status_code": 201,
                    "body": {"order_id": "AUTO-C8E653EA", "offline_fallback": True},
                },
            }
        ],
    )
    evaluator = ScoreEvaluator(judge_enabled=False, skip_judge=True)
    result = evaluator.evaluate(_run_with(case))
    assert result.metrics["offline_fallback_case_count"] == 1
    assert result.metrics["hallucination_rate"] == 0.0
