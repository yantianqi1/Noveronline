"""章节写作上下文排序器。"""

from __future__ import annotations

from typing import Any, Dict, List

MAX_MUST_KNOW = 8
MAX_SHOULD_KNOW = 8
MAX_WARNINGS = 5
MAX_SCENES = 5
CATEGORY_WEIGHTS = {
    "continuity": 3.0,
    "world_rule": 2.8,
    "pov_state": 2.6,
    "conflict": 2.3,
    "worldline_state": 2.1,
    "worldline_event": 1.6,
    "relationship": 1.1,
    "open_thread": 0.8,
}


class ChapterContextRanker:
    def rank_items(self, items: List[Dict[str, Any]], scope: Dict[str, Any], limit: int) -> List[Dict[str, Any]]:
        ranked = {}
        for item in items:
            if item.get("memory_layer") == "candidate" and not scope.get("include_candidates"):
                continue
            scored_item = {**item, "rank_score": round(self._score(item), 4)}
            dedupe_key = self._dedupe_key(scored_item)
            current = ranked.get(dedupe_key)
            if current and current["rank_score"] >= scored_item["rank_score"]:
                continue
            ranked[dedupe_key] = scored_item
        ordered = sorted(ranked.values(), key=lambda item: item["rank_score"], reverse=True)
        return ordered[:limit]

    def _score(self, item: Dict[str, Any]) -> float:
        meta = item.get("match_meta", {})
        score = 0.0
        score += CATEGORY_WEIGHTS.get(item.get("category", ""), 0.0)
        score += 4.0 if meta.get("scope_hit") else 0.0
        score += 3.0 if meta.get("pov_hit") else 0.0
        score += 2.0 if meta.get("scene_hit") else 0.0
        score += 1.5 if meta.get("thread_hit") else 0.0
        score += max(0.0, 1.2 - (0.2 * float(meta.get("chapter_distance", 5))))
        score += float(meta.get("freshness", 0.0))
        score += float(item.get("salience") or 0.0)
        if item.get("memory_layer") == "candidate":
            score -= 1.25
        return score

    def _dedupe_key(self, item: Dict[str, Any]) -> str:
        subject = str(item.get("normalized_subject") or "").strip()
        if subject:
            return f"subject:{subject}"
        return f"item:{item.get('item_id', '')}"
