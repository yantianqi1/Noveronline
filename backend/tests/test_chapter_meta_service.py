"""ChapterMetaService 单元测试。"""

import json
import os
import sqlite3
import tempfile

import pytest

from app.services.chapter_meta_storage import ChapterMetaStorage
from app.services.chapter_meta_service import ChapterMetaService


@pytest.fixture
def tmp_db():
    """创建临时数据库路径。"""
    with tempfile.TemporaryDirectory() as tmpdir:
        yield os.path.join(tmpdir, "test_chapter_meta.sqlite3")


@pytest.fixture
def storage(tmp_db):
    return ChapterMetaStorage(db_path=tmp_db)


@pytest.fixture
def service(storage):
    return ChapterMetaService(storage=storage)


class TestChapterMetaStorage:
    def test_schema_creation(self, storage):
        """验证表和索引成功创建。"""
        with storage.connect() as conn:
            tables = conn.execute(
                "SELECT name FROM sqlite_master WHERE type='table' AND name='chapter_meta'"
            ).fetchall()
            assert len(tables) == 1

    def test_idempotent_schema(self, storage):
        """确保多次 ensure_schema 不会报错。"""
        storage.ensure_schema()
        storage.ensure_schema()
        with storage.connect() as conn:
            tables = conn.execute(
                "SELECT name FROM sqlite_master WHERE type='table' AND name='chapter_meta'"
            ).fetchall()
            assert len(tables) == 1

    def test_ensure_schema_rebuilds_legacy_chapter_index_unique_constraint(self, tmp_db):
        """旧库若唯一索引仍指向 chapter_index，应迁移到 chapter_order。"""
        conn = sqlite3.connect(tmp_db)
        conn.execute(
            """
            CREATE TABLE chapter_meta (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                project_id TEXT NOT NULL,
                chapter_index INTEGER NOT NULL,
                chapter_id TEXT NOT NULL DEFAULT '',
                title TEXT NOT NULL DEFAULT '',
                summary_text TEXT NOT NULL DEFAULT '',
                open_threads_json TEXT NOT NULL DEFAULT '[]',
                timeline_note TEXT NOT NULL DEFAULT '',
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL
            )
            """
        )
        conn.execute(
            "CREATE UNIQUE INDEX idx_chapter_meta_unique ON chapter_meta(project_id, chapter_index)"
        )
        conn.execute(
            "CREATE INDEX idx_chapter_meta_project ON chapter_meta(project_id, chapter_index ASC)"
        )
        conn.execute(
            """
            INSERT INTO chapter_meta (
                project_id, chapter_index, chapter_id, title, summary_text,
                open_threads_json, timeline_note, created_at, updated_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            ("proj_legacy", 1, "chapter_0001", "旧标题", "旧摘要", "[]", "", "now", "now"),
        )
        conn.commit()
        conn.close()

        storage = ChapterMetaStorage(db_path=tmp_db)
        service = ChapterMetaService(storage=storage)

        service.save_chapter_summary(
            project_id="proj_legacy",
            chapter_index=1,
            summary_text="新摘要",
        )

        with storage.connect() as conn:
            index_cols = conn.execute(
                "PRAGMA index_info(idx_chapter_meta_unique)"
            ).fetchall()
            assert [row["name"] for row in index_cols] == ["project_id", "chapter_order"]

        result = service.get_single_summary("proj_legacy", 1)
        assert result is not None
        assert result["summary_text"] == "新摘要"



class TestChapterMetaServiceWrite:
    def test_save_and_retrieve(self, service):
        """保存摘要后能正确取回。"""
        service.save_chapter_summary(
            project_id="proj_test1",
            chapter_index=0,
            summary_text="第一章摘要：主角进入废塔。",
            chapter_id="ch_001",
            title="废塔初探",
            open_threads=["暗门悬念", "神秘脚步声"],
            timeline_note="故事第一天，清晨",
        )
        result = service.get_single_summary("proj_test1", 0)
        assert result is not None
        assert result["summary_text"] == "第一章摘要：主角进入废塔。"
        assert result["chapter_id"] == "ch_001"
        assert result["title"] == "废塔初探"
        assert result["open_threads"] == ["暗门悬念", "神秘脚步声"]
        assert result["timeline_note"] == "故事第一天，清晨"

    def test_upsert_overwrites(self, service):
        """同一 project_id + chapter_index 应覆盖。"""
        service.save_chapter_summary(
            project_id="proj_test1",
            chapter_index=0,
            summary_text="旧摘要",
        )
        service.save_chapter_summary(
            project_id="proj_test1",
            chapter_index=0,
            summary_text="新摘要",
            title="更新后",
        )
        result = service.get_single_summary("proj_test1", 0)
        assert result is not None
        assert result["summary_text"] == "新摘要"
        assert result["title"] == "更新后"

    def test_multiple_chapters(self, service):
        """多章保存后按顺序取回。"""
        for i in range(5):
            service.save_chapter_summary(
                project_id="proj_multi",
                chapter_index=i,
                summary_text=f"第{i}章摘要",
            )
        summaries = service.get_chapter_summaries("proj_multi")
        assert len(summaries) == 5
        assert summaries[0]["chapter_index"] == 0
        assert summaries[4]["chapter_index"] == 4

    def test_get_summaries_range(self, service):
        """按范围获取摘要。"""
        for i in range(5):
            service.save_chapter_summary(
                project_id="proj_range",
                chapter_index=i,
                summary_text=f"第{i}章",
            )
        summaries = service.get_chapter_summaries("proj_range", from_index=2, to_index=3)
        assert len(summaries) == 2
        assert summaries[0]["chapter_index"] == 2
        assert summaries[1]["chapter_index"] == 3

    def test_different_projects_isolated(self, service):
        """不同项目的摘要互相隔离。"""
        service.save_chapter_summary("proj_a", 0, "A的第0章")
        service.save_chapter_summary("proj_b", 0, "B的第0章")
        a = service.get_single_summary("proj_a", 0)
        b = service.get_single_summary("proj_b", 0)
        assert a["summary_text"] == "A的第0章"
        assert b["summary_text"] == "B的第0章"


class TestChapterContinuityContext:
    def test_first_chapter_returns_empty_anchor(self, service):
        """第一章（index=0）没有前章信息。"""
        ctx = service.get_chapter_continuity_context("proj_empty", 0)
        anchor = ctx["continuity_anchor"]
        assert anchor["prev_chapter_ending"] == ""
        assert anchor["chapter_summaries"] == []
        assert anchor["open_threads"] == []
        assert anchor["timeline_note"] == ""

    def test_second_chapter_with_one_summary(self, service):
        """有一章摘要时，能正确构造 continuity_anchor。"""
        service.save_chapter_summary(
            project_id="proj_ctx",
            chapter_index=0,
            summary_text="第0章：主角发现暗门。",
            open_threads=["暗门通向何处", "敌人身份不明"],
            timeline_note="第一天清晨",
        )
        ctx = service.get_chapter_continuity_context("proj_ctx", 1)
        anchor = ctx["continuity_anchor"]
        assert len(anchor["chapter_summaries"]) == 1
        assert anchor["chapter_summaries"][0]["chapter_index"] == 0
        assert "暗门" in anchor["chapter_summaries"][0]["summary"]
        assert "暗门通向何处" in anchor["open_threads"]
        assert "敌人身份不明" in anchor["open_threads"]
        assert anchor["timeline_note"] == "第一天清晨"

    def test_lookback_limited_to_three(self, service):
        """回溯最多3章。"""
        for i in range(6):
            service.save_chapter_summary(
                project_id="proj_lookback",
                chapter_index=i,
                summary_text=f"第{i}章摘要",
                open_threads=[f"线索_{i}"],
            )
        ctx = service.get_chapter_continuity_context("proj_lookback", 6)
        anchor = ctx["continuity_anchor"]
        # 应该只取 index 3, 4, 5
        assert len(anchor["chapter_summaries"]) == 3
        assert anchor["chapter_summaries"][0]["chapter_index"] == 3
        assert anchor["chapter_summaries"][2]["chapter_index"] == 5

    def test_open_threads_deduplicated(self, service):
        """open_threads 不应有重复。"""
        service.save_chapter_summary(
            "proj_dedup", 0, "ch0",
            open_threads=["线索A", "线索B"],
        )
        service.save_chapter_summary(
            "proj_dedup", 1, "ch1",
            open_threads=["线索B", "线索C"],
        )
        ctx = service.get_chapter_continuity_context("proj_dedup", 2)
        anchor = ctx["continuity_anchor"]
        assert anchor["open_threads"] == ["线索A", "线索B", "线索C"]

    def test_timeline_note_from_latest(self, service):
        """timeline_note 取最近一章的。"""
        service.save_chapter_summary(
            "proj_time", 0, "ch0", timeline_note="第一天",
        )
        service.save_chapter_summary(
            "proj_time", 1, "ch1", timeline_note="第二天傍晚",
        )
        ctx = service.get_chapter_continuity_context("proj_time", 2)
        assert ctx["continuity_anchor"]["timeline_note"] == "第二天傍晚"

    def test_nonexistent_project_returns_empty(self, service):
        """不存在的项目返回空 anchor。"""
        ctx = service.get_chapter_continuity_context("proj_nonexist", 3)
        anchor = ctx["continuity_anchor"]
        assert anchor["prev_chapter_ending"] == ""
        assert anchor["chapter_summaries"] == []
