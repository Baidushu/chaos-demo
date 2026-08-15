from __future__ import annotations

from app.exceptions import StorageException
from chaos_service import store


class IdempotencyRepository:
    def __init__(self, runtime) -> None:
        self._runtime = runtime

    def fingerprint(self, item_id: str, quantity: int) -> str:
        return store.idem_payload_fingerprint(item_id, quantity)

    def reserve(self, idem_key: str, payload_fp: str) -> tuple[str, dict]:
        try:
            return store.reserve_idempotency_key(self._runtime, idem_key, payload_fp)
        except Exception as exc:
            raise StorageException("idempotency store unavailable") from exc

    def wait_for_result(self, idem_key: str, payload_fp: str) -> tuple[str, dict]:
        try:
            return store.wait_for_idempotency_result(self._runtime, idem_key, payload_fp)
        except Exception as exc:
            raise StorageException("idempotency store unavailable") from exc

    def build_replay_response(self, record: dict) -> tuple[int, dict]:
        return store.build_replay_response(record)

    def finalize_success(
        self,
        idem_key: str,
        payload_fp: str,
        order_id: str,
        *,
        response_status: int,
        response_body: dict,
    ) -> None:
        try:
            store.finalize_idempotency_success(
                self._runtime,
                idem_key,
                payload_fp,
                order_id,
                response_status=response_status,
                response_body=response_body,
            )
        except Exception as exc:
            raise StorageException("idempotency finalize unavailable") from exc

    def save_failed(
        self,
        idem_key: str,
        payload_fp: str,
        error_message: str,
        response_status: int,
        response_body: dict,
    ) -> None:
        try:
            store.save_failed(
                self._runtime,
                idem_key,
                payload_fp,
                error_message,
                response_status,
                response_body=response_body,
            )
        except Exception as exc:
            raise StorageException("idempotency store unavailable") from exc

    def release_reservation(self, idem_key: str, record: dict | None = None) -> bool:
        try:
            return store.release_idempotency_reservation(self._runtime, idem_key, record)
        except Exception as exc:
            raise StorageException("idempotency store unavailable") from exc
