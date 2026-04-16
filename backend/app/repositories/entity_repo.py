"""Entity repository."""

from __future__ import annotations

import uuid
from datetime import datetime, timezone
from typing import Any

from sqlalchemy import Engine, and_, delete, insert, select, update

from app.tables.novel import (
    character_events,
    entities,
    entity_aliases,
    entity_labels,
)

from .base import ProjectScopedRepository


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


class EntityRepository(ProjectScopedRepository):
    def __init__(self, engine: Engine):
        super().__init__(engine, entities)
        self.aliases = ProjectScopedRepository(engine, entity_aliases)
        self.labels = ProjectScopedRepository(engine, entity_labels)

    # ------------------------------------------------------------------
    # Basic CRUD (existing)
    # ------------------------------------------------------------------

    def upsert_entity(self, project_id: str, values: dict) -> None:
        self.upsert_by_keys(project_id, values, ("entity_id",))

    def get_entity(self, project_id: str, entity_id: str) -> dict | None:
        return self.get_one(project_id, entity_id=entity_id)

    def list_entities(self, project_id: str, *, limit: int = 500) -> list[dict]:
        return self.list_by_project(project_id, limit=limit)

    def search_entities(self, project_id: str, query: str, *, limit: int = 500) -> list[dict]:
        return [
            row for row in self.list_by_project(project_id, limit=limit)
            if query in row.get("name", "")
        ]

    def delete_entity(self, project_id: str, entity_id: str) -> int:
        return self.delete_one(project_id, entity_id=entity_id)

    def upsert_alias(self, project_id: str, values: dict) -> None:
        self.aliases.upsert_by_keys(project_id, values, ("alias", "entity_id"))

    def upsert_label(self, project_id: str, values: dict) -> None:
        self.labels.upsert_by_keys(project_id, values, ("entity_id", "label"))

    # ------------------------------------------------------------------
    # Name resolution
    # ------------------------------------------------------------------

    def resolve_entity_id(self, project_id: str, name: str) -> str | None:
        """Resolve an entity name (or alias) to entity_id. Returns None if not found."""
        with self.connect() as conn:
            # Direct name match
            row = conn.execute(
                select(entities.c.entity_id).where(
                    and_(
                        entities.c.project_id == project_id,
                        entities.c.name == name,
                    )
                ).limit(1)
            ).fetchone()
            if row:
                return row.entity_id

            # Alias fallback via JOIN
            row = conn.execute(
                select(entities.c.entity_id)
                .select_from(
                    entities.join(
                        entity_aliases,
                        entities.c.entity_id == entity_aliases.c.entity_id,
                    )
                )
                .where(
                    and_(
                        entities.c.project_id == project_id,
                        entity_aliases.c.alias == name,
                    )
                )
                .limit(1)
            ).fetchone()
            return row.entity_id if row else None

    def get_entity_by_name(
        self, project_id: str, name: str, entity_type: str | None = None,
    ) -> dict[str, Any] | None:
        """Exact name match first, then alias fallback. Optionally filter by entity_type."""
        with self.connect() as conn:
            # Direct name match
            stmt = select(entities).where(
                and_(
                    entities.c.project_id == project_id,
                    entities.c.name == name,
                )
            )
            if entity_type:
                stmt = stmt.where(entities.c.entity_type == entity_type)
            row = conn.execute(stmt.limit(1)).fetchone()
            if row:
                return self.row_to_dict(row)

            # Alias fallback
            stmt = (
                select(entities)
                .select_from(
                    entities.join(
                        entity_aliases,
                        entities.c.entity_id == entity_aliases.c.entity_id,
                    )
                )
                .where(
                    and_(
                        entities.c.project_id == project_id,
                        entity_aliases.c.alias == name,
                    )
                )
            )
            if entity_type:
                stmt = stmt.where(entities.c.entity_type == entity_type)
            row = conn.execute(stmt.limit(1)).fetchone()
            return self.row_to_dict(row)

    # ------------------------------------------------------------------
    # Create / update by name
    # ------------------------------------------------------------------

    _ENTITY_WRITABLE_COLS = {
        "summary", "core_drive", "surface_mask", "hidden_tension",
        "current_objective", "ultimate_goal", "importance_tier",
        "entity_type", "speech_style", "values_text", "fears_text",
        "decision_pattern", "agent_behavior_hint",
        "mask_behavior", "emotional_baseline", "cognitive_biases_json",
    }

    def create_entity(
        self,
        project_id: str,
        name: str,
        entity_type: str,
        summary: str,
        **kwargs: Any,
    ) -> dict[str, Any]:
        """Create a new entity. Raises ValueError if name already exists."""
        now = _now()
        entity_id = f"ent_{uuid.uuid4().hex[:12]}"

        existing = self.resolve_entity_id(project_id, name)
        if existing:
            raise ValueError(f"Entity \"{name}\" already exists (ID: {existing})")

        with self.connect() as conn:
            conn.execute(
                insert(entities).values(
                    entity_id=entity_id,
                    project_id=project_id,
                    name=name,
                    entity_type=entity_type,
                    importance_tier=kwargs.get("importance_tier", "minor"),
                    summary=summary,
                    core_drive=kwargs.get("core_drive", ""),
                    surface_mask=kwargs.get("surface_mask", ""),
                    hidden_tension=kwargs.get("hidden_tension", ""),
                    current_objective=kwargs.get("current_objective", ""),
                    ultimate_goal=kwargs.get("ultimate_goal", ""),
                    values_text=kwargs.get("values_text", ""),
                    fears_text=kwargs.get("fears_text", ""),
                    decision_pattern=kwargs.get("decision_pattern", ""),
                    agent_behavior_hint=kwargs.get("agent_behavior_hint", ""),
                    profile_json="{}",
                    created_at=now,
                    updated_at=now,
                )
            )
            # Register the canonical name as an alias
            conn.execute(
                insert(entity_aliases).prefix_with("OR IGNORE").values(
                    project_id=project_id,
                    alias=name,
                    entity_id=entity_id,
                )
            )
            # Register additional aliases
            for alias in kwargs.get("aliases", []):
                if alias and alias != name:
                    conn.execute(
                        insert(entity_aliases).prefix_with("OR IGNORE").values(
                            project_id=project_id,
                            alias=alias,
                            entity_id=entity_id,
                        )
                    )

        return {"entity_id": entity_id, "name": name}

    def update_entity_by_name(self, project_id: str, name: str, **kwargs: Any) -> bool:
        """Update an existing entity by name. Returns False if not found."""
        entity_id = self.resolve_entity_id(project_id, name)
        if not entity_id:
            return False

        now = _now()
        updates = {k: v for k, v in kwargs.items() if k in self._ENTITY_WRITABLE_COLS}

        with self.connect() as conn:
            if updates:
                updates["updated_at"] = now
                conn.execute(
                    update(entities)
                    .where(
                        and_(
                            entities.c.project_id == project_id,
                            entities.c.entity_id == entity_id,
                        )
                    )
                    .values(**updates)
                )

            for alias in kwargs.get("aliases", []):
                if alias:
                    conn.execute(
                        insert(entity_aliases).prefix_with("OR IGNORE").values(
                            project_id=project_id,
                            alias=alias,
                            entity_id=entity_id,
                        )
                    )

        return True

    # ------------------------------------------------------------------
    # Query helpers
    # ------------------------------------------------------------------

    def list_entities_by_type(
        self, project_id: str, entity_type: str, limit: int = 500,
    ) -> list[dict[str, Any]]:
        stmt = (
            select(entities)
            .where(
                and_(
                    entities.c.project_id == project_id,
                    entities.c.entity_type == entity_type,
                )
            )
            .limit(limit)
        )
        with self.connect() as conn:
            return [dict(row._mapping) for row in conn.execute(stmt).fetchall()]

    def get_entity_with_details(
        self, project_id: str, entity_id: str,
    ) -> dict[str, Any] | None:
        """Get entity row plus all aliases and labels in one call."""
        entity = self.get_entity(project_id, entity_id)
        if entity is None:
            return None

        with self.connect() as conn:
            alias_rows = conn.execute(
                select(entity_aliases.c.alias).where(
                    and_(
                        entity_aliases.c.project_id == project_id,
                        entity_aliases.c.entity_id == entity_id,
                    )
                )
            ).fetchall()
            label_rows = conn.execute(
                select(entity_labels.c.label).where(
                    and_(
                        entity_labels.c.project_id == project_id,
                        entity_labels.c.entity_id == entity_id,
                    )
                )
            ).fetchall()

        entity["aliases"] = [r.alias for r in alias_rows]
        entity["labels"] = [r.label for r in label_rows]
        return entity

    def get_entity_recent_events(
        self, project_id: str, entity_id: str, limit: int = 5,
    ) -> list[dict[str, Any]]:
        """Return recent character_events for the entity."""
        stmt = (
            select(
                character_events.c.event_id,
                character_events.c.event_type,
                character_events.c.summary,
                character_events.c.chapter_order,
                character_events.c.segment_id,
            )
            .where(
                and_(
                    character_events.c.project_id == project_id,
                    character_events.c.entity_id == entity_id,
                )
            )
            .order_by(
                character_events.c.chapter_order.desc(),
                character_events.c.segment_id.desc(),
            )
            .limit(limit)
        )
        with self.connect() as conn:
            return [dict(row._mapping) for row in conn.execute(stmt).fetchall()]
