import argparse
import json
import time
import urllib.error
import urllib.request
from pathlib import Path

REPORT_JSON = Path("reports/traffic_replay_latest.json")
REPORT_MD = Path("reports/traffic_replay_latest.md")
BUILTIN_SAMPLE_PATH = Path("sample-data/traffic_record_demo.jsonl")


def send(base_url: str, event: dict, timeout: float):
    method = str(event.get("method", "GET")).upper()
    path = str(event.get("path", "/"))
    query = str(event.get("query", "") or "")
    headers = dict(event.get("headers", {}) or {})
    body = event.get("body")
    if not path.startswith("/"):
        path = "/" + path
    url = base_url.rstrip("/") + path
    if query:
        if query.startswith("?"):
            url += query
        else:
            url += "?" + query
    data = None
    if body is not None and method in {"POST", "PUT", "PATCH"}:
        data = json.dumps(body).encode("utf-8")
        headers.setdefault("Content-Type", "application/json")

    req = urllib.request.Request(url=url, data=data, headers=headers, method=method)
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            status = resp.getcode()
            text = resp.read().decode("utf-8", errors="ignore")
    except urllib.error.HTTPError as e:
        status = e.code
        text = e.read().decode("utf-8", errors="ignore")
    except Exception as e:
        status = 0
        text = str(e)
    return status, text


def iter_events(path: Path):
    if not path.exists():
        return
    with path.open("r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                yield json.loads(line)
            except json.JSONDecodeError:
                continue


def resolve_input_path(requested_path: Path, allow_builtin_sample: bool = True) -> tuple[Path, bool]:
    if requested_path.exists() and requested_path.stat().st_size > 0:
        return requested_path, False
    if allow_builtin_sample and BUILTIN_SAMPLE_PATH.exists() and BUILTIN_SAMPLE_PATH.stat().st_size > 0:
        return BUILTIN_SAMPLE_PATH, True
    return requested_path, False


def build_path_stats(rows: list):
    agg = {}
    for r in rows:
        path = str(r.get("path", "/"))
        item = agg.setdefault(path, {"path": path, "count": 0, "ok": 0, "total_elapsed_ms": 0.0})
        item["count"] += 1
        status = int(r.get("status", 0))
        if 200 <= status < 400:
            item["ok"] += 1
        item["total_elapsed_ms"] += float(r.get("elapsed_ms", 0.0))

    out = []
    for _, item in agg.items():
        count = item["count"]
        ok = item["ok"]
        avg = item["total_elapsed_ms"] / count if count else 0.0
        out.append(
            {
                "path": item["path"],
                "count": count,
                "ok": ok,
                "bad": count - ok,
                "success_rate": (ok / count) if count else 0.0,
                "avg_elapsed_ms": avg,
            }
        )
    out.sort(key=lambda x: (-x["count"], x["path"]))
    return out


def write_reports(
    *,
    base_url: str,
    requested_input: str,
    effective_input: str,
    loaded: int,
    replayed: int,
    rows: list,
    used_builtin_sample: bool,
):
    REPORT_JSON.parent.mkdir(parents=True, exist_ok=True)
    ok = sum(1 for r in rows if 200 <= r.get("status", 0) < 400)
    bad = replayed - ok
    avg_ms = sum(float(r.get("elapsed_ms", 0.0)) for r in rows) / len(rows) if rows else 0.0
    path_stats = build_path_stats(rows)

    report = {
        "generated_at": int(time.time()),
        "base_url": base_url,
        "input_requested": requested_input,
        "input_effective": effective_input,
        "used_builtin_sample": used_builtin_sample,
        "loaded": loaded,
        "replayed": replayed,
        "ok": ok,
        "bad": bad,
        "success_rate": (ok / replayed) if replayed else 0.0,
        "avg_elapsed_ms": avg_ms,
        "path_stats": path_stats,
        "samples": rows[:20],
    }
    REPORT_JSON.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")

    lines = [
        "# Traffic Replay Report (Local Demo)",
        "",
        f"- target: `{base_url}`",
        f"- input_requested: `{requested_input}`",
        f"- input_effective: `{effective_input}`",
        f"- used_builtin_sample: `{used_builtin_sample}`",
        f"- loaded: `{loaded}`",
        f"- replayed: `{replayed}`",
        f"- success: `{ok}`",
        f"- failed: `{bad}`",
        f"- success_rate: `{(ok / replayed * 100):.2f}%`" if replayed else "- success_rate: `0.00%`",
        f"- avg_elapsed_ms: `{avg_ms:.1f}`",
        "",
        "## Path Stats",
        "",
    ]
    if not path_stats:
        lines.append("- No path stats.")
    else:
        lines.append("| path | count | success | failed | success_rate | avg_elapsed_ms |")
        lines.append("|---|---:|---:|---:|---:|---:|")
        for p in path_stats[:20]:
            lines.append(
                f"| {p['path']} | {p['count']} | {p['ok']} | {p['bad']} | "
                f"{p['success_rate'] * 100:.2f}% | {p['avg_elapsed_ms']:.1f} |"
            )
    lines.extend(["", "## Sample Results", ""])
    if not rows:
        lines.append("- No replay rows.")
    else:
        lines.append("| # | method | path | status | elapsed_ms |")
        lines.append("|---:|---|---|---:|---:|")
        for i, r in enumerate(rows[:20], start=1):
            lines.append(
                f"| {i} | {r.get('method','')} | {r.get('path','')} | "
                f"{r.get('status',0)} | {float(r.get('elapsed_ms', 0.0)):.1f} |"
            )
    lines.append("")
    REPORT_MD.write_text("\n".join(lines) + "\n", encoding="utf-8")


def main():
    parser = argparse.ArgumentParser(description="Replay recorded traffic JSONL")
    parser.add_argument("--input", default="reports/traffic_record_latest.jsonl", help="Input jsonl file")
    parser.add_argument("--base-url", default="http://127.0.0.1:5000", help="Target base url")
    parser.add_argument("--limit", type=int, default=100, help="Max events to replay")
    parser.add_argument("--sleep-ms", type=int, default=30, help="Sleep between events")
    parser.add_argument("--timeout", type=float, default=5.0, help="HTTP timeout seconds")
    parser.add_argument(
        "--no-builtin-sample",
        action="store_true",
        help="Do not fall back to bundled sample traffic when input file is missing or empty",
    )
    args = parser.parse_args()

    requested_input_path = Path(args.input)
    input_path, used_builtin_sample = resolve_input_path(
        requested_input_path, allow_builtin_sample=not args.no_builtin_sample
    )
    total_limit = max(args.limit, 0)
    loaded = 0
    replayed = 0
    rows = []

    if used_builtin_sample:
        print(f"[replay_traffic] requested input empty/missing, using builtin sample: {input_path}")

    for event in iter_events(input_path):
        loaded += 1
        if replayed >= total_limit:
            continue
        replayed += 1
        started = time.perf_counter()
        status, _ = send(args.base_url, event, timeout=args.timeout)
        elapsed_ms = (time.perf_counter() - started) * 1000
        rows.append(
            {
                "method": event.get("method"),
                "path": event.get("path"),
                "status": status,
                "elapsed_ms": elapsed_ms,
            }
        )
        print(f"[replay_traffic] {replayed}/{total_limit} {event.get('method')} {event.get('path')} -> {status}")
        if args.sleep_ms > 0 and replayed < total_limit:
            time.sleep(args.sleep_ms / 1000)

    if loaded == 0:
        print(f"[replay_traffic] no events found: {args.input}")
        write_reports(
            base_url=args.base_url,
            requested_input=args.input,
            effective_input=str(input_path),
            loaded=0,
            replayed=0,
            rows=[],
            used_builtin_sample=used_builtin_sample,
        )
        print(f"[replay_traffic] saved: {REPORT_JSON}")
        print(f"[replay_traffic] saved: {REPORT_MD}")
        return

    ok = sum(1 for r in rows if 200 <= r.get("status", 0) < 400)
    bad = replayed - ok
    print(f"[replay_traffic] done ok={ok} bad={bad}")
    write_reports(
        base_url=args.base_url,
        requested_input=args.input,
        effective_input=str(input_path),
        loaded=loaded,
        replayed=replayed,
        rows=rows,
        used_builtin_sample=used_builtin_sample,
    )
    print(f"[replay_traffic] saved: {REPORT_JSON}")
    print(f"[replay_traffic] saved: {REPORT_MD}")


if __name__ == "__main__":
    main()
