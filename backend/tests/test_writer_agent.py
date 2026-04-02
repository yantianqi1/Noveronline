"""Tests for the writer agent system: NovelDB, tools, agent loop, orchestrator."""

import json
import os
import sqlite3
import uuid

import pytest

# ---------------------------------------------------------------------------
# Ensure backend is on sys.path
# ---------------------------------------------------------------------------
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))


# ---------------------------------------------------------------------------
# NovelDB tests
# ---------------------------------------------------------------------------
class TestNovelDB:
    """Test the unified data access layer."""

    TEST_PROJECT = f"__test_{uuid.uuid4().hex[:8]}"

    @pytest.fixture(autouse=True)
    def setup_teardown(self):
        from app.services.writer_agent.novel_db import NovelDB

        self.db = NovelDB()
        self.db.ensure_schema(self.TEST_PROJECT)
        yield
        db_path = self.db._db_path(self.TEST_PROJECT)
        if os.path.exists(db_path):
            os.remove(db_path)

    def test_schema_creates_tables(self):
        with self.db.connect(self.TEST_PROJECT) as conn:
            tables = {
                row[0]
                for row in conn.execute(
                    "SELECT name FROM sqlite_master WHERE type='table'"
                ).fetchall()
            }
        expected = {
            "entities", "entity_aliases", "entity_labels",
            "relationships", "entity_evidence",
            "chapter_content", "chapter_meta", "scenes",
            "sessions", "agent_states", "agent_memory", "world_events",
            "writer_presets",
        }
        assert expected.issubset(tables), f"Missing tables: {expected - tables}"

    def test_chapter_crud(self):
        self.db.create_chapter(self.TEST_PROJECT, "ch_1", 1, "第一章")
        chapters = self.db.list_chapters(self.TEST_PROJECT)
        assert len(chapters) == 1
        assert chapters[0]["title"] == "第一章"

        self.db.update_chapter(self.TEST_PROJECT, "ch_1", title="第一章·改")
        ch = self.db.get_chapter(self.TEST_PROJECT, 1)
        assert ch["title"] == "第一章·改"

        self.db.delete_chapter(self.TEST_PROJECT, "ch_1")
        assert len(self.db.list_chapters(self.TEST_PROJECT)) == 0

    def test_scene_crud_and_compile(self):
        self.db.create_chapter(self.TEST_PROJECT, "ch_1", 1, "第一章")

        self.db.upsert_scene(
            self.TEST_PROJECT, "sc_1", "ch_1", 1,
            "场景一", "月光穿过竹叶。", None, "竹林", "[]", "draft", None,
        )
        self.db.upsert_scene(
            self.TEST_PROJECT, "sc_2", "ch_1", 2,
            "场景二", "剑气纵横。", None, "演武场", "[]", "draft", None,
        )

        scenes = self.db.list_scenes(self.TEST_PROJECT, "ch_1")
        assert len(scenes) == 2
        assert scenes[0]["scene_order"] == 1

        scene = self.db.get_scene(self.TEST_PROJECT, "sc_1")
        assert scene["content"] == "月光穿过竹叶。"
        assert scene["word_count"] > 0

        self.db.compile_chapter(self.TEST_PROJECT, "ch_1")
        ch = self.db.get_chapter(self.TEST_PROJECT, 1, include_content=True)
        assert "月光穿过竹叶" in ch["content"]
        assert "剑气纵横" in ch["content"]

    def test_scene_reorder(self):
        self.db.create_chapter(self.TEST_PROJECT, "ch_1", 1, "第一章")
        self.db.upsert_scene(self.TEST_PROJECT, "sc_a", "ch_1", 1, "A", "内容A", None, None, "[]", "draft", None)
        self.db.upsert_scene(self.TEST_PROJECT, "sc_b", "ch_1", 2, "B", "内容B", None, None, "[]", "draft", None)

        self.db.reorder_scenes(self.TEST_PROJECT, "ch_1", ["sc_b", "sc_a"])
        scenes = self.db.list_scenes(self.TEST_PROJECT, "ch_1")
        assert scenes[0]["scene_id"] == "sc_b"
        assert scenes[1]["scene_id"] == "sc_a"

    def test_entity_and_alias(self):
        with self.db.connect(self.TEST_PROJECT) as conn:
            now = "2026-01-01T00:00:00"
            conn.execute(
                "INSERT INTO entities VALUES (?,?,?,?,?,?,?,?,?,?,?,?)",
                ("e1", self.TEST_PROJECT, "林远", "character", "protagonist",
                 "主角", "守护", "冷静", "内心矛盾", "{}", now, now),
            )
            conn.execute(
                "INSERT INTO entity_aliases VALUES (?,?)",
                ("小远", "e1"),
            )
            conn.commit()

        result = self.db.get_entity(self.TEST_PROJECT, "林远")
        assert result is not None
        assert result["entity_type"] == "character"

        result_alias = self.db.get_entity(self.TEST_PROJECT, "小远")
        assert result_alias is not None
        assert result_alias["name"] == "林远"

    def test_fts_search(self):
        self.db.create_chapter(self.TEST_PROJECT, "ch_1", 1, "竹林密谈")
        self.db.upsert_scene(
            self.TEST_PROJECT, "sc_1", "ch_1", 1,
            "密谈", "林远在竹林中与谢无尘密谈。", None, None, "[]", "draft", None,
        )

        # unicode61 tokenizer treats CJK titles as matchable tokens
        results = self.db.search_fts(self.TEST_PROJECT, "密谈", "all", 10)
        assert len(results) > 0

    def test_preset_crud(self):
        self.db.create_preset(
            self.TEST_PROJECT, "p1", "测试预设",
            "你是一名小说家。", "测试用", 0,
        )
        presets = self.db.list_presets(self.TEST_PROJECT)
        assert len(presets) >= 1

        self.db.update_preset(self.TEST_PROJECT, "p1", name="改名预设")
        presets = self.db.list_presets(self.TEST_PROJECT)
        updated = next(p for p in presets if p["preset_id"] == "p1")
        assert updated["name"] == "改名预设"

        self.db.delete_preset(self.TEST_PROJECT, "p1")
        presets = self.db.list_presets(self.TEST_PROJECT)
        assert all(p["preset_id"] != "p1" for p in presets)

    def test_open_threads(self):
        self.db.create_chapter(self.TEST_PROJECT, "ch_1", 1, "第一章")
        self.db.update_chapter(
            self.TEST_PROJECT, "ch_1",
            open_threads_json='["谁是幕后黑手？", "宝剑的来历"]',
        )
        self.db.create_chapter(self.TEST_PROJECT, "ch_2", 2, "第二章")
        self.db.update_chapter(
            self.TEST_PROJECT, "ch_2",
            open_threads_json='["密室的秘密"]',
        )

        threads = self.db.get_open_threads(self.TEST_PROJECT, 2)
        assert len(threads) == 3
        assert "谁是幕后黑手？" in threads


# ---------------------------------------------------------------------------
# Tool definitions tests
# ---------------------------------------------------------------------------
class TestToolDefinitions:
    def test_all_tools_defined(self):
        from app.services.writer_agent.tools import NOVEL_TOOLS, TOOL_NAME_SET

        assert len(NOVEL_TOOLS) == 8
        expected_names = {
            "query_entity", "query_relationship", "query_chapter",
            "query_scene", "search_settings", "get_recent_scenes",
            "get_world_state", "get_open_threads",
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
    def setup_teardown(self):
        from app.services.writer_agent.novel_db import NovelDB

        self.db = NovelDB()
        self.db.ensure_schema(self.TEST_PROJECT)

        # Seed test data
        self.db.create_chapter(self.TEST_PROJECT, "ch_1", 1, "第一章")
        self.db.upsert_scene(
            self.TEST_PROJECT, "sc_1", "ch_1", 1,
            "开场", "林远站在山顶，望着远方。", None, "山顶", "[]", "draft", None,
        )
        with self.db.connect(self.TEST_PROJECT) as conn:
            now = "2026-01-01T00:00:00"
            conn.execute(
                "INSERT INTO entities VALUES (?,?,?,?,?,?,?,?,?,?,?,?)",
                ("e1", self.TEST_PROJECT, "林远", "character", "protagonist",
                 "主角剑修", "守护", "冷静沉稳", "外冷内热", '{"personality":"坚毅"}', now, now),
            )
            conn.commit()
        yield

        db_path = self.db._db_path(self.TEST_PROJECT)
        if os.path.exists(db_path):
            os.remove(db_path)

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
    """Mock LLM client that returns predetermined responses."""

    def __init__(self, responses):
        self.responses = list(responses)
        self.call_count = 0

    def chat_with_tools(self, messages, tools, temperature=0.3, max_tokens=4096):
        if self.call_count >= len(self.responses):
            return MockMessage(content="No more responses", tool_calls=None)
        response = self.responses[self.call_count]
        self.call_count += 1
        return response


class TestAgentLoop:
    TEST_PROJECT = f"__test_loop_{uuid.uuid4().hex[:8]}"

    @pytest.fixture(autouse=True)
    def setup_teardown(self):
        from app.services.writer_agent.novel_db import NovelDB

        self.db = NovelDB()
        self.db.ensure_schema(self.TEST_PROJECT)

        # Seed minimal data
        self.db.create_chapter(self.TEST_PROJECT, "ch_1", 1, "第一章")
        with self.db.connect(self.TEST_PROJECT) as conn:
            now = "2026-01-01T00:00:00"
            conn.execute(
                "INSERT INTO entities VALUES (?,?,?,?,?,?,?,?,?,?,?,?)",
                ("e1", self.TEST_PROJECT, "林远", "character", "protagonist",
                 "主角", "守护", "冷静", "矛盾", "{}", now, now),
            )
            conn.commit()
        yield

        db_path = self.db._db_path(self.TEST_PROJECT)
        if os.path.exists(db_path):
            os.remove(db_path)

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
        events = list(loop.run("写第一章"))

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
        events = list(loop.run("生成大纲"))

        assert len(events) == 1
        assert events[0]["type"] == "brief_ready"

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

        events = list(loop.run("无限循环测试"))
        # Should eventually yield brief_ready (forced)
        assert any(e["type"] == "brief_ready" for e in events)
        # Should not exceed MAX_ROUNDS tool calls
        tool_calls = [e for e in events if e["type"] == "tool_call"]
        assert len(tool_calls) <= AgentLoop.MAX_ROUNDS


# ---------------------------------------------------------------------------
# Module registry tests
# ---------------------------------------------------------------------------
class TestModuleRegistry:
    def test_writer_modules_registered(self):
        from app.services.llm_module_registry import MODULE_BY_KEY

        assert "writer_orchestrator" in MODULE_BY_KEY
        assert "writer_composer" in MODULE_BY_KEY
        assert "writer_reviewer" in MODULE_BY_KEY

    def test_writer_module_labels(self):
        from app.services.llm_module_registry import MODULE_BY_KEY

        assert MODULE_BY_KEY["writer_orchestrator"].label == "写作编排调度"
        assert MODULE_BY_KEY["writer_composer"].label == "写作正文生成"
        assert MODULE_BY_KEY["writer_reviewer"].label == "写作一致性审校"


# ---------------------------------------------------------------------------
# Post-processor tests
# ---------------------------------------------------------------------------
class TestPostProcessor:
    TEST_PROJECT = f"__test_pp_{uuid.uuid4().hex[:8]}"

    @pytest.fixture(autouse=True)
    def setup_teardown(self):
        from app.services.writer_agent.novel_db import NovelDB

        self.db = NovelDB()
        self.db.ensure_schema(self.TEST_PROJECT)
        self.db.create_chapter(self.TEST_PROJECT, "ch_1", 1, "第一章")
        yield

        db_path = self.db._db_path(self.TEST_PROJECT)
        if os.path.exists(db_path):
            os.remove(db_path)

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
        scene = self.db.get_scene(self.TEST_PROJECT, "sc_test")
        assert scene is not None
        assert "月光如水" in scene["content"]

        # Verify chapter was compiled
        ch = self.db.get_chapter(self.TEST_PROJECT, 1, include_content=True)
        assert "月光如水" in ch["content"]
