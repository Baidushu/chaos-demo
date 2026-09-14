"""故障注入演示脚本 — 展示混沌工程的完整流程。

用法（服务需已启动）：
    python fault_demo.py [--base-url http://localhost:5000]

若服务端设置了 `CHAOS_ADMIN_TOKEN`（管理接口鉴权），本脚本会自动读取同名环境变量
并带上 `X-Chaos-Admin-Token` 请求头；未设置时按"鉴权未开启"处理。

演示流程：
    1. 正常请求（基线）
    2. 注入延迟故障 → 观察延迟上升
    3. 注入丢包故障 → 观察 503 错误
    4. 清除所有故障 → 观察恢复
    5. 输出对照报告
"""
from __future__ import annotations

import argparse
import json
import os
import statistics
import time
import urllib.error
import urllib.request
from pathlib import Path

REPORT_PATH = Path("reports/fault_demo_latest.json")

ADMIN_TOKEN_ENV = "CHAOS_ADMIN_TOKEN"
ADMIN_TOKEN_HEADER = "X-Chaos-Admin-Token"


def admin_headers() -> dict:
    """服务端开启了管理接口鉴权时，带上令牌头。"""
    token = os.getenv(ADMIN_TOKEN_ENV, "").strip()
    return {ADMIN_TOKEN_HEADER: token} if token else {}


def request(
    base_url: str,
    method: str,
    path: str,
    body: dict | None = None,
    *,
    admin: bool = False,
) -> dict:
    url = f"{base_url}{path}"
    data = json.dumps(body).encode() if body else None
    headers = {"Content-Type": "application/json"}
    if admin:
        headers.update(admin_headers())
    req = urllib.request.Request(url, data=data, headers=headers, method=method)
    start = time.perf_counter()
    try:
        with urllib.request.urlopen(req, timeout=10) as resp:
            status = resp.getcode()
            text = resp.read().decode()
    except urllib.error.HTTPError as e:
        status = e.code
        text = e.read().decode()
    except Exception as e:
        status = 0
        text = str(e)
    elapsed_ms = (time.perf_counter() - start) * 1000
    return {"status": status, "elapsed_ms": round(elapsed_ms, 1), "body": text[:200]}


def send_batch(base_url: str, n: int = 10) -> dict:
    """发送 n 个请求，返回统计。"""
    results = []
    for i in range(n):
        r = request(base_url, "POST", "/order", {"item_id": f"sku-{i}", "quantity": 1})
        results.append(r)

    latencies = [r["elapsed_ms"] for r in results]
    statuses = [r["status"] for r in results]
    ok = sum(1 for s in statuses if 200 <= s < 300)
    err = sum(1 for s in statuses if s >= 400)

    return {
        "count": n,
        "ok": ok,
        "errors": err,
        "latency_mean_ms": round(statistics.mean(latencies), 1),
        "latency_p95_ms": round(sorted(latencies)[int(n * 0.95)] if n > 1 else latencies[0], 1),
        "latency_min_ms": round(min(latencies), 1),
        "latency_max_ms": round(max(latencies), 1),
        "status_codes": dict(sorted({s: statuses.count(s) for s in set(statuses)}.items())),
    }


def _call_admin(base_url: str, path: str, body: dict | None = None) -> dict:
    """调用管理接口；401 时给出明确提示（而不是静默失败让人以为脚本坏了）。"""
    result = request(base_url, "POST", path, body, admin=True)
    if result["status"] == 401:
        print(
            f"  [401] 管理接口需要鉴权：请设置环境变量 {ADMIN_TOKEN_ENV} "
            f"（与服务端一致），请求头 {ADMIN_TOKEN_HEADER}"
        )
    return result


def inject_fault(base_url: str, fault_type: str, params: dict, ttl_sec: int = 30):
    _call_admin(base_url, "/fault/inject", {
        "type": fault_type,
        "params": params,
        "ttl_sec": ttl_sec,
    })


def clear_faults(base_url: str):
    _call_admin(base_url, "/fault/clear-all")


def main():
    parser = argparse.ArgumentParser(description="Fault injection demo")
    parser.add_argument("--base-url", default="http://localhost:5000")
    parser.add_argument("--requests", type=int, default=10, help="Requests per phase")
    args = parser.parse_args()
    base = args.base_url.rstrip("/")
    n = args.requests

    print(f"=== Fault Injection Demo ({base}) ===\n")

    # Phase 1: Baseline
    print("[Phase 1] Baseline (no faults)")
    baseline = send_batch(base, n)
    print(f"  ok={baseline['ok']} errors={baseline['errors']} "
          f"mean={baseline['latency_mean_ms']}ms p95={baseline['latency_p95_ms']}ms")

    # Phase 2: Latency injection
    print("\n[Phase 2] Injecting latency (200ms)")
    inject_fault(base, "latency", {"latency_ms": 200}, ttl_sec=30)
    time.sleep(0.5)
    latency_phase = send_batch(base, n)
    print(f"  ok={latency_phase['ok']} errors={latency_phase['errors']} "
          f"mean={latency_phase['latency_mean_ms']}ms p95={latency_phase['latency_p95_ms']}ms")
    clear_faults(base)
    time.sleep(0.3)

    # Phase 3: Drop injection
    print("\n[Phase 3] Injecting drop (50% rate)")
    inject_fault(base, "drop", {"drop_rate": 0.5}, ttl_sec=30)
    time.sleep(0.5)
    drop_phase = send_batch(base, n)
    print(f"  ok={drop_phase['ok']} errors={drop_phase['errors']} "
          f"mean={drop_phase['latency_mean_ms']}ms p95={drop_phase['latency_p95_ms']}ms")
    clear_faults(base)
    time.sleep(0.3)

    # Phase 4: Recovery
    print("\n[Phase 4] Recovery (faults cleared)")
    recovery = send_batch(base, n)
    print(f"  ok={recovery['ok']} errors={recovery['errors']} "
          f"mean={recovery['latency_mean_ms']}ms p95={recovery['latency_p95_ms']}ms")

    # Summary
    print("\n=== Summary ===")
    print(f"{'Phase':<20} {'OK':>4} {'Err':>4} {'Mean(ms)':>10} {'P95(ms)':>10}")
    print("-" * 52)
    for name, data in [("Baseline", baseline), ("Latency+200ms", latency_phase),
                        ("Drop 50%", drop_phase), ("Recovery", recovery)]:
        print(f"{name:<20} {data['ok']:>4} {data['errors']:>4} "
              f"{data['latency_mean_ms']:>10} {data['latency_p95_ms']:>10}")

    # Save report
    REPORT_PATH.parent.mkdir(parents=True, exist_ok=True)
    report = {
        "generated_at": int(time.time()),
        "base_url": base,
        "phases": {
            "baseline": baseline,
            "latency_200ms": latency_phase,
            "drop_50pct": drop_phase,
            "recovery": recovery,
        },
    }
    REPORT_PATH.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"\nSaved: {REPORT_PATH}")


if __name__ == "__main__":
    main()
