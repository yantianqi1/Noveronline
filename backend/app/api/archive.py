"""全局档案库 API。"""

import traceback

from flask import jsonify, request

from . import archive_bp
from ..services.archive_library_service import ArchiveLibraryService
from ..services.archive_memory_review_service import ArchiveMemoryReviewService

MEMORY_LAYERS = {"canon", "candidate", "experiment"}
MEMORY_STATUSES = {"active", "superseded", "rejected"}


def _archive_library_service() -> ArchiveLibraryService:
    return ArchiveLibraryService()


def _archive_memory_review_service() -> ArchiveMemoryReviewService:
    return ArchiveMemoryReviewService()


def _error_response(error: Exception, status_code: int = 500):
    return jsonify({
        "success": False,
        "error": str(error),
        "traceback": traceback.format_exc(),
    }), status_code


def _csv_query_values(raw_value: str, allowed: set[str], field_name: str) -> tuple[str, ...]:
    values = tuple(item.strip() for item in str(raw_value or "").split(",") if item.strip())
    if not values:
        return ()
    invalid = [item for item in values if item not in allowed]
    if invalid:
        raise ValueError(f"{field_name} 不支持: {', '.join(invalid)}")
    return values


@archive_bp.route("/library", methods=["GET"])
def list_archive_library():
    try:
        data = _archive_library_service().list_archives(
            q=request.args.get("q", ""),
            project_id=request.args.get("project_id", ""),
            entity_type=request.args.get("entity_type", ""),
            agent_kind=request.args.get("agent_kind", ""),
            importance_tier=request.args.get("importance_tier", ""),
            template_key=request.args.get("template_key", ""),
            limit=request.args.get("limit", default=20, type=int),
            offset=request.args.get("offset", default=0, type=int),
        )
        return jsonify({"success": True, "data": data})
    except Exception as exc:
        return _error_response(exc)


@archive_bp.route("/library/<archive_id>", methods=["GET"])
def get_archive_library_item(archive_id: str):
    try:
        data = _archive_library_service().get_archive(archive_id)
        return jsonify({"success": True, "data": data})
    except ValueError as exc:
        return _error_response(exc, 404)
    except Exception as exc:
        return _error_response(exc)


@archive_bp.route("/library/reindex", methods=["POST"])
def reindex_archive_library():
    try:
        count = _archive_library_service().reindex()
        return jsonify({"success": True, "data": {"count": count}})
    except Exception as exc:
        return _error_response(exc)


@archive_bp.route("/library/<archive_id>/memory", methods=["GET"])
def list_archive_memory(archive_id: str):
    try:
        _archive_library_service().get_archive(archive_id)
        layers = _csv_query_values(request.args.get("layer", ""), MEMORY_LAYERS, "layer")
        statuses = _csv_query_values(request.args.get("status", "active"), MEMORY_STATUSES, "status") or ("active",)
        data = _archive_memory_review_service().list_memory(
            archive_id,
            include_candidates=request.args.get("include_candidates", "true").lower() != "false",
            layers=layers or None,
            statuses=statuses,
        )
        return jsonify({"success": True, "data": data})
    except ValueError as exc:
        return _error_response(exc, 404 if "不存在" in str(exc) else 400)
    except Exception as exc:
        return _error_response(exc)


@archive_bp.route("/library/<archive_id>/memory/timeline", methods=["GET"])
def archive_memory_timeline(archive_id: str):
    try:
        _archive_library_service().get_archive(archive_id)
        data = _archive_memory_review_service().timeline(
            archive_id,
            memory_id=request.args.get("memory_id", ""),
            normalized_subject=request.args.get("normalized_subject", ""),
        )
        return jsonify({"success": True, "data": data})
    except ValueError as exc:
        return _error_response(exc, 404 if "不存在" in str(exc) else 400)
    except Exception as exc:
        return _error_response(exc)


@archive_bp.route("/library/<archive_id>/memory/<memory_id>/adopt", methods=["POST"])
def adopt_archive_memory(archive_id: str, memory_id: str):
    try:
        _archive_library_service().get_archive(archive_id)
        data = _archive_memory_review_service().adopt(archive_id, memory_id)
        return jsonify({"success": True, "data": data})
    except ValueError as exc:
        return _error_response(exc, 404 if "不存在" in str(exc) else 400)
    except Exception as exc:
        return _error_response(exc)


@archive_bp.route("/library/<archive_id>/memory/<memory_id>/reject", methods=["POST"])
def reject_archive_memory(archive_id: str, memory_id: str):
    try:
        _archive_library_service().get_archive(archive_id)
        data = _archive_memory_review_service().reject(archive_id, memory_id)
        return jsonify({"success": True, "data": data})
    except ValueError as exc:
        return _error_response(exc, 404 if "不存在" in str(exc) else 400)
    except Exception as exc:
        return _error_response(exc)
