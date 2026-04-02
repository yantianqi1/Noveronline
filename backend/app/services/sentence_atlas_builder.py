"""章节句子索引构建器。"""

from __future__ import annotations

from typing import Dict, List, Sequence, Tuple


SENTENCE_END_CHARS = "。！？!?"


def build_sentence_atlas(chapters: Sequence[Dict[str, object]]) -> Tuple[List[Dict[str, object]], List[Dict[str, object]]]:
    atlas: List[Dict[str, object]] = []
    updated_chapters: List[Dict[str, object]] = []
    for chapter in chapters:
        sentence_ids, sentence_items = _chapter_sentence_items(chapter)
        atlas.extend(sentence_items)
        updated_chapters.append({**chapter, "sentence_ids": sentence_ids})
    return updated_chapters, atlas


def build_sentence_map(sentence_atlas: Sequence[Dict[str, object]]) -> Dict[str, Dict[str, object]]:
    return {str(item["sentence_id"]): dict(item) for item in sentence_atlas}


def _chapter_sentence_items(chapter: Dict[str, object]) -> Tuple[List[str], List[Dict[str, object]]]:
    chapter_id = str(chapter.get("chapter_id") or "")
    chapter_order = int(chapter.get("order") or chapter.get("chapter_order") or 0)
    content = str(chapter.get("content") or "")
    sentence_ranges = _sentence_ranges(content)
    sentence_ids: List[str] = []
    sentence_items: List[Dict[str, object]] = []
    for index, (start, end, text) in enumerate(sentence_ranges, start=1):
        sentence_id = f"{chapter_id}_s{index:03d}"
        sentence_ids.append(sentence_id)
        sentence_items.append(
            {
                "sentence_id": sentence_id,
                "chapter_id": chapter_id,
                "chapter_order": chapter_order,
                "order": index,
                "text": text,
                "char_range": {"start": start, "end": end},
            }
        )
    return sentence_ids, sentence_items


def _sentence_ranges(text: str) -> List[Tuple[int, int, str]]:
    ranges: List[Tuple[int, int, str]] = []
    start = 0
    for index, char in enumerate(text):
        if char in SENTENCE_END_CHARS or char == "\n":
            ranges.extend(_emit_sentence(text, start, index + 1))
            start = index + 1
    if start < len(text):
        ranges.extend(_emit_sentence(text, start, len(text)))
    return ranges


def _emit_sentence(text: str, start: int, end: int) -> List[Tuple[int, int, str]]:
    raw = text[start:end]
    stripped = raw.strip()
    if not stripped:
        return []
    lead_trim = len(raw) - len(raw.lstrip())
    tail_trim = len(raw.rstrip())
    actual_start = start + lead_trim
    actual_end = start + tail_trim
    return [(actual_start, actual_end, text[actual_start:actual_end])]
