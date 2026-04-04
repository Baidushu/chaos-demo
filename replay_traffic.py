import argparse
import json
import time
import urllib.error
import urllib.request
from pathlib import Path

REPORT_JSON = Path("reports/traffic_replay_latest.json")
REPORT_MD = Path("reports/traffic_replay_latest.md")


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


def load_events(path: Path):
    events = []
    if not path.exists():
        return events
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            events.append(json.loads(line))
        except json.JSONDecodeError:
            continue
    return events


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


def write_reports(base_url: str, input_path: str, loaded: int, replayed: int, rows: list):
    REPORT_JSON.parent.mkdir(parents=True, exist_ok=True)
    ok = sum(1 for r in rows if 200 <= r.get("status", 0) < 400)
    bad = replayed - ok
    avg_ms = 0.0
    if rows:
        avg_ms = sum(float(r.get("elapsed_ms", 0.0)) for r in rows) / len(rows)

    path_stats = build_path_stats(rows)

    report = {
        "generated_at": int(time.time()),
        "base_url": base_url,
        "input": input_path,
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

    lines = []
    lines.append("# Traffic Replay Report (Local Demo)")
    lines.append("")
    lines.append(f"- target: `{base_url}`")
    lines.append(f"- input: `{input_path}`")
    lines.append(f"- loaded: `{loaded}`")
    lines.append(f"- replayed: `{replayed}`")
    lines.append(f"- success: `{ok}`")
    lines.append(f"- failed: `{bad}`")
    lines.append(f"- success_rate: `{(ok / replayed * 100):.2f}%`" if replayed else "- success_rate: `0.00%`")
    lines.append(f"- avg_elapsed_ms: `{avg_ms:.1f}`")
    lines.append("")
    lines.append("## Path Stats")
    lines.append("")
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
    lines.append("")
    lines.append("## Sample Results")
    lines.append("")
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
    args = parser.parse_args()

    events = load_events(Path(args.input))
    if not events:
        print(f"[replay_traffic] no events found: {args.input}")
        write_reports(
            base_url=args.base_url,
            input_path=args.input,
            loaded=0,
            replayed=0,
            rows=[],
        )
        print(f"[replay_traffic] saved: {REPORT_JSON}")
        print(f"[replay_traffic] saved: {REPORT_MD}")
        return

    total = min(len(events), max(args.limit, 0))
    ok = 0
    bad = 0
    rows = []
    print(f"[replay_traffic] loaded={len(events)} replay={total} target={args.base_url}")

    for i, event in enumerate(events[:total], start=1):
        started = time.perf_counter()
        status, _ = send(args.base_url, event, timeout=args.timeout)
        elapsed_ms = (time.perf_counter() - started) * 1000
        if 200 <= status < 400:
            ok += 1
        else:
            bad += 1
        rows.append(
            {
                "method": event.get("method"),
                "path": event.get("path"),
                "status": status,
                "elapsed_ms": elapsed_ms,
            }
        )
        print(f"[replay_traffic] {i}/{total} {event.get('method')} {event.get('path')} -> {status}")
        if args.sleep_ms > 0 and i < total:
            time.sleep(args.sleep_ms / 1000)

    print(f"[replay_traffic] done ok={ok} bad={bad}")
    write_reports(
        base_url=args.base_url,
        input_path=args.input,
        loaded=len(events),
        replayed=total,
        rows=rows,
    )
    print(f"[replay_traffic] saved: {REPORT_JSON}")
    print(f"[replay_traffic] saved: {REPORT_MD}")


if __name__ == "__main__":
    main()
