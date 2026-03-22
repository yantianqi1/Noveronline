"""Prompt 输入预算管理。"""

from __future__ import annotations

from typing import Dict

from .seed_stage_settings import MAX_PROMPT_INPUT_CHARS


SECTION_PRIORITY = {
    "主块正文": 1,
    "骨架角色列表": 2,
    "前情快照": 2,
    "锚点世界状态": 3,
    "块内事实": 3,
    "上下文章节": 4,
    "章节指纹": 5,
}

SECTION_CHAR_LIMITS = {
    "主块正文": 12000,
    "骨架角色列表": 1500,
    "前情快照": 4000,
    "锚点世界状态": 3000,
    "块内事实": 3000,
    "上下文章节": 4000,
    "章节指纹": 1500,
}

TRUNCATE_NOTICE = "\n[已截断]"


class PromptBudgetManager:
    """按段落优先级裁剪 prompt，避免输入无限膨胀。"""

    def __init__(self, max_input_chars: int = MAX_PROMPT_INPUT_CHARS):
        self.max_input_chars = max_input_chars

    def build_prompt(self, sections: Dict[str, str]) -> str:
        trimmed = {name: text for name, text in sections.items() if text}
        if self._total_chars(trimmed) <= self.max_input_chars:
            return self._assemble(trimmed)
        priorities = dict(SECTION_PRIORITY)
        limits = dict(SECTION_CHAR_LIMITS)
        for name in self._trim_order(trimmed, priorities):
            trimmed[name] = self._trim_text(trimmed[name], limits.get(name, 2000))
            if self._total_chars(trimmed) <= self.max_input_chars:
                return self._assemble(trimmed)
        return self._assemble(self._drop_low_priority_sections(trimmed, priorities))

    def _trim_order(self, sections: Dict[str, str], priorities: Dict[str, int]) -> list[str]:
        return sorted(sections, key=lambda name: priorities.get(name, 99), reverse=True)

    def _trim_text(self, text: str, limit: int) -> str:
        if len(text) <= limit:
            return text
        return text[:limit] + TRUNCATE_NOTICE

    def _drop_low_priority_sections(
        self,
        sections: Dict[str, str],
        priorities: Dict[str, int],
    ) -> Dict[str, str]:
        trimmed = dict(sections)
        while self._total_chars(trimmed) > self.max_input_chars:
            removable = self._lowest_priority_name(trimmed, priorities)
            if not removable:
                break
            del trimmed[removable]
        return trimmed

    def _lowest_priority_name(self, sections: Dict[str, str], priorities: Dict[str, int]) -> str:
        candidates = [name for name in sections if name != "主块正文"]
        if not candidates:
            return ""
        return max(candidates, key=lambda name: priorities.get(name, 99))

    def _assemble(self, sections: Dict[str, str]) -> str:
        return "\n\n".join(sections.values())

    def _total_chars(self, sections: Dict[str, str]) -> int:
        return sum(len(text) for text in sections.values())
