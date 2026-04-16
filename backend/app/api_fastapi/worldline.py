"""Native FastAPI worldline routes."""

from __future__ import annotations

import json

from fastapi import APIRouter, Body
from fastapi.responses import StreamingResponse

from app.config import Config
from app.services.agents.worldline import CharacterAgentService
from app.services.world_state_store import WorldStateStore
from app.services.worldline_auto_evolution_task_service import WorldlineAutoEvolutionTaskService
from app.services.worldline_engine_factory import build_worldline_engine
from app.services.worldline_event_service import WorldlineEventService
from app.database import get_engine
from app.repositories.worldline_prepare_repo import WorldlinePrepareRepository
from app.services.worldline_single_world import MAIN_WORLD_BRANCH_ID, current_world, resolve_branch_id

from .common import err, ok
from app.schemas.worldline_schemas import (
    AdoptEventsRequest,
    AgentActionRequest,
    AgentDialogueRequest,
    AutoEvolveRequest,
    CreateSessionRequest,
    EditEventRequest,
    InjectVariableRequest,
    PrepareSessionRequest,
    StartFromPrepareRequest,
    StepRequest,
)

router = APIRouter(prefix="/worldline", tags=["worldline"])

_store = WorldStateStore()
_engine = None
_engine_upload_root = None
character_agent_service = CharacterAgentService()


class _AttributeProxy:
    def __init__(self, resolver):
        object.__setattr__(self, "_resolver", resolver)

    def __getattr__(self, name):
        return getattr(self._resolver(), name)

    def __setattr__(self, name, value):
        setattr(self._resolver(), name, value)


def engine():
    global _engine, _engine_upload_root
    if _engine is None or _engine_upload_root != Config.UPLOAD_FOLDER:
        _engine = build_worldline_engine(_store)
        _engine_upload_root = Config.UPLOAD_FOLDER
    return _engine


def runtime_service():
    return engine().runtime_service


def memory_service():
    return engine().memory_service


def prepare_service():
    return engine().prepare_service


worldline_engine = _AttributeProxy(engine)
worldline_runtime_service = _AttributeProxy(runtime_service)
worldline_memory_service = _AttributeProxy(memory_service)
worldline_prepare_service = _AttributeProxy(prepare_service)
worldline_auto_evolution_task_service = WorldlineAutoEvolutionTaskService(
    engine=worldline_engine,
    runtime_service=worldline_runtime_service,
    memory_service=worldline_memory_service,
    prepare_service=worldline_prepare_service,
)


def project_graph(data: dict):
    return data.get("project_id"), data.get("graph_id")


def current_world_payload(session):
    world = current_world(session)
    payload = world.to_dict()
    payload["branch_id"] = MAIN_WORLD_BRANCH_ID
    payload["title"] = world.title or "当前世界"
    payload["timeline_size"] = len(world.timeline)
    payload["pending_variable_count"] = len(world.pending_variables)
    payload["pending_action_count"] = len(world.pending_actions)
    payload["latest_event"] = world.timeline[-1].to_dict() if world.timeline else None
    return payload


def session_context(session_id: str, data: dict):
    project_id, graph_id = project_graph(data)
    session = engine().get_session(session_id, project_id=project_id, graph_id=graph_id)
    if not session:
        return None, None
    _, container_dir = engine().store.resolve_container(session.project_id or project_id, session.graph_id, session_scope=session.session_scope)
    return session, container_dir


def branch_context(session_id: str, data: dict):
    session, container_dir = session_context(session_id, data)
    if not session:
        return None, None, None
    resolve_branch_id(data.get("branch_id"))
    return session, container_dir, current_world(session)


def public_agent(agent: dict) -> dict:
    return {key: value for key, value in agent.items() if key not in {"state", "state_json"}}


@router.post("/session/create")
async def create_worldline_session(body: CreateSessionRequest):
    try:
        payload = body.model_dump()
        project_id, graph_id = project_graph(payload)
        session, _ = engine().create_session(project_id=project_id, graph_id=graph_id, label=payload.get("label", ""), variables=payload.get("variables", []), focus_question=payload.get("focus_question"), branch_count=payload.get("branch_count"), archives=payload.get("archives"), archive_ids=payload.get("archive_ids"), entity_types=payload.get("entity_types"), config=payload.get("config"))
        return ok({"session_id": session.session_id, "project_id": session.project_id, "graph_id": session.graph_id, "simulation_goal": session.simulation_goal, "session_scope": session.session_scope, "source_archive_ids": session.source_archive_ids, "source_project_ids": session.source_project_ids, "source_archive_count": session.source_archive_count, "branch_count": session.branch_count, "current_world": current_world_payload(session), "source_summary": session.source_summary, "created_at": session.created_at})
    except ValueError as exc:
        return err(exc, status_code=400)
    except Exception as exc:
        return err(exc)


@router.get("/session/list")
async def list_worldline_sessions(project_id: str | None = None, graph_id: str | None = None, limit: int = 20):
    try:
        sessions = engine().list_sessions(project_id=project_id, graph_id=graph_id, limit=limit)
        return ok({"sessions": sessions, "count": len(sessions)})
    except Exception as exc:
        return err(exc)


@router.get("/session/{session_id}")
async def get_worldline_session(session_id: str, project_id: str | None = None, graph_id: str | None = None):
    try:
        session = engine().get_session(session_id, project_id=project_id, graph_id=graph_id)
        if not session:
            return err(f"世界线会话不存在: {session_id}", status_code=404)
        payload = session.to_dict()
        payload["current_world"] = current_world_payload(session)
        return ok(payload)
    except ValueError as exc:
        return err(exc, status_code=400)
    except Exception as exc:
        return err(exc)


@router.get("/session/{session_id}/branches")
async def list_worldline_branches(session_id: str):
    return err("单世界世界线已不再支持分支列表接口，请改用 session 或 timeline 接口", status_code=410)


@router.get("/session/{session_id}/comparison")
async def get_worldline_comparison(session_id: str):
    return err("单世界世界线已不再支持分支对比接口，请改用 session 接口读取当前世界", status_code=410)


@router.get("/session/{session_id}/timeline")
@router.get("/session/{session_id}/branch/{branch_id}/timeline")
async def get_worldline_timeline(session_id: str, branch_id: str | None = None, project_id: str | None = None, graph_id: str | None = None, limit: int = 30):
    try:
        session = engine().get_session(session_id, project_id=project_id, graph_id=graph_id)
        if not session:
            return err(f"世界线会话不存在: {session_id}", status_code=404)
        resolve_branch_id(branch_id)
        world = current_world(session)
        return ok({"session_id": session_id, "branch_id": world.branch_id, "events": [event.to_dict() for event in world.timeline[-limit:]]})
    except ValueError as exc:
        return err(exc, status_code=400)
    except Exception as exc:
        return err(exc)


@router.post("/session/{session_id}/step")
async def step_worldline_session(session_id: str, body: StepRequest):
    try:
        payload = body.model_dump()
        project_id, graph_id = project_graph(payload)
        steps = int(payload.get("steps", 1))
        session, container_dir, branch = branch_context(session_id, payload)
        if not session:
            return err(f"世界线会话不存在: {session_id}", status_code=404)
        for _ in range(max(1, min(steps, 10))):
            session = engine().step(session_id=session_id, project_id=project_id, graph_id=graph_id, branch_id=branch.branch_id, steps=1, evolution_intensity=payload.get("evolution_intensity", "medium"), custom_depth=payload.get("custom_depth"))
            branch = current_world(session)
        return ok({"session_id": session.session_id, "updated_at": session.updated_at, "message": f"世界线已推进 {steps} 步", "current_world": current_world_payload(session)})
    except ValueError as exc:
        return err(exc, status_code=400)
    except Exception as exc:
        return err(exc)


@router.post("/session/{session_id}/inject-variable")
async def inject_variable(session_id: str, body: InjectVariableRequest):
    try:
        payload = body.model_dump()
        project_id, graph_id = project_graph(payload)
        variable = payload.get("variable")
        data = {"name": payload.get("name", ""), "description": payload.get("description", ""), "impact_axis": payload.get("impact_axis", "")}
        if isinstance(variable, str):
            data = {"name": variable.strip(), "description": variable.strip(), "impact_axis": ""}
        elif isinstance(variable, dict):
            data = {"name": variable.get("name", ""), "description": variable.get("description", ""), "impact_axis": variable.get("impact_axis", "")}
        session = engine().inject_variable(session_id=session_id, project_id=project_id, graph_id=graph_id, branch_id=payload.get("branch_id"), **data)
        return ok({"session_id": session.session_id, "message": "变量注入成功", "world_variables": [item.to_dict() for item in session.world_variables], "current_world": current_world_payload(session)})
    except ValueError as exc:
        return err(exc, status_code=400)
    except Exception as exc:
        return err(exc)


@router.post("/session/{session_id}/agent-action")
async def inject_agent_action(session_id: str, body: AgentActionRequest):
    try:
        payload = body.model_dump()
        project_id, graph_id = project_graph(payload)
        session, container_dir, branch = branch_context(session_id, payload)
        if not session:
            return err(f"世界线会话不存在: {session_id}", status_code=404)
        agent_ref = (payload.get("actor") or payload.get("agent_id") or "").strip()
        agent = runtime_service().resolve_agent(container_dir, session, branch.branch_id, agent_ref)
        if not agent:
            return err(f"世界线中不存在 agent: {agent_ref}", status_code=404)
        session, ids = engine().queue_action(session_id=session_id, agent_id=agent["agent_id"], actor=agent["display_name"], action=payload.get("action", ""), intent=payload.get("intent", ""), target=payload.get("target", ""), project_id=project_id, graph_id=graph_id, branch_id=payload.get("branch_id"))
        return ok({"session_id": session.session_id, "message": "动作已加入世界线待处理队列", "action_event_id": ids[0], "agent": {"agent_id": agent["agent_id"], "display_name": agent["display_name"], "agent_kind": agent["agent_kind"]}, "current_world": current_world_payload(session)})
    except ValueError as exc:
        return err(exc, status_code=400)
    except Exception as exc:
        return err(exc)


@router.get("/session/{session_id}/agents")
async def list_worldline_agents(session_id: str, project_id: str | None = None, graph_id: str | None = None, branch_id: str | None = None):
    try:
        session, container_dir, branch = branch_context(session_id, {"project_id": project_id, "graph_id": graph_id, "branch_id": branch_id})
        if not session:
            return err(f"世界线会话不存在: {session_id}", status_code=404)
        agents = runtime_service().list_agents(container_dir, session, branch.branch_id)
        return ok({"session_id": session.session_id, "branch_id": branch.branch_id, "counts": runtime_service().registry.count_by_kind(agents), "agents": [public_agent(item) for item in agents]})
    except ValueError as exc:
        return err(exc, status_code=400)
    except Exception as exc:
        return err(exc)


@router.post("/session/{session_id}/agent-dialogue")
async def agent_dialogue(session_id: str, body: AgentDialogueRequest):
    try:
        payload = body.model_dump()
        actor_name = (payload.get("actor") or payload.get("agent_id") or "").strip()
        message = (payload.get("message") or "").strip()
        if not actor_name or not message:
            return err("请提供 actor/agent_id 与 message", status_code=400)
        session, container_dir, branch = branch_context(session_id, payload)
        if not session:
            return err(f"世界线会话不存在: {session_id}", status_code=404)
        agent = runtime_service().resolve_agent(container_dir, session, branch.branch_id, actor_name)
        if not agent:
            return err(f"世界线中不存在 agent: {actor_name}", status_code=404)
        memory = memory_service().build_context_bundle(container_dir, session.session_id, branch.branch_id, agent, message, payload.get("limit", 20))
        result = character_agent_service.generate_reply(actor_name=agent["display_name"], actor_state=agent["state"], message=message, recent_events=[item.to_dict() for item in branch.timeline[-4:]], branch_summary={"branch_id": branch.branch_id, "title": branch.title, "core_change": branch.core_change}, mode=(payload.get("mode") or "template").strip(), memory_bundle=memory, dossier_context=prepare_service().build_dialogue_bundle(container_dir, session, agent))
        dialogue_id = runtime_service().record_dialogue(container_dir, session, branch.branch_id, agent, message, result, result["generator_mode"], result["model_name"], f"{branch.title} | step={branch.current_step} | agent={agent['display_name']} | core={branch.core_change}")
        return ok({"session_id": session.session_id, "branch_id": branch.branch_id, "agent": agent["display_name"], "agent_id": agent["agent_id"], "dialogue_id": dialogue_id, "generator_mode": result["generator_mode"], "model_name": result["model_name"], "memory_context": memory, "result": result})
    except ValueError as exc:
        return err(exc, status_code=400)
    except Exception as exc:
        return err(exc)


@router.get("/session/{session_id}/agent-history")
async def get_agent_history(session_id: str, agent_id: str = "", project_id: str | None = None, graph_id: str | None = None, branch_id: str | None = None, limit: int = 20):
    try:
        session, container_dir, branch = branch_context(session_id, {"project_id": project_id, "graph_id": graph_id, "branch_id": branch_id})
        if not session:
            return err(f"世界线会话不存在: {session_id}", status_code=404)
        if not agent_id:
            return err("请提供 agent_id", status_code=400)
        return ok({"session_id": session.session_id, "branch_id": branch.branch_id, "agent_id": agent_id, **runtime_service().agent_history(container_dir, session.session_id, branch.branch_id, agent_id, limit)})
    except Exception as exc:
        return err(exc)


@router.get("/session/{session_id}/agent-actions")
async def list_agent_actions(session_id: str, project_id: str | None = None, graph_id: str | None = None, branch_id: str | None = None, agent_id: str | None = None, status: str | None = None, limit: int = 20):
    session, container_dir = session_context(session_id, {"project_id": project_id, "graph_id": graph_id})
    if not session:
        return err(f"世界线会话不存在: {session_id}", status_code=404)
    return ok({"session_id": session.session_id, "items": runtime_service().list_actions(container_dir, session.session_id, resolve_branch_id(branch_id), agent_id, status, limit)})


@router.get("/session/{session_id}/agent-dialogues")
async def list_agent_dialogues(session_id: str, project_id: str | None = None, graph_id: str | None = None, branch_id: str | None = None, agent_id: str | None = None, limit: int = 20):
    session, container_dir = session_context(session_id, {"project_id": project_id, "graph_id": graph_id})
    if not session:
        return err(f"世界线会话不存在: {session_id}", status_code=404)
    return ok({"session_id": session.session_id, "items": runtime_service().list_dialogues(container_dir, session.session_id, resolve_branch_id(branch_id), agent_id, limit)})


@router.get("/session/{session_id}/relation-history")
async def list_relation_history(session_id: str, project_id: str | None = None, graph_id: str | None = None, branch_id: str | None = None, agent_id: str | None = None, limit: int = 20):
    session, container_dir = session_context(session_id, {"project_id": project_id, "graph_id": graph_id})
    if not session:
        return err(f"世界线会话不存在: {session_id}", status_code=404)
    return ok({"session_id": session.session_id, "items": runtime_service().list_relation_history(container_dir, session.session_id, resolve_branch_id(branch_id), agent_id, limit)})


@router.get("/session/{session_id}/agent-memory")
async def get_agent_memory(session_id: str, agent_id: str = "", project_id: str | None = None, graph_id: str | None = None, branch_id: str | None = None, limit: int = 20):
    session, container_dir, branch = branch_context(session_id, {"project_id": project_id, "graph_id": graph_id, "branch_id": branch_id})
    if not session:
        return err(f"世界线会话不存在: {session_id}", status_code=404)
    agent = runtime_service().resolve_agent(container_dir, session, branch.branch_id, agent_id)
    if not agent:
        return err(f"世界线中不存在 agent: {agent_id}", status_code=404)
    return ok({"session_id": session.session_id, "branch_id": branch.branch_id, "agent_id": agent["agent_id"], **memory_service().agent_memories(container_dir, session.session_id, branch.branch_id, agent, limit)})


@router.get("/session/{session_id}/agent-memory-context")
async def get_agent_memory_context(session_id: str, agent_id: str = "", message: str = "", project_id: str | None = None, graph_id: str | None = None, branch_id: str | None = None, limit: int = 20):
    session, container_dir, branch = branch_context(session_id, {"project_id": project_id, "graph_id": graph_id, "branch_id": branch_id})
    if not session:
        return err(f"世界线会话不存在: {session_id}", status_code=404)
    agent = runtime_service().resolve_agent(container_dir, session, branch.branch_id, agent_id)
    if not agent:
        return err(f"世界线中不存在 agent: {agent_id}", status_code=404)
    return ok({"session_id": session.session_id, "branch_id": branch.branch_id, "agent_id": agent["agent_id"], **memory_service().build_context_bundle(container_dir, session.session_id, branch.branch_id, agent, message, limit)})


@router.post("/session/{session_id}/auto-evolve")
async def auto_evolve_worldline(session_id: str, body: AutoEvolveRequest):
    try:
        payload = body.model_dump()
        project_id, graph_id = project_graph(payload)
        tasks = await worldline_auto_evolution_task_service.start_tasks(session_id=session_id, project_id=project_id, graph_id=graph_id, branch_ids=payload.get("branch_ids"), mode=(payload.get("mode") or "").strip(), goal_text=str(payload.get("goal_text") or ""), max_steps=payload.get("max_steps"))
        return ok({"session_id": session_id, "tasks": tasks}, status_code=202)
    except ValueError as exc:
        return err(exc, status_code=400)
    except Exception as exc:
        return err(exc)


@router.post("/session/prepare")
async def prepare_worldline_session(body: PrepareSessionRequest):
    try:
        payload = body.model_dump()
        result = await prepare_service().start_prepare(label=payload.get("label", ""), project_id=payload.get("project_id"), graph_id=payload.get("graph_id"), variables=payload.get("variables"), focus_question=payload.get("focus_question"), archives=payload.get("archives"), archive_ids=payload.get("archive_ids"), entity_types=payload.get("entity_types"), config=payload.get("config"))
        return ok(result, status_code=202)
    except ValueError as exc:
        return err(exc, status_code=400)
    except Exception as exc:
        return err(exc)


@router.get("/session/prepare/{prepare_id}")
async def get_worldline_prepare(prepare_id: str, project_id: str | None = None, graph_id: str | None = None):
    try:
        run, container_dir = prepare_service().get_prepare(prepare_id, project_id=project_id, graph_id=graph_id)
        return ok(run | {"events": WorldlinePrepareRepository(get_engine()).list_events(prepare_id)})
    except ValueError as exc:
        return err(exc, status_code=404)
    except Exception as exc:
        return err(exc)


@router.get("/session/prepare/{prepare_id}/agents")
async def list_worldline_prepare_agents(prepare_id: str, project_id: str | None = None, graph_id: str | None = None):
    try:
        agents, run = prepare_service().list_prepare_agents(prepare_id, project_id=project_id, graph_id=graph_id)
        return ok({"prepare_id": prepare_id, "status": run["status"], "agents": [{**item, "prepare_id": prepare_id} for item in agents]})
    except ValueError as exc:
        return err(exc, status_code=404)
    except Exception as exc:
        return err(exc)


@router.post("/session/prepare/{prepare_id}/start")
async def start_worldline_from_prepare(prepare_id: str, body: StartFromPrepareRequest = Body(default_factory=StartFromPrepareRequest)):
    try:
        payload = body.model_dump()
        project_id, graph_id = project_graph(payload)
        session, run = prepare_service().start_session(prepare_id, project_id=project_id, graph_id=graph_id)
        return ok({"prepare_id": prepare_id, "session_id": session.session_id, "project_id": session.project_id, "graph_id": session.graph_id, "started_at": session.created_at, "prepare_status": run["status"]})
    except ValueError as exc:
        return err(exc, status_code=400)
    except Exception as exc:
        return err(exc)


@router.get("/session/{session_id}/agents/{agent_id}")
async def get_worldline_agent_detail(session_id: str, agent_id: str, project_id: str | None = None, graph_id: str | None = None, branch_id: str | None = None, limit: int = 20):
    session, container_dir, branch = branch_context(session_id, {"project_id": project_id, "graph_id": graph_id, "branch_id": branch_id})
    if not session:
        return err(f"世界线会话不存在: {session_id}", status_code=404)
    agent = runtime_service().resolve_agent(container_dir, session, branch.branch_id, agent_id)
    if not agent:
        return err(f"世界线中不存在 agent: {agent_id}", status_code=404)
    return ok({"session_id": session.session_id, "branch_id": branch.branch_id, "agent_id": agent["agent_id"], "baseline_dossier": prepare_service().get_dossier_for_session(container_dir, session, agent["agent_id"]), "current_agent": agent, "history": runtime_service().agent_history(container_dir, session.session_id, branch.branch_id, agent["agent_id"], limit), "memories": memory_service().agent_memories(container_dir, session.session_id, branch.branch_id, agent, limit), "relation_history": runtime_service().list_relation_history(container_dir, session.session_id, branch.branch_id, agent["agent_id"], limit)})


@router.post("/session/{session_id}/events/adopt")
async def adopt_events(session_id: str, body: AdoptEventsRequest):
    payload = body.model_dump()
    event_ids, action = payload.get("event_ids", []), payload.get("action", "")
    if not event_ids or not action:
        return err("event_ids and action are required", status_code=400)
    session, container_dir = session_context(session_id, payload)
    if not session:
        return err(f"Session not found: {session_id}", status_code=404)
    result = WorldlineEventService(store=_store).adopt_events(session, container_dir, event_ids, action)
    world = current_world(session)
    return ok({"session_id": session_id, **result, "current_world": {"current_step": world.current_step, "timeline_size": len(world.timeline), "canon_count": sum(1 for e in world.timeline if e.status == "canon"), "candidate_count": sum(1 for e in world.timeline if e.status == "candidate")}})


@router.post("/session/{session_id}/events/{event_id}/edit")
async def edit_event(session_id: str, event_id: str, body: EditEventRequest):
    payload = body.model_dump()
    consequence = payload.get("consequence", "").strip()
    if not consequence:
        return err("consequence is required", status_code=400)
    session, container_dir = session_context(session_id, payload)
    if not session:
        return err(f"Session not found: {session_id}", status_code=404)
    return ok({"session_id": session_id, **WorldlineEventService(store=_store).edit_event(session, container_dir, event_id, consequence)})


@router.get("/session/{session_id}/events/candidates")
async def list_candidate_events(session_id: str, project_id: str | None = None, graph_id: str | None = None, step: int | None = None):
    session, _ = session_context(session_id, {"project_id": project_id, "graph_id": graph_id})
    if not session:
        return err(f"Session not found: {session_id}", status_code=404)
    candidates = WorldlineEventService(store=_store).list_candidate_events(session, step=step)
    return ok({"session_id": session_id, "candidates": candidates, "count": len(candidates)})


@router.get("/session/{session_id}/events/canon")
async def list_canon_events(session_id: str, project_id: str | None = None, graph_id: str | None = None):
    session, _ = session_context(session_id, {"project_id": project_id, "graph_id": graph_id})
    if not session:
        return err(f"Session not found: {session_id}", status_code=404)
    canon = WorldlineEventService(store=_store).list_canon_events(session)
    return ok({"session_id": session_id, "canon": canon, "count": len(canon)})


@router.post("/session/{session_id}/auto-evolve/stream")
async def auto_evolve_stream(session_id: str, body: AutoEvolveRequest):
    payload = body.model_dump()

    async def stream():
        project_id, graph_id = project_graph(payload)
        try:
            yield _sse("evolve_start", {"session_id": session_id})
            tasks = await worldline_auto_evolution_task_service.start_tasks(
                session_id=session_id,
                project_id=project_id,
                graph_id=graph_id,
                branch_ids=payload.get("branch_ids"),
                mode=(payload.get("mode") or "").strip(),
                goal_text=str(payload.get("goal_text") or ""),
                max_steps=payload.get("max_steps"),
            )
            yield _sse("evolve_task", {"session_id": session_id, "tasks": tasks})
            yield _sse("done", {"session_id": session_id, "task_count": len(tasks)})
        except Exception as exc:
            yield _sse("error", {"message": str(exc)})

    return StreamingResponse(
        stream(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no", "Connection": "keep-alive"},
    )


def _sse(event_type: str, data: dict) -> str:
    return (
        f"event: {event_type}\n"
        f"data: {json.dumps({'type': event_type, **data}, ensure_ascii=False)}\n\n"
    )
