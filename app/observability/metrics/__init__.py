from __future__ import annotations

from dataclasses import dataclass

from prometheus_client import CollectorRegistry, Counter, Gauge, Histogram

from app.observability.registry import get_metrics_registry


@dataclass(frozen=True)
class AppMetrics:
    registry: CollectorRegistry
    request_count: Counter
    request_errors: Counter
    request_latency: Histogram
    requests_in_progress: Gauge
    order_count: Counter
    order_rejected: Counter
    order_rate_limited: Counter
    rate_limit_allowed_total: Counter
    rate_limit_rejected_total: Counter
    rate_limit_redis_error_total: Counter
    order_timeout: Counter
    order_degraded: Counter
    order_circuit_open: Counter
    circuit_breaker_requests_total: Counter
    circuit_breaker_failures_total: Counter
    circuit_breaker_timeout_total: Counter
    circuit_breaker_rejected_total: Counter
    circuit_breaker_state_change_total: Counter
    circuit_breaker_open_total: Counter
    circuit_breaker_fallback_total: Counter
    circuit_breaker_state: Gauge
    circuit_breaker_recovery_seconds: Histogram
    order_idempotent_hit: Counter
    order_idempotent_processing: Counter
    order_idempotent_conflict: Counter
    idempotency_request_total: Counter
    idempotency_replay_total: Counter
    idempotency_conflict_total: Counter
    idempotency_processing_total: Counter
    idempotency_failed_total: Counter
    idempotency_lock_failure_total: Counter
    retry_attempt_total: Counter
    retry_success_total: Counter
    retry_failure_total: Counter
    retry_duration_seconds: Histogram
    chaos_experiment_total: Counter
    chaos_experiment_success_total: Counter
    chaos_experiment_failed_total: Counter
    chaos_active_experiment: Gauge
    chaos_recovery_duration_seconds: Histogram
    chaos_fault_injected_total: Counter
    chaos_fault_recovered_total: Counter
    chaos_experiment_duration_seconds: Histogram


_METRICS: AppMetrics | None = None


def register_metrics(registry: CollectorRegistry | None = None) -> AppMetrics:
    global _METRICS
    if _METRICS is not None:
        return _METRICS

    collector_registry = registry or get_metrics_registry()
    _METRICS = AppMetrics(
        registry=collector_registry,
        request_count=Counter(
            "http_requests_total",
            "Total HTTP requests",
            ["method", "route", "status"],
            registry=collector_registry,
        ),
        request_errors=Counter(
            "http_request_errors_total",
            "Total HTTP 5xx responses",
            ["method", "route"],
            registry=collector_registry,
        ),
        request_latency=Histogram(
            "http_request_duration_seconds",
            "HTTP request duration in seconds",
            ["method", "route"],
            registry=collector_registry,
        ),
        requests_in_progress=Gauge(
            "http_requests_in_progress",
            "Current in-progress HTTP requests",
            ["method", "route"],
            registry=collector_registry,
        ),
        order_count=Counter(
            "orders_created_total",
            "Total created orders",
            registry=collector_registry,
        ),
        order_rejected=Counter(
            "orders_rejected_total",
            "Total rejected orders",
            registry=collector_registry,
        ),
        order_rate_limited=Counter(
            "orders_rate_limited_total",
            "Total rate-limited requests",
            registry=collector_registry,
        ),
        rate_limit_allowed_total=Counter(
            "rate_limit_allowed_total",
            "Total allowed rate-limit decisions",
            ["algorithm", "resource", "dimension"],
            registry=collector_registry,
        ),
        rate_limit_rejected_total=Counter(
            "rate_limit_rejected_total",
            "Total rejected rate-limit decisions",
            ["algorithm", "resource", "dimension"],
            registry=collector_registry,
        ),
        rate_limit_redis_error_total=Counter(
            "rate_limit_redis_error_total",
            "Total Redis errors during rate limiting",
            ["algorithm", "resource", "dimension"],
            registry=collector_registry,
        ),
        order_timeout=Counter(
            "orders_timeout_total",
            "Total timeout-protected requests",
            registry=collector_registry,
        ),
        order_degraded=Counter(
            "orders_degraded_total",
            "Total degraded responses",
            registry=collector_registry,
        ),
        order_circuit_open=Counter(
            "orders_circuit_open_total",
            "Total circuit-open rejections",
            registry=collector_registry,
        ),
        circuit_breaker_requests_total=Counter(
            "circuit_breaker_calls_total",
            "Total circuit breaker call decisions",
            ["resource", "state"],
            registry=collector_registry,
        ),
        circuit_breaker_failures_total=Counter(
            "circuit_breaker_failures_total",
            "Total circuit breaker failures",
            ["resource", "state"],
            registry=collector_registry,
        ),
        circuit_breaker_timeout_total=Counter(
            "circuit_breaker_timeout_total",
            "Total circuit breaker timeout events",
            ["resource"],
            registry=collector_registry,
        ),
        circuit_breaker_rejected_total=Counter(
            "circuit_breaker_rejected_total",
            "Total requests rejected by circuit breaker",
            ["resource", "state"],
            registry=collector_registry,
        ),
        circuit_breaker_state_change_total=Counter(
            "circuit_breaker_state_change_total",
            "Total circuit breaker state changes",
            ["resource", "state"],
            registry=collector_registry,
        ),
        circuit_breaker_open_total=Counter(
            "circuit_breaker_open_total",
            "Total times the circuit breaker entered open state",
            ["resource", "state"],
            registry=collector_registry,
        ),
        circuit_breaker_fallback_total=Counter(
            "circuit_breaker_fallback_total",
            "Total circuit breaker fallback executions",
            ["resource", "state"],
            registry=collector_registry,
        ),
        circuit_breaker_state=Gauge(
            "circuit_breaker_state",
            "Current circuit breaker state: closed=0 open=1 half_open=2",
            ["resource"],
            registry=collector_registry,
        ),
        circuit_breaker_recovery_seconds=Histogram(
            "circuit_breaker_recovery_seconds",
            "Time spent recovering from open to closed state",
            ["resource"],
            registry=collector_registry,
        ),
        order_idempotent_hit=Counter(
            "orders_idempotent_hit_total",
            "Total idempotent replay hits",
            registry=collector_registry,
        ),
        order_idempotent_processing=Counter(
            "orders_idempotent_processing_total",
            "Total duplicate requests still waiting on owner request",
            registry=collector_registry,
        ),
        order_idempotent_conflict=Counter(
            "orders_idempotent_conflict_total",
            "Total idempotency-key payload conflicts",
            registry=collector_registry,
        ),
        idempotency_request_total=Counter(
            "idempotency_requests_total",
            "Total requests carrying X-Idempotency-Key",
            registry=collector_registry,
        ),
        idempotency_replay_total=Counter(
            "idempotency_replay_total",
            "Total idempotency replay responses",
            registry=collector_registry,
        ),
        idempotency_conflict_total=Counter(
            "idempotency_conflict_total",
            "Total idempotency key conflicts",
            registry=collector_registry,
        ),
        idempotency_processing_total=Counter(
            "idempotency_processing_total",
            "Total duplicate requests still in processing state",
            registry=collector_registry,
        ),
        idempotency_failed_total=Counter(
            "idempotency_failed_total",
            "Total idempotency records finalized as failed",
            registry=collector_registry,
        ),
        idempotency_lock_failure_total=Counter(
            "idempotency_lock_failure_total",
            "Total idempotency compare-and-delete lock release failures",
            registry=collector_registry,
        ),
        retry_attempt_total=Counter(
            "retry_attempt_total",
            "Total retry policy attempts",
            ["operation"],
            registry=collector_registry,
        ),
        retry_success_total=Counter(
            "retry_success_total",
            "Total successful retry policy executions",
            ["operation"],
            registry=collector_registry,
        ),
        retry_failure_total=Counter(
            "retry_failure_total",
            "Total failed retry policy executions",
            ["operation", "exception_type"],
            registry=collector_registry,
        ),
        retry_duration_seconds=Histogram(
            "retry_duration_seconds",
            "Total retry execution duration in seconds",
            ["operation", "result"],
            registry=collector_registry,
        ),
        chaos_experiment_total=Counter(
            "chaos_experiment_total",
            "Total chaos experiments created",
            ["fault_type", "target"],
            registry=collector_registry,
        ),
        chaos_experiment_success_total=Counter(
            "chaos_experiment_success_total",
            "Total successful chaos experiments",
            ["fault_type", "target"],
            registry=collector_registry,
        ),
        chaos_experiment_failed_total=Counter(
            "chaos_experiment_failed_total",
            "Total failed chaos experiments",
            ["fault_type", "target"],
            registry=collector_registry,
        ),
        chaos_active_experiment=Gauge(
            "chaos_active_experiment",
            "Current active chaos experiments",
            ["fault_type", "target"],
            registry=collector_registry,
        ),
        chaos_recovery_duration_seconds=Histogram(
            "chaos_recovery_duration_seconds",
            "Chaos experiment recovery duration in seconds",
            ["fault_type", "target"],
            registry=collector_registry,
        ),
        chaos_fault_injected_total=Counter(
            "chaos_fault_injected_total",
            "Total injected chaos faults",
            ["fault_type", "target", "phase"],
            registry=collector_registry,
        ),
        chaos_fault_recovered_total=Counter(
            "chaos_fault_recovered_total",
            "Total recovered chaos experiments",
            ["fault_type", "target"],
            registry=collector_registry,
        ),
        chaos_experiment_duration_seconds=Histogram(
            "chaos_experiment_duration_seconds",
            "Configured chaos experiment duration",
            ["fault_type", "target"],
            registry=collector_registry,
        ),
    )
    return _METRICS


__all__ = ["AppMetrics", "register_metrics"]
