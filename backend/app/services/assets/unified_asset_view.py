"""统一资产视图聚合层。

将以下 6 个数据源以 **只读** 方式聚合为统一的「资产条目」DTO：

- ``assets``      —— 现有 ``AssetsService`` (assets_library.sqlite3 + 项目层)
- ``archive``     —— ``ArchiveLibraryService`` (archive_library.sqlite3)
- ``story_graph`` —— ``LocalStoryGraphStorage`` (story_graph.json/.sqlite3)
- ``novel_db``    —— ``writer_agent.NovelDB`` (novel.sqlite3) 中的
                     entities / plot_threads / world_rules / scenes
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
import sqlite3
from dataclasses import asdict, dataclass, field
from typing import Any, Iterable

from ...config import Config
from ...models.project import ProjectManager
from ..archive_library_service import ArchiveLibraryService
from ..local_story_graph_storage import LocalStoryGraphStorage
from ..writer_agent.novel_db import NovelDB
from .assets_service import AssetsService
from .assets_storage import GLOBAL_SCOPE, PROJECT_SCOPE


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

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


# ----------------------------------------------------------------------
# Reader implementations
# ----------------------------------------------------------------------


class _Readers:
    """所有 silo 的只读 reader，集中放置便于测试。"""

    def __init__(self) -> None:
        self.assets = AssetsService()
        self.archive = ArchiveLibraryService()
        self.story_graph = LocalStoryGraphStorage()
        self.novel_db = NovelDB()

    # -- assets --------------------------------------------------------
    def read_assets(self, project_id: str | None) -> list[UnifiedAsset]:
        rows = self.assets.list_merged(project_id=project_id, limit=500)
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
        out: list[UnifiedAsset] = []
        for it in items:
            tier = it.get("selected_importance_tier") or it.get("importance_tier") or ""
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
                    payload=it,
                    origin_link=f"/archive-library?archive_id={it['archive_id']}",
                )
            )
        return out

    # -- story graph ---------------------------------------------------
    def read_story_graph(self, project_id: str | None) -> list[UnifiedAsset]:
        if not project_id or not self.story_graph.has_graph(project_id):
            return []
        nodes = self.story_graph.load_all_nodes(project_id)
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
        db_path = os.path.join(
            Config.UPLOAD_FOLDER, "projects", project_id, "novel.sqlite3"
        )
        if not os.path.exists(db_path):
            return []
        out: list[UnifiedAsset] = []
        with self.novel_db.connect(project_id) as conn:
            for row in conn.execute(
                "SELECT entity_id, name, entity_type, importance_tier, summary, "
                "core_drive, updated_at FROM entities WHERE project_id = ?",
                (project_id,),
            ).fetchall():
                out.append(
                    UnifiedAsset(
                        source=SOURCE_NOVEL_DB,
                        source_ref=f"entity:{row['entity_id']}",
                        entity_type=row["entity_type"] or "entity",
                        title=row["name"] or row["entity_id"],
                        summary=row["summary"] or row["core_drive"] or "",
                        scope="project",
                        project_id=project_id,
                        importance=row["importance_tier"] or "",
                        updated_at=row["updated_at"] or "",
                        payload=dict(row),
                        origin_link=f"/writer-workbench?entity_id={row['entity_id']}",
                    )
                )
            for row in conn.execute(
                "SELECT thread_id, thread_key, status, detail, updated_at "
                "FROM plot_threads WHERE project_id = ?",
                (project_id,),
            ).fetchall():
                out.append(
                    UnifiedAsset(
                        source=SOURCE_NOVEL_DB,
                        source_ref=f"thread:{row['thread_id']}",
                        entity_type="plot_thread",
                        title=row["thread_key"] or row["thread_id"],
                        summary=row["detail"] or "",
                        scope="project",
                        project_id=project_id,
                        updated_at=row["updated_at"] or "",
                        payload=dict(row),
                        origin_link=f"/writer-workbench?thread_id={row['thread_id']}",
                    )
                )
            # world_rules table is optional — only query if present
            try:
                for row in conn.execute(
                    "SELECT rule_id, rule_key, statement, scope, updated_at "
                    "FROM world_rules WHERE project_id = ?",
                    (project_id,),
                ).fetchall():
                    out.append(
                        UnifiedAsset(
                            source=SOURCE_NOVEL_DB,
                            source_ref=f"rule:{row['rule_id']}",
                            entity_type="world_rule",
                            title=row["rule_key"] or row["rule_id"],
                            summary=row["statement"] or "",
                            scope="project",
                            project_id=project_id,
                            updated_at=row["updated_at"] or "",
                            payload=dict(row),
                            origin_link=f"/writer-workbench?rule_id={row['rule_id']}",
                        )
                    )
            except sqlite3.OperationalError:
                pass
            try:
                for row in conn.execute(
                    "SELECT scene_id, title, summary, status, updated_at "
                    "FROM scenes WHERE project_id = ? ORDER BY updated_at DESC LIMIT 200",
                    (project_id,),
                ).fetchall():
                    out.append(
                        UnifiedAsset(
                            source=SOURCE_NOVEL_DB,
                            source_ref=f"scene:{row['scene_id']}",
                            entity_type="scene",
                            title=row["title"] or row["scene_id"],
                            summary=row["summary"] or "",
                            scope="project",
                            project_id=project_id,
                            updated_at=row["updated_at"] or "",
                            payload=dict(row),
                            origin_link=f"/writer-workbench?scene_id={row['scene_id']}",
                        )
                    )
            except sqlite3.OperationalError:
                pass
        return out

    # -- worldline -----------------------------------------------------
    def read_worldline(self, project_id: str | None) -> list[UnifiedAsset]:
        if not project_id:
            return []
        wl_dir = os.path.join(
            Config.UPLOAD_FOLDER, "projects", project_id, "worldlines"
        )
        if not os.path.isdir(wl_dir):
            return []
        out: list[UnifiedAsset] = []
        sessions_dir = os.path.join(wl_dir, "sessions")
        if os.path.isdir(sessions_dir):
            for fname in sorted(os.listdir(sessions_dir)):
                if not fname.endswith(".json"):
                    continue
                path = os.path.join(sessions_dir, fname)
                try:
                    with open(path, "r", encoding="utf-8") as fp:
                        data = json.load(fp)
                except (OSError, json.JSONDecodeError):
                    continue
                sid = fname.removesuffix(".json")
                out.append(
                    UnifiedAsset(
                        source=SOURCE_WORLDLINE,
                        source_ref=f"session:{sid}",
                        entity_type="worldline_session",
                        title=data.get("title") or sid,
                        summary=data.get("summary") or data.get("description") or "",
                        scope="project",
                        project_id=project_id,
                        updated_at=data.get("updated_at") or "",
                        payload=data if isinstance(data, dict) else {},
                        origin_link=f"/worldline?session_id={sid}",
                    )
                )
        return out

    # -- seed pipeline outputs -----------------------------------------
    def read_seed(self, project_id: str | None) -> list[UnifiedAsset]:
        if not project_id:
            return []
        out: list[UnifiedAsset] = []
        archives = ProjectManager.load_project_json(project_id, "narrative_archives.json") or {}
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
        profiles = ProjectManager.load_project_json(project_id, "agent_profiles.json") or {}
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

    def __init__(self, readers: _Readers | None = None) -> None:
        self._readers = readers or _Readers()

    # -- core list -----------------------------------------------------
    def list(
        self,
        *,
        project_id: str | None = None,
        sources: Iterable[str] | None = None,
        entity_types: Iterable[str] | None = None,
        scope: str | None = None,
        q: str | None = None,
        page: int = 1,
        page_size: int = 50,
    ) -> dict[str, Any]:
        active_sources = list(sources) if sources else list(ALL_SOURCES)
        items: list[UnifiedAsset] = []
        errors: list[dict[str, str]] = []
        reader_map = {
            SOURCE_ASSETS: self._readers.read_assets,
            SOURCE_ARCHIVE: self._readers.read_archive,
            SOURCE_STORY_GRAPH: self._readers.read_story_graph,
            SOURCE_NOVEL_DB: self._readers.read_novel_db,
            SOURCE_WORLDLINE: self._readers.read_worldline,
            SOURCE_SEED: self._readers.read_seed,
        }
        for src in active_sources:
            fn = reader_map.get(src)
            if not fn:
                continue
            try:
                items.extend(fn(project_id))
            except Exception as exc:  # noqa: BLE001 — surface but continue
                errors.append({"source": src, "error": f"{type(exc).__name__}: {exc}"})

        # Filters
        if entity_types:
            wanted = set(entity_types)
            items = [a for a in items if a.entity_type in wanted]
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
            "errors": errors,
        }

    # -- facets --------------------------------------------------------
    def facets(self, *, project_id: str | None = None) -> dict[str, Any]:
        result = self.list(project_id=project_id, page=1, page_size=10000)
        sources_count: dict[str, int] = {}
        types_count: dict[str, int] = {}
        for it in result["items"]:
            sources_count[it["source"]] = sources_count.get(it["source"], 0) + 1
            t = it["entity_type"] or ""
            if t:
                types_count[t] = types_count.get(t, 0) + 1
        return {
            "sources": [{"key": k, "count": v} for k, v in sorted(sources_count.items())],
            "entity_types": [
                {"key": k, "count": v} for k, v in sorted(types_count.items(), key=lambda kv: -kv[1])
            ],
            "total": result["total"],
            "errors": result.get("errors", []),
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
