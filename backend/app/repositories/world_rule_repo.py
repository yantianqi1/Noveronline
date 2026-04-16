"""World rule repository."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from sqlalchemy import Engine, and_, insert, select

from app.tables.novel import entities, rule_entity_links, world_rule_evidence

from .base import ProjectScopedRepository


class WorldRuleRepository(ProjectScopedRepository):
    def __init__(self, engine: Engine):
        super().__init__(engine, world_rule_evidence)
        self.links = ProjectScopedRepository(engine, rule_entity_links)

    # ------------------------------------------------------------------
    # existing helpers
    # ------------------------------------------------------------------

    def upsert_world_rule(self, project_id: str, values: dict) -> None:
        self.upsert_by_keys(project_id, values, ("evidence_id",))

    def link_rule_entity(self, project_id: str, values: dict) -> None:
        self.links.upsert_by_keys(project_id, values, ("evidence_id", "entity_id"))

    # ------------------------------------------------------------------
    # list_rules
    # ------------------------------------------------------------------

    def list_rules(self, project_id: str, *, limit: int = 500) -> list[dict[str, Any]]:
        """List all world rules for a project."""
        return self.list_by_project(project_id, limit=limit)

    # ------------------------------------------------------------------
    # cross-table: entity <-> rule joins
    # ------------------------------------------------------------------

    def get_entity_rules(
        self, project_id: str, entity_id: str, *, limit: int = 5
    ) -> list[dict[str, Any]]:
        """World rules linked to a given entity (via rule_entity_links)."""
        stmt = (
            select(world_rule_evidence)
            .select_from(
                world_rule_evidence.join(
                    rule_entity_links,
                    and_(
                        world_rule_evidence.c.evidence_id == rule_entity_links.c.evidence_id,
                        world_rule_evidence.c.project_id == rule_entity_links.c.project_id,
                    ),
                )
            )
            .where(
                and_(
                    rule_entity_links.c.project_id == project_id,
                    rule_entity_links.c.entity_id == entity_id,
                )
            )
            .limit(limit)
        )
        with self.connect() as conn:
            return [dict(r._mapping) for r in conn.execute(stmt).fetchall()]

    def get_rule_entities(
        self, project_id: str, evidence_id: str, *, limit: int = 5
    ) -> list[dict[str, Any]]:
        """Entities linked to a given world rule (via rule_entity_links)."""
        stmt = (
            select(entities)
            .select_from(
                entities.join(
                    rule_entity_links,
                    and_(
                        entities.c.entity_id == rule_entity_links.c.entity_id,
                        entities.c.project_id == rule_entity_links.c.project_id,
                    ),
                )
            )
            .where(
                and_(
                    rule_entity_links.c.project_id == project_id,
                    rule_entity_links.c.evidence_id == evidence_id,
                )
            )
            .limit(limit)
        )
        with self.connect() as conn:
            return [dict(r._mapping) for r in conn.execute(stmt).fetchall()]

    # ------------------------------------------------------------------
    # link_rule_to_entity (INSERT OR IGNORE convenience)
    # ------------------------------------------------------------------

    def link_rule_to_entity(
        self,
        project_id: str,
        evidence_id: str,
        entity_id: str,
        relevance: str = "constrains",
    ) -> None:
        """Link a world rule to an entity. Silently skips if the link already exists."""
        now = datetime.now(timezone.utc).isoformat()
        stmt = (
            insert(rule_entity_links)
            .values(
                project_id=project_id,
                evidence_id=evidence_id,
                entity_id=entity_id,
                relevance=relevance,
                created_at=now,
            )
            .prefix_with("OR IGNORE")
        )
        with self.connect() as conn:
            conn.execute(stmt)
