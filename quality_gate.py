import json
import os
import sys
from pathlib import Path

#失败函数
def fail(msg: str):
    print(f"[QUALITY_GATE] FAIL: {msg}")
    sys.exit(1)


def severity_rank(level: str) -> int:
    return {"low": 1, "medium": 2, "high": 3}.get(level.lower(), 2)


def check_benchmark_gate():
    with open("reports/benchmark_latest.json", "r", encoding="utf-8") as f:
        data = json.load(f)

    baseline = data["baseline"]
    protected = data["protected"]

    # 硬性性能底线：治理版错误率不能超过5%，治理版99毫秒延迟不能超过450毫秒，治理版95毫秒延迟不能超过基线版95毫秒延迟的110%，治理版降级率和错误率不能超过35%
    if protected["error_rate"] > 0.05:
        fail(f"protected error_rate too high: {protected['error_rate']:.2%} > 5%")
    if protected["p99_ms"] > 450:
        fail(f"protected p99 too high: {protected['p99_ms']:.1f}ms > 450ms")

    # 相对性能底线：治理版95毫秒延迟不能超过基线版95毫秒延迟的110%
    if protected["p95_ms"] > baseline["p95_ms"] * 1.10:
        fail(
            "protected p95 regressed too much: "
            f"{protected['p95_ms']:.1f}ms > {baseline['p95_ms']*1.10:.1f}ms"
        )

    # 降级率和错误率不能超过35%，避免无效保护
    unstable = protected["degraded_rate"] + protected["error_rate"]
    if unstable > 0.35:
        fail(f"degraded+error too high: {unstable:.2%} > 35%")

    print(
        "[QUALITY_GATE] benchmark PASS:"
        f" p95={protected['p95_ms']:.1f}ms,"
        f" p99={protected['p99_ms']:.1f}ms,"
        f" error={protected['error_rate']:.2%},"
        f" degraded={protected['degraded_rate']:.2%}"
    )


def check_security_gate():#安全门禁：检查安全扫描报告，如果发现高危漏洞，则门禁不通过
    report_path = Path("reports/security_scan_latest.json")
    fail_on = os.getenv("SECURITY_FAIL_ON", "medium").lower()
    require_report = os.getenv("QUALITY_GATE_REQUIRE_SECURITY", "1") != "0"
    threshold = severity_rank(fail_on)

    if not report_path.exists():
        if require_report:
            fail("security report missing: reports/security_scan_latest.json (run security_scan.py first)")
        print("[QUALITY_GATE] security SKIP: report missing and gate not required")
        return

    with report_path.open("r", encoding="utf-8") as f:
        data = json.load(f)

    findings = data.get("findings", [])
    highest = 0
    sev_count = {"high": 0, "medium": 0, "low": 0}
    for item in findings:
        sev = str(item.get("severity", "low")).lower()
        sev_count[sev] = sev_count.get(sev, 0) + 1
        highest = max(highest, severity_rank(sev))

    print(
        "[QUALITY_GATE] security:"
        f" findings={len(findings)}"
        f" high={sev_count.get('high', 0)}"
        f" medium={sev_count.get('medium', 0)}"
        f" low={sev_count.get('low', 0)}"
        f" fail_on={fail_on}"
    )
    if highest >= threshold:
        fail("security findings reached fail threshold")
    print("[QUALITY_GATE] security PASS")


def main():
    check_benchmark_gate()
    check_security_gate()
    print("[QUALITY_GATE] PASS")


if __name__ == "__main__":
    main()
