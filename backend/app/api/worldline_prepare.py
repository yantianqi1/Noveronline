"""世界线 prepare 与 agent detail API。"""

import traceback

from flask import jsonify, request

from .worldline_support import (
    error,
    ok,
    project_graph_from_request,
    worldline_bp,
    worldline_memory_service,
    worldline_prepare_service,
    worldline_runtime_service,
)
from .worldline_interaction import _branch_context
from ..services.worldline_prepare_storage import WorldlinePrepareStorage


@worldline_bp.route("/session/prepare", methods=["POST"])
def prepare_worldline_session():
    try:
        data = request.get_json() or {}
        result = worldline_prepare_service.start_prepare(
            project_id=data.get("project_id"),
            graph_id=data.get("graph_id"),
            variables=data.get("variables"),
            focus_question=data.get("focus_question"),
            archives=data.get("archives"),
            archive_ids=data.get("archive_ids"),
            entity_types=data.get("entity_types"),
            config=data.get("config"),
        )
        response = ok(result)
        response.status_code = 202
        return response
    except ValueError as exc:
        return error(str(exc), 400)
    except Exception as exc:
        return jsonify({"success": False, "error": str(exc), "traceback": traceback.format_exc()}), 500


@worldline_bp.route("/session/prepare/<prepare_id>", methods=["GET"])
def get_worldline_prepare(prepare_id: str):
    try:
        run, container_dir = worldline_prepare_service.get_prepare(
            prepare_id,
            project_id=request.args.get("project_id"),
            graph_id=request.args.get("graph_id"),
        )
        payload = run | {"events": WorldlinePrepareStorage(container_dir).list_events(prepare_id)}
        return ok(payload)
    except ValueError as exc:
        return error(str(exc), 404)
    except Exception as exc:
        return jsonify({"success": False, "error": str(exc), "traceback": traceback.format_exc()}), 500


@worldline_bp.route("/session/prepare/<prepare_id>/agents", methods=["GET"])
def list_worldline_prepare_agents(prepare_id: str):
    try:
        agents, run = worldline_prepare_service.list_prepare_agents(
            prepare_id,
            project_id=request.args.get("project_id"),
            graph_id=request.args.get("graph_id"),
        )
        return ok({"prepare_id": prepare_id, "status": run["status"], "agents": [{**item, "prepare_id": prepare_id} for item in agents]})
    except ValueError as exc:
        return error(str(exc), 404)
    except Exception as exc:
        return jsonify({"success": False, "error": str(exc), "traceback": traceback.format_exc()}), 500


@worldline_bp.route("/session/prepare/<prepare_id>/start", methods=["POST"])
def start_worldline_from_prepare(prepare_id: str):
    try:
        data = request.get_json(silent=True) or {}
        project_id, graph_id = project_graph_from_request(data)
        session, run = worldline_prepare_service.start_session(prepare_id, project_id=project_id, graph_id=graph_id)
        return ok({"prepare_id": prepare_id, "session_id": session.session_id, "project_id": session.project_id, "graph_id": session.graph_id, "started_at": session.created_at, "prepare_status": run["status"]})
    except ValueError as exc:
        return error(str(exc), 400)
    except Exception as exc:
        return jsonify({"success": False, "error": str(exc), "traceback": traceback.format_exc()}), 500


@worldline_bp.route("/session/<session_id>/agents/<agent_id>", methods=["GET"])
def get_worldline_agent_detail(session_id: str, agent_id: str):
    try:
        session, container_dir, branch = _branch_context(session_id, request.args)
        if not session:
            return error(f"世界线会话不存在: {session_id}", 404)
        agent = worldline_runtime_service.resolve_agent(container_dir, session, branch.branch_id, agent_id)
        if not agent:
            return error(f"世界线中不存在 agent: {agent_id}", 404)
        baseline = worldline_prepare_service.get_dossier_for_session(container_dir, session, agent["agent_id"])
        history = worldline_runtime_service.agent_history(
            container_dir,
            session.session_id,
            branch.branch_id,
            agent["agent_id"],
            request.args.get("limit", default=20, type=int),
        )
        memories = worldline_memory_service.agent_memories(
            container_dir,
            session.session_id,
            branch.branch_id,
            agent,
            request.args.get("limit", default=20, type=int),
        )
        relations = worldline_runtime_service.list_relation_history(
            container_dir,
            session.session_id,
            branch.branch_id,
            agent["agent_id"],
            request.args.get("limit", default=20, type=int),
        )
        return ok(
            {
                "session_id": session.session_id,
                "branch_id": branch.branch_id,
                "agent_id": agent["agent_id"],
                "baseline_dossier": baseline,
                "current_agent": agent,
                "history": history,
                "memories": memories,
                "relation_history": relations,
            }
        )
    except ValueError as exc:
        return error(str(exc), 400)
    except Exception as exc:
        return jsonify({"success": False, "error": str(exc), "traceback": traceback.format_exc()}), 500
