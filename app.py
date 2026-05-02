from __future__ import annotations

import json
import logging
import os
import queue
import random
import sys
import threading
from datetime import datetime, timezone
from pathlib import Path

import redis
from flask import Flask
from prometheus_client import Counter, Histogram

from chaos_service import fault_injection, http_api, resilience, store, traffic

# ---------------------------------------------------------------------------
# 进程入口：Flask app + 可观测性 + 环境配置；CTX=本模块，供 http_api / chaos_service 读依赖与开关
# ---------------------------------------------------------------------------


class JSONFormatter(logging.Formatter):
    """单行 JSON 日志，便于 ELK/Loki 解析；可与 log_json_event 的 JSON 消息合并。"""

    def format(self, record: logging.LogRecord) -> str:
        log_entry = {
            "timestamp": datetime.fromtimestamp(record.created, tz=timezone.utc).isoformat(),
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
        }
        # 如果消息本身是 JSON 字符串（来自 log_json_event），合并字段
        if record.getMessage().startswith("{"):
            try:
                extra = json.loads(record.getMessage())
                log_entry.update(extra)
                log_entry["message"] = extra.get("event", record.getMessage())
            except (json.JSONDecodeError, TypeError):
                pass
        if record.exc_info and record.exc_info[1]:
            log_entry["exception"] = self.formatException(record.exc_info)
        return json.dumps(log_entry, ensure_ascii=False, default=str)


_USE_JSON_LOG = os.getenv("LOG_FORMAT", "json").strip().lower() == "json"

# 应用与日志
app = Flask(__name__)
if _USE_JSON_LOG:
    handler = logging.StreamHandler()
    handler.setFormatter(JSONFormatter())
    app.logger.handlers = [handler]
app.logger.setLevel(logging.INFO)
# 上下文：与 app 同模块，chaos_service 通过 ctx.redis_client / ctx.BUSINESS_TIMEOUT_MS 等访问（单测里可被 app_state 改写）
CTX = sys.modules[__name__]

# 下单临界区；Redis 客户端（单测常换 FakeRedis）
db_lock = threading.Lock()
redis_client = redis.Redis(
    host=os.getenv("REDIS_HOST", "localhost"),
    port=int(os.getenv("REDIS_PORT", "6379")),
    decode_responses=True,
)
# 韧性/限流/幂等/订单：默认来自 env，生产与单测均可改模块级变量覆盖
RATE_LIMIT_PER_SEC = int(os.getenv("RATE_LIMIT_PER_SEC", "30"))
RATE_LIMIT_ALGORITHM = os.getenv("RATE_LIMIT_ALGORITHM", "sliding").strip().lower()
RATE_LIMIT_WINDOW_SEC = float(os.getenv("RATE_LIMIT_WINDOW_SEC", "1"))
BUSINESS_TIMEOUT_MS = int(os.getenv("BUSINESS_TIMEOUT_MS", "45"))
BREAKER_FAIL_THRESHOLD = int(os.getenv("BREAKER_FAIL_THRESHOLD", "8"))
BREAKER_WINDOW_SEC = int(os.getenv("BREAKER_WINDOW_SEC", "10"))
BREAKER_OPEN_SEC = int(os.getenv("BREAKER_OPEN_SEC", "8"))
INVENTORY_BUSY_PROB = float(os.getenv("INVENTORY_BUSY_PROB", "0.03"))
ORDER_TTL_SEC = int(os.getenv("ORDER_TTL_SEC", "604800"))
ORDER_KEY_PREFIX = "order:"
IDEM_TTL_SEC = int(os.getenv("IDEM_TTL_SEC", "300"))
IDEM_PENDING_TTL_SEC = int(os.getenv("IDEM_PENDING_TTL_SEC", "15"))
IDEM_WAIT_TIMEOUT_MS = int(os.getenv("IDEM_WAIT_TIMEOUT_MS", "120"))
IDEM_WAIT_POLL_MS = int(os.getenv("IDEM_WAIT_POLL_MS", "10"))
CB_KEY_OPEN_UNTIL = "cb:open_until"
CB_KEY_FAILURES = "cb:failures"
CB_KEY_PROBE = "cb:probe"
CIRCUIT_PROBE_TTL_SEC = int(os.getenv("CIRCUIT_PROBE_TTL_SEC", "30"))
ENABLE_RESILIENCE = os.getenv("ENABLE_RESILIENCE", "true").lower() == "true"

# Prometheus 指标（hooks 里打点）
REQUEST_COUNT = Counter(
    "http_requests_total",
    "Total HTTP requests",
    ["method", "endpoint", "status"],
)
REQUEST_ERRORS = Counter(
    "http_request_errors_total",
    "Total HTTP 5xx responses",
    ["method", "endpoint"],
)
REQUEST_LATENCY = Histogram(
    "http_request_latency_seconds",
    "HTTP request latency in seconds",
    ["method", "endpoint"],
)
ORDER_COUNT = Counter("orders_created_total", "Total created orders")
ORDER_REJECTED = Counter("orders_rejected_total", "Total rejected orders")
ORDER_RATE_LIMITED = Counter("orders_rate_limited_total", "Total rate-limited requests")
ORDER_TIMEOUT = Counter("orders_timeout_total", "Total timeout-protected requests")
ORDER_DEGRADED = Counter("orders_degraded_total", "Total degraded responses")
ORDER_CIRCUIT_OPEN = Counter("orders_circuit_open_total", "Total circuit-open rejections")
ORDER_IDEMPOTENT_HIT = Counter("orders_idempotent_hit_total", "Total idempotent replay hits")
ORDER_IDEMPOTENT_PROCESSING = Counter(
    "orders_idempotent_processing_total",
    "Total duplicate requests still waiting on owner request",
)
ORDER_IDEMPOTENT_CONFLICT = Counter(
    "orders_idempotent_conflict_total",
    "Total idempotency-key payload conflicts",
)

# 可选流量落盘（异步队列 + 线程）
TRAFFIC_RECORD_ENABLED = os.getenv("TRAFFIC_RECORD_ENABLED", "false").lower() == "true"
TRAFFIC_RECORD_FILE = Path(os.getenv("TRAFFIC_RECORD_FILE", "reports/traffic_record_latest.jsonl"))
TRAFFIC_RECORD_MAX_QUEUE = int(os.getenv("TRAFFIC_RECORD_MAX_QUEUE", "2000"))
_record_queue = queue.Queue(maxsize=TRAFFIC_RECORD_MAX_QUEUE)
_writer_thread = None


# --- chaos_service 薄封装（历史调用点）；业务与路由主要在 http_api / store / resilience ---


def _order_key(order_id: str) -> str:
    return store.order_key(CTX, order_id)


def _get_order_from_store(order_id: str):
    return store.get_order_from_store(CTX, order_id)


def _put_order_in_store(order_id: str, doc: dict) -> None:
    return store.put_order_in_store(CTX, order_id, doc)


def _idem_store_key(idem_key: str) -> str:
    return store.idem_store_key(CTX, idem_key)


def _idem_payload_fingerprint(item_id: str, quantity: int) -> str:
    return store.idem_payload_fingerprint(item_id, quantity)


def _load_idempotency_record(idem_key: str) -> dict | None:
    return store.load_idempotency_record(CTX, idem_key)


def _reserve_idempotency_key(idem_key: str, payload_fp: str) -> tuple[str, dict]:
    return store.reserve_idempotency_key(CTX, idem_key, payload_fp)


def _wait_for_idempotency_result(idem_key: str, payload_fp: str) -> tuple[str, dict]:
    return store.wait_for_idempotency_result(CTX, idem_key, payload_fp)


def _finalize_idempotency_success(idem_key: str, payload_fp: str, order_id: str) -> None:
    return store.finalize_idempotency_success(CTX, idem_key, payload_fp, order_id)


def _release_idempotency_reservation(idem_key: str) -> None:
    return store.release_idempotency_reservation(CTX, idem_key)


def validate_resilience_config() -> None:
    return resilience.validate_resilience_config(CTX)


def _order_deadline_exceeded(elapsed_s: float, processing_planned_s: float, budget_ms: int) -> bool:
    return resilience.order_deadline_exceeded(elapsed_s, processing_planned_s, budget_ms)


def _log_json_event(request, event: str, **fields) -> None:
    return resilience.log_json_event(CTX, request, event, **fields)


def _mask_value(key_name, value):
    return traffic.mask_value(key_name, value)


def _sanitize_headers(headers):
    return traffic.sanitize_headers(headers)


def _traffic_writer():
    return traffic.traffic_writer(CTX)


def _record_success_traffic(response_status):
    from flask import request
    return traffic.record_success_traffic(CTX, request, response_status)


def _sliding_rate_script(redis_conn):
    return resilience.sliding_rate_script(redis_conn)


def allow_request_by_rate_limit(client_ip):
    return resilience.allow_request_by_rate_limit(CTX, client_ip)


def _cb_parse_open_until(raw) -> float:
    return resilience.cb_parse_open_until(raw)


def is_circuit_open():
    return resilience.is_circuit_open(CTX)


def record_failure_and_maybe_open():
    return resilience.record_failure_and_maybe_open(CTX)


def record_success():
    return resilience.record_success(CTX)


# 配置合法则注册 hooks/routes；否则进程退出
try:
    validate_resilience_config()
except ValueError as e:
    app.logger.error("CONFIG invalid: %s", e, exc_info=True)
    raise SystemExit(1) from e

# 挂载 before/after_request 与各路由（/order、探针、metrics、fault 等）
traffic.init_traffic_recording(CTX)
http_api.register_hooks(app, CTX)
http_api.register_routes(app, CTX)

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000)
