from __future__ import annotations


def tool_match(expected_tools, called_tools) -> int:
    return int(expected_tools == called_tools)


def avg_or_none(values):
    if not values:
        return None
    return sum(values) / len(values)


def percentile_or_none(values, p: float):
    if not values:
        return None
    arr = sorted(float(v) for v in values)
    n = len(arr)
    rank = int(round((p / 100.0) * (n - 1)))
    rank = max(0, min(rank, n - 1))
    return arr[rank]


def arg_match(expected_args, called_args):
    if not expected_args:
        return 1
    if "missing_or_invalid" in expected_args:
        return 1
    ok = 0
    total = len(expected_args)
    for key, value in expected_args.items():
        if called_args.get(key) == value:
            ok += 1
    return ok / total if total else 1
