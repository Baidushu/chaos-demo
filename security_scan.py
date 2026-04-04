import json
import os
import re
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path


REPORT_PATH = Path("reports/security_scan_latest.json")
REPORT_MD_PATH = Path("reports/security_scan_latest.md")
BASE_URL = os.getenv("SECURITY_SCAN_BASE_URL", "http://127.0.0.1:5000").rstrip("/")
FAIL_LEVEL = os.getenv("SECURITY_FAIL_ON", "medium").lower()  # low | medium | high

# Lightweight DAST checks for local demo
SQLI_PAYLOADS = [
    "' OR 1=1 --",
    "\" OR \"1\"=\"1",
    "'; DROP TABLE orders; --",
]

SENSITIVE_PATTERNS = [
    r"traceback",
    r"stack trace",
    r"sql syntax",
    r"exception",
    r"password",
    r"secret",
    r"api[_-]?key",
]

SEVERITY_RANK = {"low": 1, "medium": 2, "high": 3}


def do_request(method: str, path: str, payload: dict | None = None, headers: dict | None = None):
    url = f"{BASE_URL}{path}"
    body = None
    req_headers = {"Content-Type": "application/json"}
    if headers:
        req_headers.update(headers)
    if payload is not None:
        body = json.dumps(payload).encode("utf-8")

    req = urllib.request.Request(url, data=body, headers=req_headers, method=method)
    started = time.perf_counter()
    try:
        with urllib.request.urlopen(req, timeout=5) as resp:
            status = resp.getcode()
            text = resp.read().decode("utf-8", errors="ignore")
    except urllib.error.HTTPError as e:
        status = e.code
        text = e.read().decode("utf-8", errors="ignore")
    except Exception as e:
        status = 0
        text = str(e)
    elapsed_ms = (time.perf_counter() - started) * 1000
    return status, text, elapsed_ms


def add_finding(findings: list, severity: str, name: str, detail: str, evidence: str = ""):
    findings.append(
        {
            "severity": severity,
            "name": name,
            "detail": detail,
            "evidence": evidence[:300],
        }
    )


def scan():
    findings = []
    checks = []

    # health check
    st, text, ms = do_request("GET", "/healthz")
    checks.append({"name": "healthz", "status": st, "elapsed_ms": ms})
    if st != 200:
        add_finding(findings, "high", "service_unreachable", f"/healthz status={st}", text)
        return checks, findings

    # SQL injection-like payloads against POST /order
    for payload in SQLI_PAYLOADS:
        st, text, ms = do_request("POST", "/order", {"item_id": payload, "quantity": 1})
        checks.append({"name": "sqli_order_item", "payload": payload, "status": st, "elapsed_ms": ms})

        if st >= 500 or st == 0:
            add_finding(
                findings,
                "high",
                "sqli_causes_server_error",
                f"payload causes status {st}",
                text,
            )
        # Server should never echo suspicious payload back directly
        if payload.lower() in text.lower():
            add_finding(
                findings,
                "medium",
                "payload_reflection",
                "suspicious payload reflected in response",
                text,
            )

    # basic authorization probe
    st, text, ms = do_request("GET", "/order/../../etc/passwd")
    checks.append({"name": "path_traversal_style_probe", "status": st, "elapsed_ms": ms})
    if st >= 500 or st == 0:
        add_finding(findings, "high", "path_probe_server_error", f"status={st}", text)

    # sensitive information leakage detection on common responses
    for endpoint in ["/healthz", "/order/not-exist-id"]:
        st, text, ms = do_request("GET", endpoint)
        checks.append({"name": "sensitive_leak_probe", "endpoint": endpoint, "status": st, "elapsed_ms": ms})
        t = text.lower()
        for pat in SENSITIVE_PATTERNS:
            if re.search(pat, t):
                add_finding(
                    findings,
                    "medium",
                    "sensitive_info_leak",
                    f"pattern matched on {endpoint}: {pat}",
                    text,
                )
                break

    return checks, findings


def should_fail(findings: list):
    threshold = SEVERITY_RANK.get(FAIL_LEVEL, 2)
    highest = 0
    for f in findings:
        highest = max(highest, SEVERITY_RANK.get(f["severity"], 1))
    return highest >= threshold, highest


def build_markdown(checks: list, findings: list, sev_count: dict, fail: bool) -> str:
    lines = []
    lines.append("# Security Scan Report (Local Demo)")
    lines.append("")
    lines.append(f"- target: `{BASE_URL}`")
    lines.append(f"- fail_on: `{FAIL_LEVEL}`")
    lines.append(f"- total_checks: `{len(checks)}`")
    lines.append(
        "- findings: "
        f"high={sev_count.get('high', 0)}, "
        f"medium={sev_count.get('medium', 0)}, "
        f"low={sev_count.get('low', 0)}"
    )
    lines.append(f"- gate_result: `{'FAIL' if fail else 'PASS'}`")
    lines.append("")
    lines.append("## Findings")
    lines.append("")
    if not findings:
        lines.append("- No findings.")
    else:
        lines.append("| severity | name | detail | evidence (truncated) |")
        lines.append("|---|---|---|---|")
        for item in findings:
            sev = str(item.get("severity", "")).replace("|", "/")
            name = str(item.get("name", "")).replace("|", "/")
            detail = str(item.get("detail", "")).replace("|", "/")
            evidence = str(item.get("evidence", "")).replace("|", "/").replace("\n", " ")
            lines.append(f"| {sev} | {name} | {detail} | {evidence[:120]} |")
    lines.append("")
    lines.append("## Checks")
    lines.append("")
    if not checks:
        lines.append("- No checks executed.")
    else:
        lines.append("| check | status | elapsed_ms | note |")
        lines.append("|---|---:|---:|---|")
        for c in checks:
            check_name = str(c.get("name", "")).replace("|", "/")
            status = c.get("status", "")
            elapsed = c.get("elapsed_ms", 0.0)
            if isinstance(elapsed, float):
                elapsed_show = f"{elapsed:.1f}"
            else:
                elapsed_show = str(elapsed)
            note = ""
            if "payload" in c:
                note = f"payload={c.get('payload')}"
            elif "endpoint" in c:
                note = f"endpoint={c.get('endpoint')}"
            note = str(note).replace("|", "/")
            lines.append(f"| {check_name} | {status} | {elapsed_show} | {note} |")
    lines.append("")
    return "\n".join(lines) + "\n"


def main():
    checks, findings = scan()
    REPORT_PATH.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "generated_at": int(time.time()),
        "base_url": BASE_URL,
        "fail_on": FAIL_LEVEL,
        "checks": checks,
        "findings": findings,
        "finding_count": len(findings),
    }
    REPORT_PATH.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")

    fail, _ = should_fail(findings)
    sev_count = {"high": 0, "medium": 0, "low": 0}
    for f in findings:
        sev_count[f["severity"]] = sev_count.get(f["severity"], 0) + 1

    md = build_markdown(checks, findings, sev_count, fail)
    REPORT_MD_PATH.write_text(md, encoding="utf-8")

    print(f"Saved: {REPORT_PATH}")
    print(f"Saved: {REPORT_MD_PATH}")
    print(
        "[SECURITY_SCAN] "
        f"findings={len(findings)} high={sev_count['high']} "
        f"medium={sev_count['medium']} low={sev_count['low']} fail_on={FAIL_LEVEL}"
    )
    if fail:
        print("[SECURITY_SCAN] FAIL: findings reached fail threshold", file=sys.stderr)
        sys.exit(1)
    print("[SECURITY_SCAN] PASS")


if __name__ == "__main__":
    main()
