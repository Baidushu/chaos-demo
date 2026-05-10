import json
import os
import sys
import time
from pathlib import Path

class QualityGateError(Exception):
    """可由 `unified_quality_gate` 捕获；`main()` 仍会转为进程退出码 1。"""


def fail(msg: str):
    print(f"[QUALITY_GATE] FAIL: {msg}")
    raise QualityGateError(msg)


def severity_rank(level: str) -> int:
    return {"low": 1, "medium": 2, "high": 3}.get(level.lower(), 2)


def run_check_with_retries(check_name: str, check_fn):
    """Run a gate check with optional retries to reduce transient flakes."""
    attempts = int(os.getenv("QUALITY_GATE_RETRY_ATTEMPTS", "1"))
    delay_ms = int(os.getenv("QUALITY_GATE_RETRY_DELAY_MS", "1000"))
    attempts = max(1, attempts)
    delay_sec = max(0, delay_ms) / 1000.0
    last_err = None

    for i in range(1, attempts + 1):
        try:
            ret = check_fn()
            if i > 1:
                print(f"[QUALITY_GATE] {check_name} PASS after retry {i}/{attempts}")
            return ret
        except SystemExit as e:
            if getattr(e, "code", None) in (0, None):
                return None
            last_err = e
            if i >= attempts:
                raise
            print(
                f"[QUALITY_GATE] {check_name} retrying {i}/{attempts} "
                f"(wait={delay_ms}ms)"
            )
            if delay_sec > 0:
                time.sleep(delay_sec)
        except QualityGateError as e:
            last_err = e
            if i >= attempts:
                raise
            print(
                f"[QUALITY_GATE] {check_name} retrying {i}/{attempts} "
                f"(wait={delay_ms}ms)"
            )
            if delay_sec > 0:
                time.sleep(delay_sec)
    if last_err is not None:
        raise last_err
    return None


def load_benchmark_thresholds():
    """Benchmark gate thresholds, configurable via env vars."""
    return {
        "error_rate_max": float(os.getenv("QUALITY_GATE_ERROR_RATE_MAX", "0.05")),
        "p99_ms_max": float(os.getenv("QUALITY_GATE_P99_MS_MAX", "450")),
        "p95_regression_factor_max": float(
            os.getenv("QUALITY_GATE_P95_REGRESSION_FACTOR_MAX", "1.10")
        ),
        "unstable_rate_max": float(os.getenv("QUALITY_GATE_UNSTABLE_RATE_MAX", "0.35")),
        "p95_stdev_max": float(os.getenv("QUALITY_GATE_P95_STDEV_MAX", "0")),
    }


def check_report_freshness(data: dict, report_name: str):
    """Optionally enforce max age for generated reports."""
    enabled = os.getenv("QUALITY_GATE_CHECK_FRESHNESS", "1") != "0"
    if not enabled:
        return

    max_age_sec = int(os.getenv("QUALITY_GATE_MAX_REPORT_AGE_SEC", "3600"))
    generated_at = data.get("generated_at")
    if generated_at is None:
        fail(f"{report_name} report missing generated_at")
    try:
        age_sec = int(time.time()) - int(generated_at)
    except (TypeError, ValueError):
        fail(f"{report_name} report has invalid generated_at: {generated_at}")
    if age_sec < 0:
        fail(f"{report_name} report generated_at is in the future")
    if age_sec > max_age_sec:
        fail(
            f"{report_name} report is stale: age={age_sec}s > max={max_age_sec}s "
            "(rerun producer step in this pipeline)"
        )
    print(
        f"[QUALITY_GATE] freshness PASS: {report_name} age={age_sec}s max={max_age_sec}s"
    )


def check_benchmark_gate():
    with open("reports/benchmark_latest.json", "r", encoding="utf-8") as f:
        data = json.load(f)
    check_report_freshness(data, "benchmark")
    t = load_benchmark_thresholds()

    baseline = data["baseline"]
    protected = data["protected"]

    # 硬性性能底线（支持环境变量覆盖）
    if protected["error_rate"] > t["error_rate_max"]:
        fail(
            "protected error_rate too high: "
            f"{protected['error_rate']:.2%} > {t['error_rate_max']:.2%}"
        )
    if protected["p99_ms"] > t["p99_ms_max"]:
        fail(f"protected p99 too high: {protected['p99_ms']:.1f}ms > {t['p99_ms_max']:.1f}ms")

    # 相对性能底线：治理版95毫秒延迟不能超过基线 * 回归系数
    p95_limit = baseline["p95_ms"] * t["p95_regression_factor_max"]
    if protected["p95_ms"] > p95_limit:
        fail(
            "protected p95 regressed too much: "
            f"{protected['p95_ms']:.1f}ms > {p95_limit:.1f}ms "
            f"(factor={t['p95_regression_factor_max']:.2f})"
        )

    # 降级率和错误率不能超过阈值，避免无效保护
    unstable = protected["degraded_rate"] + protected["error_rate"]
    if unstable > t["unstable_rate_max"]:
        fail(f"degraded+error too high: {unstable:.2%} > {t['unstable_rate_max']:.2%}")

    protected_summary = data.get("protected_summary") or {}
    p95_summary = (protected_summary.get("summary") or {}).get("p95_ms") or {}
    p95_stdev_max = t["p95_stdev_max"]
    p95_stdev = float(p95_summary.get("stdev", 0.0) or 0.0)
    if p95_stdev_max > 0 and p95_stdev > p95_stdev_max:
        fail(
            "protected p95 jitter too high: "
            f"{p95_stdev:.1f}ms > {p95_stdev_max:.1f}ms"
        )

    run_count = protected.get("run_count", 1)
    aggregation = protected.get("aggregation", "single_run")
    print(
        "[QUALITY_GATE] benchmark PASS:"
        f" p95={protected['p95_ms']:.1f}ms,"
        f" p99={protected['p99_ms']:.1f}ms,"
        f" error={protected['error_rate']:.2%},"
        f" degraded={protected['degraded_rate']:.2%},"
        f" runs={run_count},"
        f" aggregation={aggregation},"
        f" p95_stdev={p95_stdev:.1f}ms,"
        f" thresholds(error<={t['error_rate_max']:.2%},"
        f" p99<={t['p99_ms_max']:.1f}ms,"
        f" p95_factor<={t['p95_regression_factor_max']:.2f},"
        f" unstable<={t['unstable_rate_max']:.2%},"
        f" p95_stdev<={p95_stdev_max:.1f}ms when enabled)"
    )


def security_report_meta(data: dict) -> str:
    """测开可读：扫描报告里的策略元数据，便于流水线日志对齐产物。"""
    bits = []
    if "context_aware" in data:
        bits.append(f"context_aware={data.get('context_aware')}")
    bu = data.get("base_url")
    if bu:
        bits.append(f"target={bu}")
    return (" " + " ".join(bits)) if bits else ""


def check_security_gate():#安全门禁：检查安全扫描报告，如果发现高危漏洞，则门禁不通过
    report_path = Path("reports/security_scan_latest.json")
    fail_on = os.getenv("SECURITY_FAIL_ON", "medium").lower()
    require_report = os.getenv("QUALITY_GATE_REQUIRE_SECURITY", "1") != "0"
    threshold = severity_rank(fail_on)

    if not report_path.exists():
        if require_report:
            fail("security report missing: reports/security_scan_latest.json (run security_scan.py first)")
        print("[QUALITY_GATE] security SKIP: report missing and gate not required")
        return "SKIPPED"

    with report_path.open("r", encoding="utf-8") as f:
        data = json.load(f)
    check_report_freshness(data, "security")

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
        f"{security_report_meta(data)}"
    )
    if highest >= threshold:
        fail("security findings reached fail threshold")
    print("[QUALITY_GATE] security PASS")
    return "PASS"


def main():
    try:
        run_check_with_retries("benchmark", check_benchmark_gate)
        run_check_with_retries("security", check_security_gate)
    except QualityGateError:
        sys.exit(1)
    print("[QUALITY_GATE] PASS")


if __name__ == "__main__":
    main()
