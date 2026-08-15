from __future__ import annotations

import importlib.util
import os
import sys
from functools import lru_cache
from pathlib import Path
from typing import Any, Callable

from ai_platform.tools.base import BaseTool
from ai_platform.tools.executor import ToolExecutionResult
from ai_platform.tools.registry import ToolRegistry


_TEXT_ORDER_OK = "已下单，订单号 {order_id}"
_TEXT_ORDER_OK_SIMPLE = "已下单。"
_TEXT_ORDER_FAIL = "下单失败，请稍后重试。"
_TEXT_QUERY_OK = "订单查询完成。"
_TEXT_QUERY_FAIL = "订单不存在或查询失败。"
_TEXT_CANCEL_OK = "订单取消完成。"
_TEXT_CANCEL_FAIL = "订单取消失败。"
_TEXT_ASK_USER = "参数不足或请求不合理，请补充信息。"


class LegacyToolAdapter(BaseTool):
    def __init__(
        self,
        *,
        name: str,
        description: str,
        schema: dict[str, dict[str, Any]],
        tools_client: Any | None = None,
        action: Callable[..., dict[str, Any]] | None = None,
        max_retry: int = 0,
    ) -> None:
        self.name = name
        self.description = description
        self.schema = schema
        self._tools_client = tools_client
        self._action = action
        self._max_retry = max_retry

    def execute(self, params: dict[str, Any], *, context: Any | None = None) -> ToolExecutionResult:
        if self.name == "ask_user":
            result = {"ok": True, "reason": params.get("reason", "missing args")}
            return ToolExecutionResult(
                tool=self.name,
                ok=True,
                result=result,
                attempts=[{"tool": self.name, "result": result}],
                metadata={"response_text": _TEXT_ASK_USER, "retry_count": 0},
            )

        if self._action is None:
            raise RuntimeError(f"Legacy tool action missing: {self.name}")

        if self.name == "place_order":
            return self._execute_place_order(params)
        if self.name == "query_order":
            return self._execute_query_order(params)
        if self.name == "cancel_order":
            return self._execute_cancel_order(params)
        raise RuntimeError(f"Unsupported legacy tool: {self.name}")

    def _execute_place_order(self, params: dict[str, Any]) -> ToolExecutionResult:
        res = self._action(
            item_name=params.get("item_name", ""),
            quantity=int(params.get("quantity", 1)),
            address=params.get("address", ""),
            retry_index=0,
        )
        attempts = [{"tool": self.name, "result": res}]
        retry_count = 0
        current_try = 0
        while (not res.get("ok")) and current_try < self._max_retry:
            current_try += 1
            retry_count += 1
            res = self._action(
                item_name=params.get("item_name", ""),
                quantity=int(params.get("quantity", 1)),
                address=params.get("address", ""),
                retry_index=current_try,
            )
            attempts.append({"tool": f"{self.name}_retry_{current_try}", "result": res})

        if res.get("ok"):
            order_id = res.get("body", {}).get("order_id")
            text = _TEXT_ORDER_OK.format(order_id=order_id) if order_id else _TEXT_ORDER_OK_SIMPLE
        else:
            text = _TEXT_ORDER_FAIL
        return ToolExecutionResult(
            tool=self.name,
            ok=bool(res.get("ok")),
            result=res,
            attempts=attempts,
            metadata={
                "response_text": text,
                "retry_count": retry_count,
                "chaos_mode": getattr(self._tools_client, "chaos_mode", "none"),
            },
        )

    def _execute_query_order(self, params: dict[str, Any]) -> ToolExecutionResult:
        res = self._action(order_id=params.get("order_id", ""))
        return ToolExecutionResult(
            tool=self.name,
            ok=bool(res.get("ok")),
            result=res,
            attempts=[{"tool": self.name, "result": res}],
            metadata={
                "response_text": _TEXT_QUERY_OK if res.get("ok") else _TEXT_QUERY_FAIL,
                "retry_count": 0,
                "chaos_mode": getattr(self._tools_client, "chaos_mode", "none"),
            },
        )

    def _execute_cancel_order(self, params: dict[str, Any]) -> ToolExecutionResult:
        res = self._action(order_id=params.get("order_id", ""))
        return ToolExecutionResult(
            tool=self.name,
            ok=bool(res.get("ok")),
            result=res,
            attempts=[{"tool": self.name, "result": res}],
            metadata={
                "response_text": _TEXT_CANCEL_OK if res.get("ok") else _TEXT_CANCEL_FAIL,
                "retry_count": 0,
                "chaos_mode": getattr(self._tools_client, "chaos_mode", "none"),
            },
        )


def build_legacy_registry(
    *,
    tools_client: Any | None = None,
    max_retry: int | None = None,
) -> ToolRegistry:
    client = tools_client or _build_default_tools_client()
    retries = max_retry if max_retry is not None else int(os.getenv("AGENT_MAX_RETRY", "2"))
    registry = ToolRegistry()
    registry.register(
        LegacyToolAdapter(
            name="place_order",
            description="Place an order via legacy HTTP tool client.",
            schema={
                "item_name": {"type": str, "required": True},
                "quantity": {"type": int, "required": True},
                "address": {"type": str, "required": True},
            },
            tools_client=client,
            action=client.place_order,
            max_retry=retries,
        )
    )
    registry.register(
        LegacyToolAdapter(
            name="query_order",
            description="Query an order via legacy HTTP tool client.",
            schema={"order_id": {"type": str, "required": True}},
            tools_client=client,
            action=client.query_order,
        )
    )
    registry.register(
        LegacyToolAdapter(
            name="cancel_order",
            description="Cancel an order via legacy HTTP tool client.",
            schema={"order_id": {"type": str, "required": True}},
            tools_client=client,
            action=client.cancel_order,
        )
    )
    registry.register(
        LegacyToolAdapter(
            name="ask_user",
            description="Ask user for more information when args are missing or invalid.",
            schema={"reason": {"type": str, "required": False}},
            tools_client=client,
        )
    )
    return registry


def _build_default_tools_client():
    tools_module = _load_legacy_tools_module()
    base_url = os.getenv("TOOLS_BASE_URL", "http://127.0.0.1:5000")
    chaos_mode = os.getenv("AGENT_CHAOS_MODE", "none")
    fail_rate = float(os.getenv("AGENT_CHAOS_FAIL_RATE", "0"))
    latency_ms = int(os.getenv("AGENT_CHAOS_LATENCY_MS", "0"))
    return tools_module.ToolsClient(
        base_url=base_url,
        chaos_mode=chaos_mode,
        fail_rate=fail_rate,
        latency_ms=latency_ms,
    )


@lru_cache(maxsize=1)
def _load_legacy_tools_module():
    repo_root = Path(__file__).resolve().parents[2]
    script_path = repo_root / "agent-eval" / "scripts" / "tools_client.py"
    scripts_dir = script_path.parent
    if str(scripts_dir) not in sys.path:
        sys.path.insert(0, str(scripts_dir))
    spec = importlib.util.spec_from_file_location("phase22_tools_client", script_path)
    if spec is None or spec.loader is None:  # pragma: no cover - defensive load path
        raise RuntimeError(f"Cannot load legacy tools client module: {script_path}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module
