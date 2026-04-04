import os
import json
import queue
import random
import re
import threading
import time
import uuid
from pathlib import Path

import redis
from flask import Flask, Response, jsonify, request
from prometheus_client import CONTENT_TYPE_LATEST, Counter, Histogram, generate_latest

app = Flask(__name__)#创建一个网站服务器对象
db_lock = threading.Lock()#模拟数据库行锁
orders = {}#模拟数据库订单表
breaker_lock = threading.Lock()#模拟断路器锁
redis_client = redis.Redis(
    host=os.getenv("REDIS_HOST", "localhost"),
    port=int(os.getenv("REDIS_PORT", "6379")),
    decode_responses=True,
)#模拟redis客户端
RATE_LIMIT_PER_SEC = int(os.getenv("RATE_LIMIT_PER_SEC", "30"))#每秒请求上限
BUSINESS_TIMEOUT_MS = int(os.getenv("BUSINESS_TIMEOUT_MS", "45"))#业务超时时间
BREAKER_FAIL_THRESHOLD = int(os.getenv("BREAKER_FAIL_THRESHOLD", "8"))#熔断失败阈值
BREAKER_WINDOW_SEC = int(os.getenv("BREAKER_WINDOW_SEC", "10"))#熔断窗口时间
BREAKER_OPEN_SEC = int(os.getenv("BREAKER_OPEN_SEC", "8"))#熔断打开时间
ENABLE_RESILIENCE = os.getenv("ENABLE_RESILIENCE", "true").lower() == "true"#是否启用熔断
breaker_failures = []#熔断失败记录
breaker_open_until = 0.0#熔断打开时间

REQUEST_COUNT = Counter(
    "http_requests_total",
    "Total HTTP requests",
    ["method", "endpoint", "status"],
)
REQUEST_ERRORS = Counter(
    "http_request_errors_total",
    "Total HTTP 5xx responses",
    ["method", "endpoint"],
)
REQUEST_LATENCY = Histogram(
    "http_request_latency_seconds",
    "HTTP request latency in seconds",
    ["method", "endpoint"],
)
ORDER_COUNT = Counter("orders_created_total", "Total created orders")
ORDER_REJECTED = Counter("orders_rejected_total", "Total rejected orders")
ORDER_RATE_LIMITED = Counter("orders_rate_limited_total", "Total rate-limited requests")
ORDER_TIMEOUT = Counter("orders_timeout_total", "Total timeout-protected requests")
ORDER_DEGRADED = Counter("orders_degraded_total", "Total degraded responses")
ORDER_CIRCUIT_OPEN = Counter("orders_circuit_open_total", "Total circuit-open rejections")

TRAFFIC_RECORD_ENABLED = os.getenv("TRAFFIC_RECORD_ENABLED", "false").lower() == "true"
TRAFFIC_RECORD_FILE = Path(os.getenv("TRAFFIC_RECORD_FILE", "reports/traffic_record_latest.jsonl"))
TRAFFIC_RECORD_MAX_QUEUE = int(os.getenv("TRAFFIC_RECORD_MAX_QUEUE", "2000"))
_record_queue = queue.Queue(maxsize=TRAFFIC_RECORD_MAX_QUEUE)#创建一个队列，用于存储流量记录

def _mask_value(key_name, value):
    key = str(key_name or "").lower()
    # 1. 敏感信息掩码函数
    if any(k in key for k in ["phone", "mobile"]):
        return "***-****-****"
    if "name" in key:
        return "***"
    # 2. 针对字符串内容，用“正则表达式”大面积搜捕、大面积替换
    if isinstance(value, str):
        v = value
        v = re.sub(r"\b1[3-9]\d{9}\b", "1**********", v)
        v = re.sub(r"([\u4e00-\u9fff]{1})[\u4e00-\u9fff]{1,3}", r"\1**", v)
        return v
    # 3. 针对复杂数据结构list，dict，递归处理
    if isinstance(value, dict):
        return {k: _mask_value(k, x) for k, x in value.items()}
    if isinstance(value, list):
        return [_mask_value("", x) for x in value]
    return value


def _sanitize_headers(headers):
    out = {}
    allow = {"content-type", "x-idempotency-key", "user-agent", "x-forwarded-for"}
    for k, v in headers.items():
        lk = k.lower()
        if lk in allow:
            out[k] = _mask_value(k, v)
    return out

# 流量记录器
def _traffic_writer():
    while True:
        # 1. 从队列中获取流量记录
        item = _record_queue.get()
        try:
            # 2. 创建流量记录文件
            TRAFFIC_RECORD_FILE.parent.mkdir(parents=True, exist_ok=True)
            # 3. 写入流量记录
            with TRAFFIC_RECORD_FILE.open("a", encoding="utf-8") as f:
                f.write(json.dumps(item, ensure_ascii=False) + "\n")
        finally:
            _record_queue.task_done()

# 记录成功请求的流量
def _record_success_traffic(response_status):
    if not TRAFFIC_RECORD_ENABLED:
        return
    path = request.path
    # 1. 排除健康检查和指标收集路径
    if path in ("/healthz", "/metrics") or path.startswith("/static/"):
        return
    # 2. 排除错误响应
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
        "query": _mask_value("query", request.query_string.decode("utf-8", errors="ignore")),
        "headers": _sanitize_headers(request.headers),
        "body": _mask_value("body", body),
        "status": response_status,
    }
    try:
        _record_queue.put_nowait(event)
    except queue.Full:
        pass

# 启动流量记录器线程
if TRAFFIC_RECORD_ENABLED:
    _writer_thread = threading.Thread(target=_traffic_writer, daemon=True)
    _writer_thread.start()


@app.before_request
def before_request():
    request._start_time = time.time()


@app.after_request
def after_request(response):
    endpoint = request.path
    method = request.method
    # 1. 计算耗时
    duration = time.time() - getattr(request, "_start_time", time.time())
    # 2. 记录请求数
    REQUEST_COUNT.labels(method=method, endpoint=endpoint, status=response.status_code).inc()
    # 3. 记录请求时延
    REQUEST_LATENCY.labels(method=method, endpoint=endpoint).observe(duration)
    # 4. 记录错误数
    if response.status_code >= 500:
        REQUEST_ERRORS.labels(method=method, endpoint=endpoint).inc()
    # 5. 记录成功请求的流量
    _record_success_traffic(response.status_code)

    return response
#创建订单函数
@app.route("/order", methods=["POST"])
def create_order():
    client_ip = request.headers.get("X-Forwarded-For", request.remote_addr or "unknown")
    #1. 检查是否限流，若超过限流则返回429状态码，表示请求被限流，并记录限流指标
    if ENABLE_RESILIENCE and not allow_request_by_rate_limit(client_ip):
        ORDER_RATE_LIMITED.inc()
        return jsonify({"error": "rate limit exceeded"}), 429#返回429状态码，表示请求被限流
    #2. 检查是否熔断，若熔断则返回202状态码，表示请求被熔断，并记录熔断指标
    if ENABLE_RESILIENCE and is_circuit_open():
        ORDER_CIRCUIT_OPEN.inc()
        ORDER_DEGRADED.inc()#记录熔断状态
        return jsonify({"status": "queued", "reason": "circuit open"}), 202#返回202状态码，表示请求被熔断
    #3. 获取请求体，若请求体不合法则返回400状态码，表示请求体不合法，并记录不合法请求指标
    payload = request.get_json(silent=True) or {}
    item_id = payload.get("item_id")
    try:
        quantity = int(payload.get("quantity", 1))
    except (TypeError, ValueError):
        quantity = -1
    if not item_id or quantity <= 0:
        ORDER_REJECTED.inc()
        return jsonify({"error": "invalid request"}), 400

    idem_key = request.headers.get("X-Idempotency-Key")
    if idem_key:
        try:
            cached = redis_client.get(f"idem:{idem_key}")
            if cached:
                return jsonify({"status": "ok", "order_id": cached, "idempotent": True}), 200
        except redis.RedisError:
            pass
    #4. 检查是否超时，若超时则返回202状态码，模拟超时预判（预感太慢就不做了）
    processing_time = random.uniform(0.01, 0.05)
    if ENABLE_RESILIENCE and processing_time * 1000 > BUSINESS_TIMEOUT_MS:
        ORDER_TIMEOUT.inc()
        ORDER_DEGRADED.inc()
        return jsonify({"status": "queued", "reason": "timeout protected"}), 202
    #5. 获取数据库锁，若获取失败则返回503状态码，表示数据库繁忙，并记录数据库繁忙指标
    with db_lock:
        time.sleep(processing_time)
        if random.random() < 0.03:
            ORDER_REJECTED.inc()
            if ENABLE_RESILIENCE:
                record_failure_and_maybe_open()
            return jsonify({"error": "inventory busy"}), 503

        order_id = str(uuid.uuid4())
        orders[order_id] = {"item_id": item_id, "quantity": quantity, "status": "created"}
        if ENABLE_RESILIENCE:
            record_success()

    if idem_key:
        try:
            redis_client.setex(f"idem:{idem_key}", 300, order_id)
        except redis.RedisError:
            pass

    ORDER_COUNT.inc()
    return jsonify({"status": "ok", "order_id": order_id}), 201

#数据核对函数
@app.route("/order/<order_id>", methods=["GET"])
def get_order(order_id):
    order = orders.get(order_id)
    if not order:
        return jsonify({"error": "order not found"}), 404
    return jsonify({"order_id": order_id, **order})

#取消订单函数，没有加 db_lock，因为不需要加锁，因为取消订单不会影响其他订单
@app.route("/order/<order_id>/cancel", methods=["POST"])
def cancel_order(order_id):
    order = orders.get(order_id)
    if not order:
        return jsonify({"error": "order not found"}), 404
    if order.get("status") == "cancelled":
        return jsonify({"status": "ok", "order_id": order_id, "already_cancelled": True}), 200
    order["status"] = "cancelled"
    return jsonify({"status": "ok", "order_id": order_id, "cancelled": True}), 200

#自愈与保命层
@app.route("/healthz")
def healthz():
    try:
        redis_client.ping()
        redis_ok = True
    except redis.RedisError:
        redis_ok = False
    return {
        "status": "healthy" if redis_ok else "degraded",
        "redis": redis_ok,
        "resilience": ENABLE_RESILIENCE,
    }

#指标收集函数 代码里分散各处的 .inc()（比如 ORDER_COUNT.inc()）收集起来，方便后续的监控和告警
@app.route("/metrics")
def metrics():
    return Response(generate_latest(), mimetype=CONTENT_TYPE_LATEST)

#限流函数（采用固定窗口计数器算法，可能会出现秒边界情况，但是后续采用多重防御，但是可能出现雪崩）
def allow_request_by_rate_limit(client_ip):
    #1. 创建一个唯一的key，用于存储当前客户端的请求计数
    key = f"rl:{client_ip}:{int(time.time())}"
    try:
        #2. 使用redis的incr命令，将key的值加1   
        value = redis_client.incr(key)
        #3. 如果key的值为1，则设置key的过期时间为2秒
        if value == 1:
            redis_client.expire(key, 2)
        #4. 如果key的值大于RATE_LIMIT_PER_SEC，则返回False
        return value <= RATE_LIMIT_PER_SEC
    #5. 如果redis操作失败，则返回True
    except redis.RedisError:
        return True

#是否熔断函数
def is_circuit_open():
    #1. 使用锁，确保只有一个线程可以访问熔断器
    with breaker_lock:
        #2. 如果当前时间还没到‘解封时间’，则返回 True（即熔断中）
        return time.time() < breaker_open_until

#记录失败并可能打开熔断函数
def record_failure_and_maybe_open():
    global breaker_open_until
    now = time.time()
    with breaker_lock:
        #将当前时间添加到熔断失败记录中
        breaker_failures.append(now)
        #计算熔断失败记录的截止时间，滑动窗口：只看最近一段时间发生的错误
        cutoff = now - BREAKER_WINDOW_SEC
        #清除过期失败记录，只保留最近一段时间发生的错误
        while breaker_failures and breaker_failures[0] < cutoff:
            breaker_failures.pop(0)
        #如果熔断失败记录的数量大于熔断失败阈值，则打开熔断器
        if len(breaker_failures) >= BREAKER_FAIL_THRESHOLD:
            #设置熔断器打开时间，熔断窗口时间：只看最近一段时间发生的错误
            breaker_open_until = now + BREAKER_OPEN_SEC

#成功一次就清除熔断失败记录，可能过于乐观，会导致频繁开关熔断器，产生震荡
def record_success():
    with breaker_lock:
        breaker_failures.clear()

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000)