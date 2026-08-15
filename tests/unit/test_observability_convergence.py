from __future__ import annotations

from types import SimpleNamespace

import pytest
from flask import Flask

from app.api.observability_controller import register_routes as register_observability_routes
from app.middleware import register_metrics_hooks as compat_register_metrics_hooks
from app.middleware.metrics_hooks import (
    register_metrics_hooks as compat_register_metrics_hooks_module,
)
from app.observability.middleware import (
    _finish_in_progress,
    _resolve_route_label,
    register_metrics_hooks,
)
from app.service.chaos_service import ChaosControlService
from chaos_service.http_api import register_hooks, register_routes
from chaos_service.resilience.limiter import RateLimitRule
from chaos_service.resilience.retry import RetryConfig


class _CounterHandle:
    def __init__(self) -> None:
        self.inc_calls = 0
        self.dec_calls = 0
        self.observe_calls: list[float] = []

    def inc(self) -> None:
        self.inc_calls += 1

    def dec(self) -> None:
        self.dec_calls += 1

    def observe(self, value: float) -> None:
        self.observe_calls.append(value)


class _Metric:
    def __init__(self) -> None:
        self.handles: dict[tuple[tuple[str, object], ...], _CounterHandle] = {}

    def labels(self, **labels):
        key = tuple(sorted(labels.items()))
        handle = self.handles.get(key)
        if handle is None:
            handle = _CounterHandle()
            self.handles[key] = handle
        return handle


def test_observability_middleware_compat_exports():
    assert compat_register_metrics_hooks is register_metrics_hooks
    assert compat_register_metrics_hooks_module is register_metrics_hooks
    assert RetryConfig.__name__ == "RetryConfig"
    assert RateLimitRule.__name__ == "RateLimitRule"


def test_observability_metrics_route_exposes_prometheus_registry(app_state):
    flask_app = Flask("observability-metrics-test")
    register_observability_routes(flask_app, app_state.runtime)

    with flask_app.test_client() as client:
        response = client.get("/metrics")

    assert response.status_code == 200
    assert response.content_type.startswith("text/plain")
    assert b"http_requests_total" in response.data


def test_observability_route_label_resolution_and_inflight_finish():
    assert _resolve_route_label(SimpleNamespace(url_rule=SimpleNamespace(rule="/orders/<id>"))) == (
        "/orders/<id>"
    )
    assert _resolve_route_label(SimpleNamespace(url_rule=None, endpoint="healthz")) == "healthz"
    assert _resolve_route_label(SimpleNamespace(url_rule=None, endpoint=None)) == "__unmatched__"

    runtime = SimpleNamespace(REQUESTS_IN_PROGRESS=_Metric())
    request_stub = SimpleNamespace(_metrics_in_progress=False)
    _finish_in_progress(runtime, request_stub, method="GET", route="/noop")
    assert runtime.REQUESTS_IN_PROGRESS.handles == {}

    request_stub = SimpleNamespace(_metrics_in_progress=True)
    _finish_in_progress(runtime, request_stub, method="POST", route="/order")
    handle = runtime.REQUESTS_IN_PROGRESS.labels(method="POST", route="/order")
    assert handle.dec_calls == 1
    assert request_stub._metrics_in_progress is False


def test_register_metrics_hooks_tracks_unmatched_500_requests():
    flask_app = Flask("observability-hooks-test")
    runtime = SimpleNamespace(
        REQUESTS_IN_PROGRESS=_Metric(),
        REQUEST_COUNT=_Metric(),
        REQUEST_LATENCY=_Metric(),
        REQUEST_ERRORS=_Metric(),
    )
    register_metrics_hooks(flask_app, runtime)

    @flask_app.route("/boom")
    def boom():
        return {"error": "boom"}, 500

    with flask_app.test_client() as client:
        response = client.get("/missing")

    assert response.status_code == 404
    count_handle = runtime.REQUEST_COUNT.labels(
        method="GET",
        route="__unmatched__",
        status=404,
    )
    assert count_handle.inc_calls == 1
    inflight_handle = runtime.REQUESTS_IN_PROGRESS.labels(method="GET", route="__unmatched__")
    assert inflight_handle.inc_calls == 1
    assert inflight_handle.dec_calls == 1

    with flask_app.test_client() as client:
        response = client.get("/boom")

    assert response.status_code == 500
    error_handle = runtime.REQUEST_ERRORS.labels(method="GET", route="/boom")
    latency_handle = runtime.REQUEST_LATENCY.labels(method="GET", route="/boom")
    assert error_handle.inc_calls == 1
    assert len(latency_handle.observe_calls) == 1


def test_http_api_compat_wrappers_delegate(monkeypatch):
    observed: list[tuple[str, object, object]] = []

    def record(name):
        def _wrapper(app, ctx):
            observed.append((name, app, ctx))

        return _wrapper

    monkeypatch.setattr("chaos_service.http_api.register_runtime_hooks", record("hooks"))
    monkeypatch.setattr("chaos_service.http_api.register_order_routes", record("order"))
    monkeypatch.setattr("chaos_service.http_api.register_chaos_routes", record("chaos"))

    app = object()
    ctx = object()

    register_hooks(app, ctx)
    register_routes(app, ctx)

    assert observed == [
        ("hooks", app, ctx),
        ("order", app, ctx),
        ("chaos", app, ctx),
    ]


@pytest.mark.parametrize(
    ("method_name", "expected"),
    [
        ("fault_status", {"faults": []}),
        ("inject_fault", {"fault_type": "latency"}),
        ("clear_fault", True),
        ("clear_all_faults", 2),
        ("list_experiments", [{"id": "exp-1"}]),
        ("create_experiment", {"id": "exp-2"}),
        ("get_experiment", {"id": "exp-3"}),
        ("get_report", {"id": "exp-4"}),
        ("stop_experiment", False),
    ],
)
def test_chaos_control_service_delegates_to_fault_injection(
    monkeypatch,
    method_name,
    expected,
):
    runtime = SimpleNamespace(CHAOS_ENABLED=True, redis_client=object())
    service = ChaosControlService(runtime)
    calls: list[tuple[str, tuple, dict]] = []

    def stub(name):
        def _runner(*args, **kwargs):
            calls.append((name, args, kwargs))
            return expected

        return _runner

    monkeypatch.setattr(
        "app.service.chaos_service.fault_injection.list_faults",
        stub("list_faults"),
    )
    monkeypatch.setattr(
        "app.service.chaos_service.fault_injection.build_fault_api_response",
        stub("build_fault_api_response"),
    )
    monkeypatch.setattr(
        "app.service.chaos_service.fault_injection.inject_fault",
        stub("inject_fault"),
    )
    monkeypatch.setattr(
        "app.service.chaos_service.fault_injection.clear_fault",
        stub("clear_fault"),
    )
    monkeypatch.setattr(
        "app.service.chaos_service.fault_injection.clear_all_faults",
        stub("clear_all_faults"),
    )
    monkeypatch.setattr(
        "app.service.chaos_service.fault_injection.list_experiments",
        stub("list_experiments"),
    )
    monkeypatch.setattr(
        "app.service.chaos_service.fault_injection.create_experiment",
        stub("create_experiment"),
    )
    monkeypatch.setattr(
        "app.service.chaos_service.fault_injection.get_experiment",
        stub("get_experiment"),
    )
    monkeypatch.setattr("app.service.chaos_service.fault_injection.get_report", stub("get_report"))
    monkeypatch.setattr(
        "app.service.chaos_service.fault_injection.stop_experiment",
        stub("stop_experiment"),
    )

    kwargs = {}
    if method_name == "inject_fault":
        args = ("latency", {"latency_ms": 10}, 30)
    elif method_name == "clear_fault":
        args = ("latency",)
    elif method_name in {"get_experiment", "get_report", "stop_experiment"}:
        args = ("exp-1",)
    elif method_name == "create_experiment":
        args = ()
        kwargs = {
            "name": "latency-test",
            "hypothesis": "service stays healthy",
            "target": {"endpoint": "/order"},
            "fault_type": "latency",
            "params": {"latency_ms": 50},
            "duration": 30,
        }
    else:
        args = ()

    result = getattr(service, method_name)(*args, **kwargs)

    assert result == expected
    assert calls


def test_chaos_control_service_blocks_when_disabled():
    service = ChaosControlService(SimpleNamespace(CHAOS_ENABLED=False, redis_client=object()))

    with pytest.raises(PermissionError):
        service.ensure_enabled()
