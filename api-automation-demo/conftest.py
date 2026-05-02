from __future__ import annotations

import os
from pathlib import Path

import httpx
import pytest
import yaml

from lib.client import LoggingHttpClient
from lib.logging_config import setup_logging

setup_logging()


def _load_cases() -> list:
    data_file = Path(__file__).resolve().parent / "data" / "api_cases.yaml"
    data = yaml.safe_load(data_file.read_text(encoding="utf-8"))
    return list(data["cases"])


def pytest_generate_tests(metafunc: pytest.Metafunc) -> None:
    if "api_case" in metafunc.fixturenames:
        cases = _load_cases()
        metafunc.parametrize("api_case", cases, ids=lambda c: str(c["id"]))


@pytest.fixture(scope="session")
def base_url() -> str:
    return os.getenv("API_AUTOMATION_BASE_URL", "").strip().rstrip("/")


@pytest.fixture
def http_client(api_case: dict, base_url: str):
    if base_url:
        client = LoggingHttpClient(base_url=base_url)
        yield client
        client.close()
        return

    if api_case["id"] == "flaky_ok_mock":
        state = {"n": 0}

        def handler(request: httpx.Request) -> httpx.Response:
            state["n"] += 1
            if state["n"] < 3:
                return httpx.Response(503, json={"error": "transient"})
            return httpx.Response(200, json={"status": "healthy"})

        transport = httpx.MockTransport(handler)
        client = LoggingHttpClient(base_url="http://mock", transport=transport)
        yield client
        client.close()
        return

    mock = api_case.get("mock") or {}
    status = int(mock.get("status_code", 200))
    body = mock.get("json")
    text = mock.get("text")

    def handler(request: httpx.Request) -> httpx.Response:
        if body is not None:
            return httpx.Response(status, json=body)
        return httpx.Response(status, text=text or "")

    transport = httpx.MockTransport(handler)
    client = LoggingHttpClient(base_url="http://mock", transport=transport)
    yield client
    client.close()
