"""Outline repository."""

from __future__ import annotations

import uuid
from datetime import datetime, timezone
from typing import Any

from sqlalchemy import Engine, and_, delete, insert, select

from app.tables.novel import outline_versions

from .base import ProjectScopedRepository

_MAX_VERSIONS_PER_CHAPTER = 20


class OutlineRepository(ProjectScopedRepository):
    def __init__(self, engine: Engine):
        super().__init__(engine, outline_versions)

    # ------------------------------------------------------------------
    # save_outline_version
    # ------------------------------------------------------------------

    def save_outline_version(
        self,
        project_id: str,
        chapter_id: str,
        outline_json: str,
        label: str = "",
    ) -> str:
        """Create a new outline snapshot and prune excess versions.

        Returns the generated ``version_id``.
        """
        now = datetime.now(timezone.utc).isoformat()
        version_id = f"ov_{uuid.uuid4().hex[:12]}"

        with self.connect() as conn:
            conn.execute(
                insert(outline_versions).values(
                    version_id=version_id,
                    project_id=project_id,
                    chapter_id=chapter_id,
                    outline_json=outline_json,
                    label=label,
                    created_at=now,
                )
            )

            # prune: keep only the newest _MAX_VERSIONS_PER_CHAPTER entries
            all_ids = conn.execute(
                select(outline_versions.c.version_id)
                .where(
                    and_(
                        outline_versions.c.project_id == project_id,
                        outline_versions.c.chapter_id == chapter_id,
                    )
                )
                .order_by(outline_versions.c.created_at.desc())
            ).fetchall()

            if len(all_ids) > _MAX_VERSIONS_PER_CHAPTER:
                excess_ids = [row[0] for row in all_ids[_MAX_VERSIONS_PER_CHAPTER:]]
                conn.execute(
                    delete(outline_versions).where(
                        outline_versions.c.version_id.in_(excess_ids)
                    )
                )

        return version_id

    # ------------------------------------------------------------------
    # list_outline_versions (lightweight, no body)
    # ------------------------------------------------------------------

    def list_outline_versions(
        self, project_id: str, chapter_id: str
    ) -> list[dict[str, Any]]:
        """List version metadata for a chapter (no outline_json body)."""
        stmt = (
            select(
                outline_versions.c.version_id,
                outline_versions.c.chapter_id,
                outline_versions.c.label,
                outline_versions.c.created_at,
            )
            .where(
                and_(
                    outline_versions.c.project_id == project_id,
                    outline_versions.c.chapter_id == chapter_id,
                )
            )
            .order_by(outline_versions.c.created_at.desc())
        )
        with self.connect() as conn:
            return [dict(r._mapping) for r in conn.execute(stmt).fetchall()]

    # ------------------------------------------------------------------
    # get_outline_version
    # ------------------------------------------------------------------

    def get_outline_version(
        self, project_id: str, version_id: str
    ) -> dict[str, Any] | None:
        """Fetch a single outline version by its version_id (full row)."""
        return self.get_one(project_id, version_id=version_id)

    # ------------------------------------------------------------------
    # delete_outline_version
    # ------------------------------------------------------------------

    def delete_outline_version(self, project_id: str, version_id: str) -> int:
        """Delete a single outline version. Returns rows affected (0 or 1)."""
        return self.delete_one(project_id, version_id=version_id)
