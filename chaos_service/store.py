"""订单与幂等：Redis 存取 + X-Idempotency-Key 状态机（与 http_api.create_order ④⑧ 对应）。

下面函数与 create_order 大致顺序：指纹 → reserve → (wait) → 写单成功 → finalize；
  超时/503 路径上 http_api 会 release（delete 占坑键）。
"""
from __future__ import annotations

import json
import time
import uuid

import redis


def order_key(ctx, order_id: str) -> str:
    """订单 Redis key：ORDER_KEY_PREFIX + order_id（ctx 来自 app 模块）。"""
    return f"{ctx.ORDER_KEY_PREFIX}{order_id}"


def get_order_from_store(ctx, order_id: str):
    """从 Redis 读取订单 JSON；成功返回 dict，未找到或解析失败返回 None。

    Redis 连接类错误向外抛，由 http_api 捕获并映射 503。
    """
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
    """写入订单文档；setex 带 ORDER_TTL_SEC 自动过期。"""
    ctx.redis_client.setex(
        order_key(ctx, order_id),
        ctx.ORDER_TTL_SEC,
        json.dumps(doc, separators=(",", ":")),
    )


def idem_store_key(ctx, idem_key: str) -> str:
    """幂等记录 Redis key：固定前缀 idem: + 客户端传入的幂等键。"""
    return f"idem:{idem_key}"


def idem_payload_fingerprint(item_id: str, quantity: int) -> str:
    """业务体指纹：与 item_id/quantity 一一对应；sort_keys 保证同内容序列化一致。

    create_order 用同指纹判断「同一单」；不同则 conflict。
    """
    return json.dumps(
        {"item_id": item_id, "quantity": quantity},
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    )


def load_idempotency_record(ctx, idem_key: str) -> dict | None:
    """读取 idem: 键：期望 JSON dict；兼容旧形态——纯字符串则视为已成功且 order_id 为该串。"""
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
    """占幂等坑：SET key JSON NX EX（IDEM_PENDING_TTL_SEC）。

    返回（状态, 记录）供 http_api 分支：
      - owner：本请求拿到锁，可继续下单；pending 含 owner_token / payload_fp。
      - replay：已有终态且 order_id，直接 200 重放。
      - conflict：已有记录且 payload_fp 与本次不一致 → 409。
      - processing：键已被他人占用（processing）或竞态下未变为终态 → http_api 可 wait 或 202。
    """
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
    """轮询读同一 idem 键，直到 replay/conflict/miss，或超过 IDEM_WAIT_TIMEOUT_MS。

    返回：
      - replay / conflict：同 reserve 语义。
      - missing：键被删等（极少路径）。
      - processing：超时仍有占坑/未到终态 → http_api 返回 202 processing。
    """
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
    """下单成功后：把幂等键写为终态 succeeded + order_id，TTL=IDEM_TTL_SEC（与 pending 不同）。"""
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
    """占坑后未完成下单（超时保护/503 等）：删除 idem: 键，避免 key 永久占死。"""
    ctx.redis_client.delete(idem_store_key(ctx, idem_key))
