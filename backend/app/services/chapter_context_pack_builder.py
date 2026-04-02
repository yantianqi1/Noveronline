"""构造作者侧 Chapter Context Pack。"""

from __future__ import annotations

import uuid
from typing import Any, Dict, List, Optional

from ..models.project import ProjectManager
from .canon_history_retriever import CanonHistoryRetriever
from .chapter_context_ranker import ChapterContextRanker, MAX_MUST_KNOW, MAX_SCENES, MAX_SHOULD_KNOW, MAX_WARNINGS
from .memory_subject_utils import normalize_memory_subject
from .worldline_engine_factory import build_worldline_engine
from .worldline_single_world import current_world, resolve_branch_id
from .writer_prompt_formatter import WriterPromptFormatter


class ChapterContextPackBuilder:
    def __init__(
        self,
        ranker: Optional[ChapterContextRanker] = None,
        formatter: Optional[WriterPromptFormatter] = None,
        history_retriever: Optional[CanonHistoryRetriever] = None,
    ):
        self.ranker = ranker or ChapterContextRanker()
        self.formatter = formatter or WriterPromptFormatter()
        self.history_retriever = history_retriever or CanonHistoryRetriever()

    def build(self, payload: Dict[str, Any]) -> Dict[str, Any]:
        scope = self._normalize_scope(payload)
        pack = self._build_worldline(scope) if scope["scope_type"] == "worldline_branch" else self._build_project(scope)
        pack = self._with_history_recall(pack)
        pack["writer_prompt_block"] = self.formatter.format(pack)
        return pack

    def build_options(self, project_id: str) -> Dict[str, Any]:
        project = self._require_project(project_id)
        chapters = self._load_required_json(project_id, "chapter_segments.json")["chapters"]
        continuity = self._load_required_json(project_id, "chapter_continuity.json")
        seed_analysis = ProjectManager.load_project_json(project_id, "seed_analysis.json") or {}
        chapter_map = {item["chapter_id"]: item for item in continuity.get("chapters", [])}
        chapter_options = []
        for chapter in chapters:
            chapter_options.append(
                {
                    "chapter_id": chapter["chapter_id"],
                    "order": chapter["order"],
                    "title": chapter.get("title", chapter["chapter_id"]),
                    "head_context": chapter_map.get(chapter["chapter_id"], {}).get("head_context", ""),
                }
            )
        pov_characters = [item.get("name", "") for item in seed_analysis.get("characters", []) if item.get("name")]
        return {
            "project_id": project.project_id,
            "project_name": project.name,
            "chapters": chapter_options,
            "pov_characters": pov_characters,
            "continuity_summary": continuity.get("global_summary", ""),
            "available_scope_types": ["project_chapter", "worldline_branch"],
        }

    def _build_project(self, scope: Dict[str, Any]) -> Dict[str, Any]:
        project_id = scope["project_id"]
        story_memory, continuity, consistency = self._load_project_sources(project_id)
        chapter = self._resolve_chapter(scope, project_id, continuity)
        scope = {**scope, "chapter_id": chapter["chapter_id"], "chapter_order": int(chapter.get("order", scope.get("chapter_order", 0)))}
        prev_chapter, next_chapter = self._neighbor_chapters(continuity, chapter["order"])
        must_items = self._project_fact_items(scope, story_memory, chapter)
        should_items = self._project_should_items(scope, story_memory, prev_chapter, next_chapter)
        warnings = self._project_warnings(scope, consistency, story_memory)
        scenes = self._project_scene_candidates(story_memory, chapter, prev_chapter, next_chapter)
        pack = self._pack_shell(scope)
        pack["must_know"] = self.ranker.rank_items(must_items, scope, MAX_MUST_KNOW)
        pack["should_know"] = self.ranker.rank_items(should_items, scope, MAX_SHOULD_KNOW)
        pack["warnings"] = self.ranker.rank_items(warnings, scope, MAX_WARNINGS)
        pack["scene_candidates"] = scenes[:MAX_SCENES]
        pack["debug_trace"] = self._debug_trace(pack)
        return pack

    def _build_worldline(self, scope: Dict[str, Any]) -> Dict[str, Any]:
        engine = build_worldline_engine()
        session = engine.get_session(scope["session_id"], project_id=scope.get("project_id"))
        if not session:
            raise ValueError(f"世界线会话不存在: {scope['session_id']}")
        resolve_branch_id(scope.get("branch_id"))
        branch = current_world(session)
        _, container_dir = engine.store.resolve_container(
            session.project_id or scope.get("project_id"),
            session.graph_id,
            session_scope=session.session_scope,
        )
        agent = engine.runtime_service.resolve_agent(container_dir, session, branch.branch_id, scope["pov_character"])
        if not agent:
            raise ValueError(f"世界线中不存在 POV 角色: {scope['pov_character']}")
        memory_summary = engine.memory_service.build_writer_memory_summary(
            container_dir,
            session.session_id,
            branch.branch_id,
            agent,
            include_candidates=scope.get("include_candidates", False),
        )
        must_items = self._worldline_fact_items(scope, branch, agent, memory_summary)
        should_items = self._worldline_should_items(scope, branch, memory_summary)
        warnings = self._worldline_warnings(scope, branch, memory_summary)
        if scope.get("project_id"):
            story_memory, continuity, consistency = self._load_project_sources(scope["project_id"])
            chapter = self._resolve_project_chapter(scope, scope["project_id"], continuity)
            if chapter:
                must_items.extend(self._project_fact_items(scope, story_memory, chapter))
                prev_chapter, next_chapter = self._neighbor_chapters(continuity, chapter["order"])
                should_items.extend(self._project_should_items(scope, story_memory, prev_chapter, next_chapter))
            else:
                must_items.extend(self._project_scope_fact_items(scope, story_memory, continuity))
                should_items.extend(self._project_should_items(scope, story_memory, None, None))
            warnings.extend(self._project_warnings(scope, consistency, story_memory))
        scenes = self._worldline_scene_candidates(scope, branch, memory_summary)
        pack = self._pack_shell({**scope, "branch_id": branch.branch_id})
        pack["must_know"] = self.ranker.rank_items(must_items, scope, MAX_MUST_KNOW)
        pack["should_know"] = self.ranker.rank_items(should_items, scope, MAX_SHOULD_KNOW)
        pack["warnings"] = self.ranker.rank_items(warnings, scope, MAX_WARNINGS)
        pack["scene_candidates"] = scenes[:MAX_SCENES]
        pack["debug_trace"] = self._debug_trace(pack)
        return pack

    def _project_fact_items(self, scope: Dict[str, Any], story_memory: Dict[str, Any], chapter: Dict[str, Any]) -> List[Dict[str, Any]]:
        items = [self._item("continuity", chapter["head_context"], "直接承接当前章节起点。", "chapter_continuity", chapter["chapter_id"], chapter.get("key_characters", []), scope, scope_hit=True, pov_hit=True)]
        for summary in chapter.get("core_conflicts", []):
            items.append(self._item("conflict", summary, "当前章节的主冲突必须继续推进。", "chapter_continuity", chapter["chapter_id"], chapter.get("key_characters", []), scope, scope_hit=True, pov_hit=scope["pov_character"] in chapter.get("key_characters", []), scene_hit=self._contains_focus(scope, summary)))
        for rule in story_memory.get("world_rules", []):
            items.append(self._item("world_rule", rule, "这是写作时不能违背的世界规则。", "story_memory", "world_rules", [scope["pov_character"]], scope, scope_hit=True, scene_hit=self._contains_focus(scope, rule)))
        for event in story_memory.get("event_timeline", []):
            if event.get("chapter_id") != chapter["chapter_id"]:
                continue
            items.append(self._item("event", event.get("summary", ""), "这是当前章节附近已发生的关键事件。", "story_memory", event.get("event_id", ""), event.get("characters", []), scope, scope_hit=True, pov_hit=scope["pov_character"] in event.get("characters", []), scene_hit=self._contains_focus(scope, event.get("summary", "")), salience=0.8))
        return items

    def _project_scope_fact_items(self, scope: Dict[str, Any], story_memory: Dict[str, Any], continuity: Dict[str, Any]) -> List[Dict[str, Any]]:
        items = []
        summary = str(continuity.get("global_summary") or "").strip()
        if summary:
            items.append(
                self._item(
                    "continuity",
                    summary,
                    "这是原著主线当前可依赖的 canon 承接。",
                    "chapter_continuity",
                    "global_summary",
                    [scope["pov_character"]],
                    scope,
                    scope_hit=True,
                    pov_hit=True,
                    salience=0.85,
                )
            )
        for rule in story_memory.get("world_rules", []):
            items.append(
                self._item(
                    "world_rule",
                    rule,
                    "这是写作时不能违背的世界规则。",
                    "story_memory",
                    "world_rules",
                    [scope["pov_character"]],
                    scope,
                    scope_hit=True,
                    scene_hit=self._contains_focus(scope, rule),
                    salience=0.9,
                )
            )
        return items

    def _project_should_items(self, scope: Dict[str, Any], story_memory: Dict[str, Any], prev_chapter: Optional[Dict[str, Any]], next_chapter: Optional[Dict[str, Any]]) -> List[Dict[str, Any]]:
        items = []
        for chapter, distance in ((prev_chapter, 1), (next_chapter, 1)):
            if not chapter:
                continue
            text = chapter.get("continuity_summary", "") or chapter.get("head_context", "")
            items.append(self._item("continuity_bridge", text, "帮助维持前后章节连贯。", "chapter_continuity", chapter["chapter_id"], chapter.get("key_characters", []), scope, chapter_distance=distance, pov_hit=scope["pov_character"] in chapter.get("key_characters", [])))
        for thread in story_memory.get("open_threads", []):
            items.append(self._item("open_thread", thread.get("summary", ""), "这是当前仍未回收的线索。", "story_memory", thread.get("thread_key", ""), [scope["pov_character"]], scope, thread_hit=True, scene_hit=self._contains_focus(scope, thread.get("summary", "")), salience=0.6))
        for relation in story_memory.get("relationship_ledger", []):
            related = [relation.get("source", ""), relation.get("target", "")]
            if scope["pov_character"] not in related:
                continue
            items.append(self._item("relationship", f"{relation.get('source', '')} 与 {relation.get('target', '')} 的关系仍在变化。", "人物关系会影响场景张力。", "story_memory", normalize_memory_subject(''.join(related)), related, scope, pov_hit=True, salience=0.7))
        return items

    def _project_warnings(self, scope: Dict[str, Any], consistency: Dict[str, Any], story_memory: Dict[str, Any]) -> List[Dict[str, Any]]:
        items = []
        for item in consistency.get("conflicts", []):
            items.append(self._item("consistency_risk", f"{item.get('name', '')} 存在连续性冲突。", "需要避免把冲突当作既定事实直接写死。", "consistency_report", item.get("kind", ""), [item.get("name", "")], scope, scope_hit=True, salience=0.9))
        for item in consistency.get("ambiguities", []):
            items.append(self._item("consistency_risk", f"{item.get('alias', '')} 的指代存在歧义。", item.get("reason", "需要消歧。"), "consistency_report", item.get("alias", ""), item.get("candidate_names", []), scope, scope_hit=True, salience=0.75))
        if story_memory.get("open_threads"):
            items.append(self._item("open_thread_risk", "仍有未回收线索悬置。", "新场景需要确认是否继续推进旧线索。", "story_memory", "open_threads", [scope["pov_character"]], scope, thread_hit=True, salience=0.4))
        return items

    def _project_scene_candidates(self, story_memory: Dict[str, Any], chapter: Dict[str, Any], prev_chapter: Optional[Dict[str, Any]], next_chapter: Optional[Dict[str, Any]]) -> List[Dict[str, Any]]:
        scenes = []
        for index, conflict in enumerate(chapter.get("core_conflicts", [])[:2], start=1):
            scenes.append(self._scene(f"场景 {index}", chapter.get("head_context", ""), conflict, "这是本章核心冲突。", [chapter["chapter_id"]]))
        for hook in chapter.get("tail_hooks", [])[:2]:
            scenes.append(self._scene("尾钩承接", hook, "尾钩会推动下一场戏。", "当前章节尾部已经埋下钩子。", [chapter["chapter_id"]]))
        if prev_chapter:
            scenes.append(self._scene("承接上章", prev_chapter.get("tail_hooks", [""])[0], chapter.get("head_context", ""), "上章尾钩与本章开场天然相连。", [prev_chapter["chapter_id"], chapter["chapter_id"]]))
        for thread in story_memory.get("open_threads", [])[:1]:
            scenes.append(self._scene("线索推进", thread.get("summary", ""), "通过角色行动推进未回收线索。", "开放线索仍有推进空间。", [thread.get("thread_key", "")]))
        if next_chapter:
            scenes.append(self._scene("前瞻下一章", next_chapter.get("head_context", ""), "为后续章节留出转场。", "当前章节可以提前压入下章压力。", [next_chapter["chapter_id"]]))
        return scenes[:MAX_SCENES]

    def _worldline_fact_items(self, scope: Dict[str, Any], branch, agent: Dict[str, Any], memory_summary: Dict[str, Any]) -> List[Dict[str, Any]]:
        items = [self._item("worldline_state", branch.core_change or branch.title, "这是当前分支的主偏移。", "worldline_branch", branch.branch_id, [scope["pov_character"]], scope, scope_hit=True, pov_hit=True, salience=0.8)]
        for event in branch.timeline[-6:]:
            items.append(self._item("worldline_event", event.summary, "这是分支最近推进出来的关键事件。", "worldline_timeline", event.event_id, event.driving_entities or [scope["pov_character"]], scope, scope_hit=True, pov_hit=scope["pov_character"] in (event.driving_entities or []), scene_hit=self._contains_focus(scope, event.summary), salience=0.85))
        state = agent.get("state", {})
        items.append(self._item("pov_state", f"{scope['pov_character']} 当前状态：{state.get('status', 'active')}，目标：{state.get('drive') or state.get('core_drive') or ''}", "POV 当前目标会决定场景走向。", "worldline_agent", agent["agent_id"], [scope["pov_character"]], scope, scope_hit=True, pov_hit=True, salience=0.9))
        items.extend(self._memory_summary_items(memory_summary, scope))
        return items

    def _worldline_should_items(self, scope: Dict[str, Any], branch, memory_summary: Dict[str, Any]) -> List[Dict[str, Any]]:
        items = []
        for relation in branch.relationship_states[-4:]:
            if scope["pov_character"] not in {relation.get("source", ""), relation.get("target", "")}:
                continue
            summary = f"{relation.get('source', '')} 与 {relation.get('target', '')}：{relation.get('note') or relation.get('change', '')}"
            items.append(self._item("relationship", summary, "分支中的关系偏移会改变人物决策。", "worldline_relation", relation.get("last_action", "") or normalize_memory_subject(summary), [relation.get("source", ""), relation.get("target", "")], scope, pov_hit=True, salience=0.75))
        for bucket in ("identity_constraints",):
            for item in memory_summary.get(bucket, []):
                items.append(self._item("runtime_memory", item["summary"], "这条运行时记忆会约束 POV 行动。", "agent_memory", item["memory_id"], [scope["pov_character"]], scope, pov_hit=True, salience=item.get("salience", 0.6), memory_layer=item.get("memory_layer", "canon"), archive_id=item.get("archive_id", ""), normalized_subject=item.get("normalized_subject", "")))
        return items

    def _worldline_warnings(self, scope: Dict[str, Any], branch, memory_summary: Dict[str, Any]) -> List[Dict[str, Any]]:
        warnings = [
            self._item("worldline_drift", "当前分支已经偏离原著时间线。", "写作时要明确区分 worldline 推演与 canon 设定。", "worldline_branch", branch.branch_id, [scope["pov_character"]], scope, scope_hit=True, salience=0.8),
        ]
        if branch.pending_actions:
            warnings.append(self._item("pending_action", "当前世界还有待处理动作。", "写场景前需要确认这些动作是否已落地。", "worldline_branch", branch.branch_id, [scope["pov_character"]], scope, scope_hit=True, salience=0.6))
        if memory_summary.get("relationship_tensions"):
            warnings.append(self._item("relationship_risk", "POV 相关关系张力仍在升高。", "对话与动作需要反映这层紧张。", "agent_memory", scope["pov_character"], [scope["pov_character"]], scope, pov_hit=True, salience=0.7))
        return warnings

    def _worldline_scene_candidates(self, scope: Dict[str, Any], branch, memory_summary: Dict[str, Any]) -> List[Dict[str, Any]]:
        scenes = []
        for event in branch.timeline[-3:]:
            scenes.append(self._scene(event.title or "世界线事件", event.summary, branch.core_change, "最近事件会自然延续成下一场戏。", [event.event_id]))
        for item in memory_summary.get("active_strategies", [])[:2]:
            scenes.append(self._scene("策略兑现", item["summary"], "POV 会尝试兑现既有策略。", "运行时策略应该转化成具体场景动作。", [item["memory_id"]]))
        if not scenes:
            scenes.append(self._scene("分支开场", branch.core_change, "从 POV 当前目标出发。", "至少需要一个起始场景。", [branch.branch_id]))
        return scenes[:MAX_SCENES]

    def _memory_summary_items(self, memory_summary: Dict[str, Any], scope: Dict[str, Any]) -> List[Dict[str, Any]]:
        items = []
        for bucket in ("recent_commitments", "active_strategies", "relationship_tensions"):
            for item in memory_summary.get(bucket, []):
                items.append(self._item("runtime_memory", item["summary"], "这条运行时记忆会直接影响下一章行动。", "agent_memory", item["memory_id"], [scope["pov_character"]], scope, pov_hit=True, salience=item.get("salience", 0.6), memory_layer=item.get("memory_layer", "canon"), archive_id=item.get("archive_id", ""), normalized_subject=item.get("normalized_subject", "")))
        return items

    def _normalize_scope(self, payload: Dict[str, Any]) -> Dict[str, Any]:
        scope_type = str(payload.get("scope_type") or "").strip()
        if scope_type not in {"project_chapter", "worldline_branch"}:
            raise ValueError("scope_type 只支持 project_chapter 或 worldline_branch")
        project_id = str(payload.get("project_id") or "").strip()
        chapter_id = str(payload.get("chapter_id") or "").strip()
        chapter_order = int(payload.get("chapter_order") or 0)
        pov_character = str(payload.get("pov_character") or "").strip()
        if scope_type == "project_chapter" and not project_id:
            raise ValueError("project_chapter 模式必须提供 project_id")
        if scope_type == "project_chapter" and not (chapter_id or chapter_order):
            raise ValueError("project_chapter 模式必须提供 chapter_id 或 chapter_order")
        if scope_type == "worldline_branch" and not str(payload.get("session_id") or "").strip():
            raise ValueError("worldline_branch 模式必须提供 session_id")
        if not pov_character:
            raise ValueError("必须提供 pov_character")
        return {
            "scope_type": scope_type,
            "project_id": project_id,
            "session_id": str(payload.get("session_id") or "").strip(),
            "branch_id": str(payload.get("branch_id") or "main").strip(),
            "chapter_id": chapter_id,
            "chapter_order": chapter_order,
            "pov_character": pov_character,
            "writing_goal": str(payload.get("writing_goal") or "").strip(),
            "scene_focus": str(payload.get("scene_focus") or "").strip(),
            "author_instruction": str(payload.get("author_instruction") or "").strip(),
            "include_candidates": bool(payload.get("include_candidates", False)),
        }

    def _resolve_chapter(self, scope: Dict[str, Any], project_id: str, continuity: Dict[str, Any]) -> Dict[str, Any]:
        chapters = continuity.get("chapters", [])
        if scope.get("chapter_id"):
            for item in chapters:
                if item["chapter_id"] == scope["chapter_id"]:
                    return item
        if scope.get("chapter_order"):
            for item in chapters:
                if int(item.get("order", 0)) == scope["chapter_order"]:
                    return item
        raise ValueError(f"未找到章节: {scope.get('chapter_id') or scope.get('chapter_order') or project_id}")

    def _neighbor_chapters(self, continuity: Dict[str, Any], order: int) -> tuple[Optional[Dict[str, Any]], Optional[Dict[str, Any]]]:
        chapters = continuity.get("chapters", [])
        prev_chapter = next((item for item in chapters if int(item.get("order", 0)) == order - 1), None)
        next_chapter = next((item for item in chapters if int(item.get("order", 0)) == order + 1), None)
        return prev_chapter, next_chapter

    def _resolve_project_chapter(self, scope: Dict[str, Any], project_id: str, continuity: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        if not self._has_chapter_selector(scope):
            return None
        return self._resolve_chapter(scope, project_id, continuity)

    def _has_chapter_selector(self, scope: Dict[str, Any]) -> bool:
        return bool(scope.get("chapter_id") or scope.get("chapter_order"))

    def _pack_shell(self, scope: Dict[str, Any]) -> Dict[str, Any]:
        return {
            "context_scope": scope,
            "must_know": [],
            "should_know": [],
            "warnings": [],
            "scene_candidates": [],
            "history_recall": self._empty_history_recall(),
            "writer_prompt_block": "",
            "debug_trace": [],
        }

    def _debug_trace(self, pack: Dict[str, Any]) -> List[Dict[str, Any]]:
        items = pack.get("must_know", []) + pack.get("should_know", []) + pack.get("warnings", [])
        return [
            {
                "item_id": item["item_id"],
                "category": item["category"],
                "source_kind": item["source_kind"],
                "source_ref": item["source_ref"],
                "memory_layer": item["memory_layer"],
                "rank_score": item.get("rank_score", 0.0),
            }
            for item in items
        ] + [
            {"trace_type": "history_recall", **item}
            for item in pack.get("history_recall", {}).get("selection_trace", [])
        ]

    def _item(self, category: str, summary: str, why: str, source_kind: str, source_ref: str, related_entities: List[str], scope: Dict[str, Any], *, scope_hit: bool = False, pov_hit: bool = False, scene_hit: bool = False, thread_hit: bool = False, chapter_distance: int = 0, salience: float = 0.5, memory_layer: str = "canon", archive_id: str = "", normalized_subject: str = "") -> Dict[str, Any]:
        return {
            "item_id": f"ctx_{uuid.uuid5(uuid.NAMESPACE_DNS, f'{category}:{source_kind}:{source_ref}:{summary}').hex[:12]}",
            "category": category,
            "summary": summary,
            "why_it_matters": why,
            "source_kind": source_kind,
            "source_ref": source_ref,
            "related_entities": [item for item in related_entities if item],
            "memory_layer": memory_layer,
            "archive_id": archive_id,
            "normalized_subject": normalized_subject,
            "salience": salience,
            "match_meta": {
                "scope_hit": scope_hit,
                "pov_hit": pov_hit,
                "scene_hit": scene_hit,
                "thread_hit": thread_hit,
                "chapter_distance": chapter_distance,
                "freshness": max(0.0, 1.0 - (0.2 * chapter_distance)),
            },
        }

    def _scene(self, title: str, setup: str, tension: str, why_now: str, depends_on: List[str]) -> Dict[str, Any]:
        return {"title": title, "setup": setup, "tension": tension, "why_now": why_now, "depends_on": depends_on}

    def _contains_focus(self, scope: Dict[str, Any], text: str) -> bool:
        focus = scope.get("scene_focus", "")
        return bool(focus and focus in str(text or ""))

    def _with_history_recall(self, pack: Dict[str, Any]) -> Dict[str, Any]:
        scope = pack["context_scope"]
        history_recall = self._build_history_recall(scope)
        pack["history_recall"] = history_recall
        if not history_recall["recent_anchors"] and not history_recall["callback_memories"]:
            pack["debug_trace"] = self._debug_trace(pack)
            return pack
        must_items, should_items = self._history_context_items(scope, history_recall)
        if scope.get("scope_type") != "project_chapter":
            should_items = must_items + should_items
            must_items = []
        pack["must_know"] = self.ranker.rank_items(pack["must_know"] + must_items, scope, MAX_MUST_KNOW)
        pack["should_know"] = self.ranker.rank_items(pack["should_know"] + should_items, scope, MAX_SHOULD_KNOW)
        pack["debug_trace"] = self._debug_trace(pack)
        return pack

    def _build_history_recall(self, scope: Dict[str, Any]) -> Dict[str, Any]:
        if not scope.get("project_id") or int(scope.get("chapter_order") or 0) <= 1:
            return self._empty_history_recall()
        return self.history_retriever.recall(
            project_id=scope["project_id"],
            current_chapter_order=int(scope["chapter_order"]),
            pov_character=scope["pov_character"],
            scene_focus=scope.get("scene_focus", ""),
            author_instruction=scope.get("author_instruction") or scope.get("writing_goal", ""),
        )

    def _history_context_items(
        self,
        scope: Dict[str, Any],
        history_recall: Dict[str, Any],
    ) -> tuple[List[Dict[str, Any]], List[Dict[str, Any]]]:
        must_items = self._history_anchor_items(scope, history_recall.get("recent_anchors", []))
        must_items.extend(self._history_world_rule_items(scope, history_recall.get("world_rules", [])))
        callbacks = history_recall.get("callback_memories", [])
        must_items.extend(self._history_callback_items(scope, callbacks[:4], True))
        should_items = self._history_callback_items(scope, callbacks[4:], False)
        should_items.extend(self._history_thread_items(scope, history_recall.get("active_threads", [])))
        return must_items, should_items

    def _history_anchor_items(self, scope: Dict[str, Any], anchors: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        items = []
        for anchor in anchors:
            summary = f"第{anchor.get('chapter_order', 0)}章《{anchor.get('title', '')}》：{anchor.get('summary_text', '')}"
            items.append(
                self._item(
                    "history_anchor",
                    summary,
                    "这是最近章节的 canon 承接，应该优先延续。",
                    "chapter_meta",
                    anchor.get("chapter_id", ""),
                    [scope["pov_character"]],
                    scope,
                    scope_hit=True,
                    chapter_distance=max(0, int(scope["chapter_order"]) - int(anchor.get("chapter_order", 0))),
                    scene_hit=self._contains_focus(scope, " ".join([anchor.get("summary_text", ""), anchor.get("end_anchor", "")])),
                    salience=0.9,
                )
            )
        return items

    def _history_world_rule_items(self, scope: Dict[str, Any], world_rules: List[str]) -> List[Dict[str, Any]]:
        return [
            self._item(
                "world_rule",
                rule,
                "这是历史召回确认仍生效的 canon 世界规则。",
                "chapter_history_item",
                f"world_rule:{index}",
                [scope["pov_character"]],
                scope,
                scope_hit=True,
                scene_hit=self._contains_focus(scope, rule),
                salience=0.85,
            )
            for index, rule in enumerate(world_rules, start=1)
        ]

    def _history_callback_items(
        self,
        scope: Dict[str, Any],
        callbacks: List[Dict[str, Any]],
        is_must: bool,
    ) -> List[Dict[str, Any]]:
        items = []
        for item in callbacks:
            category = self._history_category(item.get("item_type", "summary"))
            why = "这是需要在当前章节回调的长线 canon 记忆。" if is_must else "这条长线 canon 记忆可作为补强呼应。"
            items.append(
                self._item(
                    category,
                    item.get("summary_text", ""),
                    why,
                    item.get("source_kind", "chapter_history_item"),
                    item.get("source_ref", ""),
                    item.get("related_entities", []),
                    scope,
                    pov_hit="pov" in item.get("selected_because", []),
                    scene_hit="scene_focus" in item.get("selected_because", []),
                    thread_hit=bool(item.get("thread_key")),
                    chapter_distance=max(0, int(scope["chapter_order"]) - int(item.get("chapter_order", 0))),
                    salience=min(1.0, float(item.get("rank_score", 0.0)) / 10.0),
                    normalized_subject=item.get("subject_key", ""),
                )
            )
        return items

    def _history_thread_items(self, scope: Dict[str, Any], threads: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        return [
            self._item(
                "open_thread",
                item.get("summary_text", ""),
                "这是仍未回收的 canon 线索，当前章应考虑回应或继续推进。",
                item.get("source_kind", "chapter_history_item"),
                item.get("source_ref", ""),
                item.get("related_entities", []),
                scope,
                scene_hit="scene_focus" in item.get("selected_because", []),
                thread_hit=True,
                chapter_distance=max(0, int(scope["chapter_order"]) - int(item.get("chapter_order", 0))),
                salience=min(1.0, float(item.get("rank_score", 0.0)) / 10.0),
                normalized_subject=item.get("thread_key", ""),
            )
            for item in threads
        ]

    def _history_category(self, item_type: str) -> str:
        return {
            "summary": "history_callback",
            "event": "event",
            "relationship": "relationship",
        }.get(item_type, "history_callback")

    def _empty_history_recall(self) -> Dict[str, Any]:
        return {
            "recent_anchors": [],
            "callback_memories": [],
            "active_threads": [],
            "world_rules": [],
            "selection_trace": [],
        }

    def _load_required_json(self, project_id: str, filename: str) -> Dict[str, Any]:
        payload = ProjectManager.load_project_json(project_id, filename)
        if payload is None:
            raise ValueError(f"项目缺少必需产物: {filename}")
        return payload

    def _load_project_sources(self, project_id: str) -> tuple[Dict[str, Any], Dict[str, Any], Dict[str, Any]]:
        return (
            self._load_required_json(project_id, "story_memory.json"),
            self._load_required_json(project_id, "chapter_continuity.json"),
            self._load_required_json(project_id, "consistency_report.json"),
        )

    def _require_project(self, project_id: str):
        project = ProjectManager.get_project(project_id)
        if not project:
            raise ValueError(f"项目不存在: {project_id}")
        return project
