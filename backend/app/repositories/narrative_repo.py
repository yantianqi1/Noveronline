"""Narrative arcs, volume/segment summaries, consistency notes, and project meta."""

from __future__ import annotations

from typing import Any

from sqlalchemy import Engine, and_, select

from app.tables.novel import (
    consistency_notes,
    narrative_arcs,
    project_meta,
    segment_summaries,
    volume_summaries,
)

from .base import ProjectScopedRepository


class NarrativeRepository(ProjectScopedRepository):
    """Aggregate repository for narrative structure data."""

    def __init__(self, engine: Engine):
        super().__init__(engine, narrative_arcs)
        self.volumes = ProjectScopedRepository(engine, volume_summaries)
        self.segments = ProjectScopedRepository(engine, segment_summaries)
        self.notes = ProjectScopedRepository(engine, consistency_notes)
        self.meta = ProjectScopedRepository(engine, project_meta)

    # ------------------------------------------------------------------
    # Narrative arcs
    # ------------------------------------------------------------------

    def list_narrative_arcs(
        self, project_id: str, *, limit: int = 20
    ) -> list[dict[str, Any]]:
        stmt = (
            select(narrative_arcs)
            .where(narrative_arcs.c.project_id == project_id)
            .order_by(narrative_arcs.c.arc_id)
            .limit(limit)
        )
        with self.connect() as conn:
            return [dict(row._mapping) for row in conn.execute(stmt).fetchall()]

    def upsert_narrative_arc(
        self, project_id: str, values: dict[str, Any]
    ) -> None:
        self.upsert_by_keys(project_id, values, ("arc_id",))

    # ------------------------------------------------------------------
    # Volume summaries
    # ------------------------------------------------------------------

    def list_volume_summaries(
        self, project_id: str, *, limit: int = 20
    ) -> list[dict[str, Any]]:
        stmt = (
            select(volume_summaries)
            .where(volume_summaries.c.project_id == project_id)
            .order_by(volume_summaries.c.volume_order)
            .limit(limit)
        )
        with self.connect() as conn:
            return [dict(row._mapping) for row in conn.execute(stmt).fetchall()]

    def upsert_volume_summary(
        self, project_id: str, values: dict[str, Any]
    ) -> None:
        self.volumes.upsert_by_keys(project_id, values, ("volume_id",))

    # ------------------------------------------------------------------
    # Segment summaries
    # ------------------------------------------------------------------

    def list_segment_summaries(
        self,
        project_id: str,
        segment_ids: list[str] | None = None,
        *,
        offset: int = 0,
        limit: int = 30,
    ) -> list[dict[str, Any]]:
        """List segment summaries with optional ID filter and pagination."""
        clauses = [segment_summaries.c.project_id == project_id]
        if segment_ids is not None:
            clauses.append(segment_summaries.c.segment_id.in_(segment_ids))
        stmt = (
            select(segment_summaries)
            .where(and_(*clauses))
            .order_by(segment_summaries.c.segment_order)
            .offset(offset)
            .limit(limit)
        )
        with self.connect() as conn:
            return [dict(row._mapping) for row in conn.execute(stmt).fetchall()]

    def upsert_segment_summary(
        self, project_id: str, values: dict[str, Any]
    ) -> None:
        self.segments.upsert_by_keys(project_id, values, ("segment_id",))

    # ------------------------------------------------------------------
    # Consistency notes
    # ------------------------------------------------------------------

    def list_consistency_notes(
        self, project_id: str, *, limit: int = 20
    ) -> list[dict[str, Any]]:
        stmt = (
            select(consistency_notes)
            .where(consistency_notes.c.project_id == project_id)
            .order_by(consistency_notes.c.segment_id)
            .limit(limit)
        )
        with self.connect() as conn:
            return [dict(row._mapping) for row in conn.execute(stmt).fetchall()]

    def upsert_consistency_note(
        self, project_id: str, values: dict[str, Any]
    ) -> None:
        self.notes.upsert_by_keys(project_id, values, ("note_id",))

    # ------------------------------------------------------------------
    # Project meta
    # ------------------------------------------------------------------

    def get_project_meta(self, project_id: str) -> dict[str, Any] | None:
        return self.meta.get_one(project_id)

    def set_project_meta(
        self, project_id: str, values: dict[str, Any]
    ) -> None:
        self.meta.upsert_by_keys(project_id, values, ("project_id",))
