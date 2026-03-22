from app.services.prompt_budget_manager import (
    MAX_PROMPT_INPUT_CHARS,
    PromptBudgetManager,
    SECTION_PRIORITY,
)


def test_prompt_budget_manager_keeps_sections_when_under_budget():
    manager = PromptBudgetManager()
    sections = {
        "主块正文": "A" * 100,
        "骨架角色列表": "B" * 80,
        "锚点世界状态": "C" * 60,
    }

    prompt = manager.build_prompt(sections)

    assert "A" * 100 in prompt
    assert "B" * 80 in prompt
    assert "C" * 60 in prompt


def test_prompt_budget_manager_trims_low_priority_first_without_mutating_constants():
    manager = PromptBudgetManager(max_input_chars=200)
    original_priority = dict(SECTION_PRIORITY)
    sections = {
        "主块正文": "A" * 120,
        "骨架角色列表": "B" * 120,
        "锚点世界状态": "C" * 120,
        "上下文章节": "D" * 120,
        "章节指纹": "E" * 120,
    }

    prompt = manager.build_prompt(sections)

    assert len(prompt) <= MAX_PROMPT_INPUT_CHARS
    assert "A" * 120 in prompt
    assert SECTION_PRIORITY == original_priority
    assert "E" * 120 not in prompt
