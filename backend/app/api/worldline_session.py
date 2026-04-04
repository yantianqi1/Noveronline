"""
世界线会话与分支 API
"""

import traceback

from flask import jsonify, request

from .worldline_support import (
    current_world_payload,
    error,
    ok,
    project_graph_from_request,
    requested_branch_id,
    worldline_bp,
    worldline_engine,
)
from ..services.worldline_single_world import current_world


def _requested_branch_ids() -> list[str]:
    raw = request.args.get("branch_ids", "").strip()
    return [item.strip() for item in raw.split(",") if item.strip()]


@worldline_bp.route("/session/create", methods=["POST"])
def create_worldline_session():
    try:
        data = request.get_json() or {}
        project_id, graph_id = project_graph_from_request(data)
        session, _ = worldline_engine.create_session(
            project_id=project_id,
            graph_id=graph_id,
            label=data.get("label", ""),
            variables=data.get("variables", []),
            focus_question=data.get("focus_question"),
            branch_count=data.get("branch_count"),
            archives=data.get("archives"),
            archive_ids=data.get("archive_ids"),
            entity_types=data.get("entity_types"),
            config=data.get("config"),
        )
        return ok({
            "session_id": session.session_id,
            "project_id": session.project_id,
            "graph_id": session.graph_id,
            "simulation_goal": session.simulation_goal,
            "session_scope": session.session_scope,
            "source_archive_ids": session.source_archive_ids,
            "source_project_ids": session.source_project_ids,
            "source_archive_count": session.source_archive_count,
            "branch_count": session.branch_count,
            "current_world": current_world_payload(session),
            "source_summary": session.source_summary,
            "created_at": session.created_at,
        })
    except ValueError as exc:
        return error(str(exc), 400)
    except Exception as exc:
        return jsonify({"success": False, "error": str(exc), "traceback": traceback.format_exc()}), 500


@worldline_bp.route("/session/<session_id>", methods=["GET"])
def get_worldline_session(session_id: str):
    try:
        session = worldline_engine.get_session(
            session_id,
            project_id=request.args.get("project_id"),
            graph_id=request.args.get("graph_id"),
        )
        if not session:
            return error(f"世界线会话不存在: {session_id}", 404)
        payload = session.to_dict()
        payload["current_world"] = current_world_payload(session)
        return ok(payload)
    except ValueError as exc:
        return error(str(exc), 400)
    except Exception as exc:
        return jsonify({"success": False, "error": str(exc), "traceback": traceback.format_exc()}), 500


@worldline_bp.route("/session/list", methods=["GET"])
def list_worldline_sessions():
    try:
        sessions = worldline_engine.list_sessions(
            project_id=request.args.get("project_id"),
            graph_id=request.args.get("graph_id"),
            limit=request.args.get("limit", default=20, type=int),
        )
        return ok({"sessions": sessions, "count": len(sessions)})
    except Exception as exc:
        return jsonify({"success": False, "error": str(exc), "traceback": traceback.format_exc()}), 500


@worldline_bp.route("/session/<session_id>/branches", methods=["GET"])
def list_worldline_branches(session_id: str):
    del session_id
    return error("单世界世界线已不再支持分支列表接口，请改用 session 或 timeline 接口", 410)


@worldline_bp.route("/session/<session_id>/comparison", methods=["GET"])
def get_worldline_comparison(session_id: str):
    del session_id
    return error("单世界世界线已不再支持分支对比接口，请改用 session 接口读取当前世界", 410)


@worldline_bp.route("/session/<session_id>/timeline", methods=["GET"])
@worldline_bp.route("/session/<session_id>/branch/<branch_id>/timeline", methods=["GET"])
def get_worldline_timeline(session_id: str, branch_id: str = None):
    try:
        session = worldline_engine.get_session(
            session_id,
            project_id=request.args.get("project_id"),
            graph_id=request.args.get("graph_id"),
        )
        if not session:
            return error(f"世界线会话不存在: {session_id}", 404)
        requested_branch_id({"branch_id": branch_id or request.args.get("branch_id")})
        world = current_world(session)
        return ok({
            "session_id": session_id,
            "branch_id": world.branch_id,
            "events": [event.to_dict() for event in world.timeline[-request.args.get("limit", 30, type=int):]],
        })
    except ValueError as exc:
        return error(str(exc), 400)
    except Exception as exc:
        return jsonify({"success": False, "error": str(exc), "traceback": traceback.format_exc()}), 500
