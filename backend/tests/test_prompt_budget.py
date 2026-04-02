from app.services.prompt_budget_manager import PromptBudgetManager


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


def test_prompt_budget_manager_keeps_full_content_even_when_over_budget():
    manager = PromptBudgetManager(max_input_chars=200)
    sections = {
        "主块正文": "A" * 120,
        "骨架角色列表": "B" * 120,
        "锚点世界状态": "C" * 120,
        "上下文章节": "D" * 120,
        "章节指纹": "E" * 120,
    }

    prompt = manager.build_prompt(sections)

    assert "A" * 120 in prompt
    assert "B" * 120 in prompt
    assert "C" * 120 in prompt
    assert "D" * 120 in prompt
    assert "E" * 120 in prompt
