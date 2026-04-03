# Seed Pipeline Redesign Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace the 14-stage regex-heavy seed extraction pipeline with a 4-stage LLM-driven sequential reading pipeline that produces agent-ready character profiles.

**Architecture:** Two-phase pipeline: Phase 1 (Novel Comprehension) segments text then reads sequentially with milestone-based memory; Phase 2 (Character Agent Construction) integrates globally then generates per-character agent profiles. All new services live alongside existing ones; `SeedExtractRunner` is rewritten to call new services; old services are left in place but no longer imported by the runner.

**Tech Stack:** Python 3.11+ / Flask, Vue 3 + Vite, pytest, existing `LLMClient` + `LlmRouter` for LLM calls.

---

## File Structure

### New Files (Backend)
| File | Responsibility |
|------|---------------|
| `backend/app/services/smart_novel_segmenter.py` | Chapter detection + greedy bin-packing into token-budget segments |
| `backend/app/services/reading_notes_manager.py` | ReadingNotes data structure, merge protocol, milestone creation, context assembly, serialization |
| `backend/app/services/sequential_reader_prompts.py` | System prompts for per-segment reading and arc/volume summary LLM calls |
| `backend/app/services/sequential_reader.py` | Orchestrates sequential reading: iterates segments, calls LLM, updates notes, triggers milestones |
| `backend/app/services/character_agent_prompts.py` | Prompts for per-character agent profile generation |
| `backend/app/services/character_agent_profile_generator.py` | Generates agent-ready profiles for important characters (concurrent LLM calls) |

### New Files (Tests)
| File | Responsibility |
|------|---------------|
| `backend/tests/test_smart_novel_segmenter.py` | Unit tests for segmentation logic |
| `backend/tests/test_reading_notes_manager.py` | Unit tests for merge protocol, milestones, context assembly |
| `backend/tests/test_sequential_reader.py` | Integration test with fake LLM |
| `backend/tests/test_character_agent_profile_generator.py` | Unit test with fake LLM |
| `backend/tests/test_new_seed_pipeline.py` | End-to-end integration test of the full new pipeline |

### Modified Files (Backend)
| File | Changes |
|------|---------|
| `backend/app/services/seed_pipeline_chapters.py` | Replace 4 old chapters with 2 new chapters + new stage mappings |
| `backend/app/services/llm_module_registry.py` | Add `sequential_reading` and `character_agent_profile` module definitions + stage mappings |
| `backend/app/services/seed_extract_runner.py` | Complete rewrite: 4-stage pipeline calling new services |
| `backend/app/services/seed_extract_task_service.py` | Replace old service imports/wiring with new services |
| `backend/app/services/seed_analysis_aggregator.py` | New method `aggregate_from_reading_notes()` reading from ReadingNotes |
| `backend/tests/seed_test_helpers.py` | Add `sequential_reading` and `character_agent_profile` to `FakeSeedLlmClient` |

### Modified Files (Frontend)
| File | Changes |
|------|---------|
| `frontend/src/views/overview/seedUploadTaskView.js` | Replace IDLE_TIMELINE with 7 new stages, update STAGE_PROGRESS_RANGE |
| `frontend/src/views/overview/SeedUploadFormFields.vue` | Add "target token limit" field to advanced settings |
| `frontend/src/views/overview/SeedAnalysisPanel.vue` | Show personality traits and speech style for characters |
| `frontend/src/composables/useSeedUpload.js` | Pass `segmentTokenLimit` in upload payload |
| `frontend/src/composables/seedUploadTaskState.js` | Update `DEFAULT_TASK_METRICS` to include `segment_count` instead of `block_count` |

---

## Task 1: SmartNovelSegmenter

**Files:**
- Create: `backend/app/services/smart_novel_segmenter.py`
- Test: `backend/tests/test_smart_novel_segmenter.py`
- Reference: `backend/app/services/novel_chapter_segmenter.py` (reuse chapter detection regex)

### Overview
Groups chapters into reading segments that fit within a token budget. Never splits mid-chapter.

- [ ] **Step 1: Write the failing tests**

Create `backend/tests/test_smart_novel_segmenter.py`:

```python
"""SmartNovelSegmenter unit tests."""

from app.services.smart_novel_segmenter import SmartNovelSegmenter


def _chapter(chapter_id, title, content):
    return {
        "chapter_id": chapter_id,
        "order": int(chapter_id.split("_")[1]),
        "title": title,
        "content": content,
        "word_count": len(content),
    }


def test_single_short_chapter_becomes_one_segment():
    chapters = [_chapter("chapter_0001", "第一章", "短篇内容" * 100)]
    segmenter = SmartNovelSegmenter(target_token_limit=50000)
    result = segmenter.segment(chapters)
    assert result["segment_count"] == 1
    assert len(result["segments"]) == 1
    seg = result["segments"][0]
    assert seg["segment_id"] == "seg_001"
    assert len(seg["chapters"]) == 1
    assert seg["chapters"][0]["chapter_id"] == "chapter_0001"


def test_multiple_chapters_packed_into_segments():
    # Each chapter ~3000 chars => ~4500 tokens (Chinese 1.5x)
    chapters = [_chapter(f"chapter_{i:04d}", f"第{i}章", "这是测试" * 750) for i in range(1, 11)]
    segmenter = SmartNovelSegmenter(target_token_limit=10000)
    result = segmenter.segment(chapters)
    assert result["segment_count"] >= 2
    # Verify no chapter appears in multiple segments
    seen_ids = set()
    for seg in result["segments"]:
        for ch in seg["chapters"]:
            assert ch["chapter_id"] not in seen_ids
            seen_ids.add(ch["chapter_id"])
    assert len(seen_ids) == 10


def test_oversized_chapter_becomes_own_segment():
    small = _chapter("chapter_0001", "第一章", "短" * 100)
    big = _chapter("chapter_0002", "第二章", "长" * 50000)
    small2 = _chapter("chapter_0003", "第三章", "短" * 100)
    segmenter = SmartNovelSegmenter(target_token_limit=5000)
    result = segmenter.segment([small, big, small2])
    # The big chapter must be alone in its segment
    big_seg = [s for s in result["segments"] if any(c["chapter_id"] == "chapter_0002" for c in s["chapters"])]
    assert len(big_seg) == 1
    assert len(big_seg[0]["chapters"]) == 1


def test_chapter_range_label():
    chapters = [_chapter(f"chapter_{i:04d}", f"第{i}章", "内容" * 100) for i in range(1, 6)]
    segmenter = SmartNovelSegmenter(target_token_limit=100000)
    result = segmenter.segment(chapters)
    assert result["segment_count"] == 1
    assert result["segments"][0]["chapter_range"] == "1-5"


def test_estimated_tokens_present():
    chapters = [_chapter("chapter_0001", "第一章", "中文内容" * 1000)]
    segmenter = SmartNovelSegmenter(target_token_limit=50000)
    result = segmenter.segment(chapters)
    seg = result["segments"][0]
    assert "estimated_tokens" in seg
    assert seg["estimated_tokens"] > 0


def test_empty_chapters_returns_empty():
    segmenter = SmartNovelSegmenter(target_token_limit=50000)
    result = segmenter.segment([])
    assert result["segment_count"] == 0
    assert result["segments"] == []


def test_raw_text_segmentation():
    """When given raw text without chapters, segment by blank-line pseudo-chapters."""
    raw_text = "\n\n".join([f"段落{i}的内容" * 200 for i in range(20)])
    segmenter = SmartNovelSegmenter(target_token_limit=5000)
    result = segmenter.segment_raw_text(raw_text)
    assert result["segment_count"] >= 1
    for seg in result["segments"]:
        assert len(seg["chapters"]) >= 1
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd /root/novelwork/backend && PYTHONPATH=$(pwd) pytest tests/test_smart_novel_segmenter.py -v`
Expected: FAIL with `ModuleNotFoundError`

- [ ] **Step 3: Write the implementation**

Create `backend/app/services/smart_novel_segmenter.py`:

```python
"""Smart novel segmenter: groups chapters into token-budget reading segments."""

from __future__ import annotations

import re
from typing import Any, Dict, List, Sequence

# Reuse chapter detection patterns from NovelChapterSegmenter
CHAPTER_TITLE_PATTERNS = [
    re.compile(r"^\s*第[零一二三四五六七八九十百千万\d]+[章节回卷幕部集篇][^\n]{0,30}$", re.MULTILINE),
    re.compile(r"^\s*(序章|楔子|终章|尾声|后记|番外)[^\n]{0,30}$", re.MULTILINE),
    re.compile(r"^\s*(卷[零一二三四五六七八九十百千万\d]+[^\n]{0,30})$", re.MULTILINE),
]

# Conservative: Chinese ~1.5 tokens/char, English ~1.3 tokens/word
CHINESE_TOKENS_PER_CHAR = 1.5
ENGLISH_TOKENS_PER_WORD = 1.3

# When no chapter markers found, split on blank lines into pseudo-chapters
BLANK_LINE_SPLIT = re.compile(r"\n\s*\n")


class SmartNovelSegmenter:
    """Groups complete chapters into reading segments within a token budget."""

    def __init__(self, target_token_limit: int = 50000):
        self.target_token_limit = max(1000, target_token_limit)

    def segment(self, chapters: Sequence[Dict[str, Any]]) -> Dict[str, Any]:
        """Segment pre-detected chapters into reading segments."""
        if not chapters:
            return {"segment_count": 0, "segments": []}

        segments: List[Dict[str, Any]] = []
        current_chapters: List[Dict[str, Any]] = []
        current_tokens = 0

        for chapter in chapters:
            chapter_tokens = self._estimate_tokens(chapter["content"])
            if current_chapters and current_tokens + chapter_tokens > self.target_token_limit:
                segments.append(self._build_segment(len(segments) + 1, current_chapters, current_tokens))
                current_chapters = []
                current_tokens = 0
            current_chapters.append(chapter)
            current_tokens += chapter_tokens

        if current_chapters:
            segments.append(self._build_segment(len(segments) + 1, current_chapters, current_tokens))

        return {"segment_count": len(segments), "segments": segments}

    def segment_raw_text(self, text: str) -> Dict[str, Any]:
        """Segment raw text without chapter markers into pseudo-chapters, then segment."""
        if not text.strip():
            return {"segment_count": 0, "segments": []}

        # Try chapter detection first
        chapter_boundaries = self._detect_chapter_boundaries(text)
        if chapter_boundaries:
            chapters = self._split_by_boundaries(text, chapter_boundaries)
        else:
            chapters = self._split_by_blank_lines(text)

        return self.segment(chapters)

    def _estimate_tokens(self, text: str) -> int:
        """Conservative token estimation."""
        if not text:
            return 0
        chinese_chars = sum(1 for c in text if "\u4e00" <= c <= "\u9fff")
        non_chinese = len(text) - chinese_chars
        # Estimate non-Chinese as roughly word-count (divide by avg word length ~5)
        english_words = max(1, non_chinese / 5) if non_chinese > 0 else 0
        tokens = int(chinese_chars * CHINESE_TOKENS_PER_CHAR + english_words * ENGLISH_TOKENS_PER_WORD)
        return max(1, tokens)

    def _build_segment(
        self, index: int, chapters: List[Dict[str, Any]], estimated_tokens: int
    ) -> Dict[str, Any]:
        orders = [ch.get("order", 0) for ch in chapters]
        min_order = min(orders) if orders else 0
        max_order = max(orders) if orders else 0
        chapter_range = f"{min_order}-{max_order}" if min_order != max_order else str(min_order)
        return {
            "segment_id": f"seg_{index:03d}",
            "chapters": chapters,
            "chapter_range": chapter_range,
            "estimated_tokens": estimated_tokens,
        }

    def _detect_chapter_boundaries(self, text: str) -> List[re.Match]:
        """Find chapter title matches in text."""
        matches = []
        for pattern in CHAPTER_TITLE_PATTERNS:
            matches.extend(pattern.finditer(text))
        matches.sort(key=lambda m: m.start())
        return matches

    def _split_by_boundaries(self, text: str, boundaries: List[re.Match]) -> List[Dict[str, Any]]:
        """Split text into chapters using detected boundaries."""
        chapters = []
        for i, match in enumerate(boundaries):
            start = match.start()
            end = boundaries[i + 1].start() if i + 1 < len(boundaries) else len(text)
            content = text[start:end].strip()
            title = match.group(0).strip()
            chapters.append({
                "chapter_id": f"chapter_{i + 1:04d}",
                "order": i + 1,
                "title": title,
                "content": content,
                "word_count": len(content),
            })
        return chapters

    def _split_by_blank_lines(self, text: str) -> List[Dict[str, Any]]:
        """Split text into pseudo-chapters on blank lines."""
        parts = BLANK_LINE_SPLIT.split(text)
        parts = [p.strip() for p in parts if p.strip()]
        if not parts:
            return [{
                "chapter_id": "chapter_0001",
                "order": 1,
                "title": "全文",
                "content": text.strip(),
                "word_count": len(text.strip()),
            }]
        chapters = []
        for i, part in enumerate(parts, 1):
            chapters.append({
                "chapter_id": f"chapter_{i:04d}",
                "order": i,
                "title": f"段落{i}",
                "content": part,
                "word_count": len(part),
            })
        return chapters
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd /root/novelwork/backend && PYTHONPATH=$(pwd) pytest tests/test_smart_novel_segmenter.py -v`
Expected: All 8 tests PASS

- [ ] **Step 5: Commit**

```bash
git add backend/app/services/smart_novel_segmenter.py backend/tests/test_smart_novel_segmenter.py
git commit -m "feat: add SmartNovelSegmenter for token-budget chapter grouping"
```

---

## Task 2: ReadingNotesManager

**Files:**
- Create: `backend/app/services/reading_notes_manager.py`
- Test: `backend/tests/test_reading_notes_manager.py`

### Overview
Manages the `ReadingNotes` data structure: three-tier storage (core_facts, relationship_graph, plot_state), merge protocol, milestone creation (arc/volume summaries), adaptive context assembly, and disk persistence.

- [ ] **Step 1: Write the failing tests**

Create `backend/tests/test_reading_notes_manager.py`:

```python
"""ReadingNotesManager unit tests."""

import json
import os

from app.services.reading_notes_manager import ReadingNotesManager


def test_fresh_notes_have_correct_structure():
    manager = ReadingNotesManager()
    notes = manager.notes
    assert "core_facts" in notes
    assert "characters" in notes["core_facts"]
    assert "organizations" in notes["core_facts"]
    assert "world_rules" in notes["core_facts"]
    assert "key_locations" in notes["core_facts"]
    assert "relationship_graph" in notes
    assert "plot_state" in notes
    assert isinstance(notes["relationship_graph"], list)


def test_merge_character_update_new():
    manager = ReadingNotesManager()
    updates = [
        {
            "name": "沈夜",
            "aliases": ["夜哥"],
            "is_new": True,
            "status": "active",
            "identity": "调查者",
            "personality_traits": ["坚毅"],
            "speech_style": "简练犀利",
            "goals": "追查镜湖旧案",
            "key_actions": ["进入镜湖谷"],
            "knowledge_gained": ["发现密道"],
            "quote_examples": ["真相不会自己浮出水面。"],
        }
    ]
    manager.merge_character_updates(updates, "seg_001")
    chars = manager.notes["core_facts"]["characters"]
    assert "沈夜" in chars
    assert chars["沈夜"]["aliases"] == ["夜哥"]
    assert chars["沈夜"]["personality_traits"] == ["坚毅"]
    assert chars["沈夜"]["status"] == "active"
    assert "seg_001" in chars["沈夜"]["segments_seen"]


def test_merge_character_update_accumulates():
    manager = ReadingNotesManager()
    manager.merge_character_updates([{
        "name": "沈夜", "aliases": [], "is_new": True, "status": "active",
        "identity": "调查者", "personality_traits": ["坚毅"], "speech_style": "简练",
        "goals": "追查旧案", "key_actions": ["行动1"], "knowledge_gained": [],
        "quote_examples": ["语录1"],
    }], "seg_001")
    manager.merge_character_updates([{
        "name": "沈夜", "aliases": ["沈公子"], "is_new": False, "status": "active",
        "identity": "调查者", "personality_traits": ["多疑"],
        "speech_style": "简练犀利", "goals": "追查旧案",
        "key_actions": ["行动2"], "knowledge_gained": ["线索A"],
        "quote_examples": ["语录2"],
    }], "seg_002")

    char = manager.notes["core_facts"]["characters"]["沈夜"]
    assert set(char["aliases"]) == {"夜哥", "沈公子"}
    assert set(char["personality_traits"]) == {"坚毅", "多疑"}
    assert len(char["key_actions"]) == 2
    assert "seg_002" in char["segments_seen"]


def test_merge_relationship_changes():
    manager = ReadingNotesManager()
    changes = [
        {
            "source": "沈夜",
            "target": "秦昭",
            "previous_state": "陌生人",
            "new_state": "盟友",
            "trigger": "共同对敌",
            "evidence": "两人联手击退伏击",
        }
    ]
    manager.merge_relationship_changes(changes, "seg_001")
    graph = manager.notes["relationship_graph"]
    assert len(graph) == 1
    assert graph[0]["source"] == "沈夜"
    assert graph[0]["segment_id"] == "seg_001"


def test_merge_plot_threads():
    manager = ReadingNotesManager()
    threads = [
        {"thread": "镜湖旧案", "status": "opened", "detail": "初次发现线索"},
        {"thread": "宗门内斗", "status": "opened", "detail": "暗流涌动"},
    ]
    manager.merge_plot_threads(threads)
    open_threads = manager.notes["plot_state"]["open_threads"]
    assert len(open_threads) == 2

    threads2 = [
        {"thread": "镜湖旧案", "status": "resolved", "detail": "真相大白"},
    ]
    manager.merge_plot_threads(threads2)
    open_threads = manager.notes["plot_state"]["open_threads"]
    assert len(open_threads) == 1
    assert open_threads[0]["thread"] == "宗门内斗"


def test_add_segment_summary():
    manager = ReadingNotesManager()
    manager.add_segment_summary("seg_001", "第一段摘要内容")
    manager.add_segment_summary("seg_002", "第二段摘要内容")
    manager.add_segment_summary("seg_003", "第三段摘要内容")
    # Only last 2 kept in recent
    recent = manager.notes["plot_state"]["recent_segment_summaries"]
    assert len(recent) == 2
    assert recent[0]["segment_id"] == "seg_002"
    assert recent[1]["segment_id"] == "seg_003"
    # All are in all_segment_summaries
    assert len(manager.all_segment_summaries) == 3


def test_arc_summary_trigger():
    manager = ReadingNotesManager(arc_interval=3)
    for i in range(1, 7):
        manager.add_segment_summary(f"seg_{i:03d}", f"段落{i}摘要")
    # After 6 segments with interval=3, should need arc summaries at segments 3 and 6
    assert manager.needs_arc_summary() is False  # Already past the boundary, but _pending stays
    # Simulate: check pending arc segments
    pending = manager.pending_arc_segments()
    # After adding 6 summaries with interval 3, arcs should cover [1-3] and [4-6]
    assert len(pending) >= 1


def test_add_arc_summary():
    manager = ReadingNotesManager(arc_interval=3)
    for i in range(1, 4):
        manager.add_segment_summary(f"seg_{i:03d}", f"段落{i}摘要")
    manager.add_arc_summary("arc_001", "前三段弧线摘要", covered_segments=["seg_001", "seg_002", "seg_003"])
    arcs = manager.notes["plot_state"]["arc_summaries"]
    assert len(arcs) == 1
    assert arcs[0]["arc_id"] == "arc_001"


def test_context_assembly_short_novel():
    manager = ReadingNotesManager()
    manager.merge_character_updates([{
        "name": "沈夜", "aliases": [], "is_new": True, "status": "active",
        "identity": "主角", "personality_traits": ["坚毅"],
        "speech_style": "简练", "goals": "调查", "key_actions": ["探索"],
        "knowledge_gained": [], "quote_examples": [],
    }], "seg_001")
    manager.add_segment_summary("seg_001", "第一段发生了...")
    context = manager.assemble_context()
    assert "沈夜" in context
    assert "第一段发生了" in context


def test_save_and_load(tmp_path):
    manager = ReadingNotesManager()
    manager.merge_character_updates([{
        "name": "沈夜", "aliases": [], "is_new": True, "status": "active",
        "identity": "主角", "personality_traits": [], "speech_style": "",
        "goals": "", "key_actions": [], "knowledge_gained": [],
        "quote_examples": [],
    }], "seg_001")
    save_path = str(tmp_path / "reading_notes.json")
    manager.save(save_path)
    assert os.path.exists(save_path)

    loaded = ReadingNotesManager.load(save_path)
    assert "沈夜" in loaded.notes["core_facts"]["characters"]


def test_merge_world_building():
    manager = ReadingNotesManager()
    facts = [
        {"fact": "此世界有五大宗门", "evidence": "开篇世界观介绍"},
    ]
    manager.merge_world_building(facts)
    rules = manager.notes["core_facts"]["world_rules"]
    assert len(rules) == 1
    assert "五大宗门" in rules[0]["fact"]


def test_merge_organizations():
    manager = ReadingNotesManager()
    # Organizations come from character_updates implicitly, but also from world_building
    # Test via explicit organization merge
    manager.merge_organization("玄霄宗", {
        "type": "宗门", "status": "active",
        "members_mentioned": ["沈夜"], "purpose": "修行",
    }, "seg_001")
    orgs = manager.notes["core_facts"]["organizations"]
    assert "玄霄宗" in orgs
    assert orgs["玄霄宗"]["type"] == "宗门"
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd /root/novelwork/backend && PYTHONPATH=$(pwd) pytest tests/test_reading_notes_manager.py -v`
Expected: FAIL with `ModuleNotFoundError`

- [ ] **Step 3: Write the implementation**

Create `backend/app/services/reading_notes_manager.py`:

```python
"""Reading notes manager: maintains structured notes during sequential reading."""

from __future__ import annotations

import json
from typing import Any, Dict, List, Optional, Sequence


class ReadingNotesManager:
    """Manages the three-tier ReadingNotes structure with merge protocol and milestones."""

    def __init__(self, arc_interval: int = 5, volume_arc_threshold: int = 10):
        self.arc_interval = arc_interval
        self.volume_arc_threshold = volume_arc_threshold
        self.all_segment_summaries: List[Dict[str, str]] = []
        self._arc_cursor = 0  # index into all_segment_summaries for next arc
        self.notes: Dict[str, Any] = {
            "core_facts": {
                "characters": {},
                "organizations": {},
                "world_rules": [],
                "key_locations": {},
            },
            "relationship_graph": [],
            "plot_state": {
                "arc_summaries": [],
                "volume_summaries": [],
                "recent_segment_summaries": [],
                "open_threads": [],
                "narrative_phase": "",
            },
        }

    # ── Character updates ──

    def merge_character_updates(
        self, updates: Sequence[Dict[str, Any]], segment_id: str
    ) -> None:
        chars = self.notes["core_facts"]["characters"]
        for update in updates:
            name = update.get("name", "").strip()
            if not name:
                continue
            if name not in chars:
                chars[name] = {
                    "aliases": [],
                    "status": "unknown",
                    "identity": "",
                    "first_seen": segment_id,
                    "personality_traits": [],
                    "speech_style": "",
                    "goals": "",
                    "key_actions": [],
                    "knowledge_gained": [],
                    "quote_examples": [],
                    "segments_seen": [],
                    "status_history": [],
                }
            char = chars[name]
            # Accumulate aliases (deduplicated)
            for alias in update.get("aliases", []):
                if alias and alias not in char["aliases"]:
                    char["aliases"].append(alias)
            # Accumulate traits (deduplicated)
            for trait in update.get("personality_traits", []):
                if trait and trait not in char["personality_traits"]:
                    char["personality_traits"].append(trait)
            # Update status with history
            new_status = update.get("status", "")
            if new_status and new_status != char["status"]:
                if char["status"] != "unknown":
                    char["status_history"].append({
                        "from": char["status"],
                        "to": new_status,
                        "segment_id": segment_id,
                    })
                char["status"] = new_status
            # Overwrite scalar fields if non-empty
            for field in ("identity", "speech_style", "goals"):
                value = update.get(field, "")
                if value:
                    char[field] = value
            # Accumulate list fields
            for field in ("key_actions", "knowledge_gained", "quote_examples"):
                for item in update.get(field, []):
                    if item:
                        char[field].append(item)
            # Track segment appearance
            if segment_id not in char["segments_seen"]:
                char["segments_seen"].append(segment_id)

    # ── Organization updates ──

    def merge_organization(
        self, name: str, data: Dict[str, Any], segment_id: str
    ) -> None:
        orgs = self.notes["core_facts"]["organizations"]
        if name not in orgs:
            orgs[name] = {
                "type": "",
                "status": "active",
                "members_mentioned": [],
                "purpose": "",
                "first_seen": segment_id,
                "segments_seen": [],
            }
        org = orgs[name]
        for field in ("type", "status", "purpose"):
            value = data.get(field, "")
            if value:
                org[field] = value
        for member in data.get("members_mentioned", []):
            if member and member not in org["members_mentioned"]:
                org["members_mentioned"].append(member)
        if segment_id not in org["segments_seen"]:
            org["segments_seen"].append(segment_id)

    # ── Relationship changes ──

    def merge_relationship_changes(
        self, changes: Sequence[Dict[str, Any]], segment_id: str
    ) -> None:
        graph = self.notes["relationship_graph"]
        for change in changes:
            entry = {
                "source": change.get("source", ""),
                "target": change.get("target", ""),
                "relation": change.get("new_state", ""),
                "previous_state": change.get("previous_state", ""),
                "trigger": change.get("trigger", ""),
                "evidence": change.get("evidence", ""),
                "segment_id": segment_id,
            }
            graph.append(entry)

    # ── World building ──

    def merge_world_building(self, facts: Sequence[Dict[str, Any]]) -> None:
        rules = self.notes["core_facts"]["world_rules"]
        for item in facts:
            fact_text = item.get("fact", "").strip()
            if fact_text and not any(r.get("fact") == fact_text for r in rules):
                rules.append({
                    "fact": fact_text,
                    "evidence": item.get("evidence", ""),
                })

    # ── Plot state ──

    def merge_plot_threads(self, threads: Sequence[Dict[str, Any]]) -> None:
        open_threads = self.notes["plot_state"]["open_threads"]
        for thread_update in threads:
            thread_name = thread_update.get("thread", "")
            status = thread_update.get("status", "")
            if status == "resolved":
                open_threads[:] = [t for t in open_threads if t.get("thread") != thread_name]
            elif status in ("opened", "progressed"):
                existing = next((t for t in open_threads if t.get("thread") == thread_name), None)
                if existing:
                    existing["detail"] = thread_update.get("detail", existing.get("detail", ""))
                    existing["status"] = status
                else:
                    open_threads.append({
                        "thread": thread_name,
                        "status": status,
                        "detail": thread_update.get("detail", ""),
                    })

    def update_narrative_phase(self, phase: str) -> None:
        if phase:
            self.notes["plot_state"]["narrative_phase"] = phase

    # ── Segment summaries ──

    def add_segment_summary(self, segment_id: str, summary: str) -> None:
        self.all_segment_summaries.append({
            "segment_id": segment_id,
            "summary": summary,
        })
        # Keep only last 2 in recent
        recent = self.notes["plot_state"]["recent_segment_summaries"]
        recent.append({"segment_id": segment_id, "summary": summary})
        if len(recent) > 2:
            self.notes["plot_state"]["recent_segment_summaries"] = recent[-2:]

    # ── Arc summaries ──

    def needs_arc_summary(self) -> bool:
        uncovered = len(self.all_segment_summaries) - self._arc_cursor
        return uncovered >= self.arc_interval

    def pending_arc_segments(self) -> List[Dict[str, str]]:
        """Return segment summaries that should be covered by the next arc summary."""
        if not self.needs_arc_summary():
            return []
        return self.all_segment_summaries[self._arc_cursor:self._arc_cursor + self.arc_interval]

    def add_arc_summary(
        self, arc_id: str, summary: str, covered_segments: List[str]
    ) -> None:
        self.notes["plot_state"]["arc_summaries"].append({
            "arc_id": arc_id,
            "summary": summary,
            "covered_segments": covered_segments,
        })
        self._arc_cursor += len(covered_segments)

    # ── Volume summaries ──

    def needs_volume_summary(self) -> bool:
        return len(self.notes["plot_state"]["arc_summaries"]) >= self.volume_arc_threshold

    def add_volume_summary(self, volume_id: str, summary: str, covered_arcs: List[str]) -> None:
        self.notes["plot_state"]["volume_summaries"].append({
            "volume_id": volume_id,
            "summary": summary,
            "covered_arcs": covered_arcs,
        })

    # ── Context assembly ──

    def assemble_context(self) -> str:
        """Assemble reading notes into a text context for the next LLM call."""
        parts = []

        # Core facts
        parts.append("## 已知角色")
        chars = self.notes["core_facts"]["characters"]
        if chars:
            for name, data in chars.items():
                aliases_str = f"（别名：{'、'.join(data['aliases'])}）" if data.get("aliases") else ""
                traits_str = f"，性格：{'、'.join(data['personality_traits'])}" if data.get("personality_traits") else ""
                parts.append(f"- {name}{aliases_str}：{data.get('identity', '未知')}，状态 {data.get('status', 'unknown')}{traits_str}")
        else:
            parts.append("（尚无角色记录）")

        orgs = self.notes["core_facts"]["organizations"]
        if orgs:
            parts.append("\n## 已知组织")
            for name, data in orgs.items():
                parts.append(f"- {name}：{data.get('type', '')}，{data.get('purpose', '')}")

        rules = self.notes["core_facts"]["world_rules"]
        if rules:
            parts.append("\n## 世界规则")
            for rule in rules:
                parts.append(f"- {rule['fact']}")

        # Relationship graph (last 50 entries to control size)
        graph = self.notes["relationship_graph"]
        if graph:
            parts.append("\n## 关系变化记录")
            for entry in graph[-50:]:
                parts.append(f"- {entry['source']} → {entry['target']}：{entry.get('relation', '')}（{entry.get('trigger', '')}）")

        # Plot state
        plot = self.notes["plot_state"]

        # Volume summaries
        if plot["volume_summaries"]:
            parts.append("\n## 卷摘要")
            for vol in plot["volume_summaries"]:
                parts.append(f"### {vol['volume_id']}\n{vol['summary']}")

        # Arc summaries
        segment_count = len(self.all_segment_summaries)
        if segment_count > 10 and plot["arc_summaries"]:
            # Medium/long novel: show arc summaries
            parts.append("\n## 弧线摘要")
            for arc in plot["arc_summaries"]:
                parts.append(f"### {arc['arc_id']}\n{arc['summary']}")
        elif self.all_segment_summaries:
            # Short novel: show all segment summaries
            parts.append("\n## 段落摘要")
            for seg_sum in self.all_segment_summaries:
                parts.append(f"- [{seg_sum['segment_id']}] {seg_sum['summary']}")

        # Recent segment detail (always included for medium+ novels)
        if segment_count > 10 and plot["recent_segment_summaries"]:
            parts.append("\n## 最近段落详情")
            for seg_sum in plot["recent_segment_summaries"]:
                parts.append(f"- [{seg_sum['segment_id']}] {seg_sum['summary']}")

        # Open threads
        if plot["open_threads"]:
            parts.append("\n## 未解决的剧情线")
            for thread in plot["open_threads"]:
                parts.append(f"- {thread['thread']}：{thread.get('detail', '')}")

        if plot["narrative_phase"]:
            parts.append(f"\n当前叙事阶段：{plot['narrative_phase']}")

        return "\n".join(parts)

    # ── Persistence ──

    def save(self, path: str) -> None:
        data = {
            "notes": self.notes,
            "all_segment_summaries": self.all_segment_summaries,
            "arc_cursor": self._arc_cursor,
        }
        with open(path, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)

    @classmethod
    def load(cls, path: str) -> ReadingNotesManager:
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)
        manager = cls()
        manager.notes = data["notes"]
        manager.all_segment_summaries = data.get("all_segment_summaries", [])
        manager._arc_cursor = data.get("arc_cursor", 0)
        return manager
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd /root/novelwork/backend && PYTHONPATH=$(pwd) pytest tests/test_reading_notes_manager.py -v`
Expected: All 13 tests PASS

- [ ] **Step 5: Commit**

```bash
git add backend/app/services/reading_notes_manager.py backend/tests/test_reading_notes_manager.py
git commit -m "feat: add ReadingNotesManager for sequential reading memory"
```

---

## Task 3: Sequential Reader Prompts + Sequential Reader

**Files:**
- Create: `backend/app/services/sequential_reader_prompts.py`
- Create: `backend/app/services/sequential_reader.py`
- Test: `backend/tests/test_sequential_reader.py`
- Depends on: Task 1 (SmartNovelSegmenter), Task 2 (ReadingNotesManager)

### Overview
The sequential reader iterates over segments, calls the LLM for each one with assembled context, merges results into reading notes, and triggers arc/volume summaries at milestones.

- [ ] **Step 1: Write the prompts file**

Create `backend/app/services/sequential_reader_prompts.py`:

```python
"""Prompts for sequential deep reading and arc/volume summary generation."""

SEGMENT_READING_SYSTEM_PROMPT = """\
你是一名专业的小说分析师，正在顺序精读一部小说。

你会收到：
1. 之前阅读的笔记（包含已识别的角色、关系、剧情进展）
2. 当前阅读段的完整正文

请以读者的视角分析当前段，输出以下 JSON：

{
  "segment_summary": "200-400字总结当前段核心剧情",

  "character_updates": [
    {
      "name": "角色名",
      "aliases": ["别名1", "称号1"],
      "is_new": true或false,
      "status": "active/dead/injured/missing/unknown",
      "identity": "简要身份描述",
      "personality_traits": ["特质1", "特质2"],
      "speech_style": "说话方式描述",
      "goals": "当前动机",
      "key_actions": ["本段的关键行动"],
      "knowledge_gained": ["本段获得的信息"],
      "quote_examples": ["从文本中摘录的代表性对话"]
    }
  ],

  "relationship_changes": [
    {
      "source": "角色A",
      "target": "角色B",
      "previous_state": "之前的关系",
      "new_state": "本段之后的关系",
      "trigger": "导致变化的原因",
      "evidence": "文本证据"
    }
  ],

  "plot_threads": [
    {
      "thread": "剧情线描述",
      "status": "opened/progressed/resolved",
      "detail": "进展详情"
    }
  ],

  "world_building": [
    {"fact": "新揭示的世界观细节", "evidence": "文本证据"}
  ],

  "consistency_notes": ["矛盾或值得注意的点"],

  "narrative_phase": "setup/development/conflict/climax/turning_point/resolution"
}

重要规则：
- 角色名使用文中的主要称呼，别名放在aliases中
- 对已有角色，仅输出本段有变化或新信息的字段
- personality_traits和quote_examples是累积的，只输出本段新发现的
- 如果某个角色在本段没有新信息，不要输出该角色
- relationship_changes只输出本段发生变化的关系
- 确保JSON格式正确，所有字符串用双引号
"""

ARC_SUMMARY_SYSTEM_PROMPT = """\
你是一名小说分析师，需要将多段阅读摘要整合为一个弧线摘要。

你会收到：
1. 已知的核心角色和组织信息
2. 连续几段的摘要

请输出一个约800字的弧线摘要JSON：

{
  "arc_summary": "整合这几段的核心剧情发展、角色变化和关系演变。保留关键事件和转折点。约800字。"
}

规则：
- 保留所有关键事件和转折点
- 保留角色状态变化（如死亡、受伤、背叛）
- 保留新揭示的重要信息
- 不要遗漏对后续剧情有影响的伏笔
"""

VOLUME_SUMMARY_SYSTEM_PROMPT = """\
你是一名小说分析师，需要将多个弧线摘要整合为一个卷摘要。

你会收到多个弧线摘要，请整合为约2000字的卷摘要JSON：

{
  "volume_summary": "整合所有弧线的核心发展。保留主线推进、关键转折、角色成长和关系演变。约2000字。"
}
"""


def build_segment_reading_prompt(context: str, segment_text: str) -> list:
    """Build messages for a segment reading LLM call."""
    return [
        {"role": "system", "content": SEGMENT_READING_SYSTEM_PROMPT},
        {"role": "user", "content": f"## 之前的阅读笔记\n\n{context}\n\n---\n\n## 当前段正文\n\n{segment_text}"},
    ]


def build_arc_summary_prompt(core_facts_context: str, segment_summaries: list) -> list:
    """Build messages for an arc summary LLM call."""
    summaries_text = "\n".join(
        f"- [{s['segment_id']}] {s['summary']}" for s in segment_summaries
    )
    return [
        {"role": "system", "content": ARC_SUMMARY_SYSTEM_PROMPT},
        {"role": "user", "content": f"## 核心信息\n\n{core_facts_context}\n\n## 段落摘要\n\n{summaries_text}"},
    ]


def build_volume_summary_prompt(arc_summaries: list) -> list:
    """Build messages for a volume summary LLM call."""
    arcs_text = "\n\n".join(
        f"### {a['arc_id']}\n{a['summary']}" for a in arc_summaries
    )
    return [
        {"role": "system", "content": VOLUME_SUMMARY_SYSTEM_PROMPT},
        {"role": "user", "content": f"## 弧线摘要\n\n{arcs_text}"},
    ]
```

- [ ] **Step 2: Write the sequential reader**

Create `backend/app/services/sequential_reader.py`:

```python
"""Sequential deep reader: reads novel segments one by one with LLM analysis."""

from __future__ import annotations

import logging
from typing import Any, Callable, Dict, List, Optional, Sequence

from .llm_router import LlmRouter
from .reading_notes_manager import ReadingNotesManager
from .sequential_reader_prompts import (
    build_arc_summary_prompt,
    build_segment_reading_prompt,
    build_volume_summary_prompt,
)

logger = logging.getLogger(__name__)

MODULE_KEY = "sequential_reading"


class SequentialReader:
    """Reads novel segments sequentially, maintaining reading notes."""

    def __init__(
        self,
        llm_router: Optional[LlmRouter] = None,
        arc_interval: int = 5,
        volume_arc_threshold: int = 10,
    ):
        self.llm_router = llm_router or LlmRouter()
        self.arc_interval = arc_interval
        self.volume_arc_threshold = volume_arc_threshold

    def read(
        self,
        segments: Sequence[Dict[str, Any]],
        use_llm: bool = True,
        progress_callback: Optional[Callable[[str, Dict[str, Any]], None]] = None,
    ) -> ReadingNotesManager:
        """Read all segments sequentially, returning the completed reading notes."""
        manager = ReadingNotesManager(
            arc_interval=self.arc_interval,
            volume_arc_threshold=self.volume_arc_threshold,
        )

        if not use_llm:
            return self._offline_read(segments, manager, progress_callback)

        client = self.llm_router.build_client(MODULE_KEY)
        total = len(segments)

        for i, segment in enumerate(segments):
            segment_id = segment.get("segment_id", f"seg_{i + 1:03d}")
            segment_text = self._extract_segment_text(segment)

            if progress_callback:
                progress_callback("segment_start", {
                    "segment_id": segment_id,
                    "segment_index": i,
                    "total_segments": total,
                })

            # Assemble context and call LLM
            context = manager.assemble_context()
            messages = build_segment_reading_prompt(context, segment_text)
            result = client.chat_json_value(messages, temperature=0.3, max_tokens=8192)

            # Merge results into notes
            self._merge_segment_result(manager, result, segment_id)

            if progress_callback:
                progress_callback("segment_end", {
                    "segment_id": segment_id,
                    "segment_index": i,
                    "total_segments": total,
                })

            # Check for arc summary milestone
            while manager.needs_arc_summary():
                self._generate_arc_summary(client, manager)

        return manager

    def _merge_segment_result(
        self, manager: ReadingNotesManager, result: Dict[str, Any], segment_id: str
    ) -> None:
        """Merge a single segment's LLM output into the reading notes."""
        manager.merge_character_updates(result.get("character_updates", []), segment_id)
        manager.merge_relationship_changes(result.get("relationship_changes", []), segment_id)
        manager.merge_plot_threads(result.get("plot_threads", []))
        manager.merge_world_building(result.get("world_building", []))
        manager.update_narrative_phase(result.get("narrative_phase", ""))
        manager.add_segment_summary(segment_id, result.get("segment_summary", ""))

    def _generate_arc_summary(self, client: Any, manager: ReadingNotesManager) -> None:
        """Generate an arc summary from pending segment summaries."""
        pending = manager.pending_arc_segments()
        if not pending:
            return

        arc_index = len(manager.notes["plot_state"]["arc_summaries"]) + 1
        arc_id = f"arc_{arc_index:03d}"

        # Build core facts context (abbreviated)
        core_context = manager.assemble_context().split("\n## 段落摘要")[0]
        messages = build_arc_summary_prompt(core_context, pending)
        result = client.chat_json_value(messages, temperature=0.3, max_tokens=4096)

        summary = result.get("arc_summary", "")
        covered = [s["segment_id"] for s in pending]
        manager.add_arc_summary(arc_id, summary, covered)

        logger.info("Generated arc summary %s covering %d segments", arc_id, len(covered))

    def _offline_read(
        self,
        segments: Sequence[Dict[str, Any]],
        manager: ReadingNotesManager,
        progress_callback: Optional[Callable] = None,
    ) -> ReadingNotesManager:
        """Offline mode: create minimal reading notes without LLM."""
        total = len(segments)
        for i, segment in enumerate(segments):
            segment_id = segment.get("segment_id", f"seg_{i + 1:03d}")
            segment_text = self._extract_segment_text(segment)

            if progress_callback:
                progress_callback("segment_start", {
                    "segment_id": segment_id,
                    "segment_index": i,
                    "total_segments": total,
                })

            # Basic offline extraction: just note chapter titles
            for chapter in segment.get("chapters", []):
                title = chapter.get("title", "")
                if title:
                    manager.add_segment_summary(segment_id, f"章节：{title}")

            if progress_callback:
                progress_callback("segment_end", {
                    "segment_id": segment_id,
                    "segment_index": i,
                    "total_segments": total,
                })

        return manager

    def _extract_segment_text(self, segment: Dict[str, Any]) -> str:
        """Extract full text from a segment's chapters."""
        chapters = segment.get("chapters", [])
        if not chapters:
            return ""
        parts = []
        for chapter in chapters:
            title = chapter.get("title", "")
            content = chapter.get("content", "")
            if title:
                parts.append(f"## {title}\n\n{content}")
            else:
                parts.append(content)
        return "\n\n".join(parts)
```

- [ ] **Step 3: Write the failing tests**

Create `backend/tests/test_sequential_reader.py`:

```python
"""SequentialReader integration tests with fake LLM."""

from app.services.reading_notes_manager import ReadingNotesManager
from app.services.sequential_reader import SequentialReader
from app.services.smart_novel_segmenter import SmartNovelSegmenter


class FakeSequentialReadingClient:
    """Fake LLM client for sequential reading tests."""

    def __init__(self):
        self.call_count = 0

    def chat_json_value(self, messages, temperature=0.3, max_tokens=8192):
        self.call_count += 1
        user_msg = messages[-1]["content"]

        if "弧线摘要" in messages[0]["content"]:
            return {"arc_summary": f"弧线{self.call_count}：综合前几段剧情发展。"}

        if "卷摘要" in messages[0]["content"]:
            return {"volume_summary": f"卷{self.call_count}：整体剧情概述。"}

        # Segment reading
        return {
            "segment_summary": f"段落{self.call_count}摘要：剧情发展。",
            "character_updates": [
                {
                    "name": "沈夜",
                    "aliases": ["夜哥"] if self.call_count == 1 else [],
                    "is_new": self.call_count == 1,
                    "status": "active",
                    "identity": "调查者",
                    "personality_traits": ["坚毅"] if self.call_count == 1 else [],
                    "speech_style": "简练犀利",
                    "goals": "追查镜湖旧案",
                    "key_actions": [f"行动{self.call_count}"],
                    "knowledge_gained": [],
                    "quote_examples": [],
                },
            ],
            "relationship_changes": [
                {
                    "source": "沈夜",
                    "target": "玄霄宗",
                    "previous_state": "敌对",
                    "new_state": "冲突",
                    "trigger": "宗门施压",
                    "evidence": "对峙场景",
                },
            ] if self.call_count == 1 else [],
            "plot_threads": [
                {"thread": "镜湖旧案", "status": "opened" if self.call_count == 1 else "progressed", "detail": f"进展{self.call_count}"},
            ],
            "world_building": [
                {"fact": "五大宗门体系", "evidence": "开篇介绍"},
            ] if self.call_count == 1 else [],
            "consistency_notes": [],
            "narrative_phase": "development",
        }


class FakeRouterForReading:
    def build_client(self, module_key):
        assert module_key == "sequential_reading"
        return FakeSequentialReadingClient()


def _make_segments(count=3):
    """Create test segments."""
    segments = []
    for i in range(1, count + 1):
        segments.append({
            "segment_id": f"seg_{i:03d}",
            "chapters": [
                {
                    "chapter_id": f"chapter_{i:04d}",
                    "order": i,
                    "title": f"第{i}章 测试",
                    "content": f"第{i}章的内容。沈夜继续调查。" * 100,
                }
            ],
            "chapter_range": str(i),
            "estimated_tokens": 5000,
        })
    return segments


def test_sequential_read_produces_reading_notes():
    reader = SequentialReader(llm_router=FakeRouterForReading(), arc_interval=5)
    segments = _make_segments(3)
    manager = reader.read(segments, use_llm=True)
    chars = manager.notes["core_facts"]["characters"]
    assert "沈夜" in chars
    assert chars["沈夜"]["status"] == "active"
    assert "夜哥" in chars["沈夜"]["aliases"]
    assert len(manager.all_segment_summaries) == 3


def test_sequential_read_progress_callback():
    events = []

    def callback(event_type, data):
        events.append((event_type, data))

    reader = SequentialReader(llm_router=FakeRouterForReading(), arc_interval=5)
    segments = _make_segments(2)
    reader.read(segments, use_llm=True, progress_callback=callback)
    start_events = [e for e in events if e[0] == "segment_start"]
    end_events = [e for e in events if e[0] == "segment_end"]
    assert len(start_events) == 2
    assert len(end_events) == 2


def test_sequential_read_offline_mode():
    reader = SequentialReader(arc_interval=5)
    segments = _make_segments(2)
    manager = reader.read(segments, use_llm=False)
    assert len(manager.all_segment_summaries) >= 2


def test_arc_summary_triggered():
    """With arc_interval=2, reading 4 segments should trigger 2 arc summaries."""
    reader = SequentialReader(llm_router=FakeRouterForReading(), arc_interval=2)
    segments = _make_segments(4)
    manager = reader.read(segments, use_llm=True)
    arcs = manager.notes["plot_state"]["arc_summaries"]
    assert len(arcs) == 2


def test_end_to_end_with_segmenter():
    """Full flow: segment chapters then read sequentially."""
    segmenter = SmartNovelSegmenter(target_token_limit=10000)
    chapters = [
        {
            "chapter_id": f"chapter_{i:04d}",
            "order": i,
            "title": f"第{i}章",
            "content": f"第{i}章内容。沈夜继续追查。" * 200,
            "word_count": 2000,
        }
        for i in range(1, 6)
    ]
    seg_result = segmenter.segment(chapters)
    reader = SequentialReader(llm_router=FakeRouterForReading(), arc_interval=5)
    manager = reader.read(seg_result["segments"], use_llm=True)
    assert "沈夜" in manager.notes["core_facts"]["characters"]
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd /root/novelwork/backend && PYTHONPATH=$(pwd) pytest tests/test_sequential_reader.py -v`
Expected: All 5 tests PASS

- [ ] **Step 5: Commit**

```bash
git add backend/app/services/sequential_reader_prompts.py backend/app/services/sequential_reader.py backend/tests/test_sequential_reader.py
git commit -m "feat: add SequentialReader for LLM-driven sequential novel reading"
```

---

## Task 4: CharacterAgentProfileGenerator

**Files:**
- Create: `backend/app/services/character_agent_prompts.py`
- Create: `backend/app/services/character_agent_profile_generator.py`
- Test: `backend/tests/test_character_agent_profile_generator.py`
- Depends on: Task 2 (ReadingNotesManager, for input data structure)

### Overview
Generates agent-ready character profiles concurrently for each important character.

- [ ] **Step 1: Write the prompts file**

Create `backend/app/services/character_agent_prompts.py`:

```python
"""Prompts for per-character agent profile generation."""

CHARACTER_PROFILE_SYSTEM_PROMPT = """\
你是一名角色档案构建专家。根据提供的小说阅读笔记，为指定角色生成一份完整的 Agent 角色档案。

输出以下 JSON 结构：

{
  "basic_info": {
    "name": "",
    "aliases": [],
    "identity": "",
    "status": "alive/dead/injured/missing/unknown"
  },
  "personality": {
    "core_traits": ["特质1", "特质2"],
    "values": ["价值观1"],
    "fears": ["恐惧"],
    "decision_pattern": "决策风格描述"
  },
  "speech": {
    "style": "简洁而锐利，少用比喻",
    "verbal_habits": ["口头禅"],
    "tone_range": "通常冷淡，在...时变得激昂",
    "example_quotes": ["语录1", "语录2"]
  },
  "relationships": [
    {
      "target": "角色B",
      "current_state": "复杂的对手关系",
      "evolution": ["初始敌意", "被迫合作", "不情愿的尊重"],
      "attitude": "表面冷淡实则认可"
    }
  ],
  "capabilities": {
    "skills": ["剑术"],
    "limitations": ["社交能力差"],
    "resources": ["持有X神器"]
  },
  "knowledge_boundary": {
    "knows": ["X的真相"],
    "does_not_know": ["Y是间谍"],
    "believes_wrongly": ["以为Z已死"]
  },
  "motivation": {
    "ultimate_goal": "...",
    "current_objective": "...",
    "internal_conflict": "..."
  }
}

规则：
- 严格基于提供的阅读笔记信息，不要编造笔记中没有的内容
- relationships中只包含在笔记中有记录的关系
- knowledge_boundary要区分角色视角和读者视角
- 语录尽量使用笔记中记录的原文
"""


def build_character_profile_prompt(
    character_name: str,
    character_data: dict,
    relationship_entries: list,
    story_summary: str,
) -> list:
    """Build messages for a character profile generation LLM call."""
    char_section = _format_character_data(character_name, character_data)
    rel_section = _format_relationships(character_name, relationship_entries)

    user_content = (
        f"## 故事概要\n\n{story_summary}\n\n"
        f"## 角色信息\n\n{char_section}\n\n"
        f"## 关系记录\n\n{rel_section}\n\n"
        f"请为【{character_name}】生成完整的 Agent 角色档案。"
    )
    return [
        {"role": "system", "content": CHARACTER_PROFILE_SYSTEM_PROMPT},
        {"role": "user", "content": user_content},
    ]


def _format_character_data(name: str, data: dict) -> str:
    lines = [f"角色名：{name}"]
    if data.get("aliases"):
        lines.append(f"别名：{'、'.join(data['aliases'])}")
    lines.append(f"身份：{data.get('identity', '未知')}")
    lines.append(f"状态：{data.get('status', 'unknown')}")
    if data.get("personality_traits"):
        lines.append(f"性格特质：{'、'.join(data['personality_traits'])}")
    if data.get("speech_style"):
        lines.append(f"说话风格：{data['speech_style']}")
    if data.get("goals"):
        lines.append(f"目标：{data['goals']}")
    if data.get("key_actions"):
        lines.append("关键行动：")
        for action in data["key_actions"][-10:]:  # Last 10
            lines.append(f"  - {action}")
    if data.get("knowledge_gained"):
        lines.append("获得的信息：")
        for info in data["knowledge_gained"][-10:]:
            lines.append(f"  - {info}")
    if data.get("quote_examples"):
        lines.append("代表性台词：")
        for quote in data["quote_examples"][-5:]:
            lines.append(f"  - 「{quote}」")
    return "\n".join(lines)


def _format_relationships(name: str, entries: list) -> str:
    if not entries:
        return "（无关系记录）"
    lines = []
    for entry in entries:
        lines.append(
            f"- {entry.get('source', '')} → {entry.get('target', '')}："
            f"{entry.get('relation', '')}（{entry.get('trigger', '')}）"
        )
    return "\n".join(lines)
```

- [ ] **Step 2: Write the generator**

Create `backend/app/services/character_agent_profile_generator.py`:

```python
"""Character agent profile generator: creates agent-ready profiles from reading notes."""

from __future__ import annotations

import logging
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import Any, Callable, Dict, List, Optional

from .character_agent_prompts import build_character_profile_prompt
from .llm_router import LlmRouter
from .reading_notes_manager import ReadingNotesManager

logger = logging.getLogger(__name__)

MODULE_KEY = "character_agent_profile"
DEFAULT_IMPORTANCE_THRESHOLD = 2  # Minimum segment appearances


class CharacterAgentProfileGenerator:
    """Generates agent-ready profiles for important characters."""

    def __init__(
        self,
        llm_router: Optional[LlmRouter] = None,
        importance_threshold: int = DEFAULT_IMPORTANCE_THRESHOLD,
        max_workers: int = 10,
    ):
        self.llm_router = llm_router or LlmRouter()
        self.importance_threshold = importance_threshold
        self.max_workers = max_workers

    def generate(
        self,
        manager: ReadingNotesManager,
        use_llm: bool = True,
        progress_callback: Optional[Callable[[str, Dict[str, Any]], None]] = None,
    ) -> Dict[str, Any]:
        """Generate agent profiles for all important characters."""
        characters = manager.notes["core_facts"]["characters"]
        graph = manager.notes["relationship_graph"]

        important = self._select_important_characters(characters)

        if not use_llm or not important:
            return self._offline_profiles(important, characters)

        story_summary = self._build_story_summary(manager)
        client = self.llm_router.build_client(MODULE_KEY)
        profiles: Dict[str, Any] = {}

        total = len(important)
        if progress_callback:
            progress_callback("profiles_start", {"total": total})

        with ThreadPoolExecutor(max_workers=min(self.max_workers, total)) as pool:
            futures = {}
            for name in important:
                char_data = characters[name]
                char_rels = [
                    e for e in graph
                    if e.get("source") == name or e.get("target") == name
                ]
                messages = build_character_profile_prompt(name, char_data, char_rels, story_summary)
                future = pool.submit(
                    client.chat_json_value, messages, 0.3, 4096
                )
                futures[future] = name

            for future in as_completed(futures):
                name = futures[future]
                try:
                    result = future.result()
                    profiles[name] = result
                except Exception:
                    logger.exception("Failed to generate profile for %s", name)
                    profiles[name] = self._minimal_profile(name, characters.get(name, {}))

                if progress_callback:
                    progress_callback("profile_done", {
                        "name": name,
                        "completed": len(profiles),
                        "total": total,
                    })

        return {"profiles": profiles, "profile_count": len(profiles)}

    def _select_important_characters(self, characters: Dict[str, Any]) -> List[str]:
        """Select characters that meet the importance threshold."""
        important = []
        for name, data in characters.items():
            segment_count = len(data.get("segments_seen", []))
            if segment_count >= self.importance_threshold:
                important.append(name)
        # Sort by segment count descending
        important.sort(
            key=lambda n: len(characters[n].get("segments_seen", [])),
            reverse=True,
        )
        return important

    def _build_story_summary(self, manager: ReadingNotesManager) -> str:
        """Build a story summary from arc summaries or segment summaries."""
        arcs = manager.notes["plot_state"]["arc_summaries"]
        if arcs:
            return "\n\n".join(a["summary"] for a in arcs)
        summaries = manager.all_segment_summaries
        if summaries:
            return "\n".join(f"- {s['summary']}" for s in summaries)
        return "（无故事摘要）"

    def _offline_profiles(
        self, names: List[str], characters: Dict[str, Any]
    ) -> Dict[str, Any]:
        """Generate minimal profiles without LLM."""
        profiles = {}
        for name in names:
            profiles[name] = self._minimal_profile(name, characters.get(name, {}))
        return {"profiles": profiles, "profile_count": len(profiles)}

    def _minimal_profile(self, name: str, data: Dict[str, Any]) -> Dict[str, Any]:
        return {
            "basic_info": {
                "name": name,
                "aliases": data.get("aliases", []),
                "identity": data.get("identity", ""),
                "status": data.get("status", "unknown"),
            },
            "personality": {
                "core_traits": data.get("personality_traits", []),
                "values": [],
                "fears": [],
                "decision_pattern": "",
            },
            "speech": {
                "style": data.get("speech_style", ""),
                "verbal_habits": [],
                "tone_range": "",
                "example_quotes": data.get("quote_examples", [])[:3],
            },
            "relationships": [],
            "capabilities": {"skills": [], "limitations": [], "resources": []},
            "knowledge_boundary": {"knows": [], "does_not_know": [], "believes_wrongly": []},
            "motivation": {
                "ultimate_goal": data.get("goals", ""),
                "current_objective": "",
                "internal_conflict": "",
            },
        }
```

- [ ] **Step 3: Write the failing tests**

Create `backend/tests/test_character_agent_profile_generator.py`:

```python
"""CharacterAgentProfileGenerator tests."""

from app.services.character_agent_profile_generator import CharacterAgentProfileGenerator
from app.services.reading_notes_manager import ReadingNotesManager


class FakeProfileClient:
    def chat_json_value(self, messages, temperature=0.3, max_tokens=4096):
        # Extract character name from prompt
        user_msg = messages[-1]["content"]
        name = "沈夜" if "沈夜" in user_msg else "未知"
        return {
            "basic_info": {"name": name, "aliases": ["夜哥"], "identity": "调查者", "status": "alive"},
            "personality": {"core_traits": ["坚毅"], "values": ["正义"], "fears": ["失控"], "decision_pattern": "果断"},
            "speech": {"style": "简练", "verbal_habits": [], "tone_range": "冷淡", "example_quotes": ["..."]},
            "relationships": [{"target": "玄霄宗", "current_state": "敌对", "evolution": ["冲突"], "attitude": "警惕"}],
            "capabilities": {"skills": ["剑术"], "limitations": [], "resources": []},
            "knowledge_boundary": {"knows": ["镜湖真相"], "does_not_know": [], "believes_wrongly": []},
            "motivation": {"ultimate_goal": "揭露真相", "current_objective": "追查旧案", "internal_conflict": ""},
        }


class FakeProfileRouter:
    def build_client(self, module_key):
        assert module_key == "character_agent_profile"
        return FakeProfileClient()


def _manager_with_characters():
    manager = ReadingNotesManager()
    # Add a character that appears in 3 segments (above threshold)
    for seg in ["seg_001", "seg_002", "seg_003"]:
        manager.merge_character_updates([{
            "name": "沈夜", "aliases": ["夜哥"], "is_new": seg == "seg_001",
            "status": "active", "identity": "调查者", "personality_traits": ["坚毅"],
            "speech_style": "简练", "goals": "追查旧案",
            "key_actions": [f"{seg}行动"], "knowledge_gained": [], "quote_examples": [],
        }], seg)
    # Add a minor character (1 segment, below threshold)
    manager.merge_character_updates([{
        "name": "路人甲", "aliases": [], "is_new": True, "status": "active",
        "identity": "路人", "personality_traits": [], "speech_style": "",
        "goals": "", "key_actions": [], "knowledge_gained": [], "quote_examples": [],
    }], "seg_001")
    manager.add_segment_summary("seg_001", "沈夜开始调查。")
    return manager


def test_generate_profiles():
    gen = CharacterAgentProfileGenerator(
        llm_router=FakeProfileRouter(),
        importance_threshold=2,
    )
    manager = _manager_with_characters()
    result = gen.generate(manager, use_llm=True)
    assert "沈夜" in result["profiles"]
    assert "路人甲" not in result["profiles"]  # Below threshold
    profile = result["profiles"]["沈夜"]
    assert profile["basic_info"]["name"] == "沈夜"
    assert result["profile_count"] == 1


def test_generate_profiles_offline():
    gen = CharacterAgentProfileGenerator(importance_threshold=2)
    manager = _manager_with_characters()
    result = gen.generate(manager, use_llm=False)
    assert "沈夜" in result["profiles"]
    profile = result["profiles"]["沈夜"]
    assert profile["basic_info"]["name"] == "沈夜"
    assert profile["personality"]["core_traits"] == ["坚毅"]


def test_progress_callback():
    events = []

    def callback(event_type, data):
        events.append((event_type, data))

    gen = CharacterAgentProfileGenerator(
        llm_router=FakeProfileRouter(),
        importance_threshold=2,
    )
    manager = _manager_with_characters()
    gen.generate(manager, use_llm=True, progress_callback=callback)
    assert any(e[0] == "profiles_start" for e in events)
    assert any(e[0] == "profile_done" for e in events)
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd /root/novelwork/backend && PYTHONPATH=$(pwd) pytest tests/test_character_agent_profile_generator.py -v`
Expected: All 3 tests PASS

- [ ] **Step 5: Commit**

```bash
git add backend/app/services/character_agent_prompts.py backend/app/services/character_agent_profile_generator.py backend/tests/test_character_agent_profile_generator.py
git commit -m "feat: add CharacterAgentProfileGenerator for agent-ready character profiles"
```

---

## Task 5: Update SeedAnalysisAggregator

**Files:**
- Modify: `backend/app/services/seed_analysis_aggregator.py`
- Depends on: Task 2 (ReadingNotesManager)

### Overview
Add a new method `aggregate_from_reading_notes()` that reads from `ReadingNotesManager` output instead of story_memory. Keeps the old `aggregate()` method intact for backward compatibility.

- [ ] **Step 1: Write the failing test**

Add to a new test file `backend/tests/test_seed_analysis_from_reading_notes.py`:

```python
"""Test SeedAnalysisAggregator.aggregate_from_reading_notes."""

from app.services.seed_analysis_aggregator import SeedAnalysisAggregator
from app.services.reading_notes_manager import ReadingNotesManager


def _populated_manager():
    manager = ReadingNotesManager()
    for seg in ["seg_001", "seg_002", "seg_003", "seg_004"]:
        manager.merge_character_updates([{
            "name": "沈夜", "aliases": ["夜哥"], "is_new": seg == "seg_001",
            "status": "active", "identity": "主角调查者",
            "personality_traits": ["坚毅", "多疑"],
            "speech_style": "简练犀利",
            "goals": "追查镜湖旧案",
            "key_actions": [f"{seg}行动"],
            "knowledge_gained": [f"{seg}线索"],
            "quote_examples": ["真相不会自己浮出水面。"] if seg == "seg_001" else [],
        }], seg)
    manager.merge_character_updates([{
        "name": "秦昭", "aliases": [], "is_new": True, "status": "dead",
        "identity": "同伴", "personality_traits": ["忠诚"],
        "speech_style": "温和", "goals": "保护沈夜",
        "key_actions": ["战死"], "knowledge_gained": [], "quote_examples": [],
    }], "seg_001")
    manager.merge_organization("玄霄宗", {
        "type": "宗门", "status": "active",
        "members_mentioned": ["沈夜"], "purpose": "修行",
    }, "seg_001")
    manager.merge_relationship_changes([{
        "source": "沈夜", "target": "秦昭",
        "previous_state": "同伴", "new_state": "已逝同伴",
        "trigger": "秦昭战死", "evidence": "混战中秦昭战死",
    }], "seg_001")
    manager.merge_relationship_changes([{
        "source": "沈夜", "target": "玄霄宗",
        "previous_state": "紧张", "new_state": "冲突",
        "trigger": "宗门施压", "evidence": "对峙",
    }], "seg_002")
    manager.add_segment_summary("seg_001", "沈夜开始调查。")
    manager.add_segment_summary("seg_002", "调查深入。")
    return manager


def test_aggregate_from_reading_notes():
    aggregator = SeedAnalysisAggregator()
    manager = _populated_manager()
    result = aggregator.aggregate_from_reading_notes(
        manager=manager,
        analysis_goal="全面分析",
        project_name="测试项目",
    )
    assert result["project_name"] == "测试项目"
    assert len(result["characters"]) >= 2
    # 沈夜 should be protagonist (4 segments)
    shen = next(c for c in result["characters"] if c["name"] == "沈夜")
    assert shen["importance_tier"] == "protagonist"
    assert "坚毅" in shen.get("personality_traits", [])
    assert shen.get("speech_style") == "简练犀利"
    # Organizations
    assert len(result["organizations"]) >= 1
    # Relations
    assert len(result["relations"]) >= 1
    # Chapter beats from segment summaries
    assert len(result["chapter_beats"]) >= 1


def test_backward_compatible_fields():
    aggregator = SeedAnalysisAggregator()
    manager = _populated_manager()
    result = aggregator.aggregate_from_reading_notes(
        manager=manager,
        analysis_goal="测试",
        project_name="兼容测试",
    )
    # These fields must exist for frontend compatibility
    assert "characters" in result
    assert "organizations" in result
    assert "relations" in result
    assert "chapter_beats" in result
    assert "analysis_summary" in result
    assert "source_stats" in result
    # Each character has backward-compatible fields
    for char in result["characters"]:
        assert "name" in char
        assert "mention_count" in char
        assert "importance_tier" in char
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd /root/novelwork/backend && PYTHONPATH=$(pwd) pytest tests/test_seed_analysis_from_reading_notes.py -v`
Expected: FAIL with `AttributeError: 'SeedAnalysisAggregator' object has no attribute 'aggregate_from_reading_notes'`

- [ ] **Step 3: Add `aggregate_from_reading_notes` method**

Add to `backend/app/services/seed_analysis_aggregator.py` after the existing `aggregate` method (after line 44):

```python
    def aggregate_from_reading_notes(
        self,
        manager: "ReadingNotesManager",
        analysis_goal: str,
        project_name: str,
        agent_profiles: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        """Aggregate seed analysis from ReadingNotesManager output (new pipeline)."""
        notes = manager.notes
        characters = self._characters_from_notes(notes["core_facts"]["characters"])
        organizations = self._organizations_from_notes(notes["core_facts"]["organizations"])
        relations = self._relations_from_graph(notes["relationship_graph"])
        chapter_beats = self._beats_from_summaries(manager.all_segment_summaries)
        segment_count = len(manager.all_segment_summaries)

        result = {
            "project_name": project_name,
            "analysis_goal": analysis_goal,
            "characters": characters,
            "organizations": organizations,
            "relations": relations,
            "chapter_beats": chapter_beats,
            "analysis_summary": (
                f"已从 {segment_count} 个阅读段聚合出 "
                f"{len(characters)} 名角色、{len(organizations)} 个组织、{len(relations)} 条关系。"
            ),
            "source_stats": {
                "segment_count": segment_count,
                "character_count": len(characters),
                "organization_count": len(organizations),
                "relation_count": len(relations),
            },
        }
        if agent_profiles:
            result["agent_profiles"] = agent_profiles
        return result

    def _characters_from_notes(self, characters: Dict[str, Any]) -> List[Dict[str, Any]]:
        result = []
        for name, data in characters.items():
            segment_count = len(data.get("segments_seen", []))
            result.append({
                "name": name,
                "mention_count": segment_count,
                "importance_tier": self._importance_tier(segment_count),
                "identity_hint": data.get("identity", ""),
                "profile_summary": data.get("goals", ""),
                "evidence": data.get("key_actions", [])[:3],
                # Enriched fields (new pipeline)
                "aliases": data.get("aliases", []),
                "personality_traits": data.get("personality_traits", []),
                "speech_style": data.get("speech_style", ""),
                "status": data.get("status", "unknown"),
            })
        result.sort(key=lambda x: (-x["mention_count"], x["name"]))
        return result

    def _organizations_from_notes(self, organizations: Dict[str, Any]) -> List[Dict[str, Any]]:
        result = []
        for name, data in organizations.items():
            segment_count = len(data.get("segments_seen", []))
            result.append({
                "name": name,
                "mention_count": segment_count,
                "importance_tier": "major" if segment_count >= 2 else "supporting",
                "organization_type": data.get("type", "organization"),
                "summary": data.get("purpose", ""),
                "evidence": [],
            })
        result.sort(key=lambda x: (-x["mention_count"], x["name"]))
        return result

    def _relations_from_graph(self, graph: Sequence[Dict[str, Any]]) -> List[Dict[str, Any]]:
        # Group by source-target pair
        pairs: Dict[str, List[Dict[str, Any]]] = {}
        for entry in graph:
            key = f"{entry.get('source', '')}|{entry.get('target', '')}"
            pairs.setdefault(key, []).append(entry)

        relations = []
        for key, entries in pairs.items():
            source, target = key.split("|", 1)
            latest = entries[-1]
            relations.append({
                "source": source,
                "target": target,
                "relation_type": latest.get("relation", "co_occurrence"),
                "weight": len(entries),
                "evidence": [e.get("evidence", "") for e in entries[:3] if e.get("evidence")],
                # Enriched: evolution chain
                "evolution": [
                    {"state": e.get("relation", ""), "trigger": e.get("trigger", ""), "segment": e.get("segment_id", "")}
                    for e in entries
                ],
            })
        relations.sort(key=lambda x: (-x["weight"], x["source"], x["target"]))
        return relations

    def _beats_from_summaries(self, summaries: Sequence[Dict[str, str]]) -> List[Dict[str, Any]]:
        beats = []
        for i, item in enumerate(summaries[:20], start=1):
            beats.append({
                "beat_id": f"beat_{i}",
                "title": f"段落 {item.get('segment_id', i)}",
                "summary": item.get("summary", ""),
            })
        return beats
```

Also add the needed imports at the top of the file:

```python
from typing import Any, Dict, List, Optional, Sequence
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd /root/novelwork/backend && PYTHONPATH=$(pwd) pytest tests/test_seed_analysis_from_reading_notes.py -v`
Expected: All 2 tests PASS

- [ ] **Step 5: Run existing aggregator tests to verify no regressions**

Run: `cd /root/novelwork/backend && PYTHONPATH=$(pwd) pytest tests/ -k "seed_analysis" -v`
Expected: All existing tests still PASS

- [ ] **Step 6: Commit**

```bash
git add backend/app/services/seed_analysis_aggregator.py backend/tests/test_seed_analysis_from_reading_notes.py
git commit -m "feat: add aggregate_from_reading_notes to SeedAnalysisAggregator"
```

---

## Task 6: Update Backend Pipeline Infrastructure

**Files:**
- Modify: `backend/app/services/seed_pipeline_chapters.py`
- Modify: `backend/app/services/llm_module_registry.py`
- Modify: `backend/tests/seed_test_helpers.py`

### Overview
Update pipeline chapter definitions, LLM module registry, and test helpers for the new pipeline stages.

- [ ] **Step 1: Update seed_pipeline_chapters.py**

Replace the entire content of `backend/app/services/seed_pipeline_chapters.py`:

```python
"""种子管线章节定义与 stage→chapter 映射（新版四阶段管线）。"""

from __future__ import annotations

from typing import Dict, List

PIPELINE_CHAPTERS: List[Dict] = [
    {
        "key": "text_prep",
        "label": "文本准备",
        "stages": ["uploading", "extract_text", "smart_segmentation"],
    },
    {
        "key": "deep_reading",
        "label": "深度阅读",
        "stages": ["sequential_reading", "arc_summary"],
    },
    {
        "key": "integration",
        "label": "全局整合",
        "stages": ["global_integration", "ontology"],
    },
    {
        "key": "agent_build",
        "label": "角色构建",
        "stages": ["agent_profiles", "completed", "failed"],
    },
]

STAGE_TO_CHAPTER: Dict[str, str] = {
    stage: chapter["key"]
    for chapter in PIPELINE_CHAPTERS
    for stage in chapter["stages"]
}

CHAPTER_LABEL: Dict[str, str] = {ch["key"]: ch["label"] for ch in PIPELINE_CHAPTERS}


def chapter_for_stage(stage: str) -> str:
    """返回 stage 所属的 chapter key，未匹配时返回空字符串。"""
    return STAGE_TO_CHAPTER.get(stage, "")


def label_for_chapter(chapter_key: str) -> str:
    """返回 chapter key 对应的中文标签。"""
    return CHAPTER_LABEL.get(chapter_key, "")
```

- [ ] **Step 2: Update llm_module_registry.py**

Add new module definitions and update `STAGE_TO_MODULE_KEY` in `backend/app/services/llm_module_registry.py`. Add these entries to the `MODULE_DEFINITIONS` list:

```python
    LlmModuleDefinition(
        module_key="sequential_reading",
        label="顺序深度阅读",
        description="顺序精读每个段落，提取角色、关系、剧情线等结构化信息。",
        example_prompt="阅读当前段并分析角色、关系与剧情发展...",
        example_output="JSON: character_updates, relationship_changes, plot_threads...",
    ),
    LlmModuleDefinition(
        module_key="character_agent_profile",
        label="角色 Agent 档案生成",
        description="为每个重要角色生成可直接用于 Agent 对话的完整档案。",
        example_prompt="根据阅读笔记为指定角色生成 Agent 档案...",
        example_output="JSON: personality, speech, relationships, knowledge_boundary...",
    ),
```

Update `STAGE_TO_MODULE_KEY`:

```python
STAGE_TO_MODULE_KEY = {
    "anchor_generation": "anchor_point_summary",
    "extract_local_facts": "local_block_facts",
    "entity_resolution": "entity_resolution",
    "contextual_block_analysis": "contextual_block_analysis",
    "chapter_card_generation": "novel_chapter_summarizer",
    "ontology": "story_ontology",
    # New pipeline stages
    "sequential_reading": "sequential_reading",
    "agent_profiles": "character_agent_profile",
}
```

- [ ] **Step 3: Update seed_test_helpers.py**

Add new module handlers to `FakeSeedLlmClient` in `backend/tests/seed_test_helpers.py`. Add to the `chat_json_value` method dispatch:

```python
        if self.module_key == "sequential_reading":
            return self._sequential_reading_payload(user_message)
        if self.module_key == "character_agent_profile":
            return self._character_profile_payload(user_message)
```

Add new methods to the class:

```python
    def _sequential_reading_payload(self, user_message):
        return {
            "segment_summary": "段落摘要：沈夜继续追查镜湖旧案。",
            "character_updates": [
                {
                    "name": "沈夜",
                    "aliases": ["夜哥"],
                    "is_new": True,
                    "status": "active",
                    "identity": "调查者",
                    "personality_traits": ["坚毅"],
                    "speech_style": "简练犀利",
                    "goals": "追查镜湖旧案",
                    "key_actions": ["进入镜湖谷"],
                    "knowledge_gained": ["发现密道"],
                    "quote_examples": ["真相不会自己浮出水面。"],
                },
                {
                    "name": "秦昭",
                    "aliases": [],
                    "is_new": True,
                    "status": "active",
                    "identity": "同伴",
                    "personality_traits": ["忠诚"],
                    "speech_style": "温和",
                    "goals": "保护沈夜",
                    "key_actions": ["掩护撤退"],
                    "knowledge_gained": [],
                    "quote_examples": [],
                },
                {
                    "name": "苏半夏",
                    "aliases": [],
                    "is_new": True,
                    "status": "active",
                    "identity": "稳局者",
                    "personality_traits": ["冷静"],
                    "speech_style": "沉稳",
                    "goals": "稳住局势",
                    "key_actions": ["安排防线"],
                    "knowledge_gained": [],
                    "quote_examples": [],
                },
            ],
            "relationship_changes": [
                {
                    "source": "沈夜",
                    "target": "玄霄宗",
                    "previous_state": "紧张",
                    "new_state": "冲突",
                    "trigger": "宗门施压",
                    "evidence": "对峙升级",
                },
            ],
            "plot_threads": [
                {"thread": "镜湖旧案", "status": "opened", "detail": "线索浮现"},
            ],
            "world_building": [
                {"fact": "五大宗门体系", "evidence": "开篇设定"},
            ],
            "consistency_notes": [],
            "narrative_phase": "development",
        }

    def _character_profile_payload(self, user_message):
        name = "沈夜"
        if "秦昭" in user_message:
            name = "秦昭"
        elif "苏半夏" in user_message:
            name = "苏半夏"
        return {
            "basic_info": {"name": name, "aliases": [], "identity": "角色", "status": "alive"},
            "personality": {"core_traits": ["坚毅"], "values": [], "fears": [], "decision_pattern": ""},
            "speech": {"style": "简练", "verbal_habits": [], "tone_range": "", "example_quotes": []},
            "relationships": [],
            "capabilities": {"skills": [], "limitations": [], "resources": []},
            "knowledge_boundary": {"knows": [], "does_not_know": [], "believes_wrongly": []},
            "motivation": {"ultimate_goal": "", "current_objective": "", "internal_conflict": ""},
        }
```

- [ ] **Step 4: Verify existing tests still pass**

Run: `cd /root/novelwork/backend && PYTHONPATH=$(pwd) pytest tests/test_offline_novel_pipeline.py -v`
Expected: PASS (old pipeline tests still work since old services are untouched)

- [ ] **Step 5: Commit**

```bash
git add backend/app/services/seed_pipeline_chapters.py backend/app/services/llm_module_registry.py backend/tests/seed_test_helpers.py
git commit -m "feat: update pipeline chapters, LLM modules, and test helpers for new pipeline"
```

---

## Task 7: Rewrite SeedExtractRunner + SeedExtractTaskService

**Files:**
- Modify: `backend/app/services/seed_extract_runner.py` (complete rewrite)
- Modify: `backend/app/services/seed_extract_task_service.py` (new service wiring)
- Test: `backend/tests/test_new_seed_pipeline.py`
- Depends on: Tasks 1-6

### Overview
The runner now calls: text extraction → smart segmentation → sequential reading → global integration + ontology → agent profiles. The task service wires up the new services instead of the old ones.

- [ ] **Step 1: Rewrite SeedExtractRunner**

Replace the entire content of `backend/app/services/seed_extract_runner.py`:

```python
"""种子提取流水线执行器（新版：四阶段顺序阅读管线）。"""

from __future__ import annotations

from typing import Any, Dict, List, Optional, Tuple

from ..models.project import ProjectManager, ProjectStatus
from .llm_router import LlmRouter
from .reading_notes_manager import ReadingNotesManager
from .seed_task_callbacks import build_ontology_progress_callback
from .seed_task_progress import SeedTaskProgressTracker


class SeedExtractRunner:
    """执行新版四阶段种子提取流水线。"""

    def __init__(self, service: Any, task_id: str, use_llm: bool, project_id: str = ""):
        self.service = service
        self.use_llm = use_llm
        self.progress = SeedTaskProgressTracker(
            service.task_manager, task_id, use_llm, project_id=project_id,
        )

    def run(
        self,
        project_id: str,
        project_name: str,
        analysis_goal: str,
        additional_context: str,
    ) -> None:
        self._validate_llm_modules()

        # Stage 1: Text Extraction + Smart Segmentation
        documents, chapter_segments = self._extract_and_segment(project_id)
        segmentation_result = self._smart_segmentation(project_id, chapter_segments)

        # Stage 2: Sequential Deep Reading
        manager = self._sequential_reading(project_id, segmentation_result)

        # Stage 3: Global Integration + Ontology
        seed_analysis = self._global_integration(project_id, project_name, analysis_goal, manager)
        ontology = self._generate_ontology(
            documents, analysis_goal, additional_context, manager,
        )

        # Stage 4: Character Agent Profiles
        agent_profiles = self._generate_agent_profiles(project_id, manager)

        # Save agent profiles into seed_analysis
        if agent_profiles.get("profiles"):
            seed_analysis["agent_profiles"] = agent_profiles["profiles"]
            ProjectManager.save_project_json(project_id, "seed_analysis.json", seed_analysis)

        # Finalize
        self.service._finalize_project(project_id, analysis_goal, ontology, seed_analysis)
        self.progress.complete(
            "上传完成，项目与种子分析已生成。",
            self._result_payload(project_id, chapter_segments, segmentation_result, seed_analysis, agent_profiles),
        )

    # ── Stage 1: Text Extraction + Smart Segmentation ──

    def _extract_and_segment(self, project_id: str) -> Tuple[List[Dict[str, str]], Dict[str, Any]]:
        self.progress.enter_stage("extract_text", "正在提取上传文件文本", 3, "读取并清洗上传的原始文稿")
        step_id = self.progress.begin_step("extract_text", "file_extract", "提取上传文件文本")
        documents, all_text = self.service._extract_documents(project_id)
        self.service._save_text(project_id, documents, all_text)
        self.progress.end_step(step_id)
        self.progress.note("extract_text", "文本提取完成", f"已提取 {len(documents)} 份文稿，共 {len(all_text)} 字")

        # Use existing chapter segmenter for chapter detection
        chapter_segments = self.service.chapter_segmenter.segment_documents(documents)
        ProjectManager.save_project_json(project_id, "chapter_segments.json", chapter_segments)
        self.progress.set_counts(chapter_count=chapter_segments["chapter_count"])
        return documents, chapter_segments

    def _smart_segmentation(self, project_id: str, chapter_segments: Dict[str, Any]) -> Dict[str, Any]:
        self.progress.enter_stage("smart_segmentation", "正在智能分段", 8, "按令牌预算分组章节")
        step_id = self.progress.begin_step("smart_segmentation", "segment", "智能分段")
        segmentation_result = self.service.smart_segmenter.segment(chapter_segments["chapters"])
        ProjectManager.save_project_json(project_id, "reading_segments.json", segmentation_result)
        self.progress.end_step(step_id)
        self.progress.set_counts(segment_count=segmentation_result["segment_count"])
        self.progress.note(
            "smart_segmentation",
            "智能分段完成",
            f"共生成 {segmentation_result['segment_count']} 个阅读段",
            meta={"kind": "artifact", "artifact": "reading_segments.json"},
        )
        return segmentation_result

    # ── Stage 2: Sequential Deep Reading ──

    def _sequential_reading(self, project_id: str, segmentation_result: Dict[str, Any]) -> ReadingNotesManager:
        self.progress.enter_stage("sequential_reading", "正在顺序深度阅读", 10, "LLM逐段精读小说")
        segments = segmentation_result["segments"]
        total = len(segments)

        def reading_callback(event_type: str, data: Dict[str, Any]) -> None:
            seg_id = data.get("segment_id", "")
            seg_idx = data.get("segment_index", 0)
            if event_type == "segment_start":
                progress = 10 + int((seg_idx / max(total, 1)) * 65)
                self.progress.block_started(
                    "sequential_reading",
                    f"精读段 {seg_id}",
                    f"第 {seg_idx + 1}/{total} 段",
                    {"segment_id": seg_id, "segment_index": seg_idx},
                )
                self.progress.enter_stage(
                    "sequential_reading",
                    f"正在精读 {seg_id}（{seg_idx + 1}/{total}）",
                    progress,
                )
            elif event_type == "segment_end":
                self.progress.block_completed(
                    "sequential_reading",
                    f"完成段 {seg_id}",
                    f"第 {seg_idx + 1}/{total} 段",
                    {"segment_id": seg_id, "segment_index": seg_idx},
                )

        manager = self.service.sequential_reader.read(
            segments=segments,
            use_llm=self.use_llm,
            progress_callback=reading_callback,
        )

        # Save reading notes checkpoint
        notes_path = ProjectManager.get_project_dir(project_id) + "/reading_notes.json"
        manager.save(notes_path)
        self.progress.note(
            "sequential_reading",
            "顺序阅读完成",
            f"已精读 {total} 个段落",
            meta={"kind": "artifact", "artifact": "reading_notes.json"},
        )

        # Save segment summaries
        ProjectManager.save_project_json(project_id, "segment_summaries.json", {
            "summaries": manager.all_segment_summaries,
        })

        return manager

    # ── Stage 3: Global Integration + Ontology ──

    def _global_integration(
        self,
        project_id: str,
        project_name: str,
        analysis_goal: str,
        manager: ReadingNotesManager,
    ) -> Dict[str, Any]:
        self.progress.enter_stage("global_integration", "正在全局整合分析结果", 78)
        step_id = self.progress.begin_step("global_integration", "aggregate", "全局整合")
        seed_analysis = self.service.seed_analysis_aggregator.aggregate_from_reading_notes(
            manager=manager,
            analysis_goal=analysis_goal,
            project_name=project_name,
        )
        ProjectManager.save_project_json(project_id, "seed_analysis.json", seed_analysis)
        self.progress.end_step(step_id)
        self.progress.note(
            "global_integration",
            "全局整合完成",
            self._seed_counts_text(seed_analysis),
            meta={"kind": "artifact", "artifact": "seed_analysis.json"},
        )
        return seed_analysis

    def _generate_ontology(
        self,
        documents: List[Dict[str, str]],
        analysis_goal: str,
        additional_context: str,
        manager: ReadingNotesManager,
    ) -> Dict[str, Any]:
        self.progress.enter_stage("ontology", "正在生成小说本体与故事主轴", 85)
        step_id = self.progress.begin_step("ontology", "ontology", "生成小说本体与故事主轴")

        # Build story_memory-compatible dict for ontology generator
        reading_context = manager.assemble_context()

        result = self.service.ontology_generator.generate(
            document_texts=[item["text"] for item in documents],
            analysis_goal=analysis_goal,
            additional_context=additional_context or None,
            use_llm=self.use_llm,
            story_memory={"reading_notes_context": reading_context},
            progress_callback=build_ontology_progress_callback(self.progress),
        )
        self.progress.end_step(step_id)
        return result

    # ── Stage 4: Character Agent Profiles ──

    def _generate_agent_profiles(
        self, project_id: str, manager: ReadingNotesManager,
    ) -> Dict[str, Any]:
        self.progress.enter_stage("agent_profiles", "正在生成角色 Agent 档案", 92)

        def profile_callback(event_type: str, data: Dict[str, Any]) -> None:
            if event_type == "profile_done":
                name = data.get("name", "")
                completed = data.get("completed", 0)
                total = data.get("total", 0)
                progress = 92 + int((completed / max(total, 1)) * 8)
                self.progress.note(
                    "agent_profiles",
                    f"完成角色档案：{name}",
                    f"{completed}/{total}",
                )

        result = self.service.character_agent_profile_generator.generate(
            manager=manager,
            use_llm=self.use_llm,
            progress_callback=profile_callback,
        )
        ProjectManager.save_project_json(project_id, "agent_profiles.json", result)
        self.progress.note(
            "agent_profiles",
            "角色档案生成完成",
            f"共生成 {result['profile_count']} 份角色档案",
            meta={"kind": "artifact", "artifact": "agent_profiles.json"},
        )
        return result

    # ── Helpers ──

    def _result_payload(
        self,
        project_id: str,
        chapter_segments: Dict[str, Any],
        segmentation_result: Dict[str, Any],
        seed_analysis: Dict[str, Any],
        agent_profiles: Dict[str, Any],
    ) -> Dict[str, Any]:
        return {
            "project_id": project_id,
            "project_status": ProjectStatus.ONTOLOGY_GENERATED.value,
            "chapter_count": chapter_segments["chapter_count"],
            "segment_count": segmentation_result["segment_count"],
            "seed_analysis": {
                "character_count": len(seed_analysis.get("characters", [])),
                "organization_count": len(seed_analysis.get("organizations", [])),
                "relation_count": len(seed_analysis.get("relations", [])),
            },
            "agent_profile_count": agent_profiles.get("profile_count", 0),
        }

    def _seed_counts_text(self, seed_analysis: Dict[str, Any]) -> str:
        return (
            f"角色 {len(seed_analysis.get('characters', []))} 个，"
            f"组织 {len(seed_analysis.get('organizations', []))} 个，"
            f"关系 {len(seed_analysis.get('relations', []))} 条"
        )

    def _validate_llm_modules(self) -> None:
        if not self.use_llm:
            return
        missing = []
        router = LlmRouter()
        for module_key in ("sequential_reading", "character_agent_profile", "story_ontology"):
            try:
                router.build_client(module_key)
            except ValueError as exc:
                if not self._is_module_binding_error(str(exc)):
                    raise
                missing.append(module_key)
        if missing:
            joined = ", ".join(missing)
            raise ValueError(f"以下 LLM 模块未完成绑定或渠道不可用，无法启动分析：{joined}")

    def _is_module_binding_error(self, message: str) -> bool:
        return any(
            text in message
            for text in ("未配置 LLM 渠道和模型", "绑定的渠道已不存在", "绑定的渠道已停用")
        )
```

- [ ] **Step 2: Rewrite SeedExtractTaskService wiring**

Replace the content of `backend/app/services/seed_extract_task_service.py`:

```python
"""异步小说种子提取任务服务（新版四阶段管线）。"""

import threading
from typing import Any, Dict, List, Optional

from ..models.project import ProjectManager, ProjectStatus
from ..models.task import TaskManager
from ..utils.file_parser import FileParser
from .character_agent_profile_generator import CharacterAgentProfileGenerator
from .novel_chapter_segmenter import NovelChapterSegmenter
from .seed_analysis_aggregator import SeedAnalysisAggregator
from .seed_extract_runner import SeedExtractRunner
from .sequential_reader import SequentialReader
from .smart_novel_segmenter import SmartNovelSegmenter
from .story_ontology_generator import StoryOntologyGenerator
from .text_processor import TextProcessor
from ..utils.upstream_error_formatter import format_upstream_service_error


class SeedExtractTaskService:
    def __init__(
        self,
        task_manager: Optional[TaskManager] = None,
        chapter_segmenter: Optional[NovelChapterSegmenter] = None,
        smart_segmenter: Optional[SmartNovelSegmenter] = None,
        sequential_reader: Optional[SequentialReader] = None,
        seed_analysis_aggregator: Optional[SeedAnalysisAggregator] = None,
        ontology_generator: Optional[StoryOntologyGenerator] = None,
        character_agent_profile_generator: Optional[CharacterAgentProfileGenerator] = None,
    ):
        self.task_manager = task_manager or TaskManager()
        self.chapter_segmenter = chapter_segmenter or NovelChapterSegmenter()
        self.smart_segmenter = smart_segmenter or SmartNovelSegmenter()
        self.sequential_reader = sequential_reader or SequentialReader()
        self.seed_analysis_aggregator = seed_analysis_aggregator or SeedAnalysisAggregator()
        self.ontology_generator = ontology_generator or StoryOntologyGenerator()
        self.character_agent_profile_generator = (
            character_agent_profile_generator or CharacterAgentProfileGenerator()
        )

    def create_task(
        self,
        project_id: str,
        project_name: str,
        analysis_goal: str,
        additional_context: str,
        use_llm: bool,
    ) -> str:
        task_id = self.task_manager.create_task(
            task_type="seed_extract",
            metadata={"project_id": project_id, "project_name": project_name},
        )
        project = ProjectManager.get_project(project_id)
        if not project:
            raise ValueError(f"项目不存在: {project_id}")
        project.status = ProjectStatus.SEED_PROCESSING
        project.seed_task_id = task_id
        ProjectManager.save_project(project)
        self._start_worker(task_id, project_id, project_name, analysis_goal, additional_context, use_llm)
        return task_id

    def _start_worker(
        self,
        task_id: str,
        project_id: str,
        project_name: str,
        analysis_goal: str,
        additional_context: str,
        use_llm: bool,
    ) -> None:
        thread = threading.Thread(
            target=self._run_worker,
            args=(task_id, project_id, project_name, analysis_goal, additional_context, use_llm),
            daemon=True,
        )
        thread.start()

    def _run_worker(
        self,
        task_id: str,
        project_id: str,
        project_name: str,
        analysis_goal: str,
        additional_context: str,
        use_llm: bool,
    ) -> None:
        runner = SeedExtractRunner(self, task_id, use_llm, project_id=project_id)
        try:
            runner.run(project_id, project_name, analysis_goal, additional_context)
        except Exception as exc:
            message = format_upstream_service_error(exc)
            self._fail_project(project_id, message)
            runner.progress.fail(message)

    def _extract_documents(self, project_id: str) -> tuple[List[Dict[str, str]], str]:
        project = ProjectManager.get_project(project_id)
        if not project:
            raise ValueError(f"项目不存在: {project_id}")
        source_names = {
            item.get("saved_filename"): item.get("filename", item.get("saved_filename", "上传文件"))
            for item in project.files
        }
        payloads = []
        all_text_parts = []
        for path in ProjectManager.get_project_files(project_id):
            text = TextProcessor.preprocess_text(FileParser.extract_text(path))
            saved_name = path.rsplit("/", 1)[-1]
            filename = source_names.get(saved_name, saved_name)
            payloads.append({"source_name": filename, "text": text})
            all_text_parts.append(f"\n\n=== {filename} ===\n{text}")
        if not payloads:
            raise ValueError("项目没有可处理的上传文件")
        return payloads, "".join(all_text_parts)

    def _save_text(self, project_id: str, document_payloads: List[Dict[str, str]], all_text: str) -> None:
        project = ProjectManager.get_project(project_id)
        if not project:
            raise ValueError(f"项目不存在: {project_id}")
        project.total_text_length = len(all_text)
        ProjectManager.save_extracted_text(project_id, all_text)
        ProjectManager.save_project(project)

    def _finalize_project(
        self,
        project_id: str,
        analysis_goal: str,
        ontology: Dict[str, Any],
        seed_analysis: Dict[str, Any],
    ) -> None:
        project = ProjectManager.get_project(project_id)
        if not project:
            raise ValueError(f"项目不存在: {project_id}")
        project.analysis_goal = analysis_goal
        project.ontology = {
            "entity_types": ontology.get("entity_types", []),
            "edge_types": ontology.get("edge_types", []),
        }
        project.analysis_summary = ontology.get("analysis_summary") or seed_analysis.get("analysis_summary", "")
        project.status = ProjectStatus.ONTOLOGY_GENERATED
        project.seed_task_id = None
        project.error = None
        ProjectManager.save_project(project)

    def _fail_project(self, project_id: str, error_message: str) -> None:
        project = ProjectManager.get_project(project_id)
        if not project:
            return
        project.status = ProjectStatus.FAILED
        project.seed_task_id = None
        project.error = error_message
        ProjectManager.save_project(project)
```

- [ ] **Step 3: Update progress tracker for new metrics**

Add `segment_count` support to `SeedTaskProgressTracker.set_counts` in `backend/app/services/seed_task_progress.py`. Update the `DEFAULT_METRICS` dict and the `set_counts` method:

In `DEFAULT_METRICS` (line 19), add:
```python
DEFAULT_METRICS = {
    "chapter_count": 0,
    "block_count": 0,
    "completed_blocks": 0,
    "total_blocks": 0,
    "active_workers": 0,
    "segment_count": 0,
}
```

In `set_counts` method, add segment_count handling:
```python
    def set_counts(
        self,
        chapter_count: Optional[int] = None,
        block_count: Optional[int] = None,
        segment_count: Optional[int] = None,
    ) -> None:
        def mutate(task) -> None:
            progress_detail = self._detail_copy(task.progress_detail)
            metrics = progress_detail["task_metrics"]
            if chapter_count is not None:
                metrics["chapter_count"] = chapter_count
            if block_count is not None:
                metrics["block_count"] = block_count
                metrics["total_blocks"] = block_count
                metrics["completed_blocks"] = 0
                metrics["active_workers"] = 0
            if segment_count is not None:
                metrics["segment_count"] = segment_count
            task.progress_detail = progress_detail

        self.task_manager.mutate_task(self.task_id, mutate)
```

- [ ] **Step 4: Write end-to-end integration test**

Create `backend/tests/test_new_seed_pipeline.py`:

```python
"""End-to-end integration test for the new 4-stage seed pipeline."""

import time

from app import create_app
from app.config import Config
from app.models.project import ProjectManager
from tests.seed_test_helpers import install_fake_seed_llm


NOVEL_TEXT = """
第1章 镜湖夜

沈夜站在镜湖边，月光洒在湖面上。

"真相不会自己浮出水面。"沈夜低声道。

秦昭从暗处走出，手中握着一份密函。"夜哥，玄霄宗的人已经到了山脚。"

苏半夏冷静地安排着防线。她是队伍中最沉稳的人。

玄霄宗与白泽司的暗中博弈已经持续了数月。回声会在两方之间暗中活动。

第2章 宗门之变

清晨，玄霄宗的使者到达了。

沈夜与使者对峙，气氛紧张。秦昭始终站在沈夜身后。

"你们要的东西，我们没有。"沈夜的声音很平静。

白泽司的探子带来了新的情报——镜湖下方藏着一条密道。

苏半夏已经提前勘察了周围的地形。

第3章 暗流涌动

夜幕降临，沈夜独自进入密道。

密道深处，他发现了回声会留下的标记。这说明回声会比所有人都早一步到达了这里。

秦昭在入口处守护，不让任何人靠近。

"镜湖旧案的真相，或许就在这密道尽头。"沈夜心想。
""".strip()


def wait_for_task(client, task_id: str, timeout: float = 15.0):
    deadline = time.time() + timeout
    while time.time() < deadline:
        response = client.get(f"/api/project/task/{task_id}")
        data = response.get_json()["data"]
        if data["status"] in {"completed", "failed"}:
            return data
        time.sleep(0.05)
    raise AssertionError(f"Task timeout: {task_id}")


def test_new_pipeline_end_to_end(tmp_path, monkeypatch):
    """Full end-to-end test of the new 4-stage pipeline."""
    ProjectManager.PROJECTS_DIR = str(tmp_path / "projects")
    Config.ZEP_API_KEY = None
    install_fake_seed_llm(monkeypatch)

    app = create_app()
    client = app.test_client()

    import io
    upload = io.BytesIO(NOVEL_TEXT.encode("utf-8"))
    response = client.post(
        "/api/project/seed/extract",
        data={
            "analysis_goal": "提取全部有名角色、组织和关系",
            "project_name": "镜湖秘事",
            "files": (upload, "镜湖秘事.txt"),
        },
        content_type="multipart/form-data",
    )
    assert response.status_code == 202, response.get_json()
    task_id = response.get_json()["data"]["task_id"]
    project_id = response.get_json()["data"]["project_id"]

    task = wait_for_task(client, task_id)
    assert task["status"] == "completed", task.get("error", "")

    # Verify seed_analysis.json was produced
    seed = ProjectManager.load_project_json(project_id, "seed_analysis.json")
    assert seed is not None
    assert len(seed["characters"]) >= 3  # 沈夜, 秦昭, 苏半夏
    character_names = {c["name"] for c in seed["characters"]}
    assert {"沈夜", "秦昭", "苏半夏"}.issubset(character_names)

    # Verify reading_notes.json was produced
    notes_path = f"{ProjectManager.PROJECTS_DIR}/{project_id}/reading_notes.json"
    import json
    with open(notes_path) as f:
        notes_data = json.load(f)
    assert "沈夜" in notes_data["notes"]["core_facts"]["characters"]

    # Verify agent_profiles.json was produced
    profiles = ProjectManager.load_project_json(project_id, "agent_profiles.json")
    assert profiles is not None
    assert profiles["profile_count"] >= 1

    # Verify project is finalized
    project = ProjectManager.get_project(project_id)
    assert project.status == ProjectStatus.ONTOLOGY_GENERATED


def test_new_pipeline_offline(tmp_path, monkeypatch):
    """New pipeline in offline mode (use_llm=false)."""
    ProjectManager.PROJECTS_DIR = str(tmp_path / "projects")
    Config.ZEP_API_KEY = None

    app = create_app()
    client = app.test_client()

    import io
    upload = io.BytesIO(NOVEL_TEXT.encode("utf-8"))
    response = client.post(
        "/api/project/seed/extract",
        data={
            "analysis_goal": "离线测试",
            "project_name": "离线测试项目",
            "use_llm": "false",
            "files": (upload, "test.txt"),
        },
        content_type="multipart/form-data",
    )
    assert response.status_code == 202
    task_id = response.get_json()["data"]["task_id"]
    task = wait_for_task(client, task_id)
    assert task["status"] == "completed", task.get("error", "")
```

Add the missing import at line 2 of the test:

```python
from app.models.project import ProjectManager, ProjectStatus
```

- [ ] **Step 5: Run the integration test**

Run: `cd /root/novelwork/backend && PYTHONPATH=$(pwd) pytest tests/test_new_seed_pipeline.py -v`
Expected: Both tests PASS

- [ ] **Step 6: Commit**

```bash
git add backend/app/services/seed_extract_runner.py backend/app/services/seed_extract_task_service.py backend/app/services/seed_task_progress.py backend/tests/test_new_seed_pipeline.py
git commit -m "feat: rewrite SeedExtractRunner for 4-stage sequential reading pipeline"
```

---

## Task 8: Frontend - Update Stage Definitions

**Files:**
- Modify: `frontend/src/views/overview/seedUploadTaskView.js`
- Modify: `frontend/src/composables/seedUploadTaskState.js`

### Overview
Replace the 14-stage IDLE_TIMELINE with the new 7-stage pipeline and update metric keys.

- [ ] **Step 1: Update seedUploadTaskView.js**

Replace `IDLE_TIMELINE` and `STAGE_PROGRESS_RANGE` in `frontend/src/views/overview/seedUploadTaskView.js`:

```javascript
export const IDLE_TIMELINE = [
  ["extract_text", "提取上传文本", "读取文稿、清洗格式并准备分析输入。"],
  ["smart_segmentation", "智能分段", "按令牌预算将章节分组为阅读段。"],
  ["sequential_reading", "顺序深度阅读", "LLM逐段精读小说，提取角色、关系和剧情。"],
  ["global_integration", "全局整合", "整合阅读笔记，聚合角色、组织与关系。"],
  ["ontology", "梳理故事结构", "归纳实体类型、关系类型与故事主轴。"],
  ["agent_profiles", "角色Agent档案", "为重要角色生成可用于对话和模拟的完整档案。"],
];

const STAGE_PROGRESS_RANGE = {
  sequential_reading: { start: 10, end: 75 },
};
```

Update `resolveStageCounts` function:

```javascript
function resolveStageCounts(stageKey, taskMetrics, timeline) {
  if (stageKey === "sequential_reading") {
    return {
      completed: readSafeNumber(taskMetrics?.completedBlocks),
      total: readSafeNumber(taskMetrics?.segmentCount || taskMetrics?.totalBlocks),
      unit: "段",
    };
  }
  return { completed: 0, total: 0, unit: "" };
}
```

Update `METRIC_KEYS` to include `segment_count`:

```javascript
const METRIC_KEYS = ["chapter_count", "block_count", "completed_blocks", "total_blocks", "active_workers", "segment_count"];
```

Update `normalizeMetrics` function to include `segmentCount`:

```javascript
function normalizeMetrics(metrics) {
  const value = requireObject(metrics, "progress_detail.task_metrics");
  requireKeys(value, METRIC_KEYS, "progress_detail.task_metrics");
  return {
    chapterCount: readNumber(value.chapter_count, "progress_detail.task_metrics.chapter_count"),
    blockCount: readNumber(value.block_count, "progress_detail.task_metrics.block_count"),
    completedBlocks: readNumber(value.completed_blocks, "progress_detail.task_metrics.completed_blocks"),
    totalBlocks: readNumber(value.total_blocks, "progress_detail.task_metrics.total_blocks"),
    activeWorkers: readNumber(value.active_workers, "progress_detail.task_metrics.active_workers"),
    segmentCount: readNumber(value.segment_count, "progress_detail.task_metrics.segment_count"),
  };
}
```

Remove `resolveChapterCardCounts` function (no longer needed).

- [ ] **Step 2: Update seedUploadTaskState.js**

Update `DEFAULT_TASK_METRICS` in `frontend/src/composables/seedUploadTaskState.js`:

```javascript
export const DEFAULT_TASK_METRICS = {
  chapterCount: 0,
  blockCount: 0,
  completedBlocks: 0,
  totalBlocks: 0,
  activeWorkers: 0,
  segmentCount: 0,
};
```

- [ ] **Step 3: Verify frontend builds**

Run: `cd /root/novelwork/frontend && npm run build`
Expected: Build succeeds

- [ ] **Step 4: Commit**

```bash
git add frontend/src/views/overview/seedUploadTaskView.js frontend/src/composables/seedUploadTaskState.js
git commit -m "feat: update frontend stage definitions for new 4-stage pipeline"
```

---

## Task 9: Frontend - Upload Form Token Limit + Analysis Panel Enrichment

**Files:**
- Modify: `frontend/src/views/overview/SeedUploadFormFields.vue`
- Modify: `frontend/src/views/overview/SeedAnalysisPanel.vue`
- Modify: `frontend/src/composables/useSeedUpload.js`

### Overview
Add a "target token limit per segment" field to the upload form advanced settings, and enrich the seed analysis panel to show personality traits and speech style.

- [ ] **Step 1: Add token limit field to SeedUploadFormFields.vue**

Add after the "补充背景" textarea (after line 59 in the original file):

```html
        <div class="field">
          <label>每段令牌上限</label>
          <input
            v-model.number="upload.state.segmentTokenLimit"
            type="number"
            min="5000"
            max="200000"
            step="5000"
            placeholder="50000"
            :disabled="upload.state.uploadBusy"
          />
          <span class="field-hint">控制每个阅读段的最大令牌数，影响分析精度和速度。默认 50000。</span>
        </div>
```

Add CSS for the hint:

```css
.field-hint {
  font-size: 12px;
  color: var(--text-dim);
  margin-top: 2px;
}
```

- [ ] **Step 2: Add segmentTokenLimit to useSeedUpload.js state**

Add `segmentTokenLimit: 50000,` to the state object in `frontend/src/composables/useSeedUpload.js` (after line 19):

```javascript
  segmentTokenLimit: 50000,
```

Update the `submitUpload` function's `uploadStorySeed` call to pass the token limit:

```javascript
    activeUploadPromise = uploadStorySeed({
      projectName: state.projectName.trim() || "我的小说项目",
      analysisGoal: state.analysisGoal.trim(),
      additionalContext: state.additionalContext.trim(),
      segmentTokenLimit: state.segmentTokenLimit,
      files: state.files,
      onProgress: updateProgress,
      onRequest: (xhr) => {
        activeUploadRequest = xhr;
      },
    });
```

- [ ] **Step 3: Enrich SeedAnalysisPanel.vue**

Update the character display in `SeedAnalysisPanel.vue` to show personality traits and speech style. Replace the character list section:

```html
      <div class="seed-col">
        <div class="seed-title">角色列表（预览）</div>
        <div class="seed-item" v-for="item in seedCharactersPreview" :key="item.name">
          <div class="seed-item-main">
            <strong>{{ item.name }}</strong>
            <span class="mono">{{ formatImportanceTier(item.importance_tier) }}</span>
          </div>
          <div class="seed-item-detail" v-if="item.personality_traits?.length || item.speech_style">
            <span v-if="item.personality_traits?.length" class="trait-chips">
              <span class="trait-chip" v-for="trait in item.personality_traits.slice(0, 3)" :key="trait">{{ trait }}</span>
            </span>
            <span v-if="item.speech_style" class="speech-hint">{{ item.speech_style }}</span>
          </div>
        </div>
      </div>
```

Add styles:

```css
.seed-item-main {
  display: flex;
  justify-content: space-between;
  gap: 10px;
}

.seed-item-detail {
  margin-top: 4px;
  display: flex;
  flex-wrap: wrap;
  gap: 4px;
  align-items: center;
}

.trait-chips {
  display: flex;
  gap: 3px;
}

.trait-chip {
  background: rgba(176, 125, 75, 0.1);
  border-radius: 4px;
  padding: 1px 6px;
  font-size: 11px;
  color: var(--accent-copper-deep);
}

.speech-hint {
  font-size: 11px;
  color: var(--text-dim);
  font-style: italic;
}
```

- [ ] **Step 4: Verify frontend builds**

Run: `cd /root/novelwork/frontend && npm run build`
Expected: Build succeeds

- [ ] **Step 5: Commit**

```bash
git add frontend/src/views/overview/SeedUploadFormFields.vue frontend/src/views/overview/SeedAnalysisPanel.vue frontend/src/composables/useSeedUpload.js
git commit -m "feat: add token limit config and enriched character display"
```

---

## Task 10: Backend API - Accept segmentTokenLimit

**Files:**
- Modify: `backend/app/api/project.py` (the upload endpoint)

### Overview
Accept the `segment_token_limit` form field from the upload request and pass it through to the SmartNovelSegmenter.

- [ ] **Step 1: Find and update the upload endpoint**

In `backend/app/api/project.py`, find the `/seed/extract` POST handler. Add `segment_token_limit` extraction from the form data:

```python
segment_token_limit = request.form.get("segment_token_limit", 50000, type=int)
```

Pass it through to `SeedExtractTaskService.create_task()` by adding it to the metadata or as a parameter. The simplest approach is to pass it as part of `additional_context` or add it to the task service.

Update `SeedExtractTaskService.create_task` signature to accept `segment_token_limit: int = 50000`:

```python
    def create_task(
        self,
        project_id: str,
        project_name: str,
        analysis_goal: str,
        additional_context: str,
        use_llm: bool,
        segment_token_limit: int = 50000,
    ) -> str:
```

Store it in task metadata and configure the smart segmenter before the worker starts:

```python
        task_id = self.task_manager.create_task(
            task_type="seed_extract",
            metadata={
                "project_id": project_id,
                "project_name": project_name,
                "segment_token_limit": segment_token_limit,
            },
        )
```

Update `_start_worker` and `_run_worker` to pass `segment_token_limit`:

```python
    def _start_worker(
        self,
        task_id: str,
        project_id: str,
        project_name: str,
        analysis_goal: str,
        additional_context: str,
        use_llm: bool,
        segment_token_limit: int = 50000,
    ) -> None:
        thread = threading.Thread(
            target=self._run_worker,
            args=(task_id, project_id, project_name, analysis_goal, additional_context, use_llm, segment_token_limit),
            daemon=True,
        )
        thread.start()

    def _run_worker(
        self,
        task_id: str,
        project_id: str,
        project_name: str,
        analysis_goal: str,
        additional_context: str,
        use_llm: bool,
        segment_token_limit: int = 50000,
    ) -> None:
        self.smart_segmenter = SmartNovelSegmenter(target_token_limit=segment_token_limit)
        runner = SeedExtractRunner(self, task_id, use_llm, project_id=project_id)
        try:
            runner.run(project_id, project_name, analysis_goal, additional_context)
        except Exception as exc:
            message = format_upstream_service_error(exc)
            self._fail_project(project_id, message)
            runner.progress.fail(message)
```

- [ ] **Step 2: Update the API endpoint to pass the parameter**

In the upload endpoint handler in `backend/app/api/project.py`, pass `segment_token_limit`:

```python
task_id = seed_task_service.create_task(
    project_id=project_id,
    project_name=project_name,
    analysis_goal=analysis_goal,
    additional_context=additional_context,
    use_llm=use_llm,
    segment_token_limit=segment_token_limit,
)
```

- [ ] **Step 3: Verify the integration test still passes**

Run: `cd /root/novelwork/backend && PYTHONPATH=$(pwd) pytest tests/test_new_seed_pipeline.py -v`
Expected: PASS

- [ ] **Step 4: Commit**

```bash
git add backend/app/api/project.py backend/app/services/seed_extract_task_service.py
git commit -m "feat: accept segment_token_limit in upload API"
```

---

## Task 11: Verification - Full Test Suite

**Files:** No new files.

### Overview
Run all tests to verify nothing is broken.

- [ ] **Step 1: Run new pipeline tests**

Run: `cd /root/novelwork/backend && PYTHONPATH=$(pwd) pytest tests/test_smart_novel_segmenter.py tests/test_reading_notes_manager.py tests/test_sequential_reader.py tests/test_character_agent_profile_generator.py tests/test_seed_analysis_from_reading_notes.py tests/test_new_seed_pipeline.py -v`
Expected: All tests PASS

- [ ] **Step 2: Run existing test suite**

Run: `cd /root/novelwork/backend && PYTHONPATH=$(pwd) pytest tests/ -v --timeout=30`
Expected: All tests PASS (old pipeline tests still work since old service files remain)

- [ ] **Step 3: Verify frontend build**

Run: `cd /root/novelwork/frontend && npm run build`
Expected: Build succeeds

- [ ] **Step 4: Final commit if any fixups needed**

Only commit if fixes were required in previous steps.
