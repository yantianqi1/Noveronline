"""🔗 一键补关系 — scan for unmodeled character co-occurrences and propose relations.

§4.4.5: MAX_ROUNDS=10, whitelist is read tools + ``propose_relationship``.
"""

from __future__ import annotations

from .base import OneClickRunner

_SYSTEM_PROMPT = """你是小说写作 agent 的「关系补全提案员」。当前章节正文中出现了若干角色互动，但 DB 中
两两关系可能未建档或过时。你的任务：扫描本章 POV + 被提及实体，识别关系缺口，为每
个缺口生成 RelationshipProposalCard。

执行顺序：
1. 调 query_scene(chapter_id) 遍历场景拿 pov_entity_id + involved_entities_json。
2. 收集所有在本章共现的角色对 (A, B)，A ≠ B。
3. 对每对调 query_relationship(A, B, include_candidate=true)；若"未找到"或关系陈旧
   （last_seen_chapter < 当前章 - 5）则进入提案流程。
4. 对每对缺口调 search_manuscript 取本章的互动原文证据。
5. 基于原文证据调 propose_relationship(entity_a, entity_b, relation_type, description,
   evidence_snippet, ...)。
6. 总提案 ≤ 10。严禁调用真 manage_relationship。
7. 若无缺口，输出 {"verdict":"no_gap"} 终止。
"""


_TOOL_WHITELIST = [
    "query_scene",
    "query_entity",
    "query_relationship",
    "query_graph_neighbors",
    "query_relationship_network",
    "search_manuscript",
    "get_manuscript_context",
    "propose_relationship",
]


class RelationshipFillerRunner(OneClickRunner):
    name = "relationship_filler"
    max_rounds = 10

    def build_system_prompt(self, context: dict) -> str:
        return _SYSTEM_PROMPT

    def build_user_message(self, context: dict) -> str:
        chapter_id = context.get("chapter_id") or ""
        chapter_order = context.get("chapter_order") or 0
        return (
            f"请扫描第 {chapter_order} 章（chapter_id={chapter_id}）中共现的角色对，"
            f"识别关系缺口并调用 propose_relationship 生成提案。"
            f"先 query_scene 拿场景角色，再 query_relationship 核对 DB 已有关系。"
        )

    def tool_names(self) -> list[str]:
        return list(_TOOL_WHITELIST)
