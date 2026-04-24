"""🚫 一键扫禁词 — emit ProseDiff rewrite cards for forbidden-lexicon hits.

§4.4.4: MAX_ROUNDS=6, whitelist is scan tools + ``propose_rewrite_span``.
"""

from __future__ import annotations

from .base import OneClickRunner

_SYSTEM_PROMPT = """你是小说写作 agent 的「禁词改写提案员」。当前章节正文存在禁词命中，你的任务：为每
个命中生成 ProseDiffViewCard 改写提案。

强制规则：
1. 先调 scan_forbidden_lexicon(chapter_id=..., lexicon_asset_ids=[...]) 拿命中。
2. 若命中为 0，输出 {"verdict":"clean"} 并终止。
3. 对每个命中按 block 分组，单 block 同一匹配仅出一张卡。
4. 对每张卡调 propose_rewrite_span(block_id, original_text=<含命中的短语，扩到块内唯一>,
   new_text=<等价改写>, reason='禁词 [X] 改写')。
5. new_text 必须保留原意、角色口吻、字数差 ±20%。严禁调用真 rewrite_span。
6. 总卡数 ≤ 20；命中过多时按 severity=block 优先。
"""


_TOOL_WHITELIST = [
    "scan_forbidden_lexicon",
    "list_forbidden_lexicon",
    "get_manuscript_context",
    "propose_rewrite_span",
]


class LexiconCleanerRunner(OneClickRunner):
    name = "lexicon_cleaner"
    max_rounds = 6

    def build_system_prompt(self, context: dict) -> str:
        return _SYSTEM_PROMPT

    def build_user_message(self, context: dict) -> str:
        chapter_id = context.get("chapter_id") or ""
        chapter_order = context.get("chapter_order") or 0
        asset_ids = context.get("lexicon_asset_ids") or []
        asset_hint = (
            f"指定禁词资产 {asset_ids}" if asset_ids else "使用项目启用的全部禁词资产"
        )
        return (
            f"请扫描第 {chapter_order} 章（chapter_id={chapter_id}）的禁词。"
            f"{asset_hint}。"
            f"先调 scan_forbidden_lexicon(chapter_id, lexicon_asset_ids={asset_ids})，"
            f"再按命中逐个生成 propose_rewrite_span 提案。"
        )

    def tool_names(self) -> list[str]:
        return list(_TOOL_WHITELIST)
