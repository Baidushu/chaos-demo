from __future__ import annotations

import time
from typing import Any, cast

from flask import request


def register_metrics_hooks(flask_app, runtime) -> None:
    @flask_app.before_request
    def before_request_metrics():
        req = cast(Any, request)
        if not hasattr(req, "_start_time"):
            req._start_time = time.time()
        route = _resolve_route_label(req)
        req._metrics_route = route
        req._metrics_in_progress = True
        runtime.REQUESTS_IN_PROGRESS.labels(method=req.method, route=route).inc()

    @flask_app.after_request
    def after_request_metrics(response):
        req = cast(Any, request)
        route = getattr(req, "_metrics_route", _resolve_route_label(req))
        method = req.method
        duration = time.time() - getattr(req, "_start_time", time.time())
        runtime.REQUEST_COUNT.labels(
            method=method,
            route=route,
            status=response.status_code,
        ).inc()
        runtime.REQUEST_LATENCY.labels(method=method, route=route).observe(duration)
        if response.status_code >= 500:
            runtime.REQUEST_ERRORS.labels(method=method, route=route).inc()
        _finish_in_progress(runtime, req, method=method, route=route)
        return response

    @flask_app.teardown_request
    def teardown_request_metrics(_exc):
        req = cast(Any, request)
        route = getattr(req, "_metrics_route", _resolve_route_label(req))
        _finish_in_progress(runtime, req, method=req.method, route=route)


def _finish_in_progress(runtime, req, *, method: str, route: str) -> None:
    if not getattr(req, "_metrics_in_progress", False):
        return
    runtime.REQUESTS_IN_PROGRESS.labels(method=method, route=route).dec()
    req._metrics_in_progress = False


def _resolve_route_label(req) -> str:
    rule = getattr(req, "url_rule", None)
    if rule is not None and getattr(rule, "rule", None):
        return str(rule.rule)
    endpoint = getattr(req, "endpoint", None)
    if endpoint:
        return str(endpoint)
    return "__unmatched__"
