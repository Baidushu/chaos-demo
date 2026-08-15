"""FastAPI application for the AI Platform service.

Standalone entry point that does NOT depend on the legacy Flask app module.
Usage:
    uvicorn ai_platform_api:app --host 0.0.0.0 --port 8000
"""

from __future__ import annotations

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field
from typing import Any

from ai_platform.core import (
    AIPlatformService,
    PlatformConfig,
    PlatformError,
    SecurityBlockedError,
    create_platform_service,
)

# ── Application ──────────────────────────────────────────────────────

app = FastAPI(
    title="AI Platform Service",
    description="Unified enterprise AI platform API for agent execution",
    version="3.0.0",
)

# ── Service singleton ─────────────────────────────────────────────────

_service: AIPlatformService | None = None


def get_service() -> AIPlatformService:
    """Get or create the platform service singleton."""
    global _service
    if _service is None:
        _service = create_platform_service()
    return _service


# ── Schemas ──────────────────────────────────────────────────────────


class AgentRunRequest(BaseModel):
    request: str = Field(..., min_length=1, max_length=4096, description="User input text")
    mode: str = Field(default="rule", pattern=r"^(rule|ollama|auto)$")
    metadata: dict[str, Any] | None = Field(default=None)


class AgentRunResponse(BaseModel):
    success: bool
    answer: Any = None
    score: float | None = None
    security_score: float | None = None
    trace_id: str = ""
    evaluation: dict[str, Any] | None = None
    gate: dict[str, Any] | None = None
    error: str | None = None
    error_type: str | None = None
    violations: list[str] = []
    metadata: dict[str, Any] = {}


class ErrorResponse(BaseModel):
    success: bool = False
    error: str
    error_type: str
    violations: list[str] = []
    trace_id: str | None = None


class HealthResponse(BaseModel):
    status: str = "ok"
    version: str = "3.0.0"
    platform: str = "chaos-demo-ai-platform"


# ── Error helpers ────────────────────────────────────────────────────


def _error(status_code: int, error_type: str, message: str, violations: list[str] | None = None) -> JSONResponse:
    return JSONResponse(
        status_code=status_code,
        content=ErrorResponse(
            error=message,
            error_type=error_type,
            violations=violations or [],
        ).model_dump(),
    )


# ── Exception handlers ───────────────────────────────────────────────


@app.exception_handler(SecurityBlockedError)
async def security_blocked_handler(request: Request, exc: SecurityBlockedError) -> JSONResponse:
    return _error(403, "SecurityBlocked", str(exc), getattr(exc, "violations", []))


@app.exception_handler(PlatformError)
async def platform_error_handler(request: Request, exc: PlatformError) -> JSONResponse:
    return _error(500, type(exc).__name__, str(exc))


# ── Routes ───────────────────────────────────────────────────────────


@app.get("/api/v1/health", response_model=HealthResponse)
async def health() -> HealthResponse:
    """Health check endpoint."""
    return HealthResponse()


@app.post("/api/v1/agent/run", response_model=AgentRunResponse)
async def agent_run(body: AgentRunRequest) -> AgentRunResponse | JSONResponse:
    """Execute an agent run through the full platform pipeline.

    Flow:
      trace → security → runtime → evaluation → quality gate → result
    """
    svc = get_service()

    try:
        result = svc.run(body.request, mode=body.mode)
    except SecurityBlockedError as exc:
        return _error(403, "SecurityBlocked", str(exc), exc.violations)
    except PlatformError as exc:
        return _error(500, type(exc).__name__, str(exc))
    except Exception as exc:
        return _error(500, "InternalError", str(exc))

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

    error_type = result.error_type or "UnknownError"
    status_codes = {"SecurityBlocked": 403, "AgentError": 500, "EvaluationFailed": 422}
    return _error(status_codes.get(error_type, 500), error_type, result.error or "Unknown error", result.violations)
