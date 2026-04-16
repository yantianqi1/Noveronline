"""Relationship repository."""

from __future__ import annotations

from typing import Any

from sqlalchemy import Engine, and_, or_, select

from app.tables.novel import relationship_events, relationships

from .base import ProjectScopedRepository


class RelationshipRepository(ProjectScopedRepository):
    def __init__(self, engine: Engine):
        super().__init__(engine, relationships)
        self.events = ProjectScopedRepository(engine, relationship_events)

    # ------------------------------------------------------------------
    # Basic CRUD
    # ------------------------------------------------------------------

    def upsert_relationship(self, project_id: str, values: dict[str, Any]) -> None:
        self.upsert_by_keys(project_id, values, ("relation_id",))

    def list_relationships(self, project_id: str, *, limit: int = 500) -> list[dict[str, Any]]:
        return self.list_by_project(project_id, limit=limit)

    def get_relationship_detail(self, project_id: str, relation_id: str) -> dict[str, Any] | None:
        return self.get_one(project_id, relation_id=relation_id)

    def log_relationship_event(self, project_id: str, values: dict[str, Any]) -> None:
        self.events.upsert_by_keys(project_id, values, ("event_id",))

    # ------------------------------------------------------------------
    # Bidirectional lookup
    # ------------------------------------------------------------------

    def get_relationship_between(
        self,
        project_id: str,
        entity_a_id: str,
        entity_b_id: str,
    ) -> dict[str, Any] | None:
        """Find relationship between two entities regardless of direction."""
        stmt = (
            select(relationships)
            .where(
                and_(
                    relationships.c.project_id == project_id,
                    or_(
                        and_(
                            relationships.c.source_id == entity_a_id,
                            relationships.c.target_id == entity_b_id,
                        ),
                        and_(
                            relationships.c.source_id == entity_b_id,
                            relationships.c.target_id == entity_a_id,
                        ),
                    ),
                )
            )
            .limit(1)
        )
        with self.connect() as conn:
            return self.row_to_dict(conn.execute(stmt).fetchone())

    def get_entity_relationships(
        self,
        project_id: str,
        entity_id: str,
        *,
        limit: int = 20,
    ) -> list[dict[str, Any]]:
        """All relationships where entity is source or target."""
        stmt = (
            select(relationships)
            .where(
                and_(
                    relationships.c.project_id == project_id,
                    or_(
                        relationships.c.source_id == entity_id,
                        relationships.c.target_id == entity_id,
                    ),
                )
            )
            .limit(limit)
        )
        with self.connect() as conn:
            return [dict(row._mapping) for row in conn.execute(stmt).fetchall()]

    # ------------------------------------------------------------------
    # Relationship events (via self.events table)
    # ------------------------------------------------------------------

    def list_relationship_events(
        self,
        project_id: str,
        *,
        limit: int = 20,
    ) -> list[dict[str, Any]]:
        """List all relationship events ordered by chapter_order DESC."""
        stmt = (
            select(relationship_events)
            .where(relationship_events.c.project_id == project_id)
            .order_by(relationship_events.c.chapter_order.desc())
            .limit(limit)
        )
        with self.connect() as conn:
            return [dict(row._mapping) for row in conn.execute(stmt).fetchall()]
