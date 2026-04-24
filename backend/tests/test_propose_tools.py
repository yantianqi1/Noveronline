"""Unit tests for the 5 propose_* executors (W-3 §4.4).

Each tool must:
1. Only emit a render payload when inputs pass structural validation.
2. Never mutate DB state — verified by checking before/after snapshots.
3. Enforce hard constraints (uniqueness, char budgets, non-empty fields)
   that prevent accidental adoption of malformed proposals.
"""

from __future__ import annotations

import uuid

import pytest

from app.database import get_engine, init_db
from app.repositories import ChapterRepository, EntityRepository, ManuscriptRepository
from app.services.assets.manuscript_adapter import ManuscriptAssetAdapter


@pytest.fixture
def seeded_project():
    engine = get_engine()
    init_db(engine)
    project_id = f"proj_{uuid.uuid4().hex[:8]}"
    chapter_id = f"ch_{uuid.uuid4().hex[:8]}"
    ChapterRepository(engine).create_chapter(
        project_id=project_id, chapter_id=chapter_id, chapter_order=3, title="测试章"
    )
    adapter = ManuscriptAssetAdapter(project_id=project_id)
    block1 = adapter.commit(
        content="这是第一个块的内容，包含唯一词 Alpha。", chapter_id=chapter_id
    )
    block2 = adapter.commit(
        content="第二块包含 Beta 和 Gamma。",
        chapter_id=chapter_id,
        insert_after_block_id=block1["block_id"],
    )
    return {
        "project_id": project_id,
        "chapter_id": chapter_id,
        "block1_id": block1["block_id"],
        "block2_id": block2["block_id"],
        "engine": engine,
        "adapter": adapter,
    }


# ---------------------------------------------------------------------
# propose_outline_scene
# ---------------------------------------------------------------------


def test_propose_outline_scene_happy_path(seeded_project):
    from app.services.writer_agent.tool_executors import _propose_outline_scene

    r = _propose_outline_scene(
        {
            "chapter_id": seeded_project["chapter_id"],
            "insert_after_scene_order": 2,
            "scene_order": 3,
            "title": "新场景",
            "summary": "一个简要摘要。",
            "pov": "主角",
            "key_events": ["事件A"],
            "target_word_count": 1200,
            "reason": "填补第二幕缺口",
        },
        seeded_project["project_id"],
    )
    assert "render" in r
    payload = r["render"]
    assert payload["type"] == "scene_proposal"
    assert payload["version"] == 1
    data = payload["data"]
    assert data["chapter_id"] == seeded_project["chapter_id"]
    assert data["chapter_order"] == 3  # resolved from DB
    assert data["insert_after_scene_order"] == 2
    assert data["scene_order"] == 3
    assert data["mode"] == "insert"
    assert data["title"] == "新场景"
    assert data["pov"] == "主角"
    assert data["key_events"] == ["事件A"]
    assert data["target_word_count"] == 1200
    assert data["estimated_word_count"] == 1200
    assert data["rationale"] == "填补第二幕缺口"
    # Action must exist
    assert any(a.get("kind") == "create_scene" for a in payload["actions"])


def test_propose_outline_scene_defaults_scene_order_from_insert_after(seeded_project):
    from app.services.writer_agent.tool_executors import _propose_outline_scene

    r = _propose_outline_scene(
        {
            "chapter_id": seeded_project["chapter_id"],
            "insert_after_scene_order": 5,  # scene_order omitted
            "title": "自动编号场景",
            "summary": "x",
            "reason": "y",
        },
        seeded_project["project_id"],
    )
    assert r["render"]["data"]["scene_order"] == 6  # 5 + 1


def test_propose_outline_scene_rejects_missing_chapter(seeded_project):
    from app.services.writer_agent.tool_executors import _propose_outline_scene

    # Missing chapter_id
    r = _propose_outline_scene(
        {"insert_after_scene_order": 0, "title": "t", "summary": "s", "reason": "r"},
        seeded_project["project_id"],
    )
    assert "render" not in r

    # Unknown chapter
    r2 = _propose_outline_scene(
        {
            "chapter_id": "no_such_chap",
            "insert_after_scene_order": 0,
            "title": "t",
            "summary": "s",
            "reason": "r",
        },
        seeded_project["project_id"],
    )
    assert "render" not in r2
    assert "找不到章节" in r2["result"]


def test_propose_outline_scene_rejects_missing_reason(seeded_project):
    from app.services.writer_agent.tool_executors import _propose_outline_scene

    r = _propose_outline_scene(
        {
            "chapter_id": seeded_project["chapter_id"],
            "insert_after_scene_order": 0,
            "title": "t",
            "summary": "s",
            # reason missing — required per schema
        },
        seeded_project["project_id"],
    )
    assert "render" not in r


# ---------------------------------------------------------------------
# propose_chapter_structure
# ---------------------------------------------------------------------


def test_propose_chapter_structure_batch(seeded_project):
    from app.services.writer_agent.tool_executors import _propose_chapter_structure

    r = _propose_chapter_structure(
        {
            "plan_id": "plan_xyz",
            "start_chapter_order": 7,
            "chapters": [
                {
                    "title": "破晓",
                    "summary": "A",
                    "word_target": 3500,
                    "hook": "h",
                    "pov_character": "主角",
                    "key_threads": ["t1"],
                },
                {"title": "暗夜", "summary": "B", "word_target": 3000},
            ],
            "overall_arc": "全弧",
            "rationale": "rationale",
        },
        seeded_project["project_id"],
    )
    assert "render" in r
    payload = r["render"]
    assert payload["type"] == "chapter_structure_proposal"
    data = payload["data"]
    assert data["plan_id"] == "plan_xyz"
    assert data["start_chapter_order"] == 7
    assert len(data["chapters"]) == 2
    assert data["chapters"][0]["chapter_order"] == 7
    assert data["chapters"][1]["chapter_order"] == 8  # defaulted
    assert data["overall_arc"] == "全弧"


def test_propose_chapter_structure_filters_invalid(seeded_project):
    from app.services.writer_agent.tool_executors import _propose_chapter_structure

    r = _propose_chapter_structure(
        {
            "chapters": [
                {"title": "", "summary": "no title"},  # dropped
                {"title": "ok", "summary": ""},  # dropped
                {"title": "good", "summary": "good summary"},  # kept
            ],
        },
        seeded_project["project_id"],
    )
    assert len(r["render"]["data"]["chapters"]) == 1


def test_propose_chapter_structure_rejects_empty(seeded_project):
    from app.services.writer_agent.tool_executors import _propose_chapter_structure

    r = _propose_chapter_structure({"chapters": []}, seeded_project["project_id"])
    assert "render" not in r

    r2 = _propose_chapter_structure(
        {"chapters": [{"invalid": True}]}, seeded_project["project_id"]
    )
    assert "render" not in r2


# ---------------------------------------------------------------------
# propose_splice_block
# ---------------------------------------------------------------------


def test_propose_splice_block_expand(seeded_project):
    from app.services.writer_agent.tool_executors import _propose_splice_block

    new_content = "扩写一段情绪铺陈。" * 3
    r = _propose_splice_block(
        {
            "chapter_id": seeded_project["chapter_id"],
            "anchor_block_id": seeded_project["block1_id"],
            "position": "after",
            "new_content": new_content,
            "reason": "缓解 POV 跳变",
            "intent": "expand",
        },
        seeded_project["project_id"],
    )
    assert "render" in r
    payload = r["render"]
    assert payload["type"] == "prose_diff"
    data = payload["data"]
    assert data["scope"] == "manuscript_block"
    assert data["target_id"] == seeded_project["block1_id"]
    assert data["word_delta"] > 0  # expand
    assert data["source"] == "splice_block"
    assert len(data["hunks"]) == 1
    hunk = data["hunks"][0]
    assert hunk["replacement"] == new_content
    assert hunk["original"] == ""  # after = pure insert


def test_propose_splice_block_replace_range_shrinks(seeded_project):
    from app.services.writer_agent.tool_executors import _propose_splice_block

    r = _propose_splice_block(
        {
            "chapter_id": seeded_project["chapter_id"],
            "anchor_block_id": seeded_project["block1_id"],
            "end_anchor_block_id": seeded_project["block2_id"],
            "position": "replace_range",
            "new_content": "短。",
            "reason": "冗余过多",
            "intent": "shrink",
        },
        seeded_project["project_id"],
    )
    assert r["render"]["data"]["word_delta"] < 0


def test_propose_splice_block_rejects_missing_intent(seeded_project):
    from app.services.writer_agent.tool_executors import _propose_splice_block

    r = _propose_splice_block(
        {
            "chapter_id": seeded_project["chapter_id"],
            "anchor_block_id": seeded_project["block1_id"],
            "position": "after",
            "new_content": "x",
            "reason": "r",
            # intent missing
        },
        seeded_project["project_id"],
    )
    assert "render" not in r


def test_propose_splice_block_rejects_missing_reason(seeded_project):
    from app.services.writer_agent.tool_executors import _propose_splice_block

    r = _propose_splice_block(
        {
            "chapter_id": seeded_project["chapter_id"],
            "anchor_block_id": seeded_project["block1_id"],
            "position": "after",
            "new_content": "x",
            "reason": "",  # empty
            "intent": "expand",
        },
        seeded_project["project_id"],
    )
    assert "render" not in r


def test_propose_splice_block_rejects_delta_overflow(seeded_project):
    from app.services.writer_agent.tool_executors import (
        _SPLICE_MAX_DELTA_CHARS,
        _propose_splice_block,
    )

    # Way above the cap
    big = "x" * (_SPLICE_MAX_DELTA_CHARS + 500)
    r = _propose_splice_block(
        {
            "chapter_id": seeded_project["chapter_id"],
            "anchor_block_id": seeded_project["block1_id"],
            "position": "after",
            "new_content": big,
            "reason": "r",
            "intent": "expand",
        },
        seeded_project["project_id"],
    )
    assert "render" not in r


def test_propose_splice_block_does_not_mutate(seeded_project):
    """Critical invariant: proposal tools must never write to DB."""
    from app.services.writer_agent.tool_executors import _propose_splice_block

    before = seeded_project["adapter"].list_blocks(
        include_content=True, chapter_id=seeded_project["chapter_id"]
    )
    _propose_splice_block(
        {
            "chapter_id": seeded_project["chapter_id"],
            "anchor_block_id": seeded_project["block1_id"],
            "position": "after",
            "new_content": "扩写。" * 3,
            "reason": "r",
            "intent": "expand",
        },
        seeded_project["project_id"],
    )
    after = seeded_project["adapter"].list_blocks(
        include_content=True, chapter_id=seeded_project["chapter_id"]
    )
    assert len(before) == len(after)
    assert {b["block_id"] for b in before} == {b["block_id"] for b in after}
    for b1, b2 in zip(before, after):
        assert b1["content"] == b2["content"]


# ---------------------------------------------------------------------
# propose_rewrite_span
# ---------------------------------------------------------------------


def test_propose_rewrite_span_happy_path(seeded_project):
    from app.services.writer_agent.tool_executors import _propose_rewrite_span

    r = _propose_rewrite_span(
        {
            "block_id": seeded_project["block1_id"],
            "original_text": "Alpha",
            "new_text": "阿尔法",
            "reason": "禁词 Alpha 改写",
        },
        seeded_project["project_id"],
    )
    assert "render" in r
    payload = r["render"]
    assert payload["type"] == "prose_diff"
    assert payload["data"]["source"] == "rewrite_span"
    hunk = payload["data"]["hunks"][0]
    assert hunk["original"] == "Alpha"
    assert hunk["replacement"] == "阿尔法"
    assert hunk["category"] == "forbidden_lexicon"


def test_propose_rewrite_span_rejects_missing_text(seeded_project):
    from app.services.writer_agent.tool_executors import _propose_rewrite_span

    # Non-existent original_text
    r = _propose_rewrite_span(
        {
            "block_id": seeded_project["block1_id"],
            "original_text": "不存在的短语",
            "new_text": "X",
            "reason": "r",
        },
        seeded_project["project_id"],
    )
    assert "render" not in r


def test_propose_rewrite_span_rejects_non_unique(seeded_project):
    """The precheck must reject non-unique original_text to avoid destroying
    context when the frontend adoption does a simple content.replace()."""
    from app.services.writer_agent.tool_executors import _propose_rewrite_span

    # "一" appears in "第一个" and "唯一词" within the seeded block
    r = _propose_rewrite_span(
        {
            "block_id": seeded_project["block1_id"],
            "original_text": "一",
            "new_text": "壹",
            "reason": "r",
        },
        seeded_project["project_id"],
    )
    assert "render" not in r
    assert "不唯一" in r["result"]


def test_propose_rewrite_span_rejects_empty_new_text(seeded_project):
    """new_text must be non-empty — silent drops would cause semantic collapse
    on adoption."""
    from app.services.writer_agent.tool_executors import _propose_rewrite_span

    r = _propose_rewrite_span(
        {
            "block_id": seeded_project["block1_id"],
            "original_text": "Alpha",
            "new_text": "",
            "reason": "r",
        },
        seeded_project["project_id"],
    )
    assert "render" not in r


def test_propose_rewrite_span_rejects_empty_reason(seeded_project):
    from app.services.writer_agent.tool_executors import _propose_rewrite_span

    r = _propose_rewrite_span(
        {
            "block_id": seeded_project["block1_id"],
            "original_text": "Alpha",
            "new_text": "阿尔法",
            "reason": "",
        },
        seeded_project["project_id"],
    )
    assert "render" not in r


def test_propose_rewrite_span_rejects_delta_overflow(seeded_project):
    from app.services.writer_agent.tool_executors import (
        _REWRITE_MAX_DELTA_CHARS,
        _propose_rewrite_span,
    )

    big = "扩" * (_REWRITE_MAX_DELTA_CHARS + 100)
    r = _propose_rewrite_span(
        {
            "block_id": seeded_project["block1_id"],
            "original_text": "Alpha",
            "new_text": big,
            "reason": "r",
        },
        seeded_project["project_id"],
    )
    assert "render" not in r


def test_propose_rewrite_span_does_not_mutate(seeded_project):
    """Critical invariant: proposal tools must never write to DB."""
    from app.services.writer_agent.tool_executors import _propose_rewrite_span

    before = seeded_project["adapter"].get_block(seeded_project["block1_id"])
    _propose_rewrite_span(
        {
            "block_id": seeded_project["block1_id"],
            "original_text": "Alpha",
            "new_text": "阿尔法",
            "reason": "禁词",
        },
        seeded_project["project_id"],
    )
    after = seeded_project["adapter"].get_block(seeded_project["block1_id"])
    assert before["content"] == after["content"]


# ---------------------------------------------------------------------
# propose_relationship
# ---------------------------------------------------------------------


def test_propose_relationship_happy_path(seeded_project):
    from app.services.writer_agent.tool_executors import _propose_relationship

    r = _propose_relationship(
        {
            "entity_a": "小林",
            "entity_b": "苏晴",
            "relation_type": "师徒",
            "description": "小林拜苏晴为师。",
            "evidence_snippet": "第十章第3节原文片段",
            "trust_level": 0.7,
            "power_dynamic": "苏晴为上",
            "source_scene_ids": ["sc_1"],
        },
        seeded_project["project_id"],
    )
    assert "render" in r
    payload = r["render"]
    assert payload["type"] == "relationship_proposal"
    data = payload["data"]
    assert data["entity_a"] == "小林"
    assert data["entity_b"] == "苏晴"
    assert data["trust_level"] == 0.7
    assert data["power_dynamic"] == "苏晴为上"
    assert data["source_scene_ids"] == ["sc_1"]


def test_propose_relationship_rejects_same_entity(seeded_project):
    from app.services.writer_agent.tool_executors import _propose_relationship

    r = _propose_relationship(
        {
            "entity_a": "A",
            "entity_b": "A",
            "relation_type": "x",
            "description": "d",
            "evidence_snippet": "e",
        },
        seeded_project["project_id"],
    )
    assert "render" not in r


def test_propose_relationship_rejects_missing_evidence(seeded_project):
    from app.services.writer_agent.tool_executors import _propose_relationship

    r = _propose_relationship(
        {
            "entity_a": "A",
            "entity_b": "B",
            "relation_type": "x",
            "description": "d",
            # evidence_snippet missing
        },
        seeded_project["project_id"],
    )
    assert "render" not in r


def test_propose_relationship_rejects_trust_out_of_range(seeded_project):
    from app.services.writer_agent.tool_executors import _propose_relationship

    r = _propose_relationship(
        {
            "entity_a": "A",
            "entity_b": "B",
            "relation_type": "x",
            "description": "d",
            "evidence_snippet": "e",
            "trust_level": 1.5,
        },
        seeded_project["project_id"],
    )
    assert "render" not in r


def test_propose_relationship_does_not_mutate(seeded_project):
    """Critical invariant: no relationships row should appear after propose."""
    from app.services.writer_agent.tool_executors import _propose_relationship

    repo = ManuscriptRepository(seeded_project["engine"])  # noqa: F841 (side-effect-free)
    # Count relationships table before
    from app.tables.novel import relationships as rel_tbl
    from sqlalchemy import func, select

    def count() -> int:
        with seeded_project["engine"].connect() as conn:
            return conn.execute(select(func.count()).select_from(rel_tbl)).scalar_one()

    before = count()
    _propose_relationship(
        {
            "entity_a": "A",
            "entity_b": "B",
            "relation_type": "朋友",
            "description": "d",
            "evidence_snippet": "e",
        },
        seeded_project["project_id"],
    )
    assert count() == before


# ---------------------------------------------------------------------
# execute_tool integration — propose_* tools flow through the public entry
# ---------------------------------------------------------------------


def test_execute_tool_dispatches_propose_tools(seeded_project):
    from app.services.writer_agent.tool_executors import execute_tool

    out = execute_tool(
        "propose_rewrite_span",
        {
            "block_id": seeded_project["block1_id"],
            "original_text": "Alpha",
            "new_text": "阿尔法",
            "reason": "禁词",
        },
        seeded_project["project_id"],
    )
    assert "render" in out
    assert out["render"]["type"] == "prose_diff"
    assert isinstance(out["result"], str)
