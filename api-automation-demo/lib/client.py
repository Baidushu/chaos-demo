"""httpx 封装 + 请求/响应日志（接口自动化常用）。"""

from __future__ import annotations

import logging
import time
from typing import Any

import httpx

log = logging.getLogger("api_automation.client")


class LoggingHttpClient:
    def __init__(
        self,
        base_url: str = "",
        *,
        transport: httpx.BaseTransport | None = None,
        timeout: float = 10.0,
    ) -> None:
        self._base = base_url.rstrip("/")
        url = self._base if self._base else "http://mock"
        self._client = httpx.Client(base_url=url, transport=transport, timeout=timeout)

    def request(self, method: str, path: str, **kwargs: Any) -> httpx.Response:
        p = path if path.startswith("/") else f"/{path}"
        safe_kw = {k: kwargs[k] for k in ("json", "headers", "params") if k in kwargs}
        log.info("HTTP %s %s data=%s", method, p, safe_kw)
        t0 = time.perf_counter()
        resp = self._client.request(method, p, **kwargs)
        dt_ms = (time.perf_counter() - t0) * 1000
        log.info("HTTP done status=%s elapsed_ms=%.1f", resp.status_code, dt_ms)
        return resp

    def close(self) -> None:
        self._client.close()
