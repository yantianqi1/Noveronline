"""Prompt 输入拼接器。"""

from __future__ import annotations

from typing import Dict

from .seed_stage_settings import MAX_PROMPT_INPUT_CHARS


class PromptBudgetManager:
    """保留稳定接口，但不再对 prompt 做本地裁剪。"""

    def __init__(self, max_input_chars: int = MAX_PROMPT_INPUT_CHARS):
        self.max_input_chars = max_input_chars

    def build_prompt(self, sections: Dict[str, str]) -> str:
        visible = [text for text in sections.values() if text]
        return "\n\n".join(visible)
