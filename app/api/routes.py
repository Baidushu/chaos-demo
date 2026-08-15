"""FastAPI routes for the AI Platform service.

POST /api/v1/agent/run      — execute an agent run
GET  /api/v1/health          — health check
"""

from __future__ import annotations

from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse

from app.api.schemas import AgentRunRequest, AgentRunResponse, ErrorResponse, HealthResponse
from ai_platform.core import (
    AIPlatformService,
    PlatformConfig,
    PlatformError,
    SecurityBlockedError,
    create_platform_service,
)

router = APIRouter(prefix="/api/v1", tags=["agent"])

# ── Global service singleton (lazy init) ──────────────────────────────

_service: AIPlatformService | None = None


def get_service() -> AIPlatformService:
    """Get or create the platform service singleton."""
    global _service
    if _service is None:
        _service = create_platform_service()
    return _service


# ── Exception handlers ────────────────────────────────────────────────


def _build_error(status_code: int, error_type: str, message: str, violations: list[str] | None = None) -> JSONResponse:
    return JSONResponse(
        status_code=status_code,
        content=ErrorResponse(
            error=message,
            error_type=error_type,
            violations=violations or [],
        ).model_dump(),
    )


# ── Routes ────────────────────────────────────────────────────────────


@router.get("/health", response_model=HealthResponse)
async def health() -> HealthResponse:
    """Health check endpoint."""
    return HealthResponse()


@router.post("/agent/run", response_model=AgentRunResponse)
async def agent_run(body: AgentRunRequest) -> AgentRunResponse | JSONResponse:
    """Execute an agent run through the full platform pipeline.

    Flow:
      create trace → security check → runtime execute → evaluation → quality gate → result
    """
    svc = get_service()

    try:
        result = svc.run(
            body.request,
            mode=body.mode,
        )
    except SecurityBlockedError as exc:
        return _build_error(403, "SecurityBlocked", str(exc), exc.violations)
    except PlatformError as exc:
        return _build_error(500, type(exc).__name__, str(exc))
    except Exception as exc:
        return _build_error(500, "InternalError", str(exc))

    if result.success:
        return AgentRunResponse(
            success=True,
            answer=result.answer,
            score=result.score,
            security_score=result.security_score,
            trace_id=result.trace_id,
            evaluation=result.evaluation,
            gate=result.gate,
            metadata=result.metadata,
        )

    # Map platform error types to HTTP status codes
    error_type = result.error_type or "UnknownError"
    status_code = {
        "SecurityBlocked": 403,
        "AgentError": 500,
        "EvaluationFailed": 422,
        "InternalError": 500,
    }.get(error_type, 500)

    return _build_error(status_code, error_type, result.error or "Unknown error", result.violations)
