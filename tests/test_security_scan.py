"""security_scan 纯函数逻辑单测（无需起服务）。"""

import security_scan as ss


def test_analyze_sqli_legacy_server_error_high(monkeypatch):
    monkeypatch.setattr(ss, "CONTEXT_AWARE", False)
    payload = "' OR 1=1 --"
    fs = ss.analyze_sqli_probe(500, f"oops {payload}", payload)
    assert len(fs) == 2
    assert any(f["severity"] == "high" and f["name"] == "sqli_causes_server_error" for f in fs)
    assert any(f["name"] == "payload_reflection" for f in fs)


def test_analyze_sqli_context_generic_500_medium(monkeypatch):
    monkeypatch.setattr(ss, "CONTEXT_AWARE", True)
    fs = ss.analyze_sqli_probe(500, '{"error":"internal"}', "x")
    assert any(f["name"] == "sqli_probe_server_error_ambiguous" and f["severity"] == "medium" for f in fs)
    assert not any(f["severity"] == "high" for f in fs)


def test_analyze_sqli_context_500_with_mysql_high(monkeypatch):
    monkeypatch.setattr(ss, "CONTEXT_AWARE", True)
    fs = ss.analyze_sqli_probe(500, "MySQL server version ... syntax error", "x")
    assert any(f["name"] == "sqli_db_or_sql_signal_in_error_body" and f["severity"] == "high" for f in fs)


def test_analyze_sqli_context_201_reflection_low(monkeypatch):
    monkeypatch.setattr(ss, "CONTEXT_AWARE", True)
    payload = "sku-reflect"
    body = f'{{"order_id":"abc","item_id":"{payload}"}}'
    fs = ss.analyze_sqli_probe(201, body, payload)
    names = {f["name"] for f in fs}
    assert "payload_reflection_in_success_body" in names
    assert all(f["severity"] != "high" for f in fs)


def test_analyze_sqli_context_400_reflection_medium(monkeypatch):
    monkeypatch.setattr(ss, "CONTEXT_AWARE", True)
    p = "bad-item"
    fs = ss.analyze_sqli_probe(400, f'{{"error":"invalid {p}"}}', p)
    assert any(f["name"] == "payload_reflection_client_error" for f in fs)
