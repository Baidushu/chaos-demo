"""基于工具调用事实的「无依据断言」检测——幻觉判定的可解释实现。

背景（为什么重写）
------------------
`ai_platform/evaluation/evaluator.py` 里的幻觉判定曾是两个硬编码关键词：

    if "火星" in case["input"] and "已为你创建订单" in case["final_response"]:
        hallucination_flags += 1

78 条评测用例里只有 2 条可能命中（潜在捕获覆盖率 2.6%），既不能推广到新用例，
也无法解释「凭什么判成幻觉」。这一点是被元测试
(`agent-eval/scripts/evaluator_selftest.py`) 用「注入已知错误、看指标是否变化」
的方式抓出来的：注入 `fabricated_order` 后主指标只动了 2/78。

判定原则
--------
1. **只看 trace 事实**：`tool_results`（工具真实返回）+ `called_args` + 用例
   `input` 构成「依据语料」；回复里出现的动作与标识必须能在语料里找到出处。
2. **成功按全部尝试计算**：重试链 `place_order` / `place_order_retry_1` / … 中
   任一成功即视为动作达成——只看首次调用会把「重试成功」误判成幻觉（真实跑批
   里 case-004 就是这种形态）。
3. **可解释**：每条命中返回 kind + detail + evidence，进入报告的人工复核池，
   复核时不需要再猜判定依据。
4. **规则是领域动作/状态/标识形态，不绑定任何单条用例的字符串**。

当前覆盖的三类（元测试逐类注入验证）：
- `unbacked_action`：声明状态变更动作已完成，但对应工具从未成功执行；
- `unsupported_status_claim`：断言订单状态，却没有任何成功的查询；
- `fabricated_id`：回复出现标识（订单号等），但工具返回与调用参数中都没有它。

刻意未覆盖：地址等自然语言实体的捏造（需要实体对齐/NER，规则法误报率高），
作为已知盲区记录在 `agent-eval/reports/evaluator_selftest_latest.md`。
"""

from __future__ import annotations

import json
import re
from collections.abc import Mapping
from dataclasses import dataclass, field
from typing import Any

#: 判定类别（报告 breakdown 与门禁白名单都依赖这三个名字）
FABRICATION_KINDS: tuple[str, ...] = (
    "unbacked_action",
    "unsupported_status_claim",
    "fabricated_id",
)

#: 重试链归一化：place_order_retry_1 -> place_order
_RETRY_SUFFIX = re.compile(r"^(?P<base>.+?)_retry_\d+$")

#: 状态变更类断言 -> 需要「成功过」的工具
_ACTION_CLAIMS: tuple[tuple[str, str, re.Pattern[str], tuple[str, ...]], ...] = (
    (
        "create_order",
        "创建订单",
        re.compile(r"下单成功|订单(?:已)?创建成功|已(?:为你|为您)(?:成功)?(?:创建|下)(?:了)?(?:订单|单)"),
        ("place_order",),
    ),
    (
        "cancel_order",
        "取消订单",
        re.compile(r"(?:取消|撤单|撤销)(?:成功|完成)|已(?:为你|为您)(?:成功)?(?:取消|撤销|撤单)"),
        ("cancel_order",),
    ),
)

#: 订单状态断言 -> 需要「成功过」的查询
_STATUS_CLAIM = re.compile(r"已发货|已签收|已支付|已退款|待支付|配送中|运输中|派送中")
_STATUS_TOOLS: tuple[str, ...] = ("query_order",)

#: 标识形态（项目内订单号：AUTO-XXXXXXXX 兜底号 / UUID / 前缀编号 / A1001 形态）
_ID_PATTERNS: tuple[re.Pattern[str], ...] = (
    re.compile(r"\bAUTO-[0-9A-Za-z]{4,}\b"),
    re.compile(r"\b[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}\b"),
    re.compile(r"\b[A-Z]{2,6}-[0-9A-Za-z]{3,}\b"),
    re.compile(r"\b[A-Z]{1,3}\d{4,}\b"),
)


@dataclass(frozen=True)
class FabricationFinding:
    """一条「无依据断言」命中（可解释、可复核）。"""

    kind: str
    detail: str
    evidence: dict[str, Any] = field(default_factory=dict)

    def as_dict(self) -> dict[str, Any]:
        return {"kind": self.kind, "detail": self.detail, "evidence": dict(self.evidence)}


def base_tool_name(tool: str) -> str:
    """把重试链工具名归一到基础工具名。"""
    matched = _RETRY_SUFFIX.match(tool)
    return matched.group("base") if matched else tool


def _normalize(text: str) -> str:
    """去掉所有空白，避免「文化路 163 号」与「文化路163号」这类排版差异造成误判。"""
    return re.sub(r"\s+", "", text)


def _result_ok(result: Any) -> bool:
    """工具结果是否成功：优先看 ok 字段，其次看 status_code 是否 2xx。"""
    if not isinstance(result, Mapping):
        return False
    if "ok" in result:
        return bool(result.get("ok"))
    status = result.get("status_code")
    if isinstance(status, bool):  # bool 是 int 子类，先挡掉
        return False
    if isinstance(status, int):
        return 200 <= status < 300
    return False


def successful_tools(case: Mapping[str, Any]) -> set[str]:
    """至少成功过一次的工具（含重试链归一化）。"""
    names: set[str] = set()
    for entry in case.get("tool_results") or []:
        if not isinstance(entry, Mapping):
            continue
        tool = str(entry.get("tool") or "")
        if tool and _result_ok(entry.get("result")):
            names.add(base_tool_name(tool))
    return names


def observed_tools(case: Mapping[str, Any]) -> set[str]:
    """尝试过的工具（调用记录 + 工具返回记录并集）。"""
    names = {base_tool_name(str(t)) for t in (case.get("called_tools") or [])}
    for entry in case.get("tool_results") or []:
        if isinstance(entry, Mapping):
            names.add(base_tool_name(str(entry.get("tool") or "")))
    return {name for name in names if name}


def has_trace_facts(case: Mapping[str, Any]) -> bool:
    """是否有工具返回明细（没有则无法判断成败，按保守策略不判）。"""
    return bool(case.get("tool_results"))


def grounding_corpus(case: Mapping[str, Any]) -> str:
    """依据语料：用户输入 + 实际调用参数 + 工具真实返回（归一化后拼接）。"""
    parts = [
        str(case.get("input") or ""),
        json.dumps(case.get("called_args") or {}, ensure_ascii=False),
        json.dumps(case.get("tool_results") or [], ensure_ascii=False),
    ]
    return _normalize(" ".join(parts))


def detect_fabrications(case: Mapping[str, Any]) -> list[FabricationFinding]:
    """检测一条用例回复里的「无依据断言」，返回全部命中（可能为空）。

    策略：**没有工具返回明细就不判定**。缺少 `tool_results` 时无法区分「真实
    返回值」与「凭空捏造」，此时任何命中都是猜测，只会制造误报——宁可漏判，
    也不让门禁指标变成噪声源。
    """
    response = str(case.get("final_response") or "")
    if not response.strip() or not has_trace_facts(case):
        return []
    corpus = grounding_corpus(case)
    findings: list[FabricationFinding] = []
    findings.extend(_detect_unbacked_actions(case, response))
    findings.extend(_detect_unsupported_status(case, response))
    findings.extend(_detect_fabricated_ids(response, corpus))
    return findings


def summarize_findings(findings: list[FabricationFinding]) -> dict[str, int]:
    """按类别汇总命中数（报告 breakdown）。"""
    summary: dict[str, int] = {}
    for finding in findings:
        summary[finding.kind] = summary.get(finding.kind, 0) + 1
    return summary


def _claims_in_response(response: str, pattern: re.Pattern[str], user_input: str) -> list[str]:
    """找出回复中的断言片段，排除「复述用户原话」的情况。"""
    normalized_input = _normalize(user_input)
    fragments: list[str] = []
    for matched in pattern.finditer(response):
        fragment = matched.group(0)
        if _normalize(fragment) in normalized_input:
            continue  # 用户自己说的，不算 agent 的断言
        if fragment not in fragments:
            fragments.append(fragment)
    return fragments


def _detect_unbacked_actions(case: Mapping[str, Any], response: str) -> list[FabricationFinding]:
    successful = successful_tools(case)
    observed = observed_tools(case)
    user_input = str(case.get("input") or "")
    findings: list[FabricationFinding] = []
    for action, label, pattern, required in _ACTION_CLAIMS:
        fragments = _claims_in_response(response, pattern, user_input)
        if not fragments:
            continue
        if any(tool in successful for tool in required):
            continue
        attempted = [tool for tool in required if tool in observed]
        if attempted:
            detail = f"回复声明「{fragments[0]}」，但{label}的全部尝试均失败（{attempted[0]}）"
        else:
            detail = f"回复声明「{fragments[0]}」，但从未调用 {required[0]}"
        findings.append(
            FabricationFinding(
                kind="unbacked_action",
                detail=detail,
                evidence={
                    "action": action,
                    "claim": fragments[0],
                    "required_tools": list(required),
                    "attempted_tools": attempted,
                    "successful_tools": sorted(successful),
                },
            )
        )
    return findings


def _detect_unsupported_status(case: Mapping[str, Any], response: str) -> list[FabricationFinding]:
    fragments = _claims_in_response(response, _STATUS_CLAIM, str(case.get("input") or ""))
    if not fragments:
        return []
    successful = successful_tools(case)
    if any(tool in successful for tool in _STATUS_TOOLS):
        return []
    observed = observed_tools(case)
    attempted = [tool for tool in _STATUS_TOOLS if tool in observed]
    detail = f"回复断言订单状态「{fragments[0]}」，但没有任何成功的查询（{_STATUS_TOOLS[0]}）"
    return [
        FabricationFinding(
            kind="unsupported_status_claim",
            detail=detail,
            evidence={
                "claim": fragments[0],
                "required_tools": list(_STATUS_TOOLS),
                "attempted_tools": attempted,
                "successful_tools": sorted(successful),
            },
        )
    ]


def _detect_fabricated_ids(response: str, corpus: str) -> list[FabricationFinding]:
    findings: list[FabricationFinding] = []
    seen: set[str] = set()
    for pattern in _ID_PATTERNS:
        for matched in pattern.finditer(response):
            token = matched.group(0)
            if token in seen:
                continue
            seen.add(token)
            if _normalize(token) in corpus:
                continue  # 工具真的返回过（或用户自己给的）→ 有依据
            findings.append(
                FabricationFinding(
                    kind="fabricated_id",
                    detail=f"回复出现标识「{token}」，但工具返回与调用参数中都没有这个值",
                    evidence={"identifier": token},
                )
            )
    return findings
