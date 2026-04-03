"""
Tests for SmartNovelSegmenter — TDD first pass.
"""
import pytest
from app.services.smart_novel_segmenter import SmartNovelSegmenter


def _make_chapter(order: int, content: str) -> dict:
    return {
        "chapter_id": f"ch_{order:03d}",
        "order": order,
        "title": f"第{order}章 测试章节",
        "content": content,
        "word_count": len(content),
    }


# ---------------------------------------------------------------------------
# 1. Single short chapter becomes one segment
# ---------------------------------------------------------------------------

def test_single_short_chapter_becomes_one_segment():
    seg = SmartNovelSegmenter(target_token_limit=50000)
    chapters = [_make_chapter(1, "这是一个短章节。" * 10)]
    result = seg.segment(chapters)

    assert result["segment_count"] == 1
    assert len(result["segments"]) == 1
    segs = result["segments"]
    assert len(segs[0]["chapters"]) == 1


# ---------------------------------------------------------------------------
# 2. Multiple chapters are packed into segments correctly
# ---------------------------------------------------------------------------

def test_multiple_chapters_packed_into_segments():
    # Each chapter ~3000 chars; limit ~10000 tokens → each segment fits ~3 chapters
    seg = SmartNovelSegmenter(target_token_limit=10000)
    content = "甲" * 3000
    chapters = [_make_chapter(i, content) for i in range(1, 11)]  # 10 chapters
    result = seg.segment(chapters)

    # Should produce at least 2 segments because 10*3000*1.5 >> 10000
    assert result["segment_count"] >= 2

    # No chapter should appear in more than one segment
    seen_ids = []
    for s in result["segments"]:
        for ch in s["chapters"]:
            assert ch["chapter_id"] not in seen_ids, "Chapter appeared in multiple segments"
            seen_ids.append(ch["chapter_id"])

    # All chapters accounted for
    assert len(seen_ids) == 10


# ---------------------------------------------------------------------------
# 3. Oversized chapter becomes its own segment
# ---------------------------------------------------------------------------

def test_oversized_chapter_becomes_own_segment():
    # Limit is 5000 tokens; chapter has 10000 chars → ~15000 tokens
    seg = SmartNovelSegmenter(target_token_limit=5000)
    big_content = "乙" * 10000
    chapters = [_make_chapter(1, big_content)]
    result = seg.segment(chapters)

    assert result["segment_count"] == 1
    assert len(result["segments"][0]["chapters"]) == 1


# ---------------------------------------------------------------------------
# 4. Chapter range label
# ---------------------------------------------------------------------------

def test_chapter_range_label():
    seg = SmartNovelSegmenter(target_token_limit=500000)  # huge limit, all fit in one
    chapters = [_make_chapter(i, "丙" * 100) for i in range(1, 6)]  # 5 chapters
    result = seg.segment(chapters)

    assert result["segment_count"] == 1
    assert result["segments"][0]["chapter_range"] == "1-5"


# ---------------------------------------------------------------------------
# 5. estimated_tokens present and positive
# ---------------------------------------------------------------------------

def test_estimated_tokens_present():
    seg = SmartNovelSegmenter(target_token_limit=50000)
    chapters = [_make_chapter(1, "丁" * 500)]
    result = seg.segment(chapters)

    first_seg = result["segments"][0]
    assert "estimated_tokens" in first_seg
    assert first_seg["estimated_tokens"] > 0


# ---------------------------------------------------------------------------
# 6. Empty chapters list returns empty result
# ---------------------------------------------------------------------------

def test_empty_chapters_returns_empty():
    seg = SmartNovelSegmenter(target_token_limit=50000)
    result = seg.segment([])

    assert result["segment_count"] == 0
    assert result["segments"] == []


# ---------------------------------------------------------------------------
# 7. Raw text segmentation
# ---------------------------------------------------------------------------

def test_raw_text_segmentation():
    raw = "\n".join([
        f"第{i}章 测试章节\n{'戊' * 500}"
        for i in range(1, 6)
    ])
    seg = SmartNovelSegmenter(target_token_limit=50000)
    result = seg.segment_raw_text(raw)

    assert result["segment_count"] >= 1
    # Each segment has chapters
    for s in result["segments"]:
        assert len(s["chapters"]) >= 1
