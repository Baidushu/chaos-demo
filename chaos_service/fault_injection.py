"""故障注入模块 — 支持通过 HTTP API 动态注入故障，模拟真实混沌场景。

故障类型：
- latency:    请求处理前注入延迟（ms）
- exception:  请求处理中抛出指定异常
- drop:       按概率随机拒绝请求（返回 503）
- slow_db:    模拟数据库慢查询（额外延迟 + 随机超时）

所有故障状态存储在 Redis，多 worker 共享，支持自动过期。
通过 ENABLE_FAULT_INJECTION 环境变量控制总开关。
"""
from __future__ import annotations

import json
import os
import random as _random
import time

import redis

# 总开关
FAULT_INJECTION_ENABLED = (
    os.getenv("ENABLE_FAULT_INJECTION", "true").strip().lower()
    in ("1", "true", "yes", "on")
)

# Redis key 前缀
FAULT_KEY_PREFIX = "fault:"
# 默认故障持续时间（秒）
FAULT_DEFAULT_TTL_SEC = int(os.getenv("FAULT_DEFAULT_TTL_SEC", "60"))
# 最大延迟注入上限（ms），防止误操作
FAULT_MAX_LATENCY_MS = int(os.getenv("FAULT_MAX_LATENCY_MS", "5000"))
# 最大丢包率（允许 1.0 用于完全丢弃测试）
FAULT_MAX_DROP_RATE = float(os.getenv("FAULT_MAX_DROP_RATE", "1.0"))


def _fault_key(fault_type: str) -> str:
    return f"{FAULT_KEY_PREFIX}{fault_type}"


def _validate_fault_params(fault_type: str, params: dict) -> str | None:
    """校验故障参数，返回错误信息或 None。"""
    if fault_type == "latency":
        ms = params.get("latency_ms", 0)
        if not isinstance(ms, (int, float)) or ms < 0:
            return "latency_ms must be >= 0"
        if ms > FAULT_MAX_LATENCY_MS:
            return f"latency_ms exceeds max {FAULT_MAX_LATENCY_MS}"
    elif fault_type == "exception":
        error_type = params.get("error_type", "")
        if not error_type or not isinstance(error_type, str):
            return "error_type is required"
    elif fault_type == "drop":
        rate = params.get("drop_rate", 0)
        if not isinstance(rate, (int, float)) or not (0 <= rate <= FAULT_MAX_DROP_RATE):
            return f"drop_rate must be in [0, {FAULT_MAX_DROP_RATE}]"
    elif fault_type == "slow_db":
        base_ms = params.get("base_ms", 0)
        jitter_ms = params.get("jitter_ms", 0)
        timeout_rate = params.get("timeout_rate", 0)
        if not isinstance(base_ms, (int, float)) or base_ms < 0:
            return "base_ms must be >= 0"
        if not isinstance(jitter_ms, (int, float)) or jitter_ms < 0:
            return "jitter_ms must be >= 0"
        if not isinstance(timeout_rate, (int, float)) or not (0 <= timeout_rate <= 1):
            return "timeout_rate must be in [0, 1]"
    else:
        return f"unknown fault type: {fault_type}"
    return None


def inject_fault(
    redis_conn,
    fault_type: str,
    params: dict,
    ttl_sec: int | None = None,
) -> dict:
    """注入一个故障，返回故障记录。

    Args:
        redis_conn: Redis 连接
        fault_type: 故障类型 (latency|exception|drop|slow_db)
        params: 故障参数
        ttl_sec: 持续时间（秒），None 则使用默认值

    Returns:
        写入 Redis 的故障记录 dict
    """
    err = _validate_fault_params(fault_type, params)
    if err:
        raise ValueError(err)

    ttl = ttl_sec if ttl_sec is not None else FAULT_DEFAULT_TTL_SEC
    record = {
        "type": fault_type,
        "params": params,
        "injected_at": time.time(),
        "ttl_sec": ttl,
    }
    redis_conn.setex(
        _fault_key(fault_type),
        ttl,
        json.dumps(record, ensure_ascii=False, separators=(",", ":")),
    )
    return record


def clear_fault(redis_conn, fault_type: str) -> bool:
    """清除指定类型的故障，返回是否存在过该故障。"""
    return bool(redis_conn.delete(_fault_key(fault_type)))


def clear_all_faults(redis_conn) -> int:
    """清除所有故障，返回清除数量。"""
    keys = redis_conn.keys(f"{FAULT_KEY_PREFIX}*")
    if not keys:
        return 0
    return redis_conn.delete(*keys)


def list_faults(redis_conn) -> list[dict]:
    """列出所有活跃的故障。"""
    keys = redis_conn.keys(f"{FAULT_KEY_PREFIX}*")
    faults = []
    for key in keys:
        raw = redis_conn.get(key)
        if raw:
            try:
                faults.append(json.loads(raw))
            except (json.JSONDecodeError, TypeError):
                pass
    return faults


def get_fault(redis_conn, fault_type: str) -> dict | None:
    """获取指定类型的故障记录。"""
    raw = redis_conn.get(_fault_key(fault_type))
    if not raw:
        return None
    try:
        return json.loads(raw)
    except (json.JSONDecodeError, TypeError):
        return None


def apply_faults(ctx, request) -> str | None:
    """在请求处理前调用，根据活跃故障决定是否干预。

    Returns:
        None: 正常放行
        "latency": 已注入延迟，继续处理
        "drop": 请求被丢弃，调用方应返回 503
        "exception": 应抛出异常，调用方处理
    """
    if not FAULT_INJECTION_ENABLED:
        return None

    rc = ctx.redis_client
    applied = None

    # 丢包检测（最先判断，避免无谓延迟）
    drop = get_fault(rc, "drop")
    if drop:
        rate = drop.get("params", {}).get("drop_rate", 0)
        if _random.random() < rate:
            return "drop"

    # 延迟注入
    latency = get_fault(rc, "latency")
    if latency:
        ms = latency.get("params", {}).get("latency_ms", 0)
        if ms > 0:
            time.sleep(ms / 1000.0)
            applied = "latency"

    # 慢数据库模拟
    slow_db = get_fault(rc, "slow_db")
    if slow_db:
        params = slow_db.get("params", {})
        base_ms = params.get("base_ms", 0)
        jitter_ms = params.get("jitter_ms", 0)
        timeout_rate = params.get("timeout_rate", 0)
        total_ms = base_ms + _random.uniform(0, max(jitter_ms, 0))
        if total_ms > 0:
            time.sleep(total_ms / 1000.0)
        if _random.random() < timeout_rate:
            return "drop"  # 模拟超时 = 丢弃
        if applied is None:
            applied = "latency"

    # 异常注入
    exc = get_fault(rc, "exception")
    if exc:
        return "exception"

    return applied


def build_fault_api_response(faults: list[dict]) -> dict:
    """构建故障列表的 API 响应。"""
    return {
        "enabled": FAULT_INJECTION_ENABLED,
        "active_faults": len(faults),
        "faults": faults,
        "defaults": {
            "ttl_sec": FAULT_DEFAULT_TTL_SEC,
            "max_latency_ms": FAULT_MAX_LATENCY_MS,
            "max_drop_rate": FAULT_MAX_DROP_RATE,
        },
    }
