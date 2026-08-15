"""真实数据源适配器：Chaos Service Prometheus 指标 + 流量录制 JSONL。

设计原则（与平台降级链一致）：
  - 真实源可用 → 用真实数据，返回结果携带 source 标记；
  - 真实源不可用（服务未启动/文件缺失/网络异常）→ 返回 None，
    由调用方（QueryLogsTool / QueryMetricsTool）降级到内置模拟数据。

指标解析针对 Chaos Service 的实际命名（app/observability/metrics/__init__.py）：
  http_requests_total{method,route,status}
  http_request_errors_total{method,route}
  http_request_duration_seconds_bucket{method,route,le} / _count / _sum
  orders_rate_limited_total / orders_circuit_open_total / orders_timeout_total
  orders_degraded_total / chaos_active_experiment{fault_type,target}
  circuit_breaker_state{resource}  (closed=0 open=1 half_open=2)
"""

from __future__ import annotations

import json
import re
import time
import urllib.request
from collections import deque
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

_LABEL_RE = re.compile(r'(\w+)="([^"]*)"')
_TIME_RANGE_RE = re.compile(r"^(\d+)\s*([smh])$", re.IGNORECASE)


def parse_prometheus_text(text: str) -> dict[str, dict[tuple[str, ...], float]]:
    """解析 Prometheus 文本暴露格式 → {metric_name: {labels_tuple: value}}。

    忽略 # HELP/TYPE 注释；无标签样本用空元组。
    """
    out: dict[str, dict[tuple[str, ...], float]] = {}
    for line in text.splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        if "{" in line:
            name, rest = line.split("{", 1)
            labels_part, _, tail = rest.rpartition("}")
            labels: list[str] = []
            for key, value in _LABEL_RE.findall(labels_part):
                labels.append(f"{key}={value}")
            try:
                value = float(tail.strip().split()[0])
            except (ValueError, IndexError):
                continue
        else:
            name, _, value_part = line.partition(" ")
            try:
                value = float(value_part.strip())
            except ValueError:
                continue
            labels = []
        out.setdefault(name, {})[tuple(labels)] = value
    return out


def _sum_metric(parsed: dict, name: str) -> float:
    return sum(parsed.get(name, {}).values())


def _histogram_percentile(parsed: dict, name: str, pct: float) -> float | None:
    """从直方图 bucket 线性插值计算分位数（秒）。"""
    buckets: dict[float, float] = {}
    for labels, value in parsed.get(f"{name}_bucket", {}).items():
        le = None
        for label in labels:
            if label.startswith("le="):
                le = label[3:]
                break
        if le is None or le == "+Inf":
            continue
        try:
            buckets[float(le)] = value
        except ValueError:
            continue
    total = _sum_metric(parsed, f"{name}_count")
    if total <= 0 or not buckets:
        return None
    target = total * pct
    prev_le, prev_count = 0.0, 0.0
    for le in sorted(buckets):
        count = buckets[le]
        if count >= target:
            if count <= prev_count:
                return le
            frac = (target - prev_count) / (count - prev_count)
            return prev_le + frac * (le - prev_le)
        prev_le, prev_count = le, count
    return prev_le


def compute_service_metrics(parsed: dict[str, dict[tuple[str, ...], float]]) -> dict[str, Any]:
    """把解析后的 Prometheus 样本汇总为诊断视图。"""
    requests_total = _sum_metric(parsed, "http_requests_total")
    errors_total = _sum_metric(parsed, "http_request_errors_total")
    p50 = _histogram_percentile(parsed, "http_request_duration_seconds", 0.50)
    p99 = _histogram_percentile(parsed, "http_request_duration_seconds", 0.99)

    breaker_states = parsed.get("circuit_breaker_state", {}).values()
    return {
        "error_rate": round(errors_total / requests_total, 4) if requests_total else 0.0,
        "latency_p50_ms": round(p50 * 1000, 1) if p50 is not None else None,
        "latency_p99_ms": round(p99 * 1000, 1) if p99 is not None else None,
        "requests_total": int(requests_total),
        "errors_total": int(errors_total),
        "rate_limited_total": int(_sum_metric(parsed, "orders_rate_limited_total")),
        "circuit_open_total": int(_sum_metric(parsed, "orders_circuit_open_total")),
        "timeout_total": int(_sum_metric(parsed, "orders_timeout_total")),
        "degraded_total": int(_sum_metric(parsed, "orders_degraded_total")),
        "active_experiments": int(_sum_metric(parsed, "chaos_active_experiment")),
        "breaker_state": max(breaker_states) if breaker_states else None,
        "source": "prometheus",
    }


def fetch_metrics(base_url: str, timeout_sec: float = 2.0) -> dict[str, Any] | None:
    """GET {base_url}/metrics 并汇总；任何失败返回 None（上层降级）。"""
    url = base_url.rstrip("/")
    if not url.endswith("/metrics"):
        url += "/metrics"
    try:
        with urllib.request.urlopen(url, timeout=timeout_sec) as resp:
            text = resp.read().decode("utf-8", errors="replace")
    except Exception:
        return None
    parsed = parse_prometheus_text(text)
    if not parsed:
        return None
    return compute_service_metrics(parsed)


def _format_record(record: dict[str, Any]) -> str:
    """把一条流量录制 JSON 记录格式化成可读日志行。"""
    ts = record.get("ts")
    if isinstance(ts, (int, float)):
        when = datetime.fromtimestamp(ts, tz=timezone.utc).isoformat(timespec="seconds")
    else:
        when = str(ts)
    body = json.dumps(record.get("body") or {}, ensure_ascii=False)
    return (
        f"{when} {record.get('method', '?')} {record.get('path', '?')} "
        f"-> {record.get('status', '?')} body={body[:120]}"
    )


def read_recent_logs(
    path: Path,
    *,
    limit: int = 200,
    keyword: str | None = None,
    time_range: str | None = None,
) -> list[str] | None:
    """读取流量录制 JSONL 的最近 limit 条。

    返回 None 表示文件不可用（调用方降级模拟数据）；
    返回空 list 表示文件可用但没有匹配记录。
    """
    try:
        with path.open("r", encoding="utf-8", errors="replace") as f:
            lines = deque(f, maxlen=limit)
    except OSError:
        return None

    min_ts: float | None = None
    if time_range:
        match = _TIME_RANGE_RE.match((time_range or "").strip())
        if match:
            seconds = float(match.group(1)) * {"s": 1, "m": 60, "h": 3600}[match.group(2).lower()]
            min_ts = time.time() - seconds

    out: list[str] = []
    for raw in lines:
        raw = raw.strip()
        if not raw:
            continue
        try:
            record = json.loads(raw)
        except json.JSONDecodeError:
            out.append(raw)
            continue
        if min_ts is not None:
            ts = record.get("ts")
            if isinstance(ts, (int, float)) and ts < min_ts:
                continue
        out.append(_format_record(record))

    if keyword:
        lowered = keyword.lower()
        out = [line for line in out if lowered in line.lower()]
    return out
