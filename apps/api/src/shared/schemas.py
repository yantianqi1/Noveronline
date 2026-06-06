from __future__ import annotations

from datetime import datetime
from typing import Any

from pydantic import BaseModel, Field


class ApiError(BaseModel):
    code: str
    message: str
    details: dict[str, Any] = Field(default_factory=dict)
    retryable: bool


class ErrorResponse(BaseModel):
    trace_id: str
    error: ApiError


class HealthStatus(BaseModel):
    status: str
    service: str
    version: str


class OperationStep(BaseModel):
    step_id: str
    stage: str
    status: str
    progress_percent: int = 0
    message: str | None = None
    started_at: datetime | None = None
    finished_at: datetime | None = None
    elapsed_ms: int | None = None


class OperationResource(BaseModel):
    operation_id: str
    trace_id: str
    status: str
    progress_percent: int = 0
    message: str | None = None
    retryable: bool = False
    created_at: datetime | None = None
    updated_at: datetime | None = None
    steps: list[OperationStep] = Field(default_factory=list)
