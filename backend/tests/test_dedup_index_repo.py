"""Tests for ``DedupIndexRepository`` — writer agent anti-repetition store.

The repository is called after every scene commit by the LLM-based
``DedupExtractor`` and before the next generation by the writer orchestrator.
These tests pin the observable contract:

    - ``add_patterns`` inserts new rows and bumps ``count`` on re-insert
      (UNIQUE(project_id, pattern_type, pattern_text)).
    - ``get_constraints`` respects ``min_count`` and ``up_to_chapter`` filters
      and orders each bucket by count DESC.
    - ``purge_chapter`` / ``purge_scene`` / ``purge_project`` delete only
      their target rows.

Mirror of ``test_project_artifact_repo.py`` style: fresh tmp SQLite per test
via ``init_db`` on a disposable engine.
"""

from __future__ import annotations

import pytest
from sqlalchemy import create_engine

from app.database import init_db
from app.repositories.dedup_index_repo import DedupIndexRepository


@pytest.fixture
def engine(tmp_path):
    db_path = tmp_path / "dedup.db"
    eng = create_engine(f"sqlite:///{db_path}", future=True)
    init_db(eng)
    return eng


def test_add_patterns_inserts_new_rows(engine):
    repo = DedupIndexRepository(engine)
    written = repo.add_patterns(
        "proj_a",
        chapter_order=1,
        scene_id="sc_1",
        patterns={
            "figurative_phrase": {"像一滴浓稠的墨": 2, "眼中的世界是重叠的": 1},
            "opening_phrase": {"黄昏总是走得很慢": 1},
        },
    )
    assert written == 3
    rows = repo.list_all("proj_a")
    assert len(rows) == 3
    assert {r["pattern_type"] for r in rows} == {"figurative_phrase", "opening_phrase"}


def test_add_patterns_bumps_count_on_reinsert(engine):
    repo = DedupIndexRepository(engine)
    repo.add_patterns("proj_a", 1, "sc_1", {"figurative_phrase": {"像一滴浓稠的墨": 2}})
    repo.add_patterns("proj_a", 2, "sc_2", {"figurative_phrase": {"像一滴浓稠的墨": 3}})

    rows = repo.list_all("proj_a")
    assert len(rows) == 1  # merged via UNIQUE
    assert rows[0]["count"] == 5
    # chapter_order is pinned to earliest occurrence so range queries still hit.
    assert rows[0]["chapter_order"] == 1


def test_add_patterns_ignores_blank_text(engine):
    repo = DedupIndexRepository(engine)
    written = repo.add_patterns(
        "proj_a",
        1,
        None,
        {"figurative_phrase": {"": 2, "  ": 1, "真实短语": 1}},
    )
    assert written == 1
    rows = repo.list_all("proj_a")
    assert [r["pattern_text"] for r in rows] == ["真实短语"]


def test_get_constraints_applies_min_count(engine):
    repo = DedupIndexRepository(engine)
    repo.add_patterns(
        "proj_a",
        1,
        "sc_1",
        {
            "figurative_phrase": {"像墨": 5, "像风": 1},
            "action_verb": {"凝视": 3, "瞥了一眼": 1},
        },
    )

    all_items = repo.get_constraints("proj_a", up_to_chapter=10, min_count=1)
    assert len(all_items["figurative_phrase"]) == 2
    assert len(all_items["action_verb"]) == 2

    filtered = repo.get_constraints("proj_a", up_to_chapter=10, min_count=2)
    assert filtered["figurative_phrase"] == [("像墨", 5)]
    assert filtered["action_verb"] == [("凝视", 3)]


def test_get_constraints_orders_by_count_desc(engine):
    repo = DedupIndexRepository(engine)
    repo.add_patterns(
        "proj_a",
        1,
        "sc_1",
        {"opening_phrase": {"a": 2, "b": 5, "c": 3}},
    )
    result = repo.get_constraints("proj_a", min_count=1)
    assert result["opening_phrase"] == [("b", 5), ("c", 3), ("a", 2)]


def test_get_constraints_respects_up_to_chapter(engine):
    repo = DedupIndexRepository(engine)
    repo.add_patterns("proj_a", 1, "sc_1", {"opening_phrase": {"第一章模式": 2}})
    repo.add_patterns("proj_a", 5, "sc_5", {"opening_phrase": {"第五章模式": 2}})

    r3 = repo.get_constraints("proj_a", up_to_chapter=3, min_count=1)
    assert r3["opening_phrase"] == [("第一章模式", 2)]

    r10 = repo.get_constraints("proj_a", up_to_chapter=10, min_count=1)
    assert {text for text, _ in r10["opening_phrase"]} == {"第一章模式", "第五章模式"}


def test_get_constraints_per_type_cap(engine):
    repo = DedupIndexRepository(engine)
    patterns = {"figurative_phrase": {f"短语{i}": (20 - i) for i in range(20)}}
    repo.add_patterns("proj_a", 1, "sc_1", patterns)
    result = repo.get_constraints("proj_a", min_count=1, per_type_limit=5)
    assert len(result["figurative_phrase"]) == 5
    # Highest-count first
    assert result["figurative_phrase"][0][1] == 20


def test_purge_chapter_only_affects_target(engine):
    repo = DedupIndexRepository(engine)
    repo.add_patterns("proj_a", 1, "sc_1", {"opening_phrase": {"x": 1}})
    repo.add_patterns("proj_a", 2, "sc_2", {"opening_phrase": {"y": 1}})
    deleted = repo.purge_chapter("proj_a", 1)
    assert deleted == 1
    remaining = {r["pattern_text"] for r in repo.list_all("proj_a")}
    assert remaining == {"y"}


def test_purge_scene(engine):
    repo = DedupIndexRepository(engine)
    repo.add_patterns("proj_a", 1, "sc_1", {"opening_phrase": {"x": 1}})
    repo.add_patterns("proj_a", 1, "sc_2", {"opening_phrase": {"y": 1}})
    deleted = repo.purge_scene("proj_a", "sc_1")
    assert deleted == 1
    assert {r["pattern_text"] for r in repo.list_all("proj_a")} == {"y"}


def test_purge_project_scopes_correctly(engine):
    repo = DedupIndexRepository(engine)
    repo.add_patterns("proj_a", 1, "sc_1", {"opening_phrase": {"x": 1}})
    repo.add_patterns("proj_b", 1, "sc_1", {"opening_phrase": {"y": 1}})
    deleted = repo.purge_project("proj_a")
    assert deleted == 1
    assert repo.list_all("proj_a") == []
    assert len(repo.list_all("proj_b")) == 1
