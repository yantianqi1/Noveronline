"""Worldline prepare repository.

Replaces worldline_prepare_storage.py with SQLAlchemy Core access
through the unified database engine.

Tables: prepare_runs, prepared_agent_dossiers, prepare_event_log

prepare_runs is keyed by prepare_id (single PK).
prepared_agent_dossiers is keyed by (prepare_id, agent_id).
prepare_event_log is keyed by event_id (single PK).

project_id is nullable on all three tables (session may not yet be
bound to a project), so this repository extends BaseRepository.
"""

from __future__ import annotations

from typing import Any

from sqlalchemy import Engine, and_, asc, delete, desc, insert, select, update

from app.tables.worldline import (
    prepare_event_log,
    prepare_runs,
    prepared_agent_dossiers,
)

from .base import BaseRepository


class WorldlinePrepareRepository(BaseRepository):
    def __init__(self, engine: Engine):
        super().__init__(engine)

    # ------------------------------------------------------------------
    # 1. save_run  (upsert by prepare_id)
    # ------------------------------------------------------------------

    def save_run(self, values: dict[str, Any]) -> None:
        """Upsert a prepare_runs row keyed by ``prepare_id``."""
        tbl = prepare_runs
        prepare_id = values["prepare_id"]
        where = tbl.c.prepare_id == prepare_id

        with self.connect() as conn:
            existing = conn.execute(select(tbl).where(where).limit(1)).fetchone()
            if existing:
                conn.execute(update(tbl).where(where).values(**values))
            else:
                conn.execute(insert(tbl).values(**values))

    # ------------------------------------------------------------------
    # 2. get_run
    # ------------------------------------------------------------------

    def get_run(self, prepare_id: str) -> dict[str, Any] | None:
        tbl = prepare_runs
        stmt = select(tbl).where(tbl.c.prepare_id == prepare_id).limit(1)
        with self.connect() as conn:
            return self.row_to_dict(conn.execute(stmt).fetchone())

    # ------------------------------------------------------------------
    # 3. save_dossier  (upsert by prepare_id + agent_id)
    # ------------------------------------------------------------------

    def save_dossier(self, prepare_id: str, values: dict[str, Any]) -> None:
        """Upsert a prepared_agent_dossiers row."""
        tbl = prepared_agent_dossiers
        payload = {"prepare_id": prepare_id, **values}
        agent_id = payload["agent_id"]

        where = and_(
            tbl.c.prepare_id == prepare_id,
            tbl.c.agent_id == agent_id,
        )
        with self.connect() as conn:
            existing = conn.execute(select(tbl).where(where).limit(1)).fetchone()
            if existing:
                conn.execute(update(tbl).where(where).values(**payload))
            else:
                conn.execute(insert(tbl).values(**payload))

    # ------------------------------------------------------------------
    # 4. list_dossiers
    # ------------------------------------------------------------------

    def list_dossiers(self, prepare_id: str) -> list[dict[str, Any]]:
        tbl = prepared_agent_dossiers
        stmt = (
            select(tbl)
            .where(tbl.c.prepare_id == prepare_id)
            .order_by(asc(tbl.c.display_name))
        )
        with self.connect() as conn:
            return [dict(r._mapping) for r in conn.execute(stmt).fetchall()]

    # ------------------------------------------------------------------
    # 5. get_dossier
    # ------------------------------------------------------------------

    def get_dossier(
        self, prepare_id: str, agent_id: str,
    ) -> dict[str, Any] | None:
        tbl = prepared_agent_dossiers
        stmt = (
            select(tbl)
            .where(
                and_(
                    tbl.c.prepare_id == prepare_id,
                    tbl.c.agent_id == agent_id,
                )
            )
            .limit(1)
        )
        with self.connect() as conn:
            return self.row_to_dict(conn.execute(stmt).fetchone())

    # ------------------------------------------------------------------
    # 6. append_event
    # ------------------------------------------------------------------

    def append_event(self, values: dict[str, Any]) -> None:
        with self.connect() as conn:
            conn.execute(insert(prepare_event_log).values(**values))

    # ------------------------------------------------------------------
    # 7. list_events
    # ------------------------------------------------------------------

    def list_events(self, prepare_id: str) -> list[dict[str, Any]]:
        tbl = prepare_event_log
        stmt = (
            select(tbl)
            .where(tbl.c.prepare_id == prepare_id)
            .order_by(asc(tbl.c.created_at))
        )
        with self.connect() as conn:
            return [dict(r._mapping) for r in conn.execute(stmt).fetchall()]
