import logging
from types import SimpleNamespace

import pytest

import app as app_module
from app.factory import create_app as factory_create_app


def test_app_module_compat_wrappers_cover_legacy_exports(app_state, monkeypatch):
    app_state.BUSINESS_TIMEOUT_MS = 999
    assert app_module._order_key("OID-1") == "order:OID-1"

    app_module._put_order_in_store(
        "OID-1",
        {"item_id": "sku-app", "quantity": 1, "status": "created"},
    )
    stored = app_module._get_order_from_store("OID-1")
    assert stored["item_id"] == "sku-app"

    payload_fp = app_module._idem_payload_fingerprint("sku-app", 1)
    state, record = app_module._reserve_idempotency_key("idem-app", payload_fp)
    assert state == "owner"
    assert app_module._idem_store_key("idem-app") == "idem:idem-app"
    assert app_module._load_idempotency_record("idem-app")["state"] == "PROCESSING"
    assert app_module._wait_for_idempotency_result("idem-app", payload_fp)[0] == "processing"

    app_module._save_idempotency_failed(
        "idem-app",
        payload_fp,
        "boom",
        503,
        {"error": "boom"},
    )
    replay_status, replay_body = app_module._build_idempotency_replay_response(
        app_module._load_idempotency_record("idem-app")
    )
    assert replay_status == 503
    assert replay_body["error"] == "boom"

    release_state, release_record = app_module._reserve_idempotency_key("idem-release", payload_fp)
    assert release_state == "owner"
    assert app_module._release_idempotency_reservation("idem-release", release_record) is True

    app_module._finalize_idempotency_success(
        "idem-success",
        payload_fp,
        "OID-SUCCESS",
        response_body={"status": "ok", "order_id": "OID-SUCCESS"},
    )
    assert app_module._load_idempotency_record("idem-success")["state"] == "SUCCESS"

    assert app_module.allow_request_by_rate_limit("127.0.0.1") is True
    assert app_module._cb_parse_open_until("1.5") == 1.5
    assert app_module.record_request() == (0, 0, 0.0)
    app_module.record_success()
    app_module.record_failure_and_maybe_open()
    assert app_module.is_circuit_open() is False

    assert app_module._order_deadline_exceeded(0.04, 0.02, 50) is True
    assert app_module._mask_value("phone", "13800001234") == "***-****-****"
    assert "X-Request-Id" in app_module._sanitize_headers({"X-Request-Id": "rid"})

    monkeypatch.setattr(
        app_module.runtime,
        "app",
        SimpleNamespace(logger=logging.getLogger("app-module-test")),
    )
    app_module._log_json_event(SimpleNamespace(_request_id="rid"), "unit_test")


def test_app_module_runtime_proxy_and_factory():
    assert app_module.app is not None
    assert app_module.runtime is not None
    assert app_module.SERVICE_NAME
    assert factory_create_app().__class__.__name__ == "Flask"
    with pytest.raises(AttributeError):
        app_module.app = None
