"""章节卡的确定性回退构建器。"""

from __future__ import annotations

from typing import Any, Dict, List, Optional, Sequence

from .local_block_fact_support import split_sentences
from .novel_seed_analyzer import NovelSeedAnalyzer


MAX_KEY_EVENTS = 3
MAX_OPEN_THREADS = 3
MAX_CHARACTER_UPDATES = 3
MAX_RELATIONSHIP_UPDATES = 2
MAX_KEY_ENTITIES = 6


class ChapterCardFallbackBuilder:
    def __init__(self, analyzer: Optional[NovelSeedAnalyzer] = None):
        self.analyzer = analyzer or NovelSeedAnalyzer()

    def build(
        self,
        chapter: Dict[str, Any],
        story_memory: Dict[str, Any],
        block_analyses: Dict[str, Any],
        previous_cards: Optional[Sequence[Dict[str, Any]]] = None,
    ) -> Dict[str, Any]:
        content = str(chapter.get("content") or "").strip()
        sentences = split_sentences(content)
        analysis = self.analyzer.analyze_text(content)
        chapter_id = str(chapter.get("chapter_id") or "")
        chapter_order = int(chapter.get("chapter_order") or chapter.get("order") or 0)
        previous_card = list(previous_cards or [])[-1] if previous_cards else {}
        summary_text = self._summary_text(chapter, sentences, previous_card)
        start_anchor = self._start_anchor(sentences, previous_card, summary_text)
        end_anchor = self._end_anchor(sentences, block_analyses, chapter_id, summary_text)
        return {
            "chapter_id": chapter_id,
            "chapter_order": chapter_order,
            "title": str(chapter.get("title") or chapter_id),
            "summary_text": summary_text,
            "start_anchor": start_anchor,
            "end_anchor": end_anchor,
            "key_events": self._key_events(sentences, summary_text),
            "open_threads": self._open_threads(story_memory, chapter_order),
            "character_state_updates": self._character_updates(analysis),
            "relationship_updates": self._relationship_updates(analysis),
            "timeline_note": "时间线无明确推进",
            "key_entities": self._key_entities(analysis),
        }

    def _summary_text(self, chapter: Dict[str, Any], sentences: Sequence[str], previous_card: Dict[str, Any]) -> str:
        parts = []
        if previous_card.get("end_anchor"):
            parts.append(f"承接前章：{previous_card['end_anchor']}")
        body = "；".join(sentences[:2]).strip() or str(chapter.get("title") or "本章继续推进当前主线")
        parts.append(body)
        return " ".join(parts)[:160]

    def _start_anchor(self, sentences: Sequence[str], previous_card: Dict[str, Any], summary_text: str) -> str:
        previous_anchor = str(previous_card.get("end_anchor") or "").strip()
        if previous_anchor:
            return previous_anchor[:60]
        return (sentences[0] if sentences else summary_text)[:60]

    def _end_anchor(self, sentences: Sequence[str], block_analyses: Dict[str, Any], chapter_id: str, summary_text: str) -> str:
        if sentences:
            return "；".join(sentences[-2:])[:60]
        for block in block_analyses.get("blocks", []):
            if chapter_id and chapter_id in str(block):
                return str(block.get("plot_summary") or summary_text)[:60]
        return summary_text[:60]

    def _key_events(self, sentences: Sequence[str], summary_text: str) -> List[Dict[str, str]]:
        items = [{"summary": sentence[:80]} for sentence in sentences[:MAX_KEY_EVENTS] if sentence.strip()]
        return items or [{"summary": summary_text[:80]}]

    def _open_threads(self, story_memory: Dict[str, Any], chapter_order: int) -> List[Dict[str, str]]:
        threads = []
        for item in story_memory.get("open_threads", []):
            item_order = _order_from_ref(item.get("chapter_id", ""))
            if item_order and item_order > chapter_order:
                continue
            thread_key = str(item.get("thread_key") or "").strip()
            summary = str(item.get("summary") or thread_key).strip()
            if thread_key and summary:
                threads.append({"thread_key": thread_key, "summary": summary[:60]})
            if len(threads) >= MAX_OPEN_THREADS:
                break
        return threads

    def _character_updates(self, analysis: Dict[str, Any]) -> List[Dict[str, str]]:
        updates = []
        for item in analysis.get("characters", [])[:MAX_CHARACTER_UPDATES]:
            name = str(item.get("name") or "").strip()
            if not name:
                continue
            summary = str(item.get("profile_summary") or f"{name}在本章继续推进当前行动。").strip()
            updates.append({"name": name, "state": "active", "summary": summary[:60]})
        return updates

    def _relationship_updates(self, analysis: Dict[str, Any]) -> List[Dict[str, str]]:
        updates = []
        for item in analysis.get("relations", [])[:MAX_RELATIONSHIP_UPDATES]:
            source = str(item.get("source") or "").strip()
            target = str(item.get("target") or "").strip()
            if not source or not target:
                continue
            relation_type = str(item.get("relation_type") or "co_occurrence").strip()
            evidence = str((item.get("evidence") or ["本章共同出场"])[:1][0]).strip()
            updates.append({"source": source, "target": target, "state": relation_type, "summary": evidence[:60]})
        return updates

    def _key_entities(self, analysis: Dict[str, Any]) -> List[Dict[str, str]]:
        entities: List[Dict[str, str]] = []
        for item in analysis.get("characters", [])[:MAX_KEY_ENTITIES]:
            name = str(item.get("name") or "").strip()
            if name:
                entities.append({"name": name, "entity_type": "character"})
        remaining = MAX_KEY_ENTITIES - len(entities)
        for item in analysis.get("organizations", [])[:remaining]:
            name = str(item.get("name") or "").strip()
            if name:
                entities.append({"name": name, "entity_type": "organization"})
        return entities


def _order_from_ref(chapter_id: str) -> int:
    try:
        return int(str(chapter_id).rsplit("_", 1)[-1])
    except (TypeError, ValueError):
        return 0
