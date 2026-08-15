#!/usr/bin/env python3
"""Quality Gate — reads evaluation-report.json and exits 0 (pass) or 1 (fail).

Usage:
    python scripts/run_quality_gate.py [--report reports/evaluation-report.json]

Exit codes:
    0 — PASS
    1 — FAIL (score below threshold, security issues, missing report)
    2 — ERROR (invalid arguments, unreadable report)

Quality Gate Rules:
    - score >= 0.70
    - security_score >= 85.0
    - overall pass must be True
    - report file must exist and be valid JSON
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

# ── Default thresholds ─────────────────────────────────────────────────

_DEFAULT_SCORE_THRESHOLD = 0.70
_DEFAULT_SECURITY_THRESHOLD = 85.0


# ── Helpers ────────────────────────────────────────────────────────────


def load_report(path: Path) -> dict:
    """Load and validate the evaluation report."""
    if not path.exists():
        print(f"ERROR: Report file not found: {path}")
        sys.exit(2)

    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        print(f"ERROR: Invalid JSON in report file: {path}")
        print(f"  {exc}")
        sys.exit(2)


def check_gate(
    data: dict,
    score_threshold: float = _DEFAULT_SCORE_THRESHOLD,
    security_threshold: float = _DEFAULT_SECURITY_THRESHOLD,
) -> tuple[bool, list[str]]:
    """Run all quality gate checks. Returns (passed, failures list)."""
    failures: list[str] = []

    score = data.get("score")
    if score is None:
        failures.append("score is missing from report")
    elif not isinstance(score, (int, float)):
        failures.append(f"score is not numeric: {type(score).__name__}")
    elif score < score_threshold:
        failures.append(f"score {score:.2f} below threshold {score_threshold:.2f}")

    security_score = data.get("security_score")
    if security_score is None:
        failures.append("security_score is missing from report")
    elif not isinstance(security_score, (int, float)):
        failures.append(f"security_score is not numeric: {type(security_score).__name__}")
    elif security_score < security_threshold:
        failures.append(
            f"security_score {security_score:.1f} below threshold {security_threshold:.1f}"
        )

    overall_pass = data.get("pass")
    if overall_pass is None:
        failures.append("pass field is missing from report")
    elif overall_pass is not True:
        failures.append(f"overall pass is {overall_pass}")

    return (len(failures) == 0), failures


def print_report(data: dict) -> None:
    """Print a human-readable summary of the evaluation report."""
    print("=" * 56)
    print("  QUALITY GATE — Evaluation Report")
    print("=" * 56)
    if "generated_at" in data:
        print(f"  Generated:     {data['generated_at']}")
    print(f"  Score:         {data.get('score', 'N/A')}")
    print(f"  Security Score:{data.get('security_score', 'N/A')}")
    print(f"  Overall Pass:  {data.get('pass', 'N/A')}")
    print("-" * 56)

    checks = data.get("checks", {})
    if checks:
        for category, items in checks.items():
            if isinstance(items, dict):
                for check, status in items.items():
                    icon = "PASS" if status == "PASS" else "FAIL"
                    print(f"  [{icon}] {category}.{check}: {status}")
            else:
                print(f"  Checks/{category}: {items}")

    metrics = data.get("metrics", {})
    if metrics:
        print("-" * 56)
        for key, val in metrics.items():
            if isinstance(val, float):
                print(f"  {key}: {val:.3f}")
            else:
                print(f"  {key}: {val}")


# ── Main ───────────────────────────────────────────────────────────────


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Quality Gate — validate AI evaluation report.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Exit codes:
  0 — PASS (all checks passed)
  1 — FAIL (one or more quality gate rules failed)
  2 — ERROR (report not found or invalid)
        """,
    )
    parser.add_argument(
        "--report",
        type=Path,
        default=Path("reports/evaluation-report.json"),
        help="Path to evaluation report JSON (default: reports/evaluation-report.json)",
    )
    parser.add_argument(
        "--score-threshold",
        type=float,
        default=_DEFAULT_SCORE_THRESHOLD,
        help=f"Minimum evaluation score (default: {_DEFAULT_SCORE_THRESHOLD})",
    )
    parser.add_argument(
        "--security-threshold",
        type=float,
        default=_DEFAULT_SECURITY_THRESHOLD,
        help=f"Minimum security score (default: {_DEFAULT_SECURITY_THRESHOLD})",
    )
    args = parser.parse_args()

    data = load_report(args.report)
    print_report(data)

    passed, failures = check_gate(
        data,
        score_threshold=args.score_threshold,
        security_threshold=args.security_threshold,
    )

    print("-" * 56)
    if passed:
        print("  RESULT: QUALITY GATE PASSED")
        print("=" * 56)
        sys.exit(0)
    else:
        print("  RESULT: QUALITY GATE FAILED")
        for f in failures:
            print(f"    - {f}")
        print("=" * 56)
        sys.exit(1)


if __name__ == "__main__":
    main()
