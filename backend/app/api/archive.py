"""全局档案库 API。"""

import traceback

from flask import jsonify, request

from . import archive_bp
from ..services.archive_library_service import ArchiveLibraryService


archive_library_service = ArchiveLibraryService()


def _error_response(error: Exception, status_code: int = 500):
    return jsonify({
        "success": False,
        "error": str(error),
        "traceback": traceback.format_exc(),
    }), status_code


@archive_bp.route("/library", methods=["GET"])
def list_archive_library():
    try:
        data = archive_library_service.list_archives(
            q=request.args.get("q", ""),
            project_id=request.args.get("project_id", ""),
            entity_type=request.args.get("entity_type", ""),
            importance_tier=request.args.get("importance_tier", ""),
            limit=request.args.get("limit", default=20, type=int),
            offset=request.args.get("offset", default=0, type=int),
        )
        return jsonify({"success": True, "data": data})
    except Exception as exc:
        return _error_response(exc)


@archive_bp.route("/library/<archive_id>", methods=["GET"])
def get_archive_library_item(archive_id: str):
    try:
        data = archive_library_service.get_archive(archive_id)
        return jsonify({"success": True, "data": data})
    except ValueError as exc:
        return _error_response(exc, 404)
    except Exception as exc:
        return _error_response(exc)


@archive_bp.route("/library/reindex", methods=["POST"])
def reindex_archive_library():
    try:
        count = archive_library_service.reindex()
        return jsonify({"success": True, "data": {"count": count}})
    except Exception as exc:
        return _error_response(exc)
