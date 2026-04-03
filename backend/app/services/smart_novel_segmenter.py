"""
SmartNovelSegmenter — groups complete chapters into reading segments that fit
within a token budget.

Rules:
- Never split mid-chapter.
- A single chapter exceeding the limit becomes its own segment.
- Token estimation is conservative: Chinese text ~1.5 tokens/char.
- Greedy bin-packing: accumulate chapters; finalise when the next chapter would
  exceed the limit.
"""

import re
from typing import Any, Dict, List, Sequence

CHAPTER_TITLE_PATTERNS = [
    re.compile(r"^\s*第[零一二三四五六七八九十百千万\d]+[章节回卷幕部集篇][^\n]{0,30}$", re.MULTILINE),
    re.compile(r"^\s*(序章|楔子|终章|尾声|后记|番外)[^\n]{0,30}$", re.MULTILINE),
    re.compile(r"^\s*(卷[零一二三四五六七八九十百千万\d]+[^\n]{0,30})$", re.MULTILINE),
]

TOKENS_PER_CHAR = 1.5


def _estimate_tokens(text: str) -> int:
    return int(len(text) * TOKENS_PER_CHAR)


class SmartNovelSegmenter:
    def __init__(self, target_token_limit: int = 50000) -> None:
        self.target_token_limit = target_token_limit

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def segment(self, chapters: Sequence[Dict]) -> Dict[str, Any]:
        """Group pre-detected chapters into token-budget segments."""
        chapters = list(chapters)
        if not chapters:
            return {"segment_count": 0, "segments": []}

        segments: List[Dict[str, Any]] = []
        bucket: List[Dict] = []
        bucket_tokens = 0
        seg_index = 1

        for chapter in chapters:
            ch_tokens = _estimate_tokens(chapter.get("content", ""))

            # Greedy: if adding this chapter would exceed the limit and the
            # bucket is non-empty, finalise the current bucket first.
            if bucket and bucket_tokens + ch_tokens > self.target_token_limit:
                segments.append(self._build_segment(bucket, seg_index))
                seg_index += 1
                bucket = []
                bucket_tokens = 0

            bucket.append(chapter)
            bucket_tokens += ch_tokens

        # Flush remaining chapters.
        if bucket:
            segments.append(self._build_segment(bucket, seg_index))

        return {"segment_count": len(segments), "segments": segments}

    def segment_raw_text(self, text: str) -> Dict[str, Any]:
        """Detect chapters from raw text, then segment."""
        chapters = self._detect_chapters(text)
        return self.segment(chapters)

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _build_segment(self, chapters: List[Dict], index: int) -> Dict[str, Any]:
        orders = [ch.get("order", i + 1) for i, ch in enumerate(chapters)]
        min_order = min(orders)
        max_order = max(orders)
        chapter_range = f"{min_order}-{max_order}" if min_order != max_order else str(min_order)
        total_content = "".join(ch.get("content", "") for ch in chapters)
        return {
            "segment_id": f"seg_{index:03d}",
            "chapters": [dict(ch) for ch in chapters],
            "chapter_range": chapter_range,
            "estimated_tokens": _estimate_tokens(total_content),
        }

    def _detect_chapters(self, text: str) -> List[Dict[str, Any]]:
        """Detect chapter boundaries using CHAPTER_TITLE_PATTERNS.

        Falls back to blank-line splitting when no markers are found.
        """
        matches: List[re.Match] = []
        for pattern in CHAPTER_TITLE_PATTERNS:
            matches.extend(pattern.finditer(text))

        if not matches:
            return self._fallback_chapters(text)

        # Sort by position.
        matches = sorted(matches, key=lambda m: m.start())

        chapters: List[Dict[str, Any]] = []
        for idx, match in enumerate(matches):
            title = match.group(0).strip()
            content_start = match.end()
            content_end = matches[idx + 1].start() if idx + 1 < len(matches) else len(text)
            content = text[content_start:content_end].strip()
            order = idx + 1
            chapters.append({
                "chapter_id": f"ch_{order:03d}",
                "order": order,
                "title": title,
                "content": content,
                "word_count": len(content),
            })

        # Drop empty chapters.
        return [ch for ch in chapters if ch["content"]]

    def _fallback_chapters(self, text: str) -> List[Dict[str, Any]]:
        """Split on blank lines when no chapter markers are found."""
        paragraphs = [p.strip() for p in re.split(r"\n{2,}", text) if p.strip()]
        chapters = []
        for idx, para in enumerate(paragraphs):
            order = idx + 1
            chapters.append({
                "chapter_id": f"ch_{order:03d}",
                "order": order,
                "title": f"叙事段 {order}",
                "content": para,
                "word_count": len(para),
            })
        return chapters
