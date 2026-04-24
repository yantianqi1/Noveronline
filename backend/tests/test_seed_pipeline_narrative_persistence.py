"""Tests for narrative data persistence during the seed pipeline.

Locks in Task 2 of the 2026-04-19 writer-agent optimization: the seed runner's
``_persist_narrative_data`` method writes arc / volume / segment summaries
from the in-memory :class:`ReadingNotesManager` to the unified DB tables so
writer-agent tools (``get_story_overview``, ``query_segment_summaries``) can
actually see them.

The aggregation runner itself is exercised in
``test_new_seed_pipeline.py``; here we unit-test just the persistence hop so
a regression in the mapping logic fails loudly and close to the cause.
"""

from __future__ import annotations

import json

from app.database import get_engine
from app.repositories.narrative_repo import NarrativeRepository
from app.services.reading_notes_manager import ReadingNotesManager
from app.services.seed_extract_runner import SeedExtractRunner


class _FakeTaskManager:
    """Minimal TaskManager stand-in for SeedTaskProgressTracker bootstrap."""

    def sync_bridge(self, value):
        # SeedTaskProgressTracker._mutate calls sync_bridge on the coro returned
        # by mutate_task; in the real code it's run on the asyncio loop. In tests
        # we just swallow the coro — nobody is listening to task progress.
        if hasattr(value, "close"):
            try:
                value.close()
            except Exception:
                pass
        return None

    def is_cancelled(self, task_id):
        return False

    async def mutate_task(self, task_id, mutator):
        # No-op: progress notes don't need to be persisted for these tests.
        return None


class _FakeService:
    """Minimal service wrapper so SeedExtractRunner can instantiate outside a real pipeline."""

    def __init__(self):
        self.task_manager = _FakeTaskManager()


def _build_runner() -> SeedExtractRunner:
    service = _FakeService()
    return SeedExtractRunner(service, task_id="t_test", use_llm=False, project_id="")


def _seed_manager_with_fixtures() -> ReadingNotesManager:
    manager = ReadingNotesManager()
    manager.add_segment_summary("seg_1", "第一段发生了初遇。")
    manager.add_segment_summary("seg_2", "第二段埋下伏笔。")
    manager.add_segment_summary("seg_3", "第三段冲突爆发。")

    manager.add_arc_summary(
        "arc_1",
        "主角从懵懂到觉醒的开篇弧线。",
        covered_segments=[
            {"segment_id": "seg_1", "summary": "初遇"},
            {"segment_id": "seg_2", "summary": "伏笔"},
        ],
    )
    manager.add_arc_summary(
        "arc_2",
        "冲突升级收束。",
        covered_segments=[{"segment_id": "seg_3", "summary": "冲突"}],
    )

    manager.notes["plot_state"]["volume_summaries"].append(
        {
            "volume_id": "vol_1",
            "summary": "第一卷：觉醒与试炼。",
            "covered_arcs": ["arc_1", "arc_2"],
            "theme": "成长",
        }
    )
    return manager


def test_persist_narrative_data_writes_all_three_tables():
    project_id = "proj_narrative_test"
    runner = _build_runner()
    manager = _seed_manager_with_fixtures()

    runner._persist_narrative_data(project_id, manager)

    repo = NarrativeRepository(get_engine())

    arcs = repo.list_narrative_arcs(project_id)
    assert [a["arc_id"] for a in arcs] == ["arc_1", "arc_2"]
    assert "觉醒" in arcs[0]["summary"]
    covered = json.loads(arcs[0]["covered_segments_json"])
    assert [c["segment_id"] for c in covered] == ["seg_1", "seg_2"]

    volumes = repo.list_volume_summaries(project_id)
    assert [v["volume_id"] for v in volumes] == ["vol_1"]
    assert volumes[0]["volume_order"] == 1
    assert "觉醒与试炼" in volumes[0]["summary"]
    assert json.loads(volumes[0]["covered_arcs_json"]) == ["arc_1", "arc_2"]

    segments = repo.list_segment_summaries(project_id)
    assert [s["segment_id"] for s in segments] == ["seg_1", "seg_2", "seg_3"]
    # segment_order reflects insertion order (1-based)
    assert [s["segment_order"] for s in segments] == [1, 2, 3]


def test_persist_narrative_data_is_idempotent_on_rerun():
    project_id = "proj_narr_idem"
    runner = _build_runner()
    manager = _seed_manager_with_fixtures()

    runner._persist_narrative_data(project_id, manager)
    runner._persist_narrative_data(project_id, manager)  # second run: upsert overwrites

    repo = NarrativeRepository(get_engine())
    assert len(repo.list_narrative_arcs(project_id)) == 2
    assert len(repo.list_volume_summaries(project_id)) == 1
    assert len(repo.list_segment_summaries(project_id)) == 3


def test_persist_narrative_data_handles_empty_manager():
    project_id = "proj_narr_empty"
    runner = _build_runner()
    manager = ReadingNotesManager()

    runner._persist_narrative_data(project_id, manager)

    repo = NarrativeRepository(get_engine())
    assert repo.list_narrative_arcs(project_id) == []
    assert repo.list_volume_summaries(project_id) == []
    assert repo.list_segment_summaries(project_id) == []


def test_persist_narrative_data_skips_entries_without_id():
    project_id = "proj_narr_malformed"
    runner = _build_runner()
    manager = ReadingNotesManager()
    manager.all_segment_summaries.append({"segment_id": "", "summary": "无 id"})  # dropped
    manager.all_segment_summaries.append({"segment_id": "seg_ok", "summary": "正常"})
    manager.notes["plot_state"]["arc_summaries"].append(
        {"arc_id": "", "summary": "无 id"}
    )
    manager.notes["plot_state"]["arc_summaries"].append(
        {"arc_id": "arc_ok", "summary": "正常", "covered_segments": []}
    )

    runner._persist_narrative_data(project_id, manager)

    repo = NarrativeRepository(get_engine())
    assert [a["arc_id"] for a in repo.list_narrative_arcs(project_id)] == ["arc_ok"]
    assert [s["segment_id"] for s in repo.list_segment_summaries(project_id)] == ["seg_ok"]


def test_persist_narrative_data_dedups_retried_segments():
    """When a segment fails and is retried, both entries live in
    all_segment_summaries (one with status='retry_needed', one without).
    Persistence should keep exactly one row per segment_id."""
    project_id = "proj_narr_retry"
    runner = _build_runner()
    manager = ReadingNotesManager()
    manager.all_segment_summaries.append(
        {"segment_id": "seg_1", "summary": "first attempt failed", "status": "retry_needed"}
    )
    manager.all_segment_summaries.append(
        {"segment_id": "seg_1", "summary": "retry succeeded"}
    )

    runner._persist_narrative_data(project_id, manager)

    repo = NarrativeRepository(get_engine())
    rows = repo.list_segment_summaries(project_id)
    assert len(rows) == 1
    # First occurrence wins (we dedup by segment_id in insertion order)
    assert rows[0]["summary"] == "first attempt failed"
