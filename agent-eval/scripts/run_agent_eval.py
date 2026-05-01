import argparse
import json
import os
import random
import re
import time
import urllib.error
from pathlib import Path
from urllib import request

from tools_client import ToolsClient


ROOT = Path(__file__).resolve().parents[1]
DATA_PATH = ROOT / "datasets" / "tool_eval.jsonl"
REPORT_DIR = ROOT / "reports"
REPORT_DIR.mkdir(parents=True, exist_ok=True)
RAW_RESULT_PATH = REPORT_DIR / "agent_raw_latest.json"
AGENT_MODE = os.getenv("AGENT_MODE", "rule")  # rule | ollama
OLLAMA_ENDPOINT = os.getenv("OLLAMA_ENDPOINT", "http://localhost:11434/api/generate")
OLLAMA_MODEL = os.getenv("OLLAMA_MODEL", "qwen2.5:7b")
MAX_RETRY = int(os.getenv("AGENT_MAX_RETRY", "2"))
ALLOWED_TOOLS = {"place_order", "query_order", "cancel_order", "ask_user", "workflow"}


def parse_args_from_text(text: str):
    args = {}
    m_order = re.search(r"(A\d{4,})", text, re.IGNORECASE)
    if m_order:
        args["order_id"] = m_order.group(1).upper()
    m_qty = re.search(r"(\d+)\s*件|数量\s*(\d+)", text)
    if m_qty:
        args["quantity"] = int(m_qty.group(1) or m_qty.group(2))
    for item in ["宫保鸡丁", "鱼香肉丝", "红烧肉", "可乐"]:
        if item in text:
            args["item_name"] = item
            break
    if "号" in text:
        m_addr = re.search(r"([\u4e00-\u9fa5A-Za-z0-9\-]{2,20}号)", text)
        if m_addr:
            args["address"] = m_addr.group(1)
    return args


def _ollama_llm_meta(raw: dict) -> dict:
    """Ollama /api/generate 返回的 token 计数（不同版本字段可能略有差异）。"""
    prompt_t = raw.get("prompt_eval_count")
    eval_t = raw.get("eval_count")
    total = None
    if prompt_t is not None and eval_t is not None:
        try:
            total = int(prompt_t) + int(eval_t)
        except (TypeError, ValueError):
            total = None
    return {
        "llm_prompt_tokens": prompt_t,
        "llm_completion_tokens": eval_t,
        "llm_total_tokens": total,
    }


def plan_with_ollama(text: str):
    prompt = (
        "你是下单助手路由器。你只能输出一个JSON对象，不要输出其他内容。\n"
        "可用工具: place_order, query_order, cancel_order, ask_user\n"
        "如果信息不足或请求不合理，使用 ask_user。\n"
        "JSON格式: {\"tool\":\"...\",\"args\":{...}}\n"
        f"用户输入: {text}"
    )
    payload = json.dumps({"model": OLLAMA_MODEL, "prompt": prompt, "stream": False}).encode("utf-8")
    req = request.Request(OLLAMA_ENDPOINT, data=payload, method="POST")
    req.add_header("Content-Type", "application/json")
    with request.urlopen(req, timeout=8) as resp:
        raw = json.loads(resp.read().decode("utf-8"))
        meta = _ollama_llm_meta(raw)
        body = raw.get("response", "").strip()
        m = re.search(r"\{.*\}", body, re.DOTALL)
        if not m:
            return (
                {"tool": "ask_user", "args": {"reason": "invalid planner output"}, "_planner_valid": False},
                meta,
            )
        try:
            plan = json.loads(m.group(0))
            plan["_planner_valid"] = True
            return plan, meta
        except Exception:
            return (
                {"tool": "ask_user", "args": {"reason": "json parse fail"}, "_planner_valid": False},
                meta,
            )


def validate_plan(plan):
    if not isinstance(plan, dict):
        return {"tool": "ask_user", "args": {"reason": "plan not object"}, "_planner_valid": False}
    tool = plan.get("tool")
    if tool not in ALLOWED_TOOLS:
        return {"tool": "ask_user", "args": {"reason": "tool not allowed"}, "_planner_valid": False}
    if tool == "workflow":
        steps = plan.get("steps")
        if not isinstance(steps, list) or not steps:
            return {"tool": "ask_user", "args": {"reason": "invalid workflow steps"}, "_planner_valid": False}
        sanitized_steps = []
        for step in steps:
            if not isinstance(step, dict):
                return {"tool": "ask_user", "args": {"reason": "invalid workflow step"}, "_planner_valid": False}
            st = step.get("tool")
            if st not in {"place_order", "query_order", "cancel_order", "ask_user"}:
                return {"tool": "ask_user", "args": {"reason": "workflow tool not allowed"}, "_planner_valid": False}
            sa = step.get("args", {})
            if not isinstance(sa, dict):
                sa = {}
            sanitized_steps.append({"tool": st, "args": sa})
        return {"tool": "workflow", "steps": sanitized_steps, "_planner_valid": plan.get("_planner_valid", True)}
    args = plan.get("args", {})
    if not isinstance(args, dict):
        args = {}
    return {"tool": tool, "args": args, "_planner_valid": plan.get("_planner_valid", True)}


def rule_plan(text: str):
    args = parse_args_from_text(text)
    if "火星" in text:
        return {"tool": "ask_user", "args": {"reason": "unsupported destination"}}
    if "取消" in text and "查询" in text:
        order_id = args.get("order_id", "A0000")
        return {
            "tool": "workflow",
            "steps": [
                {"tool": "cancel_order", "args": {"order_id": order_id}},
                {"tool": "query_order", "args": {"order_id": order_id}},
            ],
        }
    if "查询" in text or "查一下" in text:
        return {"tool": "query_order", "args": {"order_id": args.get("order_id", "A0000")}}
    if "取消" in text:
        return {"tool": "cancel_order", "args": {"order_id": args.get("order_id", "A0000")}}
    if "9999999" in text or "DROP TABLE" in text or "别猜id" in text:
        return {"tool": "ask_user", "args": {"reason": "invalid or missing args"}}
    if "下单" in text:
        if "item_name" not in args or "address" not in args:
            return {"tool": "ask_user", "args": {"reason": "missing args"}}
        return {
            "tool": "place_order",
            "args": {
                "item_name": args["item_name"],
                "quantity": args.get("quantity", 1),
                "address": args["address"],
            },
        }
    return {"tool": "ask_user", "args": {"reason": "unknown intent"}}


def execute_plan(case, client: ToolsClient):
    text = case["input"]
    called_tools = []
    called_args = {}
    retry_count = 0
    final_response = "已处理。"
    tool_results = []
    planner_fallback = False
    llm_meta = {
        "llm_prompt_tokens": None,
        "llm_completion_tokens": None,
        "llm_total_tokens": None,
    }

    if AGENT_MODE == "ollama":
        try:
            plan, llm_meta = plan_with_ollama(text)
        except Exception:
            plan = rule_plan(text)
            planner_fallback = True
    else:
        plan = rule_plan(text)

    if AGENT_MODE == "ollama":
        before_valid = bool(plan.get("_planner_valid", True))
        plan = validate_plan(plan)
        if not before_valid or not plan.get("_planner_valid", True):
            planner_fallback = True
            # Invalid planner output should degrade to clarification.
            plan = {"tool": "ask_user", "args": {"reason": "planner output invalid"}, "_planner_valid": False}

    steps = plan.get("steps") if plan.get("tool") == "workflow" else [plan]
    for step in steps:
        tool = step.get("tool", "ask_user")
        args = step.get("args", {})
        called_tools.append(tool)
        called_args.update(args)
        if tool == "place_order":
            quantity = int(args.get("quantity", 1))
            res = client.place_order(
                item_name=args.get("item_name", ""),
                quantity=quantity,
                address=args.get("address", ""),
            )
            tool_results.append({"tool": tool, "result": res})
            current_try = 0
            while (not res.get("ok")) and current_try < MAX_RETRY:
                current_try += 1
                retry_count += 1
                res = client.place_order(
                    item_name=args.get("item_name", ""),
                    quantity=quantity,
                    address=args.get("address", ""),
                )
                tool_results.append({"tool": f"{tool}_retry_{current_try}", "result": res})

            if res.get("ok"):
                order_id = res.get("body", {}).get("order_id")
                final_response = f"已下单，订单号 {order_id}" if order_id else "已下单。"
            else:
                final_response = "下单失败，请稍后重试。"
        elif tool == "query_order":
            res = client.query_order(order_id=args.get("order_id", ""))
            tool_results.append({"tool": tool, "result": res})
            final_response = "订单查询完成。" if res.get("ok") else "订单不存在或查询失败。"
        elif tool == "cancel_order":
            res = client.cancel_order(order_id=args.get("order_id", ""))
            tool_results.append({"tool": tool, "result": res})
            final_response = "订单取消完成。" if res.get("ok") else "订单取消失败。"
        else:
            tool_results.append({"tool": "ask_user", "result": {"ok": True}})
            final_response = "参数不足或请求不合理，请补充信息。"

    token_usage_estimated = max(
        60, len(text) * 3 + len(final_response) * 2 + retry_count * 25 + len(called_tools) * 30
    )
    llm_total = llm_meta.get("llm_total_tokens")
    prefer = os.getenv("TOKEN_METRIC", "auto").lower()
    if prefer == "estimated":
        token_usage = token_usage_estimated
        token_usage_source = "estimated"
    elif prefer == "llm":
        token_usage = int(llm_total) if llm_total is not None else token_usage_estimated
        token_usage_source = "ollama" if llm_total is not None else "estimated_fallback"
    else:
        # auto: 有 Ollama 计数则用真实值，否则启发式
        if llm_total is not None:
            token_usage = int(llm_total)
            token_usage_source = "ollama"
        else:
            token_usage = token_usage_estimated
            token_usage_source = "estimated"

    return {
        "called_tools": called_tools,
        "called_args": called_args,
        "retry_count": retry_count,
        "tool_calls_count": len(called_tools),
        "token_usage": token_usage,
        "token_usage_estimated": token_usage_estimated,
        "token_usage_llm": llm_total,
        "token_usage_source": token_usage_source,
        "llm_prompt_tokens": llm_meta.get("llm_prompt_tokens"),
        "llm_completion_tokens": llm_meta.get("llm_completion_tokens"),
        "final_response": final_response,
        "tool_results": tool_results,
        "agent_mode": AGENT_MODE,
        "planner_valid": bool(plan.get("_planner_valid", True)),
        "planner_fallback": planner_fallback,
        "chaos_mode": client.chaos_mode,
    }


def preflight_order_service(base_url: str) -> None:
    if os.getenv("SKIP_TOOLS_HEALTH_CHECK", "").strip().lower() in ("1", "true", "yes", "on"):
        return
    url = base_url.rstrip("/") + "/healthz"
    try:
        req = request.Request(url, method="GET")
        with request.urlopen(req, timeout=8) as resp:
            if int(resp.getcode()) != 200:
                raise SystemExit(
                    f"Order service {url} returned {resp.getcode()}, expected 200. "
                    "Start `docker compose up -d` and wait, or set SKIP_TOOLS_HEALTH_CHECK=1."
                )
    except urllib.error.URLError as e:
        raise SystemExit(
            f"Cannot reach order service at {url} (TOOLS_BASE_URL). "
            "Start the stack, then retry; or set SKIP_TOOLS_HEALTH_CHECK=1 for offline runs.\n"
            f"  ({e})"
        ) from e


def load_cases():
    cases = []
    with DATA_PATH.open("r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line:
                cases.append(json.loads(line))
    return cases


def parse_args():
    parser = argparse.ArgumentParser(description="Run agent evaluation with optional chaos mode.")
    parser.add_argument("--chaos", choices=["none", "latency", "error", "mixed"], default="none")
    parser.add_argument("--fail-rate", type=float, default=0.0, dest="fail_rate")
    parser.add_argument("--latency-ms", type=int, default=0, dest="latency_ms")
    return parser.parse_args()


def main():
    args = parse_args()
    random.seed(int(os.getenv("EVAL_SEED", "42")))
    base = os.getenv("TOOLS_BASE_URL", "http://127.0.0.1:5000")
    preflight_order_service(base)
    client = ToolsClient(
        base_url=base,
        chaos_mode=args.chaos,
        fail_rate=args.fail_rate,
        latency_ms=args.latency_ms,
    )
    cases = load_cases()
    results = []
    for case in cases:
        out = execute_plan(case, client)
        results.append(
            {
                "id": case["id"],
                "category": case["category"],
                "input": case["input"],
                "expected_tools": case.get("expected_tools", []),
                "expected_args": case.get("expected_args", {}),
                "forbidden_behavior": case.get("forbidden_behavior", []),
                **out,
                "timestamp": int(time.time()),
            }
        )

    payload = {
        "generated_at": int(time.time()),
        "chaos_mode": args.chaos,
        "chaos_fail_rate": args.fail_rate,
        "chaos_latency_ms": args.latency_ms,
        "cases": results,
    }
    with RAW_RESULT_PATH.open("w", encoding="utf-8") as f:
        json.dump(payload, f, ensure_ascii=False, indent=2)
    print(f"Saved raw result: {RAW_RESULT_PATH}")


if __name__ == "__main__":
    main()
