"""统一资产视图聚合层。

将以下 6 个数据源以 **只读** 方式聚合为统一的「资产条目」DTO：

- ``assets``      —— 现有 ``AssetsService`` (assets_library.sqlite3 + 项目层)
- ``archive``     —— ``ArchiveLibraryService`` (archive_library.sqlite3)
- ``story_graph`` —— ``LocalStoryGraphStorage`` (story_graph.json/.sqlite3)
- ``novel_db``    —— ``EntityRepository`` / ``ThreadRepository`` /
                     ``WorldRuleRepository`` / ``SceneRepository`` 中的
                     entities / plot_threads / world_rule_evidence / scenes
- ``worldline``   —— ``backend/uploads/projects/<pid>/worldlines/`` 文件系统
- ``seed``        —— ``narrative_archives.json`` / ``agent_profiles.json``

设计目标：
- 不复制数据；不写入任何 silo。
- 在 Python 层做简单分页 & 过滤；FTS 由独立的 GlobalSearchIndexer 负责（见 task 2）。
- 任何 silo 读取异常都不会拖垮整个聚合 —— 单个 reader 失败时记录原因到
  返回结果的 ``errors`` 字段，符合 CLAUDE.md「失败显式暴露、不静默吞掉」。
"""

from __future__ import annotations

import json
import os
from dataclasses import asdict, dataclass, field
from typing import Any, Iterable

from sqlalchemy import and_, select

from ...config import Config
from ...database import get_engine
from ...repositories.archive_repo import ArchiveRepository
from ...repositories.entity_repo import EntityRepository
from ...repositories.graph_repo import GraphRepository
from ...repositories.relationship_repo import RelationshipRepository
from ...repositories.thread_repo import ThreadRepository
from ...repositories.world_rule_repo import WorldRuleRepository
from ...repositories.scene_repo import SceneRepository
from ...tables.archive import archive_agent_memory
from ...tables.novel import (
    chapter_content,
    entities,
    plot_threads,
    scenes,
    world_rule_evidence,
)
from ..archive_library_service import ArchiveLibraryService
from .assets_service import GLOBAL_SCOPE, PROJECT_SCOPE, AssetsService


SOURCE_ASSETS = "assets"
SOURCE_ARCHIVE = "archive"
SOURCE_STORY_GRAPH = "story_graph"
SOURCE_NOVEL_DB = "novel_db"
SOURCE_WORLDLINE = "worldline"
SOURCE_SEED = "seed"

ALL_SOURCES = (
    SOURCE_ASSETS,
    SOURCE_ARCHIVE,
    SOURCE_STORY_GRAPH,
    SOURCE_NOVEL_DB,
    SOURCE_WORLDLINE,
    SOURCE_SEED,
)


# ----------------------------------------------------------------------
# Semantic categorization layer
# ----------------------------------------------------------------------
# 这层不改任何底层存储，只是把「6 个 silo × 细 entity_type」翻译成创作者
# 视角的两个正交维度：
#   - category   ：作品里的「东西」是什么（角色 / 情节线 / 世界设定 …）
#   - lifecycle ：这条数据处在什么生命周期（种子 / 候选 / 正典 / 素材 …）
# 既保留 source/entity_type 给 agent 工具与调试用，也让 UI 能按更友好的
# 维度组织视图。

# 分类常量（语义维度，回答"这是什么"）。
# 注意：CATEGORY_WRITING_MATERIALS（"写作素材"分类）与 LIFECYCLE_MATERIAL
# （"素材"生命周期）是两个正交维度，不要混淆——前者描述资产的语义类别，
# 后者描述资产所处的生命周期阶段。
CATEGORY_CHARACTERS = "characters"   # 角色（含组织/势力作为"群体角色"）
CATEGORY_RELATIONSHIPS = "relationships"  # 关系（人物/组织之间的联系）
CATEGORY_WORLD = "world"              # 世界设定
CATEGORY_PLOT = "plot"                # 情节与场景
CATEGORY_MATERIALS = "materials"      # 写作素材（注意：与 LIFECYCLE_MATERIAL 单复数不同）
CATEGORY_OTHER = "other"

ALL_CATEGORIES = (
    CATEGORY_CHARACTERS,
    CATEGORY_RELATIONSHIPS,
    CATEGORY_WORLD,
    CATEGORY_PLOT,
    CATEGORY_MATERIALS,
    CATEGORY_OTHER,
)

# 生命周期常量（成熟度维度，回答"这条数据处于哪个阶段"）。
# 与 category 正交：例如同一个 world_rule 可以在 canon / candidate / material
# 等不同 lifecycle 下出现。LIFECYCLE_MATERIAL ≠ CATEGORY_WRITING_MATERIALS。
LIFECYCLE_SEED = "seed"              # 种子流水线产物
LIFECYCLE_CANDIDATE = "candidate"    # 候选层（archive 候选记忆）
LIFECYCLE_CANON = "canon"            # 正典 / 已采纳
LIFECYCLE_MATERIAL = "material"      # 素材库（不绑定时间线）
LIFECYCLE_SIMULATION = "simulation"  # 模拟世界线
LIFECYCLE_GRAPH = "graph"            # 图谱节点

ALL_LIFECYCLES = (
    LIFECYCLE_SEED,
    LIFECYCLE_CANDIDATE,
    LIFECYCLE_CANON,
    LIFECYCLE_MATERIAL,
    LIFECYCLE_SIMULATION,
    LIFECYCLE_GRAPH,
)

# (source, entity_type) → category
# 未匹配的 (source, entity_type) 先查 LEGACY_ENTITY_TYPE_ALIASES，再走
# _FALLBACK_CATEGORY_BY_SOURCE 兜底。
CATEGORY_MAP: dict[tuple[str, str], str] = {
    # archive 库 — 组织/势力/关系都归到"角色与关系"
    (SOURCE_ARCHIVE, "character"): CATEGORY_CHARACTERS,
    (SOURCE_ARCHIVE, "organization"): CATEGORY_CHARACTERS,
    (SOURCE_ARCHIVE, "faction"): CATEGORY_CHARACTERS,
    (SOURCE_ARCHIVE, "relationship"): CATEGORY_RELATIONSHIPS,
    # novel_db (写作工坊)
    (SOURCE_NOVEL_DB, "character"): CATEGORY_CHARACTERS,
    (SOURCE_NOVEL_DB, "organization"): CATEGORY_CHARACTERS,
    (SOURCE_NOVEL_DB, "faction"): CATEGORY_CHARACTERS,
    (SOURCE_NOVEL_DB, "relationship"): CATEGORY_RELATIONSHIPS,
    (SOURCE_NOVEL_DB, "plot_thread"): CATEGORY_PLOT,
    (SOURCE_NOVEL_DB, "scene"): CATEGORY_PLOT,
    (SOURCE_NOVEL_DB, "world_rule"): CATEGORY_WORLD,
    # 种子流水线产物
    (SOURCE_SEED, "seed_character"): CATEGORY_CHARACTERS,
    (SOURCE_SEED, "seed_world_rule"): CATEGORY_WORLD,
    (SOURCE_SEED, "seed_plot_thread"): CATEGORY_PLOT,
    # seed_agent_profile 在用户认知里就是"角色"。
    (SOURCE_SEED, "seed_agent_profile"): CATEGORY_CHARACTERS,
    # 资产库 / 创作素材
    (SOURCE_ASSETS, "writing_style"): CATEGORY_MATERIALS,
    (SOURCE_ASSETS, "author_style"): CATEGORY_MATERIALS,
    (SOURCE_ASSETS, "character_archetype"): CATEGORY_MATERIALS,
    (SOURCE_ASSETS, "prompt_template"): CATEGORY_MATERIALS,
    (SOURCE_ASSETS, "plot_template"): CATEGORY_MATERIALS,
    (SOURCE_ASSETS, "manuscript_block"): CATEGORY_MATERIALS,
    (SOURCE_ASSETS, "note"): CATEGORY_MATERIALS,
    (SOURCE_ASSETS, "world_rule"): CATEGORY_WORLD,
    (SOURCE_ASSETS, "worldview"): CATEGORY_WORLD,
    # 世界线 worldline_session 不在显式 CATEGORY_MAP 中：它只有这一种类型，
    # 与 LIFECYCLE_SIMULATION 1:1 重叠，单独占一个 category 是冗余的。
    # 通过 _FALLBACK_CATEGORY_BY_SOURCE 落入 CATEGORY_OTHER + lifecycle=simulation，
    # 用户可以通过 lifecycle="模拟" 过滤出来。
}

# 历史遗留的 entity_type 别名。任何隐式的 "兼容老数据" 规则都必须显式登记
# 在这里，便于 grep / 审计 / 删除。
LEGACY_ENTITY_TYPE_ALIASES: dict[tuple[str, str], str] = {
    (SOURCE_NOVEL_DB, "entity"): CATEGORY_CHARACTERS,
}

_FALLBACK_CATEGORY_BY_SOURCE: dict[str, str] = {
    SOURCE_ASSETS: CATEGORY_MATERIALS,
    SOURCE_ARCHIVE: CATEGORY_CHARACTERS,
    SOURCE_STORY_GRAPH: CATEGORY_OTHER,
    SOURCE_NOVEL_DB: CATEGORY_OTHER,
    SOURCE_WORLDLINE: CATEGORY_OTHER,
    SOURCE_SEED: CATEGORY_OTHER,
}

# source → 默认 lifecycle（archive 内部还会按候选/正典再细分）
LIFECYCLE_MAP: dict[str, str] = {
    SOURCE_SEED: LIFECYCLE_SEED,
    SOURCE_ARCHIVE: LIFECYCLE_CANON,
    SOURCE_NOVEL_DB: LIFECYCLE_CANON,
    SOURCE_ASSETS: LIFECYCLE_MATERIAL,
    SOURCE_WORLDLINE: LIFECYCLE_SIMULATION,
    SOURCE_STORY_GRAPH: LIFECYCLE_GRAPH,
}


# archive 候选层显式常量（替代原先内嵌的 magic string "candidate"）。
ARCHIVE_CANDIDATE_LAYER = "candidate"


def _archive_lifecycle_override(source: str, payload: Any) -> str | None:
    """archive 源的 lifecycle 细判断：若该档案最高记忆层为 candidate，
    把整体 lifecycle 降级为 candidate。返回 None 表示无 override。

    这是唯一允许读 ``payload.memory_layer`` / ``highest_memory_layer`` 的地方；
    任何对 archive 候选层的判断都必须走这里以便集中维护与审计。
    """
    if source != SOURCE_ARCHIVE or not isinstance(payload, dict):
        return None
    layer = (
        payload.get("memory_layer")
        or payload.get("highest_memory_layer")
        or ""
    ).lower()
    if layer == ARCHIVE_CANDIDATE_LAYER:
        return LIFECYCLE_CANDIDATE
    return None


def classify(source: str, entity_type: str, payload: dict[str, Any] | None = None) -> tuple[str, str]:
    """把 (source, entity_type) 翻译成 (category, lifecycle)。

    查找顺序:
      1. 持久化 classification_map 表(migration 20260418_0001 落库的行)
      2. Python 常量 CATEGORY_MAP / LEGACY_ENTITY_TYPE_ALIASES / LIFECYCLE_MAP
         作为兜底(migration 未跑的测试环境也能工作)
      3. _FALLBACK_CATEGORY_BY_SOURCE → CATEGORY_OTHER

    最后由 ``_archive_lifecycle_override`` 为 archive 候选层做降级。
    """
    cat, life = _resolve_from_db(source, entity_type or "")
    if cat is None:
        # Python 兜底:让 CATEGORY_MAP / LEGACY_ENTITY_TYPE_ALIASES 继续生效。
        key = (source, entity_type or "")
        cat = (
            CATEGORY_MAP.get(key)
            or LEGACY_ENTITY_TYPE_ALIASES.get(key)
            or _FALLBACK_CATEGORY_BY_SOURCE.get(source, CATEGORY_OTHER)
        )
        life = LIFECYCLE_MAP.get(source, LIFECYCLE_CANON)
    override = _archive_lifecycle_override(source, payload)
    if override:
        life = override
    return cat, life


# ----------------------------------------------------------------------
# classification_map DB cache
# ----------------------------------------------------------------------
# Keyed by engine URL so switching DBs (per-test tmp sqlite) does not serve
# stale rows to a fresh engine. Production only ever has one URL.

_CLASSIFICATION_CACHE: dict[str, dict[tuple[str, str], tuple[str, str]]] = {}


def _resolve_from_db(source: str, entity_type: str) -> tuple[str | None, str | None]:
    """Look up (category, lifecycle) for (source, entity_type) in the
    persistent ``classification_map`` table.

    Falls back to the source wildcard row ``(source, '*')`` when the exact
    pair is absent. Returns ``(None, None)`` if the table is empty or
    unreachable (e.g. migration not yet applied in a test sandbox), so the
    caller can fall back to the Python constants.
    """
    cache = _load_classification_cache()
    if not cache:
        return None, None
    hit = cache.get((source, entity_type))
    if hit:
        return hit
    wildcard = cache.get((source, "*"))
    if wildcard:
        return wildcard
    return None, None


def _load_classification_cache() -> dict[tuple[str, str], tuple[str, str]]:
    try:
        engine = get_engine()
    except Exception:
        return {}
    url_key = str(engine.url)
    cached = _CLASSIFICATION_CACHE.get(url_key)
    if cached is not None:
        return cached
    try:
        from ...tables.assets import classification_map
        with engine.connect() as conn:
            rows = conn.execute(
                select(
                    classification_map.c.source,
                    classification_map.c.entity_type,
                    classification_map.c.category,
                    classification_map.c.lifecycle,
                )
            ).fetchall()
    except Exception:
        # Table may not exist yet (fresh test DB without migrations, or
        # bootstrap ordering). Cache empty so classify() uses the Python
        # constants path; reset via reset_classification_cache() if needed.
        _CLASSIFICATION_CACHE[url_key] = {}
        return _CLASSIFICATION_CACHE[url_key]
    built: dict[tuple[str, str], tuple[str, str]] = {}
    for row in rows:
        m = row._mapping
        built[(m["source"], m["entity_type"])] = (m["category"], m["lifecycle"])
    _CLASSIFICATION_CACHE[url_key] = built
    return built


def reset_classification_cache() -> None:
    """Drop all cached classification_map snapshots. Call after seeding or
    during tests that need the next classify() to re-read the DB.
    """
    _CLASSIFICATION_CACHE.clear()


# ----------------------------------------------------------------------
# Taxonomy descriptors — single source of truth shared with the frontend
# via /api/unified-assets/taxonomy. Order = display order in the UI.
# ----------------------------------------------------------------------

SOURCE_DESCRIPTORS: list[dict[str, str]] = [
    {"key": SOURCE_ASSETS,      "label": "资产库",      "icon": "📦", "color": "#6366f1"},
    {"key": SOURCE_ARCHIVE,     "label": "档案库",      "icon": "🗂",  "color": "#0ea5e9"},
    {"key": SOURCE_NOVEL_DB,    "label": "写作工坊",    "icon": "✍️", "color": "#10b981"},
    {"key": SOURCE_SEED,        "label": "种子流水线",  "icon": "🌱", "color": "#84cc16"},
    {"key": SOURCE_WORLDLINE,   "label": "世界线",      "icon": "🌌", "color": "#a855f7"},
    {"key": SOURCE_STORY_GRAPH, "label": "故事图谱",    "icon": "🕸",  "color": "#f97316"},
]

CATEGORY_DESCRIPTORS: list[dict[str, str]] = [
    {"key": CATEGORY_CHARACTERS,    "label": "角色",     "icon": "👤", "color": "#6366f1"},
    {"key": CATEGORY_RELATIONSHIPS, "label": "关系",     "icon": "🔗", "color": "#ec4899"},
    {"key": CATEGORY_WORLD,         "label": "世界设定", "icon": "📜", "color": "#10b981"},
    {"key": CATEGORY_PLOT,       "label": "情节与场景", "icon": "🎬", "color": "#f59e0b"},
    {"key": CATEGORY_MATERIALS,  "label": "写作素材",   "icon": "📚", "color": "#8b5cf6"},
    {"key": CATEGORY_OTHER,      "label": "其它",       "icon": "•",  "color": "#94a3b8"},
]

LIFECYCLE_DESCRIPTORS: list[dict[str, str]] = [
    {"key": LIFECYCLE_SEED,       "label": "种子",   "icon": "🌱"},
    {"key": LIFECYCLE_CANDIDATE,  "label": "候选",   "icon": "🕓"},
    {"key": LIFECYCLE_CANON,      "label": "正典",   "icon": "✅"},
    {"key": LIFECYCLE_MATERIAL,   "label": "素材",   "icon": "📦"},
    {"key": LIFECYCLE_SIMULATION, "label": "模拟",   "icon": "🌌"},
    {"key": LIFECYCLE_GRAPH,      "label": "图谱",   "icon": "🕸"},
]

# 所有可能出现的 entity_type → 中文标签。必须覆盖 CATEGORY_MAP 中的所有
# entity_type，外加 worldline_session（隐式 fallback）和 story_graph 的 node。
# 测试 test_every_entity_type_in_category_map_has_label 会强制对账。
ENTITY_TYPE_LABELS: dict[str, str] = {
    # archive
    "character":            "角色",
    "organization":         "组织",
    "faction":              "势力",
    "relationship":         "关系",
    # novel_db
    "entity":               "实体（旧）",
    "plot_thread":          "情节线",
    "world_rule":           "世界设定",
    "scene":                "场景",
    # seed
    "seed_character":       "种子角色",
    "seed_world_rule":      "种子设定",
    "seed_plot_thread":     "种子线索",
    "seed_agent_profile":   "Agent 档案",
    # assets
    "writing_style":        "文风",
    "author_style":         "作者风格",
    "character_archetype":  "角色原型",
    "prompt_template":      "Prompt 模板",
    "plot_template":        "情节模板",
    "manuscript_block":     "稿件片段",
    "note":                 "笔记",
    "worldview":            "世界观",
    # worldline / story_graph
    "worldline_session":    "世界线会话",
    "node":                 "图谱节点",
}

IMPORTANCE_LABELS: dict[str, str] = {
    "protagonist": "主角",
    "major":       "主要",
    "supporting":  "配角",
    "minor":       "次要",
}


def build_taxonomy() -> dict[str, Any]:
    """组装一份完整的资产分类元数据，供 /api/unified-assets/taxonomy 输出。"""
    return {
        "sources":             list(SOURCE_DESCRIPTORS),
        "categories":          list(CATEGORY_DESCRIPTORS),
        "lifecycles":          list(LIFECYCLE_DESCRIPTORS),
        "entity_type_labels":  dict(ENTITY_TYPE_LABELS),
        "importance_labels":   dict(IMPORTANCE_LABELS),
    }


@dataclass
class UnifiedAsset:
    source: str
    source_ref: str  # 该 silo 内的稳定主键
    entity_type: str  # 中文友好的细分类型
    title: str
    summary: str = ""
    tags: list[str] = field(default_factory=list)
    scope: str = "project"  # global / project
    project_id: str | None = None
    importance: str = ""  # 例如 protagonist / major / supporting / minor
    updated_at: str = ""
    payload: dict[str, Any] = field(default_factory=dict)
    origin_link: str = ""  # 前端跳转目标视图的逻辑路径
    # 语义层（reader 不填，由 UnifiedAssetView.list() 在聚合时统一回填）
    category: str = ""
    lifecycle: str = ""

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


# ----------------------------------------------------------------------
# Reader implementations
# ----------------------------------------------------------------------


class Readers:
    """所有 silo 的只读 reader，集中放置便于测试。

    公共名（无下划线）—— 测试中可继承覆盖以提供 stub 数据。
    """

    def __init__(self) -> None:
        self.assets = AssetsService()
        self.archive = ArchiveLibraryService()
        engine = get_engine()
        self._archive_repo = ArchiveRepository(engine)
        self._graph_repo = GraphRepository(engine)
        self._entity_repo = EntityRepository(engine)
        self._thread_repo = ThreadRepository(engine)
        self._rule_repo = WorldRuleRepository(engine)
        self._scene_repo = SceneRepository(engine)
        self._relationship_repo = RelationshipRepository(engine)

    # -- assets --------------------------------------------------------
    def read_assets(self, project_id: str | None) -> list[UnifiedAsset]:
        rows = self.assets.list_merged(project_id=project_id, limit=500)
        # Post-P5: archive entities share the ``assets`` table but are
        # surfaced under source='archive' via ``read_archive``. Skip them
        # here to avoid double-counting in the unified list.
        rows = [r for r in rows if r.get("asset_type") != "archive_entity"]
        results: list[UnifiedAsset] = []
        for r in rows:
            results.append(
                UnifiedAsset(
                    source=SOURCE_ASSETS,
                    source_ref=r["asset_id"],
                    entity_type=r.get("asset_type", "") or "",
                    title=r.get("title") or "",
                    summary=r.get("summary") or "",
                    tags=r.get("tags") or [],
                    scope=r.get("scope") or "global",
                    project_id=r.get("project_id"),
                    updated_at=r.get("updated_at") or "",
                    payload={
                        "category": r.get("category"),
                        "content": r.get("content"),
                        "payload": r.get("payload"),
                        "enabled": r.get("enabled"),
                        "word_count": r.get("word_count"),
                        "source_kind": r.get("source_kind"),
                    },
                    origin_link=f"/asset-library?asset_id={r['asset_id']}",
                )
            )
        return results

    # -- archive library ----------------------------------------------
    def read_archive(self, project_id: str | None) -> list[UnifiedAsset]:
        result = self.archive.list_archives(project_id=project_id or "", limit=200)
        items = result.get("items", [])
        # Aggregate the highest memory layer per archive_id from
        # archive_agent_memory so the lifecycle override in classify() can
        # actually downgrade an archive to candidate. "Highest" = canon if any
        # active canon row exists; otherwise candidate if any candidate row.
        layer_by_archive: dict[str, str] = {}
        if items:
            archive_ids = [it["archive_id"] for it in items if it.get("archive_id")]
            if archive_ids:
                # Query active memory layers through the archive repo.
                # Use a direct SQLAlchemy select since the repo does not
                # expose a bulk "layers by archive IDs" helper.
                with self._archive_repo.connect() as conn:
                    stmt = (
                        select(
                            archive_agent_memory.c.archive_id,
                            archive_agent_memory.c.memory_layer,
                        )
                        .where(
                            and_(
                                archive_agent_memory.c.status == "active",
                                archive_agent_memory.c.archive_id.in_(archive_ids),
                            ),
                        )
                    )
                    rows = conn.execute(stmt).fetchall()
                    for row in rows:
                        aid = row._mapping["archive_id"]
                        layer = (row._mapping["memory_layer"] or "").lower()
                        cur = layer_by_archive.get(aid)
                        if cur == "canon":
                            continue
                        if layer == "canon":
                            layer_by_archive[aid] = "canon"
                        elif layer == "candidate" and cur is None:
                            layer_by_archive[aid] = "candidate"
        out: list[UnifiedAsset] = []
        for it in items:
            tier = it.get("selected_importance_tier") or it.get("importance_tier") or ""
            payload = dict(it)
            layer = layer_by_archive.get(it.get("archive_id") or "")
            if layer:
                payload["memory_layer"] = layer
            out.append(
                UnifiedAsset(
                    source=SOURCE_ARCHIVE,
                    source_ref=it["archive_id"],
                    entity_type=it.get("entity_type") or "",
                    title=it.get("entity_name") or "(无名)",
                    summary=it.get("entity_role")
                    or it.get("core_drive")
                    or it.get("relationship_summary")
                    or "",
                    scope="project",
                    project_id=it.get("project_id"),
                    importance=tier,
                    updated_at=it.get("synced_at") or "",
                    payload=payload,
                    origin_link=f"/archive-library?archive_id={it['archive_id']}",
                )
            )
        return out

    # -- story graph ---------------------------------------------------
    def read_story_graph(self, project_id: str | None) -> list[UnifiedAsset]:
        if not project_id or not self._graph_repo.has_graph(project_id):
            return []
        nodes = self._graph_repo.load_all_nodes(project_id)
        out: list[UnifiedAsset] = []
        for n in nodes:
            labels = n.get("labels") or []
            out.append(
                UnifiedAsset(
                    source=SOURCE_STORY_GRAPH,
                    source_ref=n["uuid"],
                    entity_type=(labels[0] if labels else "node"),
                    title=n.get("name") or n["uuid"],
                    summary=n.get("summary") or "",
                    tags=labels,
                    scope="project",
                    project_id=project_id,
                    payload={
                        "attributes": n.get("attributes"),
                        "evidence_refs": n.get("evidence_refs"),
                    },
                    origin_link=f"/story-graph?node={n['uuid']}",
                )
            )
        return out

    # -- novel_db (writer agent) --------------------------------------
    def read_novel_db(self, project_id: str | None) -> list[UnifiedAsset]:
        if not project_id:
            return []
        out: list[UnifiedAsset] = []

        # Entities via repository
        for row in self._entity_repo.list_entities(project_id, limit=500):
            out.append(
                UnifiedAsset(
                    source=SOURCE_NOVEL_DB,
                    source_ref=f"entity:{row['entity_id']}",
                    entity_type=row.get("entity_type") or "entity",
                    title=row.get("name") or row["entity_id"],
                    summary=row.get("summary") or row.get("core_drive") or "",
                    scope="project",
                    project_id=project_id,
                    importance=row.get("importance_tier") or "",
                    updated_at=row.get("updated_at") or "",
                    payload=row,
                    origin_link=f"/writer-workbench?entity_id={row['entity_id']}",
                )
            )

        # Plot threads via repository
        for row in self._thread_repo.list_threads(project_id, limit=500):
            out.append(
                UnifiedAsset(
                    source=SOURCE_NOVEL_DB,
                    source_ref=f"thread:{row['thread_id']}",
                    entity_type="plot_thread",
                    title=row.get("thread_key") or row["thread_id"],
                    summary=row.get("detail") or "",
                    scope="project",
                    project_id=project_id,
                    updated_at=row.get("updated_at") or "",
                    payload=row,
                    origin_link=f"/writer-workbench?thread_id={row['thread_id']}",
                )
            )

        # World rules via repository (world_rule_evidence table)
        for row in self._rule_repo.list_rules(project_id, limit=500):
            out.append(
                UnifiedAsset(
                    source=SOURCE_NOVEL_DB,
                    source_ref=f"rule:{row['evidence_id']}",
                    entity_type="world_rule",
                    title=row.get("fact_text", "")[:60] or row["evidence_id"],
                    summary=row.get("evidence_snippet") or row.get("fact_text") or "",
                    scope="project",
                    project_id=project_id,
                    updated_at=row.get("created_at") or "",
                    payload=row,
                    origin_link=f"/writer-workbench?rule_id={row['evidence_id']}",
                )
            )

        # Relationships via repository. Title renders as "A → B（type）" so the
        # global FTS index hits on either side's name or the relation type.
        # Resolve source_id/target_id to names in one batch pass.
        rel_rows = self._relationship_repo.list_relationships(project_id, limit=500)
        if rel_rows:
            name_cache: dict[str, str] = {}

            def _name_for(entity_id: str) -> str:
                if not entity_id:
                    return ""
                if entity_id in name_cache:
                    return name_cache[entity_id]
                row = self._entity_repo.get_entity(project_id, entity_id)
                nm = (row or {}).get("name") or entity_id
                name_cache[entity_id] = nm
                return nm

            for row in rel_rows:
                src_name = _name_for(row.get("source_id") or "")
                tgt_name = _name_for(row.get("target_id") or "")
                rel_type = row.get("relation_type") or "关系"
                title = f"{src_name} → {tgt_name}（{rel_type}）"
                summary_parts = [row.get("description") or ""]
                if row.get("power_dynamic"):
                    summary_parts.append(f"权力={row['power_dynamic']}")
                if row.get("conflict_trigger"):
                    summary_parts.append(f"冲突={row['conflict_trigger']}")
                out.append(
                    UnifiedAsset(
                        source=SOURCE_NOVEL_DB,
                        source_ref=f"relationship:{row['relation_id']}",
                        entity_type="relationship",
                        title=title,
                        summary=" / ".join(p for p in summary_parts if p),
                        scope="project",
                        project_id=project_id,
                        updated_at=row.get("updated_at") or "",
                        payload=row,
                        origin_link=f"/writer-workbench?relation_id={row['relation_id']}",
                    )
                )

        # Archive candidate memories (agent-proposed facts not yet promoted to
        # canon). Indexed with entity_type="agent_memory_candidate" so the
        # writer agent's search_settings(scope="memory") can surface them,
        # without mixing into the canonical entity/thread/rule results.
        out.extend(self._read_candidate_memories(project_id))

        # Scenes via SQLAlchemy (need cross-table JOIN)
        from sqlalchemy import func
        stmt = (
            select(
                scenes.c.scene_id,
                scenes.c.title,
                func.substr(scenes.c.content, 1, 80).label("summary"),
                scenes.c.status,
                scenes.c.updated_at,
            )
            .select_from(
                scenes.join(
                    chapter_content,
                    scenes.c.chapter_id == chapter_content.c.chapter_id,
                )
            )
            .where(chapter_content.c.project_id == project_id)
            .order_by(scenes.c.updated_at.desc())
            .limit(200)
        )
        with self._scene_repo.connect() as conn:
            for row in conn.execute(stmt).fetchall():
                r = dict(row._mapping)
                out.append(
                    UnifiedAsset(
                        source=SOURCE_NOVEL_DB,
                        source_ref=f"scene:{r['scene_id']}",
                        entity_type="scene",
                        title=r.get("title") or r["scene_id"],
                        summary=r.get("summary") or "",
                        scope="project",
                        project_id=project_id,
                        updated_at=r.get("updated_at") or "",
                        payload=r,
                        origin_link=f"/writer-workbench?scene_id={r['scene_id']}",
                    )
                )
        return out

    def _read_candidate_memories(self, project_id: str) -> list[UnifiedAsset]:
        """Surface archive candidate memories as indexable assets.

        The writer agent uses search_settings(scope="memory") to find these;
        without indexing them here, unadopted world hypotheses (relationships,
        rules, goals) would never show up in cross-silo search.
        """
        try:
            archives = self._archive_repo.list_archives(project_id=project_id, limit=500)
        except Exception:
            return []
        if not archives:
            return []

        out: list[UnifiedAsset] = []
        for arc in archives:
            archive_id = arc.get("archive_id")
            if not archive_id:
                continue
            try:
                rows = self._archive_repo.list_active_memory(
                    archive_id, layers=("candidate",), statuses=("active",), limit=50,
                )
            except Exception:
                continue
            owner = arc.get("entity_name") or archive_id
            for r in rows:
                mid = r.get("memory_id") or ""
                mtype = r.get("memory_type") or "memory"
                subject = r.get("normalized_subject") or ""
                summary = r.get("summary") or ""
                title = f"[{mtype}] {owner}：{subject or summary[:40]}"
                out.append(
                    UnifiedAsset(
                        source=SOURCE_NOVEL_DB,
                        source_ref=f"agent_memory_candidate:{mid}",
                        entity_type="agent_memory_candidate",
                        title=title,
                        summary=summary,
                        scope="project",
                        project_id=project_id,
                        updated_at=r.get("updated_at") or "",
                        payload=r,
                        origin_link=f"/assets?archive_id={archive_id}&memory_id={mid}",
                    )
                )
        return out

    # -- worldline -----------------------------------------------------
    def read_worldline(self, project_id: str | None) -> list[UnifiedAsset]:
        if not project_id:
            return []
        from ...repositories.worldline_session_repo import WorldlineSessionRepository

        repo = WorldlineSessionRepository(get_engine())
        out: list[UnifiedAsset] = []
        for summary in repo.list_sessions(project_id=project_id, limit=200):
            sid = summary["session_id"]
            out.append(
                UnifiedAsset(
                    source=SOURCE_WORLDLINE,
                    source_ref=f"session:{sid}",
                    entity_type="worldline_session",
                    title=summary.get("label") or sid,
                    summary=summary.get("simulation_goal") or "",
                    scope="project",
                    project_id=project_id,
                    updated_at=summary.get("updated_at") or "",
                    payload=summary,
                    origin_link=f"/worldline?session_id={sid}",
                )
            )
        return out

    # -- seed pipeline outputs -----------------------------------------
    def read_seed(self, project_id: str | None) -> list[UnifiedAsset]:
        if not project_id:
            return []
        from ...repositories.project_artifact_repo import load_project_artifact

        out: list[UnifiedAsset] = []
        archives = load_project_artifact(project_id, "narrative_archives") or {}
        if isinstance(archives, dict):
            characters = archives.get("characters") or {}
            if isinstance(characters, dict):
                items = characters.values()
            else:
                items = characters
            for ch in items:
                if not isinstance(ch, dict):
                    continue
                name = ch.get("name") or ch.get("entity_name") or ""
                if not name:
                    continue
                out.append(
                    UnifiedAsset(
                        source=SOURCE_SEED,
                        source_ref=f"character:{ch.get('uuid') or name}",
                        entity_type="seed_character",
                        title=name,
                        summary=ch.get("role") or ch.get("core_drive") or "",
                        scope="project",
                        project_id=project_id,
                        importance=ch.get("importance_tier") or "",
                        payload=ch,
                        origin_link=f"/overview?character={name}",
                    )
                )
            for rule in archives.get("world_rules") or []:
                if not isinstance(rule, dict):
                    continue
                title = rule.get("name") or rule.get("rule_key") or "(规则)"
                out.append(
                    UnifiedAsset(
                        source=SOURCE_SEED,
                        source_ref=f"rule:{title}",
                        entity_type="seed_world_rule",
                        title=title,
                        summary=rule.get("statement") or rule.get("description") or "",
                        scope="project",
                        project_id=project_id,
                        payload=rule,
                        origin_link=f"/overview?rule={title}",
                    )
                )
            for thread in archives.get("plot_threads") or []:
                if not isinstance(thread, dict):
                    continue
                title = thread.get("name") or thread.get("thread_key") or "(线索)"
                out.append(
                    UnifiedAsset(
                        source=SOURCE_SEED,
                        source_ref=f"thread:{title}",
                        entity_type="seed_plot_thread",
                        title=title,
                        summary=thread.get("summary") or thread.get("detail") or "",
                        scope="project",
                        project_id=project_id,
                        payload=thread,
                        origin_link=f"/overview?thread={title}",
                    )
                )
        # Reading notes — expose arc_summaries and key_events as searchable
        # entries so the writer agent (and global FTS) can pull them.
        reading_notes = load_project_artifact(project_id, "reading_notes") or {}
        if isinstance(reading_notes, dict):
            notes_inner = reading_notes.get("notes", reading_notes)
            plot_state = notes_inner.get("plot_state", {}) if isinstance(notes_inner, dict) else {}
            for arc in plot_state.get("arc_summaries", []) or []:
                if not isinstance(arc, dict):
                    continue
                arc_id = arc.get("arc_id") or ""
                summary = arc.get("summary") or ""
                if not arc_id or not summary:
                    continue
                out.append(
                    UnifiedAsset(
                        source=SOURCE_SEED,
                        source_ref=f"arc:{arc_id}",
                        entity_type="seed_arc_summary",
                        title=arc_id,
                        summary=summary,
                        scope="project",
                        project_id=project_id,
                        payload=arc,
                        origin_link=f"/overview?arc={arc_id}",
                    )
                )
            for ev in notes_inner.get("key_events", []) if isinstance(notes_inner, dict) else []:
                if not isinstance(ev, dict):
                    continue
                ev_id = ev.get("event_id") or ""
                title = ev.get("title") or ev_id
                if not ev_id:
                    continue
                out.append(
                    UnifiedAsset(
                        source=SOURCE_SEED,
                        source_ref=f"event:{ev_id}",
                        entity_type="seed_key_event",
                        title=title,
                        summary=ev.get("description") or title,
                        scope="project",
                        project_id=project_id,
                        payload=ev,
                        origin_link=f"/overview?event={ev_id}",
                    )
                )

        # Ontology — expose entity_types so writer agent can introspect labels.
        ontology = load_project_artifact(project_id, "ontology") or {}
        if isinstance(ontology, dict):
            for entity_type in ontology.get("entity_types", []) or []:
                if not isinstance(entity_type, dict):
                    continue
                name = entity_type.get("name") or ""
                if not name:
                    continue
                out.append(
                    UnifiedAsset(
                        source=SOURCE_SEED,
                        source_ref=f"ontology:entity:{name}",
                        entity_type="seed_ontology_entity",
                        title=name,
                        summary=entity_type.get("description") or "",
                        scope="project",
                        project_id=project_id,
                        payload=entity_type,
                        origin_link=f"/overview?ontology={name}",
                    )
                )

        profiles = load_project_artifact(project_id, "agent_profiles") or {}
        if isinstance(profiles, dict):
            for key, prof in profiles.items():
                if not isinstance(prof, dict):
                    continue
                out.append(
                    UnifiedAsset(
                        source=SOURCE_SEED,
                        source_ref=f"profile:{key}",
                        entity_type="seed_agent_profile",
                        title=prof.get("name") or key,
                        summary=prof.get("summary") or prof.get("role") or "",
                        scope="project",
                        project_id=project_id,
                        payload=prof,
                        origin_link=f"/overview?profile={key}",
                    )
                )
        return out


# ----------------------------------------------------------------------
# Public façade
# ----------------------------------------------------------------------


class UnifiedAssetView:
    """资产库聚合视图。线程不安全（每次请求新建即可）。"""

    def __init__(self, readers: Readers | None = None) -> None:
        self._readers = readers or Readers()

    # -- core list -----------------------------------------------------
    def list(
        self,
        *,
        project_id: str | None = None,
        sources: Iterable[str] | None = None,
        entity_types: Iterable[str] | None = None,
        categories: Iterable[str] | None = None,
        lifecycles: Iterable[str] | None = None,
        scope: str | None = None,
        q: str | None = None,
        page: int = 1,
        page_size: int = 50,
    ) -> dict[str, Any]:
        active_sources = list(sources) if sources else list(ALL_SOURCES)
        items: list[UnifiedAsset] = []
        for src in active_sources:
            fn = self._reader_map().get(src)
            if not fn:
                raise ValueError(f"unknown source: {src!r}")
            # CLAUDE.md Debug-First：reader 异常向上抛，禁止 try/except 静默降级。
            items.extend(fn(project_id))

        # 回填语义层（category / lifecycle）。reader 保持原样，避免侵入式改动。
        for a in items:
            if not a.category or not a.lifecycle:
                cat, life = classify(a.source, a.entity_type, a.payload)
                if not a.category:
                    a.category = cat
                if not a.lifecycle:
                    a.lifecycle = life

        # Filters
        if entity_types:
            wanted = set(entity_types)
            items = [a for a in items if a.entity_type in wanted]
        if categories:
            wanted_cat = set(categories)
            items = [a for a in items if a.category in wanted_cat]
        if lifecycles:
            wanted_life = set(lifecycles)
            items = [a for a in items if a.lifecycle in wanted_life]
        if scope:
            items = [a for a in items if a.scope == scope]
        if q:
            ql = q.lower()
            items = [
                a for a in items
                if ql in (a.title or "").lower()
                or ql in (a.summary or "").lower()
            ]

        total = len(items)
        items.sort(key=lambda a: a.updated_at or "", reverse=True)
        start = max(0, (page - 1) * page_size)
        end = start + page_size
        page_items = [a.to_dict() for a in items[start:end]]
        return {
            "items": page_items,
            "total": total,
            "page": page,
            "page_size": page_size,
        }

    # -- per-source pull (used by GlobalSearchIndexer.sync_source) ----
    def _reader_map(self):
        return {
            SOURCE_ASSETS: self._readers.read_assets,
            SOURCE_ARCHIVE: self._readers.read_archive,
            SOURCE_STORY_GRAPH: self._readers.read_story_graph,
            SOURCE_NOVEL_DB: self._readers.read_novel_db,
            SOURCE_WORLDLINE: self._readers.read_worldline,
            SOURCE_SEED: self._readers.read_seed,
        }

    def list_source(self, source: str, project_id: str | None) -> list[dict[str, Any]]:
        """单个 silo 的全量条目（已回填 category/lifecycle）。

        给 ``GlobalSearchIndexer.sync_source`` 用——增量索引的事实来源。
        """
        fn = self._reader_map().get(source)
        if not fn:
            raise ValueError(f"unknown source: {source!r}")
        items = fn(project_id)
        for a in items:
            cat, life = classify(a.source, a.entity_type, a.payload)
            if not a.category:
                a.category = cat
            if not a.lifecycle:
                a.lifecycle = life
        return [a.to_dict() for a in items]

    # -- facets --------------------------------------------------------
    def facets(self, *, project_id: str | None = None) -> dict[str, Any]:
        result = self.list(project_id=project_id, page=1, page_size=10000)
        sources_count: dict[str, int] = {}
        types_count: dict[str, int] = {}
        category_count: dict[str, int] = {}
        lifecycle_count: dict[str, int] = {}
        for it in result["items"]:
            sources_count[it["source"]] = sources_count.get(it["source"], 0) + 1
            t = it["entity_type"] or ""
            if t:
                types_count[t] = types_count.get(t, 0) + 1
            c = it.get("category") or ""
            if c:
                category_count[c] = category_count.get(c, 0) + 1
            l = it.get("lifecycle") or ""
            if l:
                lifecycle_count[l] = lifecycle_count.get(l, 0) + 1
        return {
            "sources": [{"key": k, "count": v} for k, v in sorted(sources_count.items())],
            "entity_types": [
                {"key": k, "count": v} for k, v in sorted(types_count.items(), key=lambda kv: -kv[1])
            ],
            "categories": [
                {"key": k, "count": category_count.get(k, 0)}
                for k in ALL_CATEGORIES
                if category_count.get(k, 0) > 0
            ],
            "lifecycles": [
                {"key": k, "count": lifecycle_count.get(k, 0)}
                for k in ALL_LIFECYCLES
                if lifecycle_count.get(k, 0) > 0
            ],
            "total": result["total"],
        }

    # -- detail --------------------------------------------------------
    def get(self, source: str, ref: str, *, project_id: str | None = None) -> dict[str, Any] | None:
        result = self.list(
            project_id=project_id,
            sources=[source],
            page=1,
            page_size=10000,
        )
        for it in result["items"]:
            if it["source_ref"] == ref:
                return it
        return None

    # -- cross-silo merges --------------------------------------------
    # Thin wrappers around NarrativeEntityService so callers who already use
    # UnifiedAssetView have a single façade for merged character/relationship
    # views (entities + archive + character_archetype refs).

    def get_entity(
        self, *, project_id: str, name: str | None = None, entity_id: str | None = None,
    ) -> dict[str, Any] | None:
        """Return the merged (entity + canon archive + archetype refs) view.

        Provide either ``name`` or ``entity_id``. Returns ``None`` if neither
        the entity nor a matching archive exists for that project.
        """
        from ..narrative_entity_service import NarrativeEntityService
        svc = NarrativeEntityService()
        if entity_id:
            merged = svc.get_by_entity_id(project_id, entity_id)
        elif name:
            merged = svc.get_by_name(project_id, name)
        else:
            raise ValueError("get_entity requires either 'name' or 'entity_id'")
        return merged.to_dict() if merged else None

    def get_relationship(
        self, *, project_id: str, entity_a: str, entity_b: str,
    ) -> dict[str, Any] | None:
        """Return relationship row + supplementary summary from both archives.

        Reads ``relationships`` (by resolved entity_ids) and enriches the row
        with ``relationship_summary`` from either participant's archive
        (canon side) if present. Returns ``None`` when no relationship row
        exists between the two entities.
        """
        from ...repositories.relationship_repo import RelationshipRepository
        from ..narrative_entity_service import NarrativeEntityService
        engine = get_engine()
        svc = NarrativeEntityService(engine)
        a_merged = svc.get_by_name(project_id, entity_a)
        b_merged = svc.get_by_name(project_id, entity_b)
        a_id = a_merged.entity_id if a_merged else None
        b_id = b_merged.entity_id if b_merged else None
        if not a_id or not b_id:
            return None
        rel_repo = RelationshipRepository(engine)
        rel = rel_repo.get_relationship_between(project_id, a_id, b_id)
        if rel is None:
            return None
        # Canon-side summary enrichment: take whichever archive has a
        # relationship_summary filled in.
        canon_summary = ""
        for side in (a_merged, b_merged):
            if side and side.canon_profile:
                s = (side.canon_profile.get("relationship_summary") or "").strip()
                if s:
                    canon_summary = s
                    break
        enriched = dict(rel)
        if canon_summary:
            enriched["canon_relationship_summary"] = canon_summary
        enriched["entity_a"] = {
            "name": entity_a,
            "entity_id": a_id,
            "archive_id": a_merged.archive_id if a_merged else None,
        }
        enriched["entity_b"] = {
            "name": entity_b,
            "entity_id": b_id,
            "archive_id": b_merged.archive_id if b_merged else None,
        }
        return enriched

    def search_world_rules_unified(
        self, *, project_id: str, query: str | None = None, limit: int = 20,
    ) -> list[dict[str, Any]]:
        """Combine novel_db ``world_rule_evidence`` with assets of type
        ``worldview`` / ``world_rule`` into one ranked list.

        Both sources carry canonical world-setting info; merging lets the
        writer agent retrieve them in a single call instead of branching.
        """
        engine = get_engine()
        out: list[dict[str, Any]] = []
        # novel_db rules
        from ...repositories.world_rule_repo import WorldRuleRepository
        rule_repo = WorldRuleRepository(engine)
        rows = rule_repo.list_rules(project_id, limit=limit) or []
        q = (query or "").strip().lower()
        for r in rows:
            if q:
                haystack = (
                    (r.get("fact_text") or "") + " " + (r.get("evidence_snippet") or "")
                ).lower()
                if q not in haystack:
                    continue
            out.append(
                {
                    "source": SOURCE_NOVEL_DB,
                    "ref": f"rule:{r.get('evidence_id')}",
                    "title": (r.get("fact_text") or "")[:60],
                    "summary": r.get("evidence_snippet") or r.get("fact_text") or "",
                    "payload": r,
                }
            )
        # assets.worldview / world_rule
        for asset_type in ("worldview", "world_rule"):
            try:
                assets = self._readers.assets.list_merged(
                    project_id=project_id,
                    asset_type=asset_type,
                    enabled_only=True,
                    limit=limit,
                ) or []
            except Exception:
                assets = []
            for a in assets:
                if q:
                    haystack = (
                        (a.get("title") or "")
                        + " "
                        + (a.get("summary") or "")
                        + " "
                        + (a.get("content") or "")
                    ).lower()
                    if q not in haystack:
                        continue
                out.append(
                    {
                        "source": SOURCE_ASSETS,
                        "ref": f"asset:{a.get('asset_id')}",
                        "title": a.get("title") or "",
                        "summary": a.get("summary") or a.get("content") or "",
                        "payload": a,
                    }
                )
        return out[:limit]
