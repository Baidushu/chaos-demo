import json
import queue
import re
import threading
import time


def mask_value(key_name, value):
    key = str(key_name or "").lower()
    if any(k in key for k in ["phone", "mobile"]):
        return "***-****-****"
    if "name" in key:
        return "***"
    if isinstance(value, str):
        v = value
        v = re.sub(r"\b1[3-9]\d{9}\b", "1**********", v)
        v = re.sub(r"([\u4e00-\u9fff]{1})[\u4e00-\u9fff]{1,3}", r"\1**", v)
        return v
    if isinstance(value, dict):
        return {k: mask_value(k, x) for k, x in value.items()}
    if isinstance(value, list):
        return [mask_value("", x) for x in value]
    return value


def sanitize_headers(headers):
    out = {}
    allow = {
        "content-type",
        "x-idempotency-key",
        "x-request-id",
        "user-agent",
        "x-forwarded-for",
    }
    for k, v in headers.items():
        lk = k.lower()
        if lk in allow:
            out[k] = mask_value(k, v)
    return out


def traffic_writer(ctx):
    while True:
        item = ctx._record_queue.get()
        try:
            ctx.TRAFFIC_RECORD_FILE.parent.mkdir(parents=True, exist_ok=True)
            with ctx.TRAFFIC_RECORD_FILE.open("a", encoding="utf-8") as f:
                f.write(json.dumps(item, ensure_ascii=False) + "\n")
        finally:
            ctx._record_queue.task_done()


def record_success_traffic(ctx, request, response_status):
    if not ctx.TRAFFIC_RECORD_ENABLED:
        return
    path = request.path
    if path in ("/healthz", "/live", "/ready", "/metrics") or path.startswith("/static/"):
        return
    if response_status >= 400:
        return
    try:
        body = request.get_json(silent=True)
    except Exception:
        body = None
    event = {
        "ts": int(time.time()),
        "method": request.method,
        "path": path,
        "query": mask_value("query", request.query_string.decode("utf-8", errors="ignore")),
        "headers": sanitize_headers(request.headers),
        "body": mask_value("body", body),
        "status": response_status,
    }
    try:
        ctx._record_queue.put_nowait(event)
    except queue.Full:
        pass


def init_traffic_recording(ctx) -> None:
    if not getattr(ctx, "TRAFFIC_RECORD_ENABLED", False):
        return
    if getattr(ctx, "_writer_thread", None) and ctx._writer_thread.is_alive():
        return
    if not hasattr(ctx, "_record_queue"):
        ctx._record_queue = queue.Queue(maxsize=ctx.TRAFFIC_RECORD_MAX_QUEUE)
    ctx._writer_thread = threading.Thread(target=traffic_writer, args=(ctx,), daemon=True)
    ctx._writer_thread.start()
