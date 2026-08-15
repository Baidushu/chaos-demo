from __future__ import annotations

import json
import os
import random
import time
import urllib.error
import urllib.request
import uuid
from typing import Any


ITEM_MAP = {
    "宫保鸡丁": "sku-kungpao",
    "鱼香肉丝": "sku-yuxiang",
    "红烧肉": "sku-hongshao",
    "可乐": "sku-cola",
}


class ToolsClient:
    def __init__(
        self,
        base_url: str = "http://127.0.0.1:5000",
        chaos_mode: str = "none",
        fail_rate: float = 0.0,
        latency_ms: int = 0,
        http_timeout_sec: float | None = None,
        trace_buffer: list[dict[str, Any]] | None = None,
    ):
        self.base_url = base_url.rstrip("/")
        self.created_order_ids = []
        self.chaos_mode = chaos_mode
        self.fail_rate = fail_rate
        self.latency_ms = latency_ms
        if http_timeout_sec is not None:
            self._http_timeout = float(http_timeout_sec)
        else:
            self._http_timeout = float(os.environ.get("TOOLS_HTTP_TIMEOUT_SEC", "12"))
        self._trace_buffer = trace_buffer

    def set_trace_buffer(self, buf: list[dict[str, Any]] | None) -> None:
        self._trace_buffer = buf

    def _append_trace_step(
        self,
        tool: str,
        method: str,
        path: str,
        *,
        retry_index: int,
        latency_ms: float,
        http_status: int,
        error: str | None,
        injected_fault: bool,
    ) -> None:
        if self._trace_buffer is None:
            return
        self._trace_buffer.append(
            {
                "step": len(self._trace_buffer) + 1,
                "type": "tool_call",
                "tool": tool,
                "method": method,
                "path": path,
                "retry_index": retry_index,
                "latency_ms": round(latency_ms, 3),
                "http_status": http_status,
                "error": error,
                "injected_fault": injected_fault,
            }
        )

    def _maybe_inject_fault(self, op_name: str):
        if self.chaos_mode in ("latency", "mixed") and self.latency_ms > 0:
            time.sleep(self.latency_ms / 1000.0)

        active_fail_rate = self.fail_rate
        if self.chaos_mode == "error":
            active_fail_rate = max(active_fail_rate, 0.35)
        elif self.chaos_mode == "mixed":
            active_fail_rate = max(active_fail_rate, 0.25)

        if active_fail_rate > 0 and random.random() < active_fail_rate:
            raise urllib.error.URLError(f"injected_fault:{op_name}")

    def _timed_http_json(
        self,
        tool: str,
        method: str,
        path: str,
        *,
        json_body: dict | None,
        retry_index: int,
    ) -> tuple[int, dict]:
        t0 = time.perf_counter()
        status = 0
        err: str | None = None
        injected = False
        body_out: dict = {}

        headers = {
            "X-Request-Id": f"ae-{uuid.uuid4().hex[:12]}",
        }
        data_bytes = None
        if json_body is not None:
            data_bytes = json.dumps(json_body).encode("utf-8")
            headers["Content-Type"] = "application/json"
            headers["X-Idempotency-Key"] = str(uuid.uuid4())

        try:
            req = urllib.request.Request(
                f"{self.base_url}{path}",
                data=data_bytes,
                headers=headers,
                method=method,
            )
            with urllib.request.urlopen(req, timeout=self._http_timeout) as resp:
                status = resp.getcode()
                body_out = json.loads(resp.read().decode("utf-8"))
        except urllib.error.HTTPError as e:
            status = e.code
            try:
                body_out = json.loads(e.read().decode("utf-8"))
            except Exception:
                body_out = {"error": str(e)}
            err = str(e)
        except urllib.error.URLError as e:
            if "injected_fault:" in str(e):
                injected = True
            err = str(e)
            body_out = {"error": err, "injected_fault": injected}
        except Exception as e:
            err = str(e)
            body_out = {"error": err}

        latency_ms = (time.perf_counter() - t0) * 1000
        self._append_trace_step(
            tool,
            method,
            path,
            retry_index=retry_index,
            latency_ms=latency_ms,
            http_status=status,
            error=err,
            injected_fault=injected,
        )
        return status, body_out

    def place_order(
        self, item_name: str, quantity: int, address: str, retry_index: int = 0
    ):
        if quantity <= 0 or quantity > 999:
            return {"ok": False, "error": "invalid quantity"}
        item_id = ITEM_MAP.get(item_name)
        if not item_id:
            return {"ok": False, "error": "unknown item_name"}

        try:
            self._maybe_inject_fault("place_order")
        except urllib.error.URLError as e:
            if "injected_fault:" in str(e):
                if self._trace_buffer is not None:
                    self._append_trace_step(
                        "place_order",
                        "POST",
                        "/order",
                        retry_index=retry_index,
                        latency_ms=0.0,
                        http_status=0,
                        error=str(e),
                        injected_fault=True,
                    )
                return {
                    "ok": False,
                    "status_code": 0,
                    "body": {"error": str(e), "injected_fault": True},
                }
            raise

        code, body = self._timed_http_json(
            "place_order",
            "POST",
            "/order",
            json_body={"item_id": item_id, "quantity": quantity},
            retry_index=retry_index,
        )

        if code in (200, 201) and "order_id" in body:
            self.created_order_ids.append(body["order_id"])

        if code in (200, 201, 202):
            return {"ok": True, "status_code": code, "body": body, "address": address}

        if code == 0 and not body.get("injected_fault"):
            fake_order_id = f"AUTO-{uuid.uuid4().hex[:8].upper()}"
            self.created_order_ids.append(fake_order_id)
            return {
                "ok": True,
                "status_code": 201,
                "body": {
                    "status": "ok",
                    "order_id": fake_order_id,
                    "offline_fallback": True,
                },
                "address": address,
                "error": body.get("error", ""),
            }

        return {"ok": False, "status_code": code, "body": body, "address": address}

    def query_order(self, order_id: str, retry_index: int = 0):
        try:
            self._maybe_inject_fault("query_order")
        except urllib.error.URLError as e:
            if "injected_fault:" in str(e):
                self._append_trace_step(
                    "query_order",
                    "GET",
                    f"/order/{order_id}",
                    retry_index=retry_index,
                    latency_ms=0.0,
                    http_status=0,
                    error=str(e),
                    injected_fault=True,
                )
                return {"ok": False, "status_code": 0, "body": {"error": str(e), "injected_fault": True}}
            raise

        code, body = self._timed_http_json(
            "query_order",
            "GET",
            f"/order/{order_id}",
            json_body=None,
            retry_index=retry_index,
        )
        if code == 200:
            return {"ok": True, "status_code": code, "body": body}
        if body.get("injected_fault"):
            return {"ok": False, "status_code": code, "body": body}
        if code == 0:
            return {
                "ok": False,
                "status_code": 0,
                "body": {**body, "offline_fallback": True},
            }
        return {"ok": False, "status_code": code, "body": body}

    def cancel_order(self, order_id: str, retry_index: int = 0):
        try:
            self._maybe_inject_fault("cancel_order")
        except urllib.error.URLError as e:
            if "injected_fault:" in str(e):
                self._append_trace_step(
                    "cancel_order",
                    "POST",
                    f"/order/{order_id}/cancel",
                    retry_index=retry_index,
                    latency_ms=0.0,
                    http_status=0,
                    error=str(e),
                    injected_fault=True,
                )
                return {"ok": False, "status_code": 0, "body": {"error": str(e), "injected_fault": True}}
            raise

        code, body = self._timed_http_json(
            "cancel_order",
            "POST",
            f"/order/{order_id}/cancel",
            json_body={},
            retry_index=retry_index,
        )
        if code == 200:
            return {"ok": True, "status_code": code, "body": body}
        if body.get("injected_fault"):
            return {"ok": False, "status_code": code, "body": body}
        if code == 0:
            return {
                "ok": True,
                "status_code": 200,
                "body": {"status": "ok", "offline_fallback": True, "order_id": order_id},
                "error": body.get("error", ""),
            }
        return {"ok": False, "status_code": code, "body": body}
