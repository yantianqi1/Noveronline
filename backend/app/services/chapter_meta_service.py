"""章节卡存储与连续性读取服务。"""

from __future__ import annotations

import json
import logging
from datetime import datetime
from typing import Any, Dict, List, Optional, Sequence

from sqlalchemy import and_, delete, desc, insert, select, update

from ..database import get_engine
from ..models.project import ProjectManager
from ..repositories.chapter_repo import ChapterRepository
from ..tables.novel import chapter_content, chapter_meta

logger = logging.getLogger(__name__)

PREV_CHAPTER_ENDING_LENGTH = 600
SUMMARY_LOOKBACK_COUNT = 3


def _now() -> str:
    return datetime.now().isoformat(timespec="seconds")


class ChapterMetaService:
    """管理章节卡头信息与可检索历史项。"""

    def __init__(self, repo: Optional[ChapterRepository] = None):
        self._repo = repo or ChapterRepository(get_engine())

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
            "chapter_id": chapter_id or f"{project_id}_chapter_{int(chapter_index):04d}",
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
        cc = chapter_content
        cm = chapter_meta
        with self._repo.connect() as conn:
            # Delete existing chapter_meta and chapter_content for this project
            conn.execute(delete(cm).where(cm.c.project_id == project_id))
            conn.execute(delete(cc).where(cc.c.project_id == project_id))
            for card in cards:
                self._write_card(conn, project_id, card)
            conn.commit()

    def upsert_chapter_card(
        self,
        project_id: str,
        chapter_card: Dict[str, Any],
        world_rules: Optional[Sequence[str]] = None,
    ) -> None:
        card = self._normalize_card(chapter_card)
        with self._repo.connect() as conn:
            self._write_card(conn, project_id, card)

    def get_chapter_summaries(
        self,
        project_id: str,
        from_index: int = 0,
        to_index: Optional[int] = None,
    ) -> List[Dict[str, Any]]:
        cc = chapter_content
        cm = chapter_meta
        joined = cc.outerjoin(cm, cc.c.chapter_id == cm.c.chapter_id)
        clauses = [cc.c.project_id == project_id, cc.c.chapter_order >= int(from_index)]
        if to_index is not None:
            clauses.append(cc.c.chapter_order <= int(to_index))
        stmt = (
            select(cc, cm.c.summary, cm.c.timeline_note, cm.c.open_threads_json, cm.c.start_anchor, cm.c.end_anchor)
            .select_from(joined)
            .where(and_(*clauses))
            .order_by(cc.c.chapter_order.asc())
        )
        with self._repo.connect() as conn:
            rows = conn.execute(stmt).fetchall()
        return [self._joined_row_to_dict(row) for row in rows]

    def get_single_summary(self, project_id: str, chapter_index: int) -> Optional[Dict[str, Any]]:
        cc = chapter_content
        cm = chapter_meta
        joined = cc.outerjoin(cm, cc.c.chapter_id == cm.c.chapter_id)
        stmt = (
            select(cc, cm.c.summary, cm.c.timeline_note, cm.c.open_threads_json, cm.c.start_anchor, cm.c.end_anchor)
            .select_from(joined)
            .where(and_(cc.c.project_id == project_id, cc.c.chapter_order == int(chapter_index)))
            .limit(1)
        )
        with self._repo.connect() as conn:
            row = conn.execute(stmt).fetchone()
        return self._joined_row_to_dict(row) if row else None

    def get_recent_chapter_anchors(
        self,
        project_id: str,
        current_chapter_order: int,
        limit: int = SUMMARY_LOOKBACK_COUNT,
    ) -> List[Dict[str, Any]]:
        cc = chapter_content
        cm = chapter_meta
        joined = cc.outerjoin(cm, cc.c.chapter_id == cm.c.chapter_id)
        stmt = (
            select(cc, cm.c.summary, cm.c.timeline_note, cm.c.open_threads_json, cm.c.start_anchor, cm.c.end_anchor)
            .select_from(joined)
            .where(and_(cc.c.project_id == project_id, cc.c.chapter_order < int(current_chapter_order)))
            .order_by(desc(cc.c.chapter_order))
            .limit(int(limit))
        )
        with self._repo.connect() as conn:
            rows = conn.execute(stmt).fetchall()
        anchors = [self._joined_row_to_dict(row) for row in reversed(rows)]
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
        """Return history items from chapter_meta key_events as flattened items."""
        cc = chapter_content
        cm = chapter_meta
        joined = cc.outerjoin(cm, cc.c.chapter_id == cm.c.chapter_id)
        stmt = (
            select(cc.c.chapter_id, cc.c.chapter_order, cm.c.summary, cm.c.key_events_json, cm.c.open_threads_json, cm.c.relationship_updates_json)
            .select_from(joined)
            .where(and_(cc.c.project_id == project_id, cc.c.chapter_order < int(current_chapter_order)))
            .order_by(desc(cc.c.chapter_order))
        )
        with self._repo.connect() as conn:
            rows = conn.execute(stmt).fetchall()
        items: List[Dict[str, Any]] = []
        for row in rows:
            chapter_id = row.chapter_id
            chapter_order = row.chapter_order
            summary = row.summary or ""
            if summary:
                items.append({
                    "project_id": project_id,
                    "chapter_order": chapter_order,
                    "chapter_id": chapter_id,
                    "item_type": "summary",
                    "subject_key": chapter_id,
                    "summary_text": summary,
                    "related_entities": [],
                    "thread_key": "",
                    "source_kind": "chapter_card",
                    "source_ref": chapter_id,
                })
            for index, event in enumerate(json.loads(row.key_events_json or "[]"), start=1):
                if isinstance(event, dict):
                    items.append({
                        "project_id": project_id,
                        "chapter_order": chapter_order,
                        "chapter_id": chapter_id,
                        "item_type": "event",
                        "subject_key": f"{chapter_id}:event:{index}",
                        "summary_text": event.get("summary", ""),
                        "related_entities": [],
                        "thread_key": "",
                        "source_kind": "chapter_card",
                        "source_ref": f"{chapter_id}:event:{index}",
                    })
            for index, thread in enumerate(json.loads(row.open_threads_json or "[]"), start=1):
                if isinstance(thread, dict):
                    thread_key = thread.get("thread_key", "") or ""
                    summary_text = thread.get("summary", "") or thread_key
                elif isinstance(thread, str) and thread.strip():
                    thread_key = thread.strip()
                    summary_text = thread_key
                else:
                    continue
                items.append({
                    "project_id": project_id,
                    "chapter_order": chapter_order,
                    "chapter_id": chapter_id,
                    "item_type": "open_thread",
                    "subject_key": f"{chapter_id}:thread:{thread_key or index}",
                    "summary_text": summary_text,
                    "related_entities": [],
                    "thread_key": thread_key,
                    "source_kind": "chapter_card",
                    "source_ref": f"{chapter_id}:thread:{thread_key or index}",
                })
            for index, rel in enumerate(json.loads(row.relationship_updates_json or "[]"), start=1):
                if isinstance(rel, dict):
                    source = rel.get("source", "") or ""
                    target = rel.get("target", "") or ""
                    items.append({
                        "project_id": project_id,
                        "chapter_order": chapter_order,
                        "chapter_id": chapter_id,
                        "item_type": "relationship",
                        "subject_key": f"{chapter_id}:rel:{index}",
                        "summary_text": rel.get("summary", ""),
                        "related_entities": [name for name in (source, target) if name],
                        "thread_key": "",
                        "source_kind": "chapter_card",
                        "source_ref": f"{chapter_id}:rel:{index}",
                    })
        return items

    def get_world_rules(self, project_id: str) -> List[str]:
        """Return world rules from story_memory.json (legacy source)."""
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
        cid = card["chapter_id"]
        cc = chapter_content
        cm = chapter_meta
        # Upsert chapter_content
        existing = conn.execute(
            select(cc.c.chapter_id).where(and_(cc.c.project_id == project_id, cc.c.chapter_id == cid)).limit(1)
        ).fetchone()
        if existing:
            conn.execute(
                update(cc)
                .where(and_(cc.c.project_id == project_id, cc.c.chapter_id == cid))
                .values(
                    chapter_order=card["chapter_order"],
                    title=card["title"],
                    updated_at=now,
                )
            )
        else:
            conn.execute(
                insert(cc).values(
                    chapter_id=cid,
                    project_id=project_id,
                    chapter_order=card["chapter_order"],
                    title=card["title"],
                    content="",
                    word_count=0,
                    status="draft",
                    created_at=now,
                    updated_at=now,
                )
            )
        # Upsert chapter_meta
        existing_meta = conn.execute(
            select(cm.c.chapter_id).where(and_(cm.c.project_id == project_id, cm.c.chapter_id == cid)).limit(1)
        ).fetchone()
        meta_values = dict(
            summary=card["summary_text"],
            timeline_note=card["timeline_note"],
            start_anchor=card["start_anchor"],
            end_anchor=card["end_anchor"],
            open_threads_json=json.dumps(self._open_thread_summaries(card["open_threads"]), ensure_ascii=False),
            key_events_json=json.dumps(card.get("key_events", []), ensure_ascii=False),
            character_state_updates_json=json.dumps(card.get("character_state_updates", []), ensure_ascii=False),
            relationship_updates_json=json.dumps(card.get("relationship_updates", []), ensure_ascii=False),
            updated_at=now,
        )
        if existing_meta:
            conn.execute(
                update(cm).where(and_(cm.c.project_id == project_id, cm.c.chapter_id == cid)).values(**meta_values)
            )
        else:
            conn.execute(
                insert(cm).values(chapter_id=cid, project_id=project_id, **meta_values)
            )

    def _recent_open_threads(self, project_id: str, current_chapter_order: int) -> List[str]:
        start_order = int(current_chapter_order) - SUMMARY_LOOKBACK_COUNT
        cc = chapter_content
        cm = chapter_meta
        joined = cc.outerjoin(cm, cc.c.chapter_id == cm.c.chapter_id)
        stmt = (
            select(cm.c.open_threads_json)
            .select_from(joined)
            .where(and_(cc.c.project_id == project_id, cc.c.chapter_order >= start_order, cc.c.chapter_order < int(current_chapter_order)))
            .order_by(cc.c.chapter_order.asc())
        )
        with self._repo.connect() as conn:
            rows = conn.execute(stmt).fetchall()
        seen: List[str] = []
        for row in rows:
            threads = json.loads(row.open_threads_json or "[]") if row.open_threads_json else []
            for text in threads:
                text = str(text).strip() if not isinstance(text, dict) else str(text.get("summary", "")).strip()
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
            "chapter_id": chapter_id or f"chapter_{chapter_order:04d}",
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

    def _joined_row_to_dict(self, row) -> Dict[str, Any]:
        """Convert a chapter_content LEFT JOIN chapter_meta row to service dict."""
        m = row._mapping
        open_threads = json.loads(m.get("open_threads_json") or "[]")
        if open_threads and isinstance(open_threads[0], dict):
            open_threads = self._open_thread_summaries(open_threads)
        return {
            "project_id": m["project_id"],
            "chapter_order": m["chapter_order"],
            "chapter_index": m["chapter_order"],
            "chapter_id": m["chapter_id"],
            "title": m.get("title") or "",
            "summary_text": m.get("summary") or "",
            "timeline_note": m.get("timeline_note") or "",
            "start_anchor": m.get("start_anchor") or "",
            "end_anchor": m.get("end_anchor") or "",
            "open_threads": open_threads,
            "created_at": m.get("created_at", ""),
            "updated_at": m.get("updated_at", ""),
        }
