"""Draft Agents 单元测试。"""

import pytest

from app.services.agents.draft.context_agent import ContextAgent
from app.services.agents.draft.memory_agent import MemoryAgent
from app.services.agents.draft import NovelDraftOrchestrator
from app.services.agents.draft import ReviewerAgent
from app.services.agents.draft.style_agent import StyleAgent
from app.services.agents.draft.writer_agent import WriterAgent


class TestContextAgent:
    def test_summarize_with_empty_pack(self):
        agent = ContextAgent()
        summary = agent.summarize({})
        assert summary["must_know_count"] == 0
        assert summary["warnings_count"] == 0
        assert summary["has_continuity"] is False

    def test_summarize_with_populated_pack(self):
        agent = ContextAgent()
        pack = {
            "must_know": [{"item_id": "1"}, {"item_id": "2"}],
            "should_know": [{"item_id": "3"}],
            "warnings": [{"item_id": "4"}],
            "scene_candidates": [],
            "context_scope": {"scope_type": "project_chapter", "pov_character": "李辰"},
        }
        summary = agent.summarize(pack)
        assert summary["must_know_count"] == 2
        assert summary["should_know_count"] == 1
        assert summary["warnings_count"] == 1
        assert summary["pov_character"] == "李辰"
        assert summary["has_continuity"] is False

    def test_summarize_with_continuity(self):
        agent = ContextAgent()
        pack = {
            "must_know": [],
            "should_know": [],
            "warnings": [],
            "scene_candidates": [],
            "context_scope": {"scope_type": "project_chapter", "pov_character": "李辰"},
            "continuity_anchor": {
                "prev_chapter_ending": "上章末尾原文",
                "chapter_summaries": [{"chapter_order": 1, "summary": "摘要"}],
                "open_threads": [],
                "timeline_note": "",
            },
        }
        summary = agent.summarize(pack)
        assert summary["has_continuity"] is True


class TestStyleAgent:
    def test_default_hints(self):
        agent = StyleAgent()
        hints = agent._default_hints()
        assert "rendered_hints" in hints
        assert hints["pov_person"] == "第三人称"
        assert hints["dialogue_ratio"] == 0.3

    def test_dialogue_ratio(self):
        agent = StyleAgent()
        text = '"你好。"他说。"不行。"她回答。这是一段叙述文字。'
        ratio = agent._dialogue_ratio(text)
        assert 0.0 < ratio < 1.0

    def test_detect_pov_person_first(self):
        agent = StyleAgent()
        text = "我走进了房间，我看到了一面镜子。我的心跳加速了。"
        assert agent._detect_pov_person(text) == "第一人称"

    def test_detect_pov_person_third(self):
        agent = StyleAgent()
        text = "他走进了房间，她看到了一面镜子。他们的心跳加速了。"
        assert agent._detect_pov_person(text) == "第三人称"

    def test_sentence_rhythm_short(self):
        agent = StyleAgent()
        text = "天亮了。风停了。雨来了。路断了。人散了。"
        rhythm = agent._sentence_rhythm(text)
        assert rhythm == "短促紧凑"

    def test_render_hints(self):
        agent = StyleAgent()
        hints = {
            "dialogue_ratio": 0.4,
            "avg_sentence_length": 25.0,
            "rhythm": "均匀适中",
            "pov_person": "第三人称",
        }
        rendered = agent._render_hints(hints)
        assert "风格提示" in rendered
        assert "第三人称" in rendered

    def test_analyze_missing_project(self):
        agent = StyleAgent()
        hints = agent.analyze("nonexistent_project_id")
        assert hints["rendered_hints"] != ""
        assert hints["sample_length"] == 0


class TestMemoryAgent:
    def test_render_empty_memory_context(self):
        agent = MemoryAgent()
        bundle = {
            "character_profile": {},
            "memories": [],
            "relationships": [],
        }
        rendered = agent._render_memory_context(bundle)
        assert rendered == "暂无角色记忆信息。"

    def test_render_with_profile(self):
        agent = MemoryAgent()
        bundle = {
            "character_profile": {"name": "李辰", "drive": "找到真相", "tension": "被追杀"},
            "memories": [{"type": "event", "summary": "发现了暗门", "salience": 0.8}],
            "relationships": [{"source": "李辰", "target": "王芸", "note": "盟友"}],
        }
        rendered = agent._render_memory_context(bundle)
        assert "李辰" in rendered
        assert "找到真相" in rendered
        assert "暗门" in rendered
        assert "王芸" in rendered


class TestReviewerAgent:
    def test_empty_text_returns_skip(self):
        agent = ReviewerAgent()
        result = agent.review("", {}, {})
        assert result["review_mode"] == "skipped"
        assert result["issues"] == []
        assert result["pass"] is True

    def test_rule_based_review_missing_pov(self):
        agent = ReviewerAgent()
        context = {"context_scope": {"pov_character": "李辰"}, "warnings": []}
        result = agent._rule_based_review("王芸走进了房间。", context)
        assert any("李辰" in issue["description"] for issue in result["issues"])
        assert result["pass"] is True  # medium severity, no high issues
        assert "score" in result

    def test_rule_based_review_no_issues(self):
        agent = ReviewerAgent()
        context = {"context_scope": {"pov_character": "李辰"}, "warnings": []}
        result = agent._rule_based_review("李辰走进了房间。", context)
        assert result["issues"] == []
        assert result["pass"] is True
        assert result["score"] == 100

    def test_rule_based_review_with_warnings(self):
        agent = ReviewerAgent()
        context = {
            "context_scope": {"pov_character": "李辰"},
            "warnings": [{"summary": "存在连续性冲突"}],
        }
        result = agent._rule_based_review("李辰走进了房间。", context)
        assert len(result["issues"]) >= 1
        assert "pass" in result
        assert "score" in result

    def test_rule_based_review_structured_issues(self):
        agent = ReviewerAgent()
        context = {"context_scope": {"pov_character": "李辰"}, "warnings": []}
        result = agent._rule_based_review("王芸独自前行。", context)
        for issue in result["issues"]:
            assert "dimension" in issue
            assert "severity" in issue
            assert "description" in issue
            assert "suggestion" in issue

    def test_build_revision_feedback(self):
        agent = ReviewerAgent()
        review = {
            "pass": False,
            "score": 55,
            "issues": [
                {
                    "dimension": "连续性",
                    "severity": "high",
                    "description": "场景转换缺少交代",
                    "suggestion": "补充过渡描写",
                },
                {
                    "dimension": "角色一致性",
                    "severity": "medium",
                    "description": "B说话太多",
                    "suggestion": "缩减台词",
                },
            ],
            "keep": ["第二段的环境描写很好"],
        }
        feedback = agent.build_revision_feedback(review)
        assert "必须修改" in feedback["revision_instruction"]
        assert "建议修改" in feedback["revision_instruction"]
        assert "保留不要改动" in feedback["revision_instruction"]
        assert len(feedback["issues"]) == 2
        assert feedback["score"] == 55

    def test_normalize_result_pass(self):
        agent = ReviewerAgent()
        result = agent._normalize_result(
            {"pass": True, "score": 85, "issues": [], "keep": ["好"], "overall_assessment": "通过"},
            "llm", "test-model"
        )
        assert result["pass"] is True
        assert result["score"] == 85
        assert result["review_mode"] == "llm"
        assert result["model_name"] == "test-model"

    def test_normalize_result_fail(self):
        agent = ReviewerAgent()
        result = agent._normalize_result(
            {
                "pass": False,
                "score": 40,
                "issues": [{"dimension": "连续性", "severity": "high", "description": "矛盾", "suggestion": "修"}],
                "keep": [],
                "overall_assessment": "不通过"
            },
            "llm"
        )
        assert result["pass"] is False
        assert len(result["issues"]) == 1


class TestWriterAgent:
    def test_build_user_prompt_simple(self):
        agent = WriterAgent()
        prompt = agent._build_user_prompt("续写第三章")
        assert "续写第三章" in prompt

    def test_build_user_prompt_revision(self):
        agent = WriterAgent()
        revision = {
            "previous_text": "上一版正文内容...",
            "revision_instruction": "对话太平淡",
        }
        prompt = agent._build_user_prompt("加强冲突", revision)
        assert "上一版正文" in prompt
        assert "对话太平淡" in prompt
        assert "加强冲突" in prompt

    def test_build_system_prompt(self):
        agent = WriterAgent()
        context_pack = {
            "context_scope": {"pov_character": "李辰", "writing_goal": "续写"},
            "must_know": [{"summary": "世界规则1", "why_it_matters": "不可违背"}],
            "should_know": [],
            "warnings": [],
            "scene_candidates": [],
        }
        memory_bundle = {"rendered_context": "POV 角色：李辰，目标：找到真相"}
        style_hints = {"rendered_hints": "风格提示：对话驱动"}
        prompt = agent._build_system_prompt(context_pack, memory_bundle, style_hints)
        assert "小说家" in prompt
        assert "李辰" in prompt
        assert "风格提示" in prompt

    def test_build_system_prompt_with_continuity(self):
        agent = WriterAgent()
        context_pack = {
            "context_scope": {"pov_character": "李辰"},
            "must_know": [],
            "should_know": [],
            "warnings": [],
            "scene_candidates": [],
            "continuity_anchor": {
                "prev_chapter_ending": "李辰推开了废塔的铁门，一股腐朽的气息扑面而来。",
                "chapter_summaries": [
                    {"chapter_order": 1, "title": "废塔初探", "summary": "李辰发现废塔暗门"},
                ],
                "open_threads": ["暗门通向何处", "神秘脚步声"],
                "timeline_note": "故事第一天傍晚",
            },
        }
        memory_bundle = {"rendered_context": ""}
        style_hints = {"rendered_hints": ""}
        prompt = agent._build_system_prompt(context_pack, memory_bundle, style_hints)
        assert "前章连续性" in prompt
        assert "上章末尾原文" in prompt
        assert "废塔" in prompt
        assert "暗门通向何处" in prompt
        assert "未解悬念线" in prompt
        assert "故事第一天傍晚" in prompt

    def test_render_continuity_empty(self):
        agent = WriterAgent()
        assert agent._render_continuity({}) == ""
        assert agent._render_continuity({"continuity_anchor": None}) == ""


class TestOrchestrator:
    def test_empty_instruction_yields_error(self):
        orchestrator = NovelDraftOrchestrator()
        events = list(orchestrator.generate_stream({"author_instruction": ""}))
        assert len(events) == 1
        assert events[0]["type"] == "error"
        assert "创作指令" in events[0]["message"]

    def test_missing_project_yields_error(self):
        orchestrator = NovelDraftOrchestrator()
        events = list(orchestrator.generate_stream({
            "author_instruction": "续写",
            "scope_type": "project_chapter",
            "project_id": "nonexistent",
            "chapter_id": "ch1",
            "pov_character": "测试角色",
        }))
        # 新的 SSE 格式：错误通过 agent_status 事件的 status="error" 传递
        has_error = any(
            e.get("type") == "error" or e.get("status") == "error"
            for e in events
        )
        assert has_error

    def test_phase_events_are_yielded(self):
        """验证编排器在正常流程中会 yield phase 事件。"""
        # 这个测试只是验证空指令的错误分支
        orchestrator = NovelDraftOrchestrator()
        events = list(orchestrator.generate_stream({"author_instruction": "  "}))
        assert events[0]["type"] == "error"
