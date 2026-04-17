"""Migrate legacy seed JSON blobs into unified tables.

Scope note (2026-04-17):
    ``chapter_segments.json`` maps to ``chapter_content`` + ``chapter_meta``.
    The remaining per-project JSON files (``seed_analysis.json`` /
    ``ontology.json`` / ``agent_profiles.json`` / ``reviewer_rules.json``
    / ``story_memory.json`` / ``reading_notes.json`` /
    ``chapter_continuity.json`` / ``consistency_report.json`` /
    ``narrative_archives.json`` / ``chapter_cards.json`` etc.) are mirrored
    verbatim into ``project_artifacts`` as TEXT JSON keyed by
    ``(project_id, artifact_key)``. Phase G / Task 8 uses this table as
    the runtime read source.
"""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from sqlalchemy import and_, delete, insert, select, update

from app.tables.novel import chapter_content, chapter_meta, project_artifacts

from .base import BaseDomainMigrator, MigrationContext

# project.json stores the Project model (name/status/timestamps). It is
# not a semantic "artifact" and should stay on disk as the authoritative
# project record.
EXCLUDED_ARTIFACT_FILENAMES: frozenset[str] = frozenset({"project.json"})


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _load_json(path: Path) -> dict[str, Any] | None:
    if not path.exists():
        return None
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None


class SeedJsonDomainMigrator(BaseDomainMigrator):
    domain_name = "seed_json"
    is_project_scoped = True

    def migrate(self, ctx: MigrationContext) -> dict[str, int]:
        if not ctx.project_id:
            return {}
        counts: dict[str, int] = {}
        n_chapters = self._migrate_chapter_segments(ctx)
        if n_chapters:
            counts["chapter_content"] = n_chapters
            counts["chapter_meta"] = n_chapters
        n_artifacts = self._migrate_project_artifacts(ctx)
        if n_artifacts:
            counts["project_artifacts"] = n_artifacts
        return counts

    def _migrate_chapter_segments(self, ctx: MigrationContext) -> int:
        project_id = ctx.project_id
        assert project_id is not None
        source = ctx.upload_root / "projects" / project_id / "chapter_segments.json"
        payload = _load_json(source)
        if not payload:
            return 0
        chapters = payload.get("chapters") or []
        if not chapters:
            return 0
        if ctx.dry_run:
            return len(chapters)

        now = _now_iso()
        content_rows: list[dict[str, Any]] = []
        meta_rows: list[dict[str, Any]] = []
        for chapter in chapters:
            chapter_id = chapter.get("chapter_id")
            if not chapter_id:
                continue
            content_rows.append(
                {
                    "chapter_id": chapter_id,
                    "project_id": project_id,
                    "chapter_order": int(chapter.get("order") or 0),
                    "title": chapter.get("title") or "",
                    "content": chapter.get("content") or "",
                    "word_count": int(chapter.get("word_count") or 0),
                    "status": "seeded",
                    "created_at": now,
                    "updated_at": now,
                }
            )
            meta_rows.append(
                {
                    "chapter_id": chapter_id,
                    "project_id": project_id,
                    "updated_at": now,
                }
            )
        if not content_rows:
            return 0

        with ctx.engine.begin() as conn:
            conn.execute(delete(chapter_meta).where(chapter_meta.c.project_id == project_id))
            conn.execute(delete(chapter_content).where(chapter_content.c.project_id == project_id))
            conn.execute(insert(chapter_content), content_rows)
            conn.execute(insert(chapter_meta), meta_rows)
        return len(content_rows)

    def _migrate_project_artifacts(self, ctx: MigrationContext) -> int:
        project_id = ctx.project_id
        assert project_id is not None
        project_dir = ctx.upload_root / "projects" / project_id
        if not project_dir.is_dir():
            return 0
        artifact_paths = sorted(
            path
            for path in project_dir.glob("*.json")
            if path.is_file() and path.name not in EXCLUDED_ARTIFACT_FILENAMES
        )
        if not artifact_paths:
            return 0
        if ctx.dry_run:
            return len(artifact_paths)

        now = _now_iso()
        rows: list[dict[str, Any]] = []
        for path in artifact_paths:
            try:
                raw_text = path.read_text(encoding="utf-8")
            except OSError:
                continue
            # Validate parseability before writing (keep bad JSON on disk).
            try:
                json.loads(raw_text)
            except json.JSONDecodeError:
                continue
            artifact_key = path.stem
            rows.append(
                {
                    "project_id": project_id,
                    "artifact_key": artifact_key,
                    "payload_json": raw_text,
                    "created_at": now,
                    "updated_at": now,
                }
            )
        if not rows:
            return 0

        with ctx.engine.begin() as conn:
            for row in rows:
                existing = conn.execute(
                    select(project_artifacts.c.project_id)
                    .where(
                        and_(
                            project_artifacts.c.project_id == project_id,
                            project_artifacts.c.artifact_key == row["artifact_key"],
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
                                project_artifacts.c.artifact_key == row["artifact_key"],
                            )
                        )
                        .values(payload_json=row["payload_json"], updated_at=row["updated_at"])
                    )
                else:
                    conn.execute(insert(project_artifacts).values(**row))
        return len(rows)


__all__ = ["SeedJsonDomainMigrator", "EXCLUDED_ARTIFACT_FILENAMES"]
