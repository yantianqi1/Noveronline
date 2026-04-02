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

# ---------------------------------------------------------------------------
# Public entry point
# ---------------------------------------------------------------------------


def execute_tool(tool_name: str, tool_input: dict, project_id: str) -> str:
    """Execute a named tool.

    Returns a formatted string result, truncated to *TOOL_RESULT_MAX_CHARS*.
    """
    executor = _EXECUTORS.get(tool_name)
    if executor is None:
        return f"未知工具：{tool_name}"
    try:
        result = executor(tool_input, project_id)
    except Exception:
        logger.error("Tool %s execution failed:\n%s", tool_name, traceback.format_exc())
        result = f"工具 {tool_name} 执行出错：{traceback.format_exc()}"
    return result[:TOOL_RESULT_MAX_CHARS]


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
        return json.dumps(obj, ensure_ascii=False, indent=2)
    except (json.JSONDecodeError, TypeError):
        return raw


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
        f"详细设定：{_pretty_json(entity.get('profile_json')) or '无'}",
    ]
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


def _get_open_threads(params: dict, project_id: str) -> str:
    up_to_chapter = params["up_to_chapter"]
    threads = _db.get_open_threads(project_id, up_to_chapter)
    if not threads:
        return f"截至第 {up_to_chapter} 章，暂无未解决的伏笔线索"

    lines = [f"截至第 {up_to_chapter} 章的未解决伏笔（{len(threads)} 条）："]
    for i, t in enumerate(threads, 1):
        lines.append(f"{i}. {t}")
    return "\n".join(lines)


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
}
