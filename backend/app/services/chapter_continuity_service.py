"""从结构化章节卡派生兼容 continuity 视图。"""

from __future__ import annotations

from typing import Any, Dict, List, Sequence


class ChapterContinuityService:
    """把章节卡转换成 Writer/旧 API 可消费的连续性结构。"""

    def build(self, chapter_cards: Sequence[Dict[str, Any]]) -> Dict[str, Any]:
        return self.build_from_chapter_cards(chapter_cards)

    def build_from_chapter_cards(self, chapter_cards: Sequence[Dict[str, Any]]) -> Dict[str, Any]:
        chapters = [self._chapter_payload(card) for card in sorted(chapter_cards, key=_chapter_order)]
        return {
            "chapter_count": len(chapters),
            "global_summary": self._global_summary(chapters),
            "chapters": chapters,
        }

    def build_from_block_analyses(
        self,
        chapters: Sequence[Dict[str, Any]],
        analysis_blocks: Sequence[Dict[str, Any]],
        block_analyses: Sequence[Dict[str, Any]],
    ) -> Dict[str, Any]:
        return self.build_from_chapter_cards(chapters)

    def _chapter_payload(self, chapter_card: Dict[str, Any]) -> Dict[str, Any]:
        head_context = str(chapter_card.get("start_anchor") or "").strip()
        tail_hooks = [item for item in [str(chapter_card.get("end_anchor") or "").strip()] if item]
        core_conflicts = self._event_summaries(chapter_card)
        open_threads = self._thread_summaries(chapter_card)
        summary_text = str(chapter_card.get("summary_text") or "").strip()
        if open_threads:
            summary_text = f"{summary_text} 未收束线索：{'；'.join(open_threads)}。".strip()
        return {
            "chapter_id": chapter_card.get("chapter_id", ""),
            "order": _chapter_order(chapter_card),
            "title": str(chapter_card.get("title") or "").strip(),
            "head_context": head_context,
            "core_conflicts": core_conflicts,
            "key_characters": self._entity_names(chapter_card, "character"),
            "key_organizations": self._entity_names(chapter_card, "organization"),
            "tail_hooks": tail_hooks,
            "continuity_summary": summary_text or head_context or "暂无章节连续性摘要。",
        }

    def _event_summaries(self, chapter_card: Dict[str, Any]) -> List[str]:
        items = [
            str(item.get("summary") or "").strip()
            for item in chapter_card.get("key_events", [])
            if isinstance(item, dict)
        ]
        return [item for item in items if item] or [str(chapter_card.get("summary_text") or "").strip()]

    def _thread_summaries(self, chapter_card: Dict[str, Any]) -> List[str]:
        items = []
        for item in chapter_card.get("open_threads", []):
            if not isinstance(item, dict):
                continue
            summary = str(item.get("summary") or item.get("thread_key") or "").strip()
            if summary:
                items.append(summary)
        return items

    def _entity_names(self, chapter_card: Dict[str, Any], entity_type: str) -> List[str]:
        names = []
        for item in chapter_card.get("key_entities", []):
            if not isinstance(item, dict):
                continue
            if str(item.get("entity_type") or "").strip() != entity_type:
                continue
            name = str(item.get("name") or "").strip()
            if name and name not in names:
                names.append(name)
        if entity_type != "character":
            return names
        for item in chapter_card.get("character_state_updates", []):
            if not isinstance(item, dict):
                continue
            name = str(item.get("name") or "").strip()
            if name and name not in names:
                names.append(name)
        return names

    def _global_summary(self, chapters: Sequence[Dict[str, Any]]) -> str:
        if not chapters:
            return "暂无章节连续性摘要。"
        opening = chapters[0]["continuity_summary"]
        ending = chapters[-1]["continuity_summary"]
        return f"开篇承接：{opening} 近期状态：{ending}"


def _chapter_order(chapter_card: Dict[str, Any]) -> int:
    return int(chapter_card.get("chapter_order") or chapter_card.get("order") or 0)
