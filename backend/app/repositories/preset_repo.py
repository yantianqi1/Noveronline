"""Writer preset repository."""

from __future__ import annotations

import uuid
from datetime import datetime, timezone
from typing import Any

from sqlalchemy import Engine, and_, delete, insert, or_, select, update

from app.tables.novel import writer_presets

from .base import ProjectScopedRepository


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


_UPDATABLE_COLS = {"name", "description", "system_prompt", "is_default"}


class PresetRepository(ProjectScopedRepository):
    """CRUD for writer presets (project-scoped or global)."""

    def __init__(self, engine: Engine):
        super().__init__(engine, writer_presets)

    # ------------------------------------------------------------------
    # Query
    # ------------------------------------------------------------------

    def list_presets(self, project_id: str) -> list[dict[str, Any]]:
        """Return presets owned by *project_id* plus global (project_id IS NULL)."""
        stmt = (
            select(writer_presets)
            .where(
                or_(
                    writer_presets.c.project_id == project_id,
                    writer_presets.c.project_id.is_(None),
                )
            )
            .order_by(writer_presets.c.created_at)
        )
        with self.connect() as conn:
            return [dict(row._mapping) for row in conn.execute(stmt).fetchall()]

    # ------------------------------------------------------------------
    # Write
    # ------------------------------------------------------------------

    def create_preset(
        self,
        project_id: str,
        preset_id: str | None = None,
        *,
        name: str,
        system_prompt: str,
        description: str = "",
        is_default: int = 0,
    ) -> dict[str, Any]:
        """Insert a new writer preset. Returns the created row as dict."""
        if not preset_id:
            preset_id = f"preset_{uuid.uuid4().hex[:12]}"
        now = _now()
        with self.connect() as conn:
            conn.execute(
                insert(writer_presets).values(
                    preset_id=preset_id,
                    project_id=project_id,
                    name=name,
                    description=description,
                    system_prompt=system_prompt,
                    is_default=is_default,
                    created_at=now,
                    updated_at=now,
                )
            )
        return {
            "preset_id": preset_id,
            "project_id": project_id,
            "name": name,
            "description": description,
            "system_prompt": system_prompt,
            "is_default": is_default,
            "created_at": now,
            "updated_at": now,
        }

    def update_preset(
        self, project_id: str, preset_id: str, **kwargs: Any
    ) -> bool:
        """Update allowed columns on an existing preset. Returns True if a row was matched."""
        updates = {k: v for k, v in kwargs.items() if k in _UPDATABLE_COLS}
        if not updates:
            return False
        updates["updated_at"] = _now()
        stmt = (
            update(writer_presets)
            .where(
                and_(
                    writer_presets.c.preset_id == preset_id,
                    or_(
                        writer_presets.c.project_id == project_id,
                        writer_presets.c.project_id.is_(None),
                    ),
                )
            )
            .values(**updates)
        )
        with self.connect() as conn:
            result = conn.execute(stmt)
            return (result.rowcount or 0) > 0

    def delete_preset(self, project_id: str, preset_id: str) -> int:
        """Delete a preset by preset_id."""
        stmt = delete(writer_presets).where(writer_presets.c.preset_id == preset_id)
        with self.connect() as conn:
            result = conn.execute(stmt)
            return result.rowcount or 0
