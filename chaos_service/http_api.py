import time
import uuid

import redis
from flask import Response, jsonify, request
from prometheus_client import CONTENT_TYPE_LATEST, generate_latest

from . import fault_injection, resilience, store, traffic


def register_hooks(app, ctx) -> None:
    @app.before_request
    def before_request():
        request._start_time = time.time()
        raw = request.headers.get("X-Request-Id", "")
        s = (raw or "").strip()
        if not s or len(s) > 256:
            request._request_id = str(uuid.uuid4())
        else:
            request._request_id = s[:128]

        # 故障注入中间件
        if request.path.startswith("/fault"):
            return  # 故障注入 API 自身不受故障影响
        if not request.path.startswith(("/healthz", "/live", "/ready", "/metrics")):
            try:
                fault_action = fault_injection.apply_faults(ctx, request)
                if fault_action == "drop":
                    ctx.ORDER_DEGRADED.inc()
                    return jsonify({"error": "fault injected: drop", "fault": True}), 503
                if fault_action == "exception":
                    error_type = (
                        fault_injection.get_fault(ctx.redis_client, "exception") or {}
                    ).get("params", {}).get("error_type", "runtime")
                    raise RuntimeError(f"fault injected: {error_type}")
            except RuntimeError:
                raise
            except Exception:
                pass  # 故障注入失败不应影响正常请求

    @app.after_request
    def after_request(response):
        endpoint = request.path
        method = request.method
        duration = time.time() - getattr(request, "_start_time", time.time())
        ctx.REQUEST_COUNT.labels(method=method, endpoint=endpoint, status=response.status_code).inc()
        ctx.REQUEST_LATENCY.labels(method=method, endpoint=endpoint).observe(duration)
        if response.status_code >= 500:
            ctx.REQUEST_ERRORS.labels(method=method, endpoint=endpoint).inc()
        traffic.record_success_traffic(ctx, request, response.status_code)

        rid = getattr(request, "_request_id", None)
        if rid:
            response.headers["X-Request-Id"] = rid
        return response


def register_routes(app, ctx) -> None:
    @app.route("/order", methods=["POST"])
    def create_order():
        client_ip = request.headers.get("X-Forwarded-For", request.remote_addr or "unknown")
        if ctx.ENABLE_RESILIENCE and not resilience.allow_request_by_rate_limit(ctx, client_ip):
            ctx.ORDER_RATE_LIMITED.inc()
            resilience.log_json_event(ctx, request, "rate_limited", path="/order", client_ip=client_ip)
            return jsonify({"error": "rate limit exceeded"}), 429
        if ctx.ENABLE_RESILIENCE and resilience.is_circuit_open(ctx):
            ctx.ORDER_CIRCUIT_OPEN.inc()
            ctx.ORDER_DEGRADED.inc()
            resilience.log_json_event(ctx, request, "circuit_open_202", path="/order")
            return jsonify({"status": "queued", "reason": "circuit open"}), 202

        payload = request.get_json(silent=True) or {}
        item_id = payload.get("item_id")
        try:
            quantity = int(payload.get("quantity", 1))
        except (TypeError, ValueError):
            quantity = -1
        if not item_id or quantity <= 0:
            ctx.ORDER_REJECTED.inc()
            return jsonify({"error": "invalid request"}), 400

        idem_key = request.headers.get("X-Idempotency-Key")
        payload_fp = store.idem_payload_fingerprint(item_id, quantity)
        idem_reserved = False
        if idem_key:
            try:
                state, record = store.reserve_idempotency_key(ctx, idem_key, payload_fp)
                if state == "replay":
                    ctx.ORDER_IDEMPOTENT_HIT.inc()
                    return jsonify({"status": "ok", "order_id": record.get("order_id"), "idempotent": True}), 200
                if state == "conflict":
                    ctx.ORDER_IDEMPOTENT_CONFLICT.inc()
                    return jsonify({"error": "idempotency key reused with different payload"}), 409
                if state == "processing":
                    waited_state, waited_record = store.wait_for_idempotency_result(ctx, idem_key, payload_fp)
                    if waited_state == "replay":
                        ctx.ORDER_IDEMPOTENT_HIT.inc()
                        return jsonify({"status": "ok", "order_id": waited_record.get("order_id"), "idempotent": True}), 200
                    if waited_state == "conflict":
                        ctx.ORDER_IDEMPOTENT_CONFLICT.inc()
                        return jsonify({"error": "idempotency key reused with different payload"}), 409
                    ctx.ORDER_IDEMPOTENT_PROCESSING.inc()
                    return jsonify({"status": "processing", "idempotent": True}), 202
                idem_reserved = True
            except redis.RedisError:
                pass

        t0 = float(getattr(request, "_start_time", time.time()))
        processing_time = ctx.random.uniform(0.01, 0.05)
        elapsed = time.time() - t0
        if ctx.ENABLE_RESILIENCE and resilience.order_deadline_exceeded(elapsed, processing_time, ctx.BUSINESS_TIMEOUT_MS):
            ctx.ORDER_TIMEOUT.inc()
            ctx.ORDER_DEGRADED.inc()
            resilience.log_json_event(
                ctx,
                request,
                "order_timeout_protected",
                elapsed_ms=round(elapsed * 1000, 3),
                planned_work_ms=round(processing_time * 1000, 3),
                budget_ms=ctx.BUSINESS_TIMEOUT_MS,
            )
            if idem_key and idem_reserved:
                try:
                    store.release_idempotency_reservation(ctx, idem_key)
                except redis.RedisError:
                    pass
            return jsonify({"status": "queued", "reason": "timeout protected"}), 202

        with ctx.db_lock:
            time.sleep(processing_time)
            if ctx.random.random() < ctx.INVENTORY_BUSY_PROB:
                ctx.ORDER_REJECTED.inc()
                if ctx.ENABLE_RESILIENCE:
                    resilience.record_failure_and_maybe_open(ctx)
                resilience.log_json_event(ctx, request, "inventory_busy_503", path="/order")
                if idem_key and idem_reserved:
                    try:
                        store.release_idempotency_reservation(ctx, idem_key)
                    except redis.RedisError:
                        pass
                return jsonify({"error": "inventory busy"}), 503

            order_id = str(uuid.uuid4())
            try:
                store.put_order_in_store(
                    ctx, order_id, {"item_id": item_id, "quantity": quantity, "status": "created"}
                )
            except redis.RedisError:
                if ctx.ENABLE_RESILIENCE:
                    resilience.record_failure_and_maybe_open(ctx)
                if idem_key and idem_reserved:
                    try:
                        store.release_idempotency_reservation(ctx, idem_key)
                    except redis.RedisError:
                        pass
                return jsonify({"error": "order store unavailable"}), 503
            if ctx.ENABLE_RESILIENCE:
                resilience.record_success(ctx)

        if idem_key:
            try:
                store.finalize_idempotency_success(ctx, idem_key, payload_fp, order_id)
            except redis.RedisError:
                pass

        ctx.ORDER_COUNT.inc()
        return jsonify({"status": "ok", "order_id": order_id}), 201

    @app.route("/order/<order_id>", methods=["GET"])
    def get_order(order_id):
        try:
            order = store.get_order_from_store(ctx, order_id)
        except redis.RedisError:
            return jsonify({"error": "order store unavailable"}), 503
        if not order:
            return jsonify({"error": "order not found"}), 404
        safe_order = {
            "item_id": order.get("item_id"),
            "quantity": order.get("quantity"),
            "status": order.get("status"),
        }
        return jsonify({"order_id": order_id, **safe_order})

    @app.route("/order/<order_id>/cancel", methods=["POST"])
    def cancel_order(order_id):
        try:
            order = store.get_order_from_store(ctx, order_id)
        except redis.RedisError:
            return jsonify({"error": "order store unavailable"}), 503
        if not order:
            return jsonify({"error": "order not found"}), 404
        if order.get("status") == "cancelled":
            return jsonify({"status": "ok", "order_id": order_id, "already_cancelled": True}), 200
        order["status"] = "cancelled"
        try:
            store.put_order_in_store(ctx, order_id, order)
        except redis.RedisError:
            return jsonify({"error": "order store unavailable"}), 503
        return jsonify({"status": "ok", "order_id": order_id, "cancelled": True}), 200

    @app.route("/live")
    def liveness():
        return jsonify({"status": "ok", "check": "liveness"}), 200

    @app.route("/ready")
    def readiness():
        try:
            ctx.redis_client.ping()
            return jsonify({"status": "ready", "check": "readiness", "redis": True, "resilience": ctx.ENABLE_RESILIENCE}), 200
        except redis.RedisError:
            return jsonify({"status": "not_ready", "check": "readiness", "redis": False, "resilience": ctx.ENABLE_RESILIENCE}), 503

    @app.route("/healthz")
    def healthz():
        try:
            ctx.redis_client.ping()
            redis_ok = True
        except redis.RedisError:
            redis_ok = False
        return jsonify({
            "status": "healthy" if redis_ok else "degraded",
            "redis": redis_ok,
            "resilience": ctx.ENABLE_RESILIENCE,
            "note": "prefer /live + /ready for K8s-style probes",
        }), 200

    @app.route("/metrics")
    def metrics():
        return Response(generate_latest(), mimetype=CONTENT_TYPE_LATEST)

    # ---- 故障注入 API ----

    @app.route("/fault/status", methods=["GET"])
    def fault_status():
        faults = fault_injection.list_faults(ctx.redis_client)
        return jsonify(fault_injection.build_fault_api_response(faults))

    @app.route("/fault/inject", methods=["POST"])
    def fault_inject():
        payload = request.get_json(silent=True) or {}
        fault_type = payload.get("type", "")
        params = payload.get("params", {})
        ttl_sec = payload.get("ttl_sec")
        if not fault_type:
            return jsonify({"error": "type is required"}), 400
        try:
            record = fault_injection.inject_fault(
                ctx.redis_client, fault_type, params, ttl_sec
            )
        except ValueError as e:
            return jsonify({"error": str(e)}), 400
        return jsonify({"status": "injected", "fault": record}), 201

    @app.route("/fault/clear", methods=["POST"])
    def fault_clear():
        payload = request.get_json(silent=True) or {}
        fault_type = payload.get("type", "")
        if not fault_type:
            return jsonify({"error": "type is required"}), 400
        existed = fault_injection.clear_fault(ctx.redis_client, fault_type)
        return jsonify({"status": "cleared", "type": fault_type, "existed": existed})

    @app.route("/fault/clear-all", methods=["POST"])
    def fault_clear_all():
        count = fault_injection.clear_all_faults(ctx.redis_client)
        return jsonify({"status": "all_cleared", "count": count})

    @app.route("/fault/inject/<fault_type>", methods=["DELETE"])
    def fault_delete(fault_type):
        existed = fault_injection.clear_fault(ctx.redis_client, fault_type)
        return jsonify({"status": "cleared", "type": fault_type, "existed": existed})
