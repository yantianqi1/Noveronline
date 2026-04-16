"""Character and relationship event repository."""

from __future__ import annotations

from typing import Any

from sqlalchemy import Engine, and_, select

from app.tables.novel import character_events, relationship_events

from .base import ProjectScopedRepository


class EventRepository(ProjectScopedRepository):
    """Tracks character events and relationship events."""

    def __init__(self, engine: Engine):
        super().__init__(engine, character_events)
        self.rel_events = ProjectScopedRepository(engine, relationship_events)

    # ------------------------------------------------------------------
    # Character events
    # ------------------------------------------------------------------

    def log_character_event(self, project_id: str, values: dict[str, Any]) -> None:
        """Upsert a character event by event_id."""
        self.upsert_by_keys(project_id, values, ("event_id",))

    def list_character_events(
        self,
        project_id: str,
        entity_id: str | None = None,
        *,
        limit: int = 20,
    ) -> list[dict[str, Any]]:
        """List character events, optionally filtered by entity_id."""
        clauses = [character_events.c.project_id == project_id]
        if entity_id is not None:
            clauses.append(character_events.c.entity_id == entity_id)
        stmt = (
            select(character_events)
            .where(and_(*clauses))
            .order_by(character_events.c.chapter_order.desc())
            .limit(limit)
        )
        with self.connect() as conn:
            return [dict(row._mapping) for row in conn.execute(stmt).fetchall()]

    # ------------------------------------------------------------------
    # Relationship events
    # ------------------------------------------------------------------

    def log_relationship_event(self, project_id: str, values: dict[str, Any]) -> None:
        """Upsert a relationship event by event_id."""
        self.rel_events.upsert_by_keys(project_id, values, ("event_id",))

    def list_relationship_events(
        self,
        project_id: str,
        source_entity_id: str | None = None,
        *,
        limit: int = 20,
    ) -> list[dict[str, Any]]:
        """List relationship events, optionally filtered by source_entity_id."""
        clauses = [relationship_events.c.project_id == project_id]
        if source_entity_id is not None:
            clauses.append(
                relationship_events.c.source_entity_id == source_entity_id
            )
        stmt = (
            select(relationship_events)
            .where(and_(*clauses))
            .order_by(relationship_events.c.chapter_order.desc())
            .limit(limit)
        )
        with self.connect() as conn:
            return [dict(row._mapping) for row in conn.execute(stmt).fetchall()]
