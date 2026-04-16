"""Worldline runtime repository.

Replaces worldline_runtime_storage.py with SQLAlchemy Core access
through the unified database engine.

Tables: agent_registry, agent_state_snapshots, agent_action_log,
        agent_dialogue_log, agent_episodic_memory, relation_state_log

All tables are session-scoped (keyed by session_id + branch_id), not
project-scoped, so this repository extends BaseRepository directly.
The tables *do* carry a project_id column for cross-cutting queries,
but the primary access pattern is by session.
"""

from __future__ import annotations

from typing import Any

from sqlalchemy import Engine, and_, delete, desc, insert, or_, select, update

from app.tables.worldline import (
    agent_action_log,
    agent_dialogue_log,
    agent_episodic_memory,
    agent_registry,
    agent_state_snapshots,
    relation_state_log,
)

from .base import BaseRepository


class WorldlineRuntimeRepository(BaseRepository):
    def __init__(self, engine: Engine):
        super().__init__(engine)

    # ------------------------------------------------------------------
    # 1. register_agent  (upsert by session_id + branch_id + agent_id)
    # ------------------------------------------------------------------

    def register_agent(self, session_id: str, values: dict[str, Any]) -> None:
        """Upsert into agent_registry keyed by (session_id, branch_id, agent_id)."""
        tbl = agent_registry
        payload = {"session_id": session_id, **values}
        branch_id = payload["branch_id"]
        agent_id = payload["agent_id"]

        where = and_(
            tbl.c.session_id == session_id,
            tbl.c.branch_id == branch_id,
            tbl.c.agent_id == agent_id,
        )
        with self.connect() as conn:
            existing = conn.execute(select(tbl).where(where).limit(1)).fetchone()
            if existing:
                conn.execute(update(tbl).where(where).values(**payload))
            else:
                conn.execute(insert(tbl).values(**payload))

    # ------------------------------------------------------------------
    # 2. list_agents
    # ------------------------------------------------------------------

    def list_agents(self, session_id: str) -> list[dict[str, Any]]:
        tbl = agent_registry
        stmt = (
            select(tbl)
            .where(tbl.c.session_id == session_id)
            .order_by(tbl.c.display_name)
        )
        with self.connect() as conn:
            return [dict(r._mapping) for r in conn.execute(stmt).fetchall()]

    # ------------------------------------------------------------------
    # 3. get_agent
    # ------------------------------------------------------------------

    def get_agent(
        self, session_id: str, agent_id: str, branch_id: str | None = None,
    ) -> dict[str, Any] | None:
        tbl = agent_registry
        clauses = [tbl.c.session_id == session_id, tbl.c.agent_id == agent_id]
        if branch_id:
            clauses.append(tbl.c.branch_id == branch_id)
        stmt = select(tbl).where(and_(*clauses)).limit(1)
        with self.connect() as conn:
            return self.row_to_dict(conn.execute(stmt).fetchone())

    # ------------------------------------------------------------------
    # 4. save_state_snapshot
    # ------------------------------------------------------------------

    def save_state_snapshot(self, values: dict[str, Any]) -> None:
        with self.connect() as conn:
            conn.execute(insert(agent_state_snapshots).values(**values))

    # ------------------------------------------------------------------
    # 5. list_state_snapshots
    # ------------------------------------------------------------------

    def list_state_snapshots(
        self,
        session_id: str,
        agent_id: str | None = None,
        *,
        limit: int = 50,
    ) -> list[dict[str, Any]]:
        tbl = agent_state_snapshots
        clauses = [tbl.c.session_id == session_id]
        if agent_id:
            clauses.append(tbl.c.agent_id == agent_id)
        stmt = (
            select(tbl)
            .where(and_(*clauses))
            .order_by(desc(tbl.c.created_at))
            .limit(limit)
        )
        with self.connect() as conn:
            return [dict(r._mapping) for r in conn.execute(stmt).fetchall()]

    # ------------------------------------------------------------------
    # 6. log_action
    # ------------------------------------------------------------------

    def log_action(self, values: dict[str, Any]) -> None:
        with self.connect() as conn:
            conn.execute(insert(agent_action_log).values(**values))

    # ------------------------------------------------------------------
    # 7. list_actions
    # ------------------------------------------------------------------

    def list_actions(
        self,
        session_id: str,
        agent_id: str | None = None,
        *,
        limit: int = 50,
    ) -> list[dict[str, Any]]:
        tbl = agent_action_log
        clauses = [tbl.c.session_id == session_id]
        if agent_id:
            clauses.append(tbl.c.agent_id == agent_id)
        stmt = (
            select(tbl)
            .where(and_(*clauses))
            .order_by(desc(tbl.c.created_at))
            .limit(limit)
        )
        with self.connect() as conn:
            return [dict(r._mapping) for r in conn.execute(stmt).fetchall()]

    # ------------------------------------------------------------------
    # 8. log_dialogue
    # ------------------------------------------------------------------

    def log_dialogue(self, values: dict[str, Any]) -> None:
        with self.connect() as conn:
            conn.execute(insert(agent_dialogue_log).values(**values))

    # ------------------------------------------------------------------
    # 9. list_dialogues
    # ------------------------------------------------------------------

    def list_dialogues(
        self,
        session_id: str,
        agent_id: str | None = None,
        *,
        limit: int = 50,
    ) -> list[dict[str, Any]]:
        tbl = agent_dialogue_log
        clauses = [tbl.c.session_id == session_id]
        if agent_id:
            clauses.append(tbl.c.agent_id == agent_id)
        stmt = (
            select(tbl)
            .where(and_(*clauses))
            .order_by(desc(tbl.c.created_at))
            .limit(limit)
        )
        with self.connect() as conn:
            return [dict(r._mapping) for r in conn.execute(stmt).fetchall()]

    # ------------------------------------------------------------------
    # 10. save_episodic_memory
    # ------------------------------------------------------------------

    def save_episodic_memory(self, values: dict[str, Any]) -> None:
        with self.connect() as conn:
            conn.execute(insert(agent_episodic_memory).values(**values))

    # ------------------------------------------------------------------
    # 11. list_episodic_memory
    # ------------------------------------------------------------------

    def list_episodic_memory(
        self,
        session_id: str,
        entity_id: str,
        *,
        limit: int = 6,
    ) -> list[dict[str, Any]]:
        """Return episodic memories for an agent, ordered by recency and salience."""
        tbl = agent_episodic_memory
        stmt = (
            select(tbl)
            .where(
                and_(
                    tbl.c.session_id == session_id,
                    tbl.c.agent_id == entity_id,
                )
            )
            .order_by(desc(tbl.c.updated_at), desc(tbl.c.salience))
            .limit(limit)
        )
        with self.connect() as conn:
            return [dict(r._mapping) for r in conn.execute(stmt).fetchall()]

    # ------------------------------------------------------------------
    # 12. log_relation_state
    # ------------------------------------------------------------------

    def log_relation_state(self, values: dict[str, Any]) -> None:
        with self.connect() as conn:
            conn.execute(insert(relation_state_log).values(**values))

    # ------------------------------------------------------------------
    # 13. list_relation_states
    # ------------------------------------------------------------------

    def list_relation_states(
        self,
        session_id: str,
        *,
        limit: int = 50,
    ) -> list[dict[str, Any]]:
        tbl = relation_state_log
        stmt = (
            select(tbl)
            .where(tbl.c.session_id == session_id)
            .order_by(desc(tbl.c.created_at))
            .limit(limit)
        )
        with self.connect() as conn:
            return [dict(r._mapping) for r in conn.execute(stmt).fetchall()]
