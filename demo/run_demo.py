#!/usr/bin/env python3
"""Chaos-Demo AI Platform — 统一Demo入口。

Usage:
  python demo/run_demo.py incident                    # Case 1: 故障分析
  python demo/run_demo.py incident --case incident-001
  python demo/run_demo.py security                    # Case 2: 安全测试
  python demo/run_demo.py security --json
  python demo/run_demo.py regression                  # Case 3: 质量回归 (退化场景)
  python demo/run_demo.py regression --mode pass      # Case 3: 质量回归 (通过场景)
  python demo/run_demo.py all                         # 全部三个场景
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

# ── Add project root ────────────────────────────────────────────────
_PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Chaos-Demo AI Platform — Enterprise Demo Scenarios",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  python demo/run_demo.py incident
  python demo/run_demo.py security --json
  python demo/run_demo.py regression --mode pass
  python demo/run_demo.py all
        """,
    )
    sub = parser.add_subparsers(dest="command", title="scenarios")

    # ── incident ──
    p_incident = sub.add_parser("incident", help="AI Incident Diagnosis (故障分析)")
    p_incident.add_argument("--case", type=str, default=None, help="Run specific case")

    # ── security ──
    p_security = sub.add_parser("security", help="AI Security Testing (安全测试)")
    p_security.add_argument("--case", type=str, default=None, help="Run specific case")
    p_security.add_argument("--json", action="store_true", help="Output as JSON")

    # ── regression ──
    p_regression = sub.add_parser("regression", help="AI Regression Quality Gate (质量回归)")
    p_regression.add_argument("--mode", type=str, choices=["pass", "fail"], default="fail",
                              help="fail=退化场景, pass=通过场景")
    p_regression.add_argument("--json", action="store_true", help="Output as JSON")

    # ── all ──
    sub.add_parser("all", help="Run all three scenarios")

    args = parser.parse_args()

    if args.command is None:
        parser.print_help()
        return

    results: dict[str, any] = {}

    if args.command in ("incident", "all"):
        print("\n" + "=" * 60)
        print("  SCENARIO 1: AI Incident Diagnosis")
        print("=" * 60)
        from demo.scenarios.incident_analysis.runner import run_incident_diagnosis
        results["incident"] = run_incident_diagnosis(args.case if args.command == "incident" else None)

    if args.command in ("security", "all"):
        print("\n" + "=" * 60)
        print("  SCENARIO 2: AI Security Testing")
        print("=" * 60)
        from demo.scenarios.security_test.runner import run_security_test
        sec_result = run_security_test(args.case if args.command == "security" else None)
        results["security"] = sec_result
        if getattr(args, "json", False) and args.command == "security":
            print(json.dumps(sec_result, ensure_ascii=False, indent=2))
            return

    if args.command in ("regression", "all"):
        mode = getattr(args, "mode", "fail") or "fail"
        print("\n" + "=" * 60)
        print(f"  SCENARIO 3: AI Regression Quality Gate ({mode.upper()})")
        print("=" * 60)
        from demo.scenarios.regression.runner import run_regression_gate
        reg_result = run_regression_gate(mode)
        results["regression"] = reg_result
        if getattr(args, "json", False) and args.command == "regression":
            print(json.dumps(reg_result, ensure_ascii=False, indent=2))
            return

    if args.command == "all":
        _print_all_summary(results)


def _print_all_summary(results: dict) -> None:
    print("\n" + "=" * 60)
    print("  ALL SCENARIOS COMPLETE — Summary")
    print("=" * 60)

    # Incident summary
    if "incident" in results:
        inc = results["incident"]
        passed = sum(1 for r in inc["results"] if r["success"])
        print(f"\n  [Report] Incident Diagnosis: {passed}/{inc['total']} cases passed")

    # Security summary
    if "security" in results:
        sec = results["security"]
        s = sec.get("stats", {})
        print(f"\n  [Guard] Security Testing: {s['blocked']}/{s['total']} attacks blocked")

    # Regression summary
    if "regression" in results:
        reg = results["regression"]
        print(f"\n  [Gate] Regression Gate: {reg['report']['gate_status']} "
              f"(baseline={reg['report']['baseline_score']}, "
              f"current={reg['report']['current_score']})")

    print(f"\n{'=' * 60}\n")


if __name__ == "__main__":
    main()
