"""Judge 位置偏置实验（LLM-as-Judge 的可靠性验证）。

动机
----
LLM-as-Judge 是行业标准做法，但评委自身不可靠：已知至少三类偏置——
**位置偏置**（同一答案放前/放后得分不同）、自偏好（偏爱同族模型输出）、
长度偏好（偏爱长回答）。评测框架如果把 Judge 的结论当 ground truth，
这些偏置会直接污染质量门禁。

本脚本用**成对比较 + 顺序交换**量化位置偏置：
同一对答案，先按 (A 在前, B 在后) 判一次，再按 (B 在前, A 在后) 判一次；
两次结论不一致 = 该样本的判定**取决于位置而非内容**（flip）。

产出三个指标：
  - flip_rate：顺序交换后结论翻转的样本占比（越低越可靠）
  - first_win_rate：回答「第一个位置」获胜的占比（显著偏离 50% = 位置偏好）
  - reference_accuracy：与人工参考标注一致的占比（按两种顺序分别统计）

用法
----
  python agent-eval/scripts/judge_bias.py                 # 走 .env 配置的真实模型（如 DeepSeek）
  python agent-eval/scripts/judge_bias.py --provider mock # 离线链路自检（mock 无偏置，仅验证管道）
  python agent-eval/scripts/judge_bias.py --limit 4       # 只跑前 4 组，省 token

产物：agent-eval/reports/judge_bias_latest.json / .md

诚实边界：样本量小（默认 8 组），指标只用于**演示偏置的存在性与量级**，
不作为统计显著性结论；样本可继续扩充 `datasets/judge_bias_pairs.jsonl`。
"""

from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
AGENT_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from ai_platform.llm.config import load_gateway_config  # noqa: E402
from ai_platform.llm.gateway import LLMGateway  # noqa: E402
from ai_platform.llm.types import LLMRequest  # noqa: E402

PAIRS_PATH = AGENT_ROOT / "datasets" / "judge_bias_pairs.jsonl"
OUT_JSON = AGENT_ROOT / "reports" / "judge_bias_latest.json"
OUT_MD = AGENT_ROOT / "reports" / "judge_bias_latest.md"

JUDGE_SYSTEM = "你是严格的回答质量评委，只输出 JSON，不做额外解释。"
JUDGE_TEMPLATE = """请比较下面两个回答的质量，选出更好的一个。

问题：{question}

回答1：
{first}

回答2：
{second}

评分标准：事实正确性、对问题的直接回应程度、可操作性（是否给出可执行结论）。
只输出 JSON：{{"winner": "1" 或 "2" 或 "tie", "reason": "一句话理由"}}"""


# ── 纯函数（可单测，无外部依赖） ─────────────────────────────────────


def build_judge_prompt(question: str, first: str, second: str) -> str:
    """构造评委 prompt：first/second 的位置由调用方决定（用于交换顺序）。"""
    return JUDGE_TEMPLATE.format(question=question, first=first, second=second)


def parse_verdict(parsed: dict | None) -> str:
    """解析评委输出为归一化结论：'first' | 'second' | 'tie' | 'invalid'。"""
    if not isinstance(parsed, dict):
        return "invalid"
    raw = str(parsed.get("winner", "")).strip().lower()
    if raw in ("1", "first", "回答1"):
        return "first"
    if raw in ("2", "second", "回答2"):
        return "second"
    if raw in ("tie", "draw", "平局"):
        return "tie"
    return "invalid"


def verdict_to_side(verdict: str, *, swapped: bool) -> str | None:
    """把「位置结论」映射回「答案侧」：a / b / tie / None(无效)。"""
    if verdict == "tie":
        return "tie"
    if verdict == "first":
        return "b" if swapped else "a"
    if verdict == "second":
        return "a" if swapped else "b"
    return None


def summarize(records: list[dict]) -> dict:
    """由逐样本记录汇总偏置指标。

    records 元素形如：{"id", "order1_verdict", "order2_verdict",
                       "order1_side", "order2_side", "reference_winner"}

    首位胜率口径：**位置无关**——顺序1 的「第一位」是答案 A（胜出记为 a），
    顺序2 的「第一位」是答案 B（胜出记为 b）。各计一次，故基准期望为 50%；
    显著高于 50% 才是评委的位置偏好。ties/无效不计入分母。
    """
    total = len(records)
    usable = [r for r in records if r.get("order1_side") and r.get("order2_side")]
    flips = [r for r in usable if r["order1_side"] != r["order2_side"]]
    ties = [r for r in usable if r.get("order1_verdict") == "tie"]

    first_pos_wins = 0
    first_pos_total = 0
    for r in usable:
        if r["order1_side"] in ("a", "b"):        # 第一位 = A
            first_pos_total += 1
            first_pos_wins += 1 if r["order1_side"] == "a" else 0
        if r["order2_side"] in ("a", "b"):        # 第一位 = B
            first_pos_total += 1
            first_pos_wins += 1 if r["order2_side"] == "b" else 0

    def _ref_acc(key: str) -> float | None:
        labeled = [r for r in usable if r.get("reference_winner") in ("a", "b")]
        if not labeled:
            return None
        hit = sum(1 for r in labeled if r.get(key) == r["reference_winner"])
        return hit / len(labeled)

    return {
        "total_pairs": total,
        "usable_pairs": len(usable),
        "invalid_pairs": total - len(usable),
        "flip_count": len(flips),
        "flip_rate": (len(flips) / len(usable)) if usable else None,
        "first_position_win_count": first_pos_wins,
        "first_position_judgment_count": first_pos_total,
        "first_position_win_rate": (first_pos_wins / first_pos_total) if first_pos_total else None,
        "tie_count": len(ties),
        "reference_accuracy_order1": _ref_acc("order1_side"),
        "reference_accuracy_order2": _ref_acc("order2_side"),
    }


# ── Judge 调用（需 LLM） ─────────────────────────────────────────────


def stub_judge(question: str, first: str, second: str) -> str:
    """本地确定性 stub 评委（provider=mock 时使用，仅验证管道与指标计算）。

    规则：更长的回答获胜——**与位置无关**，因此预期 flip_rate=0%。
    若真模型跑出非零翻转率，二者对比即说明"偏置来自评委而非管道"。
    """
    if len(first.strip()) == len(second.strip()):
        return "tie"
    return "first" if len(first.strip()) > len(second.strip()) else "second"


def judge_once(gateway: LLMGateway, *, question: str, first: str, second: str) -> str:
    """调用一次评委，返回 'first' | 'second' | 'tie' | 'invalid'。"""
    try:
        response = gateway.generate(
            LLMRequest(
                prompt=build_judge_prompt(question, first, second),
                system=JUDGE_SYSTEM,
                response_format="json",
                metadata={"caller": "judge_bias.judge_once"},
            )
        )
    except Exception:
        return "invalid"
    return parse_verdict(response.parsed_json)


def run_pair(judge_fn, case: dict) -> dict:
    """对一组答案做「顺序交换」的两次判定。"""
    q, a, b = case["question"], case["answer_a"], case["answer_b"]
    v1 = judge_fn(q, a, b)   # A 在前
    v2 = judge_fn(q, b, a)   # B 在前（交换）
    return {
        "id": case["id"],
        "reference_winner": case.get("reference_winner"),
        "note": case.get("note", ""),
        "order1_verdict": v1,
        "order2_verdict": v2,
        "order1_side": verdict_to_side(v1, swapped=False),
        "order2_side": verdict_to_side(v2, swapped=True),
    }


def load_pairs(path: Path, limit: int | None = None) -> list[dict]:
    rows: list[dict] = []
    with path.open("r", encoding="utf-8") as handle:
        for line in handle:
            line = line.strip()
            if line:
                rows.append(json.loads(line))
    return rows[:limit] if limit else rows


# ── 报告渲染 ─────────────────────────────────────────────────────────


def _pct(value: float | None) -> str:
    return "N/A" if value is None else f"{value:.1%}"


def aggregate_runs(run_summaries: list[dict]) -> dict:
    """多轮重复实验的聚合：均值 + 标准差（呼应项目的方差意识）。

    单轮小样本结论不稳定（LLM 采样噪声），故对外报告以多轮均值为准。
    """
    import statistics as _st

    def _values(key: str) -> list[float]:
        return [s[key] for s in run_summaries if s.get(key) is not None]

    out: dict = {"runs": len(run_summaries)}
    for key in ("flip_rate", "first_position_win_rate",
                "reference_accuracy_order1", "reference_accuracy_order2"):
        vals = _values(key)
        out[f"{key}_mean"] = (sum(vals) / len(vals)) if vals else None
        out[f"{key}_stdev"] = _st.stdev(vals) if len(vals) > 1 else (0.0 if vals else None)
        out[f"{key}_per_run"] = vals
    out["total_pairs"] = run_summaries[0].get("total_pairs") if run_summaries else 0
    return out


def render_markdown(report: dict) -> str:
    s = report["summary"]
    lines = [
        "# Judge 位置偏置实验报告",
        "",
        f"- 生成时间：{report['generated_at']}",
        f"- 评委模型：`{report['judge']['provider']}` / `{report['judge']['model']}`",
        f"- 样本量：{s['total_pairs']} 组 × {s['runs']} 轮",
        "",
        "## 核心指标（多轮聚合）",
        "",
        "| 指标 | 均值 | 轮间标准差 | 逐轮值 | 读法 |",
        "|---|---|---|---|---|",
        f"| 翻转率 flip_rate | **{_pct(s['flip_rate_mean'])}** | "
        f"{_pct(s['flip_rate_stdev'])} | {[round(v, 4) for v in s['flip_rate_per_run']]} | "
        "顺序交换后结论反转的占比——越高说明判定越依赖位置 |",
        f"| 首位胜率 first_win_rate | {_pct(s['first_position_win_rate_mean'])} | "
        f"{_pct(s['first_position_win_rate_stdev'])} | "
        f"{[round(v, 4) for v in s['first_position_win_rate_per_run']]} | "
        "位置无关口径，基准 50%；显著偏高 = 位置偏好 |",
        f"| 与参考一致率（顺序1） | {_pct(s['reference_accuracy_order1_mean'])} | — | "
        f"{[round(v, 4) for v in s['reference_accuracy_order1_per_run']]} | 人工标注一致率 |",
        f"| 与参考一致率（顺序2） | {_pct(s['reference_accuracy_order2_mean'])} | — | "
        f"{[round(v, 4) for v in s['reference_accuracy_order2_per_run']]} | 人工标注一致率 |",
        "",
        "> 轮间标准差非零即说明**单轮结论不可直接引用**——Judge 评估必须多轮聚合，"
        "并固定温度/提示词版本，否则测的是采样噪声。",
        "",
        "## 末轮逐样本明细",
        "",
        "| 样本 | 参考更优 | A 在前判定 | B 在前判定 | 是否翻转 | 备注 |",
        "|---|---|---|---|---|---|",
    ]
    for r in report["records"]:
        flipped = "✅ 否" if r["order1_side"] == r["order2_side"] else "⚠️ 是"
        left = r["order1_side"] or r["order1_verdict"]
        right = r["order2_side"] or r["order2_verdict"]
        lines.append(
            f"| {r['id']} | {r.get('reference_winner') or '—'} | "
            f"{left} | {right} | {flipped} | {r.get('note', '')} |"
        )
    lines += [
        "",
        "## 结论与使用建议",
        "",
        "1. **Judge 结论不等于 ground truth**：翻转率非零即证明同一样本的判定会随位置变化——"
        "把 Judge 结果直接当门禁阈值输入会引入系统性噪声。",
        "2. **缓解手段**（行业做法）：成对比较时**固定顺序或双向各判一次取一致**、"
        "多 judge 投票、必要时人工抽检校准。",
        "3. **本实验的边界**：样本量小、轮间存在方差，指标只演示偏置的存在性与量级，"
        "不作统计显著性结论；评委模型/温度/提示词变化都会影响数值。",
        "",
    ]
    return "\n".join(lines)


def main() -> int:
    parser = argparse.ArgumentParser(description="LLM-as-Judge 位置偏置实验")
    parser.add_argument("--provider", default=None, help="覆盖 LLM provider（默认取 .env 配置）")
    parser.add_argument("--model", default=None, help="覆盖模型名")
    parser.add_argument("--limit", type=int, default=None, help="只跑前 N 组样本")
    parser.add_argument("--runs", type=int, default=1, help="重复轮数（≥2 时报告轮间方差）")
    args = parser.parse_args()

    cases = load_pairs(PAIRS_PATH, limit=args.limit)
    config = load_gateway_config(provider=args.provider, model=args.model)
    gateway = LLMGateway(config=config)

    if config.provider == "mock":
        # 离线自检：本地确定性 stub（与位置无关）——管道与指标可验证，
        # 但**无法**演示真实偏置，真实实验需接真模型。
        judge_fn = lambda q, a, b: stub_judge(q, a, b)  # noqa: E731
    else:
        judge_fn = lambda q, a, b: judge_once(gateway, question=q, first=a, second=b)  # noqa: E731

    started = time.time()
    runs_detail: list[dict] = []
    for _ in range(max(1, args.runs)):
        records = [run_pair(judge_fn, case) for case in cases]
        runs_detail.append({"summary": summarize(records), "records": records})
    summary = aggregate_runs([r["summary"] for r in runs_detail])

    report = {
        "generated_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "judge": {"provider": config.provider, "model": config.model},
        "elapsed_sec": round(time.time() - started, 2),
        "summary": summary,
        "runs": runs_detail,
        "records": runs_detail[-1]["records"],   # 末轮明细（供人读）
    }

    OUT_JSON.parent.mkdir(parents=True, exist_ok=True)
    OUT_JSON.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    OUT_MD.write_text(render_markdown(report), encoding="utf-8")

    print(
        f"[JUDGE_BIAS] provider={config.provider} model={config.model} "
        f"pairs={summary['total_pairs']} runs={summary['runs']} "
        f"flip_rate={_pct(summary['flip_rate_mean'])}"
        f"(±{_pct(summary['flip_rate_stdev'])}) "
        f"first_win_rate={_pct(summary['first_position_win_rate_mean'])}"
        f"(±{_pct(summary['first_position_win_rate_stdev'])})"
    )
    print(f"Saved: {OUT_JSON}")
    print(f"Saved: {OUT_MD}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
