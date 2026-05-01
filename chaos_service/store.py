from __future__ import annotations

import json
import time
import uuid

import redis


def order_key(ctx, order_id: str) -> str:
    return f"{ctx.ORDER_KEY_PREFIX}{order_id}"


def get_order_from_store(ctx, order_id: str):
    """从 Redis 读取订单 JSON；成功返回 dict，未找到或解析失败返回 None。"""
    try:
        raw = ctx.redis_client.get(order_key(ctx, order_id))
    except redis.RedisError:
        raise
    if not raw:
        return None
    try:
        return json.loads(raw)
    except (TypeError, json.JSONDecodeError):
        return None


def put_order_in_store(ctx, order_id: str, doc: dict) -> None:
    ctx.redis_client.setex(
        order_key(ctx, order_id),
        ctx.ORDER_TTL_SEC,
        json.dumps(doc, separators=(",", ":")),
    )


def idem_store_key(ctx, idem_key: str) -> str:
    return f"idem:{idem_key}"


def idem_payload_fingerprint(item_id: str, quantity: int) -> str:
    return json.dumps(
        {"item_id": item_id, "quantity": quantity},
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    )


def load_idempotency_record(ctx, idem_key: str) -> dict | None:
    raw = ctx.redis_client.get(idem_store_key(ctx, idem_key))
    if not raw:
        return None
    try:
        data = json.loads(raw)
        if isinstance(data, dict):
            return data
    except (TypeError, json.JSONDecodeError):
        pass
    return {"state": "succeeded", "order_id": str(raw)}


def reserve_idempotency_key(ctx, idem_key: str, payload_fp: str) -> tuple[str, dict]:
    owner_token = uuid.uuid4().hex
    pending = {
        "state": "processing",
        "owner_token": owner_token,
        "payload_fp": payload_fp,
        "created_at": int(time.time()),
    }
    ok = ctx.redis_client.set(
        idem_store_key(ctx, idem_key),
        json.dumps(pending, ensure_ascii=False, separators=(",", ":")),
        nx=True,
        ex=ctx.IDEM_PENDING_TTL_SEC,
    )
    if ok:
        return "owner", pending

    existing = load_idempotency_record(ctx, idem_key) or {}
    existing_fp = existing.get("payload_fp")
    if existing_fp and existing_fp != payload_fp:
        return "conflict", existing
    if existing.get("state") == "succeeded" and existing.get("order_id"):
        return "replay", existing
    return "processing", existing


def wait_for_idempotency_result(ctx, idem_key: str, payload_fp: str) -> tuple[str, dict]:
    deadline = time.time() + max(ctx.IDEM_WAIT_TIMEOUT_MS, 0) / 1000.0
    sleep_s = max(ctx.IDEM_WAIT_POLL_MS, 1) / 1000.0
    while time.time() < deadline:
        current = load_idempotency_record(ctx, idem_key)
        if not current:
            return "missing", {}
        current_fp = current.get("payload_fp")
        if current_fp and current_fp != payload_fp:
            return "conflict", current
        if current.get("state") == "succeeded" and current.get("order_id"):
            return "replay", current
        time.sleep(sleep_s)
    current = load_idempotency_record(ctx, idem_key) or {}
    current_fp = current.get("payload_fp")
    if current_fp and current_fp != payload_fp:
        return "conflict", current
    if current.get("state") == "succeeded" and current.get("order_id"):
        return "replay", current
    return "processing", current


def finalize_idempotency_success(ctx, idem_key: str, payload_fp: str, order_id: str) -> None:
    ctx.redis_client.setex(
        idem_store_key(ctx, idem_key),
        ctx.IDEM_TTL_SEC,
        json.dumps(
            {
                "state": "succeeded",
                "payload_fp": payload_fp,
                "order_id": order_id,
                "updated_at": int(time.time()),
            },
            ensure_ascii=False,
            separators=(",", ":"),
        ),
    )


def release_idempotency_reservation(ctx, idem_key: str) -> None:
    ctx.redis_client.delete(idem_store_key(ctx, idem_key))
