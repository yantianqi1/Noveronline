"""Archive library repository.

As of P5 of the asset-library refactor (migration 20260419_0003),
entity archives are stored in the ``assets`` table with
``asset_type='archive_entity'``. This repository presents the legacy
archive-library interface (``archive_id``, archive-specific columns)
but queries ``assets`` under the hood.

Satellite tables remain:
  * ``archive_sources``            — per-project legacy JSON source log
  * ``archive_agent_memory``       — per-archive memory rows
  * ``archive_agent_memory_events`` — memory event log

Their ``archive_id`` columns are soft FKs to ``assets.asset_id`` (the
values are identical to the pre-migration archive_library.archive_id).
"""

from __future__ import annotations

from typing import Any

from sqlalchemy import Engine, and_, delete, func, insert, or_, select, update

from app.schemas.asset_types import AssetType
from app.tables.archive import (
    archive_agent_memory,
    archive_agent_memory_events,
    archive_sources,
)
from app.tables.assets import assets

from .base import BaseRepository


_ARCHIVE_ASSET_TYPE = AssetType.ARCHIVE_ENTITY.value

# Columns on ``assets`` that together reconstruct an old archive_library
# row. ``asset_id`` is exposed back to callers under the legacy name
# ``archive_id``; ``source_ref`` used to be ``entity_uuid`` but the
# dedicated ``entity_uuid`` column preserves the original value.
_ARCHIVE_COLUMNS = (
    assets.c.asset_id.label("archive_id"),
    assets.c.project_id,
    assets.c.entity_uuid,
    assets.c.entity_name,
    assets.c.entity_type,
    assets.c.agent_kind,
    assets.c.importance_tier,
    assets.c.recommended_importance_tier,
    assets.c.selected_importance_tier,
    assets.c.template_key,
    assets.c.template_version,
    assets.c.entity_role,
    assets.c.core_drive,
    assets.c.surface_mask,
    assets.c.hidden_tension,
    assets.c.relationship_summary,
    assets.c.agent_behavior_hint,
    assets.c.human_ai_relation_tag,
    assets.c.can_act_as_agent,
    assets.c.notable_risks_json,
    assets.c.template_sections_json,
    assets.c.template_payload_json,
    assets.c.template_metadata_json,
    assets.c.synced_at,
    assets.c.entity_id,
    # project_name was a denormalized column on archive_library; post-
    # merge we no longer track it. Emit empty string for compatibility.
    select(assets.c.project_id).label("project_name_placeholder"),
)


def _archive_filter():
    """Shared WHERE fragment: only archive_entity rows."""
    return assets.c.asset_type == _ARCHIVE_ASSET_TYPE


def _row_to_archive_dict(row: Any) -> dict[str, Any]:
    """Convert a SELECT-from-assets row into the legacy archive shape."""
    if row is None:
        return None  # type: ignore[return-value]
    m = dict(row._mapping)
    # Rename asset_id → archive_id for API compatibility.
    if "asset_id" in m:
        m["archive_id"] = m.pop("asset_id")
    # Remove the placeholder column (subquery) — we can't easily compute
    # project_name without joining projects, so emit empty string.
    m.pop("project_name_placeholder", None)
    m["project_name"] = ""
    return m


class ArchiveRepository(BaseRepository):
    def __init__(self, engine: Engine):
        super().__init__(engine)

    # ------------------------------------------------------------------
    # archive "table" (backed by assets WHERE asset_type='archive_entity')
    # ------------------------------------------------------------------

    def list_archives(
        self,
        *,
        project_id: str | None = None,
        entity_type: str | None = None,
        importance_tier: str | None = None,
        agent_kind: str | None = None,
        template_key: str | None = None,
        limit: int = 200,
        offset: int = 0,
    ) -> list[dict[str, Any]]:
        stmt = select(assets).where(_archive_filter())
        clauses = []
        if project_id:
            clauses.append(assets.c.project_id == project_id)
        if entity_type:
            clauses.append(func.lower(assets.c.entity_type) == entity_type.lower())
        if importance_tier:
            clauses.append(assets.c.importance_tier == importance_tier)
        if agent_kind:
            clauses.append(assets.c.agent_kind == agent_kind)
        if template_key:
            clauses.append(assets.c.template_key == template_key)
        if clauses:
            stmt = stmt.where(and_(*clauses))
        stmt = stmt.order_by(
            assets.c.synced_at.desc(),
            assets.c.entity_name.asc(),
        ).limit(limit).offset(offset)
        with self.connect() as conn:
            rows = conn.execute(stmt).fetchall()
        return [self._legacy_shape(r) for r in rows]

    def count_archives(
        self,
        *,
        project_id: str | None = None,
        entity_type: str | None = None,
        importance_tier: str | None = None,
        agent_kind: str | None = None,
        template_key: str | None = None,
    ) -> int:
        stmt = select(func.count()).select_from(assets).where(_archive_filter())
        clauses = []
        if project_id:
            clauses.append(assets.c.project_id == project_id)
        if entity_type:
            clauses.append(func.lower(assets.c.entity_type) == entity_type.lower())
        if importance_tier:
            clauses.append(assets.c.importance_tier == importance_tier)
        if agent_kind:
            clauses.append(assets.c.agent_kind == agent_kind)
        if template_key:
            clauses.append(assets.c.template_key == template_key)
        if clauses:
            stmt = stmt.where(and_(*clauses))
        with self.connect() as conn:
            return conn.execute(stmt).scalar() or 0

    def get_archive(self, archive_id: str) -> dict[str, Any] | None:
        stmt = select(assets).where(
            and_(_archive_filter(), assets.c.asset_id == archive_id),
        )
        with self.connect() as conn:
            row = conn.execute(stmt).fetchone()
        return self._legacy_shape(row) if row else None

    def upsert_archive(self, values: dict[str, Any]) -> None:
        """INSERT OR REPLACE an archive row. ``values`` uses legacy keys
        (``archive_id``, ``entity_*``, ``template_*``, …); this method
        maps them onto the merged ``assets`` schema.
        """
        archive_id = values["archive_id"]
        asset_row = self._build_asset_row(values)
        with self.connect() as conn:
            existing = conn.execute(
                select(assets.c.asset_id).where(assets.c.asset_id == archive_id),
            ).fetchone()
            if existing is None:
                conn.execute(insert(assets).values(**asset_row))
            else:
                conn.execute(
                    update(assets)
                    .where(assets.c.asset_id == archive_id)
                    .values(**asset_row),
                )

    def delete_archive(self, archive_id: str) -> int:
        with self.connect() as conn:
            result = conn.execute(
                delete(assets).where(
                    and_(_archive_filter(), assets.c.asset_id == archive_id),
                ),
            )
            return result.rowcount or 0

    def delete_archives_by_project(self, project_id: str) -> int:
        with self.connect() as conn:
            result = conn.execute(
                delete(assets).where(
                    and_(_archive_filter(), assets.c.project_id == project_id),
                ),
            )
            return result.rowcount or 0

    def search_archives(
        self,
        query: str,
        *,
        project_id: str | None = None,
        limit: int = 50,
    ) -> list[dict[str, Any]]:
        """LIKE search on entity_name, entity_role, core_drive,
        hidden_tension, relationship_summary."""
        keyword = f"%{query}%"
        like_clauses = or_(
            assets.c.entity_name.like(keyword),
            assets.c.entity_role.like(keyword),
            assets.c.core_drive.like(keyword),
            assets.c.hidden_tension.like(keyword),
            assets.c.relationship_summary.like(keyword),
        )
        conditions = [_archive_filter(), like_clauses]
        if project_id:
            conditions.append(assets.c.project_id == project_id)
        stmt = (
            select(assets)
            .where(and_(*conditions))
            .order_by(assets.c.synced_at.desc())
            .limit(limit)
        )
        with self.connect() as conn:
            rows = conn.execute(stmt).fetchall()
        return [self._legacy_shape(r) for r in rows]

    def resolve_archives(self, archive_ids: list[str]) -> list[dict[str, Any]]:
        if not archive_ids:
            return []
        stmt = select(assets).where(
            and_(_archive_filter(), assets.c.asset_id.in_(archive_ids)),
        )
        with self.connect() as conn:
            rows = conn.execute(stmt).fetchall()
        by_id = {r._mapping["asset_id"]: self._legacy_shape(r) for r in rows}
        return [by_id[aid] for aid in archive_ids if aid in by_id]

    # ------------------------------------------------------------------
    # archive_sources (unchanged)
    # ------------------------------------------------------------------

    def upsert_source(self, values: dict[str, Any]) -> None:
        pid = values["project_id"]
        with self.connect() as conn:
            existing = conn.execute(
                select(archive_sources).where(
                    archive_sources.c.project_id == pid,
                ),
            ).fetchone()
            if existing is None:
                conn.execute(insert(archive_sources).values(**values))
            else:
                conn.execute(
                    update(archive_sources)
                    .where(archive_sources.c.project_id == pid)
                    .values(**values),
                )

    def get_source(self, project_id: str) -> dict[str, Any] | None:
        stmt = select(archive_sources).where(
            archive_sources.c.project_id == project_id,
        )
        with self.connect() as conn:
            return self.row_to_dict(conn.execute(stmt).fetchone())

    def list_sources(self) -> list[dict[str, Any]]:
        with self.connect() as conn:
            return [
                dict(r._mapping)
                for r in conn.execute(select(archive_sources)).fetchall()
            ]

    def delete_source(self, project_id: str) -> int:
        with self.connect() as conn:
            result = conn.execute(
                delete(archive_sources).where(
                    archive_sources.c.project_id == project_id,
                ),
            )
            return result.rowcount or 0

    # ------------------------------------------------------------------
    # archive_agent_memory (unchanged)
    # ------------------------------------------------------------------

    def list_memory(
        self,
        archive_id: str,
        *,
        tier: str | None = None,
        status: str | None = None,
        limit: int = 100,
    ) -> list[dict[str, Any]]:
        stmt = select(archive_agent_memory).where(
            archive_agent_memory.c.archive_id == archive_id,
        )
        if tier:
            stmt = stmt.where(archive_agent_memory.c.memory_layer == tier)
        if status:
            stmt = stmt.where(archive_agent_memory.c.status == status)
        stmt = stmt.order_by(
            archive_agent_memory.c.updated_at.desc(),
            archive_agent_memory.c.salience.desc(),
        ).limit(limit)
        with self.connect() as conn:
            return [dict(r._mapping) for r in conn.execute(stmt).fetchall()]

    def get_memory(self, memory_id: str) -> dict[str, Any] | None:
        stmt = select(archive_agent_memory).where(
            archive_agent_memory.c.memory_id == memory_id,
        )
        with self.connect() as conn:
            return self.row_to_dict(conn.execute(stmt).fetchone())

    def get_memory_by_archive(
        self, archive_id: str, memory_id: str,
    ) -> dict[str, Any] | None:
        stmt = select(archive_agent_memory).where(
            and_(
                archive_agent_memory.c.archive_id == archive_id,
                archive_agent_memory.c.memory_id == memory_id,
            ),
        )
        with self.connect() as conn:
            return self.row_to_dict(conn.execute(stmt).fetchone())

    def upsert_memory(self, values: dict[str, Any]) -> None:
        memory_id = values["memory_id"]
        with self.connect() as conn:
            existing = conn.execute(
                select(archive_agent_memory).where(
                    archive_agent_memory.c.memory_id == memory_id,
                ),
            ).fetchone()
            if existing is None:
                conn.execute(insert(archive_agent_memory).values(**values))
            else:
                conn.execute(
                    update(archive_agent_memory)
                    .where(archive_agent_memory.c.memory_id == memory_id)
                    .values(**values),
                )

    def update_memory_tier(self, memory_id: str, new_tier: str) -> int:
        with self.connect() as conn:
            result = conn.execute(
                update(archive_agent_memory)
                .where(archive_agent_memory.c.memory_id == memory_id)
                .values(memory_layer=new_tier),
            )
            return result.rowcount or 0

    def update_memory_status(
        self,
        memory_id: str,
        status: str,
        *,
        updated_at: str | None = None,
        rejected_at: str | None = None,
    ) -> int:
        values: dict[str, Any] = {"status": status}
        if updated_at is not None:
            values["updated_at"] = updated_at
        if rejected_at is not None:
            values["rejected_at"] = rejected_at
        with self.connect() as conn:
            result = conn.execute(
                update(archive_agent_memory)
                .where(archive_agent_memory.c.memory_id == memory_id)
                .values(**values),
            )
            return result.rowcount or 0

    def list_memory_by_subject(
        self,
        archive_id: str,
        normalized_subject: str,
    ) -> list[dict[str, Any]]:
        stmt = (
            select(archive_agent_memory)
            .where(
                and_(
                    archive_agent_memory.c.archive_id == archive_id,
                    archive_agent_memory.c.normalized_subject == normalized_subject,
                ),
            )
            .order_by(
                archive_agent_memory.c.version.desc(),
                archive_agent_memory.c.updated_at.desc(),
            )
        )
        with self.connect() as conn:
            return [dict(r._mapping) for r in conn.execute(stmt).fetchall()]

    def list_active_memory(
        self,
        archive_id: str,
        *,
        layers: tuple[str, ...] = ("canon",),
        statuses: tuple[str, ...] = ("active",),
        limit: int = 20,
    ) -> list[dict[str, Any]]:
        stmt = (
            select(archive_agent_memory)
            .where(
                and_(
                    archive_agent_memory.c.archive_id == archive_id,
                    archive_agent_memory.c.status.in_(statuses),
                    archive_agent_memory.c.memory_layer.in_(layers),
                ),
            )
            .order_by(
                archive_agent_memory.c.updated_at.desc(),
                archive_agent_memory.c.salience.desc(),
            )
            .limit(limit)
        )
        with self.connect() as conn:
            return [dict(r._mapping) for r in conn.execute(stmt).fetchall()]

    def max_memory_version(
        self,
        archive_id: str,
        memory_type: str,
        normalized_subject: str,
    ) -> int:
        stmt = (
            select(func.max(archive_agent_memory.c.version))
            .where(
                and_(
                    archive_agent_memory.c.archive_id == archive_id,
                    archive_agent_memory.c.memory_type == memory_type,
                    archive_agent_memory.c.normalized_subject == normalized_subject,
                ),
            )
        )
        with self.connect() as conn:
            return conn.execute(stmt).scalar() or 0

    def find_active_supersede_targets(
        self,
        archive_id: str,
        memory_type: str,
        normalized_subject: str,
        layers: tuple[str, ...],
    ) -> list[dict[str, Any]]:
        stmt = (
            select(archive_agent_memory)
            .where(
                and_(
                    archive_agent_memory.c.archive_id == archive_id,
                    archive_agent_memory.c.memory_type == memory_type,
                    archive_agent_memory.c.normalized_subject == normalized_subject,
                    archive_agent_memory.c.status == "active",
                    archive_agent_memory.c.memory_layer.in_(layers),
                ),
            )
        )
        with self.connect() as conn:
            return [dict(r._mapping) for r in conn.execute(stmt).fetchall()]

    # ------------------------------------------------------------------
    # archive_agent_memory_events (unchanged)
    # ------------------------------------------------------------------

    def list_memory_events(
        self,
        archive_id: str,
        *,
        normalized_subject: str | None = None,
        memory_id: str | None = None,
        limit: int = 100,
    ) -> list[dict[str, Any]]:
        clauses = [archive_agent_memory_events.c.archive_id == archive_id]
        if normalized_subject:
            clauses.append(
                archive_agent_memory_events.c.normalized_subject == normalized_subject,
            )
        if memory_id:
            clauses.append(
                archive_agent_memory_events.c.memory_id == memory_id,
            )
        stmt = (
            select(archive_agent_memory_events)
            .where(and_(*clauses))
            .order_by(archive_agent_memory_events.c.created_at.desc())
            .limit(limit)
        )
        with self.connect() as conn:
            return [dict(r._mapping) for r in conn.execute(stmt).fetchall()]

    def log_memory_event(self, values: dict[str, Any]) -> None:
        with self.connect() as conn:
            conn.execute(insert(archive_agent_memory_events).values(**values))

    # ------------------------------------------------------------------
    # Helpers: legacy shape + upsert value mapping
    # ------------------------------------------------------------------

    @staticmethod
    def _legacy_shape(row: Any) -> dict[str, Any]:
        """Return a dict matching the pre-P5 ``archive_library`` row shape.

        The ``asset_id`` PK is exposed as ``archive_id``; ``project_name``
        (a denormalized column on the legacy table) is emitted as ''
        because post-merge we don't track it.
        """
        m = dict(row._mapping)
        m["archive_id"] = m.pop("asset_id")
        m["project_name"] = ""
        # Drop assets-only columns that the archive consumer never sees.
        for col in (
            "scope", "asset_type", "category", "title", "summary", "content",
            "payload_json", "tags_json", "source_kind", "source_ref",
            "enabled", "pinned", "word_count", "created_at", "updated_at",
        ):
            m.pop(col, None)
        return m

    @staticmethod
    def _build_asset_row(values: dict[str, Any]) -> dict[str, Any]:
        """Map a legacy archive-library values dict onto the merged
        ``assets`` row layout."""
        archive_id = values["archive_id"]
        entity_name = values.get("entity_name") or ""
        entity_role = values.get("entity_role") or ""
        core_drive = values.get("core_drive") or ""
        relationship_summary = values.get("relationship_summary") or ""
        summary = entity_role or core_drive or relationship_summary or ""
        synced_at = values.get("synced_at") or ""
        return {
            "asset_id": archive_id,
            "project_id": values.get("project_id"),
            "scope": "project",
            "asset_type": _ARCHIVE_ASSET_TYPE,
            "category": "",
            "title": entity_name,
            "summary": summary,
            "content": "",
            "payload_json": "{}",
            "tags_json": "[]",
            "source_kind": "archive",
            "source_ref": values.get("entity_uuid") or "",
            "enabled": 1,
            "pinned": 0,
            "word_count": 0,
            "created_at": synced_at,
            "updated_at": synced_at,
            # Archive-specific columns
            "entity_uuid": values.get("entity_uuid"),
            "entity_name": entity_name,
            "entity_type": values.get("entity_type"),
            "agent_kind": values.get("agent_kind"),
            "importance_tier": values.get("importance_tier"),
            "recommended_importance_tier": values.get("recommended_importance_tier"),
            "selected_importance_tier": values.get("selected_importance_tier"),
            "template_key": values.get("template_key"),
            "template_version": values.get("template_version"),
            "entity_role": entity_role,
            "core_drive": core_drive,
            "surface_mask": values.get("surface_mask"),
            "hidden_tension": values.get("hidden_tension"),
            "relationship_summary": relationship_summary,
            "agent_behavior_hint": values.get("agent_behavior_hint"),
            "human_ai_relation_tag": values.get("human_ai_relation_tag"),
            "can_act_as_agent": values.get("can_act_as_agent"),
            "notable_risks_json": values.get("notable_risks_json"),
            "template_sections_json": values.get("template_sections_json"),
            "template_payload_json": values.get("template_payload_json"),
            "template_metadata_json": values.get("template_metadata_json"),
            "entity_id": values.get("entity_id"),
            "synced_at": synced_at,
        }
