"""📐 一键对齐字数 — emit ProseDiff cards to expand/shrink a chapter.

§4.4.3: MAX_ROUNDS=6, whitelist is read tools + ``propose_splice_block``.
"""

from __future__ import annotations

from .base import OneClickRunner

_SYSTEM_PROMPT = """你是小说写作 agent 的「字数对齐提案员」。当前章节字数偏离目标，你的任务：扫描所有
block，识别最适合扩写或精简的位置，为每个候选生成 ProseDiffViewCard 提案。

强制规则：
1. 先调 get_chapter_word_stats 拿每 block 字数 + diff。
2. 若 |diff| 已在容忍区间内，输出 {"verdict":"pass"} 并终止。
3. diff < 0（不足）：在情绪铺陈/内心独白薄弱的块上调 propose_splice_block(position='after', intent='expand')
   产出扩写提案；每张卡补齐不超过 |diff| 的 40%。
4. diff > 0（超出）：在冗余修辞密集的块上调 propose_splice_block(position='replace_range', intent='shrink')
   产出精简提案；每张卡精简不超过 |diff| 的 40%。
5. 总卡数 ≤ 5。严禁调用真 splice_block / rewrite_span。
6. 每张卡必须有 reason、new_content（给出具体正文）。
"""


_TOOL_WHITELIST = [
    "get_chapter_word_stats",
    "query_scene",
    "search_manuscript",
    "get_manuscript_context",
    "propose_splice_block",
]


class WordAlignerRunner(OneClickRunner):
    name = "word_aligner"
    max_rounds = 6

    def build_system_prompt(self, context: dict) -> str:
        return _SYSTEM_PROMPT

    def build_user_message(self, context: dict) -> str:
        chapter_id = context.get("chapter_id") or ""
        chapter_order = context.get("chapter_order") or 0
        target = context.get("target_word_count") or 0
        tolerance = context.get("tolerance_pct") or 10
        return (
            f"请对第 {chapter_order} 章（chapter_id={chapter_id}）做字数对齐。"
            f"目标字数 = {target}，容忍区间 ±{tolerance}%。"
            f"先调用 get_chapter_word_stats(chapter_id, target_word_count) 拿 diff，"
            f"再决定是否生成 propose_splice_block 提案。"
        )

    def tool_names(self) -> list[str]:
        return list(_TOOL_WHITELIST)
