"""章节分析块构建服务。"""

from typing import Any, Dict, List, Optional, Sequence


DEFAULT_OWNED_CHAPTER_COUNT = 10
DEFAULT_CONTEXT_CHAPTER_COUNT = 2


class AnalysisBlockBuilder:
    """将顺序章节组装为固定主块与重叠上下文块。"""

    def __init__(
        self,
        owned_chapter_count: int = DEFAULT_OWNED_CHAPTER_COUNT,
        context_chapter_count: int = DEFAULT_CONTEXT_CHAPTER_COUNT,
    ):
        self.owned_chapter_count = owned_chapter_count
        self.context_chapter_count = context_chapter_count

    def build(self, chapters: Sequence[Dict[str, Any]]) -> Dict[str, Any]:
        ordered = sorted(chapters, key=lambda item: item.get("order", 0))
        blocks = []
        for block_index, start in enumerate(range(0, len(ordered), self.owned_chapter_count), start=1):
            blocks.append(self._build_block(block_index, start, ordered))
        return {
            "block_count": len(blocks),
            "owned_chapter_count": self.owned_chapter_count,
            "context_chapter_count": self.context_chapter_count,
            "blocks": blocks,
        }

    def _build_block(
        self,
        block_index: int,
        start: int,
        chapters: Sequence[Dict[str, Any]],
    ) -> Dict[str, Any]:
        end = start + self.owned_chapter_count
        owned = list(chapters[start:end])
        previous_context = list(chapters[max(0, start - self.context_chapter_count):start])
        next_context = list(chapters[end:end + self.context_chapter_count])
        context = previous_context + next_context
        owned_ids = [item["chapter_id"] for item in owned]
        context_ids = [item["chapter_id"] for item in context]
        owned_orders = [item["order"] for item in owned]
        context_orders = [item["order"] for item in context]
        titles = {item["chapter_id"]: item.get("title", item["chapter_id"]) for item in owned + context}
        return {
            "block_id": f"block_{block_index:04d}",
            "order": block_index,
            "owned_chapter_ids": owned_ids,
            "context_chapter_ids": context_ids,
            "owned_chapter_range": self._range_payload(owned_orders),
            "context_chapter_range": self._range_payload(context_orders),
            "chapter_titles": titles,
            "source_names": sorted({item.get("source_name", "") for item in owned if item.get("source_name")}),
        }

    def _range_payload(self, orders: List[int]) -> Optional[Dict[str, int]]:
        if not orders:
            return None
        return {"start_order": min(orders), "end_order": max(orders)}
