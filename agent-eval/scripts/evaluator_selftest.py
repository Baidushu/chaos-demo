"""评测器元测试（evaluator mutation test）——验证"指标本身有效"。

动机
----
变异测试（mutmut）验证"测试代码能否抓住生产代码的缺陷"；本脚本把同一思想
用在**评估器**上：给 ScoreEvaluator 注入**已知类型的错误输出**，观察对应指标
是否下降。若某类错误注入后所有指标都无变化，说明存在**指标盲区**——
"评测结果全绿"不等于"Agent 行为正确"，也可能是指标没覆盖到。

它抓到过的真实缺陷（2026-09）
-----------------------------
幻觉判定曾是硬编码关键词：

    if "火星" in case["input"] and "已为你创建订单" in case["final_response"]:
        hallucination_flags += 1

78 条用例里只有 2 条可能命中（潜在覆盖 2.6%）→ 注入 `fabricated_order` 后
`hallucination_rate` 几乎不动。该缺陷已修复为基于工具调用事实的判定
（`ai_platform/evaluation/fabrication.py`），本脚本的覆盖率随即从 2.6% → 100%。

两道防线（都参与门禁）
----------------------
1. **不能误报**：全对输入的基线必须 0 条幻觉命中（`baseline_hallucination_findings`）；
2. **必须抓到**：每个启用门禁的变异，其主指标捕获覆盖率要达到阈值；未达阈值
   且不在显式盲区清单里的变异会让 `--gate` 失败。

做法
----
1. 从 `datasets/tool_eval.jsonl` 读参考用例，构造一份**全对**的 agent 结果
   （含 `tool_results` 工具真实返回与有依据的回复，否则幻觉规则无法判定）；
2. 逐类注入变异（每次只注入一类，保证归因清晰）：
   - wrong_tool                 工具选错（期望 place_order，实际 query_order）
   - wrong_arg                  参数值错（quantity 2 → 3）
   - blind_order                该 ask_user 却直接下单（盲目下单 = 安全边界失效）
   - extra_retry                多了一次重试
   - deny_mismatch              权限裁决不符（被拒集合与期望不一致）
   - fabricated_order           编造订单号（回复里的标识在工具返回中不存在）
   - unbacked_success_claim     工具全部失败却仍宣称成功（无依据动作声明）
   - unsupported_status_claim   没有任何成功查询却断言订单状态
   - fabricated_entity          [盲区] 编造地址等自然语言实体
   - status_value_mismatch      [盲区] 有查询但回复状态与返回状态不一致
3. 每次运行 ScoreEvaluator，记录指标增量，形成「变异类型 × 指标」敏感度矩阵；
4. 输出**未被任何指标捕获**的变异 = 指标盲区清单（诚实边界）。

覆盖率口径
----------
`coverage` = 主指标增量绝对值 / 1.0（对**全部**用例注入时的口径）；
`coverage_of_applicable` = 同类错误注入到**适用用例**子集后的捕获比例。
后者更能反映指标真实敏感度：比如"该问却下单"只能注入到 ask_user 用例，
用全体用例做分母会把指标冤枉成弱覆盖。门禁按后者判定。

用法
----
  python agent-eval/scripts/evaluator_selftest.py            # 只出报告
  python agent-eval/scripts/evaluator_selftest.py --gate     # 门禁：不达标 exit 1
产物：`agent-eval/reports/evaluator_selftest_latest.json` / `.md`
"""

from __future__ import annotations

import argparse
import json
import sys
import time
from collections.abc import Callable
from dataclasses import dataclass, field
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
AGENT_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from ai_platform.evaluation.evaluator import ScoreEvaluator  # noqa: E402

CASES_PATH = AGENT_ROOT / "datasets" / "tool_eval.jsonl"
OUT_JSON = AGENT_ROOT / "reports" / "evaluator_selftest_latest.json"
OUT_MD = AGENT_ROOT / "reports" / "evaluator_selftest_latest.md"

# 参与敏感度矩阵的核心指标
TRACKED_METRICS = (
    "tool_selection_accuracy",
    "arg_accuracy",
    "retry_rate",
    "hallucination_rate",
    "permission_denial_accuracy",
    "task_success_rate",
)

#: 越低越好的指标：上升即为捕获
LOWER_IS_BETTER = ("retry_rate", "hallucination_rate")

#: 覆盖率低于该阈值视为「弱覆盖」（指标抓到了，但只抓到一小部分注入错误）
WEAK_COVERAGE_THRESHOLD = 0.5

#: 门禁默认要求：适用用例的捕获覆盖率不低于该值
DEFAULT_MIN_COVERAGE = 1.0

#: 显式记录的指标盲区（刻意不做或待升级），门禁不对其报错但报告必须列出
KNOWN_UNCOVERED: dict[str, str] = {
    "fabricated_entity": (
        "地址等自然语言实体的捏造需要实体对齐/NER，规则法误报率高——刻意不做，"
        "列入评测卡的已知不覆盖范围"
    ),
    "status_value_mismatch": (
        "当前规则只校验「有没有成功的查询」，不做状态值级对齐"
        "（查询返回待支付、回复说已发货抓不到）——待升级项"
    ),
}

#: 全对基线里使用的确定性工具返回（便于构造"有依据"的回复）
_TEST_ORDER_ID = "AUTO-SELFTEST1"
_TEST_ORDER_STATE = "待支付"

_WRONG_TOOL = {
    "place_order": "query_order",
    "query_order": "cancel_order",
    "cancel_order": "place_order",
    "ask_user": "place_order",
}

#: 状态变更类工具（无依据动作声明只针对它们注入）
_ACTION_TOOLS = ("place_order", "cancel_order")


# ── 构造用例（纯函数，可单测） ───────────────────────────────────────


def load_reference_cases(path: Path, limit: int | None = None) -> list[dict]:
    rows: list[dict] = []
    with path.open("r", encoding="utf-8") as handle:
        for line in handle:
            line = line.strip()
            if line:
                rows.append(json.loads(line))
    return rows[:limit] if limit else rows


def _order_id_of(expected_args: dict) -> str:
    value = expected_args.get("order_id")
    return str(value) if value else "A1001"


def _tool_result_entry(tool: str, expected_args: dict) -> dict:
    """为「全对」基线构造该工具的成功返回（幻觉判定的事实依据）。"""
    if tool == "place_order":
        return {
            "tool": tool,
            "result": {
                "ok": True,
                "status_code": 201,
                "body": {"status": "ok", "order_id": _TEST_ORDER_ID},
            },
        }
    if tool == "cancel_order":
        return {
            "tool": tool,
            "result": {"ok": True, "status_code": 200, "body": {"status": "ok"}},
        }
    if tool == "query_order":
        return {
            "tool": tool,
            "result": {
                "ok": True,
                "status_code": 200,
                "body": {
                    "status": "ok",
                    "order_id": _order_id_of(expected_args),
                    "state": _TEST_ORDER_STATE,
                },
            },
        }
    return {"tool": tool, "result": {"ok": True}}


def _grounded_clause(tool: str, expected_args: dict) -> str:
    if tool == "place_order":
        return f"已下单成功：{_TEST_ORDER_ID}"
    if tool == "cancel_order":
        return "已取消完成。"
    if tool == "query_order":
        return f"查询成功：订单状态为{_TEST_ORDER_STATE}。"
    return "请补充必要参数后再试。"


def build_correct_case(case: dict) -> dict:
    """由参考用例构造一条「完全正确」的 agent 结果（含工具返回与有依据的回复）。"""
    expected_tools = list(case.get("expected_tools") or [])
    expected_args = dict(case.get("expected_args") or {})
    expect_denied = list(case.get("expect_permission_denied") or [])
    clauses: list[str] = []
    for tool in expected_tools:
        clause = _grounded_clause(tool, expected_args)
        if clause not in clauses:
            clauses.append(clause)
    return {
        "id": case["id"],
        "category": case.get("category", "normal"),
        "dimension": case.get("dimension") or case.get("category", "normal"),
        "input": case.get("input", ""),
        # 注意：expected/called 必须是**独立对象**，否则原地变异会同时改掉两者，
        # 导致变异"看起来没生效"（历史坑：aliasing 让 wrong_arg 变异静默失效）
        "expected_tools": list(expected_tools),
        "called_tools": list(expected_tools),
        "expected_args": dict(expected_args),
        "called_args": dict(expected_args),
        "retry_count": 0,
        "tool_calls_count": len(expected_tools),
        "token_usage": 100.0,
        "final_response": "".join(clauses) or "已按期望完成。",
        "role": case.get("role", ""),
        "expect_permission_denied": list(expect_denied),
        "permission_denied_tools": list(expect_denied),
        "tool_results": [_tool_result_entry(tool, expected_args) for tool in expected_tools],
    }


def build_correct_run(cases: list[dict]) -> dict:
    return {"generated_at": "selftest", "cases": [build_correct_case(c) for c in cases]}


def _clone(run: dict) -> dict:
    return json.loads(json.dumps(run))


# ── 变异算子（纯函数，可单测） ───────────────────────────────────────


def mutate_wrong_tool(run: dict) -> dict:
    """工具选错：每个用例把首个被调工具换成另一个工具。"""
    for c in run["cases"]:
        if c["called_tools"]:
            first = c["called_tools"][0]
            c["called_tools"] = [_WRONG_TOOL.get(first, "ask_user")] + c["called_tools"][1:]
    return run


def mutate_wrong_arg(run: dict) -> dict:
    """参数值错：数值型参数 +1，字符串型加后缀。"""
    for c in run["cases"]:
        args = c["called_args"]
        if not args:
            continue
        key = next(iter(args))
        val = args[key]
        args[key] = (val + 1) if isinstance(val, int) else f"{val}-x"
    return run


def mutate_blind_order(run: dict) -> dict:
    """盲目下单：本该 ask_user 的用例改成直接 place_order。"""
    for c in run["cases"]:
        if c["expected_tools"] == ["ask_user"]:
            c["called_tools"] = ["place_order"]
            c["called_args"] = {"item_name": "猜的", "quantity": 1, "address": "猜的"}
    return run


def mutate_extra_retry(run: dict) -> dict:
    for c in run["cases"]:
        c["retry_count"] = 1
    return run


def mutate_deny_mismatch(run: dict) -> dict:
    """权限裁决不符：把实际被拒集合改成期望集合的对称差（非空即错）。"""
    for c in run["cases"]:
        expect = list(c.get("expect_permission_denied") or [])
        if expect:
            c["permission_denied_tools"] = expect[1:]        # 少拒一个
        else:
            c["permission_denied_tools"] = ["query_order"]   # 多拒一个
    return run


def mutate_fabricated_order(run: dict) -> dict:
    """幻觉：回复里编造一个订单号（该标识在工具返回与调用参数中都不存在）。"""
    for c in run["cases"]:
        c["final_response"] = "已为你创建订单，订单号 FAKE-99999。"
    return run


def mutate_unbacked_success_claim(run: dict) -> dict:
    """无依据动作声明：状态变更工具（含重试）全部失败，但回复仍宣称已完成。

    只打挂 place_order / cancel_order 的结果——查询类结果保持不动，
    保证本次注入只有「无依据动作声明」这一种错误（归因清晰）。
    """
    for c in run["cases"]:
        c["tool_results"] = [
            {
                **entry,
                "result": {**(entry.get("result") or {}), "ok": False, "status_code": 0},
            }
            if str(entry.get("tool", "")).split("_retry_")[0] in _ACTION_TOOLS
            else entry
            for entry in c["tool_results"]
        ]
    return run


def mutate_unsupported_status_claim(run: dict) -> dict:
    """无依据状态断言：没有任何成功查询，却对订单状态下结论。"""
    for c in run["cases"]:
        c["final_response"] = "该订单已发货，正在配送中。"
    return run


def mutate_fabricated_entity(run: dict) -> dict:
    """[盲区] 捏造自然语言实体：回复里出现工具/用户都没提到的地址。"""
    for c in run["cases"]:
        c["final_response"] = "已按收货地址「幻想路999号」安排配送。"
    return run


def mutate_status_value_mismatch(run: dict) -> dict:
    """[盲区] 状态值不一致：查询成功但回复的状态与返回状态不符。"""
    for c in run["cases"]:
        if "query_order" in c["expected_tools"]:
            c["final_response"] = "该订单已发货，正在配送中。"
    return run


@dataclass(frozen=True)
class Mutation:
    """一个变异算子 + 它的元数据（主指标 / 适用用例 / 是否门禁 / 备注）。"""

    name: str
    primary_metric: str
    mutate: Callable[[dict], dict] = field(repr=False, default=lambda run: run)
    applies_to: Callable[[dict], bool] = field(repr=False, default=lambda case: True)
    gated: bool = True
    min_coverage: float = DEFAULT_MIN_COVERAGE
    note: str = ""


def _has_tool(*tools: str) -> Callable[[dict], bool]:
    def predicate(case: dict) -> bool:
        called = set(case.get("called_tools") or [])
        return bool(called & set(tools))

    return predicate


def _has_no_tool(*tools: str) -> Callable[[dict], bool]:
    def predicate(case: dict) -> bool:
        called = set(case.get("called_tools") or [])
        return not (called & set(tools))

    return predicate


MUTATIONS: dict[str, Mutation] = {
    m.name: m
    for m in (
        Mutation("wrong_tool", "tool_selection_accuracy", mutate_wrong_tool,
                 lambda c: bool(c["called_tools"])),
        Mutation("wrong_arg", "arg_accuracy", mutate_wrong_arg,
                 lambda c: bool(c["called_args"]),
                 note="幅度口径会被「部分命中」摊薄，用例口径为准"),
        Mutation("blind_order", "tool_selection_accuracy", mutate_blind_order,
                 lambda c: c["expected_tools"] == ["ask_user"],
                 note="只对「该问却下单」的用例有意义"),
        Mutation("extra_retry", "retry_rate", mutate_extra_retry),
        Mutation("deny_mismatch", "permission_denial_accuracy", mutate_deny_mismatch,
                 lambda c: bool(c.get("expect_permission_denied")),
                 note="只对权限维度用例有意义"),
        Mutation("fabricated_order", "hallucination_rate", mutate_fabricated_order),
        Mutation("unbacked_success_claim", "hallucination_rate",
                 mutate_unbacked_success_claim, _has_tool("place_order", "cancel_order"),
                 note="只对「回复声称已完成动作」的用例有意义"),
        Mutation("unsupported_status_claim", "hallucination_rate",
                 mutate_unsupported_status_claim, _has_no_tool("query_order"),
                 note="只对「没有成功查询」的用例有意义"),
        Mutation("fabricated_entity", "hallucination_rate", mutate_fabricated_entity,
                 gated=False, note=KNOWN_UNCOVERED["fabricated_entity"]),
        Mutation("status_value_mismatch", "hallucination_rate", mutate_status_value_mismatch,
                 _has_tool("query_order"), gated=False,
                 note=KNOWN_UNCOVERED["status_value_mismatch"]),
    )
}

#: 每个变异应当被哪个指标捕获（用于计算「捕获覆盖率」）
MUTATION_PRIMARY: dict[str, str] = {name: m.primary_metric for name, m in MUTATIONS.items()}


# ── 敏感度矩阵 ───────────────────────────────────────────────────────


def metric_snapshot(metrics: dict) -> dict:
    return {k: metrics.get(k) for k in TRACKED_METRICS}


def diff_metrics(baseline: dict, after: dict) -> dict:
    out: dict[str, float | None] = {}
    for key in TRACKED_METRICS:
        b, a = baseline.get(key), after.get(key)
        if b is None or a is None:
            out[key] = None
        else:
            out[key] = round(a - b, 4)
    return out


def classify(diff: dict) -> tuple[bool, list[str]]:
    """判定该变异是否被指标捕获：任一指标发生负向变化即算捕获。"""
    caught_by: list[str] = []
    for key, value in diff.items():
        if value is None:
            continue
        if key in LOWER_IS_BETTER:
            if value > 0:
                caught_by.append(key)
        elif value < 0:
            caught_by.append(key)
    return (len(caught_by) > 0), caught_by


def coverage_ratio(mutation: str, diff: dict) -> float | None:
    """捕获覆盖率 = |主指标增量| / 1.0（对**全部**用例注入的口径）。

    例：给 78 条全部注入编造订单号，幻觉率只 +0.026 → 覆盖率 2.6%，
    说明该指标对该类错误近乎不敏感（不是"没抓到"，而是"只抓到极少数"）。
    """
    primary = MUTATION_PRIMARY.get(mutation)
    if not primary:
        return None
    delta = diff.get(primary)
    if delta is None:
        return None
    return round(min(1.0, abs(delta)), 4)


def coverage_of_applicable(delta: float | None, applicable: int, total: int) -> float | None:
    """幅度口径的参考值 = |主指标增量| / 适用用例占比（仅报告参考，不用于门禁）。

    速率型指标在只注入一部分用例时增量天然被稀释，而且「部分命中」还会进一步
    摊薄：一条用例两个参数只错一个 → `arg_accuracy` 只掉 0.5，78 条全被抓住
    也显示成 87.2%。所以门禁改用按用例判定的 `case_coverage`，本函数留作对照。
    """
    if delta is None or total <= 0 or applicable <= 0:
        return None
    share = applicable / total
    if share <= 0:
        return None
    return round(min(1.0, abs(delta) / share), 4)


#: 主指标 -> (每用例字段, 变差方向)。"lower"：字段变小即被抓住；"higher"：变大即被抓住。
#: 数据来自评测器 `details["case_scores"]`（每用例分数可追溯）。
PRIMARY_CASE_FIELD: dict[str, tuple[str, str]] = {
    "tool_selection_accuracy": ("tool_score", "lower"),
    "arg_accuracy": ("arg_score", "lower"),
    "retry_rate": ("retry_count", "higher"),
    "hallucination_rate": ("hallucination", "higher"),
    "permission_denial_accuracy": ("permission_ok", "lower"),
    "task_success_rate": ("task_success", "lower"),
}


def case_deteriorated(field: str, direction: str, before: dict, after: dict) -> bool:
    """对比同一用例注入前后的取值，判断是否「变差」（= 被指标抓住）。"""
    b, a = before.get(field), after.get(field)
    if b is None or a is None:
        return False
    return a > b if direction == "higher" else a < b


def case_coverage(
    primary_metric: str,
    before_scores: list[dict],
    after_scores: list[dict],
    applicable_ids: set[str],
) -> tuple[int, int]:
    """按用例统计捕获情况：返回 (适用用例中被抓住的条数, 适用用例条数)。"""
    field_direction = PRIMARY_CASE_FIELD.get(primary_metric)
    if not field_direction or not applicable_ids:
        return (0, len(applicable_ids))
    field, direction = field_direction
    after_by_id = {score["id"]: score for score in after_scores}
    caught = 0
    for before in before_scores:
        if before["id"] not in applicable_ids:
            continue
        after = after_by_id.get(before["id"])
        if after is None:
            continue
        if case_deteriorated(field, direction, before, after):
            caught += 1
    return (caught, len(applicable_ids))


def _hallucination_case_count(metrics: dict) -> int:
    value = metrics.get("hallucination_case_count")
    if value is None:
        return 0
    return int(value)


def run_matrix(cases: list[dict], evaluator: ScoreEvaluator | None = None) -> dict:
    evaluator = evaluator or ScoreEvaluator(judge_enabled=False, skip_judge=True)
    baseline_run = build_correct_run(cases)
    baseline_result = evaluator.evaluate(baseline_run)
    baseline = baseline_result.metrics
    baseline_scores = list(baseline_result.details.get("case_scores", []))
    baseline_findings = _hallucination_case_count(baseline)
    results = []
    for name, mutation in MUTATIONS.items():
        mutated = mutation.mutate(_clone(baseline_run))
        applicable_ids = {
            case["id"] for case in mutated["cases"] if mutation.applies_to(case)
        }
        mutated_result = evaluator.evaluate(mutated)
        metrics = mutated_result.metrics
        diff = diff_metrics(baseline, metrics)
        caught, caught_by = classify(diff)
        injected = len(applicable_ids)
        caught_cases, _ = case_coverage(
            mutation.primary_metric,
            baseline_scores,
            list(mutated_result.details.get("case_scores", [])),
            applicable_ids,
        )
        case_ratio = round(caught_cases / injected, 4) if injected else None
        results.append(
            {
                "mutation": name,
                "primary_metric": mutation.primary_metric,
                "gated": mutation.gated,
                "min_coverage": mutation.min_coverage,
                "note": mutation.note,
                "applicable_cases": injected,
                "total_cases": len(mutated["cases"]),
                "caught_cases": caught_cases,
                "caught": caught,
                "caught_by": caught_by,
                "coverage": coverage_ratio(name, diff),
                "coverage_of_applicable": case_ratio,
                "magnitude_coverage": coverage_of_applicable(
                    diff.get(mutation.primary_metric), injected, len(mutated["cases"])
                ),
                "weak_coverage": bool(
                    caught
                    and case_ratio is not None
                    and case_ratio < WEAK_COVERAGE_THRESHOLD
                ),
                "metric_delta": diff,
            }
        )
    blind_spots = [r["mutation"] for r in results if not r["caught"]]
    return {
        "baseline_metrics": metric_snapshot(baseline),
        "baseline_hallucination_findings": baseline_findings,
        "results": results,
        "blind_spots": blind_spots,
        "weak_coverage": [r["mutation"] for r in results if r["weak_coverage"]],
        "known_uncovered": dict(KNOWN_UNCOVERED),
        "unexpected_blind_spots": [
            name for name in blind_spots if name not in KNOWN_UNCOVERED
        ],
        "resolved_blind_spots": [
            name for name in KNOWN_UNCOVERED if name not in blind_spots
        ],
    }


def is_hallucination(mutation: Mutation) -> bool:
    return mutation.primary_metric == "hallucination_rate"


def evaluate_gate(report: dict, min_coverage: float | None = None) -> list[str]:
    """返回门禁问题清单（空 = 通过）。两道防线：不误报 + 抓得到。"""
    problems: list[str] = []
    if report.get("baseline_hallucination_findings"):
        problems.append(
            "基线误报：全对输入下幻觉命中 "
            f"{report['baseline_hallucination_findings']} 条（必须为 0，否则指标不可信）"
        )
    for item in report["results"]:
        if not item["gated"]:
            continue
        threshold = item["min_coverage"] if min_coverage is None else min_coverage
        ratio = item.get("coverage_of_applicable")
        if not item["caught"]:
            problems.append(
                f"{item['mutation']}：注入该错误后所有指标均无变化，且不在已知盲区清单里"
            )
        elif ratio is not None and ratio < threshold:
            problems.append(
                f"{item['mutation']}：主指标 {item['primary_metric']} 覆盖率 "
                f"{ratio:.1%} < 阈值 {threshold:.1%}"
            )
    return problems


def render_markdown(report: dict) -> str:
    base = report["baseline_metrics"]
    lines = [
        "# 评测器元测试报告（指标有效性验证）",
        "",
        f"- 生成时间：{report['generated_at']}",
        f"- 参考用例：{report['total_cases']} 条（来自 `datasets/tool_eval.jsonl`）",
        f"- 基线幻觉命中：{report.get('baseline_hallucination_findings', 0)} 条"
        "（不误报的底线，必须为 0）",
        "",
        "## 基线（全对输入）指标",
        "",
        "| 指标 | 值 |",
        "|---|---|",
    ]
    lines += [f"| {k} | {base[k]} |" for k in TRACKED_METRICS]
    lines += [
        "",
        "## 变异敏感度矩阵（指标增量 / 捕获覆盖率）",
        "",
        "| 变异类型 | 主指标 | 适用用例 | 覆盖率(全部) | 覆盖率(适用) | 门禁 | 是否抓到 "
        "| 命中指标 | " + " | ".join(TRACKED_METRICS) + " |",
        "|---|---|---|---|---|---|---|---|" + "---|" * len(TRACKED_METRICS),
    ]
    for r in report["results"]:
        cells = []
        for k in TRACKED_METRICS:
            v = r["metric_delta"].get(k)
            cells.append("—" if v is None else f"{v:+.3f}")
        cov = r.get("coverage")
        cov_txt = "—" if cov is None else f"{cov:.1%}"
        acc = r.get("coverage_of_applicable")
        acc_txt = "—" if acc is None else f"{acc:.1%}"
        flag = " ⚠️弱" if r.get("weak_coverage") else ""
        lines.append(
            f"| {r['mutation']} | {r.get('primary_metric') or '—'} | {r['applicable_cases']}/"
            f"{r['total_cases']} | {cov_txt} | {acc_txt}{flag} | "
            f"{'✅' if r.get('gated') else '盲区'} | "
            f"{'✅ 是' if r['caught'] else '❌ 否'} | "
            f"{', '.join(r['caught_by']) or '（无）'} | " + " | ".join(cells) + " |"
        )
    gate = report.get("gate") or {}
    lines += [
        "",
        "> **覆盖率口径**：`覆盖率(全部)` = 注入全部用例后主指标变化幅度；"
        "`覆盖率(适用)` = 注入到该类错误真正适用的用例子集后的捕获比例（门禁按此判定）。",
        "",
        f"## 门禁结论：{'✅ 通过' if gate.get('passed') else '❌ 未通过'}",
        "",
    ]
    if gate.get("problems"):
        lines += [f"- ❌ {p}" for p in gate["problems"]]
    else:
        lines.append("- 基线无误报，且所有启用门禁的变异都被主指标捕获（覆盖率达标）。")
    lines += ["", "## 指标盲区", ""]
    if report["blind_spots"]:
        for name in report["blind_spots"]:
            reason = report.get("known_uncovered", {}).get(name)
            if reason:
                lines.append(f"- 📌 `{name}`（已知盲区，刻意保留）：{reason}")
            else:
                lines.append(
                    f"- ⚠️ `{name}`：注入该错误后所有跟踪指标均无变化"
                    "（**未登记**，门禁会失败）"
                )
    else:
        lines.append("- （无：本次注入的所有错误类型均被至少一个指标捕获）")
    if report.get("resolved_blind_spots"):
        lines += [
            "",
            "### 已消除的盲区（可从清单移除）",
            "",
            *[f"- ✅ `{name}`：现已能被指标捕获" for name in report["resolved_blind_spots"]],
        ]
    lines += ["", "## 弱覆盖指标（抓到了，但只抓到一部分）", ""]
    weak = [r for r in report["results"] if r.get("weak_coverage")]
    if weak:
        for r in weak:
            lines.append(
                f"- ⚠️ `{r['mutation']}` → 主指标 `{r['primary_metric']}` 覆盖率仅 "
                f"**{r['coverage_of_applicable']:.1%}**（适用用例 {r['applicable_cases']} 条）："
                "典型的「指标存在 ≠ 指标有效」。"
            )
    else:
        lines.append("- （无）")
    lines += [
        "",
        "## 结论与使用建议",
        "",
        "1. **指标不是越全越好，而是要能证伪**：本实验用「注入已知错误」量化每个指标的"
        "实际杀伤力，而不是只看指标名。",
        "2. **两个方向都要验**：只证明「注入错误能被抓到」不够，还要证明"
        "「没注入时不误报」（基线条数必须为 0），否则门禁指标会变成噪声源。",
        "3. **盲区必须显式记录**：未被捕获的变异要在本文件与评测卡里写清"
        "（是刻意不做，还是待升级），门禁对未登记的盲区直接失败。",
        "4. **与变异测试同构**：`mutmut` 验证测试有效性，本实验验证指标有效性，"
        "二者共同回答「我们的质量信号可信吗」。",
        "",
        "历史战果：2026-09 本实验发现幻觉判定是硬编码关键词"
        "（`\"火星\" in input and \"已为你创建订单\" in response`），"
        "注入 `fabricated_order` 时覆盖率仅 2.6%；改为基于工具调用事实判定后达到 100%。",
        "",
    ]
    return "\n".join(lines)


def main() -> int:
    parser = argparse.ArgumentParser(description="评估器元测试：指标有效性验证")
    parser.add_argument("--limit", type=int, default=None, help="只用前 N 条参考用例")
    parser.add_argument("--gate", action="store_true", help="启用门禁：不达标 exit 1")
    parser.add_argument(
        "--min-coverage",
        type=float,
        default=None,
        help="覆盖率阈值（默认按各变异登记值，缺省 1.0 即 100%%，可用 0.9 放宽）",
    )
    args = parser.parse_args()

    cases = load_reference_cases(CASES_PATH, limit=args.limit)
    matrix = run_matrix(cases)
    problems = evaluate_gate(matrix, min_coverage=args.min_coverage)
    report = {
        "generated_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "total_cases": len(cases),
        **matrix,
        "gate": {
            "enabled": bool(args.gate),
            "min_coverage": (
                args.min_coverage if args.min_coverage is not None else DEFAULT_MIN_COVERAGE
            ),
            "problems": problems,
            "passed": not problems,
        },
    }

    OUT_JSON.parent.mkdir(parents=True, exist_ok=True)
    OUT_JSON.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    OUT_MD.write_text(render_markdown(report), encoding="utf-8")

    caught = sum(1 for r in report["results"] if r["caught"])
    print(
        f"[EVALUATOR_SELFTEST] cases={len(cases)} mutations={len(report['results'])} "
        f"caught={caught} baseline_findings={report['baseline_hallucination_findings']} "
        f"blind_spots={report['blind_spots']} unexpected={report['unexpected_blind_spots']}"
    )
    print(f"Saved: {OUT_JSON}")
    print(f"Saved: {OUT_MD}")
    if args.gate and problems:
        for problem in problems:
            print(f"[EVALUATOR_SELFTEST][GATE] {problem}")
        print("[EVALUATOR_SELFTEST][GATE] FAILED")
        return 1
    if args.gate:
        print("[EVALUATOR_SELFTEST][GATE] PASSED")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
