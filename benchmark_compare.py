import argparse
import json
import os
import statistics
import sys
import time
import urllib.error
import urllib.request
import uuid
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path


METRIC_FIELDS = (
    "qps",
    "p50_ms",
    "p95_ms",
    "p99_ms",
    "success_rate",
    "degraded_rate",
    "limited_rate",
    "error_rate",
)
REPORT_DIR = Path("reports")
BENCHMARK_LATEST_PATH = REPORT_DIR / "benchmark_latest.json"
BENCHMARK_HISTORY_DIR = REPORT_DIR / "benchmark_history"
BENCHMARK_TREND_JSON = REPORT_DIR / "benchmark_trend_latest.json"
BENCHMARK_TREND_MD = REPORT_DIR / "benchmark_trend_latest.md"


def one_request(base_url: str, idempotency_key: str):
    """??? POST /order????????????? uuid ? seed ????"""
    payload = json.dumps({"item_id": "sku-bench", "quantity": 1}).encode()
    headers = {
        "Content-Type": "application/json",
        "X-Idempotency-Key": idempotency_key,
    }
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


def _idempotency_keys(n: int, seed: int | None, run_label: str) -> list[str]:
    """? seed ????? uuid4?? seed ?? run_label ???"""
    if seed is None:
        return [str(uuid.uuid4()) for _ in range(n)]
    return [f"bench-{run_label}-s{seed}-n{i:06d}" for i in range(n)]


def _percentile(latencies: list[float], pct: float) -> float:
    if not latencies:
        return 0.0
    if len(latencies) == 1:
        return float(latencies[0])
    rank = max(1, min(int(pct), 99))
    return float(statistics.quantiles(latencies, n=100)[rank - 1])


def run_warmup(
    base_url: str,
    count: int,
    concurrency: int,
    seed: int | None,
    run_label: str,
) -> None:
    """?????????????????????"""
    if count <= 0:
        return
    wlabel = f"{run_label}-warmup"
    keys = _idempotency_keys(count, seed, wlabel)
    with ThreadPoolExecutor(max_workers=concurrency) as pool:
        futs = [pool.submit(one_request, base_url, k) for k in keys]
        for f in as_completed(futs):
            f.result()


def run_benchmark(
    base_url: str,
    total_requests: int = 300,
    concurrency: int = 20,
    *,
    seed: int | None = None,
    run_label: str = "run",
) -> dict:
    if total_requests < 1:
        raise ValueError("total_requests must be >= 1")
    if concurrency < 1:
        raise ValueError("concurrency must be >= 1")

    keys = _idempotency_keys(total_requests, seed, run_label)
    latencies = []
    status_count = {}
    started_at = time.perf_counter()
    with ThreadPoolExecutor(max_workers=concurrency) as pool:
        futures = [pool.submit(one_request, base_url, k) for k in keys]
        for fut in as_completed(futures):
            status, latency = fut.result()
            latencies.append(latency)
            status_count[status] = status_count.get(status, 0) + 1
    elapsed = time.perf_counter() - started_at
    success = status_count.get(201, 0) + status_count.get(200, 0)
    degraded = status_count.get(202, 0)
    limited = status_count.get(429, 0)
    errors = sum(v for k, v in status_count.items() if k >= 500 or k == 0)

    return {
        "qps": total_requests / elapsed if elapsed > 0 else 0.0,
        "p50_ms": _percentile(latencies, 50),
        "p95_ms": _percentile(latencies, 95),
        "p99_ms": _percentile(latencies, 99),
        "success_rate": success / total_requests,
        "degraded_rate": degraded / total_requests,
        "limited_rate": limited / total_requests,
        "error_rate": errors / total_requests,
        "status_count": status_count,
        "elapsed_s": elapsed,
        "request_count": total_requests,
        "run_label": run_label,
    }


def _metric_stats(values: list[float]) -> dict:
    values = [float(v) for v in values]
    return {
        "median": statistics.median(values),
        "min": min(values),
        "max": max(values),
        "stdev": statistics.stdev(values) if len(values) > 1 else 0.0,
    }


def summarize_runs(runs: list[dict]) -> dict:
    if not runs:
        raise ValueError("runs must not be empty")

    metric_summary = {
        metric: _metric_stats([run[metric] for run in runs]) for metric in METRIC_FIELDS
    }
    aggregate_status_count = {}
    for run in runs:
        for status, count in (run.get("status_count") or {}).items():
            aggregate_status_count[status] = aggregate_status_count.get(status, 0) + int(count)

    p95_median = metric_summary["p95_ms"]["median"]
    representative_index = min(
        range(len(runs)), key=lambda idx: abs(float(runs[idx]["p95_ms"]) - float(p95_median))
    )
    representative_run = runs[representative_index]

    median_view = {metric: metric_summary[metric]["median"] for metric in METRIC_FIELDS}
    median_view["status_count"] = aggregate_status_count
    median_view["run_count"] = len(runs)
    median_view["aggregation"] = "median_of_runs"
    median_view["representative_run_label"] = representative_run.get("run_label")

    return {
        "run_count": len(runs),
        "median": median_view,
        "summary": metric_summary,
        "representative_run_index": representative_index,
        "representative_run": representative_run,
    }


def _safe_metric(report: dict, side: str, metric: str) -> float | None:
    try:
        return float(report.get(side, {}).get(metric))
    except (TypeError, ValueError):
        return None


def archive_report(report: dict, session_id: str) -> Path:
    BENCHMARK_HISTORY_DIR.mkdir(parents=True, exist_ok=True)
    ts = int(report.get("generated_at") or time.time())
    path = BENCHMARK_HISTORY_DIR / f"benchmark_{ts}_{session_id}.json"
    path.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")

    keep = max(1, _parse_int_env("BENCHMARK_HISTORY_KEEP", 20))
    history_files = sorted(BENCHMARK_HISTORY_DIR.glob("benchmark_*.json"))
    if len(history_files) > keep:
        for old in history_files[: len(history_files) - keep]:
            old.unlink(missing_ok=True)
    return path


def load_recent_history(limit: int = 10) -> list[dict]:
    if not BENCHMARK_HISTORY_DIR.exists():
        return []
    files = sorted(BENCHMARK_HISTORY_DIR.glob("benchmark_*.json"))
    out = []
    for path in files[-max(limit, 0) :]:
        try:
            out.append(json.loads(path.read_text(encoding="utf-8")))
        except (OSError, json.JSONDecodeError):
            continue
    return out


def build_trend_report(current: dict, previous_reports: list[dict]) -> dict:
    protected_p95_history = [
        v for v in (_safe_metric(rep, "protected", "p95_ms") for rep in previous_reports) if v is not None
    ]
    protected_error_history = [
        v for v in (_safe_metric(rep, "protected", "error_rate") for rep in previous_reports) if v is not None
    ]
    baseline_p95_history = [
        v for v in (_safe_metric(rep, "baseline", "p95_ms") for rep in previous_reports) if v is not None
    ]

    current_protected_p95 = float(current["protected"]["p95_ms"])
    current_baseline_p95 = float(current["baseline"]["p95_ms"])
    current_protected_error = float(current["protected"]["error_rate"])

    prev_protected_p95_median = statistics.median(protected_p95_history) if protected_p95_history else None
    prev_protected_error_median = (
        statistics.median(protected_error_history) if protected_error_history else None
    )
    prev_baseline_p95_median = statistics.median(baseline_p95_history) if baseline_p95_history else None

    def delta(cur: float, prev: float | None) -> float | None:
        if prev is None:
            return None
        return cur - prev

    return {
        "generated_at": int(time.time()),
        "history_window": len(previous_reports),
        "current_generated_at": current.get("generated_at"),
        "current": {
            "protected_p95_ms": current_protected_p95,
            "baseline_p95_ms": current_baseline_p95,
            "protected_error_rate": current_protected_error,
            "protected_run_count": current.get("protected", {}).get("run_count", 1),
        },
        "previous_medians": {
            "protected_p95_ms": prev_protected_p95_median,
            "baseline_p95_ms": prev_baseline_p95_median,
            "protected_error_rate": prev_protected_error_median,
        },
        "delta_vs_history_median": {
            "protected_p95_ms": delta(current_protected_p95, prev_protected_p95_median),
            "baseline_p95_ms": delta(current_baseline_p95, prev_baseline_p95_median),
            "protected_error_rate": delta(current_protected_error, prev_protected_error_median),
        },
    }


def write_trend_reports(trend: dict) -> None:
    REPORT_DIR.mkdir(parents=True, exist_ok=True)
    BENCHMARK_TREND_JSON.write_text(json.dumps(trend, ensure_ascii=False, indent=2), encoding="utf-8")
    current = trend["current"]
    previous = trend["previous_medians"]
    delta = trend["delta_vs_history_median"]

    def fmt_num(v: float | None, suffix: str = "") -> str:
        if v is None:
            return "N/A"
        return f"{v:.1f}{suffix}" if suffix else f"{v:.4f}" if abs(v) < 1 else f"{v:.1f}"

    lines = [
        "# Benchmark Trend Report",
        "",
        f"- current_generated_at: `{trend['current_generated_at']}`",
        f"- history_window: `{trend['history_window']}`",
        f"- protected_run_count: `{current['protected_run_count']}`",
        "",
        "| Metric | Current | Previous Median | Delta |",
        "|---|---:|---:|---:|",
        f"| Protected P95 (ms) | {fmt_num(current['protected_p95_ms'])} | {fmt_num(previous['protected_p95_ms'])} | {fmt_num(delta['protected_p95_ms'])} |",
        f"| Baseline P95 (ms) | {fmt_num(current['baseline_p95_ms'])} | {fmt_num(previous['baseline_p95_ms'])} | {fmt_num(delta['baseline_p95_ms'])} |",
        f"| Protected Error Rate | {current['protected_error_rate']*100:.2f}% | "
        + (f"{previous['protected_error_rate']*100:.2f}%" if previous['protected_error_rate'] is not None else "N/A")
        + " | "
        + (f"{delta['protected_error_rate']*100:.2f}%" if delta['protected_error_rate'] is not None else "N/A")
        + " |",
        "",
    ]
    BENCHMARK_TREND_MD.write_text("\n".join(lines), encoding="utf-8")


def print_md_row(name, data):
    print(
        f"| {name} | {data['qps']:.1f} | {data['p95_ms']:.1f} | {data['p99_ms']:.1f} | "
        f"{data['success_rate']*100:.1f}% | {data['degraded_rate']*100:.1f}% | "
        f"{data['limited_rate']*100:.1f}% | {data['error_rate']*100:.1f}% |"
    )


def print_run_spread(label: str, summary: dict) -> None:
    print(
        f"- {label}: runs={summary['run_count']} | "
        f"P95 median/min/max/stdev = {summary['summary']['p95_ms']['median']:.1f}/"
        f"{summary['summary']['p95_ms']['min']:.1f}/"
        f"{summary['summary']['p95_ms']['max']:.1f}/"
        f"{summary['summary']['p95_ms']['stdev']:.1f} ms | "
        f"Error median = {summary['summary']['error_rate']['median']:.2%}"
    )


def probe_health(base_url: str, label: str) -> None:
    """??????????????????????"""
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


def _parse_int_env(name: str, default: int) -> int:
    raw = os.environ.get(name, "").strip()
    if not raw:
        return default
    return int(raw)


def _parse_seed() -> int | None:
    raw = os.environ.get("BENCHMARK_SEED", "").strip()
    if not raw:
        return None
    return int(raw)


def build_arg_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        description="HTTP ???Baseline(???) vs Protected(??) ?? reports/benchmark_latest.json"
    )
    p.add_argument(
        "--baseline-url",
        default=os.environ.get("BENCHMARK_BASELINE_URL", "http://127.0.0.1:5001"),
        help="????? URL?? BENCHMARK_BASELINE_URL?",
    )
    p.add_argument(
        "--protected-url",
        default=os.environ.get("BENCHMARK_PROTECTED_URL", "http://127.0.0.1:5000"),
        help="????? URL?? BENCHMARK_PROTECTED_URL?",
    )
    p.add_argument(
        "-n",
        "--total-requests",
        type=int,
        default=_parse_int_env("BENCHMARK_TOTAL_REQUESTS", 300),
        help="????????? 300??? BENCHMARK_TOTAL_REQUESTS ??",
    )
    p.add_argument(
        "-c",
        "--concurrency",
        type=int,
        default=_parse_int_env("BENCHMARK_CONCURRENCY", 20),
        help="???????? 20??? BENCHMARK_CONCURRENCY ??",
    )
    p.add_argument(
        "--seed",
        type=str,
        default=None,
        metavar="N",
        help="??????????????????? 0?????? BENCHMARK_SEED?????? uuid?",
    )
    p.add_argument(
        "--warmup",
        type=int,
        default=_parse_int_env("BENCHMARK_WARMUP", 0),
        help="??????????????????????0 ????? BENCHMARK_WARMUP?",
    )
    p.add_argument(
        "--runs",
        type=int,
        default=_parse_int_env("BENCHMARK_RUNS", 3),
        help="????????????? 3??????????????",
    )
    return p


def _resolve_seed(cli_seed: str | None) -> int | None:
    """CLI ?? --seed ????????????????????? seed??"""
    if cli_seed is not None:
        t = cli_seed.strip()
        if t == "":
            return None
        return int(t)
    return _parse_seed()


def _run_many(
    *,
    base_url: str,
    scenario: str,
    total_requests: int,
    concurrency: int,
    seed: int | None,
    warmup: int,
    runs: int,
    session_id: str,
) -> list[dict]:
    all_runs = []
    for idx in range(runs):
        run_label = f"{session_id}-{scenario}-r{idx + 1}"
        if warmup > 0:
            run_warmup(base_url, warmup, concurrency, seed, run_label)
        run = run_benchmark(
            base_url,
            total_requests=total_requests,
            concurrency=concurrency,
            seed=seed,
            run_label=run_label,
        )
        run["run_no"] = idx + 1
        all_runs.append(run)
    return all_runs


def main() -> None:
    parser = build_arg_parser()
    args = parser.parse_args()
    if args.total_requests < 1 or args.concurrency < 1 or args.runs < 1:
        print(
            "[benchmark_compare] total-requests / concurrency / runs ?? >=1",
            file=sys.stderr,
        )
        sys.exit(2)
    if args.warmup < 0:
        print("[benchmark_compare] warmup ?? >=0", file=sys.stderr)
        sys.exit(2)

    seed: int | None = _resolve_seed(args.seed)
    if seed is not None:
        print(
            f"[benchmark_compare] seed={seed}?????????????? session_id ????????? Redis ???"
        )

    params = {
        "baseline_url": args.baseline_url.rstrip("/"),
        "protected_url": args.protected_url.rstrip("/"),
        "total_requests": args.total_requests,
        "concurrency": args.concurrency,
        "seed": seed,
        "warmup_per_scenario": args.warmup,
        "runs": args.runs,
        "aggregation": "median_of_runs",
    }

    probe_health(args.baseline_url, "Baseline :5001")
    probe_health(args.protected_url, "Protected :5000")

    session_id = uuid.uuid4().hex[:8]
    if args.warmup > 0:
        print(
            f"[benchmark_compare] warmup: {args.warmup} req/scenario/run, c={args.concurrency} (not in report)"
        )
    print(f"[benchmark_compare] runs={args.runs}, session_id={session_id}")

    baseline_runs = _run_many(
        base_url=args.baseline_url,
        scenario="baseline",
        total_requests=args.total_requests,
        concurrency=args.concurrency,
        seed=seed,
        warmup=args.warmup,
        runs=args.runs,
        session_id=session_id,
    )
    protected_runs = _run_many(
        base_url=args.protected_url,
        scenario="protected",
        total_requests=args.total_requests,
        concurrency=args.concurrency,
        seed=seed,
        warmup=args.warmup,
        runs=args.runs,
        session_id=session_id,
    )

    baseline_summary = summarize_runs(baseline_runs)
    protected_summary = summarize_runs(protected_runs)
    baseline = baseline_summary["median"]
    protected = protected_summary["median"]

    print("## Benchmark Compare (Median of Runs)")
    print()
    print("| Scenario | QPS | P95(ms) | P99(ms) | Success | Degraded | Limited | Error |")
    print("|---|---:|---:|---:|---:|---:|---:|---:|")
    print_md_row("Baseline (no resilience)", baseline)
    print_md_row("Protected (resilience on)", protected)
    print()
    print("### Run Spread")
    print_run_spread("Baseline", baseline_summary)
    print_run_spread("Protected", protected_summary)
    print()
    print("### Aggregated Raw Status Count")
    print(f"- Baseline: {baseline['status_count']}")
    print(f"- Protected: {protected['status_count']}")
    print()
    seed_label = seed if seed is not None else "random"
    print(
        f"### Params (n={args.total_requests}, c={args.concurrency}, runs={args.runs}, seed={seed_label}, warmup={args.warmup}, aggregation=median_of_runs)"
    )

    result = {
        "generated_at": int(time.time()),
        "params": params,
        "baseline": baseline,
        "protected": protected,
        "baseline_runs": baseline_runs,
        "protected_runs": protected_runs,
        "baseline_summary": baseline_summary,
        "protected_summary": protected_summary,
    }
    REPORT_DIR.mkdir(parents=True, exist_ok=True)
    previous_reports = load_recent_history(limit=_parse_int_env("BENCHMARK_TREND_WINDOW", 10))
    with BENCHMARK_LATEST_PATH.open("w", encoding="utf-8") as f:
        json.dump(result, f, ensure_ascii=False, indent=2)
    archive_path = archive_report(result, session_id=session_id)
    trend = build_trend_report(result, previous_reports)
    write_trend_reports(trend)
    print()
    print(f"Saved: {BENCHMARK_LATEST_PATH}")
    print(f"Archived: {archive_path}")
    print(f"Saved: {BENCHMARK_TREND_JSON}")
    print(f"Saved: {BENCHMARK_TREND_MD}")


if __name__ == "__main__":
    main()
