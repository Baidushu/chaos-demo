"""评测器元测试（evaluator mutation test）——验证"指标本身有效"。

动机
----
变分测试（mutmut）验证"测试代码能否抓住生产代码的缺陷"；本脚本把同一思想
用在**评估器**上：给 ScoreEvaluator 注入**已知类型的错误输出**，观察对应指标
是否下降。若某类错误注入后所有指标都无变化，说明存在**指标盲区**——
"评测结果全绿"不等于"Agent 行为正确"，也可能是指标没覆盖到。

做法
----
1. 从 `datasets/tool_eval.jsonl` 读参考用例，构造一份**全对**的 agent 结果；
2. 逐类注入变异（每次只注入一类，保证归因清晰）：
   - wrong_tool        工具选错（期望 place_order，实际 query_order）
   - wrong_arg         参数值错（quantity 2 → 3）
   - blind_order       该 ask_user 却直接下单（盲目下单 = 安全边界失效）
   - extra_retry       多了一次重试
   - deny_mismatch     权限裁决不符（被拒集合与期望不一致）
   - fabricated_order  编造订单号（幻觉）
3. 每次运行 ScoreEvaluator，记录指标增量，形成「变异类型 × 指标」敏感度矩阵；
4. 输出**未被任何指标捕获**的变异 = 指标盲区清单（诚实边界）。

用法
----
  python agent-eval/scripts/evaluator_selftest.py
产物：`agent-eval/reports/evaluator_selftest_latest.json` / `.md`
"""

from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path
from typing import Any

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

_WRONG_TOOL = {"place_order": "query_order", "query_order": "cancel_order",
               "cancel_order": "place_order", "ask_user": "place_order"}


# ── 构造用例（纯函数，可单测） ───────────────────────────────────────


def load_reference_cases(path: Path, limit: int | None = None) -> list[dict]:
    rows: list[dict] = []
    with path.open("r", encoding="utf-8") as handle:
        for line in handle:
            line = line.strip()
            if line:
                rows.append(json.loads(line))
    return rows[:limit] if limit else rows


def build_correct_case(case: dict) -> dict:
    """由参考用例构造一条「完全正确」的 agent 结果。"""
    expected_tools = list(case.get("expected_tools") or [])
    expected_args = dict(case.get("expected_args") or {})
    expect_denied = list(case.get("expect_permission_denied") or [])
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
        "final_response": "已按期望完成。",
        "role": case.get("role", ""),
        "expect_permission_denied": list(expect_denied),
        "permission_denied_tools": list(expect_denied),
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
    """幻觉：回复里编造一个订单号（不依赖特定关键词）。"""
    for c in run["cases"]:
        c["final_response"] = "已为你创建订单，订单号 FAKE-99999。"
    return run


MUTATIONS: dict[str, Any] = {
    "wrong_tool": mutate_wrong_tool,
    "wrong_arg": mutate_wrong_arg,
    "blind_order": mutate_blind_order,
    "extra_retry": mutate_extra_retry,
    "deny_mismatch": mutate_deny_mismatch,
    "fabricated_order": mutate_fabricated_order,
}

#: 每个变异应当被哪个指标捕获（用于计算「捕获覆盖率」）
MUTATION_PRIMARY: dict[str, str] = {
    "wrong_tool": "tool_selection_accuracy",
    "wrong_arg": "arg_accuracy",
    "blind_order": "tool_selection_accuracy",
    "extra_retry": "retry_rate",
    "deny_mismatch": "permission_denial_accuracy",
    "fabricated_order": "hallucination_rate",
}

#: 覆盖率低于该阈值视为「弱覆盖」（指标抓到了，但只抓到一小部分注入错误）
WEAK_COVERAGE_THRESHOLD = 0.5


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
    caught_by = [
        k for k, v in diff.items()
        if v is not None and v < 0 if k not in ("retry_rate", "hallucination_rate")
    ]
    # retry_rate / hallucination_rate 是「越低越好」，上升即捕获
    for k in ("retry_rate", "hallucination_rate"):
        v = diff.get(k)
        if v is not None and v > 0:
            caught_by.append(k)
    return (len(caught_by) > 0), caught_by


def coverage_ratio(mutation: str, diff: dict) -> float | None:
    """捕获覆盖率 = |主指标增量| / 1.0（全部用例都被注入时，速率类指标应打到 1.0）。

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


def run_matrix(cases: list[dict]) -> dict:
    evaluator = ScoreEvaluator()
    baseline_run = build_correct_run(cases)
    baseline = evaluator.evaluate(baseline_run).metrics
    results = []
    for name, fn in MUTATIONS.items():
        mutated = fn(_clone(baseline_run))
        metrics = evaluator.evaluate(mutated).metrics
        diff = diff_metrics(baseline, metrics)
        caught, caught_by = classify(diff)
        coverage = coverage_ratio(name, diff)
        results.append({
            "mutation": name,
            "primary_metric": MUTATION_PRIMARY.get(name),
            "caught": caught,
            "caught_by": caught_by,
            "coverage": coverage,
            "weak_coverage": bool(
                caught and coverage is not None and coverage < WEAK_COVERAGE_THRESHOLD
            ),
            "metric_delta": diff,
        })
    return {
        "baseline_metrics": metric_snapshot(baseline),
        "results": results,
        "blind_spots": [r["mutation"] for r in results if not r["caught"]],
        "weak_coverage": [r["mutation"] for r in results if r["weak_coverage"]],
    }


def render_markdown(report: dict) -> str:
    base = report["baseline_metrics"]
    lines = [
        "# 评测器元测试报告（指标有效性验证）",
        "",
        f"- 生成时间：{report['generated_at']}",
        f"- 参考用例：{report['total_cases']} 条（来自 `datasets/tool_eval.jsonl`）",
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
        "| 变异类型 | 主指标 | 捕获覆盖率 | 是否抓到 | 命中指标 | "
        + " | ".join(TRACKED_METRICS) + " |",
        "|---|---|---|---|---|" + "---|" * len(TRACKED_METRICS),
    ]
    for r in report["results"]:
        cells = []
        for k in TRACKED_METRICS:
            v = r["metric_delta"].get(k)
            cells.append("—" if v is None else f"{v:+.3f}")
        cov = r.get("coverage")
        cov_txt = "—" if cov is None else f"{cov:.1%}"
        flag = " ⚠️弱" if r.get("weak_coverage") else ""
        lines.append(
            f"| {r['mutation']} | {r.get('primary_metric') or '—'} | {cov_txt}{flag} | "
            f"{'✅ 是' if r['caught'] else '❌ 否'} | "
            f"{', '.join(r['caught_by']) or '（无）'} | " + " | ".join(cells) + " |"
        )
    lines += [
        "",
        "> **覆盖率口径**：把同类错误注入**全部**用例后，主指标的变化幅度 / 1.0。"
        "覆盖率低 = 指标名义上存在、实际只对少数样本敏感。",
        "",
        "## 指标盲区（未捕获的变异）",
        "",
    ]
    if report["blind_spots"]:
        lines += [f"- ⚠️ `{m}`：注入该错误后所有跟踪指标均无变化" for m in report["blind_spots"]]
    else:
        lines.append("- （无：本次注入的所有错误类型均被至少一个指标捕获）")
    lines += [
        "",
        "## 弱覆盖指标（抓到了，但只抓到一部分）",
        "",
    ]
    if report.get("weak_coverage"):
        for r in report["results"]:
            if r.get("weak_coverage"):
                lines.append(
                    f"- ⚠️ `{r['mutation']}` → 主指标 `{r['primary_metric']}` 覆盖率仅 "
                    f"**{r['coverage']:.1%}**：该类错误对整个数据集生效，但指标只对少数样本敏感——"
                    "典型的「指标存在 ≠ 指标有效」。"
                )
    else:
        lines.append("- （无）")
    lines += [
        "",
        "## 结论与使用建议",
        "",
        "1. **指标不是越全越好，而是要能证伪**：本实验用「注入已知错误」的方式量化"
        "每个指标的实际杀伤力，而不是只看指标名。",
        "2. **盲区必须显式记录**：未被捕获的变异说明该行为不在当前指标体系内——"
        "要么补指标/规则，要么在评测卡里写清「不覆盖」。",
        "3. **与变异测试同构**：`mutmut` 验证测试有效性，本实验验证指标有效性，"
        "二者共同回答「我们的质量信号可信吗」。",
        "",
    ]
    return "\n".join(lines)


def main() -> int:
    parser = argparse.ArgumentParser(description="评估器元测试：指标有效性验证")
    parser.add_argument("--limit", type=int, default=None, help="只用前 N 条参考用例")
    args = parser.parse_args()

    cases = load_reference_cases(CASES_PATH, limit=args.limit)
    matrix = run_matrix(cases)
    report = {
        "generated_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "total_cases": len(cases),
        **matrix,
    }

    OUT_JSON.parent.mkdir(parents=True, exist_ok=True)
    OUT_JSON.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    OUT_MD.write_text(render_markdown(report), encoding="utf-8")

    caught = sum(1 for r in report["results"] if r["caught"])
    print(
        f"[EVALUATOR_SELFTEST] cases={len(cases)} mutations={len(report['results'])} "
        f"caught={caught} blind_spots={report['blind_spots']} "
        f"weak_coverage={report.get('weak_coverage', [])}"
    )
    print(f"Saved: {OUT_JSON}")
    print(f"Saved: {OUT_MD}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
