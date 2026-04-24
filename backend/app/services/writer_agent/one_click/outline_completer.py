"""🪄 一键补全大纲 — scan for outline gaps and emit SceneProposalCards.

See §4.4.1 of the writer-workbench plan for the full spec: MAX_ROUNDS=8,
whitelist covers read tools + ``propose_outline_scene``.
"""

from __future__ import annotations

from .base import OneClickRunner

_SYSTEM_PROMPT = """你是小说写作 agent 的「大纲补全助手」。当前章节已有部分 scene/beat，但存在断裂或
缺失（如 POV 切换没过渡、悬念抛出后无承接、关键角色登场前无铺垫）。你的唯一任务：
扫描现有大纲和前后章节的连接点，识别缺口，通过 propose_outline_scene 工具为每个
缺口产出一个 SceneProposalCard 提案。

强制规则：
1. 严禁直接调用 manage_* / splice_block / rewrite_span 等任何写工具，你只能提案。
2. 先调用 query_chapter(本章) + query_chapter(前一章) + query_chapter(后一章)
   + get_open_threads 摸清现状，再识别缺口。
3. 每个缺口最多生成 1 个 SceneProposalCard；总提案数不超过 6。
4. 缺口判定：场景 A 和 B 之间 POV 跳变但无过渡、悬念抛出 3 个场景仍未推进、
   新角色无登场铺垫、章节字数目标差异显著。
5. 每张卡必须含 insert_after_scene_order / reason / target_word_count。
6. 若无缺口，直接输出 {"verdict":"no_gap"} 终止，不要编造。
"""


_TOOL_WHITELIST = [
    # Read tools
    "query_chapter",
    "query_scene",
    "get_open_threads",
    "get_story_overview",
    "query_entity",
    "search_settings",
    "global_search",
    "query_segment_summaries",
    # The only write-ish tool (but really a proposal, so it runs in the read lane)
    "propose_outline_scene",
]


class OutlineCompleterRunner(OneClickRunner):
    name = "outline_completer"
    max_rounds = 8

    def build_system_prompt(self, context: dict) -> str:
        return _SYSTEM_PROMPT

    def build_user_message(self, context: dict) -> str:
        chapter_id = context.get("chapter_id") or ""
        chapter_order = context.get("chapter_order") or 0
        return (
            f"请扫描第 {chapter_order} 章（chapter_id={chapter_id}）的大纲，"
            f"识别缺口并调用 propose_outline_scene 生成提案。"
            f"先查询本章 + 前后章 + open threads。"
        )

    def tool_names(self) -> list[str]:
        return list(_TOOL_WHITELIST)
