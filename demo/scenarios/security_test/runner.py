#!/usr/bin/env python3
"""Case 2: AI Security Testing — 安全测试演示。

Usage:
  python demo/scenarios/security_test/runner.py
  python demo/scenarios/security_test/runner.py --case attack-001

加载 attack_cases.json 中的攻击用例, 通过 SecurityGuard 检测,
输出 SecurityReport。
"""

from __future__ import annotations

import json
import sys
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

# ── Add project root ────────────────────────────────────────────────
_PROJECT_ROOT = Path(__file__).resolve().parents[3]
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))

from ai_platform.security.policy import SecurityPolicy
from ai_platform.security.guard import SecurityGuard
from ai_platform.security.permission import PermissionChecker
from ai_platform.security.security_result import SecurityResult
from ai_platform.observability.collector import Collector, reset_collector
from ai_platform.observability.event import AgentEvent
from ai_platform.observability.trace import SpanStatus


@dataclass
class SecurityReport:
    """安全测试报告"""
    case_id: str
    attack_type: str
    user_input: str
    blocked: bool
    reason: str
    trace_id: str = ""
    violations: list[str] = field(default_factory=list)
    risk_level: str = "none"
    check_details: dict[str, Any] = field(default_factory=dict)
    elapsed_ms: float = 0.0

    def as_dict(self) -> dict[str, Any]:
        return {
            "case_id": self.case_id,
            "attack_type": self.attack_type,
            "user_input": self.user_input,
            "blocked": self.blocked,
            "reason": self.reason,
            "trace_id": self.trace_id,
            "violations": list(self.violations),
            "risk_level": self.risk_level,
            "check_details": dict(self.check_details),
            "elapsed_ms": self.elapsed_ms,
        }


def run_security_test(case_id: str | None = None) -> dict[str, Any]:
    """运行安全测试演示。"""
    # 重置 collector 确保干净的 trace
    reset_collector()
    collector = Collector()

    # 加载攻击用例
    cases_path = Path(__file__).parent / "attack_cases.json"
    cases_data = json.loads(cases_path.read_text(encoding="utf-8"))
    attack_cases = cases_data["attack_cases"]

    if case_id:
        attack_cases = [c for c in attack_cases if c["id"] == case_id]
        if not attack_cases:
            print(f"ERROR: Case not found: {case_id}")
            sys.exit(2)

    # 使用标准 SecurityPolicy (非宽松模式)
    policy = SecurityPolicy()
    guard = SecurityGuard(policy)

    results: list[SecurityReport] = []
    stats = {"total": len(attack_cases), "blocked": 0, "passed": 0, "by_type": {}}

    for case in attack_cases:
        print(f"\n{'='*60}")
        print(f"  Case: {case['id']} | Type: {case['attack_type']} | Severity: {case['severity']}")
        print(f"  Input: {case['user_input']}")
        print(f"{'='*60}")

        start = time.perf_counter()

        # 开始 trace
        trace = collector.start_trace(metadata={"case_id": case["id"], "attack_type": case["attack_type"]})
        collector.record(AgentEvent.start(trace.trace_id, request=case["user_input"]))

        # ── 完整安全检查流水线 ──
        check_details: dict[str, Any] = {}
        blocked = False
        all_violations: list[str] = []
        worst_risk = "none"
        reason = "All checks passed"

        # Step 1: Input check (input_validator + prompt_guard)
        input_result = guard.check_input(case["user_input"])
        check_details["input_check"] = {
            "check_name": input_result.check_name,
            "passed": input_result.passed,
            "risk_level": input_result.risk_level,
            "violations": input_result.violations,
        }
        if not input_result.passed:
            blocked = True
            all_violations.extend(input_result.violations)
            worst_risk = input_result.risk_level
            reason = f"Input blocked: {', '.join(input_result.violations)}"

        # Step 2: 如果有工具名, 做 permission check
        if "tool_name" in case:
            perm_checker = PermissionChecker(policy)
            # 把恶意工具加入 blocklist
            policy.blocked_tools.append(case["tool_name"])
            perm_result = perm_checker.check(case["tool_name"])
            check_details["permission_check"] = {
                "check_name": perm_result.check_name,
                "passed": perm_result.passed,
                "tool_name": case["tool_name"],
                "violations": perm_result.violations,
            }
            if not perm_result.passed:
                blocked = True
                all_violations.extend(perm_result.violations)
                if perm_result.risk_level != "none":
                    worst_risk = perm_result.risk_level
                reason = f"Permission blocked: {', '.join(perm_result.violations)}"

        elapsed_ms = (time.perf_counter() - start) * 1000

        # 结束 trace
        collector.finish_trace(trace)

        report = SecurityReport(
            case_id=case["id"],
            attack_type=case["attack_type"],
            user_input=case["user_input"],
            blocked=blocked,
            reason=reason,
            trace_id=trace.trace_id,
            violations=all_violations,
            risk_level=worst_risk,
            check_details=check_details,
            elapsed_ms=round(elapsed_ms, 1),
        )

        results.append(report)
        _print_security_result(report, case)

        # 统计
        if blocked:
            stats["blocked"] += 1
        else:
            stats["passed"] += 1
        atype = case["attack_type"]
        if atype not in stats["by_type"]:
            stats["by_type"][atype] = {"total": 0, "blocked": 0}
        stats["by_type"][atype]["total"] += 1
        if blocked:
            stats["by_type"][atype]["blocked"] += 1

    # ── 总结 ──
    print(f"\n{'='*60}")
    print(f"  SECURITY TEST SUMMARY")
    print(f"{'='*60}")
    print(f"  Total cases:    {stats['total']}")
    print(f"  Blocked:        {stats['blocked']} ({stats['blocked']/max(stats['total'],1)*100:.0f}%)")
    print(f"  Passed:         {stats['passed']} ({stats['passed']/max(stats['total'],1)*100:.0f}%)")
    print(f"  By attack type:")
    for atype, s in sorted(stats["by_type"].items()):
        rate = f"{s['blocked']}/{s['total']}"
        print(f"    {atype:<30s} blocked={rate}")

    return {
        "scenario": "AI Security Testing",
        "results": [r.as_dict() for r in results],
        "total": len(results),
        "stats": stats,
    }


def _print_security_result(report: SecurityReport, case: dict[str, Any]) -> None:
    """打印安全检测结果。"""
    expected_blocked = case.get("expected_blocked", False)

    if report.blocked:
        match = "✅" if expected_blocked else "⚠️  UNEXPECTED"
        print(f"\n  🛡️  SECURITY: BLOCKED {match}")
        print(f"  检测到攻击:  {report.attack_type}")
        print(f"  风险等级:    {report.risk_level}")
        print(f"  违规详情:")
        for v in report.violations:
            print(f"    • {v}")
        print(f"  Trace ID:    {report.trace_id}")
    else:
        match = "✅" if not expected_blocked else "❌ MISSED"
        print(f"\n  ✅ SECURITY: PASSED {match}")
        print(f"  类型:        {report.attack_type} (benign)")
        print(f"  说明:        {report.reason}")
        print(f"  Trace ID:    {report.trace_id}")

    print(f"  耗时:        {report.elapsed_ms:.2f}ms")


if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser(description="AI Security Testing Demo")
    parser.add_argument("--case", type=str, default=None, help="Run specific case (e.g. attack-001)")
    parser.add_argument("--json", action="store_true", help="Output results as JSON")
    args = parser.parse_args()

    result = run_security_test(args.case)

    if args.json:
        print(json.dumps(result, ensure_ascii=False, indent=2))
