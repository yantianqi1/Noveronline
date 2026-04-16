"""Archive library repository.

Operates on GLOBAL tables with manual project_id filtering:
``archive_library``, ``archive_sources``, ``archive_agent_memory``,
``archive_agent_memory_events``.

Replaces the old ``archive_library_storage.py`` connect-only layer.
"""

from __future__ import annotations

from typing import Any

from sqlalchemy import Engine, and_, delete, insert, or_, select, update

from app.tables.archive import (
    archive_agent_memory,
    archive_agent_memory_events,
    archive_library,
    archive_sources,
)

from .base import BaseRepository


class ArchiveRepository(BaseRepository):
    def __init__(self, engine: Engine):
        super().__init__(engine)

    # ------------------------------------------------------------------
    # archive_library
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
        stmt = select(archive_library)
        clauses = []
        if project_id:
            clauses.append(archive_library.c.project_id == project_id)
        if entity_type:
            clauses.append(archive_library.c.entity_type == entity_type)
        if importance_tier:
            clauses.append(archive_library.c.importance_tier == importance_tier)
        if agent_kind:
            clauses.append(archive_library.c.agent_kind == agent_kind)
        if template_key:
            clauses.append(archive_library.c.template_key == template_key)
        if clauses:
            stmt = stmt.where(and_(*clauses))
        stmt = stmt.order_by(
            archive_library.c.synced_at.desc(),
            archive_library.c.project_name.asc(),
            archive_library.c.entity_name.asc(),
        ).limit(limit).offset(offset)
        with self.connect() as conn:
            return [dict(r._mapping) for r in conn.execute(stmt).fetchall()]

    def count_archives(
        self,
        *,
        project_id: str | None = None,
        entity_type: str | None = None,
        importance_tier: str | None = None,
        agent_kind: str | None = None,
        template_key: str | None = None,
    ) -> int:
        """Return the total count matching the same filters as list_archives."""
        from sqlalchemy import func

        stmt = select(func.count()).select_from(archive_library)
        clauses = []
        if project_id:
            clauses.append(archive_library.c.project_id == project_id)
        if entity_type:
            clauses.append(archive_library.c.entity_type == entity_type)
        if importance_tier:
            clauses.append(archive_library.c.importance_tier == importance_tier)
        if agent_kind:
            clauses.append(archive_library.c.agent_kind == agent_kind)
        if template_key:
            clauses.append(archive_library.c.template_key == template_key)
        if clauses:
            stmt = stmt.where(and_(*clauses))
        with self.connect() as conn:
            return conn.execute(stmt).scalar() or 0

    def get_archive(self, archive_id: str) -> dict[str, Any] | None:
        stmt = select(archive_library).where(
            archive_library.c.archive_id == archive_id,
        )
        with self.connect() as conn:
            return self.row_to_dict(conn.execute(stmt).fetchone())

    def upsert_archive(self, values: dict[str, Any]) -> None:
        """INSERT OR REPLACE an archive row by ``archive_id``."""
        archive_id = values["archive_id"]
        with self.connect() as conn:
            existing = conn.execute(
                select(archive_library).where(
                    archive_library.c.archive_id == archive_id,
                ),
            ).fetchone()
            if existing is None:
                conn.execute(insert(archive_library).values(**values))
            else:
                conn.execute(
                    update(archive_library)
                    .where(archive_library.c.archive_id == archive_id)
                    .values(**values),
                )

    def delete_archive(self, archive_id: str) -> int:
        with self.connect() as conn:
            result = conn.execute(
                delete(archive_library).where(
                    archive_library.c.archive_id == archive_id,
                ),
            )
            return result.rowcount or 0

    def delete_archives_by_project(self, project_id: str) -> int:
        with self.connect() as conn:
            result = conn.execute(
                delete(archive_library).where(
                    archive_library.c.project_id == project_id,
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
            archive_library.c.entity_name.like(keyword),
            archive_library.c.entity_role.like(keyword),
            archive_library.c.core_drive.like(keyword),
            archive_library.c.hidden_tension.like(keyword),
            archive_library.c.relationship_summary.like(keyword),
        )
        conditions = [like_clauses]
        if project_id:
            conditions.append(archive_library.c.project_id == project_id)
        stmt = (
            select(archive_library)
            .where(and_(*conditions))
            .order_by(archive_library.c.synced_at.desc())
            .limit(limit)
        )
        with self.connect() as conn:
            return [dict(r._mapping) for r in conn.execute(stmt).fetchall()]

    def resolve_archives(self, archive_ids: list[str]) -> list[dict[str, Any]]:
        """Fetch multiple archives by ID list, preserving input order."""
        if not archive_ids:
            return []
        stmt = select(archive_library).where(
            archive_library.c.archive_id.in_(archive_ids),
        )
        with self.connect() as conn:
            rows = {
                r._mapping["archive_id"]: dict(r._mapping)
                for r in conn.execute(stmt).fetchall()
            }
        return [rows[aid] for aid in archive_ids if aid in rows]

    # ------------------------------------------------------------------
    # archive_sources
    # ------------------------------------------------------------------

    def upsert_source(self, values: dict[str, Any]) -> None:
        """INSERT OR REPLACE a source row by ``project_id``."""
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
    # archive_agent_memory
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
        """INSERT OR REPLACE a memory row by ``memory_id``."""
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
        """Update the ``memory_layer`` of a single memory row."""
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
        """Update status (and optionally timestamps) of a memory row."""
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
        """List active memories for an archive, ordered by layer priority."""
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
        """Return the highest version number for a subject, or 0."""
        from sqlalchemy import func

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
        """Find active rows that should be superseded before inserting."""
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
    # archive_agent_memory_events
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
        """Insert a new memory event row."""
        with self.connect() as conn:
            conn.execute(insert(archive_agent_memory_events).values(**values))
