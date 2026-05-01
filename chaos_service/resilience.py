import json
import time
import uuid

import redis


_RL_SLIDING_LUA = """
local key = KEYS[1]
local now = tonumber(ARGV[1])
local window = tonumber(ARGV[2])
local limit = tonumber(ARGV[3])
local member = ARGV[4]
local ttl = tonumber(ARGV[5])
redis.call('ZREMRANGEBYSCORE', key, '-inf', now - window)
local n = redis.call('ZCARD', key)
if n >= limit then
  return 0
end
redis.call('ZADD', key, now, member)
redis.call('EXPIRE', key, ttl)
return 1
"""
_sliding_rate_scripts = {}


def validate_resilience_config(ctx) -> None:
    if ctx.RATE_LIMIT_PER_SEC < 0:
        raise ValueError("RATE_LIMIT_PER_SEC must be >= 0")
    if ctx.RATE_LIMIT_WINDOW_SEC <= 0:
        raise ValueError("RATE_LIMIT_WINDOW_SEC must be > 0")
    if ctx.RATE_LIMIT_ALGORITHM not in ("sliding", "fixed"):
        raise ValueError("RATE_LIMIT_ALGORITHM must be sliding|fixed")
    if ctx.BUSINESS_TIMEOUT_MS < 0:
        raise ValueError("BUSINESS_TIMEOUT_MS must be >= 0")
    if not 0.0 <= ctx.INVENTORY_BUSY_PROB <= 1.0:
        raise ValueError("INVENTORY_BUSY_PROB must be in [0, 1]")
    if ctx.BREAKER_FAIL_THRESHOLD < 1 or ctx.BREAKER_WINDOW_SEC < 1 or ctx.BREAKER_OPEN_SEC < 1:
        raise ValueError("BREAKER_* must be >= 1 where applicable")
    if ctx.ORDER_TTL_SEC < 60:
        raise ValueError("ORDER_TTL_SEC must be >= 60 (seconds)")
    if ctx.IDEM_TTL_SEC < 1 or ctx.IDEM_PENDING_TTL_SEC < 1:
        raise ValueError("IDEM_*_TTL_SEC must be >= 1")
    if ctx.IDEM_WAIT_TIMEOUT_MS < 0 or ctx.IDEM_WAIT_POLL_MS < 1:
        raise ValueError("IDEM_WAIT_TIMEOUT_MS must be >= 0 and IDEM_WAIT_POLL_MS >= 1")
    if ctx.CIRCUIT_PROBE_TTL_SEC < 1:
        raise ValueError("CIRCUIT_PROBE_TTL_SEC must be >= 1")


def order_deadline_exceeded(elapsed_s: float, processing_planned_s: float, budget_ms: int) -> bool:
    return elapsed_s + processing_planned_s > (budget_ms / 1000.0)


def log_json_event(ctx, request, event: str, **fields) -> None:
    rid = getattr(request, "_request_id", None)
    rec = {"event": event, "request_id": rid, **fields}
    ctx.app.logger.info(json.dumps(rec, ensure_ascii=False, default=str))


def sliding_rate_script(redis_conn):
    sid = id(redis_conn)
    if sid not in _sliding_rate_scripts:
        _sliding_rate_scripts[sid] = redis_conn.register_script(_RL_SLIDING_LUA)
    return _sliding_rate_scripts[sid]


def allow_request_by_rate_limit(ctx, client_ip):
    try:
        if ctx.RATE_LIMIT_ALGORITHM == "fixed":
            key = f"rl:{client_ip}:{int(time.time())}"
            value = ctx.redis_client.incr(key)
            if value == 1:
                ctx.redis_client.expire(key, 2)
            return value <= ctx.RATE_LIMIT_PER_SEC

        key = f"rl:sw:{client_ip}"
        now = time.time()
        window = max(ctx.RATE_LIMIT_WINDOW_SEC, 0.001)
        member = f"{now:.6f}:{uuid.uuid4().hex}"
        ttl = int(window) + 2
        if hasattr(ctx.redis_client, "rate_limit_sliding_allow"):
            return ctx.redis_client.rate_limit_sliding_allow(
                key, now, window, ctx.RATE_LIMIT_PER_SEC, member, ttl
            )
        script = sliding_rate_script(ctx.redis_client)
        allowed = script(keys=[key], args=[str(now), str(window), str(ctx.RATE_LIMIT_PER_SEC), member, str(ttl)])
        return bool(int(allowed))
    except redis.RedisError:
        return True


def cb_parse_open_until(raw) -> float:
    if raw is None or raw == "":
        return 0.0
    try:
        return float(raw)
    except (TypeError, ValueError):
        return 0.0


def is_circuit_open(ctx):
    if not ctx.ENABLE_RESILIENCE:
        return False
    now = time.time()
    try:
        ou = cb_parse_open_until(ctx.redis_client.get(ctx.CB_KEY_OPEN_UNTIL))
        if ou > 0.0 and now < ou:
            return True
        if ou > 0.0 and now >= ou:
            if ctx.redis_client.get(ctx.CB_KEY_PROBE):
                return True
            ok = ctx.redis_client.set(
                ctx.CB_KEY_PROBE,
                "1",
                nx=True,
                ex=ctx.CIRCUIT_PROBE_TTL_SEC,
            )
            if ok:
                ctx.app.logger.info("[CIRCUIT] transition=half_open probe=allow now=%.3f", now)
                return False
            return True
    except redis.RedisError:
        return False
    return False


def record_failure_and_maybe_open(ctx):
    now = time.time()
    try:
        if ctx.redis_client.get(ctx.CB_KEY_PROBE):
            ctx.redis_client.delete(ctx.CB_KEY_PROBE)
            ctx.redis_client.set(ctx.CB_KEY_OPEN_UNTIL, str(now + ctx.BREAKER_OPEN_SEC))
            try:
                ctx.redis_client.delete(ctx.CB_KEY_FAILURES)
            except redis.RedisError:
                pass
            member = f"{now:.6f}:{uuid.uuid4().hex}"
            ctx.redis_client.zadd(ctx.CB_KEY_FAILURES, {member: now})
            ctx.app.logger.warning(
                "[CIRCUIT] transition=reopen_from_half_open open_until=%.3f",
                now + ctx.BREAKER_OPEN_SEC,
            )
            return

        member = f"{now:.6f}:{uuid.uuid4().hex}"
        ctx.redis_client.zadd(ctx.CB_KEY_FAILURES, {member: now})
        ctx.redis_client.zremrangebyscore(
            ctx.CB_KEY_FAILURES, float("-inf"), now - float(ctx.BREAKER_WINDOW_SEC)
        )
        n = ctx.redis_client.zcard(ctx.CB_KEY_FAILURES)
        if n >= ctx.BREAKER_FAIL_THRESHOLD:
            ou = now + float(ctx.BREAKER_OPEN_SEC)
            ctx.redis_client.set(ctx.CB_KEY_OPEN_UNTIL, str(ou))
            ctx.app.logger.warning(
                "[CIRCUIT] transition=open failures=%d window_sec=%d open_until=%.3f",
                n,
                ctx.BREAKER_WINDOW_SEC,
                ou,
            )
    except redis.RedisError:
        return


def record_success(ctx):
    try:
        was_probe = bool(ctx.redis_client.get(ctx.CB_KEY_PROBE))
        ou = cb_parse_open_until(ctx.redis_client.get(ctx.CB_KEY_OPEN_UNTIL))
        was = was_probe or ou > 0.0
        ctx.redis_client.delete(ctx.CB_KEY_PROBE, ctx.CB_KEY_FAILURES)
        ctx.redis_client.set(ctx.CB_KEY_OPEN_UNTIL, "0")
        if was:
            ctx.app.logger.info("[CIRCUIT] transition=closed reason=success")
    except redis.RedisError:
        return
