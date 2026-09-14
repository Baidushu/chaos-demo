"""管理接口鉴权单测：`/fault/*`、`/chaos/*` 的写操作必须带令牌。

覆盖：
1. 未配置 `CHAOS_ADMIN_TOKEN` → 保持放行（本地零配置演示），但**启动时必须有告警**；
2. 配置令牌后：缺失/错误令牌 401，正确令牌放行，令牌比较不泄露期望值；
3. 只读接口（`GET /fault/status`、`GET /chaos/experiments`）保持公开，便于巡检/大盘；
4. 前缀 + 方法级守卫 = 新增写接口默认被保护（fail-closed），而不是默认裸奔。
"""

from __future__ import annotations

import logging
import sys
from pathlib import Path

from flask import Flask, jsonify

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from app.api.admin_auth import (  # noqa: E402
    ADMIN_TOKEN_ENV,
    ADMIN_TOKEN_HEADER,
    admin_auth_status,
    is_protected_request,
    register_admin_guard,
    token_accepted,
)

TOKEN = "test-admin-token-1234"


class _Recorder(logging.Handler):
    def __init__(self) -> None:
        super().__init__()
        self.messages: list[str] = []

    def emit(self, record: logging.LogRecord) -> None:  # pragma: no cover - 简单收集
        self.messages.append(record.getMessage())


class TestProtectedRequestPolicy:
    def test_write_methods_on_management_prefixes_are_protected(self):
        for method, path in (
            ("POST", "/fault/inject"),
            ("POST", "/fault/clear"),
            ("POST", "/fault/clear-all"),
            ("DELETE", "/fault/inject/exception"),
            ("POST", "/chaos/experiments"),
            ("POST", "/chaos/experiments/abc/stop"),
        ):
            assert is_protected_request(method, path) is True, (method, path)

    def test_read_only_and_business_routes_are_not_protected(self):
        for method, path in (
            ("GET", "/fault/status"),
            ("GET", "/chaos/experiments"),
            ("HEAD", "/fault/status"),
            ("POST", "/order"),
            ("GET", "/healthz"),
            ("POST", "/metrics"),
        ):
            assert is_protected_request(method, path) is False, (method, path)


class TestTokenComparison:
    def test_missing_token_env_accepts_anything(self, monkeypatch):
        monkeypatch.delenv(ADMIN_TOKEN_ENV, raising=False)
        assert token_accepted(None) is True
        assert token_accepted("whatever") is True
        assert admin_auth_status() == "open"

    def test_configured_token_requires_exact_match(self, monkeypatch):
        monkeypatch.setenv(ADMIN_TOKEN_ENV, TOKEN)
        assert token_accepted(TOKEN) is True
        assert token_accepted(f" {TOKEN} ") is True
        assert token_accepted(None) is False
        assert token_accepted("") is False
        assert token_accepted("wrong") is False
        assert token_accepted(TOKEN + "x") is False
        assert admin_auth_status() == "token"

    def test_blank_env_value_counts_as_unconfigured(self, monkeypatch):
        monkeypatch.setenv(ADMIN_TOKEN_ENV, "   ")
        assert admin_auth_status() == "open"


class TestStartupWarning:
    def _register(self, monkeypatch, token: str | None) -> list[str]:
        if token is None:
            monkeypatch.delenv(ADMIN_TOKEN_ENV, raising=False)
        else:
            monkeypatch.setenv(ADMIN_TOKEN_ENV, token)
        flask_app = Flask("admin-auth-warning-test")
        recorder = _Recorder()
        target_logger = flask_app.logger
        target_logger.addHandler(recorder)
        try:
            register_admin_guard(flask_app)
        finally:
            target_logger.removeHandler(recorder)
        return recorder.messages

    def test_warns_when_token_missing(self, monkeypatch):
        messages = self._register(monkeypatch, None)
        assert any("unauthenticated" in message for message in messages)
        assert any(ADMIN_TOKEN_ENV in message for message in messages)

    def test_no_warning_when_token_configured(self, monkeypatch):
        messages = self._register(monkeypatch, TOKEN)
        assert messages == []


class TestGuardThroughFlask:
    def _build(self, monkeypatch, token: str | None) -> Flask:
        if token is None:
            monkeypatch.delenv(ADMIN_TOKEN_ENV, raising=False)
        else:
            monkeypatch.setenv(ADMIN_TOKEN_ENV, token)
        flask_app = Flask("admin-auth-guard-test")
        register_admin_guard(flask_app)

        @flask_app.route("/fault/inject", methods=["POST"])
        def inject():
            return jsonify({"status": "injected"}), 201

        @flask_app.route("/fault/status", methods=["GET"])
        def status():
            return jsonify({"faults": []})

        # 模拟"将来新增的写接口"：只挂路由、不额外加鉴权，验证前缀守卫默认生效
        @flask_app.route("/chaos/experiments", methods=["POST"])
        def future_write():
            return jsonify({"experiment": {}}), 201

        return flask_app

    def test_open_when_unconfigured(self, monkeypatch):
        client = self._build(monkeypatch, None).test_client()
        assert client.post("/fault/inject", json={"type": "latency"}).status_code == 201
        assert client.post("/chaos/experiments", json={}).status_code == 201

    def test_rejects_missing_token(self, monkeypatch):
        client = self._build(monkeypatch, TOKEN).test_client()
        resp = client.post("/fault/inject", json={"type": "latency"})
        assert resp.status_code == 401
        body = resp.get_json()
        assert body["code"] == "admin_auth_required"
        assert TOKEN not in resp.get_data(as_text=True)

    def test_rejects_wrong_token(self, monkeypatch):
        client = self._build(monkeypatch, TOKEN).test_client()
        resp = client.post(
            "/fault/inject",
            json={"type": "latency"},
            headers={ADMIN_TOKEN_HEADER: "nope"},
        )
        assert resp.status_code == 401

    def test_accepts_correct_token(self, monkeypatch):
        client = self._build(monkeypatch, TOKEN).test_client()
        resp = client.post(
            "/fault/inject",
            json={"type": "latency"},
            headers={ADMIN_TOKEN_HEADER: TOKEN},
        )
        assert resp.status_code == 201

    def test_read_only_endpoint_stays_open(self, monkeypatch):
        client = self._build(monkeypatch, TOKEN).test_client()
        assert client.get("/fault/status").status_code == 200

    def test_new_write_route_is_protected_by_prefix(self, monkeypatch):
        """fail-closed：将来新增的 /chaos 写接口无需改代码就已受保护。"""
        client = self._build(monkeypatch, TOKEN).test_client()
        assert client.post("/chaos/experiments", json={}).status_code == 401
        ok = client.post(
            "/chaos/experiments", json={}, headers={ADMIN_TOKEN_HEADER: TOKEN}
        )
        assert ok.status_code == 201


class TestGuardWiredIntoRealApp:
    """确认真实应用（`build_application`）注册了守卫——自建 Flask app 测不出接线错误。"""

    def test_real_app_requires_token_when_configured(self, client, monkeypatch):
        monkeypatch.setenv(ADMIN_TOKEN_ENV, TOKEN)
        resp = client.post(
            "/fault/inject",
            json={"type": "latency", "params": {"latency_ms": 10}},
        )
        assert resp.status_code == 401
        assert resp.get_json()["code"] == "admin_auth_required"

    def test_real_app_accepts_token_and_keeps_reads_open(self, client, monkeypatch):
        monkeypatch.setenv(ADMIN_TOKEN_ENV, TOKEN)
        injected = client.post(
            "/fault/inject",
            json={"type": "latency", "params": {"latency_ms": 10}, "ttl_sec": 30},
            headers={ADMIN_TOKEN_HEADER: TOKEN},
        )
        assert injected.status_code == 201
        assert client.get("/fault/status").status_code == 200
        cleared = client.post("/fault/clear-all", headers={ADMIN_TOKEN_HEADER: TOKEN})
        assert cleared.status_code == 200

    def test_real_app_open_without_token_env(self, client, monkeypatch):
        monkeypatch.delenv(ADMIN_TOKEN_ENV, raising=False)
        injected = client.post(
            "/fault/inject",
            json={"type": "latency", "params": {"latency_ms": 10}, "ttl_sec": 30},
        )
        assert injected.status_code == 201
        client.post("/fault/clear-all")
