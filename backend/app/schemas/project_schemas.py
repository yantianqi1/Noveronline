"""Pydantic request schemas for /api/project routes."""

from __future__ import annotations

from ._base import AllowExtraBase


class RerunSeedRequest(AllowExtraBase):
    analysis_goal: str | None = None
    additional_context: str = ""
    segment_token_limit: int = 50000


class BuildGraphRequest(AllowExtraBase):
    project_id: str
    graph_name: str = "Novel Story Graph"
