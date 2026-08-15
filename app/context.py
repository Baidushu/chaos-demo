from __future__ import annotations

import queue
import random
import threading
import time
from dataclasses import dataclass, field
from typing import Any

from flask import Flask

from app.config import AppConfig
from app.infrastructure.metrics import AppMetrics


@dataclass
class RequestContext:
    request_id: str
    trace_id: str
    user_id: str | None
    started_at: float
    request: Any
    deadline: float | None = None
    experiment_id: str | None = None


@dataclass
class AppRuntime:
    app: Flask
    config: AppConfig
    redis_client: Any
    metrics: AppMetrics
    logger: Any
    random: Any = random
    db_lock: threading.Lock = field(default_factory=threading.Lock)
    request_context_cls: type[RequestContext] = RequestContext
    order_repository: Any = None
    idempotency_repository: Any = None
    order_service: Any = None
    chaos_control_service: Any = None
    _record_queue: queue.Queue = field(init=False)
    _writer_thread: threading.Thread | None = None

    def __post_init__(self) -> None:
        self._record_queue = queue.Queue(maxsize=self.config.traffic.max_queue)
        self._sync_legacy_attributes()

    def _sync_legacy_attributes(self) -> None:
        self.SERVICE_NAME = self.config.rate_limit.service_name
        self.APP_ENV = self.config.app_env
        self.RATE_LIMIT_RESOURCE = self.config.rate_limit.resource
        self.RATE_LIMIT_DIMENSION = self.config.rate_limit.dimension
        self.RATE_LIMIT_ALGORITHM = self.config.rate_limit.algorithm
        self.RATE_LIMIT_PER_SEC = self.config.rate_limit.limit
        self.RATE_LIMIT_WINDOW_SEC = self.config.rate_limit.window_sec
        self.RATE_LIMIT_LUA_DIR = self.config.rate_limit.lua_dir

        self.BUSINESS_TIMEOUT_MS = self.config.business.timeout_ms
        self.ENABLE_RESILIENCE = self.config.business.resilience_enabled
        self.INVENTORY_BUSY_PROB = self.config.business.inventory_busy_prob

        self.BREAKER_RESOURCE = self.config.breaker.resource
        self.BREAKER_FAIL_THRESHOLD = self.config.breaker.fail_threshold
        self.BREAKER_WINDOW_SEC = self.config.breaker.window_sec
        self.BREAKER_OPEN_SEC = self.config.breaker.open_sec
        self.BREAKER_FAILURE_RATE_THRESHOLD = self.config.breaker.failure_rate_threshold
        self.MIN_REQUEST_AMOUNT = self.config.breaker.min_request_amount
        self.CIRCUIT_PROBE_TTL_SEC = self.config.breaker.probe_ttl_sec
        self.CB_KEY_OPEN_UNTIL = self.config.breaker.key_open_until
        self.CB_KEY_FAILURES = self.config.breaker.key_failures
        self.CB_KEY_TOTAL_REQUESTS = self.config.breaker.key_total_requests
        self.CB_KEY_PROBE = self.config.breaker.key_probe

        self.ORDER_TTL_SEC = self.config.idempotency.order_ttl_sec
        self.ORDER_KEY_PREFIX = self.config.idempotency.order_key_prefix
        self.IDEM_TTL_SEC = self.config.idempotency.ttl_sec
        self.IDEM_PENDING_TTL_SEC = self.config.idempotency.pending_ttl_sec
        self.IDEM_WAIT_TIMEOUT_MS = self.config.idempotency.wait_timeout_ms
        self.IDEM_WAIT_POLL_MS = self.config.idempotency.wait_poll_ms

        self.RETRY_MAX_ATTEMPTS = self.config.retry.max_attempts
        self.RETRY_BASE_DELAY_MS = self.config.retry.base_delay_ms
        self.RETRY_MAX_DELAY_MS = self.config.retry.max_delay_ms

        self.CHAOS_ENABLED = self.config.chaos.enabled
        self.FAULT_INJECTION_ENABLED = self.config.chaos.fault_injection_enabled
        self.FAULT_DEFAULT_TTL_SEC = self.config.chaos.default_ttl_sec
        self.FAULT_MAX_LATENCY_MS = self.config.chaos.max_latency_ms
        self.FAULT_MAX_DROP_RATE = self.config.chaos.max_drop_rate

        self.TRAFFIC_RECORD_ENABLED = self.config.traffic.enabled
        self.TRAFFIC_RECORD_FILE = self.config.traffic.record_file
        self.TRAFFIC_RECORD_MAX_QUEUE = self.config.traffic.max_queue

        self.REQUEST_COUNT = self.metrics.request_count
        self.REQUEST_ERRORS = self.metrics.request_errors
        self.REQUEST_LATENCY = self.metrics.request_latency
        self.REQUESTS_IN_PROGRESS = self.metrics.requests_in_progress
        self.ORDER_COUNT = self.metrics.order_count
        self.ORDER_REJECTED = self.metrics.order_rejected
        self.ORDER_RATE_LIMITED = self.metrics.order_rate_limited
        self.RATE_LIMIT_ALLOWED_TOTAL = self.metrics.rate_limit_allowed_total
        self.RATE_LIMIT_REJECTED_TOTAL = self.metrics.rate_limit_rejected_total
        self.RATE_LIMIT_REDIS_ERROR_TOTAL = self.metrics.rate_limit_redis_error_total
        self.ORDER_TIMEOUT = self.metrics.order_timeout
        self.ORDER_DEGRADED = self.metrics.order_degraded
        self.ORDER_CIRCUIT_OPEN = self.metrics.order_circuit_open
        self.CIRCUIT_BREAKER_REQUESTS_TOTAL = self.metrics.circuit_breaker_requests_total
        self.CIRCUIT_BREAKER_FAILURES_TOTAL = self.metrics.circuit_breaker_failures_total
        self.CIRCUIT_BREAKER_TIMEOUT_TOTAL = self.metrics.circuit_breaker_timeout_total
        self.CIRCUIT_BREAKER_REJECTED_TOTAL = self.metrics.circuit_breaker_rejected_total
        self.CIRCUIT_BREAKER_STATE_CHANGE_TOTAL = self.metrics.circuit_breaker_state_change_total
        self.CIRCUIT_BREAKER_OPEN_TOTAL = self.metrics.circuit_breaker_open_total
        self.CIRCUIT_BREAKER_FALLBACK_TOTAL = self.metrics.circuit_breaker_fallback_total
        self.CIRCUIT_BREAKER_STATE = self.metrics.circuit_breaker_state
        self.CIRCUIT_BREAKER_RECOVERY_SECONDS = self.metrics.circuit_breaker_recovery_seconds
        self.ORDER_IDEMPOTENT_HIT = self.metrics.order_idempotent_hit
        self.ORDER_IDEMPOTENT_PROCESSING = self.metrics.order_idempotent_processing
        self.ORDER_IDEMPOTENT_CONFLICT = self.metrics.order_idempotent_conflict
        self.IDEMPOTENCY_REQUEST_TOTAL = self.metrics.idempotency_request_total
        self.IDEMPOTENCY_REPLAY_TOTAL = self.metrics.idempotency_replay_total
        self.IDEMPOTENCY_CONFLICT_TOTAL = self.metrics.idempotency_conflict_total
        self.IDEMPOTENCY_PROCESSING_TOTAL = self.metrics.idempotency_processing_total
        self.IDEMPOTENCY_FAILED_TOTAL = self.metrics.idempotency_failed_total
        self.IDEMPOTENCY_LOCK_FAILURE_TOTAL = self.metrics.idempotency_lock_failure_total
        self.RETRY_ATTEMPT_TOTAL = self.metrics.retry_attempt_total
        self.RETRY_SUCCESS_TOTAL = self.metrics.retry_success_total
        self.RETRY_FAILURE_TOTAL = self.metrics.retry_failure_total
        self.RETRY_DURATION_SECONDS = self.metrics.retry_duration_seconds
        self.CHAOS_EXPERIMENT_TOTAL = self.metrics.chaos_experiment_total
        self.CHAOS_EXPERIMENT_SUCCESS_TOTAL = self.metrics.chaos_experiment_success_total
        self.CHAOS_EXPERIMENT_FAILED_TOTAL = self.metrics.chaos_experiment_failed_total
        self.CHAOS_ACTIVE_EXPERIMENT = self.metrics.chaos_active_experiment
        self.CHAOS_RECOVERY_DURATION_SECONDS = self.metrics.chaos_recovery_duration_seconds
        self.CHAOS_FAULT_INJECTED_TOTAL = self.metrics.chaos_fault_injected_total
        self.CHAOS_FAULT_RECOVERED_TOTAL = self.metrics.chaos_fault_recovered_total
        self.CHAOS_EXPERIMENT_DURATION_SECONDS = self.metrics.chaos_experiment_duration_seconds

    def build_request_context(
        self,
        request_obj,
        *,
        request_id: str,
        trace_id: str,
        user_id: str | None,
    ) -> RequestContext:
        deadline = float(getattr(request_obj, "_start_time", time.time())) + (
            self.BUSINESS_TIMEOUT_MS / 1000.0
        )
        return self.request_context_cls(
            request_id=request_id,
            trace_id=trace_id,
            user_id=user_id,
            started_at=float(getattr(request_obj, "_start_time", time.time())),
            request=request_obj,
            deadline=deadline,
        )

    def update_setting(self, name: str, value: Any) -> None:
        setattr(self, name, value)
        if name == "redis_client":
            self.redis_client = value

    @property
    def request_context(self) -> type[RequestContext]:
        return self.request_context_cls
