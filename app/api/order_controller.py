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
        payload = request.get_json(silent=True)
        # 类型守卫：body 可能是 list/str/number 等 JSON 非 object 形态
        # （schemathesis fuzz 实证：[null,null] 曾触发 AttributeError → 500）
        if not isinstance(payload, dict):
            payload = {}
        item_id = payload.get("item_id")
        raw_quantity = payload.get("quantity", 1)
        # 契约对齐（tests/contract/openapi_order_api.yaml）：item_id 必须
        # string、quantity 必须 int（拒绝 bool/float/list 等类型混淆输入）。
        # 该防线由 schemathesis 负向用例驱动——曾发现 [null,null] 作为
        # item_id 穿透 truthy 校验直达存储层的缺口。
        if not isinstance(item_id, str):
            item_id = None  # 交由 service 的必填校验拒绝 → 400
        if isinstance(raw_quantity, bool) or not isinstance(raw_quantity, int):
            quantity = -1  # 非法 → service 校验拒绝 → 400
        else:
            quantity = raw_quantity

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
