"""Tests for manuscript blocks: DB CRUD, context builder, and API."""

import json
import os
import tempfile

import pytest

from app.config import Config
from app.services.writer_agent.novel_db import NovelDB
from app.services.writer_agent.manuscript_context_builder import build_continuation_context


@pytest.fixture
def db(tmp_path):
    """Provide a NovelDB instance with a temp upload dir."""
    Config.UPLOAD_FOLDER = str(tmp_path)
    novel_db = NovelDB()
    novel_db.ensure_schema("test_project")
    return novel_db


PROJECT = "test_project"


class TestManuscriptBlocksCRUD:
    def test_commit_and_list(self, db):
        result = db.commit_manuscript_block(PROJECT, "第一段正文内容，李明走进了密室。")
        assert result["block_id"].startswith("mb_")
        assert result["word_count"] > 0
        assert result["block_order"] == 10  # first block, gap=10

        blocks = db.list_manuscript_blocks(PROJECT)
        assert len(blocks) == 1
        assert blocks[0]["content"] == "第一段正文内容，李明走进了密室。"

    def test_commit_multiple_blocks_ordering(self, db):
        db.commit_manuscript_block(PROJECT, "段落一")
        db.commit_manuscript_block(PROJECT, "段落二")
        db.commit_manuscript_block(PROJECT, "段落三")

        blocks = db.list_manuscript_blocks(PROJECT)
        assert len(blocks) == 3
        orders = [b["block_order"] for b in blocks]
        assert orders == sorted(orders)
        assert blocks[0]["content"] == "段落一"
        assert blocks[2]["content"] == "段落三"

    def test_commit_insert_after(self, db):
        b1 = db.commit_manuscript_block(PROJECT, "段落一")
        b3 = db.commit_manuscript_block(PROJECT, "段落三")
        b2 = db.commit_manuscript_block(
            PROJECT, "段落二", insert_after_block_id=b1["block_id"]
        )

        blocks = db.list_manuscript_blocks(PROJECT)
        assert len(blocks) == 3
        contents = [b["content"] for b in blocks]
        assert contents == ["段落一", "段落二", "段落三"]

    def test_update_block_content(self, db):
        result = db.commit_manuscript_block(PROJECT, "原始内容")
        db.update_manuscript_block(
            PROJECT, result["block_id"], content="修改后的内容"
        )
        block = db.get_manuscript_block(PROJECT, result["block_id"])
        assert block["content"] == "修改后的内容"
        assert block["word_count"] == len("修改后的内容")

    def test_update_block_metadata(self, db):
        result = db.commit_manuscript_block(PROJECT, "测试内容")
        db.update_manuscript_block(
            PROJECT, result["block_id"],
            summary="这是一段测试内容",
            open_threads_json=json.dumps(["悬念1", "悬念2"]),
            pov_entity_id="ent_liming",
            location="密室",
            narrative_note="紧张",
        )
        block = db.get_manuscript_block(PROJECT, result["block_id"])
        assert block["summary"] == "这是一段测试内容"
        assert json.loads(block["open_threads_json"]) == ["悬念1", "悬念2"]
        assert block["pov_entity_id"] == "ent_liming"
        assert block["location"] == "密室"

    def test_delete_block(self, db):
        result = db.commit_manuscript_block(PROJECT, "要删除的内容")
        db.delete_manuscript_block(PROJECT, result["block_id"])
        blocks = db.list_manuscript_blocks(PROJECT)
        assert len(blocks) == 0

    def test_reorder_blocks(self, db):
        b1 = db.commit_manuscript_block(PROJECT, "一")
        b2 = db.commit_manuscript_block(PROJECT, "二")
        b3 = db.commit_manuscript_block(PROJECT, "三")

        db.reorder_manuscript_blocks(
            PROJECT, [b3["block_id"], b1["block_id"], b2["block_id"]]
        )
        blocks = db.list_manuscript_blocks(PROJECT)
        contents = [b["content"] for b in blocks]
        assert contents == ["三", "一", "二"]

    def test_tag_blocks(self, db):
        b1 = db.commit_manuscript_block(PROJECT, "一")
        b2 = db.commit_manuscript_block(PROJECT, "二")
        b3 = db.commit_manuscript_block(PROJECT, "三")

        count = db.tag_manuscript_blocks(
            PROJECT, [b1["block_id"], b2["block_id"]], "第一章"
        )
        assert count == 2

        blocks = db.list_manuscript_blocks(PROJECT)
        assert blocks[0]["chapter_tag"] == "第一章"
        assert blocks[1]["chapter_tag"] == "第一章"
        assert blocks[2]["chapter_tag"] is None

    def test_get_stats(self, db):
        db.commit_manuscript_block(PROJECT, "一" * 100)
        db.commit_manuscript_block(PROJECT, "二" * 200)
        b3 = db.commit_manuscript_block(PROJECT, "三" * 50)
        db.tag_manuscript_blocks(PROJECT, [b3["block_id"]], "第二章")

        stats = db.get_manuscript_stats(PROJECT)
        assert stats["total_blocks"] == 3
        assert stats["total_words"] == 350
        assert "第二章" in stats["chapter_tags"]

    def test_export(self, db):
        db.commit_manuscript_block(PROJECT, "段落一")
        db.commit_manuscript_block(PROJECT, "段落二")
        text = db.export_manuscript(PROJECT)
        assert text == "段落一\n\n段落二"

    def test_search_fts_chinese_3char(self, db):
        """Trigram FTS works for 3+ character Chinese queries."""
        db.commit_manuscript_block(PROJECT, "李明走进了密室，发现了一把古剑。")
        db.commit_manuscript_block(PROJECT, "王雪在塔楼上等待消息。")

        results = db.search_manuscript_fts(PROJECT, "密室，发")
        assert len(results) >= 1

    def test_search_fts_chinese_2char_like_fallback(self, db):
        """2-character Chinese queries use LIKE fallback."""
        db.commit_manuscript_block(PROJECT, "李明走进了密室，发现了一把古剑。")
        db.commit_manuscript_block(PROJECT, "王雪在塔楼上等待消息。")

        results = db.search_manuscript_fts(PROJECT, "密室")
        assert len(results) >= 1

        results2 = db.search_manuscript_fts(PROJECT, "塔楼")
        assert len(results2) >= 1

    def test_search_fts_multiword_chinese(self, db):
        """Multi-word Chinese queries (space-separated) match via AND logic."""
        db.commit_manuscript_block(PROJECT, "李明走进了密室，发现了一把古剑。王雪也在场。")
        db.commit_manuscript_block(PROJECT, "王雪在塔楼上等待消息。")

        # Both terms appear in block 1 only
        results = db.search_manuscript_fts(PROJECT, "李明走 王雪也")
        assert len(results) >= 1

        # Single term still works
        results2 = db.search_manuscript_fts(PROJECT, "塔楼上等")
        assert len(results2) >= 1

    def test_list_without_content(self, db):
        db.commit_manuscript_block(PROJECT, "长正文" * 100)
        blocks = db.list_manuscript_blocks(PROJECT, include_content=False)
        assert len(blocks) == 1
        assert "content" not in blocks[0]


class TestContinuationContext:
    def test_empty_manuscript(self, db):
        ctx = build_continuation_context(PROJECT)
        assert ctx["recent_summaries"] == []
        assert ctx["active_threads"] == []
        assert ctx["tail_text"] == ""
        assert ctx["total_blocks"] == 0

    def test_basic_context(self, db):
        content = "这是一段比较长的正文内容。" * 50
        b1 = db.commit_manuscript_block(PROJECT, content)
        # Manually set metadata since we won't call LLM
        db.update_manuscript_block(
            PROJECT, b1["block_id"],
            summary="李明探索密室",
            open_threads_json=json.dumps(["密信来源", "守卫身份"]),
            pov_entity_id="ent_liming",
            location="地下密室",
            narrative_note="紧张悬疑",
        )

        ctx = build_continuation_context(PROJECT)
        assert ctx["last_pov"] == "ent_liming"
        assert ctx["last_location"] == "地下密室"
        assert ctx["narrative_note"] == "紧张悬疑"
        assert len(ctx["tail_text"]) > 0
        assert len(ctx["active_threads"]) == 2
        assert ctx["total_blocks"] == 1

    def test_multiple_blocks_context(self, db):
        for i in range(5):
            b = db.commit_manuscript_block(PROJECT, f"段落{i}的内容" * 20)
            db.update_manuscript_block(
                PROJECT, b["block_id"],
                summary=f"第{i}段摘要",
                open_threads_json=json.dumps([f"伏笔{i}"]),
            )

        ctx = build_continuation_context(PROJECT)
        assert ctx["total_blocks"] == 5
        assert len(ctx["recent_summaries"]) > 0
        # Summaries should be in chronological order
        orders = [s["block_order"] for s in ctx["recent_summaries"]]
        assert orders == sorted(orders)

    def test_null_metadata_blocks(self, db):
        """Blocks with no metadata should not crash."""
        db.commit_manuscript_block(PROJECT, "无元数据段落")
        ctx = build_continuation_context(PROJECT)
        assert ctx["total_blocks"] == 1
        assert ctx["tail_text"] == "无元数据段落"
        assert ctx["recent_summaries"] == []  # no summary set

    def test_thread_deduplication(self, db):
        for i in range(3):
            b = db.commit_manuscript_block(PROJECT, f"段落{i}")
            db.update_manuscript_block(
                PROJECT, b["block_id"],
                open_threads_json=json.dumps(["重复伏笔", f"伏笔{i}"]),
            )

        ctx = build_continuation_context(PROJECT)
        thread_values = ctx["active_threads"]
        assert len(set(thread_values)) == len(thread_values), "Threads should be deduplicated"
