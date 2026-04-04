import json
import os
import statistics
import sys
import time
import urllib.error
import urllib.request
import uuid
from concurrent.futures import ThreadPoolExecutor, as_completed

#向服务器发一次下单请求，返回状态码和延迟时间
def one_request(base_url: str):
    #请求体,包含商品ID和数量
    payload = json.dumps({"item_id": "sku-bench", "quantity": 1}).encode()
    #请求头,包含内容类型和幂等键
    headers = {
        "Content-Type": "application/json",
        "X-Idempotency-Key": str(uuid.uuid4()),
    }
    #请求对象,包含请求体,请求头,请求方法
    req = urllib.request.Request(
        f"{base_url}/order",
        data=payload,
        headers=headers,
        method="POST",
    )
    start = time.perf_counter()
    try:
        with urllib.request.urlopen(req, timeout=5) as resp:
            status = resp.getcode()
            _ = resp.read()
    except urllib.error.HTTPError as e:
        status = e.code
    except Exception:
        status = 0
    latency_ms = (time.perf_counter() - start) * 1000
    return status, latency_ms

#压测函数，并发20个请求，总共200次请求
def run_benchmark(base_url: str, total_requests: int = 200, concurrency: int = 20):
    latencies = []#延迟时间列表:记录每个请求跑了多少毫秒
    status_count = {}#状态码计数器:记录每个状态码出现了多少次
    start = time.perf_counter()#开始时间
    with ThreadPoolExecutor(max_workers=concurrency) as pool:#创建一个线程池，最大并发数为20
        futures = [pool.submit(one_request, base_url) for _ in range(total_requests)]#提交请求
        for fut in as_completed(futures):#等待请求完成
            status, latency = fut.result()
            latencies.append(latency)#添加延迟时间
            status_count[status] = status_count.get(status, 0) + 1#添加状态码计数   （状态码计数器）
    elapsed = time.perf_counter() - start
    success = status_count.get(201, 0) + status_count.get(200, 0)#成功请求数
    degraded = status_count.get(202, 0)#降级请求数
    limited = status_count.get(429, 0)#限流请求数
    errors = sum(v for k, v in status_count.items() if k >= 500 or k == 0)#错误请求数

    return {#返回结果   
        "qps": total_requests / elapsed if elapsed > 0 else 0,
        "p50_ms": statistics.quantiles(latencies, n=100)[49] if latencies else 0,
        "p95_ms": statistics.quantiles(latencies, n=100)[94] if latencies else 0,
        "p99_ms": statistics.quantiles(latencies, n=100)[98] if latencies else 0,
        "success_rate": success / total_requests,
        "degraded_rate": degraded / total_requests,
        "limited_rate": limited / total_requests,
        "error_rate": errors / total_requests,
        "status_count": status_count,
    }


def print_md_row(name, data):
    print(
        f"| {name} | {data['qps']:.1f} | {data['p95_ms']:.1f} | {data['p99_ms']:.1f} | "
        f"{data['success_rate']*100:.1f}% | {data['degraded_rate']*100:.1f}% | "
        f"{data['limited_rate']*100:.1f}% | {data['error_rate']*100:.1f}% |"
    )


def probe_health(base_url: str, label: str) -> None:
    """压测前探测，避免服务未启动时 200 次请求慢失败。"""
    url = f"{base_url.rstrip('/')}/healthz"
    try:
        urllib.request.urlopen(url, timeout=3)
    except Exception as e:
        print(
            "[benchmark_compare] ERROR: 服务不可达 —— "
            f"{label} ({base_url})\n"
            "  请先启动 Docker Desktop，再在项目根目录执行:\n"
            "    docker compose up --build -d\n"
            "  并等待浏览器或 curl 能访问: http://127.0.0.1:5000/healthz\n"
            f"  原始错误: {e}",
            file=sys.stderr,
        )
        sys.exit(1)


if __name__ == "__main__":
    # 1. 先测 Baseline (5001端口：没有保护的原始版)
    probe_health("http://127.0.0.1:5001", "Baseline :5001")
    # 2. 再测 Protected (5000端口：有保护的治理版)
    probe_health("http://127.0.0.1:5000", "Protected :5000")
    # 3. 然后压测 Baseline 和 Protected
    baseline = run_benchmark("http://127.0.0.1:5001")#压测 Baseline
    protected = run_benchmark("http://127.0.0.1:5000")#压测 Protected   

    print("## Benchmark Compare")
    print()
    print("| Scenario | QPS | P95(ms) | P99(ms) | Success | Degraded | Limited | Error |")
    print("|---|---:|---:|---:|---:|---:|---:|---:|")
    print_md_row("Baseline (no resilience)", baseline)
    print_md_row("Protected (resilience on)", protected)
    print()
    print("### Raw Status Count")
    print(f"- Baseline: {baseline['status_count']}")
    print(f"- Protected: {protected['status_count']}")

    result = {
        "generated_at": int(time.time()),
        "baseline": baseline,
        "protected": protected,
    }
    os.makedirs("reports", exist_ok=True)
    with open("reports/benchmark_latest.json", "w", encoding="utf-8") as f:
        json.dump(result, f, indent=2)
    print()
    print("Saved: reports/benchmark_latest.json")
