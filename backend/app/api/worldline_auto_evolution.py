"""世界线自动演化 API。"""

import traceback

from flask import jsonify, request

from .worldline_support import (
    error,
    ok,
    project_graph_from_request,
    worldline_bp,
    worldline_engine,
    worldline_memory_service,
    worldline_runtime_service,
)
from ..services.worldline_auto_evolution_task_service import WorldlineAutoEvolutionTaskService

worldline_auto_evolution_task_service = WorldlineAutoEvolutionTaskService(
    engine=worldline_engine,
    runtime_service=worldline_runtime_service,
    memory_service=worldline_memory_service,
    prepare_service=worldline_engine.prepare_service,
)


@worldline_bp.route("/session/<session_id>/auto-evolve", methods=["POST"])
def auto_evolve_worldline(session_id: str):
    try:
        data = request.get_json() or {}
        project_id, graph_id = project_graph_from_request(data)
        tasks = worldline_auto_evolution_task_service.start_tasks(
            session_id=session_id,
            project_id=project_id,
            graph_id=graph_id,
            branch_ids=data.get("branch_ids"),
            mode=(data.get("mode") or "").strip(),
            goal_text=str(data.get("goal_text") or ""),
            max_steps=data.get("max_steps"),
        )
        response = ok({"session_id": session_id, "tasks": tasks})
        response.status_code = 202
        return response
    except ValueError as exc:
        return error(str(exc), 400)
    except Exception as exc:
        return jsonify({"success": False, "error": str(exc), "traceback": traceback.format_exc()}), 500
