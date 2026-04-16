"""Tests for the writer agent system: repos, tools, agent loop, orchestrator."""

import asyncio
import json
import os
import uuid

import pytest

from sqlalchemy import create_engine, insert

import app.database as db_mod
from app.database import init_db
from app.repositories.chapter_repo import ChapterRepository
from app.repositories.entity_repo import EntityRepository
from app.repositories.outline_repo import OutlineRepository
from app.repositories.preset_repo import PresetRepository
from app.repositories.scene_repo import SceneRepository
from app.tables.novel import entities, entity_aliases


# ---------------------------------------------------------------------------
# Shared helper: set up a fresh in-memory engine for each test class
# ---------------------------------------------------------------------------

def _make_engine(monkeypatch):
    """Create an in-memory engine, init all tables, and monkeypatch get_engine()."""
    engine = create_engine("sqlite:///:memory:", future=True)
    init_db(engine)
    monkeypatch.setattr(db_mod, "_engine", engine)
    return engine


# ---------------------------------------------------------------------------
# Chapter/Scene/Entity/Preset repo tests (formerly TestNovelDB)
# ---------------------------------------------------------------------------
class TestNovelDB:
    """Test the unified repository layer."""

    TEST_PROJECT = f"__test_{uuid.uuid4().hex[:8]}"

    @pytest.fixture(autouse=True)
    def setup_teardown(self, monkeypatch):
        self.engine = _make_engine(monkeypatch)
        self.chapters = ChapterRepository(self.engine)
        self.scenes = SceneRepository(self.engine)
        self.entities = EntityRepository(self.engine)
        self.presets = PresetRepository(self.engine)
        self.outlines = OutlineRepository(self.engine)
        yield

    def test_schema_creates_tables(self):
        from sqlalchemy import inspect
        inspector = inspect(self.engine)
        table_names = set(inspector.get_table_names())
        expected = {
            "entities", "entity_aliases", "entity_labels",
            "relationships", "entity_evidence",
            "chapter_content", "chapter_meta", "scenes",
            "sessions", "agent_states", "agent_memory", "world_events",
            "writer_presets", "outline_versions",
        }
        assert expected.issubset(table_names), f"Missing tables: {expected - table_names}"

    def test_chapter_crud(self):
        self.chapters.create_chapter(self.TEST_PROJECT, "ch_1", 1, "第一章")
        chapters = self.chapters.list_chapters(self.TEST_PROJECT)
        assert len(chapters) == 1
        assert chapters[0]["title"] == "第一章"

        self.chapters.update_chapter(self.TEST_PROJECT, "ch_1", title="第一章·改")
        ch = self.chapters.get_chapter_by_order(self.TEST_PROJECT, 1)
        assert ch["title"] == "第一章·改"

        self.chapters.delete_chapter(self.TEST_PROJECT, "ch_1")
        assert len(self.chapters.list_chapters(self.TEST_PROJECT)) == 0

    def test_scene_crud_and_compile(self):
        self.chapters.create_chapter(self.TEST_PROJECT, "ch_1", 1, "第一章")

        self.scenes.upsert_scene(
            self.TEST_PROJECT,
            {"scene_id": "sc_1", "chapter_id": "ch_1", "scene_order": 1,
             "title": "场景一", "content": "月光穿过竹叶。", "location": "竹林",
             "involved_entities_json": "[]", "status": "draft"},
        )
        self.scenes.upsert_scene(
            self.TEST_PROJECT,
            {"scene_id": "sc_2", "chapter_id": "ch_1", "scene_order": 2,
             "title": "场景二", "content": "剑气纵横。", "location": "演武场",
             "involved_entities_json": "[]", "status": "draft"},
        )

        scenes = self.scenes.list_scenes(self.TEST_PROJECT, "ch_1")
        assert len(scenes) == 2
        assert scenes[0]["scene_order"] == 1

        scene = self.scenes.get_scene(self.TEST_PROJECT, "sc_1")
        assert scene["content"] == "月光穿过竹叶。"
        assert scene["word_count"] > 0

        self.chapters.compile_chapter(self.TEST_PROJECT, "ch_1")
        ch = self.chapters.get_chapter(self.TEST_PROJECT, "ch_1", include_content=True)
        assert "月光穿过竹叶" in ch["content"]
        assert "剑气纵横" in ch["content"]

    def test_scene_reorder(self):
        self.chapters.create_chapter(self.TEST_PROJECT, "ch_1", 1, "第一章")
        self.scenes.upsert_scene(
            self.TEST_PROJECT,
            {"scene_id": "sc_a", "chapter_id": "ch_1", "scene_order": 1,
             "title": "A", "content": "内容A", "involved_entities_json": "[]", "status": "draft"},
        )
        self.scenes.upsert_scene(
            self.TEST_PROJECT,
            {"scene_id": "sc_b", "chapter_id": "ch_1", "scene_order": 2,
             "title": "B", "content": "内容B", "involved_entities_json": "[]", "status": "draft"},
        )

        self.scenes.reorder_scenes(self.TEST_PROJECT, "ch_1", ["sc_b", "sc_a"])
        scenes = self.scenes.list_scenes(self.TEST_PROJECT, "ch_1")
        assert scenes[0]["scene_id"] == "sc_b"
        assert scenes[1]["scene_id"] == "sc_a"

    def test_entity_and_alias(self):
        now = "2026-01-01T00:00:00"
        with self.engine.connect() as conn:
            conn.execute(
                insert(entities).values(
                    entity_id="e1", project_id=self.TEST_PROJECT, name="林远",
                    entity_type="character", importance_tier="protagonist",
                    summary="主角", core_drive="守护", surface_mask="冷静",
                    hidden_tension="内心矛盾", profile_json="{}",
                    created_at=now, updated_at=now,
                )
            )
            conn.execute(
                insert(entity_aliases).values(
                    project_id=self.TEST_PROJECT, alias="小远", entity_id="e1",
                )
            )
            conn.commit()

        result = self.entities.resolve_entity_id(self.TEST_PROJECT, "林远")
        assert result is not None

        result_alias = self.entities.resolve_entity_id(self.TEST_PROJECT, "小远")
        assert result_alias is not None
        assert result_alias == result  # same entity_id

    def test_preset_crud(self):
        self.presets.create_preset(
            self.TEST_PROJECT, "p1",
            name="测试预设", system_prompt="你是一名小说家。",
            description="测试用", is_default=0,
        )
        presets = self.presets.list_presets(self.TEST_PROJECT)
        assert len(presets) >= 1

        self.presets.update_preset(self.TEST_PROJECT, "p1", name="改名预设")
        presets = self.presets.list_presets(self.TEST_PROJECT)
        updated = next(p for p in presets if p["preset_id"] == "p1")
        assert updated["name"] == "改名预设"

        self.presets.delete_preset(self.TEST_PROJECT, "p1")
        presets = self.presets.list_presets(self.TEST_PROJECT)
        assert all(p["preset_id"] != "p1" for p in presets)


# ---------------------------------------------------------------------------
# Outline version history tests
# ---------------------------------------------------------------------------
class TestOutlineVersions:
    """Test outline version history via repos."""

    TEST_PROJECT = f"__test_{uuid.uuid4().hex[:8]}"

    @pytest.fixture(autouse=True)
    def setup_teardown(self, monkeypatch):
        self.engine = _make_engine(monkeypatch)
        self.chapters = ChapterRepository(self.engine)
        self.outlines = OutlineRepository(self.engine)
        self.chapters.create_chapter(self.TEST_PROJECT, "ch_1", 1, "第一章")
        yield

    def test_outline_versions_table_exists(self):
        from sqlalchemy import inspect
        inspector = inspect(self.engine)
        assert "outline_versions" in inspector.get_table_names()

    def test_save_outline_version(self):
        vid = self.outlines.save_outline_version(self.TEST_PROJECT, "ch_1", '[{"scene_order":1}]')
        assert vid.startswith("ov_")
        versions = self.outlines.list_outline_versions(self.TEST_PROJECT, "ch_1")
        assert len(versions) == 1
        assert versions[0]["version_id"] == vid
        assert "outline_json" not in versions[0]  # list should not include body

    def test_save_outline_version_with_label(self):
        vid = self.outlines.save_outline_version(self.TEST_PROJECT, "ch_1", '[{"scene_order":1}]', label="初版")
        versions = self.outlines.list_outline_versions(self.TEST_PROJECT, "ch_1")
        assert versions[0]["label"] == "初版"

    def test_get_outline_version(self):
        vid = self.outlines.save_outline_version(self.TEST_PROJECT, "ch_1", '[{"scene_order":1}]')
        version = self.outlines.get_outline_version(self.TEST_PROJECT, vid)
        assert version is not None
        assert version["outline_json"] == '[{"scene_order":1}]'

    def test_list_versions_ordered_desc(self):
        import time
        self.outlines.save_outline_version(self.TEST_PROJECT, "ch_1", '[]', label="v1")
        time.sleep(0.01)
        self.outlines.save_outline_version(self.TEST_PROJECT, "ch_1", '[{"scene_order":1}]', label="v2")
        versions = self.outlines.list_outline_versions(self.TEST_PROJECT, "ch_1")
        assert len(versions) == 2
        assert versions[0]["label"] == "v2"  # newest first
        assert versions[1]["label"] == "v1"

    def test_max_20_versions(self):
        for i in range(22):
            self.outlines.save_outline_version(self.TEST_PROJECT, "ch_1", f'[{{"n":{i}}}]')
        versions = self.outlines.list_outline_versions(self.TEST_PROJECT, "ch_1")
        assert len(versions) == 20

    def test_chapter_service_update_creates_version(self):
        from app.services.writer_agent.chapter_service import ChapterService
        svc = ChapterService()
        # Set initial outline
        self.chapters.update_chapter(self.TEST_PROJECT, "ch_1", outline_json='[{"scene_order":1}]')
        # Update via service -- should snapshot old value
        svc.update_chapter(self.TEST_PROJECT, "ch_1", outline_json='[{"scene_order":1},{"scene_order":2}]')
        versions = self.outlines.list_outline_versions(self.TEST_PROJECT, "ch_1")
        assert len(versions) == 1
        full = self.outlines.get_outline_version(self.TEST_PROJECT, versions[0]["version_id"])
        assert full["outline_json"] == '[{"scene_order":1}]'  # old value snapshotted

    def test_chapter_service_update_passes_label(self):
        from app.services.writer_agent.chapter_service import ChapterService
        svc = ChapterService()
        self.chapters.update_chapter(self.TEST_PROJECT, "ch_1", outline_json='[]')
        svc.update_chapter(self.TEST_PROJECT, "ch_1", outline_json='[{"x":1}]', outline_label="手动标注")
        versions = self.outlines.list_outline_versions(self.TEST_PROJECT, "ch_1")
        assert versions[0]["label"] == "手动标注"

    def test_chapter_service_update_no_version_without_outline(self):
        from app.services.writer_agent.chapter_service import ChapterService
        svc = ChapterService()
        svc.update_chapter(self.TEST_PROJECT, "ch_1", title="改标题")
        versions = self.outlines.list_outline_versions(self.TEST_PROJECT, "ch_1")
        assert len(versions) == 0  # no version created when outline not changed

    def test_chapter_service_restore(self):
        from app.services.writer_agent.chapter_service import ChapterService
        svc = ChapterService()
        self.chapters.update_chapter(self.TEST_PROJECT, "ch_1", outline_json='[{"v":"old"}]')
        vid = self.outlines.save_outline_version(self.TEST_PROJECT, "ch_1", '[{"v":"old"}]')
        self.chapters.update_chapter(self.TEST_PROJECT, "ch_1", outline_json='[{"v":"new"}]')
        svc.restore_outline_version(self.TEST_PROJECT, "ch_1", vid)
        ch = self.chapters.get_chapter_by_order(self.TEST_PROJECT, 1)
        assert ch["outline_json"] == '[{"v":"old"}]'
        # Current value before restore should be snapshotted
        versions = self.outlines.list_outline_versions(self.TEST_PROJECT, "ch_1")
        assert len(versions) == 2


# ---------------------------------------------------------------------------
# Tool definitions tests
# ---------------------------------------------------------------------------
class TestToolDefinitions:
    def test_all_tools_defined(self):
        from app.services.writer_agent.tools import NOVEL_TOOLS, TOOL_NAME_SET

        assert len(NOVEL_TOOLS) == 24
        expected_names = {
            "query_entity", "query_relationship", "query_chapter",
            "query_scene", "search_settings", "get_recent_scenes",
            "get_world_state", "get_open_threads",
            "get_character_voice", "query_character_timeline",
            "query_relationship_timeline", "query_thread_history",
            "search_world_rules",
            "list_worldline_branches", "get_branch_timeline",
            "get_branch_agent_state",
            "get_story_overview", "query_segment_summaries",
            "get_story_ontology",
            "manage_entity", "manage_thread",
            "manage_world_rule", "manage_relationship",
            "record_character_event",
        }
        assert TOOL_NAME_SET == expected_names

    def test_tool_schema_format(self):
        from app.services.writer_agent.tools import NOVEL_TOOLS

        for tool in NOVEL_TOOLS:
            assert tool["type"] == "function"
            func = tool["function"]
            assert "name" in func
            assert "description" in func
            assert "parameters" in func
            assert func["parameters"]["type"] == "object"


# ---------------------------------------------------------------------------
# Tool executors tests
# ---------------------------------------------------------------------------
class TestToolExecutors:
    TEST_PROJECT = f"__test_exec_{uuid.uuid4().hex[:8]}"

    @pytest.fixture(autouse=True)
    def setup_teardown(self, monkeypatch):
        self.engine = _make_engine(monkeypatch)
        chapters = ChapterRepository(self.engine)
        scenes = SceneRepository(self.engine)

        # Seed test data
        chapters.create_chapter(self.TEST_PROJECT, "ch_1", 1, "第一章")
        scenes.upsert_scene(
            self.TEST_PROJECT,
            {"scene_id": "sc_1", "chapter_id": "ch_1", "scene_order": 1,
             "title": "开场", "content": "林远站在山顶，望着远方。",
             "location": "山顶", "involved_entities_json": "[]", "status": "draft"},
        )
        now = "2026-01-01T00:00:00"
        with self.engine.connect() as conn:
            conn.execute(
                insert(entities).values(
                    entity_id="e1", project_id=self.TEST_PROJECT, name="林远",
                    entity_type="character", importance_tier="protagonist",
                    summary="主角剑修", core_drive="守护", surface_mask="冷静沉稳",
                    hidden_tension="外冷内热", profile_json='{"personality":"坚毅"}',
                    created_at=now, updated_at=now,
                )
            )
            conn.commit()
        yield

    def test_execute_query_entity(self):
        from app.services.writer_agent.tool_executors import execute_tool

        result = execute_tool("query_entity", {"name": "林远"}, self.TEST_PROJECT)
        assert "林远" in result
        assert "主角" in result or "protagonist" in result

    def test_execute_query_entity_not_found(self):
        from app.services.writer_agent.tool_executors import execute_tool

        result = execute_tool("query_entity", {"name": "不存在的角色"}, self.TEST_PROJECT)
        assert "未找到" in result

    def test_execute_query_chapter(self):
        from app.services.writer_agent.tool_executors import execute_tool

        result = execute_tool("query_chapter", {"chapter_order": 1}, self.TEST_PROJECT)
        assert "第一章" in result

    def test_execute_unknown_tool(self):
        from app.services.writer_agent.tool_executors import execute_tool

        result = execute_tool("nonexistent_tool", {}, self.TEST_PROJECT)
        assert "未知" in result or "Unknown" in result

    def test_result_truncation(self):
        from app.services.writer_agent.tool_executors import TOOL_RESULT_MAX_CHARS, execute_tool

        # This should not crash even with large data
        result = execute_tool("search_settings", {"query": "林远", "scope": "all"}, self.TEST_PROJECT)
        assert len(result) <= TOOL_RESULT_MAX_CHARS + 100  # small margin


# ---------------------------------------------------------------------------
# Agent loop tests (with mock LLM)
# ---------------------------------------------------------------------------
class MockToolCallFunction:
    def __init__(self, name, arguments):
        self.name = name
        self.arguments = json.dumps(arguments)


class MockToolCall:
    def __init__(self, name, arguments):
        self.id = f"call_{uuid.uuid4().hex[:8]}"
        self.function = MockToolCallFunction(name, arguments)


class MockMessage:
    def __init__(self, content=None, tool_calls=None):
        self.content = content
        self.tool_calls = tool_calls


class MockLLMClient:
    """Mock LLM client that returns predetermined responses (async-compatible)."""

    def __init__(self, responses):
        self.responses = list(responses)
        self.call_count = 0

    async def chat_with_tools(self, messages, tools, temperature=0.3, max_tokens=4096):
        if self.call_count >= len(self.responses):
            msg = MockMessage(content="No more responses", tool_calls=None)
            msg._usage = None
            return msg
        response = self.responses[self.call_count]
        self.call_count += 1
        response._usage = {"prompt_tokens": 100, "completion_tokens": 50, "total_tokens": 150}
        return response


class TestAgentLoop:
    TEST_PROJECT = f"__test_loop_{uuid.uuid4().hex[:8]}"

    @staticmethod
    async def _collect(async_gen):
        """Collect all items from an async generator into a list."""
        result = []
        async for item in async_gen:
            result.append(item)
        return result

    @pytest.fixture(autouse=True)
    def setup_teardown(self, monkeypatch):
        self.engine = _make_engine(monkeypatch)
        chapters = ChapterRepository(self.engine)
        chapters.create_chapter(self.TEST_PROJECT, "ch_1", 1, "第一章")

        now = "2026-01-01T00:00:00"
        with self.engine.connect() as conn:
            conn.execute(
                insert(entities).values(
                    entity_id="e1", project_id=self.TEST_PROJECT, name="林远",
                    entity_type="character", importance_tier="protagonist",
                    summary="主角", core_drive="守护", surface_mask="冷静",
                    hidden_tension="矛盾", profile_json="{}",
                    created_at=now, updated_at=now,
                )
            )
            conn.commit()
        yield

    def test_loop_with_tool_calls_then_brief(self):
        from app.services.writer_agent.agent_loop import AgentLoop
        from app.services.writer_agent.tools import NOVEL_TOOLS

        # Mock: first call returns a tool_use, second returns the brief
        mock_client = MockLLMClient([
            MockMessage(
                content=None,
                tool_calls=[MockToolCall("query_entity", {"name": "林远"})],
            ),
            MockMessage(
                content='{"task": "write_scene", "pov": {"name": "林远"}}',
                tool_calls=None,
            ),
        ])

        loop = AgentLoop(mock_client, NOVEL_TOOLS, "你是编排助手", self.TEST_PROJECT)
        events = asyncio.run(self._collect(loop.run("写第一章")))

        event_types = [e["type"] for e in events]
        assert "tool_call" in event_types
        assert "tool_result" in event_types
        assert "brief_ready" in event_types

        brief_event = next(e for e in events if e["type"] == "brief_ready")
        assert "write_scene" in brief_event["content"]

    def test_loop_no_tool_calls(self):
        from app.services.writer_agent.agent_loop import AgentLoop
        from app.services.writer_agent.tools import NOVEL_TOOLS

        mock_client = MockLLMClient([
            MockMessage(
                content='{"task": "outline", "scenes": []}',
                tool_calls=None,
            ),
        ])

        loop = AgentLoop(mock_client, NOVEL_TOOLS, "你是编排助手", self.TEST_PROJECT)
        events = asyncio.run(self._collect(loop.run("生成大纲")))

        assert len(events) == 2
        assert events[0]["type"] == "prompt_snapshot"
        assert events[1]["type"] == "brief_ready"

    def test_loop_max_rounds(self):
        from app.services.writer_agent.agent_loop import AgentLoop
        from app.services.writer_agent.tools import NOVEL_TOOLS

        # Mock: always returns tool calls, never stops
        infinite_responses = [
            MockMessage(
                content=None,
                tool_calls=[MockToolCall("query_entity", {"name": "林远"})],
            )
        ] * 20  # more than MAX_ROUNDS

        mock_client = MockLLMClient(infinite_responses)
        loop = AgentLoop(mock_client, NOVEL_TOOLS, "你是编排助手", self.TEST_PROJECT)

        events = asyncio.run(self._collect(loop.run("无限循环测试")))
        # Should eventually yield brief_ready (forced)
        assert any(e["type"] == "brief_ready" for e in events)
        # Should not exceed MAX_ROUNDS tool calls
        tool_calls = [e for e in events if e["type"] == "tool_call"]
        assert len(tool_calls) <= AgentLoop.MAX_ROUNDS

    def test_loop_events_include_round_and_usage(self):
        from app.services.writer_agent.agent_loop import AgentLoop
        from app.services.writer_agent.tools import NOVEL_TOOLS

        mock_client = MockLLMClient([
            MockMessage(
                content=None,
                tool_calls=[MockToolCall("query_entity", {"name": "林远"})],
            ),
            MockMessage(
                content='{"task": "write_scene"}',
                tool_calls=None,
            ),
        ])

        loop = AgentLoop(mock_client, NOVEL_TOOLS, "你是编排助手", self.TEST_PROJECT)
        events = asyncio.run(self._collect(loop.run("写第一章")))

        # tool_call and tool_result should carry round number
        tool_call_evt = next(e for e in events if e["type"] == "tool_call")
        assert tool_call_evt["round"] == 0

        tool_result_evt = next(e for e in events if e["type"] == "tool_result")
        assert tool_result_evt["round"] == 0
        assert "status" in tool_result_evt
        assert tool_result_evt["status"] == "ok"
        assert "tool_elapsed_ms" in tool_result_evt
        assert "full_result" in tool_result_evt

        # total_usage should be accumulated
        assert loop.total_usage["total_tokens"] > 0


# ---------------------------------------------------------------------------
# Module registry tests
# ---------------------------------------------------------------------------
class TestModuleRegistry:
    def test_writer_modules_registered(self):
        from app.services.llm_module_registry import MODULE_BY_KEY

        assert "writer_orchestrator" in MODULE_BY_KEY
        assert "writer_composer" in MODULE_BY_KEY

    def test_writer_module_labels(self):
        from app.services.llm_module_registry import MODULE_BY_KEY

        assert MODULE_BY_KEY["writer_orchestrator"].label == "写作编排调度"
        assert MODULE_BY_KEY["writer_composer"].label == "写作正文生成"


# ---------------------------------------------------------------------------
# Post-processor tests
# ---------------------------------------------------------------------------
class TestPostProcessor:
    TEST_PROJECT = f"__test_pp_{uuid.uuid4().hex[:8]}"

    @pytest.fixture(autouse=True)
    def setup_teardown(self, monkeypatch):
        self.engine = _make_engine(monkeypatch)
        self.chapters = ChapterRepository(self.engine)
        self.scenes = SceneRepository(self.engine)
        self.chapters.create_chapter(self.TEST_PROJECT, "ch_1", 1, "第一章")
        yield

    def test_process_saves_scene_and_compiles(self):
        from app.services.writer_agent.post_processor import PostProcessor

        pp = PostProcessor()
        result = pp.process(
            project_id=self.TEST_PROJECT,
            chapter_id="ch_1",
            scene_order=1,
            scene_id="sc_test",
            content="月光如水，洒落在竹林间。",
            writing_brief={"task": "write_scene"},
            title="竹林月色",
        )

        assert result["scene_id"] == "sc_test"
        assert result["word_count"] > 0

        # Verify scene was saved
        scene = self.scenes.get_scene(self.TEST_PROJECT, "sc_test")
        assert scene is not None
        assert "月光如水" in scene["content"]

        # Verify chapter was compiled
        ch = self.chapters.get_chapter(self.TEST_PROJECT, "ch_1", include_content=True)
        assert "月光如水" in ch["content"]
