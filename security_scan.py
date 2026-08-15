import json
import os
import re
import sys
import time
import urllib.error
import urllib.request
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path


REPORT_PATH = Path("reports/security_scan_latest.json")
REPORT_MD_PATH = Path("reports/security_scan_latest.md")
BASE_URL = os.getenv("SECURITY_SCAN_BASE_URL", "http://127.0.0.1:5000").rstrip("/")
FAIL_LEVEL = os.getenv("SECURITY_FAIL_ON", "medium").lower()  # low | medium | high
HEALTH_RETRY_ATTEMPTS = int(os.getenv("SECURITY_HEALTH_RETRY_ATTEMPTS", "5"))
HEALTH_RETRY_DELAY_MS = int(os.getenv("SECURITY_HEALTH_RETRY_DELAY_MS", "500"))
SCAN_WORKERS = int(os.getenv("SECURITY_SCAN_WORKERS", "4"))
# 测开向：结合 HTTP 状态与响应体降低误报（如 2xx 回显 item_id、泛化 5xx 无 DB 指纹）
CONTEXT_AWARE = os.getenv("SECURITY_SCAN_CONTEXT_AWARE", "true").strip().lower() in (
    "1",
    "true",
    "yes",
    "on",
)
# 认证支持：优先使用 SECURITY_SCAN_AUTH_TOKEN，其次 AUTH_TOKEN；API Key 可按头名注入
AUTH_TOKEN = os.getenv("SECURITY_SCAN_AUTH_TOKEN", os.getenv("AUTH_TOKEN", "")).strip()
API_KEY = os.getenv("SECURITY_SCAN_API_KEY", "").strip()
API_KEY_HEADER = os.getenv("SECURITY_SCAN_API_KEY_HEADER", "X-Api-Key").strip() or "X-Api-Key"

# Lightweight DAST checks for local demo
#SQL注入的payloads，用于测试SQL注入 漏洞预定义的恶意字符，尝试破坏 SQL 语义。
SQLI_PAYLOADS = [
    "' OR 1=1 --",
    "\" OR \"1\"=\"1",
    "'; DROP TABLE orders; --",
]

#敏感信息泄露的关键词，用于测试敏感信息泄露，防止由于后端报错过于详细而泄露服务器内部结构
SENSITIVE_PATTERNS = [
    r"traceback",
    r"stack trace",
    r"sql syntax",
    r"exception",
    r"password",
    r"secret",
    r"api[_-]?key",
]
#严重程度排名，用于确定安全扫描的严重程度
SEVERITY_RANK = {"low": 1, "medium": 2, "high": 3}

# 5xx/连接失败体中出现时，与「恶意 payload 探测」联合判为高危（偏 SQL/驱动栈）
SQL_BODY_DB_SIGNAL = re.compile(
    r"sql syntax|syntax error near|syntax error at|sqlite|mysql|mariadb|"
    r"postgres|postgresql|ora-\d{4,5}|odbc|driver|operationalerror|"
    r"sqlexception|invalid column|unknown column|table .* doesn'?t exist",
    re.I,
)

#发送请求，用于发送请求到目标网站
#请求过程：
#1. 构建请求URL：构建请求URL
#2. 构建请求体：构建请求体
#3. 构建请求头：构建请求头
#4. 发送请求：发送请求
#5. 返回请求结果：返回请求结果
#6. 计算请求时间：计算请求时间
#7. 返回请求结果：返回请求结果
def do_request(method: str, path: str, payload: dict | None = None, headers: dict | None = None):
    url = f"{BASE_URL}{path}"
    body = None
    req_headers = {"Content-Type": "application/json"}
    if AUTH_TOKEN:
        req_headers["Authorization"] = f"Bearer {AUTH_TOKEN}"
    if API_KEY:
        req_headers[API_KEY_HEADER] = API_KEY
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


def health_check_with_retry():
    """Retry healthz briefly to reduce transient false positives after benchmark load."""
    attempts = max(1, HEALTH_RETRY_ATTEMPTS)
    delay_sec = max(0, HEALTH_RETRY_DELAY_MS) / 1000.0
    last = (0, "health check not executed", 0.0)
    for i in range(attempts):
        last = do_request("GET", "/healthz")
        status, _, _ = last
        if status == 200:
            return last, i + 1
        if i < attempts - 1 and delay_sec > 0:
            time.sleep(delay_sec)
    return last, attempts


def add_finding(findings: list, severity: str, name: str, detail: str, evidence: str = ""):
    findings.append(
        {
            "severity": severity,
            "name": name,
            "detail": detail,
            "evidence": evidence[:300],
        }
    )


def analyze_sqli_probe(status: int, text: str, payload: str) -> list[dict]:
    """根据状态码 + 响应体生成 SQLi 探针类 findings（可单测，供测开调门禁策略）。"""
    findings: list[dict] = []
    raw = text or ""
    evidence = raw[:300]
    tl = raw.lower()
    pl = payload.lower()

    if status >= 500 or status == 0:
        if CONTEXT_AWARE:
            if SQL_BODY_DB_SIGNAL.search(raw):
                findings.append(
                    {
                        "severity": "high",
                        "name": "sqli_db_or_sql_signal_in_error_body",
                        "detail": f"status={status} and body suggests SQL/DB stack under payload probe",
                        "evidence": evidence,
                    }
                )
            else:
                findings.append(
                    {
                        "severity": "medium",
                        "name": "sqli_probe_server_error_ambiguous",
                        "detail": f"status={status} without clear SQL/DB fingerprint (review body)",
                        "evidence": evidence,
                    }
                )
        else:
            findings.append(
                {
                    "severity": "high",
                    "name": "sqli_causes_server_error",
                    "detail": f"payload causes status {status}",
                    "evidence": evidence,
                }
            )

    if pl in tl:
        if CONTEXT_AWARE:
            if 200 <= status < 300:
                findings.append(
                    {
                        "severity": "low",
                        "name": "payload_reflection_in_success_body",
                        "detail": "payload echoed in 2xx body (often benign field echo; verify intent)",
                        "evidence": evidence,
                    }
                )
            elif 300 <= status < 400:
                findings.append(
                    {
                        "severity": "low",
                        "name": "payload_reflection_redirect_family",
                        "detail": f"payload reflected with status={status}",
                        "evidence": evidence,
                    }
                )
            elif 400 <= status < 500:
                findings.append(
                    {
                        "severity": "medium",
                        "name": "payload_reflection_client_error",
                        "detail": "payload reflected in 4xx response (verbose error or echo)",
                        "evidence": evidence,
                    }
                )
            else:
                findings.append(
                    {
                        "severity": "medium",
                        "name": "payload_reflection_server_or_transport_error",
                        "detail": f"payload reflected with status={status}",
                        "evidence": evidence,
                    }
                )
        else:
            findings.append(
                {
                    "severity": "medium",
                    "name": "payload_reflection",
                    "detail": "suspicious payload reflected in response",
                    "evidence": evidence,
                }
            )
    return findings


def run_sqli_check(payload: str):
    st, text, ms = do_request("POST", "/order", {"item_id": payload, "quantity": 1})
    check = {
        "name": "sqli_order_item",
        "payload": payload,
        "status": st,
        "elapsed_ms": ms,
        "context_aware": CONTEXT_AWARE,
    }
    findings = analyze_sqli_probe(st, text, payload)
    return check, findings

#扫描函数，用于扫描目标网站的安全性
#扫描过程：
#1. 健康检查：检查目标网站是否可达
#2. SQL注入测试：测试目标网站是否存在SQL注入漏洞
#3. 路径遍历测试：测试目标网站是否存在路径遍历漏洞
#4. 敏感信息泄露测试：测试目标网站是否存在敏感信息泄露漏洞
#5. 返回扫描结果
def scan():
    findings = []
    checks = []

    # health check：健康检查，检查目标网站是否可达
    (st, text, ms), tries = health_check_with_retry()
    checks.append(
        {
            "name": "healthz",
            "status": st,
            "elapsed_ms": ms,
            "attempts": tries,
        }
    )
    if st != 200:
        add_finding(
            findings,
            "high",
            "service_unreachable",
            f"/healthz status={st} after {tries} attempts",
            text,
        )
        return checks, findings

    # SQL injection-like payloads against POST /order：并发执行可缩短扫描耗时
    workers = max(1, min(SCAN_WORKERS, len(SQLI_PAYLOADS)))
    if workers == 1:
        for payload in SQLI_PAYLOADS:
            check, found = run_sqli_check(payload)
            checks.append(check)
            findings.extend(found)
    else:
        ordered = {}
        with ThreadPoolExecutor(max_workers=workers) as pool:
            future_map = {
                pool.submit(run_sqli_check, payload): idx
                for idx, payload in enumerate(SQLI_PAYLOADS)
            }
            for fut in as_completed(future_map):
                idx = future_map[fut]
                check, found = fut.result()
                ordered[idx] = (check, found)
        for idx in range(len(SQLI_PAYLOADS)):
            check, found = ordered[idx]
            checks.append(check)
            findings.extend(found)

    # basic authorization probe：基本授权测试，测试目标网站是否存在基本授权漏洞
    st, text, ms = do_request("GET", "/order/../../etc/passwd")
    checks.append({"name": "path_traversal_style_probe", "status": st, "elapsed_ms": ms})
    if st >= 500 or st == 0:
        add_finding(findings, "high", "path_probe_server_error", f"status={st}", text)

    # sensitive information leakage detection on common responses：敏感信息泄露检测，检测目标网站是否存在敏感信息泄露漏洞
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

#判断是否失败，用于确定安全扫描是否失败
#判断过程：
#1. 获取失败阈值：获取失败阈值
#2. 获取最高严重程度：获取最高严重程度
#3. 返回是否失败：返回是否失败
def should_fail(findings: list):
    threshold = SEVERITY_RANK.get(FAIL_LEVEL, 2)
    highest = 0
    for f in findings:
        highest = max(highest, SEVERITY_RANK.get(f["severity"], 1))
    return highest >= threshold, highest

#生成Markdown报告，用于生成安全扫描报告
#报告内容：
#1. 目标网站：目标网站
#2. 失败阈值：失败阈值
#3. 总检查数：总检查数
#4. 发现数量：发现数量
#5. 返回是否失败：返回是否失败
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

#主函数，用于执行安全扫描并生成报告
#扫描过程：
#1. 执行扫描：执行安全扫描并生成报告
#2. 保存报告：保存扫描结果到文件
#3. 生成报告：生成扫描报告
#4. 返回扫描结果
def main():
    checks, findings = scan()
    REPORT_PATH.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "generated_at": int(time.time()),
        "base_url": BASE_URL,
        "fail_on": FAIL_LEVEL,
        "context_aware": CONTEXT_AWARE,
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
