"""
世界线会话与分支 API
"""

import traceback

from flask import jsonify, request

from .worldline_support import error, ok, project_graph_from_request, worldline_bp, worldline_engine


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
            "branches": [
                {
                    "branch_id": branch.branch_id,
                    "title": branch.title,
                    "core_change": branch.core_change,
                    "current_step": branch.current_step,
                    "key_agents": branch.key_agents,
                    "evolution_intensity": branch.evolution_intensity,
                    "evolution_depth": branch.evolution_depth,
                }
                for branch in session.branches
            ],
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
        return ok(session.to_dict())
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
    try:
        session = worldline_engine.get_session(
            session_id,
            project_id=request.args.get("project_id"),
            graph_id=request.args.get("graph_id"),
        )
        if not session:
            return error(f"世界线会话不存在: {session_id}", 404)
        return ok({
            "session_id": session_id,
            "branches": [
                {
                    "branch_id": branch.branch_id,
                    "title": branch.title,
                    "core_change": branch.core_change,
                    "narrative_value": branch.narrative_value,
                    "current_step": branch.current_step,
                    "status": branch.status,
                    "key_agents": branch.key_agents,
                    "expected_conflicts": branch.expected_conflicts,
                    "evolution_intensity": branch.evolution_intensity,
                    "evolution_depth": branch.evolution_depth,
                    "timeline_size": len(branch.timeline),
                    "pending_variables": len(branch.pending_variables),
                    "pending_actions": len(branch.pending_actions),
                }
                for branch in session.branches
            ],
        })
    except Exception as exc:
        return jsonify({"success": False, "error": str(exc), "traceback": traceback.format_exc()}), 500


@worldline_bp.route("/session/<session_id>/comparison", methods=["GET"])
def get_worldline_comparison(session_id: str):
    try:
        comparison = worldline_engine.compare_branches(
            session_id,
            {
                "project_id": request.args.get("project_id"),
                "graph_id": request.args.get("graph_id"),
                "branch_ids": _requested_branch_ids() or None,
            },
        )
        return ok(comparison)
    except LookupError as exc:
        return error(str(exc), 404)
    except ValueError as exc:
        return error(str(exc), 400)
    except Exception as exc:
        return jsonify({"success": False, "error": str(exc), "traceback": traceback.format_exc()}), 500


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
        branch_id = branch_id or request.args.get("branch_id")
        if branch_id:
            branch = next((item for item in session.branches if item.branch_id == branch_id), None)
            if not branch:
                return error(f"分支不存在: {branch_id}", 404)
            return ok({
                "session_id": session_id,
                "branch_id": branch_id,
                "events": [event.to_dict() for event in branch.timeline[-request.args.get('limit', 30, type=int):]],
            })
        return ok({
            "session_id": session_id,
            "timeline": {
                item.branch_id: [event.to_dict() for event in item.timeline[-request.args.get('limit', 30, type=int):]]
                for item in session.branches
            },
        })
    except Exception as exc:
        return jsonify({"success": False, "error": str(exc), "traceback": traceback.format_exc()}), 500
