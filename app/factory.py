from __future__ import annotations

import os
from pathlib import Path

from flask import Flask

from app.api import (
    register_chaos_routes,
    register_error_handlers,
    register_hooks,
    register_observability_routes,
    register_order_routes,
)
from app.config import load_app_config
from app.context import AppRuntime
from app.infrastructure import build_redis_client, configure_logging, register_metrics
from app.observability import register_metrics_hooks
from app.repository import IdempotencyRepository, OrderRepository
from app.service import ChaosControlService, OrderService
from chaos_service import resilience, traffic


def build_application() -> tuple[Flask, AppRuntime]:
    project_root = Path(__file__).resolve().parent.parent
    config = load_app_config(project_root)

    flask_app = Flask(__name__)
    configure_logging(
        flask_app,
        use_json=config.log_json,
        service_name=config.rate_limit.service_name,
        environment=config.app_env or os.getenv("APP_ENV", "dev"),
    )
    metrics = register_metrics()
    redis_client = build_redis_client(config.redis)
    runtime = AppRuntime(
        app=flask_app,
        config=config,
        redis_client=redis_client,
        metrics=metrics,
        logger=flask_app.logger,
    )

    runtime.order_repository = OrderRepository(runtime)
    runtime.idempotency_repository = IdempotencyRepository(runtime)
    runtime.order_service = OrderService(
        runtime,
        runtime.order_repository,
        runtime.idempotency_repository,
    )
    runtime.chaos_control_service = ChaosControlService(runtime)

    _validate_runtime(runtime)
    traffic.init_traffic_recording(runtime)
    register_error_handlers(flask_app)
    register_metrics_hooks(flask_app, runtime)
    register_hooks(flask_app, runtime)
    register_order_routes(flask_app, runtime)
    register_chaos_routes(flask_app, runtime)
    register_observability_routes(flask_app, runtime)
    flask_app.extensions["runtime"] = runtime
    return flask_app, runtime


def create_app() -> Flask:
    flask_app, _ = build_application()
    return flask_app


def _validate_runtime(runtime: AppRuntime) -> None:
    try:
        resilience.validate_resilience_config(runtime)
    except ValueError as exc:
        runtime.app.logger.error("CONFIG invalid: %s", exc, exc_info=True)
        raise SystemExit(1) from exc
