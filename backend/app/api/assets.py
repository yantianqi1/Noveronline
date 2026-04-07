"""资产库 REST API。"""

from __future__ import annotations

import traceback

from flask import jsonify, request

from . import assets_bp
from ..models.task import TaskManager
from ..services.assets.assets_service import AssetsService
from ..services.assets.assets_storage import GLOBAL_SCOPE, PROJECT_SCOPE
from ..services.assets.style_extractor import StyleExtractor


def _service() -> AssetsService:
    return AssetsService()


def _err(exc: Exception, status: int = 500):
    return jsonify({
        "success": False,
        "error": str(exc),
        "traceback": traceback.format_exc(),
    }), status


def _validate_scope(scope: str) -> str:
    if scope not in (GLOBAL_SCOPE, PROJECT_SCOPE):
        raise ValueError(f"scope 必须是 global 或 project，收到 {scope!r}")
    return scope


# ----------------------------------------------------------------------
# Listing & search
# ----------------------------------------------------------------------


@assets_bp.route("", methods=["GET"])
def list_assets():
    try:
        scope = request.args.get("scope", "all")
        project_id = request.args.get("project_id") or None
        asset_type = request.args.get("asset_type") or None
        category = request.args.get("category")
        enabled_only = request.args.get("enabled_only", "false").lower() == "true"
        limit = int(request.args.get("limit", "200"))
        offset = int(request.args.get("offset", "0"))

        svc = _service()
        if scope == "all":
            data = svc.list_merged(
                project_id=project_id,
                asset_type=asset_type,
                category=category,
                enabled_only=enabled_only,
                limit=limit,
            )
        else:
            _validate_scope(scope)
            data = svc.list(
                scope=scope, project_id=project_id,
                asset_type=asset_type, category=category,
                enabled_only=enabled_only, limit=limit, offset=offset,
            )
        return jsonify({"success": True, "data": data})
    except Exception as exc:
        return _err(exc)


@assets_bp.route("/search", methods=["POST"])
def search_assets():
    try:
        body = request.get_json() or {}
        query = body.get("query", "")
        if not query.strip():
            return jsonify({"success": False, "error": "query 不能为空"}), 400
        scope = body.get("scope", "all")
        project_id = body.get("project_id") or None
        asset_type = body.get("asset_type") or None
        category = body.get("category")
        enabled_only = bool(body.get("enabled_only", True))
        limit = int(body.get("limit", 20))

        svc = _service()
        if scope == "all":
            data = svc.search_merged(
                query, project_id=project_id, asset_type=asset_type,
                category=category, enabled_only=enabled_only, limit=limit,
            )
        else:
            _validate_scope(scope)
            data = svc.search(
                query, scope=scope, project_id=project_id,
                asset_type=asset_type, category=category,
                enabled_only=enabled_only, limit=limit,
            )
        return jsonify({"success": True, "data": data})
    except Exception as exc:
        return _err(exc)


# ----------------------------------------------------------------------
# CRUD
# ----------------------------------------------------------------------


@assets_bp.route("/<asset_id>", methods=["GET"])
def get_asset(asset_id: str):
    try:
        project_id = request.args.get("project_id") or None
        asset = _service().find(asset_id, project_id=project_id)
        if not asset:
            return jsonify({"success": False, "error": "未找到资产"}), 404
        return jsonify({"success": True, "data": asset})
    except Exception as exc:
        return _err(exc)


@assets_bp.route("", methods=["POST"])
def create_asset():
    try:
        body = request.get_json() or {}
        scope = _validate_scope(body.get("scope", GLOBAL_SCOPE))
        asset = _service().create(
            scope=scope,
            asset_type=body["asset_type"],
            title=body["title"],
            project_id=body.get("project_id"),
            category=body.get("category", ""),
            summary=body.get("summary", ""),
            content=body.get("content", ""),
            payload=body.get("payload"),
            tags=body.get("tags"),
            source_kind=body.get("source_kind", "manual"),
            source_ref=body.get("source_ref", ""),
            enabled=bool(body.get("enabled", True)),
            pinned=bool(body.get("pinned", False)),
        )
        return jsonify({"success": True, "data": asset})
    except Exception as exc:
        return _err(exc)


@assets_bp.route("/<asset_id>", methods=["PUT"])
def update_asset(asset_id: str):
    try:
        body = request.get_json() or {}
        scope = _validate_scope(body.pop("scope", GLOBAL_SCOPE))
        project_id = body.pop("project_id", None)
        asset = _service().update(asset_id, scope=scope, project_id=project_id, **body)
        return jsonify({"success": True, "data": asset})
    except Exception as exc:
        return _err(exc)


@assets_bp.route("/<asset_id>", methods=["DELETE"])
def delete_asset(asset_id: str):
    try:
        scope = _validate_scope(request.args.get("scope", GLOBAL_SCOPE))
        project_id = request.args.get("project_id") or None
        ok = _service().delete(asset_id, scope=scope, project_id=project_id)
        return jsonify({"success": ok})
    except Exception as exc:
        return _err(exc)


# ----------------------------------------------------------------------
# Batch
# ----------------------------------------------------------------------


@assets_bp.route("/batch-toggle", methods=["POST"])
def batch_toggle():
    try:
        body = request.get_json() or {}
        scope = _validate_scope(body.get("scope", GLOBAL_SCOPE))
        n = _service().batch_set_enabled(
            body.get("asset_ids") or [],
            bool(body.get("enabled", True)),
            scope=scope, project_id=body.get("project_id"),
        )
        return jsonify({"success": True, "data": {"updated": n}})
    except Exception as exc:
        return _err(exc)


@assets_bp.route("/batch-categorize", methods=["POST"])
def batch_categorize():
    try:
        body = request.get_json() or {}
        scope = _validate_scope(body.get("scope", GLOBAL_SCOPE))
        n = _service().batch_set_category(
            body.get("asset_ids") or [],
            body.get("category", ""),
            scope=scope, project_id=body.get("project_id"),
        )
        return jsonify({"success": True, "data": {"updated": n}})
    except Exception as exc:
        return _err(exc)


# ----------------------------------------------------------------------
# Style extraction
# ----------------------------------------------------------------------


@assets_bp.route("/style-extract", methods=["POST"])
def style_extract():
    try:
        body = request.get_json() or {}
        text = body.get("text") or ""
        title = (body.get("title") or "").strip()
        if not text.strip() or not title:
            return jsonify({"success": False, "error": "text 与 title 必填"}), 400
        task_id = StyleExtractor().extract_background(
            text,
            title=title,
            category=body.get("category", ""),
            tags=body.get("tags") or [],
            target_chunk_chars=int(body.get("target_chunk_chars") or 3000),
            max_chunks=int(body.get("max_chunks") or 30),
        )
        return jsonify({"success": True, "data": {"task_id": task_id}})
    except Exception as exc:
        return _err(exc)


@assets_bp.route("/style-extract/<task_id>", methods=["GET"])
def style_extract_status(task_id: str):
    try:
        task = TaskManager().get_task(task_id)
        if not task:
            return jsonify({"success": False, "error": "任务不存在"}), 404
        return jsonify({"success": True, "data": task.to_dict()})
    except Exception as exc:
        return _err(exc)
