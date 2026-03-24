"""
世界线交互 API
"""

import traceback

from flask import jsonify, request

from .worldline_support import (
    character_agent_service,
    current_world_payload,
    error,
    ok,
    project_graph_from_request,
    requested_branch_id,
    worldline_agent_registry,
    worldline_bp,
    worldline_engine,
    worldline_memory_service,
    worldline_runtime_service,
)
from ..services.worldline_single_world import current_world


def _variable_payload(data):
    variable = data.get("variable")
    if isinstance(variable, str):
        return {"name": variable.strip(), "description": variable.strip(), "impact_axis": ""}
    if isinstance(variable, dict):
        return {
            "name": variable.get("name", ""),
            "description": variable.get("description", ""),
            "impact_axis": variable.get("impact_axis", ""),
        }
    return {
        "name": data.get("name", ""),
        "description": data.get("description", ""),
        "impact_axis": data.get("impact_axis", ""),
    }


def _target_branch(session, branch_id):
    requested_branch_id({"branch_id": branch_id})
    return current_world(session)


def _session_context(session_id: str, request_data):
    project_id, graph_id = project_graph_from_request(request_data)
    session = worldline_engine.get_session(session_id, project_id=project_id, graph_id=graph_id)
    if not session:
        return None, None
    _, container_dir = worldline_engine.store.resolve_container(
        session.project_id or project_id,
        session.graph_id,
        session_scope=session.session_scope,
    )
    return session, container_dir


def _branch_context(session_id: str, request_data):
    session, container_dir = _session_context(session_id, request_data)
    if not session:
        return None, None, None
    branch = _target_branch(session, request_data.get("branch_id"))
    return session, container_dir, branch


def _public_agent(agent):
    return {key: value for key, value in agent.items() if key not in {"state", "state_json"}}


def _dialogue_context_summary(branch, agent):
    return f"{branch.title} | step={branch.current_step} | agent={agent['display_name']} | core={branch.core_change}"


def _memory_bundle(session, container_dir, branch, agent, message, limit):
    return worldline_memory_service.build_context_bundle(
        container_dir,
        session.session_id,
        branch.branch_id,
        agent,
        message,
        limit,
    )


@worldline_bp.route("/session/<session_id>/agents", methods=["GET"])
def list_worldline_agents(session_id: str):
    try:
        session, container_dir, branch = _branch_context(session_id, request.args)
        if not session:
            return error(f"世界线会话不存在: {session_id}", 404)
        agents = worldline_runtime_service.list_agents(container_dir, session, branch.branch_id)
        return ok({
            "session_id": session.session_id,
            "branch_id": branch.branch_id,
            "counts": worldline_agent_registry.count_by_kind(agents),
            "agents": [_public_agent(item) for item in agents],
        })
    except ValueError as exc:
        return error(str(exc), 400)
    except Exception as exc:
        return jsonify({"success": False, "error": str(exc), "traceback": traceback.format_exc()}), 500


@worldline_bp.route("/session/<session_id>/step", methods=["POST"])
def step_worldline_session(session_id: str):
    try:
        data = request.get_json() or {}
        project_id, graph_id = project_graph_from_request(data)
        session = worldline_engine.step(
            session_id=session_id,
            project_id=project_id,
            graph_id=graph_id,
            branch_id=data.get("branch_id"),
            steps=data.get("steps", 1),
            evolution_intensity=data.get("evolution_intensity", "medium"),
            custom_depth=data.get("custom_depth"),
        )
        return ok({
            "session_id": session.session_id,
            "updated_at": session.updated_at,
            "message": f"世界线已推进 {data.get('steps', 1)} 步",
            "current_world": current_world_payload(session),
        })
    except ValueError as exc:
        return error(str(exc), 400)
    except Exception as exc:
        return jsonify({"success": False, "error": str(exc), "traceback": traceback.format_exc()}), 500


@worldline_bp.route("/session/<session_id>/inject-variable", methods=["POST"])
def inject_variable(session_id: str):
    try:
        data = request.get_json() or {}
        project_id, graph_id = project_graph_from_request(data)
        variable = _variable_payload(data)
        session = worldline_engine.inject_variable(
            session_id=session_id,
            name=variable["name"],
            description=variable["description"],
            impact_axis=variable["impact_axis"],
            project_id=project_id,
            graph_id=graph_id,
            branch_id=data.get("branch_id"),
        )
        return ok({
            "session_id": session.session_id,
            "message": "变量注入成功",
            "world_variables": [item.to_dict() for item in session.world_variables],
            "current_world": current_world_payload(session),
        })
    except ValueError as exc:
        return error(str(exc), 400)
    except Exception as exc:
        return jsonify({"success": False, "error": str(exc), "traceback": traceback.format_exc()}), 500


@worldline_bp.route("/session/<session_id>/agent-action", methods=["POST"])
def inject_agent_action(session_id: str):
    try:
        data = request.get_json() or {}
        project_id, graph_id = project_graph_from_request(data)
        session, container_dir, branch = _branch_context(session_id, data)
        if not session:
            return error(f"世界线会话不存在: {session_id}", 404)
        agent_ref = (data.get("actor") or data.get("agent_id") or "").strip()
        agent = worldline_runtime_service.resolve_agent(container_dir, session, branch.branch_id, agent_ref)
        agent_error = None if agent else error(f"世界线中不存在 agent: {agent_ref}", 404)
        if agent_error:
            return agent_error
        session, action_event_ids = worldline_engine.queue_action(
            session_id=session_id,
            agent_id=agent["agent_id"],
            actor=agent["display_name"],
            action=data.get("action", ""),
            intent=data.get("intent", ""),
            target=data.get("target", ""),
            project_id=project_id,
            graph_id=graph_id,
            branch_id=data.get("branch_id"),
        )
        return ok({
            "session_id": session.session_id,
            "message": "动作已加入世界线待处理队列",
            "action_event_id": action_event_ids[0],
            "agent": {
                "agent_id": agent["agent_id"],
                "display_name": agent["display_name"],
                "agent_kind": agent["agent_kind"],
            },
            "current_world": current_world_payload(session),
        })
    except ValueError as exc:
        return error(str(exc), 400)
    except Exception as exc:
        return jsonify({"success": False, "error": str(exc), "traceback": traceback.format_exc()}), 500


@worldline_bp.route("/session/<session_id>/agent-dialogue", methods=["POST"])
def agent_dialogue(session_id: str):
    try:
        data = request.get_json() or {}
        actor_name = (data.get("actor") or data.get("agent_id") or "").strip()
        message = (data.get("message") or "").strip()
        mode = (data.get("mode") or "template").strip()
        if not actor_name or not message:
            return error("请提供 actor/agent_id 与 message", 400)
        session, container_dir, branch = _branch_context(session_id, data)
        if not session:
            return error(f"世界线会话不存在: {session_id}", 404)
        agent = worldline_runtime_service.resolve_agent(container_dir, session, branch.branch_id, actor_name)
        agent_error = None if agent else error(f"世界线中不存在 agent: {actor_name}", 404)
        if agent_error:
            return agent_error
        memory_bundle = _memory_bundle(
            session,
            container_dir,
            branch,
            agent,
            message,
            data.get("limit", 20),
        )
        result = character_agent_service.generate_reply(
            actor_name=agent["display_name"],
            actor_state=agent["state"],
            message=message,
            recent_events=[item.to_dict() for item in branch.timeline[-4:]],
            branch_summary={"branch_id": branch.branch_id, "title": branch.title, "core_change": branch.core_change},
            mode=mode,
            memory_bundle=memory_bundle,
        )
        dialogue_id = worldline_runtime_service.record_dialogue(
            container_dir,
            session,
            branch.branch_id,
            agent,
            message,
            result,
            result["generator_mode"],
            result["model_name"],
            _dialogue_context_summary(branch, agent),
        )
        return ok({
            "session_id": session.session_id,
            "branch_id": branch.branch_id,
            "agent": agent["display_name"],
            "agent_id": agent["agent_id"],
            "dialogue_id": dialogue_id,
            "generator_mode": result["generator_mode"],
            "model_name": result["model_name"],
            "memory_context": memory_bundle,
            "result": result,
        })
    except ValueError as exc:
        return error(str(exc), 400)
    except Exception as exc:
        return jsonify({"success": False, "error": str(exc), "traceback": traceback.format_exc()}), 500


@worldline_bp.route("/session/<session_id>/agent-history", methods=["GET"])
def get_agent_history(session_id: str):
    try:
        session, container_dir, branch = _branch_context(session_id, request.args)
        if not session:
            return error(f"世界线会话不存在: {session_id}", 404)
        agent_id = (request.args.get("agent_id") or "").strip()
        if not agent_id:
            return error("请提供 agent_id", 400)
        history = worldline_runtime_service.agent_history(
            container_dir,
            session.session_id,
            branch.branch_id,
            agent_id,
            request.args.get("limit", default=20, type=int),
        )
        return ok({
            "session_id": session.session_id,
            "branch_id": branch.branch_id,
            "agent_id": agent_id,
            **history,
        })
    except ValueError as exc:
        return error(str(exc), 400)
    except Exception as exc:
        return jsonify({"success": False, "error": str(exc), "traceback": traceback.format_exc()}), 500


@worldline_bp.route("/session/<session_id>/agent-actions", methods=["GET"])
def list_agent_actions(session_id: str):
    try:
        session, container_dir = _session_context(session_id, request.args)
        if not session:
            return error(f"世界线会话不存在: {session_id}", 404)
        items = worldline_runtime_service.list_actions(
            container_dir,
            session.session_id,
            requested_branch_id(request.args),
            request.args.get("agent_id"),
            request.args.get("status"),
            request.args.get("limit", default=20, type=int),
        )
        return ok({"session_id": session.session_id, "items": items})
    except ValueError as exc:
        return error(str(exc), 400)
    except Exception as exc:
        return jsonify({"success": False, "error": str(exc), "traceback": traceback.format_exc()}), 500


@worldline_bp.route("/session/<session_id>/agent-memory", methods=["GET"])
def get_agent_memory(session_id: str):
    try:
        session, container_dir, branch = _branch_context(session_id, request.args)
        if not session:
            return error(f"世界线会话不存在: {session_id}", 404)
        agent_ref = (request.args.get("agent_id") or "").strip()
        if not agent_ref:
            return error("请提供 agent_id", 400)
        agent = worldline_runtime_service.resolve_agent(container_dir, session, branch.branch_id, agent_ref)
        if not agent:
            return error(f"世界线中不存在 agent: {agent_ref}", 404)
        payload = worldline_memory_service.agent_memories(
            container_dir,
            session.session_id,
            branch.branch_id,
            agent,
            request.args.get("limit", default=20, type=int),
        )
        return ok({
            "session_id": session.session_id,
            "branch_id": branch.branch_id,
            "agent_id": agent["agent_id"],
            **payload,
        })
    except ValueError as exc:
        return error(str(exc), 400)
    except Exception as exc:
        return jsonify({"success": False, "error": str(exc), "traceback": traceback.format_exc()}), 500


@worldline_bp.route("/session/<session_id>/agent-memory-context", methods=["GET"])
def get_agent_memory_context(session_id: str):
    try:
        session, container_dir, branch = _branch_context(session_id, request.args)
        if not session:
            return error(f"世界线会话不存在: {session_id}", 404)
        agent_ref = (request.args.get("agent_id") or "").strip()
        if not agent_ref:
            return error("请提供 agent_id", 400)
        agent = worldline_runtime_service.resolve_agent(container_dir, session, branch.branch_id, agent_ref)
        if not agent:
            return error(f"世界线中不存在 agent: {agent_ref}", 404)
        payload = _memory_bundle(
            session,
            container_dir,
            branch,
            agent,
            request.args.get("message", ""),
            request.args.get("limit", default=20, type=int),
        )
        return ok({
            "session_id": session.session_id,
            "branch_id": branch.branch_id,
            "agent_id": agent["agent_id"],
            **payload,
        })
    except ValueError as exc:
        return error(str(exc), 400)
    except Exception as exc:
        return jsonify({"success": False, "error": str(exc), "traceback": traceback.format_exc()}), 500


@worldline_bp.route("/session/<session_id>/agent-dialogues", methods=["GET"])
def list_agent_dialogues(session_id: str):
    try:
        session, container_dir = _session_context(session_id, request.args)
        if not session:
            return error(f"世界线会话不存在: {session_id}", 404)
        items = worldline_runtime_service.list_dialogues(
            container_dir,
            session.session_id,
            requested_branch_id(request.args),
            request.args.get("agent_id"),
            request.args.get("limit", default=20, type=int),
        )
        return ok({"session_id": session.session_id, "items": items})
    except ValueError as exc:
        return error(str(exc), 400)
    except Exception as exc:
        return jsonify({"success": False, "error": str(exc), "traceback": traceback.format_exc()}), 500


@worldline_bp.route("/session/<session_id>/relation-history", methods=["GET"])
def list_relation_history(session_id: str):
    try:
        session, container_dir = _session_context(session_id, request.args)
        if not session:
            return error(f"世界线会话不存在: {session_id}", 404)
        items = worldline_runtime_service.list_relation_history(
            container_dir,
            session.session_id,
            requested_branch_id(request.args),
            request.args.get("agent_id"),
            request.args.get("limit", default=20, type=int),
        )
        return ok({"session_id": session.session_id, "items": items})
    except ValueError as exc:
        return error(str(exc), 400)
    except Exception as exc:
        return jsonify({"success": False, "error": str(exc), "traceback": traceback.format_exc()}), 500
