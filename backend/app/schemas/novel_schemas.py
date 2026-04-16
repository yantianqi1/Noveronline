"""Pydantic request schemas for /api/novel routes."""

from __future__ import annotations

from typing import Any

from ._base import AllowExtraBase, ProjectContextMixin


class ArchiveCandidatesRequest(ProjectContextMixin):
    entity_types: list[str] | None = None


class GenerateArchivesRequest(ProjectContextMixin):
    entity_types: list[str] | None = None
    use_llm: bool = True
    tier_overrides: list[dict[str, Any]] | None = None
    candidate_snapshot: list[dict[str, Any]] | None = None


class ParallelWorldConfigRequest(ProjectContextMixin):
    entity_types: list[str] | None = None
    focus_question: str | None = None
    variables: list[Any] = []
    branch_count: int | None = None
    use_llm: bool = True


class SeedAnalysisRequest(AllowExtraBase):
    project_id: str
    analysis_goal: str | None = None


class PlotInspirationRequest(ProjectContextMixin):
    creator_prompt: str
    session_id: str | None = None
    branch_id: str | None = None
    entity_types: list[str] | None = None


class ChapterContextRequest(AllowExtraBase):
    """Passed directly to ChapterContextPackBuilder.build()."""
    pass


class ReviewerRulesRequest(AllowExtraBase):
    project_id: str
    custom_prompt: str = ""
