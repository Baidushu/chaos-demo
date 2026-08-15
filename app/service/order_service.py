from __future__ import annotations

import time
import uuid
from dataclasses import dataclass

from app.exceptions import StorageException, ValidationException
from app.infrastructure.logging import log_event
from chaos_service import fault_injection, resilience


@dataclass(frozen=True)
class ServiceResult:
    status_code: int
    body: dict


@dataclass(frozen=True)
class CreateOrderCommand:
    item_id: str | None
    quantity: int
    idempotency_key: str | None


class OrderService:
    def __init__(self, runtime, order_repository, idempotency_repository) -> None:
        self._runtime = runtime
        self._order_repository = order_repository
        self._idempotency_repository = idempotency_repository

    def create_order(self, command: CreateOrderCommand, request_context) -> ServiceResult:
        breaker = None
        if self._runtime.ENABLE_RESILIENCE:
            breaker = resilience.build_circuit_breaker(self._runtime)
        request_obj = request_context.request

        if breaker is not None and not breaker.allow_request():
            self._runtime.ORDER_CIRCUIT_OPEN.inc()
            self._runtime.ORDER_DEGRADED.inc()
            fault_injection.record_fallback(self._runtime, request_obj)
            log_event(
                self._runtime.app.logger,
                "breaker_open",
                component="order_service",
                operation="create_order",
                result="queued",
                path="/order",
            )
            return ServiceResult(202, {"status": "queued", "reason": "circuit open"})

        if not command.item_id or command.quantity <= 0:
            self._runtime.ORDER_REJECTED.inc()
            raise ValidationException("invalid request")

        payload_fp = self._idempotency_repository.fingerprint(command.item_id, command.quantity)
        idem_reserved = False
        idem_record = None
        if command.idempotency_key:
            self._runtime.IDEMPOTENCY_REQUEST_TOTAL.inc()
            try:
                state, record = self._idempotency_repository.reserve(
                    command.idempotency_key,
                    payload_fp,
                )
                if state == "replay":
                    self._runtime.ORDER_IDEMPOTENT_HIT.inc()
                    self._runtime.IDEMPOTENCY_REPLAY_TOTAL.inc()
                    status, body = self._idempotency_repository.build_replay_response(record)
                    return ServiceResult(status, body)
                if state == "conflict":
                    self._runtime.ORDER_IDEMPOTENT_CONFLICT.inc()
                    self._runtime.IDEMPOTENCY_CONFLICT_TOTAL.inc()
                    return ServiceResult(
                        409,
                        {"error": "idempotency key reused with different payload"},
                    )
                if state == "processing":
                    waited_state, waited_record = self._idempotency_repository.wait_for_result(
                        command.idempotency_key,
                        payload_fp,
                    )
                    if waited_state == "replay":
                        self._runtime.ORDER_IDEMPOTENT_HIT.inc()
                        self._runtime.IDEMPOTENCY_REPLAY_TOTAL.inc()
                        status, body = self._idempotency_repository.build_replay_response(
                            waited_record
                        )
                        return ServiceResult(status, body)
                    if waited_state == "conflict":
                        self._runtime.ORDER_IDEMPOTENT_CONFLICT.inc()
                        self._runtime.IDEMPOTENCY_CONFLICT_TOTAL.inc()
                        return ServiceResult(
                            409,
                            {"error": "idempotency key reused with different payload"},
                        )
                    self._runtime.ORDER_IDEMPOTENT_PROCESSING.inc()
                    self._runtime.IDEMPOTENCY_PROCESSING_TOTAL.inc()
                    return ServiceResult(202, {"status": "processing", "idempotent": True})
                idem_reserved = True
                idem_record = record
            except StorageException:
                pass

        t0 = request_context.started_at
        processing_time = self._runtime.random.uniform(0.01, 0.05)
        elapsed = time.time() - t0
        if self._runtime.ENABLE_RESILIENCE and resilience.order_deadline_exceeded(
            elapsed,
            processing_time,
            self._runtime.BUSINESS_TIMEOUT_MS,
        ):
            if breaker is not None:
                breaker.record_timeout()
            self._runtime.ORDER_TIMEOUT.inc()
            self._runtime.ORDER_DEGRADED.inc()
            log_event(
                self._runtime.app.logger,
                "order_timeout_protected",
                component="order_service",
                operation="create_order",
                result="queued",
                elapsed_ms=round(elapsed * 1000, 3),
                planned_work_ms=round(processing_time * 1000, 3),
                budget_ms=self._runtime.BUSINESS_TIMEOUT_MS,
            )
            if command.idempotency_key and idem_reserved and idem_record:
                try:
                    self._idempotency_repository.release_reservation(
                        command.idempotency_key,
                        idem_record,
                    )
                except StorageException:
                    pass
            return ServiceResult(202, {"status": "queued", "reason": "timeout protected"})

        try:
            fault_injection.before_service_operation(self._runtime, request_obj, stage="service")
            with self._runtime.db_lock:
                time.sleep(processing_time)
                if self._runtime.random.random() < self._runtime.INVENTORY_BUSY_PROB:
                    self._runtime.ORDER_REJECTED.inc()
                    if breaker is not None:
                        breaker.record_failure()
                    log_event(
                        self._runtime.app.logger,
                        "inventory_busy",
                        component="order_service",
                        operation="create_order",
                        result="failed",
                        path="/order",
                        level="WARNING",
                    )
                    if command.idempotency_key and idem_reserved:
                        self._save_failed(
                            command.idempotency_key,
                            payload_fp,
                            "inventory busy",
                            503,
                            {"error": "inventory busy"},
                        )
                    return ServiceResult(503, {"error": "inventory busy"})

                order_id = str(uuid.uuid4())
                try:
                    self._order_repository.save(
                        order_id,
                        {
                            "item_id": command.item_id,
                            "quantity": command.quantity,
                            "status": "created",
                        },
                    )
                except StorageException:
                    if breaker is not None:
                        breaker.record_failure()
                    if command.idempotency_key and idem_reserved:
                        self._save_failed(
                            command.idempotency_key,
                            payload_fp,
                            "order store unavailable",
                            503,
                            {"error": "order store unavailable"},
                        )
                    return ServiceResult(503, {"error": "order store unavailable"})
                if breaker is not None:
                    breaker.record_success()
        except fault_injection.ChaosDropTriggered as exc:
            if breaker is not None:
                breaker.record_failure()
            if command.idempotency_key and idem_reserved:
                self._save_failed(
                    command.idempotency_key,
                    payload_fp,
                    exc.message,
                    503,
                    exc.to_response(),
                )
            return ServiceResult(exc.status_code, exc.to_response())
        except fault_injection.ChaosFaultTriggered as exc:
            if breaker is not None:
                breaker.record_failure()
            if command.idempotency_key and idem_reserved:
                self._save_failed(
                    command.idempotency_key,
                    payload_fp,
                    exc.message,
                    exc.status_code,
                    exc.to_response(),
                )
            return ServiceResult(exc.status_code, exc.to_response())

        if command.idempotency_key:
            try:
                self._idempotency_repository.finalize_success(
                    command.idempotency_key,
                    payload_fp,
                    order_id,
                    response_status=201,
                    response_body={"status": "ok", "order_id": order_id},
                )
            except StorageException:
                pass

        self._runtime.ORDER_COUNT.inc()
        log_event(
            self._runtime.app.logger,
            "order_created",
            component="order_service",
            operation="create_order",
            result="success",
            order_id=order_id,
        )
        return ServiceResult(201, {"status": "ok", "order_id": order_id})

    def get_order(self, order_id: str) -> ServiceResult:
        order = self._order_repository.get(order_id)
        if not order:
            return ServiceResult(404, {"error": "order not found"})
        safe_order = {
            "item_id": order.get("item_id"),
            "quantity": order.get("quantity"),
            "status": order.get("status"),
        }
        return ServiceResult(200, {"order_id": order_id, **safe_order})

    def cancel_order(self, order_id: str) -> ServiceResult:
        order = self._order_repository.get(order_id)
        if not order:
            return ServiceResult(404, {"error": "order not found"})
        if order.get("status") == "cancelled":
            return ServiceResult(
                200,
                {"status": "ok", "order_id": order_id, "already_cancelled": True},
            )
        order["status"] = "cancelled"
        self._order_repository.save(order_id, order)
        return ServiceResult(200, {"status": "ok", "order_id": order_id, "cancelled": True})

    def _save_failed(
        self,
        idem_key: str,
        payload_fp: str,
        error_message: str,
        response_status: int,
        response_body: dict,
    ) -> None:
        try:
            self._idempotency_repository.save_failed(
                idem_key,
                payload_fp,
                error_message,
                response_status,
                response_body,
            )
            self._runtime.IDEMPOTENCY_FAILED_TOTAL.inc()
        except StorageException:
            pass
