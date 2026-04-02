"""章节分析块构建服务。"""

from typing import Any, Dict, List, Optional, Sequence


DEFAULT_TARGET_OWNED_CHAR_COUNT = 5000
DEFAULT_CONTEXT_CHAPTER_COUNT = 2


class AnalysisBlockBuilder:
    """将顺序章节组装为动态主块与重叠上下文块。"""

    def __init__(
        self,
        target_owned_char_count: int = DEFAULT_TARGET_OWNED_CHAR_COUNT,
        context_chapter_count: int = DEFAULT_CONTEXT_CHAPTER_COUNT,
    ):
        self.target_owned_char_count = target_owned_char_count
        self.context_chapter_count = context_chapter_count

    def build(self, chapters: Sequence[Dict[str, Any]]) -> Dict[str, Any]:
        ordered = sorted(chapters, key=lambda item: item.get("order", 0))
        blocks = []
        for block_index, (start, end) in enumerate(self._owned_ranges(ordered), start=1):
            blocks.append(self._build_block(block_index, start, end, ordered))
        return {
            "block_count": len(blocks),
            "target_owned_char_count": self.target_owned_char_count,
            "context_chapter_count": self.context_chapter_count,
            "blocks": blocks,
        }

    def _owned_ranges(self, chapters: Sequence[Dict[str, Any]]) -> List[tuple[int, int]]:
        ranges: List[tuple[int, int]] = []
        start = 0
        owned_char_count = 0
        for index, chapter in enumerate(chapters):
            owned_char_count += self._chapter_char_count(chapter)
            if owned_char_count < self.target_owned_char_count:
                continue
            ranges.append((start, index + 1))
            start = index + 1
            owned_char_count = 0
        if start < len(chapters):
            ranges.append((start, len(chapters)))
        return ranges

    def _build_block(
        self,
        block_index: int,
        start: int,
        end: int,
        chapters: Sequence[Dict[str, Any]],
    ) -> Dict[str, Any]:
        owned = list(chapters[start:end])
        previous_context = list(chapters[max(0, start - self.context_chapter_count):start])
        next_context = list(chapters[end:end + self.context_chapter_count])
        context = previous_context + next_context
        owned_ids = [item["chapter_id"] for item in owned]
        context_ids = [item["chapter_id"] for item in context]
        owned_sentence_ids = [sentence_id for item in owned for sentence_id in item.get("sentence_ids", [])]
        context_sentence_ids = [sentence_id for item in context for sentence_id in item.get("sentence_ids", [])]
        owned_char_count = sum(self._chapter_char_count(item) for item in owned)
        owned_orders = [item["order"] for item in owned]
        context_orders = [item["order"] for item in context]
        titles = {item["chapter_id"]: item.get("title", item["chapter_id"]) for item in owned + context}
        return {
            "block_id": f"block_{block_index:04d}",
            "order": block_index,
            "owned_chapter_ids": owned_ids,
            "owned_char_count": owned_char_count,
            "context_chapter_ids": context_ids,
            "owned_sentence_ids": owned_sentence_ids,
            "context_sentence_ids": context_sentence_ids,
            "owned_chapter_range": self._range_payload(owned_orders),
            "context_chapter_range": self._range_payload(context_orders),
            "chapter_titles": titles,
            "source_names": sorted({item.get("source_name", "") for item in owned if item.get("source_name")}),
        }

    def _range_payload(self, orders: List[int]) -> Optional[Dict[str, int]]:
        if not orders:
            return None
        return {"start_order": min(orders), "end_order": max(orders)}

    def _chapter_char_count(self, chapter: Dict[str, Any]) -> int:
        title = chapter.get("title", chapter.get("chapter_id", ""))
        content = chapter.get("content", "")
        return len(title) + len(content)
