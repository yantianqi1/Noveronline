"""ChapterMetaService 单元测试。"""

import json
from datetime import datetime

import pytest

from sqlalchemy import create_engine

from app.database import init_db
from app.repositories.chapter_repo import ChapterRepository
from app.repositories.world_rule_repo import WorldRuleRepository
from app.services.chapter_meta_service import ChapterMetaService


@pytest.fixture
def engine():
    """Create an in-memory engine with all tables."""
    eng = create_engine("sqlite:///:memory:", future=True)
    init_db(eng)
    return eng


@pytest.fixture
def repo(engine):
    return ChapterRepository(engine)


@pytest.fixture
def service(repo):
    return ChapterMetaService(repo=repo)


class TestChapterMetaStorage:
    def test_schema_creation(self, engine):
        """Verify tables are created by init_db."""
        from sqlalchemy import inspect
        inspector = inspect(engine)
        assert "chapter_meta" in inspector.get_table_names()
        assert "chapter_content" in inspector.get_table_names()

    def test_idempotent_schema(self, engine):
        """Ensure multiple init_db calls don't raise."""
        init_db(engine)
        init_db(engine)
        from sqlalchemy import inspect
        inspector = inspect(engine)
        assert "chapter_meta" in inspector.get_table_names()


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

    def test_replace_project_chapter_cards_persists_world_rules_to_db(
        self, engine, service, monkeypatch
    ):
        """章节卡入口携带的世界规则应写入 world_rule_evidence。"""
        from app.services import chapter_meta_service as service_module

        service.replace_project_chapter_cards(
            "proj_rules_from_cards",
            [
                {
                    "chapter_id": "chapter_0001",
                    "chapter_order": 1,
                    "title": "镜湖旧祠",
                    "summary_text": "沈夜进入旧祠。",
                }
            ],
            world_rules=["镜湖城内夜间禁用传讯符。", "", "沈家血脉能感知旧案残响。"],
        )

        rows = WorldRuleRepository(engine).list_rules("proj_rules_from_cards")
        assert [row["fact_text"] for row in rows] == [
            "镜湖城内夜间禁用传讯符。",
            "沈家血脉能感知旧案残响。",
        ]

        def fail_artifact_probe(_project_id: str, artifact_name: str):
            raise AssertionError(f"chapter meta should not load artifact {artifact_name}")

        monkeypatch.setattr(
            service_module, "load_project_artifact", fail_artifact_probe, raising=False
        )
        assert service.get_world_rules("proj_rules_from_cards") == [
            "镜湖城内夜间禁用传讯符。",
            "沈家血脉能感知旧案残响。",
        ]

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

    def test_prev_chapter_ending_uses_structured_end_anchor_without_artifact(
        self, service, monkeypatch
    ):
        """无正文时，上一章结尾应来自 chapter_meta.end_anchor。"""
        from app.services import chapter_meta_service as service_module

        service.upsert_chapter_card(
            "proj_prev_anchor",
            {
                "chapter_id": "chapter_0001",
                "chapter_order": 1,
                "title": "镜湖旧祠",
                "summary_text": "沈夜进入旧祠。",
                "start_anchor": "旧祠门前风铃无声。",
                "end_anchor": "沈夜在香灰下摸到半枚镜湖令。",
            },
        )

        def fail_artifact_probe(_project_id: str, artifact_name: str):
            raise AssertionError(f"chapter meta should not load artifact {artifact_name}")

        monkeypatch.setattr(
            service_module, "load_project_artifact", fail_artifact_probe, raising=False
        )

        ctx = service.get_chapter_continuity_context("proj_prev_anchor", 2)

        assert (
            ctx["continuity_anchor"]["prev_chapter_ending"]
            == "沈夜在香灰下摸到半枚镜湖令。"
        )

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

    def test_world_rules_read_from_structured_db_without_artifact(self, engine, service):
        """世界规则应优先从 world_rule_evidence 表读取。"""
        now = datetime.now().isoformat()
        rules = WorldRuleRepository(engine)
        rules.upsert_world_rule(
            "proj_rules_db",
            {
                "evidence_id": "rule_001",
                "fact_text": "镜湖城内夜间禁用传讯符。",
                "segment_id": "seg_001",
                "chapter_order": 1,
                "evidence_snippet": "城规写明夜间禁符。",
                "created_at": now,
            },
        )
        rules.upsert_world_rule(
            "proj_rules_db",
            {
                "evidence_id": "rule_002",
                "fact_text": "沈家血脉能感知旧案残响。",
                "segment_id": "seg_002",
                "chapter_order": 2,
                "evidence_snippet": "沈夜听见旧案残响。",
                "created_at": now,
            },
        )

        assert service.get_world_rules("proj_rules_db") == [
            "镜湖城内夜间禁用传讯符。",
            "沈家血脉能感知旧案残响。",
        ]

    def test_world_rules_do_not_fall_back_to_story_memory_artifact(
        self, service, monkeypatch
    ):
        """无结构化世界规则时，运行时不应读取 story_memory artifact。"""
        from app.services import chapter_meta_service as service_module

        def fail_artifact_probe(_project_id: str, artifact_name: str):
            raise AssertionError(f"chapter meta should not load artifact {artifact_name}")

        monkeypatch.setattr(
            service_module, "load_project_artifact", fail_artifact_probe, raising=False
        )

        assert service.get_world_rules("proj_no_rules") == []

    def test_prev_chapter_ending_reads_from_chapter_content_without_artifact(
        self, repo, service
    ):
        """上一章结尾应从 chapter_content.content 读取。"""
        repo.create_chapter(
            "proj_prev_db",
            "chapter_0001",
            chapter_order=1,
            title="密信初现",
        )
        repo.update_chapter(
            "proj_prev_db",
            "chapter_0001",
            content="沈夜翻开密信，发现落款早已被水浸花。线索最终指向镜湖旧祠。",
            word_count=32,
            status="draft",
        )

        assert service._get_prev_chapter_ending("proj_prev_db", 2).endswith(
            "线索最终指向镜湖旧祠。"
        )

    def test_prev_chapter_ending_does_not_fall_back_to_chapter_segments_artifact(
        self, service, monkeypatch
    ):
        """缺少上一章结构化正文/锚点时，运行时不应读取 chapter_segments artifact。"""
        from app.services import chapter_meta_service as service_module

        def fail_artifact_probe(_project_id: str, artifact_name: str):
            raise AssertionError(f"chapter meta should not load artifact {artifact_name}")

        monkeypatch.setattr(
            service_module, "load_project_artifact", fail_artifact_probe, raising=False
        )

        assert service._get_prev_chapter_ending("proj_prev_missing", 2) == ""
