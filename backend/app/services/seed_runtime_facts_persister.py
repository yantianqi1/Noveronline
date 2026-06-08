"""Persist ReadingNotesManager runtime facts into structured novel tables."""

from __future__ import annotations

import json
import re
import uuid
from datetime import datetime, timezone
from typing import Any

from sqlalchemy import Engine

from ..database import get_engine
from ..repositories.entity_repo import EntityRepository
from ..repositories.event_repo import EventRepository
from ..repositories.narrative_repo import NarrativeRepository
from ..repositories.thread_repo import ThreadRepository
from ..repositories.world_rule_repo import WorldRuleRepository
from .reading_notes_manager import ReadingNotesManager


class SeedRuntimeFactsPersister:
    def __init__(self, engine: Engine | None = None):
        self.engine = engine or get_engine()
        self.entities = EntityRepository(self.engine)
        self.events = EventRepository(self.engine)
        self.narrative = NarrativeRepository(self.engine)
        self.threads = ThreadRepository(self.engine)
        self.world_rules = WorldRuleRepository(self.engine)

    def persist(self, project_id: str, manager: ReadingNotesManager) -> dict[str, int]:
        now = datetime.now(timezone.utc).isoformat()
        notes = manager.notes
        counts = {
            "plot_threads": self._persist_plot_threads(project_id, notes, now),
            "world_rules": self._persist_world_rules(project_id, notes, now),
            "character_events": self._persist_character_events(project_id, notes, now),
            "relationship_events": self._persist_relationship_events(project_id, notes, now),
            "consistency_notes": self._persist_consistency_notes(project_id, notes, now),
        }
        return counts

    def _persist_plot_threads(
        self, project_id: str, notes: dict[str, Any], now: str
    ) -> int:
        count = 0
        plot_state = notes.get("plot_state", {}) or {}
        entries = list(plot_state.get("open_threads", []) or [])
        entries.extend(plot_state.get("resolved_threads", []) or [])
        for entry in entries:
            if not isinstance(entry, dict):
                continue
            thread_key = self._text(entry.get("thread_key") or entry.get("thread"))
            if not thread_key:
                continue
            detail = self._text(entry.get("detail") or entry.get("summary")) or ""
            status = self._thread_status(entry.get("status"))
            thread_id = self._stable_id("thread", project_id, thread_key)
            self.threads.upsert_thread(
                project_id,
                {
                    "thread_id": thread_id,
                    "thread_key": thread_key,
                    "status": status,
                    "detail": detail,
                    "source_chapter": str(entry.get("source_chapter") or ""),
                    "created_at": now,
                    "updated_at": now,
                },
            )
            count += 1
        return count

    def _persist_world_rules(
        self, project_id: str, notes: dict[str, Any], now: str
    ) -> int:
        count = 0
        for entry in notes.get("core_facts", {}).get("world_rules", []) or []:
            if not isinstance(entry, dict):
                continue
            fact_text = self._text(entry.get("fact") or entry.get("fact_text"))
            if not fact_text:
                continue
            evidence = self._text(entry.get("evidence") or entry.get("evidence_snippet")) or ""
            self.world_rules.upsert_world_rule(
                project_id,
                {
                    "evidence_id": self._stable_id("rule", project_id, fact_text),
                    "fact_text": fact_text,
                    "segment_id": self._text(entry.get("segment_id")) or "",
                    "chapter_order": self._chapter_order(entry),
                    "evidence_snippet": evidence,
                    "created_at": now,
                },
            )
            count += 1
        return count

    def _persist_character_events(
        self, project_id: str, notes: dict[str, Any], now: str
    ) -> int:
        count = 0
        characters = notes.get("core_facts", {}).get("characters", {}) or {}
        for name, data in characters.items():
            if not isinstance(data, dict):
                continue
            entity = self.entities.get_entity_by_name(project_id, str(name))
            if not entity:
                continue
            segment_id = self._first_segment(data)
            for action in data.get("key_actions", []) or []:
                summary = self._text(action)
                if not summary:
                    continue
                self.events.log_character_event(
                    project_id,
                    {
                        "event_id": self._stable_id("char_event", project_id, entity["entity_id"], segment_id, summary),
                        "entity_id": entity["entity_id"],
                        "segment_id": segment_id,
                        "chapter_order": self._segment_order(segment_id),
                        "event_type": "action",
                        "summary": summary,
                        "detail_json": json.dumps({"source": "reading_notes"}, ensure_ascii=False),
                        "created_at": now,
                    },
                )
                count += 1
        return count

    def _persist_relationship_events(
        self, project_id: str, notes: dict[str, Any], now: str
    ) -> int:
        count = 0
        for entry in notes.get("relationship_graph", []) or []:
            if not isinstance(entry, dict):
                continue
            source_name = self._text(entry.get("source"))
            target_name = self._text(entry.get("target"))
            if not source_name or not target_name:
                continue
            source = self.entities.get_entity_by_name(project_id, source_name)
            target = self.entities.get_entity_by_name(project_id, target_name)
            if not source or not target:
                continue
            segment_id = self._text(entry.get("segment_id")) or ""
            relation_type = self._text(entry.get("relation") or entry.get("new_state")) or ""
            trigger = self._text(entry.get("trigger")) or ""
            evidence = self._text(entry.get("evidence")) or ""
            self.events.log_relationship_event(
                project_id,
                {
                    "event_id": self._stable_id(
                        "rel_event",
                        project_id,
                        source["entity_id"],
                        target["entity_id"],
                        segment_id,
                        relation_type,
                        trigger,
                    ),
                    "source_entity_id": source["entity_id"],
                    "target_entity_id": target["entity_id"],
                    "segment_id": segment_id,
                    "chapter_order": self._segment_order(segment_id),
                    "relation_type": relation_type,
                    "previous_state": self._text(entry.get("previous_state")) or "",
                    "new_state": relation_type,
                    "trigger_event": trigger,
                    "emotional_shift": "",
                    "power_shift": "",
                    "evidence": evidence,
                    "created_at": now,
                },
            )
            count += 1
        return count

    def _persist_consistency_notes(
        self, project_id: str, notes: dict[str, Any], now: str
    ) -> int:
        count = 0
        for entry in notes.get("core_facts", {}).get("consistency_notes", []) or []:
            if isinstance(entry, dict):
                note_text = self._text(entry.get("note") or entry.get("note_text"))
                segment_id = self._text(entry.get("segment_id")) or ""
            else:
                note_text = self._text(entry)
                segment_id = ""
            if not note_text:
                continue
            self.narrative.upsert_consistency_note(
                project_id,
                {
                    "note_id": self._stable_id("consistency", project_id, segment_id, note_text),
                    "segment_id": segment_id,
                    "chapter_order": self._segment_order(segment_id),
                    "note_text": note_text,
                    "created_at": now,
                },
            )
            count += 1
        return count

    @staticmethod
    def _thread_status(value: Any) -> str:
        status = str(value or "open").strip().lower()
        return {"opened": "open", "opening": "open"}.get(status, status or "open")

    @staticmethod
    def _first_segment(data: dict[str, Any]) -> str:
        segments = data.get("segments_seen", []) or []
        return str(segments[0]) if segments else ""

    def _chapter_order(self, entry: dict[str, Any]) -> int:
        value = entry.get("chapter_order") or entry.get("chapter")
        try:
            return int(value)
        except (TypeError, ValueError):
            return self._segment_order(self._text(entry.get("segment_id")) or "")

    @staticmethod
    def _segment_order(segment_id: str) -> int:
        matches = re.findall(r"\d+", segment_id or "")
        return int(matches[-1]) if matches else 0

    @staticmethod
    def _text(value: Any) -> str | None:
        if value is None:
            return None
        text = str(value).strip()
        return text or None

    @staticmethod
    def _stable_id(prefix: str, *parts: Any) -> str:
        raw = "|".join(str(part) for part in parts)
        return f"{prefix}_{uuid.uuid5(uuid.NAMESPACE_URL, raw).hex[:16]}"
