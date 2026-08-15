"""订单与幂等：Redis 存取 + X-Idempotency-Key 状态机。"""

from __future__ import annotations

import json
import time
import uuid
from typing import Any

import redis

from app.infrastructure.logging import log_event

from . import fault_injection, retry

IDEM_STATE_PROCESSING = "PROCESSING"
IDEM_STATE_SUCCESS = "SUCCESS"
IDEM_STATE_FAILED = "FAILED"
IDEM_STATE_EXPIRED = "EXPIRED"

_LEGACY_STATE_MAP = {
    "processing": IDEM_STATE_PROCESSING,
    "succeeded": IDEM_STATE_SUCCESS,
    "failed": IDEM_STATE_FAILED,
    "expired": IDEM_STATE_EXPIRED,
}

_COMPARE_AND_DELETE_LUA = """
if redis.call("GET", KEYS[1]) == ARGV[1] then
    return redis.call("DEL", KEYS[1])
end
return 0
"""


def _log_idempotency_event(ctx, event: str, *, result: str, **fields: Any) -> None:
    app = getattr(ctx, "app", None)
    logger = getattr(app, "logger", None) or getattr(ctx, "logger", None)
    if logger is None:
        return
    log_event(
        logger,
        event,
        component="idempotency",
        operation="idempotency",
        result=result,
        **fields,
    )


def _execute_redis(ctx, operation: str, func):
    policy = retry.build_retry_policy(ctx)
    return policy.execute(
        lambda: _execute_redis_once(ctx, operation, func),
        operation=operation,
    )


def _execute_redis_once(ctx, operation: str, func):
    fault_injection.before_store_operation(ctx, operation)
    return func()


def order_key(ctx, order_id: str) -> str:
    """订单 Redis key：ORDER_KEY_PREFIX + order_id。"""
    return f"{ctx.ORDER_KEY_PREFIX}{order_id}"


def get_order_from_store(ctx, order_id: str):
    """从 Redis 读取订单 JSON。"""
    try:
        raw = _execute_redis(
            ctx,
            "order_store_get",
            lambda: ctx.redis_client.get(order_key(ctx, order_id)),
        )
    except redis.RedisError:
        raise
    if not raw:
        return None
    try:
        return json.loads(raw)
    except (TypeError, json.JSONDecodeError):
        return None


def put_order_in_store(ctx, order_id: str, doc: dict) -> None:
    """写入订单文档，带 TTL。"""
    _execute_redis(
        ctx,
        "order_store_set",
        lambda: ctx.redis_client.setex(
            order_key(ctx, order_id),
            ctx.ORDER_TTL_SEC,
            json.dumps(doc, separators=(",", ":")),
        ),
    )


def idem_store_key(ctx, idem_key: str) -> str:
    """幂等记录 Redis key。"""
    return f"idem:{idem_key}"


def idem_payload_fingerprint(item_id: str, quantity: int) -> str:
    """业务体指纹。"""
    return json.dumps(
        {"item_id": item_id, "quantity": quantity},
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    )


def _normalize_state(state: Any) -> str:
    if not state:
        return IDEM_STATE_SUCCESS
    if state in (IDEM_STATE_PROCESSING, IDEM_STATE_SUCCESS, IDEM_STATE_FAILED, IDEM_STATE_EXPIRED):
        return str(state)
    return _LEGACY_STATE_MAP.get(str(state).strip().lower(), str(state))


def _record_timestamp(record: dict[str, Any]) -> int:
    for field in ("updated_at", "created_at", "timestamp"):
        value = record.get(field)
        if isinstance(value, (int, float)):
            return int(value)
    return int(time.time())


def _normalize_record(ctx, data: dict[str, Any], raw: str | None = None) -> dict[str, Any]:
    record = dict(data)
    state = _normalize_state(record.get("state"))
    record["state"] = state
    record.setdefault("timestamp", _record_timestamp(record))
    if state == IDEM_STATE_PROCESSING and _is_processing_stale(ctx, record):
        record["state"] = IDEM_STATE_EXPIRED
    if state == IDEM_STATE_SUCCESS:
        body = record.get("response_body")
        if not isinstance(body, dict):
            order_id = record.get("order_id")
            if order_id:
                record["response_body"] = {"status": "ok", "order_id": order_id}
        record.setdefault("response_status", 201)
    if state == IDEM_STATE_FAILED:
        record.setdefault("response_status", 503)
    if raw is not None:
        record["_raw"] = raw
    return record


def _is_processing_stale(ctx, record: dict[str, Any]) -> bool:
    if _normalize_state(record.get("state")) != IDEM_STATE_PROCESSING:
        return False
    created_at = record.get("created_at")
    if not isinstance(created_at, (int, float)):
        return False
    return (time.time() - float(created_at)) >= max(int(ctx.IDEM_PENDING_TTL_SEC), 0)


def _serialize_record(record: dict[str, Any]) -> str:
    clean = {k: v for k, v in record.items() if not str(k).startswith("_")}
    return json.dumps(clean, ensure_ascii=False, separators=(",", ":"), sort_keys=True)


def _build_processing_record(payload_fp: str) -> dict[str, Any]:
    now = int(time.time())
    return {
        "state": IDEM_STATE_PROCESSING,
        "owner_token": uuid.uuid4().hex,
        "payload_fp": payload_fp,
        "created_at": now,
        "updated_at": now,
        "timestamp": now,
    }


def _build_success_record(
    payload_fp: str, order_id: str, response_status: int, response_body: dict[str, Any]
) -> dict[str, Any]:
    now = int(time.time())
    return {
        "state": IDEM_STATE_SUCCESS,
        "payload_fp": payload_fp,
        "order_id": order_id,
        "response_status": int(response_status),
        "response_body": response_body,
        "updated_at": now,
        "timestamp": now,
    }


def _build_failed_record(
    payload_fp: str,
    error_message: str,
    response_status: int,
    response_body: dict[str, Any],
) -> dict[str, Any]:
    now = int(time.time())
    return {
        "state": IDEM_STATE_FAILED,
        "payload_fp": payload_fp,
        "error_message": error_message,
        "response_status": int(response_status),
        "response_body": response_body,
        "updated_at": now,
        "timestamp": now,
    }


def _get_compare_and_delete_script(redis_client):
    script = getattr(redis_client, "_idem_compare_and_delete_script", None)
    if script is None:
        script = redis_client.register_script(_COMPARE_AND_DELETE_LUA)
        redis_client._idem_compare_and_delete_script = script
    return script


def _compare_and_delete(ctx, redis_key: str, expected_raw: str | None) -> bool:
    if not expected_raw:
        return False
    deleted = _execute_redis(
        ctx,
        "idempotency_compare_delete",
        lambda: _get_compare_and_delete_script(ctx.redis_client)(
            keys=[redis_key],
            args=[expected_raw],
        ),
    )
    return bool(int(deleted or 0))


def build_replay_response(record: dict[str, Any]) -> tuple[int, dict[str, Any]]:
    """构造重复请求返回体。"""
    state = _normalize_state(record.get("state"))
    body = record.get("response_body")
    payload = dict(body) if isinstance(body, dict) else {}

    if state == IDEM_STATE_SUCCESS:
        if "order_id" not in payload and record.get("order_id"):
            payload["order_id"] = record.get("order_id")
        payload.setdefault("status", "ok")
        payload["idempotent"] = True
        return 200, payload

    if state == IDEM_STATE_FAILED:
        if not payload:
            payload = {"error": record.get("error_message") or "request failed"}
        payload["idempotent"] = True
        return int(record.get("response_status") or 503), payload

    payload = {"status": "processing", "idempotent": True}
    return 202, payload


def load_idempotency_record(ctx, idem_key: str) -> dict | None:
    """读取幂等记录，兼容旧格式纯字符串 order_id。"""
    raw = _execute_redis(
        ctx,
        "idempotency_get",
        lambda: ctx.redis_client.get(idem_store_key(ctx, idem_key)),
    )
    if not raw:
        return None
    try:
        data = json.loads(raw)
        if isinstance(data, dict):
            return _normalize_record(ctx, data, raw=raw)
    except (TypeError, json.JSONDecodeError):
        pass
    return _normalize_record(
        ctx,
        {
            "state": IDEM_STATE_SUCCESS,
            "order_id": str(raw),
            "response_status": 201,
            "response_body": {"status": "ok", "order_id": str(raw)},
        },
        raw=str(raw),
    )


def _reserve_new_processing(ctx, idem_key: str, payload_fp: str) -> tuple[bool, dict[str, Any]]:
    pending = _build_processing_record(payload_fp)
    pending_raw = _serialize_record(pending)
    ok = _execute_redis(
        ctx,
        "idempotency_reserve",
        lambda: ctx.redis_client.set(
            idem_store_key(ctx, idem_key),
            pending_raw,
            nx=True,
            ex=ctx.IDEM_PENDING_TTL_SEC,
        ),
    )
    pending["_raw"] = pending_raw
    return bool(ok), pending


def reserve_idempotency_key(ctx, idem_key: str, payload_fp: str) -> tuple[str, dict]:
    """抢占幂等键，返回 owner/replay/conflict/processing。"""
    reserved, pending = _reserve_new_processing(ctx, idem_key, payload_fp)
    if reserved:
        _log_idempotency_event(ctx, "idempotency_reserve", result="owner")
        return "owner", pending

    existing = load_idempotency_record(ctx, idem_key) or {}
    existing_fp = existing.get("payload_fp")
    if existing_fp and existing_fp != payload_fp:
        _log_idempotency_event(ctx, "idempotency_conflict", result="conflict")
        return "conflict", existing

    if existing.get("state") in (IDEM_STATE_SUCCESS, IDEM_STATE_FAILED):
        _log_idempotency_event(ctx, "idempotency_replay", result="replay")
        return "replay", existing

    if existing.get("state") == IDEM_STATE_EXPIRED:
        if _compare_and_delete(ctx, idem_store_key(ctx, idem_key), existing.get("_raw")):
            reserved, pending = _reserve_new_processing(ctx, idem_key, payload_fp)
            if reserved:
                _log_idempotency_event(ctx, "idempotency_reserve", result="owner")
                return "owner", pending
        else:
            if hasattr(ctx, "IDEMPOTENCY_LOCK_FAILURE_TOTAL"):
                ctx.IDEMPOTENCY_LOCK_FAILURE_TOTAL.inc()
        existing = load_idempotency_record(ctx, idem_key) or {}
        if existing.get("payload_fp") and existing.get("payload_fp") != payload_fp:
            _log_idempotency_event(ctx, "idempotency_conflict", result="conflict")
            return "conflict", existing
        if existing.get("state") in (IDEM_STATE_SUCCESS, IDEM_STATE_FAILED):
            _log_idempotency_event(ctx, "idempotency_replay", result="replay")
            return "replay", existing

    return "processing", existing


def wait_for_idempotency_result(ctx, idem_key: str, payload_fp: str) -> tuple[str, dict]:
    """轮询同一幂等键，直到 replay/conflict/miss 或等待超时。"""
    deadline = time.time() + max(ctx.IDEM_WAIT_TIMEOUT_MS, 0) / 1000.0
    sleep_s = max(ctx.IDEM_WAIT_POLL_MS, 1) / 1000.0
    while time.time() < deadline:
        current = load_idempotency_record(ctx, idem_key)
        if not current:
            return "missing", {}
        current_fp = current.get("payload_fp")
        if current_fp and current_fp != payload_fp:
            _log_idempotency_event(ctx, "idempotency_conflict", result="conflict")
            return "conflict", current
        if current.get("state") in (IDEM_STATE_SUCCESS, IDEM_STATE_FAILED):
            _log_idempotency_event(ctx, "idempotency_replay", result="replay")
            return "replay", current
        if current.get("state") == IDEM_STATE_EXPIRED:
            return "missing", current
        time.sleep(sleep_s)

    current = load_idempotency_record(ctx, idem_key) or {}
    current_fp = current.get("payload_fp")
    if current_fp and current_fp != payload_fp:
        _log_idempotency_event(ctx, "idempotency_conflict", result="conflict")
        return "conflict", current
    if current.get("state") in (IDEM_STATE_SUCCESS, IDEM_STATE_FAILED):
        _log_idempotency_event(ctx, "idempotency_replay", result="replay")
        return "replay", current
    return "processing", current


def finalize_idempotency_success(
    ctx,
    idem_key: str,
    payload_fp: str,
    order_id: str,
    response_status: int = 201,
    response_body: dict[str, Any] | None = None,
) -> None:
    """下单成功后，将幂等键写为成功终态。"""
    success_body = response_body or {"status": "ok", "order_id": order_id}
    record = _build_success_record(payload_fp, order_id, response_status, success_body)
    _execute_redis(
        ctx,
        "idempotency_finalize",
        lambda: ctx.redis_client.setex(
            idem_store_key(ctx, idem_key),
            ctx.IDEM_TTL_SEC,
            _serialize_record(record),
        ),
    )


def save_failed(
    ctx,
    idem_key: str,
    payload_fp: str,
    error_message: str,
    response_status: int,
    response_body: dict[str, Any] | None = None,
) -> None:
    """保存失败终态，避免幂等键永久停留在 processing。"""
    failed_body = response_body or {"error": error_message}
    record = _build_failed_record(payload_fp, error_message, response_status, failed_body)
    _execute_redis(
        ctx,
        "idempotency_save_failed",
        lambda: ctx.redis_client.setex(
            idem_store_key(ctx, idem_key),
            ctx.IDEM_TTL_SEC,
            _serialize_record(record),
        ),
    )


def release_idempotency_reservation(
    ctx, idem_key: str, record: dict[str, Any] | None = None
) -> bool:
    """释放 processing 预留，仅允许 owner 删除自己的占位记录。"""
    deleted = _compare_and_delete(ctx, idem_store_key(ctx, idem_key), (record or {}).get("_raw"))
    if not deleted and hasattr(ctx, "IDEMPOTENCY_LOCK_FAILURE_TOTAL"):
        ctx.IDEMPOTENCY_LOCK_FAILURE_TOTAL.inc()
    return deleted
