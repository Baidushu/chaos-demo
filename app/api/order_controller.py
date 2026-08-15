from __future__ import annotations

from typing import Any, cast

import redis
from flask import jsonify, request

from app.exceptions import StorageException
from app.service import CreateOrderCommand


def register_routes(flask_app, runtime) -> None:
    order_service = runtime.order_service

    @flask_app.route("/order", methods=["POST"])
    def create_order():
        req = cast(Any, request)
        payload = request.get_json(silent=True) or {}
        item_id = payload.get("item_id")
        try:
            quantity = int(payload.get("quantity", 1))
        except (TypeError, ValueError):
            quantity = -1

        result = order_service.create_order(
            CreateOrderCommand(
                item_id=item_id,
                quantity=quantity,
                idempotency_key=request.headers.get("X-Idempotency-Key"),
            ),
            req._request_context,
        )
        return jsonify(result.body), result.status_code

    @flask_app.route("/order/<order_id>", methods=["GET"])
    def get_order(order_id):
        try:
            result = order_service.get_order(order_id)
        except StorageException:
            return jsonify({"error": "order store unavailable"}), 503
        return jsonify(result.body), result.status_code

    @flask_app.route("/order/<order_id>/cancel", methods=["POST"])
    def cancel_order(order_id):
        try:
            result = order_service.cancel_order(order_id)
        except StorageException:
            return jsonify({"error": "order store unavailable"}), 503
        return jsonify(result.body), result.status_code

    @flask_app.route("/live")
    def liveness():
        return jsonify({"status": "ok", "check": "liveness"}), 200

    @flask_app.route("/ready")
    def readiness():
        try:
            runtime.redis_client.ping()
        except redis.RedisError:
            body = {
                "status": "not_ready",
                "check": "readiness",
                "redis": False,
                "resilience": runtime.ENABLE_RESILIENCE,
            }
            return jsonify(body), 503
        body = {
            "status": "ready",
            "check": "readiness",
            "redis": True,
            "resilience": runtime.ENABLE_RESILIENCE,
        }
        return jsonify(body), 200

    @flask_app.route("/healthz")
    def healthz():
        try:
            runtime.redis_client.ping()
            redis_ok = True
        except redis.RedisError:
            redis_ok = False
        return (
            jsonify(
                {
                    "status": "healthy" if redis_ok else "degraded",
                    "redis": redis_ok,
                    "resilience": runtime.ENABLE_RESILIENCE,
                    "note": "prefer /live + /ready for K8s-style probes",
                }
            ),
            200,
        )
