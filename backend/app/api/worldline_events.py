"""Worldline event adopt/edit/query API."""

import traceback

from flask import jsonify, request

from .worldline_support import (
    error,
    ok,
    project_graph_from_request,
    worldline_bp,
    worldline_engine,
    worldline_store,
)
from ..services.worldline_event_service import WorldlineEventService
from ..services.worldline_single_world import current_world

worldline_event_service = WorldlineEventService(store=worldline_store)


def _session_and_container(session_id, data):
    project_id, graph_id = project_graph_from_request(data)
    session = worldline_engine.get_session(session_id, project_id=project_id, graph_id=graph_id)
    if not session:
        return None, None
    _, container_dir = worldline_engine.store.resolve_container(
        session.project_id or project_id,
        session.graph_id,
        session_scope=session.session_scope,
    )
    return session, container_dir


@worldline_bp.route("/session/<session_id>/events/adopt", methods=["POST"])
def adopt_events(session_id: str):
    try:
        data = request.get_json() or {}
        event_ids = data.get("event_ids", [])
        action = data.get("action", "")
        if not event_ids or not action:
            return error("event_ids and action are required", 400)

        session, container_dir = _session_and_container(session_id, data)
        if not session:
            return error(f"Session not found: {session_id}", 404)

        result = worldline_event_service.adopt_events(session, container_dir, event_ids, action)
        world = current_world(session)
        return ok({
            "session_id": session_id,
            **result,
            "current_world": {
                "current_step": world.current_step,
                "timeline_size": len(world.timeline),
                "canon_count": sum(1 for e in world.timeline if e.status == "canon"),
                "candidate_count": sum(1 for e in world.timeline if e.status == "candidate"),
            },
        })
    except ValueError as exc:
        return error(str(exc), 400)
    except Exception as exc:
        return jsonify({"success": False, "error": str(exc), "traceback": traceback.format_exc()}), 500


@worldline_bp.route("/session/<session_id>/events/<event_id>/edit", methods=["POST"])
def edit_event(session_id: str, event_id: str):
    try:
        data = request.get_json() or {}
        consequence = data.get("consequence", "").strip()
        if not consequence:
            return error("consequence is required", 400)

        session, container_dir = _session_and_container(session_id, data)
        if not session:
            return error(f"Session not found: {session_id}", 404)

        result = worldline_event_service.edit_event(session, container_dir, event_id, consequence)
        return ok({
            "session_id": session_id,
            **result,
        })
    except ValueError as exc:
        return error(str(exc), 400)
    except Exception as exc:
        return jsonify({"success": False, "error": str(exc), "traceback": traceback.format_exc()}), 500


@worldline_bp.route("/session/<session_id>/events/candidates", methods=["GET"])
def list_candidate_events(session_id: str):
    try:
        session, _ = _session_and_container(session_id, request.args)
        if not session:
            return error(f"Session not found: {session_id}", 404)

        step = request.args.get("step", default=None, type=int)
        candidates = worldline_event_service.list_candidate_events(session, step=step)
        return ok({
            "session_id": session_id,
            "candidates": candidates,
            "count": len(candidates),
        })
    except ValueError as exc:
        return error(str(exc), 400)
    except Exception as exc:
        return jsonify({"success": False, "error": str(exc), "traceback": traceback.format_exc()}), 500


@worldline_bp.route("/session/<session_id>/events/canon", methods=["GET"])
def list_canon_events(session_id: str):
    try:
        session, _ = _session_and_container(session_id, request.args)
        if not session:
            return error(f"Session not found: {session_id}", 404)

        canon = worldline_event_service.list_canon_events(session)
        return ok({
            "session_id": session_id,
            "canon": canon,
            "count": len(canon),
        })
    except ValueError as exc:
        return error(str(exc), 400)
    except Exception as exc:
        return jsonify({"success": False, "error": str(exc), "traceback": traceback.format_exc()}), 500
