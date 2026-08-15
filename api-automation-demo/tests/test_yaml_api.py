from __future__ import annotations

import allure

from lib.retry import retry_call


@allure.epic("QE API Demo")
@allure.feature("YAML data-driven")
def test_yaml_case(api_case: dict, http_client) -> None:
    method = api_case["method"]
    path = api_case["path"]
    headers = api_case.get("headers") or {}
    json_body = api_case.get("json_body")

    def do_request():
        kw: dict = {"headers": headers}
        if json_body is not None:
            kw["json"] = json_body
        r = http_client.request(method, path, **kw)
        if api_case.get("retry") and r.status_code >= 500:
            raise RuntimeError(f"transient http {r.status_code}")
        return r

    if api_case.get("retry"):
        resp = retry_call(
            do_request,
            attempts=int(api_case.get("retry_attempts", 3)),
            delay_sec=float(api_case.get("retry_delay_sec", 0.05)),
            retry_on=(Exception,),
        )
    else:
        resp = do_request()

    ast = api_case["assertions"]
    with allure.step(f"assert status {ast.get('status')}"):
        assert resp.status_code == ast["status"]

    if ast.get("json_contains"):
        data = resp.json()
        with allure.step("assert json_contains"):
            for k, v in ast["json_contains"].items():
                assert data.get(k) == v
