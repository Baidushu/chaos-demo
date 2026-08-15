from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class BusinessException(Exception):
    message: str
    status_code: int = 400
    error_code: str = "business_error"
    payload: dict = field(default_factory=dict)

    def to_response(self) -> dict:
        body = {"error": self.message, "code": self.error_code}
        body.update(self.payload)
        return body


class ValidationException(BusinessException):
    def __init__(self, message: str, *, payload: dict | None = None) -> None:
        super().__init__(
            message=message,
            status_code=400,
            error_code="validation_error",
            payload=payload or {},
        )


class StorageException(BusinessException):
    def __init__(self, message: str, *, payload: dict | None = None) -> None:
        super().__init__(
            message=message,
            status_code=503,
            error_code="storage_error",
            payload=payload or {},
        )


class TimeoutException(BusinessException):
    def __init__(
        self,
        message: str,
        *,
        status_code: int = 202,
        payload: dict | None = None,
    ) -> None:
        super().__init__(
            message=message,
            status_code=status_code,
            error_code="timeout",
            payload=payload or {},
        )


class ChaosException(BusinessException):
    def __init__(
        self,
        message: str,
        *,
        status_code: int = 503,
        payload: dict | None = None,
    ) -> None:
        super().__init__(
            message=message,
            status_code=status_code,
            error_code="chaos_error",
            payload=payload or {},
        )
