"""Migrate legacy seed JSON blobs into unified tables.

Scope note (2026-04-17):
    Only ``chapter_segments.json`` has a fully defined mapping today
    (``chapter_content`` + ``chapter_meta``). ``seed_analysis.json`` /
    ``ontology.json`` / ``agent_profiles.json`` / ``narrative_archives.json``
    have no corresponding unified-table columns yet — their mapping is
    owned by Phase G / Task 8. Placeholder methods exist below so new
    mappings can land incrementally without touching the orchestrator.
"""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from sqlalchemy import delete, insert

from app.tables.novel import chapter_content, chapter_meta

from .base import BaseDomainMigrator, MigrationContext


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


__all__ = ["SeedJsonDomainMigrator"]
