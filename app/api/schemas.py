"""API request/response schemas for the AI Platform service."""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field


class AgentRunRequest(BaseModel):
    """Request to execute an agent run."""

    request: str = Field(..., min_length=1, max_length=4096, description="User input text")
    mode: str = Field(
        default="rule",
        pattern=r"^(rule|ollama|auto)$",
        description="Agent mode: 'rule', 'ollama', or 'auto'",
    )
    metadata: dict[str, Any] | None = Field(
        default=None,
        description="Optional metadata to pass to the agent",
    )


class AgentRunResponse(BaseModel):
    """Response from an agent run."""

    success: bool = Field(..., description="Whether the request succeeded")
    answer: Any = Field(default=None, description="Agent answer")
    score: float | None = Field(default=None, description="Evaluation score (0.0-1.0)")
    security_score: float | None = Field(
        default=None, description="Security score (0-100, 100=fully safe)"
    )
    trace_id: str = Field(default="", description="Observability trace ID")
    evaluation: dict[str, Any] | None = Field(default=None, description="Evaluation details")
    gate: dict[str, Any] | None = Field(default=None, description="Quality gate report")
    error: str | None = Field(default=None, description="Error message if failed")
    error_type: str | None = Field(default=None, description="Error type classification")
    violations: list[str] = Field(default_factory=list, description="Security violations")
    metadata: dict[str, Any] = Field(default_factory=dict, description="Additional metadata")


class ErrorResponse(BaseModel):
    """Standard error response."""

    success: bool = False
    error: str = Field(..., description="Error message")
    error_type: str = Field(..., description="Error type classification")
    violations: list[str] = Field(default_factory=list, description="Violations if applicable")
    trace_id: str | None = Field(default=None, description="Trace ID if available")


class HealthResponse(BaseModel):
    """Health check response."""

    status: str = "ok"
    version: str = "3.0.0"
    platform: str = "chaos-demo-ai-platform"
