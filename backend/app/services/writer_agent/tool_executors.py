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
from typing import Any, TypedDict

from sqlalchemy import and_, insert, or_, select, update

from ...config import Config
from ...database import get_engine
from ...schemas.asset_types import AssetType
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


class ToolExecResultDict(TypedDict, total=False):
    """Executor return shape seen by ``AgentLoop``.

    Legacy executors return plain ``str``; ``execute_tool`` wraps those into
    ``{"result": truncated_str}``. New-style executors return this dict
    directly with an optional pre-serialised ``render`` payload dict.
    """

    result: str
    render: dict


def execute_tool(
    tool_name: str,
    tool_input: dict,
    project_id: str,
) -> ToolExecResultDict:
    """Execute a named tool.

    Always returns a dict. ``result`` is the truncated text the LLM sees;
    ``render`` (optional) is a UI-only payload already serialised by the
    executor (e.g. ``WordBudgetRender(...).model_dump(mode="json")``).
    Legacy executors that still return plain ``str`` are wrapped
    transparently so this change is backwards compatible.
    """
    executor = _EXECUTORS.get(tool_name)
    if executor is None:
        return {"result": f"未知工具：{tool_name}"}
    try:
        raw = executor(tool_input, project_id)
    except Exception:
        logger.error("Tool %s execution failed:\n%s", tool_name, traceback.format_exc())
        return {"result": f"工具 {tool_name} 执行出错：{traceback.format_exc()}"}

    # Back-compat: legacy executors still return plain str.
    if isinstance(raw, str):
        return {"result": _truncate_result(raw)}

    # New-style executors return a dict with {result, render?}. We only
    # truncate `result` — `render` is structured UI data the frontend needs
    # whole.
    if not isinstance(raw, dict):
        logger.warning(
            "Tool %s returned unexpected type %s; coercing via str()",
            tool_name,
            type(raw).__name__,
        )
        return {"result": _truncate_result(str(raw))}

    result_text = _truncate_result(str(raw.get("result", "")))
    out: ToolExecResultDict = {"result": result_text}
    render = raw.get("render")
    if render is not None:
        out["render"] = render
    return out


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
# Name resolution with fuzzy suggestions
# ---------------------------------------------------------------------------
#
# Problem: the seed pipeline populates `graph_nodes` + `archive_library` but
# leaves the `entities` table empty, and the project's own alias map
# (`graph_aliases`) isn't visible to `EntityRepository`. So a tool call like
# query_entity("白鲤") — where 白鲤 is a graph alias pointing to the canonical
# node "朱灵韵" — gets a hard "未找到" even though the data is right there.
# On top of that, name-query tools previously returned a flat "not found" with
# no hint of the canonical name, forcing the agent to give up.
#
# The resolver below unifies lookup across all real data sources and, on miss,
# surfaces up to 5 candidates via substring + single-char decomposition so the
# agent can self-correct without human intervention.

from dataclasses import dataclass, field  # noqa: E402


@dataclass
class NameResolveResult:
    entity: dict | None = None
    merged: Any | None = None
    graph_node: dict | None = None
    canonical_name: str | None = None
    matched_via: str = ""  # entity | entity_alias | archive | graph_node | graph_alias
    suggestions: list[dict] = field(default_factory=list)

    @property
    def found(self) -> bool:
        return (
            self.entity is not None
            or self.merged is not None
            or self.graph_node is not None
        )


def _lookup_graph_node_by_name(project_id: str, name: str) -> dict | None:
    """Find a graph node by name or alias. Returns {uuid, name, summary, matched_via} or None."""
    from ...repositories.graph_repo import GraphRepository

    return GraphRepository(get_engine()).lookup_node_by_name_or_alias(project_id, name)


def _gather_fuzzy_suggestions(
    project_id: str, name: str, limit: int = 5,
) -> list[dict]:
    """Collect fuzzy candidates via substring + single-char decomposition.

    Sources: graph_nodes.name, graph_aliases.alias, archive_library.entity_name.
    Ordered by importance_tier (protagonist/major first), deduped by canonical name.
    """
    from ...repositories.graph_repo import GraphRepository
    from ...tables.assets import assets as assets_table

    engine = get_engine()
    seen: set[str] = set()
    out: list[dict] = []

    # --- Graph sources (nodes + aliases + CJK single-char decomposition) ---
    # find_graph_candidates already dedups within the graph slice and applies
    # the same single-char decomposition rule; we just merge its payload into
    # our uniform shape.
    graph_repo = GraphRepository(engine)
    for cand in graph_repo.find_graph_candidates(project_id, name, limit=limit * 3):
        if cand["canonical_name"] in seen:
            continue
        seen.add(cand["canonical_name"])
        out.append(
            {
                "canonical_name": cand["canonical_name"],
                "source": cand["source"],
                "entity_type": "",
                "importance_tier": "",
                "summary": cand.get("summary", ""),
                "why": cand["why"],
            }
        )

    # --- Archive entities (merged into the assets table in P5) ---
    # This crosses repo boundaries, so we keep a targeted Core select here
    # rather than inflating AssetRepository with a narrow helper. Still
    # SQLAlchemy-typed — no raw text() strings.
    pattern = f"%{name}%"
    with engine.connect() as conn:
        archive_rows = conn.execute(
            select(
                assets_table.c.entity_name,
                assets_table.c.entity_type,
                assets_table.c.importance_tier,
            )
            .where(
                and_(
                    assets_table.c.project_id == project_id,
                    assets_table.c.asset_type == "archive_entity",
                    assets_table.c.entity_name.like(pattern),
                )
            )
            .limit(15)
        ).fetchall()

    for row in archive_rows:
        canonical = row.entity_name or ""
        if not canonical or canonical in seen:
            continue
        seen.add(canonical)
        out.append(
            {
                "canonical_name": canonical,
                "source": "archive",
                "entity_type": row.entity_type or "",
                "importance_tier": row.importance_tier or "",
                "summary": "",
                "why": f"档案库名字含「{name}」",
            }
        )

    tier_priority = {"protagonist": 0, "major": 1, "supporting": 2, "minor": 3}
    out.sort(key=lambda x: tier_priority.get(x.get("importance_tier") or "", 5))
    return out[:limit]


def _resolve_entity_fuzzy(
    project_id: str, name: str, entity_type: str | None = None,
) -> NameResolveResult:
    """Unified entity-name resolution across all project data sources.

    Precedence for a direct hit: entities > archive (merged) > graph_nodes.
    Alias hits get redirected to the canonical name; we then re-query the
    richer sources so the caller always gets the best available payload.
    On miss, gathers up to 5 fuzzy candidates for the agent to retry.
    """
    result = NameResolveResult()
    if not name:
        return result

    repos = _get_repos()
    engine = get_engine()

    # L1: entities / entity_aliases
    entity = repos["entity"].get_entity_by_name(project_id, name, entity_type)
    if entity:
        result.entity = entity
        result.canonical_name = entity.get("name") or name
        result.matched_via = "entity"

    # L2: archive / merged view
    try:
        from ..narrative_entity_service import NarrativeEntityService
        merged = NarrativeEntityService(engine).get_by_name(project_id, name)
        if merged is not None:
            result.merged = merged
            if not result.canonical_name:
                result.canonical_name = merged.name or name
                result.matched_via = "archive"
    except Exception:
        logger.warning("NarrativeEntityService merge failed for %s", name, exc_info=True)

    # L3: graph_nodes + graph_aliases
    node_info = _lookup_graph_node_by_name(project_id, name)
    if node_info:
        result.graph_node = node_info
        canonical = node_info["name"]
        if not result.canonical_name:
            result.canonical_name = canonical
            result.matched_via = node_info.get("matched_via", "graph_node")
        # Alias redirected to a new canonical name — re-hydrate entities/archive
        # so the caller gets the richer shape instead of a bare graph node.
        if canonical and canonical != name:
            if result.entity is None:
                hydrated = repos["entity"].get_entity_by_name(
                    project_id, canonical, entity_type,
                )
                if hydrated:
                    result.entity = hydrated
            if result.merged is None:
                try:
                    from ..narrative_entity_service import NarrativeEntityService
                    rehydrated = NarrativeEntityService(engine).get_by_name(
                        project_id, canonical,
                    )
                    if rehydrated is not None:
                        result.merged = rehydrated
                except Exception:
                    logger.warning(
                        "NarrativeEntityService rehydrate failed for %s",
                        canonical, exc_info=True,
                    )

    if result.found:
        return result

    # Miss: gather suggestions so the agent can retry a corrected name.
    result.suggestions = _gather_fuzzy_suggestions(project_id, name)
    return result


def _format_suggestions(name: str, suggestions: list[dict]) -> str:
    """Render a 'not found + did-you-mean' message that prods the agent to retry."""
    if not suggestions:
        return (
            f"未找到「{name}」，项目里也没有相似候选。\n"
            "可能原因：① 该名字是写作指令里的幻觉，并非项目真实存在的角色/实体；"
            "② 名字严重错别字。请先用 global_search 或 search_assets 确认；"
            "若确认是新角色，请调用 manage_entity(action='create') 先建档，再继续写作。"
        )
    lines = [f"未找到「{name}」。项目里相似候选如下，请用 query_entity 重试正确名字："]
    for s in suggestions:
        meta_parts = [x for x in (s.get("entity_type"), s.get("importance_tier")) if x]
        meta = f"（{'/'.join(meta_parts)}）" if meta_parts else ""
        head = f"  - {s['canonical_name']}{meta} [来源:{s.get('source', '')}]"
        lines.append(head)
        why = s.get("why", "")
        if why:
            lines.append(f"      命中原因：{why}")
        summary = s.get("summary") or ""
        if summary:
            lines.append(f"      简介：{summary}")
    lines.append(
        "注意：若以上候选都不是你想查的人，请用 global_search 再确认一次；"
        "若确认是全新角色，请用 manage_entity(action='create') 先建档——**不要直接放弃检索**。"
    )
    return "\n".join(lines)


def _format_graph_only(project_id: str, node: dict) -> str:
    """Fallback formatter when only a graph node exists (no entity/archive row)."""
    from ...repositories.graph_repo import GraphRepository

    node_uuid = node.get("uuid", "")
    lines = [
        f"【图谱节点】{node.get('name', '')}",
        f"概述：{node.get('summary') or '无'}",
    ]

    graph_repo = GraphRepository(get_engine())
    labels = graph_repo.get_node_labels(project_id, node_uuid, limit=8)
    if labels:
        lines.append(f"标签：{', '.join(labels)}")

    # get_neighbors_with_labels returns the edge + neighbor rollup already
    # ordered by weight DESC, so no extra post-processing needed.
    neighbors = graph_repo.get_neighbors_with_labels(project_id, node_uuid, limit=10)
    if neighbors:
        lines.append("\n【图谱关系】")
        for nb in neighbors:
            direction = "→" if nb["direction"] == "outgoing" else "←"
            line = (
                f"  {direction} {nb['neighbor_name']}"
                f"（{nb['edge_name']}, weight={nb['edge_weight']}）"
            )
            if nb["edge_fact"]:
                line += f"：{nb['edge_fact']}"
            lines.append(line)
    lines.append(
        "\n（注：此实体仅在故事图谱中存在，尚无结构化角色档案。"
        "写作时请结合上面的图谱关系推断具体设定。）"
    )
    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Individual executors
# ---------------------------------------------------------------------------


def _query_entity(params: dict, project_id: str) -> str:
    name = params["name"]
    entity_type = params.get("entity_type")
    section = (params.get("section") or "overview").strip().lower()
    if section not in {"overview", "profile", "relations", "events", "memories"}:
        return (
            f"query_entity section 参数非法：{section!r}。允许的值："
            "overview / profile / relations / events / memories。"
        )
    resolved = _resolve_entity_fuzzy(project_id, name, entity_type)

    if not resolved.found:
        return _format_suggestions(name, resolved.suggestions)

    entity = resolved.entity
    merged = resolved.merged
    graph_node = resolved.graph_node
    canonical = resolved.canonical_name or name

    # Note to agent when the query was resolved via alias/canonical remap,
    # so downstream tool calls can use the canonical name and not waste a
    # second round re-querying.
    header = ""
    if canonical != name:
        header = (
            f"注：你查的「{name}」已通过 {resolved.matched_via} 解析为「{canonical}」。"
            f"后续 query_relationship / query_character_timeline 等请直接用「{canonical}」。\n\n"
        )

    # Archive-only / graph-only fallbacks don't support paginated sections —
    # they don't have an entity row to hang section-specific data off, so we
    # return the same compact view regardless of section.
    if entity is None and merged is not None and merged.archive_id:
        body = _format_archive_only(merged)
        if section in {"relations", "events"}:
            body += (
                f"\n\n（section={section}：该实体仅存在于档案库，"
                "尚无 entities 行，因此无法返回 in-story 关系/事件。"
                "请用 query_relationship 或 search_settings 进一步查询。）"
            )
        elif section == "memories" and merged.archive_id:
            body += "\n\n" + _render_memory_section(merged.archive_id, params)
        return header + body

    if entity is None and merged is None and graph_node is not None:
        return header + _format_graph_only(project_id, graph_node) + (
            f"\n\n（section={section}：该实体仅存在于故事图谱，"
            "尚无结构化档案；请结合图谱邻居推断。）"
        )

    # Main path: entity row exists (optionally with merged archive).
    entity_id = entity.get("entity_id", "")
    if section == "overview":
        return header + _render_entity_overview(project_id, entity, merged, entity_id)
    if section == "profile":
        return header + _render_entity_profile(entity, merged)
    if section == "relations":
        return header + _render_entity_relations(project_id, entity, entity_id, params)
    if section == "events":
        return header + _render_entity_events(project_id, entity, entity_id, params)
    if section == "memories":
        archive_id = (merged.archive_id if merged is not None else None) or entity.get("archive_id")
        if not archive_id:
            return header + (
                f"【{entity.get('name', name)}】暂无 archive，无法查询长期记忆。"
                "请改用 section='overview' 或 section='profile'。"
            )
        return header + _render_memory_section(archive_id, params)

    # Shouldn't happen — guarded at top.
    return header + f"未知 section：{section}"


# ---------------------------------------------------------------------------
# query_entity section renderers
# ---------------------------------------------------------------------------


def _render_entity_overview(
    project_id: str, entity: dict, merged: Any, entity_id: str,
) -> str:
    """overview section: basics + aliases + labels + short summary.

    Deliberately compact — designed to be the first call the agent makes on
    every POV/involved character, so we keep it cheap.
    """
    lines: list[str] = [
        f"【{entity.get('entity_type', '未知')}】{entity.get('name', '')}（section=overview）",
        f"重要性：{entity.get('importance_tier', '未知')}",
    ]

    # aliases + labels via entity_repo.get_entity_with_details
    aliases: list[str] = []
    labels: list[str] = []
    if entity_id:
        try:
            repos = _get_repos()
            detailed = repos["entity"].get_entity_with_details(project_id, entity_id)
            if detailed:
                aliases = [a for a in detailed.get("aliases", []) if a and a != entity.get("name")]
                labels = list(detailed.get("labels", []))
        except Exception:
            logger.warning("get_entity_with_details failed for %s", entity_id, exc_info=True)

    if aliases:
        lines.append(f"别名：{'、'.join(aliases)}")
    if labels:
        lines.append(f"标签：{'、'.join(labels)}")
    _append_if(lines, "概述", entity.get("summary"))
    _append_if(lines, "核心驱动", entity.get("core_drive"))
    _append_if(lines, "表面表现", entity.get("surface_mask"))
    _append_if(lines, "内在矛盾", entity.get("hidden_tension"))
    _append_if(lines, "当前目标", entity.get("current_objective"))
    _append_if(lines, "终极目标", entity.get("ultimate_goal"))

    # Canon fields exclusive to archive
    if merged is not None and merged.canon_profile:
        cp = merged.canon_profile
        if cp.get("relationship_summary"):
            lines.append(f"正典·关系概述：{cp['relationship_summary']}")
        if cp.get("agent_behavior_hint"):
            lines.append(f"Agent 行为提示：{cp['agent_behavior_hint']}")

    lines.append("")
    lines.append(
        "（overview 只含基础字段。续取：section='profile' 拿长文档案，"
        "section='relations' 拿关系/伏笔/规则，section='events' 拿事件，"
        "section='memories' 拿 canon + candidate 记忆。）"
    )
    return "\n".join(lines)


def _render_entity_profile(entity: dict, merged: Any) -> str:
    """profile section: deep_profile_md + full structured personality fields."""
    lines: list[str] = [
        f"【{entity.get('entity_type', '未知')}】{entity.get('name', '')}（section=profile）",
    ]

    deep_profile = (entity.get("deep_profile_md") or "").strip()
    if deep_profile:
        lines.append("===== 角色长文档案（写作时必须严格遵守，下述行为禁区与语言禁忌优先级最高）=====")
        lines.append(deep_profile)
        lines.append("===== 长文档案结束 =====")
        lines.append("")
        lines.append("以下为补充结构化字段，与上面长文档案不一致时，以长文档案为准：")

    # Canon profile from archive (canon-exclusive fields only)
    if merged is not None and merged.canon_profile:
        cp = merged.canon_profile
        canon_lines: list[str] = []

        def _maybe(label: str, canon_val, entity_field: str | None = None) -> None:
            if not canon_val:
                return
            if entity_field and (entity.get(entity_field) or "") == canon_val:
                return
            canon_lines.append(f"{label}：{canon_val}")

        _maybe("身份定位", cp.get("entity_role"), "entity_role")
        _maybe("正典·核心驱动", cp.get("core_drive"), "core_drive")
        _maybe("正典·表面伪装", cp.get("surface_mask"), "surface_mask")
        _maybe("正典·深层张力", cp.get("hidden_tension"), "hidden_tension")
        if cp.get("relationship_summary"):
            canon_lines.append(f"正典·关系概述：{cp['relationship_summary']}")
        if cp.get("agent_behavior_hint"):
            canon_lines.append(f"Agent 行为提示：{cp['agent_behavior_hint']}")
        notable = _pretty_json(cp.get("notable_risks_json"))
        if notable:
            canon_lines.append(f"正典·风险清单：{notable}")

        if canon_lines:
            lines.append("")
            lines.append(
                "===== 正典档案（与 entity 同名字段已折叠，此处仅列 canon 独有或与 entity 不一致的部分）====="
            )
            lines.extend(canon_lines)
            lines.append("===== 正典档案结束 =====")

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

    _append_if(lines, "详细设定", _pretty_json(entity.get("profile_json")))

    # Character archetype refs
    if merged is not None and merged.archetype_refs:
        lines.append("\n【关联角色原型模板】")
        for ref in merged.archetype_refs[:5]:
            title = ref.get("title") or ref.get("asset_id") or ""
            summary = ref.get("summary") or ""
            scope = ref.get("scope") or ""
            scope_tag = f"({scope})" if scope else ""
            line = f"  · {title} {scope_tag}"
            if summary:
                line += f"：{summary}"
            lines.append(line)

    return "\n".join(lines)


def _render_entity_relations(
    project_id: str, entity: dict, entity_id: str, params: dict,
) -> str:
    """relations section: all bidirectional relationships + threads + world rules."""
    limit = max(1, min(int(params.get("limit") or 20), 100))
    lines: list[str] = [
        f"【{entity.get('name', '')}】关系网络（section=relations）",
    ]

    repos = _get_repos()

    rels = repos["relationship"].get_entity_relationships(
        project_id, entity_id, limit=limit,
    )
    if rels:
        # Pre-resolve opposite-end entity names
        other_ids = {
            r.get("target_id") if r.get("source_id") == entity_id else r.get("source_id")
            for r in rels
        }
        other_ids.discard(None)
        name_map: dict[str, str] = {}
        for oid in other_ids:
            if not oid:
                continue
            row = repos["entity"].get_entity(project_id, oid)
            if row:
                name_map[oid] = row.get("name") or oid

        lines.append(f"\n【双向关系】（共 {len(rels)} 条）")
        for r in rels:
            if r.get("source_id") == entity_id:
                other_id = r.get("target_id")
                direction = "→"
            else:
                other_id = r.get("source_id")
                direction = "←"
            other_name = name_map.get(other_id or "", other_id or "?")
            rel_type = r.get("relation_type") or "未分类"
            trust = r.get("trust_level")
            power = r.get("power_dynamic") or ""
            lines.append(f"  {direction} {other_name}（{rel_type}）")
            if r.get("description"):
                lines.append(f"    描述：{r['description']}")
            meta_parts = []
            if trust is not None and trust != "":
                meta_parts.append(f"信任={trust}")
            if power:
                meta_parts.append(f"权力={power}")
            if r.get("conflict_trigger"):
                meta_parts.append(f"冲突触发={r['conflict_trigger']}")
            if meta_parts:
                lines.append(f"    {'、'.join(meta_parts)}")
    else:
        lines.append("\n【双向关系】无")

    threads = repos["thread"].get_entity_threads(project_id, entity_id, limit=limit)
    if threads:
        lines.append(f"\n【关联伏笔】（共 {len(threads)} 条）")
        for t in threads:
            status = t.get("status", "open")
            label = _STATUS_LABELS.get(status, status)
            key = t.get("thread_key", "")
            detail = t.get("detail", "")
            text = f"  [{label}] {key}"
            if detail:
                text += f"：{detail}"
            lines.append(text)

    rules = repos["world_rule"].get_entity_rules(project_id, entity_id, limit=limit)
    if rules:
        lines.append(f"\n【适用世界规则】（共 {len(rules)} 条）")
        for r in rules:
            lines.append(f"  规则：{r.get('fact_text', '')}")
            snippet = r.get("evidence_snippet", "")
            if snippet:
                lines.append(f"    证据：{snippet}")

    if len(lines) == 1:
        lines.append("（尚无关系 / 伏笔 / 世界规则记录。）")
    return "\n".join(lines)


def _render_entity_events(
    project_id: str, entity: dict, entity_id: str, params: dict,
) -> str:
    """events section: paginated character_events, newest first."""
    limit = max(1, min(int(params.get("limit") or 50), 200))
    cursor = params.get("cursor") or ""

    # Cursor protocol: "offset=<n>" — resilient and avoids coupling to DB row IDs.
    offset = 0
    if cursor.startswith("offset="):
        try:
            offset = max(0, int(cursor.split("=", 1)[1]))
        except ValueError:
            offset = 0

    repos = _get_repos()
    # Fetch offset + limit + 1 so we know if there's a next page.
    all_events = repos["entity"].get_entity_recent_events(
        project_id, entity_id, limit=offset + limit + 1,
    )
    page = all_events[offset : offset + limit]
    has_more = len(all_events) > offset + limit

    lines: list[str] = [
        f"【{entity.get('name', '')}】事件时间线（section=events, offset={offset}, limit={limit}）",
    ]
    if not page:
        lines.append("（该实体尚无事件记录。）")
        return "\n".join(lines)

    for e in page:
        etype = e.get("event_type", "")
        prefix = f"[{etype}] " if etype else ""
        detail = e.get("summary", "")
        ch = e.get("chapter_order", "")
        ch_prefix = f"第{ch}章：" if ch else ""
        lines.append(f"  {prefix}{ch_prefix}{detail}")

    if has_more:
        next_offset = offset + limit
        lines.append(f"\nnext_cursor=offset={next_offset}")
        lines.append("（还有更多事件；下次调用 query_entity 传入 cursor 继续。）")
    else:
        lines.append("\n（已到事件列表末尾。）")
    return "\n".join(lines)


def _render_memory_section(archive_id: str, params: dict) -> str:
    """memories section: canon + candidate long-term memories from archive."""
    limit = max(1, min(int(params.get("limit") or 20), 100))
    try:
        from ..agents.memory.long_term_store import LongTermMemoryStore
    except Exception:
        logger.warning("LongTermMemoryStore import failed", exc_info=True)
        return "（无法加载长期记忆模块。）"

    store = LongTermMemoryStore()
    canon = store.list_active_memories(archive_id, layers=("canon",), limit=limit)
    candidate = store.list_active_memories(archive_id, layers=("candidate",), limit=limit)

    lines: list[str] = [f"【长期记忆】archive={archive_id}（section=memories）"]

    def _render_mem_block(title: str, rows: list[dict]) -> None:
        if not rows:
            lines.append(f"\n{title}（0 条）")
            return
        lines.append(f"\n{title}（{len(rows)} 条，按更新时间/显著性排序）")
        for m in rows:
            mtype = m.get("memory_type", "")
            subject = m.get("normalized_subject") or ""
            summary = m.get("summary", "")
            salience = m.get("salience")
            layer = m.get("memory_layer", "")
            head = f"  [{mtype}] {subject} — {summary}"
            meta = []
            if salience is not None:
                meta.append(f"salience={salience:.2f}" if isinstance(salience, float) else f"salience={salience}")
            if layer:
                meta.append(f"layer={layer}")
            if meta:
                head += f"  ({', '.join(meta)})"
            lines.append(head)

    _render_mem_block("正典记忆（canon，已采纳）", canon)
    _render_mem_block("候选记忆（candidate，尚未采纳——写作时可参考但不可作为既定事实）", candidate)
    return "\n".join(lines)


def _format_archive_only(merged: Any) -> str:
    """Fallback formatter when the character exists in the archive but has no
    in-story entity row yet (e.g. seed-stage projects).
    """
    cp = merged.canon_profile or {}
    lines = [
        f"【{merged.entity_type or '角色'}】{merged.name}",
        f"重要性：{merged.importance_tier or '未知'}",
        "===== 正典档案（仅来自档案库，尚无在地状态）=====",
    ]
    _append_if(lines, "身份定位", cp.get("entity_role"))
    _append_if(lines, "正典·核心驱动", cp.get("core_drive"))
    _append_if(lines, "正典·表面伪装", cp.get("surface_mask"))
    _append_if(lines, "正典·深层张力", cp.get("hidden_tension"))
    _append_if(lines, "正典·关系概述", cp.get("relationship_summary"))
    _append_if(lines, "Agent 行为提示", cp.get("agent_behavior_hint"))
    lines.append("===== 正典档案结束 =====")
    if merged.archetype_refs:
        lines.append("\n【关联角色原型模板】")
        for ref in merged.archetype_refs[:5]:
            title = ref.get("title") or ref.get("asset_id") or ""
            summary = ref.get("summary") or ""
            line = f"  · {title}"
            if summary:
                line += f"：{summary}"
            lines.append(line)
    return "\n".join(lines)


def _query_relationship(params: dict, project_id: str) -> str:
    entity_a = params["entity_a"]
    entity_b = params["entity_b"]
    include_candidate = params.get("include_candidate")
    if include_candidate is None:
        include_candidate = True
    include_candidate = bool(include_candidate)

    # Step 1: fuzzy-resolve both names. If either side has no hit, surface
    # suggestions for it — the caller typically wants to retry with a
    # corrected name rather than fail the whole query.
    resolved_a = _resolve_entity_fuzzy(project_id, entity_a)
    resolved_b = _resolve_entity_fuzzy(project_id, entity_b)

    missing_blocks: list[str] = []
    if not resolved_a.found:
        missing_blocks.append(_format_suggestions(entity_a, resolved_a.suggestions))
    if not resolved_b.found:
        missing_blocks.append(_format_suggestions(entity_b, resolved_b.suggestions))
    if missing_blocks:
        return "\n\n".join(missing_blocks)

    canonical_a = resolved_a.canonical_name or entity_a
    canonical_b = resolved_b.canonical_name or entity_b
    alias_note = ""
    if canonical_a != entity_a or canonical_b != entity_b:
        alias_note = (
            f"注：查询已解析为「{canonical_a}」↔「{canonical_b}」"
            f"（输入的「{entity_a}」/「{entity_b}」经别名重定向）。"
            f"后续请直接用解析后的正式名。\n\n"
        )

    # Step 2: try the structured `relationships` table by entity_ids (richest).
    engine = get_engine()
    rels: list[dict] = []
    a_id = resolved_a.entity.get("entity_id") if resolved_a.entity else None
    b_id = resolved_b.entity.get("entity_id") if resolved_b.entity else None
    if a_id and b_id:
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

    # Step 2b: candidate relationship memories from both archives.
    # Surfaced regardless of whether canonical rels were found — worldline
    # exploration often produces relationship hypotheses that never get
    # promoted to canon, and the writer should still see them as
    # "not-yet-settled" context.
    candidate_block = ""
    if include_candidate:
        candidate_block = _collect_candidate_relationship_memories(
            project_id,
            resolved_a.merged,
            resolved_b.merged,
            canonical_a,
            canonical_b,
        )

    if rels:
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
        body = alias_note + "\n---\n".join(parts)
        if candidate_block:
            body += "\n\n" + candidate_block
        return body

    # Step 3: fall back to graph_edges between the resolved graph nodes.
    # This matters when the project only has graph data (seed pipeline shape)
    # — the old implementation would return "未找到关系记录" here even though
    # edges clearly exist.
    from ...repositories.graph_repo import GraphRepository

    a_uuid = resolved_a.graph_node.get("uuid") if resolved_a.graph_node else None
    b_uuid = resolved_b.graph_node.get("uuid") if resolved_b.graph_node else None
    if a_uuid and b_uuid:
        edge_rows = GraphRepository(engine).find_edges_between(
            project_id, a_uuid, b_uuid, limit=15,
        )
        if edge_rows:
            lines = [f"【图谱关系】{canonical_a} ↔ {canonical_b}（共 {len(edge_rows)} 条图谱边）"]
            for e in edge_rows:
                direction = "→" if e["source_node_uuid"] == a_uuid else "←"
                head = (
                    f"  {canonical_a} {direction} {canonical_b}"
                    f"（{e['name']}, weight={e['weight']}）"
                )
                lines.append(head)
                if e["fact"]:
                    lines.append(f"    事实：{e['fact']}")
            body = alias_note + "\n".join(lines)
            if candidate_block:
                body += "\n\n" + candidate_block
            return body

    tail = (
        alias_note
        + f"未在关系表或图谱边中找到「{canonical_a}」与「{canonical_b}」之间的直接关系。"
        f"\n可尝试：① query_graph_neighbors('{canonical_a}') 看 {canonical_a} 的完整关系网络；"
        f"② query_relationship_timeline 查关系事件时间线；"
        f"③ query_entity('{canonical_a}') / query_entity('{canonical_b}') 看各自档案里是否提到对方。"
    )
    if candidate_block:
        tail += "\n\n" + candidate_block
    return tail


def _collect_candidate_relationship_memories(
    project_id: str,
    merged_a: Any,
    merged_b: Any,
    canonical_a: str,
    canonical_b: str,
) -> str:
    """Pull archive candidate memories that mention the opposite entity.

    Match rule: return candidate rows where
      - memory_type == 'relationship', OR
      - normalized_subject / summary contains the opposite canonical name.

    Returns empty string when no candidates found (caller decides whether to
    emit a block).
    """
    try:
        from ..agents.memory.long_term_store import LongTermMemoryStore
    except Exception:
        logger.warning("LongTermMemoryStore import failed", exc_info=True)
        return ""

    archive_ids: list[tuple[str, str, str]] = []  # (archive_id, owner_canonical, other_canonical)
    if merged_a is not None and getattr(merged_a, "archive_id", None):
        archive_ids.append((merged_a.archive_id, canonical_a, canonical_b))
    if merged_b is not None and getattr(merged_b, "archive_id", None):
        archive_ids.append((merged_b.archive_id, canonical_b, canonical_a))
    if not archive_ids:
        return ""

    store = LongTermMemoryStore()
    hits: list[dict] = []
    for archive_id, owner, other in archive_ids:
        try:
            rows = store.list_active_memories(
                archive_id, layers=("candidate",), limit=20,
            )
        except Exception:
            logger.warning(
                "list candidate memories failed for archive=%s", archive_id, exc_info=True,
            )
            continue
        for row in rows:
            mtype = row.get("memory_type") or ""
            subject = row.get("normalized_subject") or ""
            summary = row.get("summary") or ""
            if (
                mtype == "relationship"
                or other in subject
                or other in summary
            ):
                hits.append({
                    "owner": owner,
                    "other": other,
                    "memory_type": mtype,
                    "subject": subject,
                    "summary": summary,
                    "salience": row.get("salience"),
                })
    if not hits:
        return ""

    lines = [
        f"【候选关系假设（尚未采纳，仅供参考）】（共 {len(hits)} 条）",
        "来源：archive candidate memory；世界线探索/自动演化产出但未被创作者采纳。",
        "写作时可引用这些假设作为心理活动或暗示，但不要当作既定事实。",
    ]
    for h in hits:
        meta = []
        if h["memory_type"]:
            meta.append(h["memory_type"])
        if h["salience"] is not None:
            try:
                meta.append(f"salience={float(h['salience']):.2f}")
            except (TypeError, ValueError):
                meta.append(f"salience={h['salience']}")
        meta_str = f"（{', '.join(meta)}）" if meta else ""
        lines.append(f"  · [{h['owner']} → {h['other']}] {h['subject']}{meta_str}")
        if h["summary"]:
            lines.append(f"    摘要：{h['summary']}")
    return "\n".join(lines)


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

    # Map scope to entity_type filters for the global search index.
    # The global_index row has two independent filterable columns:
    #   - source      ("novel_db", "archive", "assets", ...)  the silo
    #   - entity_type ("entity", "chapter", "relationship", ...)  the kind
    # We filter by entity_type here because scope is about what kind of
    # data to search, not which silo. See unified_asset_view.read_novel_db
    # for the indexer contract.
    #
    # Values are mixed-case because different silos settled on different
    # conventions: archive/story_graph stamp TitleCase ("Character",
    # "Relationship") while novel_db + seed use snake_case ("entity",
    # "world_rule"). We list every known surface form for each scope so
    # the writer doesn't care which silo a match lives in.
    entity_type_map = {
        "entities": [
            "entity", "Entity", "Character", "Artifact",
            "seed_character", "seed_agent_profile",
        ],
        "chapters": ["chapter"],
        "scenes": ["scene"],
        "relationships": ["relationship", "Relationship"],
        "world_rules": ["world_rule", "seed_world_rule"],
        "threads": ["plot_thread", "seed_plot_thread"],
        "memory": ["agent_memory_candidate"],
    }
    entity_types = entity_type_map.get(scope)  # None means "all"
    results = repos["search"].search(
        query, project_id=project_id, entity_types=entity_types, limit=limit,
    )
    if not results:
        return f"未找到与「{query}」相关的设定（scope={scope}）"

    lines = [f"搜索「{query}」结果（scope={scope}，{len(results)} 条）："]
    for i, r in enumerate(results, 1):
        source = r.get("source", "未知")
        entity_type = r.get("entity_type", "")
        name = r.get("name") or r.get("title") or ""
        snippet = r.get("snippet", "")
        tag = f"{source}/{entity_type}" if entity_type else source
        lines.append(f"{i}. [{tag}] {name}")
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
    resolved = _resolve_entity_fuzzy(project_id, name)
    if not resolved.found:
        return _format_suggestions(name, resolved.suggestions)

    entity = resolved.entity
    canonical = resolved.canonical_name or name
    alias_note = ""
    if canonical != name:
        alias_note = (
            f"注：你查的「{name}」已通过 {resolved.matched_via} 解析为「{canonical}」。\n\n"
        )

    # Voice data lives in the `entities` row. If the entity table is empty
    # (seed-stage projects), there is no structured voice — tell the agent
    # exactly what to try instead, rather than returning a cryptic empty shell.
    if entity is None:
        return (
            alias_note
            + f"「{canonical}」在项目中存在（来源：{resolved.matched_via}），"
            "但 entities 表中尚无结构化角色档案，因此无法提供 speech_style / verbal_habits 等字段。\n"
            f"建议：① 用 query_entity('{canonical}') 看档案库里是否有说话风格描述；"
            "② 用 query_character_timeline 看历史事件里的台词；"
            "③ 用 manage_entity(action='update') 补充 speech_style、example_quotes 等字段。"
        )

    lines = [alias_note.rstrip()] if alias_note else []
    lines.append(f"【角色语言风格】{entity.get('name', canonical)}")
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

    resolved_a = _resolve_entity_fuzzy(project_id, a_name)
    resolved_b = _resolve_entity_fuzzy(project_id, b_name)
    missing_blocks: list[str] = []
    if not resolved_a.found:
        missing_blocks.append(_format_suggestions(a_name, resolved_a.suggestions))
    if not resolved_b.found:
        missing_blocks.append(_format_suggestions(b_name, resolved_b.suggestions))
    if missing_blocks:
        return "\n\n".join(missing_blocks)

    canonical_a = resolved_a.canonical_name or a_name
    canonical_b = resolved_b.canonical_name or b_name
    # Timeline is keyed off entity_ids in `relationship_events`; if the
    # entities table is empty we have no timeline records to show, so fall
    # back to the name strings (they might match the older legacy schema
    # where source_entity_id held a name rather than an id).
    a_id = resolved_a.entity.get("entity_id") if resolved_a.entity else canonical_a
    b_id = resolved_b.entity.get("entity_id") if resolved_b.entity else canonical_b

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
                            relationship_events.c.source_entity_id == canonical_a,
                            relationship_events.c.target_entity_id == canonical_b,
                        ),
                        and_(
                            relationship_events.c.source_entity_id == canonical_b,
                            relationship_events.c.target_entity_id == canonical_a,
                        ),
                    ),
                )
            ).order_by(
                relationship_events.c.chapter_order,
                relationship_events.c.segment_id,
            )
        ).fetchall()
        results = [dict(r._mapping) for r in rows]

    alias_note = ""
    if canonical_a != a_name or canonical_b != b_name:
        alias_note = (
            f"注：查询已解析为「{canonical_a}」↔「{canonical_b}」。\n\n"
        )

    if not results:
        return (
            alias_note
            + f"未找到「{canonical_a}」与「{canonical_b}」之间的关系事件。"
            "可改用 query_relationship 查当前关系状态或 query_graph_neighbors 看双方各自的关系网络。"
        )
    lines = [f"【关系时间线】{canonical_a} ↔ {canonical_b}（共 {len(results)} 条事件）"]
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
    return alias_note + "\n".join(lines)


def _query_character_timeline(inp: dict, project_id: str) -> str:
    name = inp.get("name", "")
    event_type = inp.get("event_type", "all")
    limit = inp.get("limit", 20)
    resolved = _resolve_entity_fuzzy(project_id, name)
    if not resolved.found:
        return _format_suggestions(name, resolved.suggestions)
    canonical = resolved.canonical_name or name
    # Events may be keyed by entity_id (new data) or by name string (legacy),
    # so try both. If we hit via graph-only, fall back to canonical name as id.
    entity = resolved.entity
    entity_id = entity.get("entity_id", canonical) if entity else canonical

    engine = get_engine()
    clauses = [
        character_events.c.project_id == project_id,
        or_(
            character_events.c.entity_id == entity_id,
            character_events.c.entity_id == canonical,
        ),
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

    alias_note = ""
    if canonical != name:
        alias_note = f"注：你查的「{name}」已解析为「{canonical}」。\n\n"

    if not results:
        return (
            alias_note
            + f"未找到「{canonical}」的事件记录。"
            f"可改用 query_entity('{canonical}') 看角色档案里是否包含近期事件字段，"
            "或 get_story_overview / query_segment_summaries 看全局叙事。"
        )
    lines = [f"【角色时间线】{canonical}（共 {len(results)} 条事件）"]
    for r in results:
        prefix = f"[{r['event_type']}]" if r.get("event_type") else ""
        seg = f" ({r['segment_id']})" if r.get("segment_id") else ""
        lines.append(f"  {prefix} {r['summary']}{seg}")
    return alias_note + "\n".join(lines)


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

    lines: list[str] = []
    if results:
        lines.append(f"搜索「{query}」世界观规则（{len(results)} 条）：")
        for r in results:
            lines.append(f"  规则：{r['fact_text']}")
            if r.get("evidence_snippet"):
                lines.append(f"    证据：{r['evidence_snippet']}")
            if r.get("chapter_order"):
                lines.append(f"    出处：第{r['chapter_order']}章")
            eid = r.get("evidence_id")
            if eid:
                ents = repos["world_rule"].get_rule_entities(project_id, eid, limit=10)
                if ents:
                    lines.append(f"    关联实体：{_format_entity_names(ents)}")

    # Always try the agent_memory fallback too — worldline session agents
    # emit world_rule observations that live here and never make it into
    # world_rule_evidence; the writer still benefits from seeing them.
    # NOTE: this is app.tables.novel.agent_memory (session-scoped), which
    # does NOT have memory_layer / archive_id / normalized_subject columns —
    # only the minimal set below.
    with engine.connect() as conn:
        mem_rows = conn.execute(
            select(
                agent_memory.c.memory_id,
                agent_memory.c.summary,
                agent_memory.c.detail_json,
                agent_memory.c.source_kind,
            ).where(
                and_(
                    agent_memory.c.memory_type == "world_rule",
                    or_(
                        agent_memory.c.summary.like(like_pattern),
                        agent_memory.c.detail_json.like(like_pattern),
                    ),
                )
            ).limit(limit)
        ).fetchall()

    if mem_rows:
        lines.append("")
        lines.append(f"【世界线 agent 观察记忆命中】（{len(mem_rows)} 条，尚未进入 world_rule_evidence）")
        for r in mem_rows:
            src = r.source_kind or "session"
            lines.append(f"  [{src}] {r.summary}")

    if not lines:
        return f"未找到与「{query}」相关的世界观规则"
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

    if lines:
        return "\n".join(lines)
    # No rows anywhere — distinguish "tables empty" from "tool未实现" so the
    # agent and the user can act on it instead of giving up silently.
    return (
        "未找到故事概览数据。\n"
        "诊断：narrative_arcs / volume_summaries 表均为空。可能原因：\n"
        "  ① 种子管线尚未完成 Stage 3 聚合（先在「总览」页跑完种子分析）；\n"
        "  ② 本书尚未启用叙事弧线分析。\n"
        "缺失该工具不致命，但 Agent 将无法感知全书阶段/弧线进度。"
    )


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

    if summaries:
        return "\n".join(lines)
    # Same diagnostic pattern as get_story_overview — tell the agent what's
    # missing so it can warn the user instead of silently falling back.
    return (
        "未找到段落摘要数据。\n"
        "诊断：segment_summaries 表为空。可能原因：\n"
        "  ① 种子管线尚未完成 Stage 2 / Stage 3（逐段精读 + 聚合）；\n"
        "  ② 传入的 segment_ids 不在本项目中。\n"
        "缺失该工具会让续写时的『前情回顾』不可用，请优先跑完种子分析。"
    )


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

    node_info = repo.lookup_node_by_name_or_alias(project_id, name)
    if node_info is None:
        return f"故事图谱中未找到节点：{name}"
    node_uuid = node_info["uuid"]

    # get_neighbors_with_labels already packs edge + neighbor into one row,
    # ordered by weight DESC. We just render it.
    neighbors = repo.get_neighbors_with_labels(project_id, node_uuid, limit=limit)
    lines = [
        f"# 节点：{node_info['name']}",
        f"摘要：{node_info['summary'] or '(无)'}",
        "",
        f"## 邻居 / 关系（{len(neighbors)} 条）",
    ]
    for nb in neighbors:
        direction = "→" if nb["direction"] == "outgoing" else "←"
        lines.append(
            f"- {direction} {nb['neighbor_name']} "
            f"({nb['edge_name']}, weight={nb['edge_weight']})\n"
            f"    fact: {nb['edge_fact']}\n"
            f"    对端摘要: {(nb['neighbor_summary'] or '')[:120]}"
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

    # Pull nodes labeled PlotEvent or Conflict. The event_id filter lives inside
    # attributes_json, so we fetch a wider bucket (500 each) and post-filter
    # in Python — mirroring the legacy text()-based implementation.
    bucket: list[dict] = []
    seen_uuids: set[str] = set()
    for label in ("PlotEvent", "Conflict"):
        for row in repo.find_nodes_by_label(project_id, label, limit=500):
            if row["uuid"] in seen_uuids:
                continue
            seen_uuids.add(row["uuid"])
            bucket.append(row)

    matches: list[dict] = []
    for r in bucket:
        attrs = r.get("attributes") or {}
        if event_id:
            if str(attrs.get("event_id", "")) != event_id:
                continue
        elif name:
            if name not in (r["name"] or "") and name not in (r["summary"] or ""):
                continue
        matches.append(
            {
                "uuid": r["uuid"],
                "name": r["name"],
                "summary": r["summary"],
                "attrs": attrs,
                # find_nodes_by_label doesn't surface evidence_refs; fall back
                # to load_node for the matched entry to enrich with evidence.
                "evidence": [],
            }
        )
        if len(matches) >= limit:
            break

    if not matches:
        target = event_id or name
        return f"未找到事件：{target}"

    # Enrich with evidence via load_node (only for matches — cheap).
    for m in matches:
        node = repo.load_node(project_id, m["uuid"])
        if node:
            m["evidence"] = node.get("evidence_refs") or []

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

    node_info = repo.lookup_node_by_name_or_alias(project_id, name)
    if node_info is None:
        return f"故事图谱中未找到节点：{name}"
    node_uuid = node_info["uuid"]

    # Over-fetch so the label filter has room to drop non-person neighbors.
    neighbors = repo.get_neighbors_with_labels(project_id, node_uuid, limit=limit * 2)

    person_labels = {"Character", "Organization", "Faction", "Group"}
    filtered: list[dict] = []
    for nb in neighbors:
        if not (set(nb["neighbor_labels"]) & person_labels):
            continue
        filtered.append(nb)
        if len(filtered) >= limit:
            break

    if not filtered:
        return f"# {node_info['name']}\n暂无角色关系网络"
    lines = [
        f"# {node_info['name']} 的关系网络（{len(filtered)} 条）",
        f"摘要: {node_info['summary'] or '(无)'}",
        "",
    ]
    for nb in filtered:
        direction = "→" if nb["direction"] == "outgoing" else "←"
        lines.append(
            f"- {direction} {nb['neighbor_name']}  "
            f"[{nb['edge_name']}, weight={nb['edge_weight']}]"
        )
        if nb["edge_fact"]:
            lines.append(f"    事实: {nb['edge_fact']}")
    return "\n".join(lines)


def _query_worldline_session(params: dict, project_id: str) -> str:
    """Read worldline session data from the unified DB via repositories.

    Was file-based (``uploads/projects/{pid}/worldlines/sessions/*.json``) until
    Phase D/E migrated sessions into ``worldline_sessions``. The payload we read
    is the session's ``to_dict()`` (see :class:`WorldlineSession`): events live
    inside ``branches[].timeline``, not at the top level — the old code's
    ``data.get("events")`` was never populated against current payloads.
    """
    from ...repositories.worldline_session_repo import WorldlineSessionRepository

    engine = get_engine()
    session_repo = WorldlineSessionRepository(engine)

    sid = (params.get("session_id") or "").strip()
    summary: dict | None = None
    if sid:
        data = session_repo.load_session(sid)
        if data is None:
            return (
                f"未找到 session: {sid}\n"
                "诊断：该 session_id 在 worldline_sessions 表中不存在。"
                "可能是 session 已删除，或 id 拼写错误。"
            )
        # Prevent cross-project leakage when a caller passes a sid from another project.
        if data.get("project_id") and data.get("project_id") != project_id:
            return f"session {sid} 不属于当前项目"
    else:
        recent = session_repo.list_sessions(project_id=project_id, limit=1)
        if not recent:
            return (
                f"项目 {project_id} 暂无世界线推演记录。\n"
                "诊断：worldline_sessions 表中没有本项目的条目。\n"
                "如需使用世界线分支数据，请先在「世界线」页创建并推演一个 session；"
                "如果本次写作不需要推演分支，忽略此工具即可。"
            )
        summary = recent[0]
        sid = summary["session_id"]
        data = session_repo.load_session(sid)
        if data is None:
            return f"session {sid} 数据缺失（有列表记录但无 session_data_json）"

    title = data.get("label") or "(无)"
    goal = (data.get("simulation_goal") or "").strip()
    focus = (data.get("focus_question") or "").strip()
    desc_parts: list[str] = []
    if goal:
        desc_parts.append(goal)
    if focus and focus != goal:
        desc_parts.append(f"焦点问题：{focus}")
    description = " / ".join(desc_parts) or "(无)"
    updated = data.get("updated_at") or (summary.get("updated_at") if summary else "(未知)")

    lines = [
        f"# 世界线 Session: {sid}",
        f"标题: {title}",
        f"描述: {description}",
        f"状态: {data.get('status', '(未知)')}",
        f"更新时间: {updated}",
    ]

    variables = data.get("world_variables") or []
    if variables:
        lines.append(f"\n## 世界变量（{len(variables)} 条）")
        for v in variables[:20]:
            if not isinstance(v, dict):
                continue
            name = v.get("name") or v.get("variable_id") or "?"
            vdesc = v.get("description") or ""
            impact = v.get("impact_axis") or ""
            meta = f"（{impact}）" if impact else ""
            lines.append(f"- {name}{meta}：{vdesc}" if vdesc else f"- {name}{meta}")

    branches = data.get("branches") or []
    if branches:
        lines.append(f"\n## 分支（共 {len(branches)}）")
        for branch in branches:
            if not isinstance(branch, dict):
                continue
            bid = branch.get("branch_id", "?")
            btitle = branch.get("title", "")
            core = branch.get("core_change", "")
            step = branch.get("current_step", 0)
            bstatus = branch.get("status", "")
            lines.append(f"### 分支 {bid}: {btitle}")
            if core:
                lines.append(f"  核心变化: {core}")
            lines.append(f"  当前步: {step} · 状态: {bstatus}")

    # Collect agent identities across branches (dedup by id)
    agent_ids: list[str] = []
    seen_agents: set[str] = set()
    for branch in branches:
        if not isinstance(branch, dict):
            continue
        for aid in branch.get("key_agents") or []:
            if aid and aid not in seen_agents:
                seen_agents.add(aid)
                agent_ids.append(aid)
        for aid in (branch.get("actor_states") or {}).keys():
            if aid and aid not in seen_agents:
                seen_agents.add(aid)
                agent_ids.append(aid)
    if agent_ids:
        lines.append(f"\n## 参与角色（{len(agent_ids)}）")
        for aid in agent_ids[:30]:
            lines.append(f"- {aid}")

    # Flatten timeline across branches, newest first
    all_events: list[dict] = []
    for branch in branches:
        if not isinstance(branch, dict):
            continue
        bid = branch.get("branch_id", "?")
        for ev in branch.get("timeline") or []:
            if not isinstance(ev, dict):
                continue
            all_events.append(
                {
                    "branch_id": bid,
                    "step": ev.get("step", 0),
                    "title": ev.get("title", ""),
                    "summary": ev.get("summary", ""),
                }
            )
    if all_events:
        all_events.sort(key=lambda e: e.get("step", 0), reverse=True)
        shown = all_events[:10]
        lines.append(f"\n## 最近事件（共 {len(all_events)}，最新 {len(shown)} 条）")
        for ev in shown:
            head = f"- [分支 {ev['branch_id']} · 步 {ev['step']}]"
            title_line = ev["title"] or ""
            summary_line = ev["summary"] or ""
            if title_line and summary_line:
                lines.append(f"{head} {title_line}：{summary_line}")
            elif title_line:
                lines.append(f"{head} {title_line}")
            elif summary_line:
                lines.append(f"{head} {summary_line}")
            else:
                lines.append(head)

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


def _get_chapter_word_stats(params: dict, project_id: str) -> dict:
    """Return chapter word-count breakdown with an optional WordBudgetRender.

    Emits a two-part response: ``result`` (LLM-visible text) plus ``render``
    (structured UI payload consumed by the WordBudgetGauge card).
    """
    chapter_id = params.get("chapter_id") or ""
    if not chapter_id:
        return {"result": "get_chapter_word_stats 需要 chapter_id"}
    target = params.get("target_word_count")
    adapter = _get_manuscript_adapter(project_id)
    blocks = adapter.list_blocks(include_content=True, chapter_id=chapter_id)
    if not blocks:
        return {"result": f"章节 {chapter_id} 暂无已提交稿件块"}

    lines: list[str] = []
    total = 0
    block_payloads: list[dict] = []
    for b in blocks:
        c = _block_chars(b.get("content") or "")
        total += c
        preview = (b.get("content") or "").strip().replace("\n", " ")[:32]
        lines.append(
            f"- block_id={b['block_id']}  order={b.get('block_order')}  chars={c}  preview={preview!r}"
        )
        block_payloads.append(
            {
                "block_id": b["block_id"],
                "block_order": int(b.get("block_order") or 0),
                "word_count": c,
                "preview": preview,
            }
        )

    header = [f"章节 {chapter_id} 共 {len(blocks)} 块，总字数={total}"]
    target_int: int | None = None
    diff = 0
    pct = 0.0
    if target is not None:
        try:
            target_int = int(target)
            diff = total - target_int
            pct = (diff / target_int * 100) if target_int else 0.0
            header.append(f"目标={target_int}，差值={diff:+d}（{pct:+.1f}%）")
        except (TypeError, ValueError):
            target_int = None

    # Resolve chapter meta (order/title) for the render header.
    chapter_order = 0
    chapter_title = ""
    try:
        chapter_row = ChapterRepository(get_engine()).get_chapter(project_id, chapter_id)
        if chapter_row:
            chapter_order = int(chapter_row.get("chapter_order") or 0)
            chapter_title = str(chapter_row.get("title") or "")
    except Exception:  # noqa: BLE001
        pass

    result_text = "\n".join(header + [""] + lines)

    # Only attach render when the caller supplied a target — without it we
    # can't compute a budget status, which is the whole point of the card.
    render_payload = None
    if target_int is not None:
        from ...schemas.writer_agent_schemas import WordBudgetRender

        tolerance_pct = 10  # Card is read-only; backend default is fine here.
        deficit_pct = abs(pct)
        if deficit_pct <= tolerance_pct:
            status = "on_target"
        elif diff > 0:
            status = "over"
        else:
            status = "under"

        render_payload = WordBudgetRender(
            data={
                "chapter_id": chapter_id,
                "chapter_order": chapter_order,
                "chapter_title": chapter_title,
                "target": target_int,
                "total": total,
                "diff": diff,
                "tolerance_pct": tolerance_pct,
                "blocks": block_payloads,
                "status": status,
            },
            actions=[],
            tool_call_id=params.get("_call_id"),
        ).model_dump(mode="json")

    return {"result": result_text, "render": render_payload}


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
            if asset and asset.get("enabled") and asset.get("asset_type") == AssetType.FORBIDDEN_LEXICON.value:
                assets.append(asset)
    else:
        assets = svc.list_merged(
            project_id=project_id,
            asset_type=AssetType.FORBIDDEN_LEXICON.value,
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
        asset_type=AssetType.FORBIDDEN_LEXICON.value,
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
        asset_type=AssetType.FORBIDDEN_LEXICON.value,
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


# ---------------------------------------------------------------------------
# propose_* tools — draft render cards, never write DB. Users adopt by clicking
# the card's [采纳] button which dispatches to the real API client by render.type.
# ---------------------------------------------------------------------------


def _propose_outline_scene(params: dict, project_id: str) -> dict:
    """Draft a SceneProposalCard for a chapter gap. Never writes DB."""
    from ...schemas.writer_agent_schemas import SceneProposalRender, ToolRenderAction

    chapter_id = params.get("chapter_id") or ""
    title = (params.get("title") or "").strip()
    summary = (params.get("summary") or "").strip()
    reason = (params.get("reason") or "").strip()
    insert_after = params.get("insert_after_scene_order")
    if not chapter_id or not title or not summary or not reason:
        return {
            "result": "propose_outline_scene 需要 chapter_id / title / summary / reason",
        }
    if insert_after is None:
        return {"result": "propose_outline_scene 需要 insert_after_scene_order（0 表示章首）"}

    try:
        insert_after_int = int(insert_after)
    except (TypeError, ValueError):
        return {"result": f"insert_after_scene_order 必须是整数，收到 {insert_after!r}"}

    chapter_row = ChapterRepository(get_engine()).get_chapter(project_id, chapter_id)
    if not chapter_row:
        return {"result": f"找不到章节 {chapter_id}"}
    chapter_order = int(chapter_row.get("chapter_order") or 0)

    scene_order = params.get("scene_order")
    try:
        scene_order_int = int(scene_order) if scene_order is not None else insert_after_int + 1
    except (TypeError, ValueError):
        scene_order_int = insert_after_int + 1

    pov = (params.get("pov") or "").strip()
    key_events_raw = params.get("key_events") or []
    if isinstance(key_events_raw, str):
        key_events = [key_events_raw]
    elif isinstance(key_events_raw, list):
        key_events = [str(x) for x in key_events_raw if x]
    else:
        key_events = []

    target_wc = params.get("target_word_count")
    try:
        target_wc_int = int(target_wc) if target_wc is not None else None
    except (TypeError, ValueError):
        target_wc_int = None

    data = {
        "chapter_id": chapter_id,
        "chapter_order": chapter_order,
        "scene_order": scene_order_int,
        "mode": "insert",
        "insert_after_scene_order": insert_after_int,
        "title": title,
        "summary": summary,
        "pov": pov,
        "key_events": key_events,
        "rationale": reason,
        "reason": reason,
    }
    if target_wc_int is not None:
        data["estimated_word_count"] = target_wc_int
        data["target_word_count"] = target_wc_int

    render = SceneProposalRender(
        data=data,
        actions=[
            ToolRenderAction(label="采纳并创建场景", kind="create_scene", variant="primary"),
        ],
        tool_call_id=params.get("_call_id"),
    ).model_dump(mode="json")

    result_text = (
        f"已草拟新场景提案：第 {chapter_order} 章 · {title}\n"
        f"插入位置：#{insert_after_int} 之后 → #{scene_order_int}\n"
        f"POV: {pov or '未指定'}；目标字数：{target_wc_int or '未指定'}\n"
        f"理由：{reason}\n"
        f"（尚未入库，等待用户采纳）"
    )
    return {"result": result_text, "render": render}


def _propose_chapter_structure(params: dict, project_id: str) -> dict:
    """Draft a ChapterStructureProposalCard with a batch of chapter stubs."""
    from ...schemas.writer_agent_schemas import (
        ChapterStructureProposalRender,
        ToolRenderAction,
    )

    start_raw = params.get("start_chapter_order")
    chapters_raw = params.get("chapters") or []
    if not isinstance(chapters_raw, list) or not chapters_raw:
        return {"result": "propose_chapter_structure 需要 chapters 数组（至少 1 项）"}
    try:
        start_order = int(start_raw) if start_raw is not None else 1
    except (TypeError, ValueError):
        return {"result": f"start_chapter_order 必须是整数，收到 {start_raw!r}"}

    normalized: list[dict] = []
    for idx, raw in enumerate(chapters_raw):
        if not isinstance(raw, dict):
            continue
        title = str(raw.get("title") or "").strip()
        summary = str(raw.get("summary") or "").strip()
        if not title or not summary:
            continue
        try:
            order = int(raw.get("chapter_order") or (start_order + idx))
        except (TypeError, ValueError):
            order = start_order + idx
        try:
            word_target = int(raw.get("word_target") or 0)
        except (TypeError, ValueError):
            word_target = 0
        threads_raw = raw.get("key_threads") or []
        key_threads = (
            [str(t) for t in threads_raw if t]
            if isinstance(threads_raw, list)
            else []
        )
        normalized.append(
            {
                "chapter_order": order,
                "title": title,
                "summary": summary,
                "hook": str(raw.get("hook") or "").strip() or None,
                "word_target": word_target,
                "pov_character": str(raw.get("pov_character") or "").strip() or None,
                "key_threads": key_threads,
            }
        )
    if not normalized:
        return {"result": "chapters 数组中没有有效的章节（需要 title + summary）"}

    data = {
        "plan_id": params.get("plan_id") or None,
        "start_chapter_order": start_order,
        "chapters": normalized,
        "overall_arc": (params.get("overall_arc") or "").strip() or None,
        "rationale": (params.get("rationale") or "").strip() or None,
    }

    render = ChapterStructureProposalRender(
        data=data,
        actions=[
            ToolRenderAction(
                label="采纳并批量建章",
                kind="create_chapters",
                variant="primary",
            ),
        ],
        tool_call_id=params.get("_call_id"),
    ).model_dump(mode="json")

    titles = "、".join(f"#{c['chapter_order']} {c['title']}" for c in normalized[:5])
    more = f"（共 {len(normalized)} 章）" if len(normalized) > 5 else ""
    result_text = (
        f"已草拟章节骨架提案：从第 {start_order} 章起 → {titles}{more}\n"
        f"（尚未入库，等待用户采纳）"
    )
    return {"result": result_text, "render": render}


def _propose_splice_block(params: dict, project_id: str) -> dict:
    """Draft a ProseDiffCard (single-hunk expand/shrink). Never writes DB."""
    from ...schemas.writer_agent_schemas import ProseDiffRender, ToolRenderAction

    chapter_id = params.get("chapter_id") or ""
    anchor_block_id = params.get("anchor_block_id") or ""
    position = (params.get("position") or "").lower()
    new_content = params.get("new_content") or ""
    reason = (params.get("reason") or "").strip()
    intent = (params.get("intent") or "").lower()
    if not chapter_id or not anchor_block_id or not position:
        return {"result": "propose_splice_block 需要 chapter_id / anchor_block_id / position"}
    if position not in ("before", "after", "replace_range"):
        return {"result": f"position 必须是 before|after|replace_range，收到 {position!r}"}
    if not new_content and position != "replace_range":
        return {"result": "propose_splice_block 在 before/after 模式下 new_content 不能为空"}
    if not reason:
        return {"result": "propose_splice_block 要求 reason 非空（让用户看到提案动机）"}
    if intent not in ("expand", "shrink"):
        return {"result": "propose_splice_block 要求 intent=expand|shrink"}

    new_chars = _block_chars(new_content)
    if new_chars > _SPLICE_MAX_DELTA_CHARS:
        return {
            "result": (
                f"propose_splice_block 被拒绝：单次写入 {new_chars} 字超过上限 "
                f"{_SPLICE_MAX_DELTA_CHARS}"
            )
        }

    adapter = _get_manuscript_adapter(project_id)
    anchor = adapter.get_block(anchor_block_id)
    if not anchor:
        return {"result": f"找不到锚点块 {anchor_block_id}"}
    if anchor.get("chapter_id") != chapter_id:
        return {"result": f"锚点块不属于章节 {chapter_id}"}

    original_text = ""
    old_chars = 0
    if position == "replace_range":
        end_anchor = params.get("end_anchor_block_id") or anchor_block_id
        end_block = adapter.get_block(end_anchor)
        if not end_block or end_block.get("chapter_id") != chapter_id:
            return {"result": f"replace_range 的结束锚点 {end_anchor} 不合法"}
        start_order = anchor.get("block_order") or 0
        end_order = end_block.get("block_order") or 0
        if end_order < start_order:
            return {"result": "end_anchor_block_id 的顺序必须 ≥ anchor_block_id"}
        blocks = adapter.list_blocks(include_content=True, chapter_id=chapter_id)
        in_range = [
            b for b in blocks
            if (b.get("block_order") or 0) >= start_order
            and (b.get("block_order") or 0) <= end_order
        ]
        original_text = "\n\n".join(b.get("content") or "" for b in in_range)
        old_chars = sum(_block_chars(b.get("content") or "") for b in in_range)
        delta = new_chars - old_chars
        if abs(delta) > _SPLICE_MAX_DELTA_CHARS:
            return {
                "result": (
                    f"propose_splice_block replace_range 被拒绝：净变化 {delta:+d} 字超过上限 "
                    f"±{_SPLICE_MAX_DELTA_CHARS}"
                )
            }
    word_delta = new_chars - old_chars

    hunk = {
        "hunk_id": f"splice_{uuid.uuid4().hex[:8]}",
        "original": original_text,
        "replacement": new_content,
        "reason": reason,
        "severity": "medium",
        "category": f"{intent}_splice",
        "location_hint": f"{position} of {anchor_block_id}",
    }

    data = {
        "scope": "manuscript_block",
        "target_id": anchor_block_id,
        "chapter_label": params.get("chapter_label") or "",
        "hunks": [hunk],
        "word_delta": word_delta,
        "source": "splice_block",
    }

    render = ProseDiffRender(
        data=data,
        actions=[
            ToolRenderAction(label="采纳改写", kind="apply_hunks", variant="primary"),
        ],
        tool_call_id=params.get("_call_id"),
    ).model_dump(mode="json")

    label = "扩写" if intent == "expand" else "精简"
    result_text = (
        f"已草拟 {label} 提案：锚定 {anchor_block_id}（{position}）\n"
        f"字数：{old_chars} → {new_chars}（Δ{word_delta:+d}）\n"
        f"理由：{reason}\n（尚未入库，等待用户采纳）"
    )
    return {"result": result_text, "render": render}


def _propose_rewrite_span(params: dict, project_id: str) -> dict:
    """Draft a ProseDiffCard for a forbidden-lexicon rewrite. Never writes DB.

    Hard-enforces:
    - original_text unique within the block (so adoption can safely replace).
    - new_text non-empty and reason non-empty (guard against silent drops).
    - |Δchars| ≤ _REWRITE_MAX_DELTA_CHARS (same budget as real rewrite_span).
    """
    from ...schemas.writer_agent_schemas import ProseDiffRender, ToolRenderAction

    block_id = params.get("block_id") or ""
    original = params.get("original_text") or ""
    new_text = params.get("new_text") or ""
    reason = (params.get("reason") or "").strip()
    if not block_id or not original:
        return {"result": "propose_rewrite_span 需要 block_id 和 original_text"}
    if not new_text:
        return {"result": "propose_rewrite_span 要求 new_text 非空（防止误点采纳后语义塌陷）"}
    if not reason:
        return {"result": "propose_rewrite_span 要求 reason 非空"}

    old_chars = _block_chars(original)
    new_chars = _block_chars(new_text)
    word_delta = new_chars - old_chars
    if abs(word_delta) > _REWRITE_MAX_DELTA_CHARS:
        return {
            "result": (
                f"propose_rewrite_span 被拒绝：字数变化 {word_delta:+d} 超过上限 "
                f"±{_REWRITE_MAX_DELTA_CHARS}"
            )
        }

    adapter = _get_manuscript_adapter(project_id)
    block = adapter.get_block(block_id)
    if not block:
        return {"result": f"找不到 block_id={block_id}"}
    content = block.get("content") or ""
    occurrences = content.count(original)
    if occurrences == 0:
        return {
            "result": (
                f"original_text 未出现在块 {block_id} 中，请先 get_manuscript_context "
                f"或 scan_forbidden_lexicon 核对实际文本"
            )
        }
    if occurrences > 1:
        return {
            "result": (
                f"original_text 在块 {block_id} 中出现 {occurrences} 次（不唯一），"
                f"请扩展 original_text 使之唯一后重试"
            )
        }

    hunk = {
        "hunk_id": f"rewrite_{uuid.uuid4().hex[:8]}",
        "original": original,
        "replacement": new_text,
        "reason": reason,
        "severity": "high",
        "category": "forbidden_lexicon",
        "location_hint": f"block={block_id}",
    }
    data = {
        "scope": "manuscript_block",
        "target_id": block_id,
        "chapter_label": params.get("chapter_label") or "",
        "hunks": [hunk],
        "word_delta": word_delta,
        "source": "rewrite_span",
    }

    render = ProseDiffRender(
        data=data,
        actions=[
            ToolRenderAction(label="采纳改写", kind="apply_hunks", variant="primary"),
        ],
        tool_call_id=params.get("_call_id"),
    ).model_dump(mode="json")

    result_text = (
        f"已草拟禁词改写提案：块 {block_id}\n"
        f"「{original}」→「{new_text}」（Δ{word_delta:+d} 字）\n"
        f"理由：{reason}\n（尚未入库，等待用户采纳）"
    )
    return {"result": result_text, "render": render}


def _propose_relationship(params: dict, project_id: str) -> dict:
    """Draft a RelationshipProposalCard. Never writes DB."""
    from ...schemas.writer_agent_schemas import (
        RelationshipProposalRender,
        ToolRenderAction,
    )

    a = (params.get("entity_a") or "").strip()
    b = (params.get("entity_b") or "").strip()
    rel_type = (params.get("relation_type") or "").strip()
    description = (params.get("description") or "").strip()
    evidence = (params.get("evidence_snippet") or "").strip()
    if not a or not b or not rel_type:
        return {"result": "propose_relationship 需要 entity_a / entity_b / relation_type"}
    if a == b:
        return {"result": "entity_a 与 entity_b 不能相同"}
    if not description:
        return {"result": "propose_relationship 要求 description 非空"}
    if not evidence:
        return {"result": "propose_relationship 要求 evidence_snippet 非空（避免无据生成）"}

    trust_level = params.get("trust_level")
    try:
        trust_val = float(trust_level) if trust_level is not None else None
    except (TypeError, ValueError):
        trust_val = None
    if trust_val is not None and not (0.0 <= trust_val <= 1.0):
        return {"result": f"trust_level 需在 [0, 1] 区间，收到 {trust_level!r}"}

    # Resolve entity IDs if possible (not required — frontend uses names for display)
    repos = _get_repos()
    entity_a_id = repos["entity"].resolve_entity_id(project_id, a)
    entity_b_id = repos["entity"].resolve_entity_id(project_id, b)

    source_scene_ids_raw = params.get("source_scene_ids") or []
    source_scene_ids = (
        [str(s) for s in source_scene_ids_raw if s]
        if isinstance(source_scene_ids_raw, list)
        else []
    )

    data = {
        "entity_a": a,
        "entity_b": b,
        "entity_a_id": entity_a_id,
        "entity_b_id": entity_b_id,
        "relation_type": rel_type,
        "description": description,
        "trust_level": trust_val,
        "power_dynamic": (params.get("power_dynamic") or "").strip() or None,
        "conflict_trigger": (params.get("conflict_trigger") or "").strip() or None,
        "evidence_snippet": evidence,
        "source_scene_ids": source_scene_ids,
    }

    render = RelationshipProposalRender(
        data=data,
        actions=[
            ToolRenderAction(label="采纳并落库", kind="update_world", variant="primary"),
        ],
        tool_call_id=params.get("_call_id"),
    ).model_dump(mode="json")

    result_text = (
        f"已草拟关系提案：{a} ↔ {b}（{rel_type}）\n"
        f"描述：{description}\n"
        f"证据：{evidence[:80]}{'…' if len(evidence) > 80 else ''}\n"
        f"（尚未入库，等待用户采纳）"
    )
    return {"result": result_text, "render": render}


def _propose_prose_continuation(params: dict, project_id: str) -> dict:
    """Declare that retrieval is done; signal the chapter_continuer runner to
    hand off to WriterComposer. This tool does NOT produce a render payload —
    the runner intercepts the tool call, runs the composer, and emits the
    final ProseDiff card itself.

    We still validate params here so the LLM gets a clear error if it calls
    this with garbage; the runner trusts a successful result.
    """
    anchor_block_id = params.get("anchor_block_id") or ""
    target_word_count = params.get("target_word_count")
    writing_brief = params.get("writing_brief")

    if not anchor_block_id:
        return {"result": "propose_prose_continuation 需要 anchor_block_id"}
    if not isinstance(writing_brief, dict) or not writing_brief:
        return {"result": "propose_prose_continuation 需要非空 writing_brief (dict)"}
    try:
        target_int = int(target_word_count)
    except (TypeError, ValueError):
        return {"result": "target_word_count 必须是整数"}
    if not (200 <= target_int <= 1200):
        return {"result": f"target_word_count={target_int} 超出 [200, 1200] 区间"}

    return {
        "result": (
            f"已收到续写检索结果：锚点={anchor_block_id}，目标={target_int} 字。"
            f"WriterComposer 将开始流式生成。"
        )
    }


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
    # propose_* tools (draft-only, never write DB)
    "propose_outline_scene": _propose_outline_scene,
    "propose_chapter_structure": _propose_chapter_structure,
    "propose_splice_block": _propose_splice_block,
    "propose_rewrite_span": _propose_rewrite_span,
    "propose_relationship": _propose_relationship,
    "propose_prose_continuation": _propose_prose_continuation,
}
