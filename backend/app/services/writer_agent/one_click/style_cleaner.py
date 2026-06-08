"""🎨 一键风格清理 — emit ProseDiff rewrite cards for anti-AI-flavor (style) hits.

仿 lexicon_cleaner：MAX_ROUNDS=6，只读 + ``propose_rewrite_span``（非破坏，出提案卡，
用户在前端采纳）。没有确定性扫描器——由 LLM 对照 STYLE_AUDIT_CHECKLIST 判断 high 级
AI 味/套路问题。来源：小说梦想家 SOUL v3.4 / PITFALLS。
"""

from __future__ import annotations

from ..prompts import STYLE_AUDIT_CHECKLIST
from .base import OneClickRunner

_SYSTEM_PROMPT = (
    "你是小说写作 agent 的「风格清理提案员」。当前章节正文可能存在 AI 味/套路化问题，"
    "你的任务：对照死令清单找出 high 级问题，为每处生成 ProseDiffViewCard 改写提案（绝不直接改库）。\n"
    "\n"
    "强制规则：\n"
    "1. 先调 get_chapter_word_stats(chapter_id=...) 拿到所有 block_id + 预览；"
    "再用 get_manuscript_context / search_manuscript / query_scene 读出可疑块的完整正文。\n"
    "2. 对照下方死令清单逐句判断；若无 high 级问题，输出 {\"verdict\": \"clean\"} 并终止。\n"
    "3. 对每个 high 级问题：调 propose_rewrite_span(block_id, original_text=<含问题的块内唯一片段>, "
    "new_text=<改写>, reason=<命中的死令>)。new_text 必须保留原意、POV 口吻、情节，字数差 ±15%。\n"
    "4. 单 block 同一问题仅出一张卡；总卡数 ≤ 20。严禁调用真 rewrite_span。\n"
    "\n"
    "## 反 AI 味死令清单（命中即 high）\n"
    + STYLE_AUDIT_CHECKLIST
)


_TOOL_WHITELIST = [
    "get_chapter_word_stats",
    "get_manuscript_context",
    "search_manuscript",
    "query_scene",
    "propose_rewrite_span",
]


class StyleCleanerRunner(OneClickRunner):
    name = "style_cleaner"
    max_rounds = 6

    def build_system_prompt(self, context: dict) -> str:
        return _SYSTEM_PROMPT

    def build_user_message(self, context: dict) -> str:
        chapter_id = context.get("chapter_id") or ""
        chapter_order = context.get("chapter_order") or 0
        return (
            f"请对第 {chapter_order} 章（chapter_id={chapter_id}）做风格清理（反 AI 味）。"
            f"先调 get_chapter_word_stats(chapter_id={chapter_id}) 拿块清单，"
            "读出可疑块正文，再对照死令清单逐处生成 propose_rewrite_span 提案卡。"
        )

    def tool_names(self) -> list[str]:
        return list(_TOOL_WHITELIST)
