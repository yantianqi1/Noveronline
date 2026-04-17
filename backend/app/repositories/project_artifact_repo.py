"""Project artifact key-value repository (Phase G / Task 8).

Backs ``project_artifacts`` — a per-project JSON blob store keyed by
``(project_id, artifact_key)``. Service code reads these entries instead
of opening filesystem JSON files under ``uploads/projects/<pid>/``.

Artifact keys are the legacy JSON filename without the ``.json``
extension (e.g. ``seed_analysis``, ``ontology``, ``agent_profiles``,
``reviewer_rules``, ``story_memory``, ``reading_notes``,
``chapter_segments``, ``chapter_continuity``, ``consistency_report``,
``narrative_archives``).
"""

from __future__ import annotations

import json
from datetime import datetime
from typing import Any

from sqlalchemy import Engine, and_, delete, insert, select, update

from app.tables.novel import project_artifacts

from .base import BaseRepository


def _now_iso() -> str:
    return datetime.now().isoformat()


def artifact_key_from_filename(filename: str) -> str:
    """Map a legacy JSON filename (``seed_analysis.json``) to its key."""
    name = str(filename or "").strip()
    if name.endswith(".json"):
        name = name[: -len(".json")]
    return name


class ProjectArtifactRepository(BaseRepository):
    def __init__(self, engine: Engine):
        super().__init__(engine)

    def save(self, project_id: str, artifact_key: str, payload: Any) -> None:
        """Upsert ``payload`` for ``(project_id, artifact_key)``.

        ``payload`` is serialized to JSON; ``None`` is stored as ``null``.
        """
        if not project_id:
            raise ValueError("project_id is required")
        if not artifact_key:
            raise ValueError("artifact_key is required")
        now = _now_iso()
        serialized = json.dumps(payload, ensure_ascii=False)
        with self.connect() as conn:
            existing = conn.execute(
                select(project_artifacts.c.project_id)
                .where(
                    and_(
                        project_artifacts.c.project_id == project_id,
                        project_artifacts.c.artifact_key == artifact_key,
                    )
                )
                .limit(1)
            ).fetchone()
            if existing:
                conn.execute(
                    update(project_artifacts)
                    .where(
                        and_(
                            project_artifacts.c.project_id == project_id,
                            project_artifacts.c.artifact_key == artifact_key,
                        )
                    )
                    .values(payload_json=serialized, updated_at=now)
                )
            else:
                conn.execute(
                    insert(project_artifacts).values(
                        project_id=project_id,
                        artifact_key=artifact_key,
                        payload_json=serialized,
                        created_at=now,
                        updated_at=now,
                    )
                )

    def load(self, project_id: str, artifact_key: str) -> Any | None:
        """Return the deserialized payload or ``None`` if missing."""
        if not project_id or not artifact_key:
            return None
        stmt = (
            select(project_artifacts.c.payload_json)
            .where(
                and_(
                    project_artifacts.c.project_id == project_id,
                    project_artifacts.c.artifact_key == artifact_key,
                )
            )
            .limit(1)
        )
        with self.connect() as conn:
            row = conn.execute(stmt).fetchone()
        if row is None:
            return None
        raw = row[0]
        if raw is None:
            return None
        return json.loads(raw)

    def list_keys(self, project_id: str) -> list[str]:
        if not project_id:
            return []
        stmt = (
            select(project_artifacts.c.artifact_key)
            .where(project_artifacts.c.project_id == project_id)
            .order_by(project_artifacts.c.artifact_key.asc())
        )
        with self.connect() as conn:
            rows = conn.execute(stmt).fetchall()
        return [row[0] for row in rows]

    def delete(self, project_id: str, artifact_key: str) -> int:
        if not project_id or not artifact_key:
            return 0
        stmt = delete(project_artifacts).where(
            and_(
                project_artifacts.c.project_id == project_id,
                project_artifacts.c.artifact_key == artifact_key,
            )
        )
        with self.connect() as conn:
            result = conn.execute(stmt)
        return result.rowcount or 0


__all__ = ["ProjectArtifactRepository", "artifact_key_from_filename"]
