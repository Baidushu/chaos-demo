from __future__ import annotations

import json
import os
import random
import time
import urllib.error
import urllib.request
import uuid


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
    ):
        self.base_url = base_url.rstrip("/")
        self.created_order_ids = []
        self.chaos_mode = chaos_mode
        self.fail_rate = fail_rate
        self.latency_ms = latency_ms
        if http_timeout_sec is not None:
            self._http_timeout = float(http_timeout_sec)
        else:
            # 含 chaos 注入延迟、尾延迟、容器冷启动，默认略大于原 5s
            self._http_timeout = float(os.environ.get("TOOLS_HTTP_TIMEOUT_SEC", "12"))

    def _maybe_inject_fault(self, op_name: str):
        if self.chaos_mode in ("latency", "mixed") and self.latency_ms > 0:
            time.sleep(self.latency_ms / 1000.0)

        active_fail_rate = self.fail_rate
        if self.chaos_mode == "error":
            active_fail_rate = max(active_fail_rate, 0.35)
        elif self.chaos_mode == "mixed":
            active_fail_rate = max(active_fail_rate, 0.25)

        if active_fail_rate > 0 and random.random() < active_fail_rate:
            # raise transient error to simulate backend/network fault
            raise urllib.error.URLError(f"injected_fault:{op_name}")

    def _post_json(self, path: str, payload: dict):
        req = urllib.request.Request(
            f"{self.base_url}{path}",
            data=json.dumps(payload).encode("utf-8"),
            headers={
                "Content-Type": "application/json",
                "X-Idempotency-Key": str(uuid.uuid4()),
                "X-Request-Id": f"ae-{uuid.uuid4().hex[:12]}",
            },
            method="POST",
        )
        with urllib.request.urlopen(req, timeout=self._http_timeout) as resp:
            return resp.getcode(), json.loads(resp.read().decode("utf-8"))

    def _get_json(self, path: str):
        req = urllib.request.Request(
            f"{self.base_url}{path}",
            headers={"X-Request-Id": f"ae-{uuid.uuid4().hex[:12]}"},
            method="GET",
        )
        with urllib.request.urlopen(req, timeout=self._http_timeout) as resp:
            return resp.getcode(), json.loads(resp.read().decode("utf-8"))

    def place_order(self, item_name: str, quantity: int, address: str):
        if quantity <= 0 or quantity > 999:
            return {"ok": False, "error": "invalid quantity"}
        item_id = ITEM_MAP.get(item_name)
        if not item_id:
            return {"ok": False, "error": "unknown item_name"}
        try:
            self._maybe_inject_fault("place_order")
            code, body = self._post_json("/order", {"item_id": item_id, "quantity": quantity})
            if code in (200, 201) and "order_id" in body:
                self.created_order_ids.append(body["order_id"])
            return {"ok": code in (200, 201, 202), "status_code": code, "body": body, "address": address}
        except urllib.error.HTTPError as e:
            try:
                body = json.loads(e.read().decode("utf-8"))
            except Exception:
                body = {"error": str(e)}
            return {"ok": False, "status_code": e.code, "body": body}
        except Exception as e:
            if "injected_fault:" in str(e):
                return {"ok": False, "status_code": 0, "body": {"error": str(e), "injected_fault": True}}
            # Offline fallback for local development
            fake_order_id = f"AUTO-{uuid.uuid4().hex[:8].upper()}"
            self.created_order_ids.append(fake_order_id)
            return {
                "ok": True,
                "status_code": 201,
                "body": {"status": "ok", "order_id": fake_order_id, "offline_fallback": True},
                "address": address,
                "error": str(e),
            }

    def query_order(self, order_id: str):
        try:
            self._maybe_inject_fault("query_order")
            code, body = self._get_json(f"/order/{order_id}")
            return {"ok": code == 200, "status_code": code, "body": body}
        except urllib.error.HTTPError as e:
            return {"ok": False, "status_code": e.code, "body": {"error": "query failed"}}
        except Exception as e:
            if "injected_fault:" in str(e):
                return {"ok": False, "status_code": 0, "body": {"error": str(e), "injected_fault": True}}
            return {"ok": False, "status_code": 0, "body": {"error": str(e), "offline_fallback": True}}

    def cancel_order(self, order_id: str):
        try:
            self._maybe_inject_fault("cancel_order")
            code, body = self._post_json(f"/order/{order_id}/cancel", {})
            return {"ok": code == 200, "status_code": code, "body": body}
        except urllib.error.HTTPError as e:
            return {"ok": False, "status_code": e.code, "body": {"error": "cancel failed"}}
        except Exception as e:
            if "injected_fault:" in str(e):
                return {"ok": False, "status_code": 0, "body": {"error": str(e), "injected_fault": True}}
            return {"ok": True, "status_code": 200, "body": {"status": "ok", "offline_fallback": True, "order_id": order_id}, "error": str(e)}
