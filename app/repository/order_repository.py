from __future__ import annotations

from app.exceptions import StorageException
from chaos_service import store


class OrderRepository:
    def __init__(self, runtime) -> None:
        self._runtime = runtime

    def get(self, order_id: str):
        try:
            return store.get_order_from_store(self._runtime, order_id)
        except Exception as exc:
            raise StorageException("order store unavailable") from exc

    def save(self, order_id: str, doc: dict) -> None:
        try:
            store.put_order_in_store(self._runtime, order_id, doc)
        except Exception as exc:
            raise StorageException("order store unavailable") from exc
