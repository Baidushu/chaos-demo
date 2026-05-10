"""可选流量录制：异步写 JSONL，供 replay 等工具消费；与 http_api.register_hooks after_request 衔接。

知识点：
  【掌握】 TRAFFIC_RECORD_ENABLED 开/关；record_success_traffic 只记「成功且非探针」；
          队列满 put_nowait 静默丢（保护主路径）。
  【理解】  mask_value / sanitize_headers：手机号、姓名类字段脱敏；headers 白名单。
  【关联】  app.py：init_traffic_recording(CTX) 起 daemon 线程；ctx 上 _record_queue / TRAFFIC_RECORD_FILE。

注意：ctx 为 app 模块；线程与队列挂在 ctx 上，与单测 FakeRedis 无冲突。
"""
import json
import queue
import re
import threading
import time


def mask_value(key_name, value):
    """递归脱敏：phone/mobile/name 规则 + 字符串内大陆手机号/中文姓名模式；dict/list 下钻。"""
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
    """只保留白名单头（小写比对），值仍可走 mask_value（如 UA 里的敏感片段）。"""
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
    """后台线程：阻塞读 _record_queue，追加写入 TRAFFIC_RECORD_FILE（JSON Lines）。"""
    while True:
        item = ctx._record_queue.get()
        try:
            ctx.TRAFFIC_RECORD_FILE.parent.mkdir(parents=True, exist_ok=True)
            with ctx.TRAFFIC_RECORD_FILE.open("a", encoding="utf-8") as f:
                f.write(json.dumps(item, ensure_ascii=False) + "\n")
        finally:
            ctx._record_queue.task_done()


def record_success_traffic(ctx, request, response_status):
    """after_request 调用：仅当开关开、2xx/3xx 成功、且非探针/metrics/static 时入队。

    get_json 失败不致命；队列满则丢弃本条（不阻塞请求）。
    """
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
    """app 启动时：若 TRAFFIC_RECORD_ENABLED，创建有界队列并拉起 daemon 写盘线程。"""
    if not getattr(ctx, "TRAFFIC_RECORD_ENABLED", False):
        return
    if getattr(ctx, "_writer_thread", None) and ctx._writer_thread.is_alive():
        return
    if not hasattr(ctx, "_record_queue"):
        ctx._record_queue = queue.Queue(maxsize=ctx.TRAFFIC_RECORD_MAX_QUEUE)
    ctx._writer_thread = threading.Thread(target=traffic_writer, args=(ctx,), daemon=True)
    ctx._writer_thread.start()
