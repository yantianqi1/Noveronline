"""Migrate legacy seed JSON blobs into unified tables.

Scope note (2026-04-17):
    ``project.json`` maps to ``project_meta.project_json`` so runtime project
    metadata can be DB-only.
    ``chapter_segments.json`` maps to ``chapter_content`` + ``chapter_meta``;
    ``chapter_continuity.json`` fills chapter anchors/summaries and project
    continuity settings.
    ``story_memory.json`` world rules map to ``world_rule_evidence``.
    ``story_memory.json`` open threads map to ``plot_threads``.
    ``story_memory.json`` relationship ledger maps to ``relationships``.
    ``story_memory.json`` event timeline maps to ``world_events``.
    ``consistency_report.json`` conflicts / ambiguities map to
    ``consistency_notes``.
    ``reviewer_rules.json`` maps to
    ``project_meta.project_json.settings.reviewer_rules``.
    ``parallel_world_config.json`` maps to
    ``project_meta.project_json.settings.parallel_world_config``.
    ``agent_profiles.json`` maps to structured ``entities`` /
    ``entity_aliases`` profile fields.
    The remaining per-project JSON files (``seed_analysis.json`` /
    ``ontology.json`` / ``agent_profiles.json`` / ``reviewer_rules.json``
    / ``story_memory.json`` / ``reading_notes.json`` /
    ``chapter_continuity.json`` / ``consistency_report.json`` /
    ``narrative_archives.json`` / ``chapter_cards.json`` etc.) are also
    mirrored verbatim into ``project_artifacts`` as TEXT JSON keyed by
    ``(project_id, artifact_key)``. Phase G / Task 8 uses this table as
    the runtime read source.

    ``extracted_text.txt`` maps to ``project_artifacts`` key
    ``extracted_text`` as a JSON string.
"""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from sqlalchemy import and_, delete, insert, select, update

from app.services.agent_profile_persister import AgentProfilePersister
from app.tables.novel import (
    chapter_content,
    chapter_meta,
    consistency_notes,
    plot_threads,
    project_artifacts,
    project_meta,
    relationships,
    world_events,
    world_rule_evidence,
)

from .base import BaseDomainMigrator, MigrationContext

# project.json stores the Project model and is migrated to project_meta,
# not mirrored as a project_artifacts row.
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
        n_project_meta = self._migrate_project_meta(ctx)
        if n_project_meta:
            counts["project_meta"] = n_project_meta
        n_chapters = self._migrate_chapter_segments(ctx)
        if n_chapters:
            counts["chapter_content"] = n_chapters
            counts["chapter_meta"] = n_chapters
        n_world_rules = self._migrate_story_memory_world_rules(ctx)
        if n_world_rules:
            counts["world_rule_evidence"] = n_world_rules
        n_open_threads = self._migrate_story_memory_open_threads(ctx)
        if n_open_threads:
            counts["plot_threads"] = n_open_threads
        n_relationships = self._migrate_story_memory_relationships(ctx)
        if n_relationships:
            counts["relationships"] = n_relationships
        n_events = self._migrate_story_memory_events(ctx)
        if n_events:
            counts["world_events"] = n_events
        n_consistency_notes = self._migrate_consistency_report_notes(ctx)
        if n_consistency_notes:
            counts["consistency_notes"] = n_consistency_notes
        n_project_settings = (
            self._migrate_reviewer_rules_setting(ctx)
            + self._migrate_parallel_world_config_setting(ctx)
            + self._migrate_chapter_continuity_setting(ctx)
        )
        if n_project_settings:
            counts["project_settings"] = n_project_settings
        n_agent_profiles = self._migrate_agent_profiles(ctx)
        if n_agent_profiles:
            counts["agent_profiles"] = n_agent_profiles
        n_artifacts = self._migrate_project_artifacts(ctx)
        if n_artifacts:
            counts["project_artifacts"] = n_artifacts
        return counts

    def _migrate_project_meta(self, ctx: MigrationContext) -> int:
        project_id = ctx.project_id
        assert project_id is not None
        source = ctx.upload_root / "projects" / project_id / "project.json"
        payload = _load_json(source)
        if not payload:
            return 0
        payload = {"project_id": project_id, **payload}
        if ctx.dry_run:
            return 1

        now = _now_iso()
        row = {
            "project_id": project_id,
            "project_json": json.dumps(payload, ensure_ascii=False),
            "updated_at": payload.get("updated_at") or now,
        }
        with ctx.engine.begin() as conn:
            existing = conn.execute(
                select(project_meta.c.project_id)
                .where(project_meta.c.project_id == project_id)
                .limit(1)
            ).fetchone()
            if existing:
                conn.execute(
                    update(project_meta)
                    .where(project_meta.c.project_id == project_id)
                    .values(project_json=row["project_json"], updated_at=row["updated_at"])
                )
            else:
                conn.execute(insert(project_meta).values(**row))
        return 1

    def _migrate_reviewer_rules_setting(self, ctx: MigrationContext) -> int:
        project_id = ctx.project_id
        assert project_id is not None
        source = ctx.upload_root / "projects" / project_id / "reviewer_rules.json"
        payload = _load_json(source)
        if not isinstance(payload, dict):
            return 0
        if ctx.dry_run:
            return 1

        now = _now_iso()
        reviewer_rules = dict(payload)
        reviewer_rules.setdefault("updated_at", now)
        with ctx.engine.begin() as conn:
            existing = conn.execute(
                select(project_meta.c.project_json)
                .where(project_meta.c.project_id == project_id)
                .limit(1)
            ).fetchone()
            if existing:
                try:
                    project_payload = json.loads(existing[0] or "{}")
                except json.JSONDecodeError:
                    project_payload = {}
            else:
                project_payload = {}
            if not isinstance(project_payload, dict):
                project_payload = {}
            project_payload.setdefault("project_id", project_id)
            settings = project_payload.get("settings")
            if not isinstance(settings, dict):
                settings = {}
                project_payload["settings"] = settings
            settings["reviewer_rules"] = reviewer_rules
            row = {
                "project_id": project_id,
                "project_json": json.dumps(project_payload, ensure_ascii=False),
                "updated_at": project_payload.get("updated_at") or now,
            }
            if existing:
                conn.execute(
                    update(project_meta)
                    .where(project_meta.c.project_id == project_id)
                    .values(project_json=row["project_json"], updated_at=row["updated_at"])
                )
            else:
                conn.execute(insert(project_meta).values(**row))
        return 1

    def _migrate_parallel_world_config_setting(self, ctx: MigrationContext) -> int:
        project_id = ctx.project_id
        assert project_id is not None
        source = ctx.upload_root / "projects" / project_id / "parallel_world_config.json"
        payload = _load_json(source)
        if not isinstance(payload, dict):
            return 0
        if ctx.dry_run:
            return 1

        now = _now_iso()
        with ctx.engine.begin() as conn:
            existing = conn.execute(
                select(project_meta.c.project_json)
                .where(project_meta.c.project_id == project_id)
                .limit(1)
            ).fetchone()
            if existing:
                try:
                    project_payload = json.loads(existing[0] or "{}")
                except json.JSONDecodeError:
                    project_payload = {}
            else:
                project_payload = {}
            if not isinstance(project_payload, dict):
                project_payload = {}
            project_payload.setdefault("project_id", project_id)
            settings = project_payload.get("settings")
            if not isinstance(settings, dict):
                settings = {}
                project_payload["settings"] = settings
            settings["parallel_world_config"] = dict(payload)
            row = {
                "project_id": project_id,
                "project_json": json.dumps(project_payload, ensure_ascii=False),
                "updated_at": project_payload.get("updated_at") or now,
            }
            if existing:
                conn.execute(
                    update(project_meta)
                    .where(project_meta.c.project_id == project_id)
                    .values(project_json=row["project_json"], updated_at=row["updated_at"])
                )
            else:
                conn.execute(insert(project_meta).values(**row))
        return 1

    def _migrate_agent_profiles(self, ctx: MigrationContext) -> int:
        project_id = ctx.project_id
        assert project_id is not None
        source = ctx.upload_root / "projects" / project_id / "agent_profiles.json"
        payload = _load_json(source)
        if not isinstance(payload, dict):
            return 0
        profiles = payload.get("profiles")
        if not isinstance(profiles, dict):
            return 0
        if ctx.dry_run:
            return sum(
                1
                for profile_key, profile in profiles.items()
                if isinstance(profile, dict)
                and (
                    str((profile.get("basic_info") or {}).get("name") or "").strip()
                    or str(profile_key or "").strip()
                )
            )

        result = AgentProfilePersister(ctx.engine).persist(project_id, payload)
        return int(result.get("profiles") or 0)

    def _migrate_chapter_continuity_setting(self, ctx: MigrationContext) -> int:
        project_id = ctx.project_id
        assert project_id is not None
        source = ctx.upload_root / "projects" / project_id / "chapter_continuity.json"
        payload = _load_json(source)
        if not isinstance(payload, dict):
            return 0
        global_summary = str(payload.get("global_summary") or "").strip()
        if not global_summary:
            return 0
        if ctx.dry_run:
            return 1

        now = _now_iso()
        with ctx.engine.begin() as conn:
            existing = conn.execute(
                select(project_meta.c.project_json)
                .where(project_meta.c.project_id == project_id)
                .limit(1)
            ).fetchone()
            if existing:
                try:
                    project_payload = json.loads(existing[0] or "{}")
                except json.JSONDecodeError:
                    project_payload = {}
            else:
                project_payload = {}
            if not isinstance(project_payload, dict):
                project_payload = {}
            project_payload.setdefault("project_id", project_id)
            settings = project_payload.get("settings")
            if not isinstance(settings, dict):
                settings = {}
                project_payload["settings"] = settings
            settings["chapter_continuity_summary"] = global_summary
            row = {
                "project_id": project_id,
                "project_json": json.dumps(project_payload, ensure_ascii=False),
                "updated_at": project_payload.get("updated_at") or now,
            }
            if existing:
                conn.execute(
                    update(project_meta)
                    .where(project_meta.c.project_id == project_id)
                    .values(project_json=row["project_json"], updated_at=row["updated_at"])
                )
            else:
                conn.execute(insert(project_meta).values(**row))
        return 1

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
        continuity_by_chapter = self._chapter_continuity_by_chapter(ctx)
        content_rows: list[dict[str, Any]] = []
        meta_rows: list[dict[str, Any]] = []
        for chapter in chapters:
            chapter_id = chapter.get("chapter_id")
            if not chapter_id:
                continue
            continuity = continuity_by_chapter.get(str(chapter_id), {})
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
                    "summary": str(
                        continuity.get("continuity_summary")
                        or chapter.get("summary")
                        or ""
                    ).strip(),
                    "outline_json": "[]",
                    "timeline_note": str(continuity.get("timeline_note") or "").strip(),
                    "open_threads_json": "[]",
                    "pov_character": None,
                    "key_events_json": json.dumps(
                        self._continuity_key_events(continuity),
                        ensure_ascii=False,
                    ),
                    "character_state_updates_json": "[]",
                    "relationship_updates_json": "[]",
                    "start_anchor": str(continuity.get("head_context") or "").strip(),
                    "end_anchor": self._continuity_tail_hook(continuity),
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

    def _chapter_continuity_by_chapter(self, ctx: MigrationContext) -> dict[str, dict[str, Any]]:
        project_id = ctx.project_id
        assert project_id is not None
        source = ctx.upload_root / "projects" / project_id / "chapter_continuity.json"
        payload = _load_json(source)
        if not isinstance(payload, dict):
            return {}
        chapters = payload.get("chapters")
        if not isinstance(chapters, list):
            return {}
        return {
            str(item.get("chapter_id") or "").strip(): item
            for item in chapters
            if isinstance(item, dict) and str(item.get("chapter_id") or "").strip()
        }

    def _continuity_key_events(self, continuity: dict[str, Any]) -> list[dict[str, str]]:
        events: list[dict[str, str]] = []
        for item in continuity.get("core_conflicts") or []:
            text = str(item or "").strip()
            if text:
                events.append({"summary": text})
        return events

    def _continuity_tail_hook(self, continuity: dict[str, Any]) -> str:
        tail_hooks = continuity.get("tail_hooks") or []
        if isinstance(tail_hooks, list):
            for item in reversed(tail_hooks):
                text = str(item or "").strip()
                if text:
                    return text
        return str(continuity.get("end_anchor") or "").strip()

    def _migrate_story_memory_world_rules(self, ctx: MigrationContext) -> int:
        project_id = ctx.project_id
        assert project_id is not None
        source = ctx.upload_root / "projects" / project_id / "story_memory.json"
        payload = _load_json(source)
        if not payload:
            return 0

        rules: list[str] = []
        seen: set[str] = set()
        for item in payload.get("world_rules") or []:
            text = str(item or "").strip()
            if not text or text in seen:
                continue
            seen.add(text)
            rules.append(text)
        if not rules:
            return 0
        if ctx.dry_run:
            return len(rules)

        prefix = f"{project_id}:story_memory_world_rule:"
        now = _now_iso()
        rows = [
            {
                "project_id": project_id,
                "evidence_id": f"{prefix}{index:04d}",
                "fact_text": text,
                "segment_id": "story_memory",
                "chapter_order": 0,
                "evidence_snippet": text,
                "created_at": now,
            }
            for index, text in enumerate(rules, start=1)
        ]

        with ctx.engine.begin() as conn:
            conn.execute(
                delete(world_rule_evidence).where(
                    and_(
                        world_rule_evidence.c.project_id == project_id,
                        world_rule_evidence.c.evidence_id.like(f"{prefix}%"),
                    )
                )
            )
            conn.execute(insert(world_rule_evidence), rows)
        return len(rows)

    def _migrate_story_memory_open_threads(self, ctx: MigrationContext) -> int:
        project_id = ctx.project_id
        assert project_id is not None
        source = ctx.upload_root / "projects" / project_id / "story_memory.json"
        payload = _load_json(source)
        if not payload:
            return 0

        threads: list[dict[str, str]] = []
        seen: set[str] = set()
        for item in payload.get("open_threads") or []:
            if isinstance(item, dict):
                thread_key = str(item.get("thread_key") or item.get("thread") or "").strip()
                summary = str(item.get("summary") or item.get("detail") or "").strip()
                status = str(item.get("status") or "open").strip() or "open"
                source_chapter = str(
                    item.get("source_chapter")
                    or item.get("chapter_order")
                    or item.get("chapter_id")
                    or ""
                ).strip()
            else:
                thread_key = str(item or "").strip()
                summary = thread_key
                status = "open"
                source_chapter = ""
            thread_key = thread_key or summary
            detail = summary or thread_key
            if not thread_key or thread_key in seen:
                continue
            seen.add(thread_key)
            threads.append(
                {
                    "thread_key": thread_key,
                    "detail": detail,
                    "status": status,
                    "source_chapter": source_chapter,
                }
            )
        if not threads:
            return 0
        if ctx.dry_run:
            return len(threads)

        prefix = f"{project_id}:story_memory_thread:"
        now = _now_iso()
        rows = [
            {
                "project_id": project_id,
                "thread_id": f"{prefix}{index:04d}",
                "thread_key": thread["thread_key"],
                "status": thread["status"],
                "detail": thread["detail"],
                "source_chapter": thread["source_chapter"],
                "created_at": now,
                "updated_at": now,
            }
            for index, thread in enumerate(threads, start=1)
        ]

        with ctx.engine.begin() as conn:
            conn.execute(
                delete(plot_threads).where(
                    and_(
                        plot_threads.c.project_id == project_id,
                        plot_threads.c.thread_id.like(f"{prefix}%"),
                    )
                )
            )
            conn.execute(insert(plot_threads), rows)
        return len(rows)

    def _migrate_story_memory_relationships(self, ctx: MigrationContext) -> int:
        project_id = ctx.project_id
        assert project_id is not None
        source = ctx.upload_root / "projects" / project_id / "story_memory.json"
        payload = _load_json(source)
        if not payload:
            return 0

        ledger: list[dict[str, str]] = []
        seen: set[tuple[str, str]] = set()
        for item in payload.get("relationship_ledger") or []:
            if not isinstance(item, dict):
                continue
            source_id = str(item.get("source") or item.get("source_id") or "").strip()
            target_id = str(item.get("target") or item.get("target_id") or "").strip()
            if not source_id or not target_id or (source_id, target_id) in seen:
                continue
            seen.add((source_id, target_id))
            change = self._latest_relationship_change(item)
            relation_type = str(
                item.get("relation_type")
                or item.get("relation")
                or change.get("change")
                or change.get("relation_type")
                or change.get("new_state")
                or "related"
            ).strip()
            description = str(item.get("description") or item.get("summary") or "").strip()
            if not description:
                evidence = change.get("evidence") or ""
                if isinstance(evidence, list):
                    description = "；".join(str(part).strip() for part in evidence if str(part).strip())
                else:
                    description = str(evidence or "").strip()
            ledger.append(
                {
                    "source_id": source_id,
                    "target_id": target_id,
                    "relation_type": relation_type or "related",
                    "description": description,
                }
            )
        if not ledger:
            return 0
        if ctx.dry_run:
            return len(ledger)

        prefix = f"{project_id}:story_memory_relationship:"
        now = _now_iso()
        rows = [
            {
                "project_id": project_id,
                "relation_id": f"{prefix}{index:04d}",
                "source_id": item["source_id"],
                "target_id": item["target_id"],
                "relation_type": item["relation_type"],
                "description": item["description"],
                "updated_at": now,
            }
            for index, item in enumerate(ledger, start=1)
        ]

        with ctx.engine.begin() as conn:
            conn.execute(
                delete(relationships).where(
                    and_(
                        relationships.c.project_id == project_id,
                        relationships.c.relation_id.like(f"{prefix}%"),
                    )
                )
            )
            conn.execute(insert(relationships), rows)
        return len(rows)

    def _latest_relationship_change(self, item: dict[str, Any]) -> dict[str, Any]:
        changes = item.get("changes") or []
        if isinstance(changes, list):
            for change in reversed(changes):
                if isinstance(change, dict):
                    return change
        return {}

    def _migrate_story_memory_events(self, ctx: MigrationContext) -> int:
        project_id = ctx.project_id
        assert project_id is not None
        source = ctx.upload_root / "projects" / project_id / "story_memory.json"
        payload = _load_json(source)
        if not payload:
            return 0

        events: list[dict[str, Any]] = []
        seen: set[str] = set()
        for item in payload.get("event_timeline") or []:
            if isinstance(item, dict):
                summary = str(item.get("summary") or item.get("title") or "").strip()
                event_key = str(item.get("event_id") or summary).strip()
                characters = item.get("characters") or item.get("driving_entities") or []
                step = self._story_event_step(item)
                event_type = str(item.get("event_type") or "story_memory_event").strip()
            else:
                summary = str(item or "").strip()
                event_key = summary
                characters = []
                step = 0
                event_type = "story_memory_event"
            if not summary or not event_key or event_key in seen:
                continue
            seen.add(event_key)
            events.append(
                {
                    "summary": summary,
                    "characters": [
                        str(character).strip()
                        for character in characters
                        if str(character).strip()
                    ]
                    if isinstance(characters, list)
                    else [],
                    "step": step,
                    "event_type": event_type or "story_memory_event",
                }
            )
        if not events:
            return 0
        if ctx.dry_run:
            return len(events)

        prefix = f"{project_id}:story_memory_event:"
        now = _now_iso()
        rows = [
            {
                "project_id": project_id,
                "event_id": f"{prefix}{index:04d}",
                "session_id": "seed_story_memory",
                "branch_id": "main",
                "step": int(event["step"] or 0),
                "title": str(event["summary"])[:80],
                "summary": event["summary"],
                "event_type": event["event_type"],
                "driving_entities_json": json.dumps(event["characters"], ensure_ascii=False),
                "state_changes_json": "[]",
                "status": "canon",
                "created_at": now,
            }
            for index, event in enumerate(events, start=1)
        ]

        with ctx.engine.begin() as conn:
            conn.execute(
                delete(world_events).where(
                    and_(
                        world_events.c.project_id == project_id,
                        world_events.c.event_id.like(f"{prefix}%"),
                    )
                )
            )
            conn.execute(insert(world_events), rows)
        return len(rows)

    def _story_event_step(self, item: dict[str, Any]) -> int:
        raw = item.get("chapter_order") or item.get("order") or item.get("step")
        if raw is None:
            raw = item.get("chapter_id") or ""
        try:
            return int(raw)
        except (TypeError, ValueError):
            digits = "".join(character for character in str(raw) if character.isdigit())
            return int(digits) if digits else 0

    def _migrate_consistency_report_notes(self, ctx: MigrationContext) -> int:
        project_id = ctx.project_id
        assert project_id is not None
        source = ctx.upload_root / "projects" / project_id / "consistency_report.json"
        payload = _load_json(source)
        if not payload:
            return 0

        notes: list[str] = []
        seen: set[str] = set()
        for conflict in payload.get("conflicts") or []:
            text = self._conflict_note_text(conflict)
            if text and text not in seen:
                seen.add(text)
                notes.append(text)
        for ambiguity in payload.get("ambiguities") or []:
            text = self._ambiguity_note_text(ambiguity)
            if text and text not in seen:
                seen.add(text)
                notes.append(text)
        if not notes:
            return 0
        if ctx.dry_run:
            return len(notes)

        prefix = f"{project_id}:consistency_report:"
        now = _now_iso()
        rows = [
            {
                "project_id": project_id,
                "note_id": f"{prefix}{index:04d}",
                "segment_id": "consistency_report",
                "chapter_order": 0,
                "note_text": text,
                "created_at": now,
            }
            for index, text in enumerate(notes, start=1)
        ]
        with ctx.engine.begin() as conn:
            conn.execute(
                delete(consistency_notes).where(
                    and_(
                        consistency_notes.c.project_id == project_id,
                        consistency_notes.c.note_id.like(f"{prefix}%"),
                    )
                )
            )
            conn.execute(insert(consistency_notes), rows)
        return len(rows)

    def _conflict_note_text(self, conflict: Any) -> str:
        if not isinstance(conflict, dict):
            return str(conflict or "").strip()
        name = str(conflict.get("name") or conflict.get("entity") or "").strip()
        kind = str(conflict.get("kind") or "consistency_conflict").strip()
        summary = str(conflict.get("summary") or conflict.get("note") or "").strip()
        evidence = conflict.get("evidence") or []
        if isinstance(evidence, list):
            evidence_text = "；".join(str(item).strip() for item in evidence if str(item).strip())
        else:
            evidence_text = str(evidence or "").strip()
        detail = summary or evidence_text or kind
        return f"{name}：{detail}" if name else detail

    def _ambiguity_note_text(self, ambiguity: Any) -> str:
        if not isinstance(ambiguity, dict):
            return str(ambiguity or "").strip()
        alias = str(ambiguity.get("alias") or "").strip()
        reason = str(ambiguity.get("reason") or "存在多个候选实体").strip()
        candidates = ambiguity.get("candidate_names") or []
        if isinstance(candidates, list):
            candidate_text = "、".join(str(item).strip() for item in candidates if str(item).strip())
        else:
            candidate_text = str(candidates or "").strip()
        if alias and candidate_text:
            return f"{alias} 的指代存在歧义：{reason} 候选：{candidate_text}"
        if alias:
            return f"{alias} 的指代存在歧义：{reason}"
        return reason

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
        text_path = project_dir / "extracted_text.txt"
        if ctx.dry_run:
            parseable_json_count = 0
            for path in artifact_paths:
                try:
                    json.loads(path.read_text(encoding="utf-8"))
                except (OSError, json.JSONDecodeError):
                    continue
                parseable_json_count += 1
            return parseable_json_count + (1 if text_path.is_file() else 0)

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
        if text_path.is_file():
            try:
                extracted_text = text_path.read_text(encoding="utf-8")
            except OSError:
                extracted_text = None
            if extracted_text is not None:
                rows.append(
                    {
                        "project_id": project_id,
                        "artifact_key": "extracted_text",
                        "payload_json": json.dumps(extracted_text, ensure_ascii=False),
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
