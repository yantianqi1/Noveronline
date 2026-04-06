"""Tests for the modularized draft prompt system."""

import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from app.services.agents.draft.prompts import assemble_writer_prompt, assemble_reviewer_prompt
from app.services.agents.draft.prompts.base import WRITER_BASE_PROMPT
from app.services.agents.draft.prompts.prose_quality import PROSE_QUALITY_RULES
from app.services.agents.draft.prompts.anti_cliche import ANTI_CLICHE_RULES
from app.services.agents.draft.prompts.dialogue import DIALOGUE_RULES
from app.services.agents.draft.prompts.pacing import PACING_RULES
from app.services.agents.draft.prompts.reviewer import REVIEWER_PROMPT


class TestBasePrompt:
    def test_base_prompt_is_nonempty_string(self):
        assert isinstance(WRITER_BASE_PROMPT, str)
        assert len(WRITER_BASE_PROMPT) > 100

    def test_base_prompt_contains_role(self):
        assert "资深小说家" in WRITER_BASE_PROMPT

    def test_assemble_includes_base(self):
        full = assemble_writer_prompt()
        assert "资深小说家" in full


class TestProseQualityRules:
    def test_contains_sensory_rules(self):
        assert "禁止人声描写" in PROSE_QUALITY_RULES
        assert "禁止解读眼神" in PROSE_QUALITY_RULES
        assert "禁止状态介词外挂" in PROSE_QUALITY_RULES

    def test_contains_environment_rules(self):
        assert "环境参与叙事" in PROSE_QUALITY_RULES

    def test_assembled_prompt_includes_prose_quality(self):
        full = assemble_writer_prompt()
        assert "白描准则" in full
        assert "感官描写规范" in full


class TestAntiClicheRules:
    def test_contains_banned_words_section(self):
        assert "程度副词" in ANTI_CLICHE_RULES
        assert "极其" in ANTI_CLICHE_RULES

    def test_contains_oily_words_section(self):
        assert "禁油腻词汇" in ANTI_CLICHE_RULES
        assert "邪魅" in ANTI_CLICHE_RULES

    def test_contains_anatomy_ban(self):
        assert "解剖学标签" in ANTI_CLICHE_RULES

    def test_assembled_includes_anti_cliche(self):
        full = assemble_writer_prompt()
        assert "反八股死令" in full


class TestDialogueRules:
    def test_contains_voice_ban(self):
        assert "禁止语气描述" in DIALOGUE_RULES

    def test_contains_echo_ban(self):
        assert "反回声复述" in DIALOGUE_RULES

    def test_assembled_includes_dialogue(self):
        full = assemble_writer_prompt()
        assert "对白准则" in full


class TestPacingRules:
    def test_contains_scene_closure(self):
        assert "场景收束" in PACING_RULES
        assert "反完结感" in PACING_RULES

    def test_contains_anti_summary(self):
        assert "反总结升华" in PACING_RULES

    def test_assembled_includes_all_modules(self):
        full = assemble_writer_prompt()
        assert "资深小说家" in full
        assert "白描准则" in full
        assert "反八股死令" in full
        assert "对白准则" in full
        assert "场景收束" in full


class TestReviewerPrompt:
    def test_contains_six_dimensions(self):
        assert "连续性" in REVIEWER_PROMPT
        assert "角色一致性" in REVIEWER_PROMPT
        assert "悬念与伏笔" in REVIEWER_PROMPT
        assert "风格一致性" in REVIEWER_PROMPT
        assert "描写质量" in REVIEWER_PROMPT
        assert "叙事节奏" in REVIEWER_PROMPT

    def test_contains_death_order_markers(self):
        assert "死令级" in REVIEWER_PROMPT
        assert "severity: high" in REVIEWER_PROMPT

    def test_assemble_reviewer(self):
        result = assemble_reviewer_prompt()
        assert result == REVIEWER_PROMPT
        assert len(result) > 500
