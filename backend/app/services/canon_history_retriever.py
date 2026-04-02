"""基于章节卡与历史检索项召回 canon 上下文。"""

from __future__ import annotations

import re
from typing import Any, Dict, List, Optional, Sequence

from .chapter_meta_service import ChapterMetaService


CALLBACK_LIMIT = 12
THREAD_LIMIT = 8
ITEM_TYPE_WEIGHTS = {
    "summary": 0.8,
    "event": 1.6,
    "open_thread": 1.9,
    "relationship": 1.3,
}


class CanonHistoryRetriever:
    """从 `< 当前章节` 的历史 canon 中召回近章承接与长线回调。"""

    def __init__(self, chapter_meta_service: Optional[ChapterMetaService] = None):
        self.chapter_meta_service = chapter_meta_service or ChapterMetaService()

    def recall(
        self,
        project_id: str,
        current_chapter_order: int,
        pov_character: str,
        scene_focus: str = "",
        author_instruction: str = "",
    ) -> Dict[str, Any]:
        recent_anchors = self.chapter_meta_service.get_recent_chapter_anchors(
            project_id,
            current_chapter_order,
            limit=3,
        )
        history_items = self.chapter_meta_service.get_history_items(
            project_id,
            current_chapter_order,
        )
        scored = [
            self._score_item(item, current_chapter_order, pov_character, scene_focus, author_instruction)
            for item in history_items
        ]
        callback_memories = self._select_items(scored, "callback")
        active_threads = self._select_items(scored, "thread")
        selection_trace = [
            self._selection_trace(item)
            for item in callback_memories + active_threads
        ]
        return {
            "recent_anchors": recent_anchors,
            "callback_memories": callback_memories,
            "active_threads": active_threads,
            "world_rules": self.chapter_meta_service.get_world_rules(project_id),
            "selection_trace": selection_trace,
        }

    def _score_item(
        self,
        item: Dict[str, Any],
        current_chapter_order: int,
        pov_character: str,
        scene_focus: str,
        author_instruction: str,
    ) -> Dict[str, Any]:
        haystack = " ".join(
            [
                item.get("summary_text", ""),
                item.get("thread_key", ""),
                item.get("subject_key", ""),
                " ".join(item.get("related_entities", [])),
            ]
        )
        reasons = []
        score = ITEM_TYPE_WEIGHTS.get(item.get("item_type", ""), 0.0)
        if pov_character and pov_character in haystack:
            score += 3.5
            reasons.append("pov")
        if scene_focus and scene_focus in haystack:
            score += 3.0
            reasons.append("scene_focus")
        for term in _instruction_terms(author_instruction):
            if term in haystack:
                score += 0.9
                reasons.append("author_instruction")
        age = max(0, current_chapter_order - int(item.get("chapter_order", 0)))
        score += max(0.0, 1.8 - (0.18 * age))
        return {
            **item,
            "rank_score": round(score, 4),
            "selected_because": reasons or ["recency"],
        }

    def _select_items(self, scored: Sequence[Dict[str, Any]], mode: str) -> List[Dict[str, Any]]:
        if mode == "thread":
            items = [item for item in scored if item.get("item_type") == "open_thread"]
            limit = THREAD_LIMIT
        else:
            items = [item for item in scored if item.get("item_type") != "open_thread"]
            limit = CALLBACK_LIMIT
        ordered = sorted(items, key=lambda item: item.get("rank_score", 0.0), reverse=True)
        return ordered[:limit]

    def _selection_trace(self, item: Dict[str, Any]) -> Dict[str, Any]:
        return {
            "chapter_order": item.get("chapter_order", 0),
            "item_type": item.get("item_type", ""),
            "summary_text": item.get("summary_text", ""),
            "source_ref": item.get("source_ref", ""),
            "rank_score": item.get("rank_score", 0.0),
            "selected_because": list(item.get("selected_because", [])),
        }


def _instruction_terms(author_instruction: str) -> List[str]:
    chunks = re.findall(r"[\u4e00-\u9fffA-Za-z0-9]{2,12}", author_instruction or "")
    seen = []
    for item in chunks:
        if item in seen:
            continue
        seen.append(item)
    return seen[:8]
