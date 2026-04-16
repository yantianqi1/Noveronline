"""Shared Pydantic base for all request schemas."""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict


class AllowExtraBase(BaseModel):
    model_config = ConfigDict(extra="allow")


class ProjectContextMixin(AllowExtraBase):
    project_id: str | None = None
    graph_id: str | None = None
