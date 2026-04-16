"""Project metadata and sessions repository."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from sqlalchemy import Engine, and_, select, update

from app.tables.novel import project_meta, sessions

from .base import ProjectScopedRepository


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


class MetaRepository(ProjectScopedRepository):
    def __init__(self, engine: Engine):
        super().__init__(engine, project_meta)
        self.sessions_tbl = ProjectScopedRepository(engine, sessions)

    # ------------------------------------------------------------------
    # Project meta (legacy convenience)
    # ------------------------------------------------------------------

    def get_project_meta(self, project_id: str) -> dict[str, Any] | None:
        """Return the full project_meta row."""
        return self.get_one(project_id)

    def set_project_meta(self, project_id: str, values: dict[str, Any]) -> None:
        """Upsert project_meta keyed by project_id."""
        self.upsert_by_keys(project_id, values, ("project_id",))

    # ------------------------------------------------------------------
    # Generic key-value on project_meta
    # ------------------------------------------------------------------

    def get_meta(self, project_id: str, key: str) -> Any | None:
        """Retrieve a single column value from project_meta.

        *key* must be a valid column name on the project_meta table
        (e.g. ``narrative_phase``, ``total_segments``).
        Returns None if the project row does not exist or the column is NULL.
        """
        if key not in project_meta.c:
            return None
        stmt = (
            select(project_meta.c[key])
            .where(project_meta.c.project_id == project_id)
            .limit(1)
        )
        with self.connect() as conn:
            row = conn.execute(stmt).fetchone()
            return row[0] if row else None

    def set_meta(self, project_id: str, key: str, value: Any) -> None:
        """Set a single column on project_meta, upserting the row if needed.

        *key* must be a valid column name.
        """
        if key not in project_meta.c:
            raise ValueError(f"Unknown project_meta column: {key}")
        self.upsert_by_keys(
            project_id,
            {key: value, "updated_at": _now()},
            ("project_id",),
        )

    # ------------------------------------------------------------------
    # Sessions
    # ------------------------------------------------------------------

    def list_sessions(self, project_id: str) -> list[dict[str, Any]]:
        """List all sessions for a project, ordered by creation time."""
        stmt = (
            select(sessions)
            .where(sessions.c.project_id == project_id)
            .order_by(sessions.c.created_at.desc())
        )
        with self.connect() as conn:
            return [dict(row._mapping) for row in conn.execute(stmt).fetchall()]

    def get_session(
        self, project_id: str, session_id: str
    ) -> dict[str, Any] | None:
        """Get a single session by session_id."""
        return self.sessions_tbl.get_one(project_id, session_id=session_id)
