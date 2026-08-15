from __future__ import annotations

from ai_platform.evaluation.metrics import arg_match, avg_or_none, percentile_or_none, tool_match


def test_tool_match_exact():
    assert tool_match(["place_order", "query_order"], ["place_order", "query_order"]) == 1
    assert tool_match(["place_order"], ["cancel_order"]) == 0


def test_arg_match_full():
    expected = {"order_id": "A1001", "item_name": "宫保鸡丁"}
    called = {"order_id": "A1001", "item_name": "宫保鸡丁"}
    assert arg_match(expected, called) == 1.0


def test_arg_match_partial():
    expected = {"order_id": "A1001", "item_name": "宫保鸡丁"}
    called = {"order_id": "A1001", "item_name": "鱼香肉丝"}
    assert arg_match(expected, called) == 0.5


def test_arg_match_empty():
    assert arg_match({}, {}) == 1
    assert arg_match({}, {"order_id": "A1001"}) == 1


def test_arg_match_missing_or_invalid_key():
    assert arg_match({"missing_or_invalid": True}, {"order_id": "A1001"}) == 1


def test_avg_or_none_empty():
    assert avg_or_none([]) is None


def test_avg_or_none_normal():
    assert avg_or_none([1, 2, 3]) == 2.0


def test_percentile_or_none_empty():
    assert percentile_or_none([], 50) is None


def test_percentile_or_none_p50():
    assert percentile_or_none([1, 2, 3, 4, 5], 50) == 3.0


def test_percentile_or_none_p99():
    result = percentile_or_none([1.0, 2.0, 100.0], 99)
    assert result == 100.0
