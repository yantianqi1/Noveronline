"""统一资产视图 REST API。

提供跨 silo 的聚合查询、facets、详情和全局 FTS 搜索。
"""

from __future__ import annotations

import traceback

from flask import jsonify, request

from . import unified_assets_bp
from ..services.assets.global_search_indexer import GlobalSearchIndexer
from ..services.assets.unified_asset_view import ALL_SOURCES, UnifiedAssetView


def _err(exc: Exception, status: int = 500):
    return (
        jsonify(
            {
                "success": False,
                "error": str(exc),
                "traceback": traceback.format_exc(),
            }
        ),
        status,
    )


def _split_csv(value: str | None) -> list[str]:
    if not value:
        return []
    return [v.strip() for v in value.split(",") if v.strip()]


@unified_assets_bp.route("", methods=["GET"])
def list_unified():
    try:
        project_id = request.args.get("project_id") or None
        sources = _split_csv(request.args.get("source")) or None
        entity_types = _split_csv(request.args.get("entity_type")) or None
        scope = request.args.get("scope") or None
        q = request.args.get("q") or None
        page = int(request.args.get("page", "1"))
        page_size = int(request.args.get("page_size", "50"))
        view = UnifiedAssetView()
        data = view.list(
            project_id=project_id,
            sources=sources,
            entity_types=entity_types,
            scope=scope,
            q=q,
            page=page,
            page_size=page_size,
        )
        return jsonify({"success": True, "data": data})
    except Exception as exc:  # noqa: BLE001
        return _err(exc)


@unified_assets_bp.route("/facets", methods=["GET"])
def facets_unified():
    try:
        project_id = request.args.get("project_id") or None
        view = UnifiedAssetView()
        return jsonify({"success": True, "data": view.facets(project_id=project_id)})
    except Exception as exc:  # noqa: BLE001
        return _err(exc)


@unified_assets_bp.route("/search", methods=["GET"])
def search_unified():
    try:
        q = (request.args.get("q") or "").strip()
        if not q:
            return jsonify({"success": False, "error": "q 不能为空"}), 400
        project_id = request.args.get("project_id") or None
        sources = _split_csv(request.args.get("source")) or None
        entity_types = _split_csv(request.args.get("entity_type")) or None
        limit = int(request.args.get("limit", "50"))
        offset = int(request.args.get("offset", "0"))
        indexer = GlobalSearchIndexer()
        # 若项目索引为空则懒重建一次
        if project_id:
            with indexer._connect() as conn:  # noqa: SLF001
                row = conn.execute(
                    "SELECT COUNT(*) AS n FROM global_index WHERE project_id = ?",
                    (project_id,),
                ).fetchone()
            if row and row["n"] == 0:
                indexer.reindex_project(project_id)
        data = indexer.search(
            q,
            project_id=project_id,
            sources=sources,
            entity_types=entity_types,
            limit=limit,
            offset=offset,
        )
        return jsonify({"success": True, "data": data})
    except Exception as exc:  # noqa: BLE001
        return _err(exc)


@unified_assets_bp.route("/reindex", methods=["POST"])
def reindex_unified():
    try:
        body = request.get_json(silent=True) or {}
        project_id = body.get("project_id") or request.args.get("project_id")
        if not project_id:
            return jsonify({"success": False, "error": "project_id 必填"}), 400
        n = GlobalSearchIndexer().reindex_project(project_id)
        return jsonify({"success": True, "data": {"indexed": n}})
    except Exception as exc:  # noqa: BLE001
        return _err(exc)


@unified_assets_bp.route("/sources", methods=["GET"])
def list_sources():
    return jsonify({"success": True, "data": list(ALL_SOURCES)})


@unified_assets_bp.route("/<source>/<path:ref>", methods=["GET"])
def get_unified(source: str, ref: str):
    try:
        project_id = request.args.get("project_id") or None
        view = UnifiedAssetView()
        item = view.get(source, ref, project_id=project_id)
        if not item:
            return jsonify({"success": False, "error": "未找到资产"}), 404
        return jsonify({"success": True, "data": item})
    except Exception as exc:  # noqa: BLE001
        return _err(exc)
