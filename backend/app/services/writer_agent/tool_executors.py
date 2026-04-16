"""Tool executor implementations for the novel writer agent.

Each executor calls the corresponding repository methods and formats
the result as readable text for the LLM.
"""

from __future__ import annotations

import json
import logging
import os
import traceback
import uuid
from datetime import datetime, timezone
from typing import Any

from sqlalchemy import and_, insert, or_, select, update

from ...config import Config
from ...database import get_engine
from ...repositories import (
    ChapterRepository,
    EntityRepository,
    EventRepository,
    ManuscriptRepository,
    MetaRepository,
    NarrativeRepository,
    RelationshipRepository,
    SceneRepository,
    SearchRepository,
    ThreadRepository,
    WorldRuleRepository,
)
from ...tables.novel import (
    agent_memory,
    agent_states,
    character_events,
    entities,
    entity_aliases,
    entity_evidence,
    plot_threads,
    relationship_events,
    sessions,
    thread_lifecycle,
    world_events,
    world_rule_evidence,
    worldline_branches,
)

logger = logging.getLogger(__name__)

TOOL_RESULT_MAX_CHARS = 16000
_PRESERVE_HEAD = 11000  # Enough to keep a full 5000-char deep profile + structured fields
_PRESERVE_TAIL = 2500


def _truncate_result(result: str, max_chars: int = TOOL_RESULT_MAX_CHARS) -> str:
    """Truncate keeping head + tail so trailing context (often most relevant) is preserved."""
    if len(result) <= max_chars:
        return result
    omitted = len(result) - _PRESERVE_HEAD - _PRESERVE_TAIL
    return (
        result[:_PRESERVE_HEAD]
        + f"\n\n... [省略 {omitted} 字] ...\n\n"
        + result[-_PRESERVE_TAIL:]
    )


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


# ---------------------------------------------------------------------------
# Public entry point
# ---------------------------------------------------------------------------


def execute_tool(tool_name: str, tool_input: dict, project_id: str) -> str:
    """Execute a named tool.

    Returns a formatted string result, truncated with head+tail preservation.
    """
    executor = _EXECUTORS.get(tool_name)
    if executor is None:
        return f"未知工具：{tool_name}"
    try:
        result = executor(tool_input, project_id)
    except Exception:
        logger.error("Tool %s execution failed:\n%s", tool_name, traceback.format_exc())
        result = f"工具 {tool_name} 执行出错：{traceback.format_exc()}"
    return _truncate_result(result)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _get_repos() -> dict[str, Any]:
    """Return a dict of repository instances sharing a single engine.

    Each call creates fresh repo objects (lightweight); the underlying engine
    is a shared singleton so connection-pool overhead is minimal.
    """
    engine = get_engine()
    return {
        "entity": EntityRepository(engine),
        "scene": SceneRepository(engine),
        "chapter": ChapterRepository(engine),
        "thread": ThreadRepository(engine),
        "world_rule": WorldRuleRepository(engine),
        "relationship": RelationshipRepository(engine),
        "manuscript": ManuscriptRepository(engine),
        "event": EventRepository(engine),
        "outline": OutlineRepository(engine),
        "narrative": NarrativeRepository(engine),
        "meta": MetaRepository(engine),
        "search": SearchRepository(engine),
    }


# Re-export OutlineRepository for _get_repos
from ...repositories import OutlineRepository  # noqa: E402


def _pretty_json(raw: str | None) -> str:
    """Try to parse a JSON string and return indented readable text."""
    if not raw:
        return ""
    try:
        obj = json.loads(raw)
        if isinstance(obj, (dict, list)) and not obj:
            return ""  # Treat empty containers as "no data"
        return json.dumps(obj, ensure_ascii=False, indent=2)
    except (json.JSONDecodeError, TypeError):
        return raw


def _append_if(lines: list[str], label: str, value: str | None) -> None:
    """Append ``label：value`` to *lines* only when *value* is non-empty."""
    if value and value.strip():
        lines.append(f"{label}：{value}")


# ---------------------------------------------------------------------------
# Individual executors
# ---------------------------------------------------------------------------


def _query_entity(params: dict, project_id: str) -> str:
    name = params["name"]
    entity_type = params.get("entity_type")
    repos = _get_repos()
    entity = repos["entity"].get_entity_by_name(project_id, name, entity_type)
    if entity is None:
        return f"未找到实体：{name}"

    lines: list[str] = []

    # Long-form character bible (deep profile) — placed at the very top so the
    # writer LLM sees it first. This is the strongest防 OOC约束。
    deep_profile = (entity.get("deep_profile_md") or "").strip()
    if deep_profile:
        lines.append("===== 角色长文档案（写作时必须严格遵守，下述行为禁区与语言禁忌优先级最高）=====")
        lines.append(deep_profile)
        lines.append("===== 长文档案结束 =====")
        lines.append("")  # blank line separator
        lines.append("以下为补充结构化字段，与上面长文档案不一致时，以长文档案为准：")

    lines.extend([
        f"【{entity.get('entity_type', '未知')}】{entity.get('name', name)}",
        f"重要性：{entity.get('importance_tier', '未知')}",
        f"概述：{entity.get('summary') or '无'}",
        f"核心驱动：{entity.get('core_drive') or '无'}",
        f"表面表现：{entity.get('surface_mask') or '无'}",
        f"内在矛盾：{entity.get('hidden_tension') or '无'}",
    ])

    # Structured personality & speech fields
    _append_if(lines, "说话风格", entity.get("speech_style"))
    _append_if(lines, "口头禅", _pretty_json(entity.get("verbal_habits_json")))
    _append_if(lines, "经典台词", _pretty_json(entity.get("example_quotes_json")))
    _append_if(lines, "性格特征", _pretty_json(entity.get("personality_traits_json")))
    _append_if(lines, "价值观", entity.get("values_text"))
    _append_if(lines, "恐惧", entity.get("fears_text"))
    _append_if(lines, "决策模式", entity.get("decision_pattern"))

    # Character psychology
    _append_if(lines, "社交面具", entity.get("mask_behavior"))
    _append_if(lines, "情绪基线", entity.get("emotional_baseline"))
    _append_if(lines, "认知偏差", _pretty_json(entity.get("cognitive_biases_json")))

    # Capabilities & knowledge
    _append_if(lines, "能力", _pretty_json(entity.get("skills_json")))
    _append_if(lines, "局限", _pretty_json(entity.get("limitations_json")))
    _append_if(lines, "资源", entity.get("resources_text"))
    _append_if(lines, "知识边界", _pretty_json(entity.get("knowledge_boundary_json")))

    # Goals
    _append_if(lines, "终极目标", entity.get("ultimate_goal"))
    _append_if(lines, "当前目标", entity.get("current_objective"))

    # Archive-sourced extras
    _append_if(lines, "关系概述", entity.get("relationship_summary_text"))
    _append_if(lines, "行为提示", entity.get("agent_behavior_hint"))
    _append_if(lines, "风险", _pretty_json(entity.get("notable_risks_json")))

    lines.append(f"详细设定：{_pretty_json(entity.get('profile_json')) or '无'}")

    # --- Associated plot threads ---
    entity_id = entity.get("entity_id", "")
    if entity_id:
        threads = repos["thread"].get_entity_threads(project_id, entity_id, limit=5)
        if threads:
            lines.append("\n【关联伏笔】")
            for t in threads:
                status = t.get("status", "open")
                label = _STATUS_LABELS.get(status, status)
                key = t.get("thread_key", "")
                detail = t.get("detail", "")
                text = f"  [{label}] {key}"
                if detail:
                    text += f"：{detail}"
                lines.append(text)

        # --- Associated world rules ---
        rules = repos["world_rule"].get_entity_rules(project_id, entity_id, limit=5)
        if rules:
            lines.append("\n【适用世界规则】")
            for r in rules:
                lines.append(f"  规则：{r.get('fact_text', '')}")
                snippet = r.get("evidence_snippet", "")
                if snippet:
                    lines.append(f"    证据：{snippet}")

        # --- Recent events ---
        events = repos["entity"].get_entity_recent_events(project_id, entity_id, limit=5)
        if events:
            lines.append("\n【近期事件】")
            for e in events:
                etype = e.get("event_type", "")
                prefix = f"[{etype}] " if etype else ""
                detail = e.get("summary", "")
                ch = e.get("chapter_order", "")
                ch_prefix = f"第{ch}章：" if ch else ""
                lines.append(f"  {prefix}{ch_prefix}{detail}")

    return "\n".join(lines)


def _query_relationship(params: dict, project_id: str) -> str:
    entity_a = params["entity_a"]
    entity_b = params["entity_b"]
    repos = _get_repos()
    # Resolve names to entity_ids
    a_id = repos["entity"].resolve_entity_id(project_id, entity_a)
    b_id = repos["entity"].resolve_entity_id(project_id, entity_b)
    if not a_id or not b_id:
        return f"未找到 {entity_a} 与 {entity_b} 之间的关系记录"

    # Bidirectional lookup: all relationships where (source, target) match
    engine = get_engine()
    from ...tables.novel import relationships as rel_tbl
    with engine.connect() as conn:
        rows = conn.execute(
            select(rel_tbl).where(
                and_(
                    rel_tbl.c.project_id == project_id,
                    or_(
                        and_(rel_tbl.c.source_id == a_id, rel_tbl.c.target_id == b_id),
                        and_(rel_tbl.c.source_id == b_id, rel_tbl.c.target_id == a_id),
                    ),
                )
            )
        ).fetchall()
        rels = [dict(r._mapping) for r in rows]

    if not rels:
        return f"未找到 {entity_a} 与 {entity_b} 之间的关系记录"

    parts: list[str] = []
    for r in rels:
        lines = [
            f"关系类型：{r.get('relation_type', '未知')}",
            f"描述：{r.get('description') or '无'}",
            f"信任度：{r.get('trust_level', '未知')}",
            f"权力动态：{r.get('power_dynamic') or '无'}",
            f"历史：{r.get('history') or '无'}",
            f"冲突触发：{r.get('conflict_trigger') or '无'}",
        ]
        parts.append("\n".join(lines))
    return "\n---\n".join(parts)


def _query_chapter(params: dict, project_id: str) -> str:
    chapter_order = params["chapter_order"]
    include_content = params.get("include_content", False)
    repos = _get_repos()
    chapter = repos["chapter"].get_chapter_by_order(project_id, chapter_order, include_content)
    if chapter is None:
        return f"未找到第 {chapter_order} 章"

    lines = [
        f"第 {chapter_order} 章：{chapter.get('title') or '无标题'}",
        f"状态：{chapter.get('status', '未知')}",
        f"字数：{chapter.get('word_count', 0)}",
        f"POV 角色：{chapter.get('pov_character') or '未指定'}",
        f"摘要：{chapter.get('summary') or '无'}",
        f"大纲：{_pretty_json(chapter.get('outline_json')) or '无'}",
        f"时间线：{chapter.get('timeline_note') or '无'}",
        f"未解决线索：{_pretty_json(chapter.get('open_threads_json')) or '无'}",
    ]
    _append_if(lines, "关键事件", _pretty_json(chapter.get("key_events_json")))
    _append_if(lines, "角色状态变化", _pretty_json(chapter.get("character_state_updates_json")))
    _append_if(lines, "关系变化", _pretty_json(chapter.get("relationship_updates_json")))
    _append_if(lines, "起始锚点", chapter.get("start_anchor"))
    _append_if(lines, "结束锚点", chapter.get("end_anchor"))
    if include_content:
        content = chapter.get("content", "")
        lines.append(f"正文：\n{content}")
    return "\n".join(lines)


def _query_scene(params: dict, project_id: str) -> str:
    chapter_id = params["chapter_id"]
    scene_order = params.get("scene_order")
    repos = _get_repos()

    if scene_order is not None:
        # Find the specific scene by chapter_id + scene_order
        scene_list = repos["scene"].list_scenes(project_id, chapter_id)
        scene = None
        for s in scene_list:
            if s.get("scene_order") == scene_order:
                scene = repos["scene"].get_scene(project_id, s["scene_id"])
                break
        if scene is None:
            return f"未找到章节 {chapter_id} 的第 {scene_order} 个场景"
        lines = [
            f"场景 {scene.get('scene_order', '?')}：{scene.get('title') or '无标题'}",
            f"状态：{scene.get('status', '未知')}",
            f"字数：{scene.get('word_count', 0)}",
            f"地点：{scene.get('location') or '未指定'}",
            f"POV 实体：{scene.get('pov_entity_id') or '未指定'}",
            f"涉及实体：{_pretty_json(scene.get('involved_entities_json')) or '无'}",
            f"写作简报：{_pretty_json(scene.get('writing_brief_json')) or '无'}",
            f"内容：\n{scene.get('content', '')}",
        ]
        return "\n".join(lines)
    else:
        # List all scenes for the chapter
        scene_list = repos["scene"].list_scenes(project_id, chapter_id)
        if not scene_list:
            return f"章节 {chapter_id} 暂无场景"
        lines = [f"章节 {chapter_id} 场景列表："]
        for s in scene_list:
            lines.append(
                f"  [{s.get('scene_order', '?')}] {s.get('title') or '无标题'}"
                f" （{s.get('status', '未知')}，{s.get('word_count', 0)} 字）"
            )
        return "\n".join(lines)


def _search_settings(params: dict, project_id: str) -> str:
    query = params["query"]
    scope = params.get("scope", "all")
    limit = params.get("limit", 10)
    repos = _get_repos()

    # Map scope to source filters for the global search index
    source_map = {
        "entities": ["entity"],
        "chapters": ["chapter"],
        "scenes": ["scene"],
    }
    sources = source_map.get(scope)  # None means "all"
    results = repos["search"].search(
        query, project_id=project_id, sources=sources, limit=limit,
    )
    if not results:
        return f"未找到与「{query}」相关的设定"

    lines = [f"搜索「{query}」结果（{len(results)} 条）："]
    for i, r in enumerate(results, 1):
        source = r.get("source", "未知")
        name = r.get("name") or r.get("title") or ""
        snippet = r.get("snippet", "")
        lines.append(f"{i}. [{source}] {name}")
        if snippet:
            lines.append(f"   {snippet}")
    return "\n".join(lines)


def _get_recent_scenes(params: dict, project_id: str) -> str:
    chapter_id = params["chapter_id"]
    scene_order = params["scene_order"]
    count = params.get("count", 2)
    repos = _get_repos()
    recent = repos["scene"].get_recent_scenes(project_id, chapter_id, scene_order, count)
    if not recent:
        return "没有找到前序场景"

    parts: list[str] = []
    for s in recent:
        lines = [
            f"场景 {s.get('scene_order', '?')}：{s.get('title') or '无标题'}",
            s.get("content", ""),
        ]
        parts.append("\n".join(lines))
    return "\n---\n".join(parts)


def _get_world_state(params: dict, project_id: str) -> str:
    session_id = params["session_id"]
    entity_id = params.get("entity_id")
    branch_id = params.get("branch_id")

    engine = get_engine()
    with engine.connect() as conn:
        # Session
        session_row = conn.execute(
            select(sessions).where(sessions.c.session_id == session_id).limit(1)
        ).fetchone()
        session = dict(session_row._mapping) if session_row else None

        # Agent states
        state_clauses = [agent_states.c.session_id == session_id]
        if branch_id:
            state_clauses.append(agent_states.c.branch_id == branch_id)
        if entity_id:
            state_clauses.append(agent_states.c.entity_id == entity_id)
        state_rows = conn.execute(
            select(agent_states).where(and_(*state_clauses))
        ).fetchall()

        # Events
        ev_clauses = [world_events.c.session_id == session_id]
        if branch_id:
            ev_clauses.append(world_events.c.branch_id == branch_id)
        ev_rows = conn.execute(
            select(world_events).where(and_(*ev_clauses))
            .order_by(world_events.c.step.desc()).limit(10)
        ).fetchall()

    state = {
        "session": session,
        "agent_states": [dict(r._mapping) for r in state_rows],
        "recent_events": [dict(r._mapping) for r in ev_rows],
    }

    lines: list[str] = []

    session = state.get("session")
    if session:
        lines.append(f"会话：{session.get('title') or session_id}")
        lines.append(f"状态：{session.get('status', '未知')}")
        lines.append(f"类型：{session.get('session_type', '未知')}")
        focus = session.get("focus_question")
        if focus:
            lines.append(f"焦点问题：{focus}")
        if branch_id:
            lines.append(f"分支过滤：{branch_id}")
    else:
        lines.append(f"未找到会话：{session_id}")

    agent_states = state.get("agent_states", [])
    if agent_states:
        lines.append(f"\nAgent 状态（{len(agent_states)} 个）：")
        for a in agent_states:
            branch_tag = f"[{a.get('branch_id', 'main')}] " if not branch_id else ""
            lines.append(f"  {branch_tag}实体 {a.get('entity_id', '?')}：{_pretty_json(a.get('state_json'))}")

    events = state.get("recent_events", [])
    if events:
        lines.append(f"\n近期事件（{len(events)} 条）：")
        for e in events:
            branch_tag = f"[{e.get('branch_id', 'main')}] " if not branch_id else ""
            lines.append(
                f"  {branch_tag}步骤 {e.get('step', '?')}：{e.get('title', '无标题')}"
                f" — {e.get('summary', '')}"
            )

    return "\n".join(lines)


def _list_worldline_branches(params: dict, project_id: str) -> str:
    session_id = params["session_id"]
    engine = get_engine()
    with engine.connect() as conn:
        rows = conn.execute(
            select(worldline_branches).where(
                and_(
                    worldline_branches.c.session_id == session_id,
                    worldline_branches.c.project_id == project_id,
                )
            ).order_by(worldline_branches.c.created_at)
        ).fetchall()
        branches = [dict(r._mapping) for r in rows]
    if not branches:
        return f"会话 {session_id} 暂无分支数据"
    lines = [f"会话 {session_id} 共有 {len(branches)} 个分支："]
    for b in branches:
        lines.append(
            f"  [{b.get('branch_id')}] {b.get('title', '无标题')}"
            f" — 核心变化：{b.get('core_change', '无')}"
            f" | 步数：{b.get('current_step', 0)}"
            f" | 状态：{b.get('status', '未知')}"
        )
        agents_json = b.get("key_agents_json", "[]")
        try:
            agents = json.loads(agents_json) if isinstance(agents_json, str) else agents_json
            if agents:
                lines.append(f"    关键角色：{'、'.join(str(a) for a in agents)}")
        except Exception:
            pass
    return "\n".join(lines)


def _get_branch_timeline(params: dict, project_id: str) -> str:
    session_id = params["session_id"]
    branch_id = params["branch_id"]
    limit = params.get("limit", 20)
    engine = get_engine()
    with engine.connect() as conn:
        rows = conn.execute(
            select(world_events).where(
                and_(
                    world_events.c.session_id == session_id,
                    world_events.c.branch_id == branch_id,
                )
            ).order_by(world_events.c.step.asc()).limit(limit)
        ).fetchall()
        events = [dict(r._mapping) for r in rows]
    if not events:
        return f"分支 {branch_id} 暂无事件"
    lines = [f"分支 {branch_id} 时间线（{len(events)} 条事件）："]
    for e in events:
        lines.append(
            f"  步骤 {e.get('step', '?')}：{e.get('title', '无标题')}"
            f" — {e.get('summary', '')}"
        )
        etype = e.get("event_type", "")
        if etype:
            lines.append(f"    类型：{etype} | 状态：{e.get('status', '未知')}")
    return "\n".join(lines)


def _get_branch_agent_state(params: dict, project_id: str) -> str:
    session_id = params["session_id"]
    branch_id = params["branch_id"]
    entity_id = params.get("entity_id")
    engine = get_engine()
    clauses = [
        agent_states.c.session_id == session_id,
        agent_states.c.branch_id == branch_id,
    ]
    if entity_id:
        clauses.append(agent_states.c.entity_id == entity_id)
    with engine.connect() as conn:
        rows = conn.execute(
            select(agent_states).where(and_(*clauses))
        ).fetchall()
        states = [dict(r._mapping) for r in rows]
    if not states:
        target = f"实体 {entity_id}" if entity_id else "所有实体"
        return f"分支 {branch_id} 中 {target} 暂无状态数据"
    lines = [f"分支 {branch_id} Agent 状态（{len(states)} 个）："]
    for a in states:
        lines.append(f"  实体 {a.get('entity_id', '?')}：{_pretty_json(a.get('state_json'))}")
    return "\n".join(lines)


_STATUS_LABELS = {"open": "未解决", "progressed": "进行中", "resolved": "已解决"}


def _format_entity_names(entities: list[dict]) -> str:
    """Format a list of entity dicts into a compact 'Name(type)' string."""
    parts = []
    for e in entities:
        name = e.get("name", "?")
        etype = e.get("entity_type", "")
        parts.append(f"{name}({etype})" if etype else name)
    return "、".join(parts)


def _get_open_threads(params: dict, project_id: str) -> str:
    up_to_chapter = params["up_to_chapter"]
    repos = _get_repos()
    threads = repos["thread"].get_open_threads(project_id, up_to_chapter=up_to_chapter)
    if not threads:
        return f"截至第 {up_to_chapter} 章，暂无未解决的伏笔线索"

    lines = [f"截至第 {up_to_chapter} 章的伏笔线索（{len(threads)} 条）："]
    for i, t in enumerate(threads, 1):
        if isinstance(t, dict):
            status = t.get("status", "open")
            label = _STATUS_LABELS.get(status, status)
            key = t.get("thread_key", "")
            detail = t.get("detail", "")
            text = f"[{label}] {key}"
            if detail:
                text += f" — {detail}"
            lines.append(f"{i}. {text}")
            # Reverse link: show entities involved in this thread
            thread_id = t.get("thread_id")
            if thread_id:
                ents = repos["thread"].get_thread_entities(project_id, thread_id, limit=5)
                if ents:
                    lines.append(f"   涉及实体：{_format_entity_names(ents)}")
        else:
            lines.append(f"{i}. {t}")
    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Manuscript tool executors
# ---------------------------------------------------------------------------


def _get_manuscript_context(params: dict, project_id: str) -> str:
    from .manuscript_context_builder import build_continuation_context
    token_budget = params.get("token_budget", 8000)
    last_block_id = params.get("last_block_id") or None
    ctx = build_continuation_context(project_id, token_budget, last_block_id=last_block_id)

    if not ctx.get("recent_summaries") and not ctx.get("tail_text"):
        return "稿件尚无已提交内容"

    lines: list[str] = []
    lines.append(f"稿件概况：{ctx['total_blocks']}段，{ctx['total_words']}字")

    if ctx.get("last_pov"):
        lines.append(f"上一段 POV：{ctx['last_pov']}")
    if ctx.get("last_location"):
        lines.append(f"上一段地点：{ctx['last_location']}")
    if ctx.get("narrative_note"):
        lines.append(f"叙事状态：{ctx['narrative_note']}")

    if ctx.get("recent_summaries"):
        lines.append("\n--- 近期段落摘要 ---")
        for s in ctx["recent_summaries"]:
            label = s.get("chapter_tag") or ""
            tag = f" [{label}]" if label else ""
            lines.append(f"第{s['block_order']}段{tag}：{s['summary']}")

    if ctx.get("active_threads"):
        lines.append("\n--- 活跃伏笔 ---")
        for i, t in enumerate(ctx["active_threads"], 1):
            lines.append(f"{i}. {t}")

    if ctx.get("tail_text"):
        lines.append("\n--- 原文尾部 ---")
        lines.append(ctx["tail_text"])

    return "\n".join(lines)


def _search_manuscript(params: dict, project_id: str) -> str:
    query = params["query"]
    limit = params.get("limit", 10)
    # Use the manuscript adapter (still backed by assets table) for FTS
    from .manuscript_context_builder import _get_manuscript_adapter
    adapter = _get_manuscript_adapter(project_id)
    results = adapter.search_fts(query, limit=limit)
    if not results:
        return f"稿件中未找到与「{query}」相关的内容"

    lines = [f"稿件搜索「{query}」结果（{len(results)}条）："]
    for i, r in enumerate(results, 1):
        label = r.get("chapter_title") or r.get("chapter_tag") or ""
        tag = f" [{label}]" if label else ""
        lines.append(f"{i}. 第{r['block_order']}段{tag}（{r['word_count']}字）")
        if r.get("snippet"):
            lines.append(f"   {r['snippet']}")
    return "\n".join(lines)


def _get_manuscript_stats(params: dict, project_id: str) -> str:
    from .manuscript_context_builder import _get_manuscript_adapter
    adapter = _get_manuscript_adapter(project_id)
    stats = adapter.stats()
    lines = [
        f"稿件统计：",
        f"总段落数：{stats['total_blocks']}",
        f"总字数：{stats['total_words']}",
    ]
    if stats.get("chapters"):
        ch_labels = [f"第{ch['chapter_order']}章·{ch['title']}({ch['block_count']}段)" for ch in stats["chapters"]]
        lines.append(f"章节：{', '.join(ch_labels)}")
    elif stats.get("chapter_tags"):
        lines.append(f"章节标签：{', '.join(stats['chapter_tags'])}")
    else:
        lines.append("尚未标注章节")
    return "\n".join(lines)


# ---------------------------------------------------------------------------
# New tools: voice, timelines, threads, world rules
# ---------------------------------------------------------------------------

def _get_character_voice(inp: dict, project_id: str) -> str:
    name = inp.get("name", "")
    repos = _get_repos()
    entity = repos["entity"].get_entity_by_name(project_id, name)
    if not entity:
        return f"未找到角色 {name}"
    lines = [f"【角色语言风格】{entity.get('name', name)}"]
    if entity.get("speech_style"):
        lines.append(f"说话风格：{entity['speech_style']}")
    if entity.get("personality_traits_json"):
        try:
            traits = json.loads(entity["personality_traits_json"])
            if traits:
                lines.append(f"性格特征：{'、'.join(traits)}")
        except Exception:
            pass
    if entity.get("verbal_habits_json"):
        try:
            habits = json.loads(entity["verbal_habits_json"])
            if habits:
                lines.append(f"口头禅/语气：{'、'.join(habits)}")
        except Exception:
            pass
    if entity.get("example_quotes_json"):
        try:
            quotes = json.loads(entity["example_quotes_json"])
            if quotes:
                lines.append("经典台词/内心戏：")
                for q in quotes[:8]:
                    lines.append(f"  「{q}」")
        except Exception:
            pass
    if entity.get("core_drive"):
        lines.append(f"核心驱动：{entity['core_drive']}")
    if entity.get("hidden_tension"):
        lines.append(f"内在矛盾：{entity['hidden_tension']}")
    # Also fetch entity_evidence quotes
    try:
        engine = get_engine()
        with engine.connect() as conn:
            evs = conn.execute(
                select(entity_evidence.c.snippet).where(
                    entity_evidence.c.owner_id == entity.get("entity_id", "")
                ).limit(10)
            ).fetchall()
            if evs:
                lines.append("原文引用：")
                for ev in evs:
                    lines.append(f"  「{ev.snippet}」")
    except Exception:
        pass
    return "\n".join(lines)


def _query_relationship_timeline(inp: dict, project_id: str) -> str:
    a_name = inp.get("entity_a", "")
    b_name = inp.get("entity_b", "")
    repos = _get_repos()
    a = repos["entity"].get_entity_by_name(project_id, a_name)
    b = repos["entity"].get_entity_by_name(project_id, b_name)
    if not a or not b:
        missing = a_name if not a else b_name
        return f"未找到角色 {missing}"
    a_id = a.get("entity_id", "")
    b_id = b.get("entity_id", "")

    engine = get_engine()
    with engine.connect() as conn:
        rows = conn.execute(
            select(relationship_events).where(
                and_(
                    relationship_events.c.project_id == project_id,
                    or_(
                        and_(
                            relationship_events.c.source_entity_id == a_id,
                            relationship_events.c.target_entity_id == b_id,
                        ),
                        and_(
                            relationship_events.c.source_entity_id == b_id,
                            relationship_events.c.target_entity_id == a_id,
                        ),
                        and_(
                            relationship_events.c.source_entity_id == a_name,
                            relationship_events.c.target_entity_id == b_name,
                        ),
                        and_(
                            relationship_events.c.source_entity_id == b_name,
                            relationship_events.c.target_entity_id == a_name,
                        ),
                    ),
                )
            ).order_by(
                relationship_events.c.chapter_order,
                relationship_events.c.segment_id,
            )
        ).fetchall()
        results = [dict(r._mapping) for r in rows]

    if not results:
        return f"未找到 {a_name} 与 {b_name} 之间的关系事件"
    lines = [f"【关系时间线】{a_name} ↔ {b_name}（共 {len(results)} 条事件）"]
    for r in results:
        parts = []
        if r.get("segment_id"):
            parts.append(f"[{r['segment_id']}]")
        if r.get("relation_type"):
            parts.append(f"关系: {r['relation_type']}")
        if r.get("trigger_event"):
            parts.append(f"触发: {r['trigger_event']}")
        if r.get("evidence"):
            parts.append(f"证据: {r['evidence']}")
        if r.get("emotional_shift"):
            parts.append(f"情感: {r['emotional_shift']}")
        if r.get("power_shift"):
            parts.append(f"权力: {r['power_shift']}")
        lines.append("  " + " | ".join(parts))

    # Append current relationship state
    from ...tables.novel import relationships as rel_tbl
    with engine.connect() as conn:
        rel_rows = conn.execute(
            select(rel_tbl).where(
                and_(
                    rel_tbl.c.project_id == project_id,
                    or_(
                        and_(rel_tbl.c.source_id == a_id, rel_tbl.c.target_id == b_id),
                        and_(rel_tbl.c.source_id == b_id, rel_tbl.c.target_id == a_id),
                    ),
                )
            )
        ).fetchall()
        rels = [dict(r._mapping) for r in rel_rows]
    if rels:
        lines.append("当前关系状态：")
        for rel in rels:
            lines.append(f"  {rel.get('relation_type', '?')}：{rel.get('description', '')}")
    return "\n".join(lines)


def _query_character_timeline(inp: dict, project_id: str) -> str:
    name = inp.get("name", "")
    event_type = inp.get("event_type", "all")
    limit = inp.get("limit", 20)
    repos = _get_repos()
    entity = repos["entity"].get_entity_by_name(project_id, name)
    entity_id = entity.get("entity_id", name) if entity else name

    engine = get_engine()
    clauses = [
        character_events.c.project_id == project_id,
        character_events.c.entity_id == entity_id,
    ]
    if event_type and event_type != "all":
        clauses.append(character_events.c.event_type == event_type)

    with engine.connect() as conn:
        rows = conn.execute(
            select(character_events).where(and_(*clauses))
            .order_by(character_events.c.chapter_order, character_events.c.segment_id)
            .limit(limit)
        ).fetchall()
        results = [dict(r._mapping) for r in rows]

    if not results:
        return f"未找到 {name} 的事件记录"
    lines = [f"【角色时间线】{name}（共 {len(results)} 条事件）"]
    for r in results:
        prefix = f"[{r['event_type']}]" if r.get("event_type") else ""
        seg = f" ({r['segment_id']})" if r.get("segment_id") else ""
        lines.append(f"  {prefix} {r['summary']}{seg}")
    return "\n".join(lines)


def _query_thread_history(inp: dict, project_id: str) -> str:
    thread_key = inp.get("thread_key", "")
    repos = _get_repos()
    engine = get_engine()

    # Try thread_lifecycle table first
    with engine.connect() as conn:
        rows = conn.execute(
            select(thread_lifecycle).where(
                and_(
                    thread_lifecycle.c.project_id == project_id,
                    thread_lifecycle.c.thread_key.like(f"%{thread_key}%"),
                )
            ).order_by(thread_lifecycle.c.chapter_order, thread_lifecycle.c.segment_id)
        ).fetchall()
        lifecycle_results = [dict(r._mapping) for r in rows]

    if not lifecycle_results:
        # Also check plot_threads table
        with engine.connect() as conn:
            pt_rows = conn.execute(
                select(plot_threads).where(
                    and_(
                        plot_threads.c.project_id == project_id,
                        or_(
                            plot_threads.c.thread_key.like(f"%{thread_key}%"),
                            plot_threads.c.detail.like(f"%{thread_key}%"),
                        ),
                    )
                )
            ).fetchall()
            pt_results = [dict(r._mapping) for r in pt_rows]

        if not pt_results:
            return f"未找到与「{thread_key}」相关的伏笔线索"
        lines = [f"【伏笔线索】匹配到 {len(pt_results)} 条"]
        for r in pt_results:
            lines.append(f"  [{r['status']}] {r['thread_key']}：{r['detail']}")
            tid = r.get("thread_id")
            if tid:
                ents = repos["thread"].get_thread_entities(project_id, tid, limit=5)
                if ents:
                    lines.append(f"    关联实体：{_format_entity_names(ents)}")
        return "\n".join(lines)

    lines = [f"【伏笔生命周期】{thread_key}（共 {len(lifecycle_results)} 条记录）"]
    for r in lifecycle_results:
        parts = [f"[{r['status']}]", r.get("detail") or ""]
        if r.get("resolution_detail"):
            parts.append(f"解决方式: {r['resolution_detail']}")
        if r.get("segment_id"):
            parts.append(f"({r['segment_id']})")
        lines.append("  " + " ".join(p for p in parts if p))
    return "\n".join(lines)


def _search_world_rules(inp: dict, project_id: str) -> str:
    query = inp.get("query", "")
    limit = inp.get("limit", 10)
    repos = _get_repos()
    engine = get_engine()

    like_pattern = f"%{query}%"
    results: list[dict] = []
    with engine.connect() as conn:
        rows = conn.execute(
            select(world_rule_evidence).where(
                and_(
                    world_rule_evidence.c.project_id == project_id,
                    or_(
                        world_rule_evidence.c.fact_text.like(like_pattern),
                        world_rule_evidence.c.evidence_snippet.like(like_pattern),
                    ),
                )
            ).limit(limit)
        ).fetchall()
        results = [dict(r._mapping) for r in rows]

    if not results:
        # Also search agent_memory world_rules
        with engine.connect() as conn:
            mem_rows = conn.execute(
                select(agent_memory.c.summary, agent_memory.c.detail_json).where(
                    and_(
                        agent_memory.c.memory_type == "world_rule",
                        agent_memory.c.summary.like(like_pattern),
                    )
                ).limit(limit)
            ).fetchall()
            if mem_rows:
                lines = [f"搜索「{query}」世界观规则（{len(mem_rows)} 条）："]
                for r in mem_rows:
                    lines.append(f"  规则：{r.summary}")
                return "\n".join(lines)
        return f"未找到与「{query}」相关的世界观规则"

    lines = [f"搜索「{query}」世界观规则（{len(results)} 条）："]
    for r in results:
        lines.append(f"  规则：{r['fact_text']}")
        if r.get("evidence_snippet"):
            lines.append(f"    证据：{r['evidence_snippet']}")
        eid = r.get("evidence_id")
        if eid:
            ents = repos["world_rule"].get_rule_entities(project_id, eid, limit=5)
            if ents:
                lines.append(f"    关联实体：{_format_entity_names(ents)}")
    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Write tool executors
# ---------------------------------------------------------------------------


def _manage_entity(params: dict, project_id: str) -> str:
    action = params.get("action", "")
    name = params.get("name", "")
    if not name:
        return "缺少必填参数 name"

    repos = _get_repos()

    if action == "create":
        entity_type = params.get("entity_type")
        summary = params.get("summary")
        if not entity_type or not summary:
            return "创建实体需要提供 entity_type 和 summary"
        kwargs: dict[str, Any] = {}
        for key in ("core_drive", "hidden_tension", "current_objective", "importance_tier",
                    "ultimate_goal", "surface_mask", "values_text", "fears_text",
                    "decision_pattern", "agent_behavior_hint"):
            if params.get(key):
                kwargs[key] = params[key]
        if params.get("aliases"):
            kwargs["aliases"] = params["aliases"]
        try:
            result = repos["entity"].create_entity(project_id, name, entity_type, summary, **kwargs)
        except ValueError as e:
            return str(e)
        return f"已创建实体「{name}」（{entity_type}），ID: {result['entity_id']}"

    elif action == "update":
        kwargs = {}
        for key in ("summary", "core_drive", "hidden_tension", "current_objective",
                     "entity_type", "importance_tier",
                     "ultimate_goal", "surface_mask", "values_text", "fears_text",
                     "decision_pattern", "agent_behavior_hint"):
            if params.get(key) is not None:
                kwargs[key] = params[key]
        if params.get("aliases"):
            kwargs["aliases"] = params["aliases"]
        if not kwargs:
            return "未提供任何更新字段"
        ok = repos["entity"].update_entity_by_name(project_id, name, **kwargs)
        if not ok:
            return f"未找到实体「{name}」，无法更新。如需新建请使用 action='create'"
        return f"已更新实体「{name}」的设定"

    return f"未知操作：{action}，请使用 create 或 update"


def _manage_thread(params: dict, project_id: str) -> str:
    action = params.get("action", "")
    thread_key = params.get("thread_key", "")
    if not thread_key:
        return "缺少必填参数 thread_key"

    repos = _get_repos()

    if action == "create":
        detail = params.get("detail", "")
        chapter_order = params.get("chapter_order", 0)
        result = repos["thread"].create_thread(project_id, thread_key, detail, chapter_order=chapter_order)
        return f"已创建伏笔「{thread_key}」，ID: {result['thread_id']}"

    elif action == "update":
        status = params.get("status")
        detail = params.get("detail")
        resolution = params.get("resolution_detail")
        chapter_order = params.get("chapter_order", 0)
        try:
            ok = repos["thread"].update_thread(
                project_id, thread_key, status=status, detail=detail,
                resolution_detail=resolution, chapter_order=chapter_order,
            )
        except ValueError as e:
            return str(e)
        if not ok:
            return f"未找到伏笔「{thread_key}」，如需新建请使用 action='create'"
        status_note = f"，状态→{status}" if status else ""
        return f"已更新伏笔「{thread_key}」{status_note}"

    return f"未知操作：{action}，请使用 create 或 update"


def _manage_world_rule(params: dict, project_id: str) -> str:
    fact_text = params.get("fact_text", "")
    if not fact_text:
        return "缺少必填参数 fact_text"
    snippet = params.get("evidence_snippet", "")
    chapter_order = params.get("chapter_order", 0)
    try:
        result = _create_or_update_world_rule(project_id, fact_text, snippet, chapter_order)
    except Exception as e:
        return f"世界规则写入失败：{e}"
    verb = "更新" if result.get("updated") else "记录"
    return f"已{verb}世界规则：{fact_text}"


def _create_or_update_world_rule(
    project_id: str, fact_text: str, evidence_snippet: str = "", chapter_order: int = 0,
) -> dict[str, Any]:
    """Create a world rule or update if fact_text already exists. Inline replacement for NovelDB method."""
    engine = get_engine()
    now = _now()
    with engine.connect() as conn:
        existing = conn.execute(
            select(world_rule_evidence.c.evidence_id).where(
                and_(
                    world_rule_evidence.c.fact_text == fact_text,
                    world_rule_evidence.c.project_id == project_id,
                )
            )
        ).fetchone()
        if existing:
            eid = existing.evidence_id
            conn.execute(
                update(world_rule_evidence).where(
                    world_rule_evidence.c.evidence_id == eid
                ).values(evidence_snippet=evidence_snippet, chapter_order=chapter_order)
            )
            updated = True
        else:
            eid = f"wre_{uuid.uuid4().hex[:12]}"
            conn.execute(
                insert(world_rule_evidence).values(
                    evidence_id=eid,
                    project_id=project_id,
                    fact_text=fact_text,
                    evidence_snippet=evidence_snippet,
                    chapter_order=chapter_order,
                    created_at=now,
                )
            )
            updated = False

        # Auto-link entities mentioned in the text
        text = f"{fact_text} {evidence_snippet}"
        for entity_id in _link_entities_for_text(conn, project_id, text):
            from ...tables.novel import rule_entity_links
            conn.execute(
                insert(rule_entity_links).prefix_with("OR IGNORE").values(
                    project_id=project_id,
                    evidence_id=eid,
                    entity_id=entity_id,
                    relevance="constrains",
                    created_at=now,
                )
            )
        conn.commit()
    return {"evidence_id": eid, "fact_text": fact_text, "updated": updated}


def _link_entities_for_text(conn, project_id: str, text: str) -> list[str]:
    """Scan text for known entity names/aliases and return matched entity_ids."""
    matched: list[str] = []
    seen: set[str] = set()
    for row in conn.execute(
        select(entities.c.entity_id, entities.c.name).where(
            entities.c.project_id == project_id
        )
    ).fetchall():
        name = row.name
        if name and len(name) >= 2 and name in text and row.entity_id not in seen:
            matched.append(row.entity_id)
            seen.add(row.entity_id)
    for row in conn.execute(
        select(entity_aliases.c.entity_id, entity_aliases.c.alias).select_from(
            entity_aliases.join(entities, entity_aliases.c.entity_id == entities.c.entity_id)
        ).where(entities.c.project_id == project_id)
    ).fetchall():
        alias = row.alias
        if alias and len(alias) >= 2 and alias in text and row.entity_id not in seen:
            matched.append(row.entity_id)
            seen.add(row.entity_id)
    return matched


def _manage_relationship(params: dict, project_id: str) -> str:
    a = params.get("entity_a", "")
    b = params.get("entity_b", "")
    rel_type = params.get("relation_type", "")
    if not a or not b or not rel_type:
        return "缺少必填参数：entity_a、entity_b、relation_type"
    kwargs: dict[str, Any] = {}
    for k in ("description", "trust_level", "power_dynamic", "conflict_trigger"):
        if params.get(k) is not None:
            kwargs[k] = params[k]
    try:
        result = _create_or_update_relationship(project_id, a, b, rel_type, **kwargs)
    except ValueError as e:
        return str(e)
    verb = "更新" if result.get("updated") else "创建"
    return f"已{verb}关系：{a} ↔ {b}（{rel_type}）"


def _create_or_update_relationship(
    project_id: str, source_name: str, target_name: str, relation_type: str, **kwargs: Any,
) -> dict[str, Any]:
    """Create or update a relationship between two entities. Inline replacement for NovelDB method."""
    from ...tables.novel import relationships as rel_tbl

    repos = _get_repos()
    source_id = repos["entity"].resolve_entity_id(project_id, source_name)
    if not source_id:
        raise ValueError(f"未找到实体「{source_name}」")
    target_id = repos["entity"].resolve_entity_id(project_id, target_name)
    if not target_id:
        raise ValueError(f"未找到实体「{target_name}」")

    now = _now()
    engine = get_engine()
    writable = {"description", "trust_level", "power_dynamic", "history", "conflict_trigger"}
    extras = {k: v for k, v in kwargs.items() if k in writable and v is not None}
    prev_relation_type = ""

    with engine.connect() as conn:
        row = conn.execute(
            select(rel_tbl.c.relation_id, rel_tbl.c.relation_type).where(
                and_(
                    rel_tbl.c.project_id == project_id,
                    or_(
                        and_(rel_tbl.c.source_id == source_id, rel_tbl.c.target_id == target_id),
                        and_(rel_tbl.c.source_id == target_id, rel_tbl.c.target_id == source_id),
                    ),
                )
            )
        ).fetchone()

        if row:
            rid = row.relation_id
            prev_relation_type = row.relation_type or ""
            up: dict[str, Any] = {"relation_type": relation_type, "updated_at": now}
            up.update(extras)
            conn.execute(
                update(rel_tbl).where(rel_tbl.c.relation_id == rid).values(**up)
            )
            updated = True
        else:
            rid = f"rel_{uuid.uuid4().hex[:12]}"
            conn.execute(
                insert(rel_tbl).values(
                    relation_id=rid,
                    project_id=project_id,
                    source_id=source_id,
                    target_id=target_id,
                    relation_type=relation_type,
                    description=extras.get("description", ""),
                    trust_level=extras.get("trust_level"),
                    power_dynamic=extras.get("power_dynamic", ""),
                    conflict_trigger=extras.get("conflict_trigger", ""),
                    updated_at=now,
                )
            )
            updated = False

        # Auto-record a relationship_event for timeline tracking
        event_id = f"re_{uuid.uuid4().hex[:12]}"
        conn.execute(
            insert(relationship_events).values(
                event_id=event_id,
                project_id=project_id,
                source_entity_id=source_id,
                target_entity_id=target_id,
                segment_id="",
                chapter_order=0,
                relation_type=relation_type,
                previous_state=prev_relation_type if updated else "",
                new_state=relation_type,
                trigger_event=extras.get("description", ""),
                emotional_shift="",
                power_shift=extras.get("power_dynamic", ""),
                evidence=extras.get("conflict_trigger", ""),
                created_at=now,
            )
        )
        conn.commit()
    return {
        "relation_id": rid,
        "source": source_name,
        "target": target_name,
        "updated": updated,
    }


def _record_character_event(params: dict, project_id: str) -> str:
    name = params.get("name", "")
    if not name:
        return "缺少必填参数 name"
    event_type = params.get("event_type", "action")
    summary = params.get("summary", "")
    if not summary:
        return "缺少必填参数 summary"
    chapter_order = params.get("chapter_order", 0)

    repos = _get_repos()
    entity = repos["entity"].get_entity_by_name(project_id, name)
    if not entity:
        return f"未找到角色「{name}」"
    entity_id = entity.get("entity_id", name)

    event_id = f"ce_{uuid.uuid4().hex[:12]}"
    now = _now()
    engine = get_engine()
    with engine.connect() as conn:
        conn.execute(
            insert(character_events).values(
                event_id=event_id,
                project_id=project_id,
                entity_id=entity_id,
                segment_id="",
                chapter_order=chapter_order,
                event_type=event_type,
                summary=summary,
                detail_json="{}",
                created_at=now,
            )
        )
        conn.commit()
    return f"已记录角色事件：{name} [{event_type}] {summary}（ID: {event_id}）"


def _get_story_overview(params: dict, project_id: str) -> str:
    repos = _get_repos()
    lines: list[str] = []

    meta = repos["narrative"].get_project_meta(project_id)
    if meta:
        lines.append(f"【叙事阶段】{meta.get('narrative_phase') or '未知'}")
        lines.append(f"【总段落数】{meta.get('total_segments', 0)}")

    if params.get("include_arcs", True):
        arcs = repos["narrative"].list_narrative_arcs(project_id)
        if arcs:
            lines.append(f"\n【叙事弧线】共 {len(arcs)} 条")
            for a in arcs:
                segs = json.loads(a.get("covered_segments_json", "[]"))
                seg_info = f"（覆盖 {len(segs)} 段）" if segs else ""
                lines.append(f"  - {a['arc_id']}: {a['summary']}{seg_info}")

    if params.get("include_volumes", True):
        vols = repos["narrative"].list_volume_summaries(project_id)
        if vols:
            lines.append(f"\n【卷册摘要】共 {len(vols)} 卷")
            for v in vols:
                lines.append(f"  - 第{v['volume_order'] + 1}卷: {v['summary']}")

    return "\n".join(lines) if lines else "未找到故事概览数据"


def _query_segment_summaries(params: dict, project_id: str) -> str:
    repos = _get_repos()
    segment_ids = params.get("segment_ids")
    offset = params.get("offset", 0)
    limit = params.get("limit", 30)

    summaries = repos["narrative"].list_segment_summaries(
        project_id, segment_ids, offset=offset, limit=limit,
    )
    lines: list[str] = [f"【逐段摘要】共返回 {len(summaries)} 条"]
    for s in summaries:
        lines.append(f"\n[{s['segment_id']}] (序号 {s['segment_order']})")
        lines.append(s["summary"])

    if params.get("include_consistency_notes", True):
        notes = repos["narrative"].list_consistency_notes(project_id)
        if notes:
            lines.append(f"\n【一致性注释】共 {len(notes)} 条")
            for n in notes:
                lines.append(f"  - [{n['segment_id']}] {n['note_text']}")

    return "\n".join(lines) if summaries else "未找到段落摘要数据"


def _get_story_ontology(params: dict, project_id: str) -> str:
    proj_dir = os.path.join(Config.UPLOAD_FOLDER, "projects", project_id)
    proj_path = os.path.join(proj_dir, "project.json")
    if not os.path.isfile(proj_path):
        return "未找到项目本体论数据"
    with open(proj_path, encoding="utf-8") as f:
        project = json.load(f)
    ontology = project.get("ontology", {})
    if not ontology:
        return "未找到本体论定义"
    kind = params.get("kind", "all")
    lines: list[str] = []

    if kind in ("entity_type", "all"):
        for et in ontology.get("entity_types", []):
            attrs = ", ".join(a.get("name", "") for a in et.get("attributes", []))
            lines.append(f"【实体类型】{et.get('name', '')}: {et.get('description', '')}")
            if attrs:
                lines.append(f"  属性: {attrs}")

    if kind in ("edge_type", "all"):
        for et in ontology.get("edge_types", []):
            attrs = ", ".join(a.get("name", "") for a in et.get("attributes", []))
            lines.append(f"【关系类型】{et.get('name', '')}: {et.get('description', '')}")
            if attrs:
                lines.append(f"  属性: {attrs}")

    return "\n".join(lines) if lines else "未找到本体论定义"


# ---------------------------------------------------------------------------
# Executor registry
# ---------------------------------------------------------------------------

# ---------------------------------------------------------------------------
# Asset library executors
# ---------------------------------------------------------------------------


def _get_assets_service():
    from ..assets.assets_service import AssetsService
    return AssetsService()


def _format_asset_brief(a: dict) -> str:
    parts = [
        f"[{a['asset_id']}] {a.get('title', '')}",
        f"  类型：{a.get('asset_type', '')}",
    ]
    if a.get("category"):
        parts.append(f"  分类：{a['category']}")
    if a.get("summary"):
        parts.append(f"  摘要：{a['summary']}")
    if a.get("snippet"):
        parts.append(f"  片段：{a['snippet']}")
    parts.append(f"  scope：{a.get('scope', '')}  enabled：{a.get('enabled')}")
    return "\n".join(parts)


def _search_assets(params: dict, project_id: str) -> str:
    from ..assets.global_search_indexer import MIN_QUERY_CHARS, QueryTooShort
    query = (params.get("query") or "").strip()
    if len(query) < MIN_QUERY_CHARS:
        return f"search_assets 需要 query ≥ {MIN_QUERY_CHARS} 字符（当前 {len(query)}）"
    asset_type = params.get("asset_type") or None
    category = params.get("category")
    scope = params.get("scope") or "all"
    limit = int(params.get("limit") or 10)
    svc = _get_assets_service()
    try:
        if scope == "global":
            hits = svc.search(query, scope="global", asset_type=asset_type, category=category, limit=limit)
        elif scope == "project":
            hits = svc.search(query, scope="project", project_id=project_id, asset_type=asset_type, category=category, limit=limit)
        else:
            hits = svc.search_merged(query, project_id=project_id, asset_type=asset_type, category=category, limit=limit)
    except QueryTooShort as exc:
        return f"search_assets query 不合法：{exc}"
    if not hits:
        return f"未在资产库中找到与“{query}”相关的已启用资产"
    return f"找到 {len(hits)} 条资产：\n\n" + "\n\n".join(_format_asset_brief(a) for a in hits)


def _get_asset(params: dict, project_id: str) -> str:
    aid = params.get("asset_id") or ""
    if not aid:
        return "get_asset 需要 asset_id"
    svc = _get_assets_service()
    asset = svc.find(aid, project_id=project_id)
    if not asset:
        return f"未找到资产：{aid}"
    if not asset.get("enabled"):
        return f"资产 {aid} 处于禁用状态，请创作者先在资产库中启用后再调用"
    lines = [
        f"# {asset.get('title', '')}",
        f"asset_id: {asset['asset_id']}",
        f"类型：{asset.get('asset_type', '')}  分类：{asset.get('category', '') or '无'}",
        f"scope：{asset.get('scope', '')}",
    ]
    if asset.get("summary"):
        lines.append(f"\n摘要：{asset['summary']}")
    if asset.get("content"):
        lines.append(f"\n正文：\n{asset['content']}")
    payload = asset.get("payload") or {}
    if payload:
        lines.append("\n结构化数据：\n" + json.dumps(payload, ensure_ascii=False, indent=2))
    tags = asset.get("tags") or []
    if tags:
        lines.append(f"\n标签：{', '.join(tags)}")
    return "\n".join(lines)


def _list_assets(params: dict, project_id: str) -> str:
    asset_type = params.get("asset_type") or ""
    if not asset_type:
        return "list_assets 需要 asset_type"
    category = params.get("category")
    scope = params.get("scope") or "all"
    limit = int(params.get("limit") or 30)
    svc = _get_assets_service()
    if scope == "global":
        rows = svc.list(scope="global", asset_type=asset_type, category=category, enabled_only=True, limit=limit)
    elif scope == "project":
        rows = svc.list(scope="project", project_id=project_id, asset_type=asset_type, category=category, enabled_only=True, limit=limit)
    else:
        rows = svc.list_merged(project_id=project_id, asset_type=asset_type, category=category, enabled_only=True, limit=limit)
    if not rows:
        return f"暂无 {asset_type} 类型的已启用资产"
    return f"共 {len(rows)} 条 {asset_type}：\n\n" + "\n\n".join(_format_asset_brief(a) for a in rows)


# ----------------------------------------------------------------------
# Unified / cross-silo tools
# ----------------------------------------------------------------------


def _global_search(params: dict, project_id: str) -> str:
    from ..assets.global_search_indexer import (
        GlobalSearchIndexer,
        MIN_QUERY_CHARS,
        QueryTooShort,
    )
    query = (params.get("query") or "").strip()
    if len(query) < MIN_QUERY_CHARS:
        return f"global_search 需要 query ≥ {MIN_QUERY_CHARS} 字符（当前 {len(query)}）"
    # source 接受 list（新 schema）或逗号分隔字符串（向后兼容旧调用约定）。
    sources: list[str] | None = None
    raw_src = params.get("source")
    if isinstance(raw_src, list):
        sources = [str(s).strip() for s in raw_src if str(s).strip()]
    elif isinstance(raw_src, str) and raw_src.strip():
        sources = [s.strip() for s in raw_src.split(",") if s.strip()]
    limit = min(int(params.get("limit") or 20), 100)
    indexer = GlobalSearchIndexer()
    # 不再懒重建——索引由各 silo 写入端实时维护。query 不合法直接抛。
    try:
        hits = indexer.search(query, project_id=project_id, sources=sources, limit=limit)
    except QueryTooShort as exc:
        return f"global_search query 不合法：{exc}"
    if not hits:
        return f"未在全局索引中找到与“{query}”相关的条目"
    lines = [f"找到 {len(hits)} 条："]
    for h in hits:
        lines.append(
            f"- [{h['source']}] {h['title']}  ({h['entity_type']})\n"
            f"    ref: {h['source_ref']}\n"
            f"    {h.get('snippet') or h.get('summary') or ''}"
        )
    return "\n".join(lines)


def _query_graph_neighbors(params: dict, project_id: str) -> str:
    from app.database import get_engine as _get_engine
    from app.repositories.graph_repo import GraphRepository as _GraphRepo
    name = (params.get("name") or "").strip()
    if not name:
        return "query_graph_neighbors 需要 name"
    limit = int(params.get("limit") or 20)
    repo = _GraphRepo(_get_engine())
    if not repo.has_graph(project_id):
        return f"项目 {project_id} 暂无故事图谱"
    from sqlalchemy import text as _text
    with repo.engine.connect() as conn:
        # 1) find node by exact name or alias
        node_row = conn.execute(
            _text("SELECT * FROM graph_nodes WHERE project_id = :pid AND name = :name LIMIT 1"),
            {"pid": project_id, "name": name},
        ).mappings().first()
        if not node_row:
            alias_row = conn.execute(
                _text("SELECT node_uuid FROM graph_aliases WHERE project_id = :pid AND alias = :name LIMIT 1"),
                {"pid": project_id, "name": name},
            ).mappings().first()
            if alias_row:
                node_row = conn.execute(
                    _text("SELECT * FROM graph_nodes WHERE project_id = :pid AND uuid = :uuid"),
                    {"pid": project_id, "uuid": alias_row["node_uuid"]},
                ).mappings().first()
        if not node_row:
            return f"故事图谱中未找到节点：{name}"

        node_uuid = node_row["uuid"]
        edges = conn.execute(
            _text(
                "SELECT * FROM graph_edges WHERE project_id = :pid "
                "AND (source_node_uuid = :uuid OR target_node_uuid = :uuid) "
                "ORDER BY weight DESC LIMIT :lim"
            ),
            {"pid": project_id, "uuid": node_uuid, "lim": limit},
        ).mappings().all()
        # gather neighbor info
        neighbor_uuids = set()
        for e in edges:
            other = e["target_node_uuid"] if e["source_node_uuid"] == node_uuid else e["source_node_uuid"]
            neighbor_uuids.add(other)
        neighbor_map = {}
        if neighbor_uuids:
            placeholders = ",".join(f":u{i}" for i in range(len(neighbor_uuids)))
            bind = {"pid": project_id}
            bind.update({f"u{i}": u for i, u in enumerate(neighbor_uuids)})
            for n in conn.execute(
                _text(f"SELECT uuid, name, summary FROM graph_nodes WHERE project_id = :pid AND uuid IN ({placeholders})"),
                bind,
            ).mappings().all():
                neighbor_map[n["uuid"]] = (n["name"], n["summary"])

    lines = [f"# 节点：{node_row['name']}", f"摘要：{node_row['summary'] or '(无)'}", "", f"## 邻居 / 关系（{len(edges)} 条）"]
    for e in edges:
        other_uuid = e["target_node_uuid"] if e["source_node_uuid"] == node_uuid else e["source_node_uuid"]
        other_name, other_summary = neighbor_map.get(other_uuid, ("?", ""))
        direction = "→" if e["source_node_uuid"] == node_uuid else "←"
        lines.append(
            f"- {direction} {other_name} ({e['name']}, weight={e['weight']})\n"
            f"    fact: {e['fact']}\n"
            f"    对端摘要: {other_summary[:120] if other_summary else ''}"
        )
    return "\n".join(lines)


def _query_event(params: dict, project_id: str) -> str:
    import json as _json
    from app.database import get_engine as _get_engine
    from app.repositories.graph_repo import GraphRepository as _GraphRepo
    event_id = (params.get("event_id") or "").strip()
    name = (params.get("name") or "").strip()
    limit = max(1, min(int(params.get("limit") or 5), 20))
    if not event_id and not name:
        return "query_event 需要 event_id 或 name 之一"
    repo = _GraphRepo(_get_engine())
    if not repo.has_graph(project_id):
        return f"项目 {project_id} 暂无故事图谱"
    from sqlalchemy import text as _text
    with repo.engine.connect() as conn:
        # Filter to PlotEvent label via graph_node_labels join
        rows = conn.execute(
            _text(
                "SELECT n.* FROM graph_nodes n "
                "JOIN graph_node_labels l ON l.project_id = n.project_id AND l.node_uuid = n.uuid "
                "WHERE n.project_id = :pid AND l.label IN ('PlotEvent', 'Conflict') "
                "ORDER BY n.name LIMIT 500"
            ),
            {"pid": project_id},
        ).mappings().all()

    matches: list[dict] = []
    for r in rows:
        try:
            attrs = _json.loads(r["attributes_json"]) if r["attributes_json"] else {}
        except _json.JSONDecodeError:
            attrs = {}
        if event_id:
            if str(attrs.get("event_id", "")) != event_id:
                continue
        elif name:
            if name not in (r["name"] or "") and name not in (r["summary"] or ""):
                continue
        try:
            evidence = _json.loads(r["evidence_refs_json"]) if r["evidence_refs_json"] else []
        except _json.JSONDecodeError:
            evidence = []
        matches.append({
            "uuid": r["uuid"],
            "name": r["name"],
            "summary": r["summary"],
            "attrs": attrs,
            "evidence": evidence,
        })
        if len(matches) >= limit:
            break

    if not matches:
        target = event_id or name
        return f"未找到事件：{target}"
    lines = [f"找到 {len(matches)} 条事件："]
    for m in matches:
        attrs = m["attrs"]
        lines.append(f"\n## {m['name']}")
        if attrs.get("event_id"):
            lines.append(f"event_id: {attrs['event_id']}")
        if attrs.get("kind"):
            lines.append(f"类型: {attrs['kind']}")
        if attrs.get("arc_id"):
            lines.append(f"所属弧线: {attrs['arc_id']}")
        if attrs.get("chapter_id"):
            lines.append(f"章节: {attrs['chapter_id']}")
        participants = attrs.get("participants") or []
        if participants:
            lines.append(f"参与者: {', '.join(participants)}")
        if m["summary"]:
            lines.append(f"描述: {m['summary']}")
        if attrs.get("consequence"):
            lines.append(f"影响: {attrs['consequence']}")
        for ev in (m["evidence"] or [])[:2]:
            snippet = ev.get("snippet") if isinstance(ev, dict) else str(ev)
            if snippet:
                lines.append(f"佐证: {snippet}")
    return "\n".join(lines)


def _has_table(conn, name: str) -> bool:
    return conn.execute(
        "SELECT 1 FROM sqlite_master WHERE type='table' AND name=?", (name,)
    ).fetchone() is not None


def _query_relationship_network(params: dict, project_id: str) -> str:
    from app.database import get_engine as _get_engine
    from app.repositories.graph_repo import GraphRepository as _GraphRepo
    name = (params.get("name") or "").strip()
    if not name:
        return "query_relationship_network 需要 name"
    limit = max(1, min(int(params.get("limit") or 30), 100))
    repo = _GraphRepo(_get_engine())
    if not repo.has_graph(project_id):
        return f"项目 {project_id} 暂无故事图谱"
    from sqlalchemy import text as _text
    with repo.engine.connect() as conn:
        node_row = conn.execute(
            _text("SELECT * FROM graph_nodes WHERE project_id = :pid AND name = :name LIMIT 1"),
            {"pid": project_id, "name": name},
        ).mappings().first()
        if not node_row:
            alias_row = conn.execute(
                _text("SELECT node_uuid FROM graph_aliases WHERE project_id = :pid AND alias = :name LIMIT 1"),
                {"pid": project_id, "name": name},
            ).mappings().first()
            if alias_row:
                node_row = conn.execute(
                    _text("SELECT * FROM graph_nodes WHERE project_id = :pid AND uuid = :uuid"),
                    {"pid": project_id, "uuid": alias_row["node_uuid"]},
                ).mappings().first()
        if not node_row:
            return f"故事图谱中未找到节点：{name}"
        node_uuid = node_row["uuid"]
        # Restrict to character/organization/faction neighbors via label join when available
        edges = conn.execute(
            _text(
                "SELECT * FROM graph_edges "
                "WHERE project_id = :pid AND (source_node_uuid = :uuid OR target_node_uuid = :uuid) "
                "ORDER BY weight DESC LIMIT :lim"
            ),
            {"pid": project_id, "uuid": node_uuid, "lim": limit * 2},
        ).mappings().all()
        neighbor_uuids = set()
        for e in edges:
            other = e["target_node_uuid"] if e["source_node_uuid"] == node_uuid else e["source_node_uuid"]
            neighbor_uuids.add(other)
        neighbor_map: dict[str, dict] = {}
        if neighbor_uuids:
            placeholders = ",".join(f":u{i}" for i in range(len(neighbor_uuids)))
            bind = {"pid": project_id}
            bind.update({f"u{i}": u for i, u in enumerate(neighbor_uuids)})
            for n in conn.execute(
                _text(
                    f"SELECT n.uuid, n.name, n.summary, "
                    f"  (SELECT GROUP_CONCAT(label) FROM graph_node_labels "
                    f"   WHERE project_id = :pid AND node_uuid = n.uuid) AS labels "
                    f"FROM graph_nodes n WHERE n.project_id = :pid AND n.uuid IN ({placeholders})"
                ),
                bind,
            ).mappings().all():
                neighbor_map[n["uuid"]] = {
                    "name": n["name"],
                    "summary": n["summary"],
                    "labels": (n["labels"] or "").split(","),
                }

    # Filter to character-like neighbors
    person_labels = {"Character", "Organization", "Faction", "Group"}
    filtered = []
    for e in edges:
        other_uuid = e["target_node_uuid"] if e["source_node_uuid"] == node_uuid else e["source_node_uuid"]
        info = neighbor_map.get(other_uuid)
        if not info:
            continue
        if not (set(info["labels"]) & person_labels):
            continue
        filtered.append((e, info, other_uuid))
        if len(filtered) >= limit:
            break

    if not filtered:
        return f"# {node_row['name']}\n暂无角色关系网络"
    lines = [
        f"# {node_row['name']} 的关系网络（{len(filtered)} 条）",
        f"摘要: {node_row['summary'] or '(无)'}",
        "",
    ]
    for e, info, other_uuid in filtered:
        direction = "→" if e["source_node_uuid"] == node_uuid else "←"
        lines.append(
            f"- {direction} {info['name']}  [{e['name']}, weight={e['weight']}]"
        )
        if e["fact"]:
            lines.append(f"    事实: {e['fact']}")
    return "\n".join(lines)


def _query_worldline_session(params: dict, project_id: str) -> str:
    import os as _os
    import json as _json
    from ...config import Config
    sid = (params.get("session_id") or "").strip()
    sessions_dir = _os.path.join(
        Config.UPLOAD_FOLDER, "projects", project_id, "worldlines", "sessions"
    )
    if not _os.path.isdir(sessions_dir):
        return f"项目 {project_id} 暂无世界线推演记录"
    files = [f for f in _os.listdir(sessions_dir) if f.endswith(".json")]
    if not files:
        return "暂无世界线 session"
    if sid:
        target = sid + ".json"
        if target not in files:
            return f"未找到 session: {sid}"
        chosen = target
    else:
        # 取最近修改
        files.sort(key=lambda f: _os.path.getmtime(_os.path.join(sessions_dir, f)), reverse=True)
        chosen = files[0]
    path = _os.path.join(sessions_dir, chosen)
    try:
        with open(path, "r", encoding="utf-8") as fp:
            data = _json.load(fp)
    except (OSError, _json.JSONDecodeError) as exc:
        return f"读取 session 失败: {exc}"

    chosen_id = chosen.removesuffix(".json")
    lines = [
        f"# 世界线 Session: {chosen_id}",
        f"标题: {data.get('title') or '(无)'}",
        f"描述: {data.get('description') or data.get('summary') or '(无)'}",
        f"更新时间: {data.get('updated_at') or '(未知)'}",
    ]
    variables = data.get("variables") or data.get("world_variables") or {}
    if variables:
        lines.append("\n## 世界变量")
        lines.append(_json.dumps(variables, ensure_ascii=False, indent=2)[:1200])
    agents = data.get("agents") or data.get("participants") or []
    if agents:
        lines.append(f"\n## 参与角色（{len(agents)}）")
        for a in agents[:20]:
            if isinstance(a, dict):
                lines.append(f"- {a.get('name') or a.get('id') or '?'}")
    events = data.get("events") or data.get("event_log") or []
    if events:
        lines.append(f"\n## 最近事件（共 {len(events)}，截取最新 10 条）")
        for ev in events[-10:]:
            if isinstance(ev, dict):
                lines.append(f"- [{ev.get('step') or ev.get('time') or '?'}] {ev.get('summary') or ev.get('text') or ev.get('description') or ''}")
    return "\n".join(lines)


# ----------------------------------------------------------------------
# Book-run executors: word-count audit, forbidden-lexicon scan, splice/rewrite
# ----------------------------------------------------------------------

_SPLICE_MAX_DELTA_CHARS = 5000  # hard cap per single splice action
_REWRITE_MAX_DELTA_CHARS = 3000  # hard cap per single rewrite_span action
_SCAN_REGEX_TIMEOUT_SECONDS = 5


def _get_manuscript_adapter(project_id: str):
    from .manuscript_service import _get_adapter
    return _get_adapter(project_id)


def _block_chars(content: str | None) -> int:
    from ...utils.word_count import count_cjk_chars
    return count_cjk_chars(content)


def _get_chapter_word_stats(params: dict, project_id: str) -> str:
    chapter_id = params.get("chapter_id") or ""
    if not chapter_id:
        return "get_chapter_word_stats 需要 chapter_id"
    target = params.get("target_word_count")
    adapter = _get_manuscript_adapter(project_id)
    blocks = adapter.list_blocks(include_content=True, chapter_id=chapter_id)
    if not blocks:
        return f"章节 {chapter_id} 暂无已提交稿件块"
    lines: list[str] = []
    total = 0
    for b in blocks:
        c = _block_chars(b.get("content") or "")
        total += c
        preview = (b.get("content") or "").strip().replace("\n", " ")[:32]
        lines.append(
            f"- block_id={b['block_id']}  order={b.get('block_order')}  chars={c}  preview={preview!r}"
        )
    header = [f"章节 {chapter_id} 共 {len(blocks)} 块，总字数={total}"]
    if target is not None:
        try:
            target_int = int(target)
            diff = total - target_int
            pct = (diff / target_int * 100) if target_int else 0.0
            header.append(f"目标={target_int}，差值={diff:+d}（{pct:+.1f}%）")
        except (TypeError, ValueError):
            pass
    return "\n".join(header + [""] + lines)


def _load_forbidden_lexicon_entries(
    project_id: str, lexicon_asset_ids: list[str] | None
) -> list[dict]:
    """Load and normalize forbidden_lexicon entries from selected assets.

    Normalized entry shape: {
        id, pattern, match_type, category, severity, note,
        whitelist_contexts, asset_id, asset_title
    }
    """
    svc = _get_assets_service()
    if lexicon_asset_ids:
        assets: list[dict] = []
        for aid in lexicon_asset_ids:
            asset = svc.find(aid, project_id=project_id)
            if asset and asset.get("enabled") and asset.get("asset_type") == "forbidden_lexicon":
                assets.append(asset)
    else:
        assets = svc.list_merged(
            project_id=project_id,
            asset_type="forbidden_lexicon",
            enabled_only=True,
            limit=50,
        )
    out: list[dict] = []
    for asset in assets:
        payload = asset.get("payload") or {}
        raw_entries = payload.get("entries") or []
        for i, raw in enumerate(raw_entries):
            if isinstance(raw, str):
                norm = {"pattern": raw, "match_type": "literal"}
            elif isinstance(raw, dict):
                norm = dict(raw)
            else:
                continue
            if not norm.get("pattern"):
                continue
            out.append(
                {
                    "id": norm.get("id") or f"{asset['asset_id']}#{i}",
                    "pattern": norm["pattern"],
                    "match_type": (norm.get("match_type") or "literal").lower(),
                    "category": norm.get("category") or "word",
                    "severity": norm.get("severity") or "block",
                    "note": norm.get("note") or "",
                    "whitelist_contexts": norm.get("whitelist_contexts") or [],
                    "asset_id": asset["asset_id"],
                    "asset_title": asset.get("title") or "",
                }
            )
    return out


def _scan_forbidden_lexicon(params: dict, project_id: str) -> str:
    import re as _re
    import time as _time

    chapter_id = params.get("chapter_id") or ""
    block_ids = params.get("block_ids") or []
    lexicon_asset_ids = params.get("lexicon_asset_ids") or []

    adapter = _get_manuscript_adapter(project_id)
    if block_ids:
        blocks = []
        for bid in block_ids:
            b = adapter.get_block(bid)
            if b:
                blocks.append(b)
    elif chapter_id:
        blocks = adapter.list_blocks(include_content=True, chapter_id=chapter_id)
    else:
        return "scan_forbidden_lexicon 需要 chapter_id 或 block_ids"
    if not blocks:
        return "未找到待扫描的稿件块"

    entries = _load_forbidden_lexicon_entries(project_id, lexicon_asset_ids or None)
    if not entries:
        return "没有已启用的禁词资产（forbidden_lexicon），跳过扫描"

    deadline = _time.monotonic() + _SCAN_REGEX_TIMEOUT_SECONDS
    hits: list[dict] = []
    for entry in entries:
        pattern = entry["pattern"]
        match_type = entry["match_type"]
        try:
            if match_type == "regex":
                compiled = _re.compile(pattern)
            elif match_type == "phrase":
                compiled = _re.compile(_re.escape(pattern).replace(r"\ ", r"\s+"))
            else:
                compiled = None  # literal
        except _re.error as exc:
            hits.append(
                {
                    "block_id": None,
                    "error": f"正则 {pattern!r} 编译失败：{exc}",
                    "entry_id": entry["id"],
                }
            )
            continue
        for b in blocks:
            if _time.monotonic() > deadline:
                hits.append({"error": "扫描超时 5s，已中止（请精简正则规则）"})
                break
            content = b.get("content") or ""
            if compiled is None:
                start = 0
                while True:
                    idx = content.find(pattern, start)
                    if idx < 0:
                        break
                    hits.append(_format_hit(b, entry, idx, idx + len(pattern), pattern))
                    start = idx + max(len(pattern), 1)
            else:
                for m in compiled.finditer(content):
                    if _time.monotonic() > deadline:
                        break
                    hits.append(
                        _format_hit(b, entry, m.start(), m.end(), m.group(0))
                    )
        else:
            continue
        break  # timeout broke inner loop

    # Apply whitelist filter
    filtered: list[dict] = []
    for h in hits:
        if "error" in h:
            filtered.append(h)
            continue
        wls = h.get("whitelist_contexts") or []
        if wls and any(wl for wl in wls if wl in (h.get("context") or "")):
            continue
        filtered.append(h)

    if not filtered:
        return f"扫描完成，共比对 {len(entries)} 条规则，未命中任何禁词。"
    lines = [f"扫描完成，共比对 {len(entries)} 条规则，命中 {len(filtered)} 处："]
    for h in filtered[:80]:
        if "error" in h:
            lines.append(f"  [错误] {h['error']}")
            continue
        lines.append(
            f"- block={h['block_id']}(order={h['block_order']}) "
            f"match={h['match']!r}  [{h['match_type']}/{h['severity']}] "
            f"entry={h['entry_id']}  ctx={h['context']!r}"
        )
    if len(filtered) > 80:
        lines.append(f"... 另有 {len(filtered) - 80} 条命中省略")
    return "\n".join(lines)


def _format_hit(
    block: dict, entry: dict, start: int, end: int, matched: str
) -> dict:
    content = block.get("content") or ""
    ctx_start = max(0, start - 40)
    ctx_end = min(len(content), end + 40)
    return {
        "block_id": block["block_id"],
        "block_order": block.get("block_order"),
        "match": matched,
        "start": start,
        "end": end,
        "entry_id": entry["id"],
        "pattern": entry["pattern"],
        "match_type": entry["match_type"],
        "severity": entry["severity"],
        "asset_title": entry["asset_title"],
        "context": content[ctx_start:ctx_end].replace("\n", " "),
        "whitelist_contexts": entry.get("whitelist_contexts") or [],
    }


def _list_forbidden_lexicon(params: dict, project_id: str) -> str:
    include_entries = bool(params.get("include_entries"))
    svc = _get_assets_service()
    assets = svc.list_merged(
        project_id=project_id,
        asset_type="forbidden_lexicon",
        enabled_only=False,
        limit=50,
    )
    if not assets:
        return "暂无 forbidden_lexicon 类型资产"
    lines = [f"共 {len(assets)} 份禁词资产："]
    for a in assets:
        payload = a.get("payload") or {}
        entries = payload.get("entries") or []
        lines.append(
            f"- [{a['asset_id']}] {a.get('title', '')}  条目={len(entries)}  enabled={a.get('enabled')}  scope={a.get('scope')}"
        )
        if include_entries and entries:
            for i, e in enumerate(entries[:30]):
                if isinstance(e, str):
                    lines.append(f"    {i}. {e}  (literal)")
                elif isinstance(e, dict):
                    lines.append(
                        f"    {i}. {e.get('pattern', '?')}  "
                        f"[{e.get('match_type', 'literal')}/{e.get('category', 'word')}/{e.get('severity', 'block')}]"
                    )
            if len(entries) > 30:
                lines.append(f"    ... 另有 {len(entries) - 30} 条")
    return "\n".join(lines)


def _upsert_forbidden_lexicon(params: dict, project_id: str) -> str:
    asset_id = params.get("asset_id")
    title = (params.get("title") or "").strip()
    raw_entries = params.get("entries")
    if not isinstance(raw_entries, list):
        return "upsert_forbidden_lexicon 需要 entries 数组"
    normalized: list[dict] = []
    for raw in raw_entries:
        if isinstance(raw, str):
            if raw.strip():
                normalized.append({"pattern": raw.strip(), "match_type": "literal"})
        elif isinstance(raw, dict):
            if not raw.get("pattern"):
                continue
            normalized.append(
                {
                    "pattern": str(raw["pattern"]),
                    "match_type": (raw.get("match_type") or "literal").lower(),
                    "category": raw.get("category") or "word",
                    "severity": raw.get("severity") or "block",
                    "note": raw.get("note") or "",
                    "whitelist_contexts": raw.get("whitelist_contexts") or [],
                }
            )
    # Validate regex entries up-front
    import re as _re
    for e in normalized:
        if e["match_type"] == "regex":
            try:
                _re.compile(e["pattern"])
            except _re.error as exc:
                return f"禁词正则 {e['pattern']!r} 不合法：{exc}"

    svc = _get_assets_service()
    payload = {"entries": normalized}
    if asset_id:
        existing = svc.find(asset_id, project_id=project_id)
        if not existing:
            return f"未找到 asset_id={asset_id}"
        svc.update(
            asset_id,
            scope=existing.get("scope", "project"),
            project_id=existing.get("project_id"),
            title=title or existing.get("title") or "禁词表",
            payload=payload,
        )
        return f"已更新禁词资产 {asset_id}，共 {len(normalized)} 条规则"
    if not title:
        return "新建禁词资产必须提供 title"
    created = svc.create(
        scope="project",
        project_id=project_id,
        asset_type="forbidden_lexicon",
        title=title,
        summary=f"{len(normalized)} 条禁用规则",
        payload=payload,
        source_kind="writer_agent",
    )
    return f"已创建禁词资产 {created.get('asset_id')}，共 {len(normalized)} 条规则"


def _splice_block(params: dict, project_id: str) -> str:
    chapter_id = params.get("chapter_id") or ""
    anchor_block_id = params.get("anchor_block_id") or ""
    position = (params.get("position") or "").lower()
    content = params.get("content") or ""
    end_anchor = params.get("end_anchor_block_id")
    if not chapter_id or not anchor_block_id or not position:
        return "splice_block 需要 chapter_id / anchor_block_id / position"
    if position not in ("before", "after", "replace_range"):
        return f"position 必须是 before|after|replace_range，收到 {position!r}"
    if not content and position != "replace_range":
        return "splice_block 在 before/after 模式下 content 不能为空"

    new_chars = _block_chars(content)
    if new_chars > _SPLICE_MAX_DELTA_CHARS:
        return (
            f"splice_block 被拒绝：单次写入 {new_chars} 字超过上限 "
            f"{_SPLICE_MAX_DELTA_CHARS}，请拆分为多次调用"
        )

    adapter = _get_manuscript_adapter(project_id)
    anchor = adapter.get_block(anchor_block_id)
    if not anchor:
        return f"找不到锚点块 {anchor_block_id}"
    if anchor.get("chapter_id") != chapter_id:
        return f"锚点块不属于章节 {chapter_id}"

    reason = params.get("reason") or ""

    if position == "after":
        block = adapter.commit(
            content,
            insert_after_block_id=anchor_block_id,
            chapter_id=chapter_id,
        )
        return (
            f"已在 {anchor_block_id} 之后插入新块 {block['block_id']}"
            f"（字数={new_chars}，reason={reason!r}）"
        )

    if position == "before":
        blocks = adapter.list_blocks(include_content=False, chapter_id=chapter_id)
        blocks.sort(key=lambda b: b.get("block_order") or 0)
        prev_id = None
        for b in blocks:
            if b["block_id"] == anchor_block_id:
                break
            prev_id = b["block_id"]
        block = adapter.commit(
            content,
            insert_after_block_id=prev_id,
            chapter_id=chapter_id,
        )
        return (
            f"已在 {anchor_block_id} 之前插入新块 {block['block_id']}"
            f"（字数={new_chars}，reason={reason!r}）"
        )

    # replace_range
    if not end_anchor:
        end_anchor = anchor_block_id
    end_block = adapter.get_block(end_anchor)
    if not end_block or end_block.get("chapter_id") != chapter_id:
        return f"replace_range 的结束锚点 {end_anchor} 不合法"
    start_order = anchor.get("block_order") or 0
    end_order = end_block.get("block_order") or 0
    if end_order < start_order:
        return "end_anchor_block_id 的顺序必须 ≥ anchor_block_id"

    blocks = adapter.list_blocks(include_content=True, chapter_id=chapter_id)
    in_range = [
        b for b in blocks
        if (b.get("block_order") or 0) >= start_order
        and (b.get("block_order") or 0) <= end_order
    ]
    if not in_range:
        return "replace_range 区间内无块"
    old_chars = sum(_block_chars(b.get("content") or "") for b in in_range)
    delta = new_chars - old_chars
    if abs(delta) > _SPLICE_MAX_DELTA_CHARS:
        return (
            f"splice_block replace_range 被拒绝：净变化 {delta:+d} 字超过上限 "
            f"±{_SPLICE_MAX_DELTA_CHARS}"
        )

    adapter.update_block(anchor_block_id, content=content)
    removed: list[str] = []
    for b in in_range:
        if b["block_id"] == anchor_block_id:
            continue
        adapter.delete_block(b["block_id"])
        removed.append(b["block_id"])
    return (
        f"已替换区间：保留 {anchor_block_id} 并写入新正文（{old_chars} → {new_chars} 字，"
        f"净变化 {delta:+d}），删除 {len(removed)} 块：{removed}。reason={reason!r}"
    )


def _rewrite_span(params: dict, project_id: str) -> str:
    block_id = params.get("block_id") or ""
    original = params.get("original_text") or ""
    new_text = params.get("new_text") or ""
    reason = params.get("reason") or ""
    if not block_id or not original:
        return "rewrite_span 需要 block_id 和 original_text"

    old_chars = _block_chars(original)
    new_chars = _block_chars(new_text)
    if abs(new_chars - old_chars) > _REWRITE_MAX_DELTA_CHARS:
        return (
            f"rewrite_span 被拒绝：字数变化 {new_chars - old_chars:+d} 超过上限 "
            f"±{_REWRITE_MAX_DELTA_CHARS}"
        )

    adapter = _get_manuscript_adapter(project_id)
    block = adapter.get_block(block_id)
    if not block:
        return f"找不到 block_id={block_id}"
    content = block.get("content") or ""
    occurrences = content.count(original)
    if occurrences == 0:
        return (
            f"original_text 未出现在块 {block_id} 中，请先 get_manuscript_context "
            f"或 scan_forbidden_lexicon 核对实际文本"
        )
    if occurrences > 1:
        return (
            f"original_text 在块 {block_id} 中出现 {occurrences} 次（不唯一），"
            f"请扩展 original_text 使之唯一后重试"
        )
    updated = content.replace(original, new_text, 1)
    adapter.update_block(block_id, content=updated)
    return (
        f"已在 {block_id} 内完成 1 次替换"
        f"（{old_chars} → {new_chars} 字，reason={reason!r}）"
    )


_EXECUTORS: dict[str, Any] = {
    "query_entity": _query_entity,
    "query_relationship": _query_relationship,
    "query_chapter": _query_chapter,
    "query_scene": _query_scene,
    "search_settings": _search_settings,
    "get_recent_scenes": _get_recent_scenes,
    "get_world_state": _get_world_state,
    "list_worldline_branches": _list_worldline_branches,
    "get_branch_timeline": _get_branch_timeline,
    "get_branch_agent_state": _get_branch_agent_state,
    "get_open_threads": _get_open_threads,
    "get_manuscript_context": _get_manuscript_context,
    "search_manuscript": _search_manuscript,
    "get_manuscript_stats": _get_manuscript_stats,
    "get_character_voice": _get_character_voice,
    "query_relationship_timeline": _query_relationship_timeline,
    "query_character_timeline": _query_character_timeline,
    "query_thread_history": _query_thread_history,
    "search_world_rules": _search_world_rules,
    "get_story_overview": _get_story_overview,
    "query_segment_summaries": _query_segment_summaries,
    "get_story_ontology": _get_story_ontology,
    # Write tools
    "manage_entity": _manage_entity,
    "manage_thread": _manage_thread,
    "manage_world_rule": _manage_world_rule,
    "manage_relationship": _manage_relationship,
    "record_character_event": _record_character_event,
    # Asset library
    "search_assets": _search_assets,
    "get_asset": _get_asset,
    "list_assets": _list_assets,
    # Unified / cross-silo
    "global_search": _global_search,
    "query_graph_neighbors": _query_graph_neighbors,
    "query_event": _query_event,
    "query_relationship_network": _query_relationship_network,
    "query_worldline_session": _query_worldline_session,
    # Book-run (字数/禁词审计 + 段落编辑)
    "get_chapter_word_stats": _get_chapter_word_stats,
    "scan_forbidden_lexicon": _scan_forbidden_lexicon,
    "list_forbidden_lexicon": _list_forbidden_lexicon,
    "upsert_forbidden_lexicon": _upsert_forbidden_lexicon,
    "splice_block": _splice_block,
    "rewrite_span": _rewrite_span,
}
