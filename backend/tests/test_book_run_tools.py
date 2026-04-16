"""MVP smoke tests for the book_run feature: data layer + agent tools.

Covers:
- word_count utility
- BookPlanRepository CRUD
- scan_forbidden_lexicon tool (literal / regex / whitelist)
- splice_block tool (before / after / replace_range + over-swing rejection)
- rewrite_span tool (uniqueness guard + delta cap)

LLM-driven flows (BookRunOrchestrator end-to-end) are not unit-tested here
— run them manually via the frontend 成书 tab.
"""

from __future__ import annotations

import pytest


# ----------------------------------------------------------------------
# Shared fixture: temp DB + one empty project + one chapter with 3 blocks
# ----------------------------------------------------------------------


@pytest.fixture()
def project_env(monkeypatch, tmp_path):
    upload_root = tmp_path / "uploads"
    (upload_root / "system").mkdir(parents=True)
    (upload_root / "projects" / "proj_bookrun").mkdir(parents=True)

    from app.config import Config
    from app.models.project import ProjectManager

    monkeypatch.setattr(Config, "UPLOAD_FOLDER", str(upload_root))
    monkeypatch.setattr(ProjectManager, "PROJECTS_DIR", str(upload_root / "projects"))

    # Build a fresh in-memory DB per test to avoid cross-test pollution.
    from sqlalchemy import create_engine
    from app.database import init_db

    engine = create_engine("sqlite:///:memory:", future=True)
    init_db(engine)

    from app.repositories.chapter_repo import ChapterRepository
    from app.services.assets.manuscript_adapter import ManuscriptAssetAdapter

    project_id = "proj_bookrun"
    chapter_repo = ChapterRepository(engine)
    chapter_id = "chap_test01"
    chapter_repo.create_chapter(project_id, chapter_id, 1, title="测试章")

    adapter = ManuscriptAssetAdapter(
        project_id,
        chapter_lookup=lambda cid: chapter_repo.get_chapter(project_id, cid) if cid else None,
    )
    b1 = adapter.commit("苏小雨走进咖啡馆，阳光洒在桌面。", chapter_id=chapter_id)
    b2 = adapter.commit("她突然想起了什么，眉头微皱。", chapter_id=chapter_id, insert_after_block_id=b1["block_id"])
    b3 = adapter.commit("窗外的街道显得格外安静。", chapter_id=chapter_id, insert_after_block_id=b2["block_id"])

    return {
        "project_id": project_id,
        "chapter_id": chapter_id,
        "block_ids": [b1["block_id"], b2["block_id"], b3["block_id"]],
    }


# ----------------------------------------------------------------------
# word_count
# ----------------------------------------------------------------------


def test_count_cjk_chars_excludes_whitespace():
    from app.utils.word_count import count_cjk_chars

    assert count_cjk_chars("苏小雨走进了咖啡馆。") == 10
    assert count_cjk_chars("  苏小雨  \n 走进了 \t 咖啡馆 。  ") == 10
    assert count_cjk_chars("") == 0
    assert count_cjk_chars(None) == 0


def test_count_cjk_chars_keeps_punctuation():
    from app.utils.word_count import count_cjk_chars

    text = "他说：“你来了。”"
    assert count_cjk_chars(text) == len("他说：“你来了。”")


# ----------------------------------------------------------------------
# BookPlanRepository CRUD
# ----------------------------------------------------------------------


def test_book_plan_repo_crud(project_env):
    from app.services.writer_agent.book_plan_service import BookPlanService

    svc = BookPlanService()
    plan = svc.create_plan(
        project_id=project_env["project_id"],
        title="卷一·起势",
        chapter_count=3,
        per_chapter_word_target=2000,
        word_tolerance_pct=15,
        overall_direction="主角从躲避到反击",
        forbidden_lexicon_asset_ids=["lex_a", "lex_b"],
    )
    assert plan["plan_id"].startswith("bp_")
    assert plan["chapter_count"] == 3
    assert plan["status"] == "draft"
    assert plan["forbidden_lexicon_asset_ids"] == ["lex_a", "lex_b"]

    plan_id = plan["plan_id"]

    svc.set_status(plan_id, "writing", last_stage="CHAPTER_WRITE#1", current_chapter_order=1)
    refreshed = svc.get_plan(plan_id)
    assert refreshed["status"] == "writing"
    assert refreshed["current_chapter_order"] == 1

    svc.append_chapter_id(plan_id, "chap_x")
    svc.append_chapter_id(plan_id, "chap_y")
    svc.append_chapter_id(plan_id, "chap_x")  # dedup
    refreshed = svc.get_plan(plan_id)
    assert refreshed["chapter_ids"] == ["chap_x", "chap_y"]

    svc.append_error(plan_id, {"stage": "WORD_AUDIT", "error": "failed"})
    refreshed = svc.get_plan(plan_id)
    assert len(refreshed["error_log"]) == 1

    listed = svc.list_plans(project_env["project_id"])
    assert any(p["plan_id"] == plan_id for p in listed)

    svc.delete_plan(plan_id)
    assert svc.get_plan(plan_id) is None


# ----------------------------------------------------------------------
# scan_forbidden_lexicon
# ----------------------------------------------------------------------


def _make_lexicon(project_id: str, entries: list) -> str:
    from app.services.assets.assets_service import AssetsService
    svc = AssetsService()
    created = svc.create(
        scope="project",
        project_id=project_id,
        asset_type="forbidden_lexicon",
        title="测试禁词",
        payload={"entries": entries},
    )
    return created["asset_id"]


def test_scan_forbidden_lexicon_literal_hit(project_env):
    from app.services.writer_agent.tool_executors import _scan_forbidden_lexicon

    asset_id = _make_lexicon(project_env["project_id"], [{"pattern": "突然", "match_type": "literal", "severity": "block"}])
    result = _scan_forbidden_lexicon(
        {"chapter_id": project_env["chapter_id"], "lexicon_asset_ids": [asset_id]},
        project_env["project_id"],
    )
    assert "命中 1 处" in result
    assert "突然" in result


def test_scan_forbidden_lexicon_regex_hit(project_env):
    from app.services.writer_agent.tool_executors import _scan_forbidden_lexicon

    asset_id = _make_lexicon(
        project_env["project_id"],
        [{"pattern": r"眉头[微轻]?皱", "match_type": "regex", "severity": "warn"}],
    )
    result = _scan_forbidden_lexicon(
        {"chapter_id": project_env["chapter_id"], "lexicon_asset_ids": [asset_id]},
        project_env["project_id"],
    )
    assert "命中" in result
    assert "眉头" in result


def test_scan_forbidden_lexicon_no_hit(project_env):
    from app.services.writer_agent.tool_executors import _scan_forbidden_lexicon

    asset_id = _make_lexicon(project_env["project_id"], ["完全不存在的词"])
    result = _scan_forbidden_lexicon(
        {"chapter_id": project_env["chapter_id"], "lexicon_asset_ids": [asset_id]},
        project_env["project_id"],
    )
    assert "未命中" in result


def test_scan_forbidden_lexicon_whitelist_exception(project_env):
    """Hit suppressed when the surrounding 40-char context contains a whitelist entry."""
    from app.services.writer_agent.tool_executors import _scan_forbidden_lexicon

    asset_id = _make_lexicon(
        project_env["project_id"],
        [{
            "pattern": "突然",
            "match_type": "literal",
            "whitelist_contexts": ["想起了"],  # 'b2' block has "突然想起了"
        }],
    )
    result = _scan_forbidden_lexicon(
        {"chapter_id": project_env["chapter_id"], "lexicon_asset_ids": [asset_id]},
        project_env["project_id"],
    )
    assert "未命中" in result


# ----------------------------------------------------------------------
# splice_block
# ----------------------------------------------------------------------


def test_splice_block_after(project_env):
    from app.services.writer_agent.tool_executors import _splice_block
    from app.services.writer_agent.manuscript_service import _get_adapter

    block_ids = project_env["block_ids"]
    result = _splice_block(
        {
            "chapter_id": project_env["chapter_id"],
            "anchor_block_id": block_ids[0],
            "position": "after",
            "content": "她点了一杯美式。",
            "reason": "补充动作细节",
        },
        project_env["project_id"],
    )
    assert "插入新块" in result

    adapter = _get_adapter(project_env["project_id"])
    blocks = adapter.list_blocks(chapter_id=project_env["chapter_id"])
    assert len(blocks) == 4


def test_splice_block_before(project_env):
    from app.services.writer_agent.tool_executors import _splice_block
    from app.services.writer_agent.manuscript_service import _get_adapter

    block_ids = project_env["block_ids"]
    _splice_block(
        {
            "chapter_id": project_env["chapter_id"],
            "anchor_block_id": block_ids[1],
            "position": "before",
            "content": "时间在此停顿了一拍。",
        },
        project_env["project_id"],
    )
    adapter = _get_adapter(project_env["project_id"])
    blocks = sorted(adapter.list_blocks(chapter_id=project_env["chapter_id"]), key=lambda b: b["block_order"])
    assert len(blocks) == 4
    # New block should be at position 1 (between original #0 and #1)
    assert "停顿" in blocks[1]["content"]


def test_splice_block_replace_range(project_env):
    from app.services.writer_agent.tool_executors import _splice_block
    from app.services.writer_agent.manuscript_service import _get_adapter

    block_ids = project_env["block_ids"]
    result = _splice_block(
        {
            "chapter_id": project_env["chapter_id"],
            "anchor_block_id": block_ids[0],
            "end_anchor_block_id": block_ids[1],
            "position": "replace_range",
            "content": "她走进咖啡馆，心里突然冒出一个念头。",
        },
        project_env["project_id"],
    )
    assert "替换区间" in result
    adapter = _get_adapter(project_env["project_id"])
    blocks = adapter.list_blocks(chapter_id=project_env["chapter_id"])
    assert len(blocks) == 2


def test_splice_block_over_swing_rejected(project_env):
    from app.services.writer_agent.tool_executors import _splice_block

    huge = "内容" * 4000  # 8000 chars > 5000 hard cap
    result = _splice_block(
        {
            "chapter_id": project_env["chapter_id"],
            "anchor_block_id": project_env["block_ids"][0],
            "position": "after",
            "content": huge,
        },
        project_env["project_id"],
    )
    assert "被拒绝" in result


# ----------------------------------------------------------------------
# rewrite_span
# ----------------------------------------------------------------------


def test_rewrite_span_unique(project_env):
    from app.services.writer_agent.tool_executors import _rewrite_span
    from app.services.writer_agent.manuscript_service import _get_adapter

    block_id = project_env["block_ids"][1]
    result = _rewrite_span(
        {
            "block_id": block_id,
            "original_text": "突然",
            "new_text": "霎时",
            "reason": "禁词替换",
        },
        project_env["project_id"],
    )
    assert "1 次替换" in result
    adapter = _get_adapter(project_env["project_id"])
    block = adapter.get_block(block_id)
    assert "霎时" in block["content"]
    assert "突然" not in block["content"]


def test_rewrite_span_ambiguous_rejected(project_env):
    from app.services.writer_agent.tool_executors import _rewrite_span
    from app.services.writer_agent.manuscript_service import _get_adapter

    # Create a block with a repeated substring
    adapter = _get_adapter(project_env["project_id"])
    res = adapter.commit("好好，好好的。", chapter_id=project_env["chapter_id"])
    block_id = res["block_id"]

    result = _rewrite_span(
        {
            "block_id": block_id,
            "original_text": "好好",  # appears twice
            "new_text": "妥",
        },
        project_env["project_id"],
    )
    assert "不唯一" in result


def test_rewrite_span_missing_original(project_env):
    from app.services.writer_agent.tool_executors import _rewrite_span

    result = _rewrite_span(
        {
            "block_id": project_env["block_ids"][0],
            "original_text": "不存在的原文",
            "new_text": "替换",
        },
        project_env["project_id"],
    )
    assert "未出现" in result


def test_rewrite_span_delta_cap_rejected(project_env):
    from app.services.writer_agent.tool_executors import _rewrite_span

    result = _rewrite_span(
        {
            "block_id": project_env["block_ids"][0],
            "original_text": "苏小雨",
            "new_text": "苏小雨" + ("扩写" * 2000),  # 4003 chars delta
        },
        project_env["project_id"],
    )
    assert "被拒绝" in result
