"""章节卡存储与连续性读取服务。"""

from __future__ import annotations

import json
import logging
from datetime import datetime
from typing import Any, Dict, Iterable, List, Optional, Sequence

from ..models.project import ProjectManager
from .chapter_meta_storage import ChapterMetaStorage

logger = logging.getLogger(__name__)

PREV_CHAPTER_ENDING_LENGTH = 600
SUMMARY_LOOKBACK_COUNT = 3


def _now() -> str:
    return datetime.now().isoformat(timespec="seconds")


class ChapterMetaService:
    """管理章节卡头信息与可检索历史项。"""

    def __init__(self, storage: Optional[ChapterMetaStorage] = None):
        self.storage = storage or ChapterMetaStorage()

    def save_chapter_summary(
        self,
        project_id: str,
        chapter_index: int,
        summary_text: str,
        chapter_id: str = "",
        title: str = "",
        open_threads: Optional[List[str]] = None,
        timeline_note: str = "",
    ) -> None:
        card = {
            "chapter_id": chapter_id or f"chapter_{int(chapter_index):04d}",
            "chapter_order": int(chapter_index),
            "title": title,
            "summary_text": summary_text,
            "start_anchor": "",
            "end_anchor": "",
            "key_events": [{"summary": summary_text}] if summary_text else [],
            "open_threads": [
                {"thread_key": item, "summary": item}
                for item in (open_threads or [])
                if str(item or "").strip()
            ],
            "character_state_updates": [],
            "relationship_updates": [],
            "timeline_note": timeline_note,
            "key_entities": [],
        }
        self.upsert_chapter_card(project_id, card)

    def replace_project_chapter_cards(
        self,
        project_id: str,
        chapter_cards: Sequence[Dict[str, Any]],
        world_rules: Optional[Sequence[str]] = None,
    ) -> None:
        cards = [self._normalize_card(card) for card in chapter_cards]
        with self.storage.connect() as conn:
            conn.execute("DELETE FROM chapter_meta WHERE project_id = ?", (project_id,))
            conn.execute("DELETE FROM chapter_history_item WHERE project_id = ?", (project_id,))
            for card in cards:
                self._write_card(conn, project_id, card)
            self._sync_world_rules(conn, project_id, world_rules or [])
            conn.commit()

    def upsert_chapter_card(
        self,
        project_id: str,
        chapter_card: Dict[str, Any],
        world_rules: Optional[Sequence[str]] = None,
    ) -> None:
        card = self._normalize_card(chapter_card)
        with self.storage.connect() as conn:
            self._write_card(conn, project_id, card)
            if world_rules is not None:
                self._sync_world_rules(conn, project_id, world_rules)
            conn.commit()

    def get_chapter_summaries(
        self,
        project_id: str,
        from_index: int = 0,
        to_index: Optional[int] = None,
    ) -> List[Dict[str, Any]]:
        query = [
            "SELECT * FROM chapter_meta",
            "WHERE project_id = ? AND chapter_order >= ?",
        ]
        params: list[Any] = [project_id, int(from_index)]
        if to_index is not None:
            query.append("AND chapter_order <= ?")
            params.append(int(to_index))
        query.append("ORDER BY chapter_order ASC")
        with self.storage.connect() as conn:
            rows = conn.execute(" ".join(query), params).fetchall()
        return [self._meta_row_to_dict(row) for row in rows]

    def get_single_summary(self, project_id: str, chapter_index: int) -> Optional[Dict[str, Any]]:
        with self.storage.connect() as conn:
            row = conn.execute(
                "SELECT * FROM chapter_meta WHERE project_id = ? AND chapter_order = ?",
                (project_id, int(chapter_index)),
            ).fetchone()
        return self._meta_row_to_dict(row) if row else None

    def get_recent_chapter_anchors(
        self,
        project_id: str,
        current_chapter_order: int,
        limit: int = SUMMARY_LOOKBACK_COUNT,
    ) -> List[Dict[str, Any]]:
        with self.storage.connect() as conn:
            rows = conn.execute(
                """
                SELECT * FROM chapter_meta
                WHERE project_id = ? AND chapter_order < ?
                ORDER BY chapter_order DESC
                LIMIT ?
                """,
                (project_id, int(current_chapter_order), int(limit)),
            ).fetchall()
        anchors = [self._meta_row_to_dict(row) for row in reversed(rows)]
        return [
            {
                "chapter_order": item["chapter_order"],
                "chapter_id": item["chapter_id"],
                "title": item["title"],
                "summary_text": item["summary_text"],
                "start_anchor": item["start_anchor"],
                "end_anchor": item["end_anchor"],
                "timeline_note": item["timeline_note"],
            }
            for item in anchors
        ]

    def get_history_items(self, project_id: str, current_chapter_order: int) -> List[Dict[str, Any]]:
        with self.storage.connect() as conn:
            rows = conn.execute(
                """
                SELECT * FROM chapter_history_item
                WHERE project_id = ? AND chapter_order < ? AND item_type != 'world_rule'
                ORDER BY chapter_order DESC, id ASC
                """,
                (project_id, int(current_chapter_order)),
            ).fetchall()
        return [self._history_row_to_dict(row) for row in rows]

    def get_world_rules(self, project_id: str) -> List[str]:
        with self.storage.connect() as conn:
            rows = conn.execute(
                """
                SELECT summary_text FROM chapter_history_item
                WHERE project_id = ? AND item_type = 'world_rule'
                ORDER BY id ASC
                """,
                (project_id,),
            ).fetchall()
        if rows:
            return [str(row["summary_text"] or "").strip() for row in rows if str(row["summary_text"] or "").strip()]
        story_memory = ProjectManager.load_project_json(project_id, "story_memory.json") or {}
        return [str(item or "").strip() for item in story_memory.get("world_rules", []) if str(item or "").strip()]

    def get_chapter_continuity_context(
        self,
        project_id: str,
        current_chapter_order: int,
    ) -> Dict[str, Any]:
        anchors = self.get_recent_chapter_anchors(project_id, current_chapter_order, SUMMARY_LOOKBACK_COUNT)
        return {
            "continuity_anchor": {
                "prev_chapter_ending": self._get_prev_chapter_ending(project_id, current_chapter_order),
                "chapter_summaries": [self._continuity_summary(item) for item in anchors],
                "open_threads": self._recent_open_threads(project_id, current_chapter_order),
                "timeline_note": anchors[-1]["timeline_note"] if anchors else "",
            }
        }

    def _write_card(self, conn, project_id: str, card: Dict[str, Any]) -> None:
        now = _now()
        conn.execute(
            """
            INSERT INTO chapter_meta
                (project_id, chapter_order, chapter_id, title, summary_text, timeline_note,
                 start_anchor, end_anchor, open_threads_json, created_at, updated_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(project_id, chapter_order) DO UPDATE SET
                chapter_id = excluded.chapter_id,
                title = excluded.title,
                summary_text = excluded.summary_text,
                timeline_note = excluded.timeline_note,
                start_anchor = excluded.start_anchor,
                end_anchor = excluded.end_anchor,
                open_threads_json = excluded.open_threads_json,
                updated_at = excluded.updated_at
            """,
            (
                project_id,
                card["chapter_order"],
                card["chapter_id"],
                card["title"],
                card["summary_text"],
                card["timeline_note"],
                card["start_anchor"],
                card["end_anchor"],
                json.dumps(self._open_thread_summaries(card["open_threads"]), ensure_ascii=False),
                now,
                now,
            ),
        )
        conn.execute(
            "DELETE FROM chapter_history_item WHERE project_id = ? AND chapter_order = ?",
            (project_id, card["chapter_order"]),
        )
        for item in self._card_history_items(project_id, card):
            conn.execute(
                """
                INSERT INTO chapter_history_item
                    (project_id, chapter_order, chapter_id, item_type, subject_key,
                     summary_text, related_entities_json, thread_key, source_kind,
                     source_ref, created_at, updated_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    project_id,
                    item["chapter_order"],
                    item["chapter_id"],
                    item["item_type"],
                    item["subject_key"],
                    item["summary_text"],
                    json.dumps(item["related_entities"], ensure_ascii=False),
                    item["thread_key"],
                    item["source_kind"],
                    item["source_ref"],
                    now,
                    now,
                ),
            )

    def _sync_world_rules(self, conn, project_id: str, world_rules: Sequence[str]) -> None:
        conn.execute(
            "DELETE FROM chapter_history_item WHERE project_id = ? AND item_type = 'world_rule'",
            (project_id,),
        )
        now = _now()
        for index, rule in enumerate(world_rules, start=1):
            text = str(rule or "").strip()
            if not text:
                continue
            conn.execute(
                """
                INSERT INTO chapter_history_item
                    (project_id, chapter_order, chapter_id, item_type, subject_key,
                     summary_text, related_entities_json, thread_key, source_kind,
                     source_ref, created_at, updated_at)
                VALUES (?, 0, '', 'world_rule', '', ?, '[]', '', 'story_memory', ?, ?, ?)
                """,
                (project_id, text, f"world_rule:{index}", now, now),
            )

    def _card_history_items(self, project_id: str, card: Dict[str, Any]) -> List[Dict[str, Any]]:
        entities = self._entity_names(card)
        items = [
            self._history_item(card, "summary", card["chapter_id"], card["summary_text"], entities, "", "chapter_card", card["chapter_id"]),
        ]
        items.extend(
            self._history_item(card, "event", f"{card['chapter_id']}:event:{index}", item["summary"], entities, "", "chapter_card", f"{card['chapter_id']}:event:{index}")
            for index, item in enumerate(card["key_events"], start=1)
        )
        items.extend(
            self._history_item(card, "open_thread", item["thread_key"], item["summary"], entities, item["thread_key"], "chapter_card", f"{card['chapter_id']}:thread:{item['thread_key']}")
            for item in card["open_threads"]
        )
        items.extend(
            self._history_item(card, "relationship", f"{item['source']}::{item['target']}", item["summary"], [item["source"], item["target"]], "", "chapter_card", f"{card['chapter_id']}:relationship:{index}")
            for index, item in enumerate(card["relationship_updates"], start=1)
        )
        return items

    def _history_item(
        self,
        card: Dict[str, Any],
        item_type: str,
        subject_key: str,
        summary_text: str,
        related_entities: Iterable[str],
        thread_key: str,
        source_kind: str,
        source_ref: str,
    ) -> Dict[str, Any]:
        return {
            "chapter_order": card["chapter_order"],
            "chapter_id": card["chapter_id"],
            "item_type": item_type,
            "subject_key": subject_key,
            "summary_text": summary_text,
            "related_entities": [item for item in related_entities if item],
            "thread_key": thread_key,
            "source_kind": source_kind,
            "source_ref": source_ref,
        }

    def _recent_open_threads(self, project_id: str, current_chapter_order: int) -> List[str]:
        start_order = int(current_chapter_order) - SUMMARY_LOOKBACK_COUNT
        with self.storage.connect() as conn:
            rows = conn.execute(
                """
                SELECT summary_text FROM chapter_history_item
                WHERE project_id = ? AND item_type = 'open_thread'
                  AND chapter_order >= ? AND chapter_order < ?
                ORDER BY chapter_order ASC, id ASC
                """,
                (project_id, start_order, int(current_chapter_order)),
            ).fetchall()
        seen: List[str] = []
        for row in rows:
            text = str(row["summary_text"] or "").strip()
            if text and text not in seen:
                seen.append(text)
        return seen

    def _get_prev_chapter_ending(self, project_id: str, current_chapter_order: int) -> str:
        if int(current_chapter_order) <= 1:
            return ""
        chapters = (ProjectManager.load_project_json(project_id, "chapter_segments.json") or {}).get("chapters", [])
        prev_order = int(current_chapter_order) - 1
        for chapter in chapters:
            if int(chapter.get("order") or 0) != prev_order:
                continue
            text = str(chapter.get("content") or chapter.get("text") or "").strip()
            return text[-PREV_CHAPTER_ENDING_LENGTH:] if text else ""
        return ""

    def _normalize_card(self, card: Dict[str, Any]) -> Dict[str, Any]:
        chapter_order = int(card.get("chapter_order") or card.get("order") or 0)
        chapter_id = str(card.get("chapter_id") or "").strip()
        title = str(card.get("title") or chapter_id or f"第{chapter_order}章").strip()
        return {
            "chapter_id": chapter_id,
            "chapter_order": chapter_order,
            "title": title,
            "summary_text": str(card.get("summary_text") or "").strip(),
            "timeline_note": str(card.get("timeline_note") or "").strip(),
            "start_anchor": str(card.get("start_anchor") or "").strip(),
            "end_anchor": str(card.get("end_anchor") or "").strip(),
            "open_threads": [item for item in card.get("open_threads", []) if isinstance(item, dict)],
            "key_events": [item for item in card.get("key_events", []) if isinstance(item, dict)],
            "relationship_updates": [item for item in card.get("relationship_updates", []) if isinstance(item, dict)],
            "key_entities": [item for item in card.get("key_entities", []) if isinstance(item, dict)],
            "character_state_updates": [
                item for item in card.get("character_state_updates", []) if isinstance(item, dict)
            ],
        }

    def _entity_names(self, card: Dict[str, Any]) -> List[str]:
        names = [str(item.get("name") or "").strip() for item in card.get("key_entities", [])]
        names.extend(str(item.get("name") or "").strip() for item in card.get("character_state_updates", []))
        deduped: List[str] = []
        for name in names:
            if name and name not in deduped:
                deduped.append(name)
        return deduped

    def _open_thread_summaries(self, open_threads: Sequence[Dict[str, Any]]) -> List[str]:
        items = []
        for item in open_threads:
            summary = str(item.get("summary") or item.get("thread_key") or "").strip()
            if summary and summary not in items:
                items.append(summary)
        return items

    def _continuity_summary(self, item: Dict[str, Any]) -> Dict[str, Any]:
        return {
            "chapter_order": item["chapter_order"],
            "chapter_index": item["chapter_order"],
            "chapter_id": item["chapter_id"],
            "title": item["title"],
            "summary": item["summary_text"],
            "start_anchor": item["start_anchor"],
            "end_anchor": item["end_anchor"],
        }

    def _meta_row_to_dict(self, row) -> Dict[str, Any]:
        open_threads = json.loads(row["open_threads_json"] or "[]")
        if open_threads and isinstance(open_threads[0], dict):
            open_threads = self._open_thread_summaries(open_threads)
        return {
            "id": row["id"],
            "project_id": row["project_id"],
            "chapter_order": row["chapter_order"],
            "chapter_index": row["chapter_order"],
            "chapter_id": row["chapter_id"],
            "title": row["title"],
            "summary_text": row["summary_text"],
            "timeline_note": row["timeline_note"],
            "start_anchor": row["start_anchor"],
            "end_anchor": row["end_anchor"],
            "open_threads": open_threads,
            "created_at": row["created_at"],
            "updated_at": row["updated_at"],
        }

    def _history_row_to_dict(self, row) -> Dict[str, Any]:
        return {
            "id": row["id"],
            "project_id": row["project_id"],
            "chapter_order": row["chapter_order"],
            "chapter_id": row["chapter_id"],
            "item_type": row["item_type"],
            "subject_key": row["subject_key"],
            "summary_text": row["summary_text"],
            "related_entities": json.loads(row["related_entities_json"] or "[]"),
            "thread_key": row["thread_key"],
            "source_kind": row["source_kind"],
            "source_ref": row["source_ref"],
        }
