"""Plot thread repository."""

from __future__ import annotations

import uuid
from datetime import datetime, timezone
from typing import Any

from sqlalchemy import Engine, and_, delete, insert, select, update

from app.tables.novel import entities, plot_threads, thread_entity_links, thread_lifecycle

from .base import ProjectScopedRepository

_VALID_TRANSITIONS: dict[str, set[str]] = {
    "open": {"progressed", "resolved"},
    "progressed": {"open", "resolved"},
    "resolved": set(),
}


class ThreadRepository(ProjectScopedRepository):
    def __init__(self, engine: Engine):
        super().__init__(engine, plot_threads)
        self.links = ProjectScopedRepository(engine, thread_entity_links)
        self.lifecycle = ProjectScopedRepository(engine, thread_lifecycle)

    # ------------------------------------------------------------------
    # existing helpers
    # ------------------------------------------------------------------

    def upsert_thread(self, project_id: str, values: dict) -> None:
        self.upsert_by_keys(project_id, values, ("thread_id",))

    def list_threads(self, project_id: str, *, limit: int = 500) -> list[dict]:
        return self.list_by_project(project_id, limit=limit)

    def link_thread_entity(self, project_id: str, values: dict) -> None:
        self.links.upsert_by_keys(project_id, values, ("thread_id", "entity_id"))

    # ------------------------------------------------------------------
    # get_thread / get_thread_by_id
    # ------------------------------------------------------------------

    def get_thread(self, project_id: str, thread_key: str) -> dict[str, Any] | None:
        """Query a single thread by its thread_key."""
        return self.get_one(project_id, thread_key=thread_key)

    def get_thread_by_id(self, project_id: str, thread_id: str) -> dict[str, Any] | None:
        """Query a single thread by its thread_id."""
        return self.get_one(project_id, thread_id=thread_id)

    # ------------------------------------------------------------------
    # create_thread
    # ------------------------------------------------------------------

    def create_thread(
        self,
        project_id: str,
        thread_key: str,
        detail: str,
        status: str = "open",
        chapter_order: int = 0,
    ) -> dict[str, str]:
        """Create a new plot thread and its first lifecycle entry.

        Returns ``{"thread_id": ..., "thread_key": ...}``.
        """
        now = datetime.now(timezone.utc).isoformat()
        thread_id = f"pt_{uuid.uuid4().hex[:12]}"
        lifecycle_id = f"tl_{uuid.uuid4().hex[:12]}"

        with self.connect() as conn:
            conn.execute(
                insert(plot_threads).values(
                    thread_id=thread_id,
                    project_id=project_id,
                    thread_key=thread_key,
                    status=status,
                    detail=detail,
                    source_chapter=str(chapter_order),
                    created_at=now,
                    updated_at=now,
                )
            )
            conn.execute(
                insert(thread_lifecycle).values(
                    lifecycle_id=lifecycle_id,
                    project_id=project_id,
                    thread_key=thread_key,
                    segment_id="",
                    chapter_order=chapter_order,
                    status=status,
                    detail=detail,
                    resolution_detail="",
                    created_at=now,
                )
            )

        return {"thread_id": thread_id, "thread_key": thread_key}

    # ------------------------------------------------------------------
    # update_thread
    # ------------------------------------------------------------------

    def update_thread(
        self,
        project_id: str,
        thread_key: str,
        *,
        status: str | None = None,
        detail: str | None = None,
        resolution_detail: str | None = None,
        chapter_order: int = 0,
    ) -> bool:
        """Update an existing thread (exact then fuzzy match on thread_key).

        Validates status transitions and appends a lifecycle entry.
        Raises ``ValueError`` on invalid status transition.
        Returns ``True`` if a row was updated.
        """
        with self.connect() as conn:
            # --- locate the thread: exact match first, then LIKE fuzzy ---
            row = conn.execute(
                select(plot_threads).where(
                    and_(
                        plot_threads.c.project_id == project_id,
                        plot_threads.c.thread_key == thread_key,
                    )
                ).limit(1)
            ).fetchone()

            if row is None:
                row = conn.execute(
                    select(plot_threads).where(
                        and_(
                            plot_threads.c.project_id == project_id,
                            plot_threads.c.thread_key.like(f"%{thread_key}%"),
                        )
                    ).limit(1)
                ).fetchone()

            if row is None:
                return False

            current = dict(row._mapping)
            current_status = current["status"]

            # --- validate status transition ---
            new_status = status or current_status
            if new_status != current_status:
                allowed = _VALID_TRANSITIONS.get(current_status, set())
                if new_status not in allowed:
                    raise ValueError(
                        f"Invalid thread status transition: {current_status!r} -> {new_status!r}"
                    )

            now = datetime.now(timezone.utc).isoformat()

            # --- build UPDATE payload ---
            updates: dict[str, Any] = {"updated_at": now}
            if status is not None:
                updates["status"] = status
            if detail is not None:
                updates["detail"] = detail

            conn.execute(
                update(plot_threads)
                .where(
                    and_(
                        plot_threads.c.project_id == project_id,
                        plot_threads.c.thread_id == current["thread_id"],
                    )
                )
                .values(**updates)
            )

            # --- append lifecycle entry ---
            lifecycle_id = f"tl_{uuid.uuid4().hex[:12]}"
            conn.execute(
                insert(thread_lifecycle).values(
                    lifecycle_id=lifecycle_id,
                    project_id=project_id,
                    thread_key=current["thread_key"],
                    segment_id="",
                    chapter_order=chapter_order,
                    status=new_status,
                    detail=detail or current["detail"],
                    resolution_detail=resolution_detail or "",
                    created_at=now,
                )
            )

        return True

    # ------------------------------------------------------------------
    # get_open_threads
    # ------------------------------------------------------------------

    def get_open_threads(
        self, project_id: str, *, up_to_chapter: int | None = None
    ) -> list[dict[str, Any]]:
        """Return open threads, optionally filtered by chapter order."""
        conditions = [
            plot_threads.c.project_id == project_id,
            plot_threads.c.status == "open",
        ]
        if up_to_chapter is not None:
            conditions.append(plot_threads.c.source_chapter <= str(up_to_chapter))

        stmt = (
            select(plot_threads)
            .where(and_(*conditions))
            .order_by(plot_threads.c.updated_at.desc())
        )
        with self.connect() as conn:
            return [dict(r._mapping) for r in conn.execute(stmt).fetchall()]

    # ------------------------------------------------------------------
    # cross-table: entity <-> thread joins
    # ------------------------------------------------------------------

    def get_entity_threads(
        self, project_id: str, entity_id: str, *, limit: int = 5
    ) -> list[dict[str, Any]]:
        """Threads linked to a given entity (via thread_entity_links)."""
        stmt = (
            select(plot_threads)
            .select_from(
                plot_threads.join(
                    thread_entity_links,
                    and_(
                        plot_threads.c.thread_id == thread_entity_links.c.thread_id,
                        plot_threads.c.project_id == thread_entity_links.c.project_id,
                    ),
                )
            )
            .where(
                and_(
                    thread_entity_links.c.project_id == project_id,
                    thread_entity_links.c.entity_id == entity_id,
                )
            )
            .limit(limit)
        )
        with self.connect() as conn:
            return [dict(r._mapping) for r in conn.execute(stmt).fetchall()]

    def get_thread_entities(
        self, project_id: str, thread_id: str, *, limit: int = 5
    ) -> list[dict[str, Any]]:
        """Entities linked to a given thread (via thread_entity_links)."""
        stmt = (
            select(entities)
            .select_from(
                entities.join(
                    thread_entity_links,
                    and_(
                        entities.c.entity_id == thread_entity_links.c.entity_id,
                        entities.c.project_id == thread_entity_links.c.project_id,
                    ),
                )
            )
            .where(
                and_(
                    thread_entity_links.c.project_id == project_id,
                    thread_entity_links.c.thread_id == thread_id,
                )
            )
            .limit(limit)
        )
        with self.connect() as conn:
            return [dict(r._mapping) for r in conn.execute(stmt).fetchall()]

    # ------------------------------------------------------------------
    # lifecycle
    # ------------------------------------------------------------------

    def list_thread_lifecycle(
        self, project_id: str, thread_key: str
    ) -> list[dict[str, Any]]:
        """All lifecycle entries for a thread_key, ordered by created_at."""
        stmt = (
            select(thread_lifecycle)
            .where(
                and_(
                    thread_lifecycle.c.project_id == project_id,
                    thread_lifecycle.c.thread_key == thread_key,
                )
            )
            .order_by(thread_lifecycle.c.created_at)
        )
        with self.connect() as conn:
            return [dict(r._mapping) for r in conn.execute(stmt).fetchall()]
