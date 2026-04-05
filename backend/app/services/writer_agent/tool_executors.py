"""Tool executor implementations for the novel writer agent.

Each executor calls the corresponding ``NovelDB`` method and formats
the result as readable text for the LLM.
"""

from __future__ import annotations

import json
import logging
import traceback
from typing import Any

from .novel_db import NovelDB

logger = logging.getLogger(__name__)

TOOL_RESULT_MAX_CHARS = 8000
_PRESERVE_HEAD = 3000
_PRESERVE_TAIL = 1500


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

_db = NovelDB()


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
    entity = _db.get_entity(project_id, name, entity_type)
    if entity is None:
        return f"未找到实体：{name}"

    lines = [
        f"【{entity.get('entity_type', '未知')}】{entity.get('name', name)}",
        f"重要性：{entity.get('importance_tier', '未知')}",
        f"概述：{entity.get('summary') or '无'}",
        f"核心驱动：{entity.get('core_drive') or '无'}",
        f"表面表现：{entity.get('surface_mask') or '无'}",
        f"内在矛盾：{entity.get('hidden_tension') or '无'}",
    ]

    # Structured personality & speech fields
    _append_if(lines, "说话风格", entity.get("speech_style"))
    _append_if(lines, "口头禅", _pretty_json(entity.get("verbal_habits_json")))
    _append_if(lines, "经典台词", _pretty_json(entity.get("example_quotes_json")))
    _append_if(lines, "性格特征", _pretty_json(entity.get("personality_traits_json")))
    _append_if(lines, "价值观", entity.get("values_text"))
    _append_if(lines, "恐惧", entity.get("fears_text"))
    _append_if(lines, "决策模式", entity.get("decision_pattern"))

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
        threads = _db.get_entity_threads(project_id, entity_id, limit=5)
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
        rules = _db.get_entity_rules(project_id, entity_id, limit=5)
        if rules:
            lines.append("\n【适用世界规则】")
            for r in rules:
                lines.append(f"  规则：{r.get('fact_text', '')}")
                snippet = r.get("evidence_snippet", "")
                if snippet:
                    lines.append(f"    证据：{snippet}")

        # --- Recent events ---
        events = _db.get_entity_recent_events(project_id, entity_id, limit=5)
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
    rels = _db.get_relationship(project_id, entity_a, entity_b)
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
    chapter = _db.get_chapter(project_id, chapter_order, include_content)
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

    if scene_order is not None:
        # Find the specific scene by chapter_id + scene_order
        scenes = _db.list_scenes(project_id, chapter_id)
        scene = None
        for s in scenes:
            if s.get("scene_order") == scene_order:
                scene = _db.get_scene(project_id, s["scene_id"])
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
        scenes = _db.list_scenes(project_id, chapter_id)
        if not scenes:
            return f"章节 {chapter_id} 暂无场景"
        lines = [f"章节 {chapter_id} 场景列表："]
        for s in scenes:
            lines.append(
                f"  [{s.get('scene_order', '?')}] {s.get('title') or '无标题'}"
                f" （{s.get('status', '未知')}，{s.get('word_count', 0)} 字）"
            )
        return "\n".join(lines)


def _search_settings(params: dict, project_id: str) -> str:
    query = params["query"]
    scope = params.get("scope", "all")
    limit = params.get("limit", 10)
    results = _db.search_fts(project_id, query, scope, limit)
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
    scenes = _db.get_recent_scenes(project_id, chapter_id, scene_order, count)
    if not scenes:
        return "没有找到前序场景"

    parts: list[str] = []
    for s in scenes:
        lines = [
            f"场景 {s.get('scene_order', '?')}：{s.get('title') or '无标题'}",
            s.get("content", ""),
        ]
        parts.append("\n".join(lines))
    return "\n---\n".join(parts)


def _get_world_state(params: dict, project_id: str) -> str:
    session_id = params["session_id"]
    entity_id = params.get("entity_id")
    state = _db.get_world_state(project_id, session_id, entity_id)

    lines: list[str] = []

    session = state.get("session")
    if session:
        lines.append(f"会话：{session.get('title') or session_id}")
        lines.append(f"状态：{session.get('status', '未知')}")
        lines.append(f"类型：{session.get('session_type', '未知')}")
        focus = session.get("focus_question")
        if focus:
            lines.append(f"焦点问题：{focus}")
    else:
        lines.append(f"未找到会话：{session_id}")

    agent_states = state.get("agent_states", [])
    if agent_states:
        lines.append(f"\nAgent 状态（{len(agent_states)} 个）：")
        for a in agent_states:
            lines.append(f"  实体 {a.get('entity_id', '?')}：{_pretty_json(a.get('state_json'))}")

    events = state.get("recent_events", [])
    if events:
        lines.append(f"\n近期事件（{len(events)} 条）：")
        for e in events:
            lines.append(
                f"  步骤 {e.get('step', '?')}：{e.get('title', '无标题')}"
                f" — {e.get('summary', '')}"
            )

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
    threads = _db.get_open_threads(project_id, up_to_chapter)
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
                ents = _db.get_thread_entities(project_id, thread_id, limit=5)
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
    ctx = build_continuation_context(project_id, token_budget)

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
            tag = f" [{s['chapter_tag']}]" if s.get("chapter_tag") else ""
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
    results = _db.search_manuscript_fts(project_id, query, limit)
    if not results:
        return f"稿件中未找到与「{query}」相关的内容"

    lines = [f"稿件搜索「{query}」结果（{len(results)}条）："]
    for i, r in enumerate(results, 1):
        tag = f" [{r.get('chapter_tag')}]" if r.get("chapter_tag") else ""
        lines.append(f"{i}. 第{r['block_order']}段{tag}（{r['word_count']}字）")
        if r.get("snippet"):
            lines.append(f"   {r['snippet']}")
    return "\n".join(lines)


def _get_manuscript_stats(params: dict, project_id: str) -> str:
    stats = _db.get_manuscript_stats(project_id)
    lines = [
        f"稿件统计：",
        f"总段落数：{stats['total_blocks']}",
        f"总字数：{stats['total_words']}",
    ]
    if stats.get("chapter_tags"):
        lines.append(f"章节标签：{', '.join(stats['chapter_tags'])}")
    else:
        lines.append("尚未标注章节")
    return "\n".join(lines)


# ---------------------------------------------------------------------------
# New tools: voice, timelines, threads, world rules
# ---------------------------------------------------------------------------

def _get_character_voice(inp: dict, project_id: str) -> str:
    name = inp.get("name", "")
    entity = _db.get_entity(project_id, name)
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
        _db.ensure_schema(project_id)
        with _db.connect(project_id) as conn:
            evs = conn.execute(
                "SELECT snippet FROM entity_evidence WHERE owner_id = ? LIMIT 10",
                (entity.get("entity_id", ""),),
            ).fetchall()
            if evs:
                lines.append("原文引用：")
                for ev in evs:
                    lines.append(f"  「{ev['snippet']}」")
    except Exception:
        pass
    return "\n".join(lines)


def _query_relationship_timeline(inp: dict, project_id: str) -> str:
    a_name = inp.get("entity_a", "")
    b_name = inp.get("entity_b", "")
    a = _db.get_entity(project_id, a_name)
    b = _db.get_entity(project_id, b_name)
    if not a or not b:
        missing = a_name if not a else b_name
        return f"未找到角色 {missing}"
    a_id = a.get("entity_id", "")
    b_id = b.get("entity_id", "")
    _db.ensure_schema(project_id)
    with _db.connect(project_id) as conn:
        rows = conn.execute(
            """SELECT * FROM relationship_events
               WHERE project_id = ?
                 AND ((source_entity_id = ? AND target_entity_id = ?)
                   OR (source_entity_id = ? AND target_entity_id = ?))
               ORDER BY chapter_order, segment_id""",
            (project_id, a_id, b_id, b_id, a_id),
        ).fetchall()
    if not rows:
        # Try by name
        with _db.connect(project_id) as conn:
            rows = conn.execute(
                """SELECT * FROM relationship_events
                   WHERE project_id = ?
                     AND ((source_entity_id = ? AND target_entity_id = ?)
                       OR (source_entity_id = ? AND target_entity_id = ?))
                   ORDER BY chapter_order, segment_id""",
                (project_id, a_name, b_name, b_name, a_name),
            ).fetchall()
    if not rows:
        return f"未找到 {a_name} 与 {b_name} 之间的关系事件"
    lines = [f"【关系时间线】{a_name} ↔ {b_name}（共 {len(rows)} 条事件）"]
    for r in rows:
        parts = []
        if r["segment_id"]:
            parts.append(f"[{r['segment_id']}]")
        if r["relation_type"]:
            parts.append(f"关系: {r['relation_type']}")
        if r["trigger_event"]:
            parts.append(f"触发: {r['trigger_event']}")
        if r["evidence"]:
            parts.append(f"证据: {r['evidence']}")
        if r["emotional_shift"]:
            parts.append(f"情感: {r['emotional_shift']}")
        if r["power_shift"]:
            parts.append(f"权力: {r['power_shift']}")
        lines.append("  " + " | ".join(parts))
    # Append current relationship state
    rels = _db.get_relationship(project_id, a_name, b_name)
    if rels:
        lines.append("当前关系状态：")
        for rel in rels:
            lines.append(f"  {rel.get('relation_type', '?')}：{rel.get('description', '')}")
    return "\n".join(lines)


def _query_character_timeline(inp: dict, project_id: str) -> str:
    name = inp.get("name", "")
    event_type = inp.get("event_type", "all")
    limit = inp.get("limit", 20)
    entity = _db.get_entity(project_id, name)
    entity_id = entity.get("entity_id", name) if entity else name
    _db.ensure_schema(project_id)
    with _db.connect(project_id) as conn:
        if event_type and event_type != "all":
            rows = conn.execute(
                "SELECT * FROM character_events WHERE project_id = ? AND entity_id = ? AND event_type = ? ORDER BY chapter_order, segment_id LIMIT ?",
                (project_id, entity_id, event_type, limit),
            ).fetchall()
        else:
            rows = conn.execute(
                "SELECT * FROM character_events WHERE project_id = ? AND entity_id = ? ORDER BY chapter_order, segment_id LIMIT ?",
                (project_id, entity_id, limit),
            ).fetchall()
    if not rows:
        return f"未找到 {name} 的事件记录"
    lines = [f"【角色时间线】{name}（共 {len(rows)} 条事件）"]
    for r in rows:
        prefix = f"[{r['event_type']}]" if r["event_type"] else ""
        seg = f" ({r['segment_id']})" if r["segment_id"] else ""
        lines.append(f"  {prefix} {r['summary']}{seg}")
    return "\n".join(lines)


def _query_thread_history(inp: dict, project_id: str) -> str:
    thread_key = inp.get("thread_key", "")
    _db.ensure_schema(project_id)
    with _db.connect(project_id) as conn:
        rows = conn.execute(
            "SELECT * FROM thread_lifecycle WHERE project_id = ? AND thread_key LIKE ? ORDER BY chapter_order, segment_id",
            (project_id, f"%{thread_key}%"),
        ).fetchall()
    if not rows:
        # Also check plot_threads table
        with _db.connect(project_id) as conn:
            pt_rows = conn.execute(
                "SELECT * FROM plot_threads WHERE project_id = ? AND (thread_key LIKE ? OR detail LIKE ?)",
                (project_id, f"%{thread_key}%", f"%{thread_key}%"),
            ).fetchall()
        if not pt_rows:
            return f"未找到与「{thread_key}」相关的伏笔线索"
        lines = [f"【伏笔线索】匹配到 {len(pt_rows)} 条"]
        for r in pt_rows:
            lines.append(f"  [{r['status']}] {r['thread_key']}：{r['detail']}")
            try:
                tid = r["thread_id"]
            except (KeyError, IndexError):
                tid = None
            if tid:
                ents = _db.get_thread_entities(project_id, tid, limit=5)
                if ents:
                    lines.append(f"    关联实体：{_format_entity_names(ents)}")
        return "\n".join(lines)
    lines = [f"【伏笔生命周期】{thread_key}（共 {len(rows)} 条记录）"]
    for r in rows:
        parts = [f"[{r['status']}]", r["detail"] or ""]
        if r["resolution_detail"]:
            parts.append(f"解决方式: {r['resolution_detail']}")
        if r["segment_id"]:
            parts.append(f"({r['segment_id']})")
        lines.append("  " + " ".join(p for p in parts if p))
    return "\n".join(lines)


def _search_world_rules(inp: dict, project_id: str) -> str:
    query = inp.get("query", "")
    limit = inp.get("limit", 10)
    _db.ensure_schema(project_id)
    fts_param = _db._fts_match_param(query)
    results = []
    with _db.connect(project_id) as conn:
        try:
            rows = conn.execute(
                """SELECT wre.evidence_id, wre.fact_text, wre.evidence_snippet, wre.segment_id,
                          snippet(world_rule_evidence_fts, 0, '<b>', '</b>', '...', 48) AS snip
                   FROM world_rule_evidence_fts
                   JOIN world_rule_evidence wre ON wre.rowid = world_rule_evidence_fts.rowid
                   WHERE world_rule_evidence_fts MATCH ?
                   LIMIT ?""",
                (fts_param, limit),
            ).fetchall()
            for r in rows:
                results.append(r)
        except Exception:
            # Fallback to LIKE
            rows = conn.execute(
                "SELECT evidence_id, fact_text, evidence_snippet, segment_id FROM world_rule_evidence WHERE project_id = ? AND (fact_text LIKE ? OR evidence_snippet LIKE ?) LIMIT ?",
                (project_id, f"%{query}%", f"%{query}%", limit),
            ).fetchall()
            for r in rows:
                results.append(r)
    if not results:
        # Also search agent_memory world_rules
        with _db.connect(project_id) as conn:
            rows = conn.execute(
                "SELECT summary, detail_json FROM agent_memory WHERE memory_type = 'world_rule' AND summary LIKE ? LIMIT ?",
                (f"%{query}%", limit),
            ).fetchall()
            if rows:
                lines = [f"搜索「{query}」世界观规则（{len(rows)} 条）："]
                for r in rows:
                    lines.append(f"  规则：{r['summary']}")
                return "\n".join(lines)
        return f"未找到与「{query}」相关的世界观规则"
    lines = [f"搜索「{query}」世界观规则（{len(results)} 条）："]
    for r in results:
        lines.append(f"  规则：{r['fact_text']}")
        if r["evidence_snippet"]:
            lines.append(f"    证据：{r['evidence_snippet']}")
        try:
            eid = r["evidence_id"]
        except (KeyError, IndexError):
            eid = None
        if eid:
            ents = _db.get_rule_entities(project_id, eid, limit=5)
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

    if action == "create":
        entity_type = params.get("entity_type")
        summary = params.get("summary")
        if not entity_type or not summary:
            return "创建实体需要提供 entity_type 和 summary"
        kwargs: dict[str, Any] = {}
        for key in ("core_drive", "hidden_tension", "current_objective", "importance_tier"):
            if params.get(key):
                kwargs[key] = params[key]
        if params.get("aliases"):
            kwargs["aliases"] = params["aliases"]
        try:
            result = _db.create_entity(project_id, name, entity_type, summary, **kwargs)
        except ValueError as e:
            return str(e)
        return f"已创建实体「{name}」（{entity_type}），ID: {result['entity_id']}"

    elif action == "update":
        kwargs = {}
        for key in ("summary", "core_drive", "hidden_tension", "current_objective",
                     "entity_type", "importance_tier"):
            if params.get(key) is not None:
                kwargs[key] = params[key]
        if params.get("aliases"):
            kwargs["aliases"] = params["aliases"]
        if not kwargs:
            return "未提供任何更新字段"
        ok = _db.update_entity(project_id, name, **kwargs)
        if not ok:
            return f"未找到实体「{name}」，无法更新。如需新建请使用 action='create'"
        return f"已更���实体「{name}」的设定"

    return f"未知操作：{action}，请使用 create 或 update"


def _manage_thread(params: dict, project_id: str) -> str:
    action = params.get("action", "")
    thread_key = params.get("thread_key", "")
    if not thread_key:
        return "缺少必填参数 thread_key"

    if action == "create":
        detail = params.get("detail", "")
        chapter_order = params.get("chapter_order", 0)
        result = _db.create_thread(project_id, thread_key, detail, chapter_order=chapter_order)
        return f"已创建伏笔「{thread_key}」，ID: {result['thread_id']}"

    elif action == "update":
        status = params.get("status")
        detail = params.get("detail")
        resolution = params.get("resolution_detail")
        chapter_order = params.get("chapter_order", 0)
        try:
            ok = _db.update_thread(
                project_id, thread_key, status=status, detail=detail,
                resolution_detail=resolution, chapter_order=chapter_order,
            )
        except ValueError as e:
            return str(e)
        if not ok:
            return f"未找到伏���「{thread_key}」，如需新建请使用 action='create'"
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
        result = _db.create_or_update_world_rule(project_id, fact_text, snippet, chapter_order)
    except Exception as e:
        return f"世界规则写入失败：{e}"
    verb = "更新" if result.get("updated") else "记录"
    return f"已{verb}世界规则：{fact_text}"


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
        result = _db.create_or_update_relationship(
            project_id, a, b, rel_type, **kwargs,
        )
    except ValueError as e:
        return str(e)
    verb = "更新" if result.get("updated") else "创建"
    return f"已{verb}关系：{a} ↔ {b}（{rel_type}）"


# ---------------------------------------------------------------------------
# Executor registry
# ---------------------------------------------------------------------------

_EXECUTORS: dict[str, Any] = {
    "query_entity": _query_entity,
    "query_relationship": _query_relationship,
    "query_chapter": _query_chapter,
    "query_scene": _query_scene,
    "search_settings": _search_settings,
    "get_recent_scenes": _get_recent_scenes,
    "get_world_state": _get_world_state,
    "get_open_threads": _get_open_threads,
    "get_manuscript_context": _get_manuscript_context,
    "search_manuscript": _search_manuscript,
    "get_manuscript_stats": _get_manuscript_stats,
    "get_character_voice": _get_character_voice,
    "query_relationship_timeline": _query_relationship_timeline,
    "query_character_timeline": _query_character_timeline,
    "query_thread_history": _query_thread_history,
    "search_world_rules": _search_world_rules,
    # Write tools
    "manage_entity": _manage_entity,
    "manage_thread": _manage_thread,
    "manage_world_rule": _manage_world_rule,
    "manage_relationship": _manage_relationship,
}
