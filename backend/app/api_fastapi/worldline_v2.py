"""Resource-oriented worldline API v2 routes."""

from __future__ import annotations

import json

from fastapi import APIRouter, Body
from fastapi.responses import StreamingResponse

from app.database import get_engine
from app.repositories.worldline_prepare_repo import WorldlinePrepareRepository
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
from app.services.worldline_event_service import WorldlineEventService
from app.services.worldline_single_world import current_world, resolve_branch_id

from .common import err, ok
from .worldline import (
    _store,
    branch_context,
    character_agent_service,
    current_world_payload,
    engine,
    memory_service,
    prepare_service,
    project_graph,
    runtime_service,
    session_context,
    worldline_auto_evolution_task_service,
)

router = APIRouter(prefix="/worldlines", tags=["worldline-v2"])


def _sse_v2(event_type: str, data: dict) -> str:
    return (
        f"event: {event_type}\n"
        f"data: {json.dumps({'type': event_type, **data}, ensure_ascii=False)}\n\n"
    )


@router.post("/preparations")
async def prepare_worldline_session_v2(body: PrepareSessionRequest):
    try:
        payload = body.model_dump()
        result = await prepare_service().start_prepare(
            label=payload.get("label", ""),
            project_id=payload.get("project_id"),
            graph_id=payload.get("graph_id"),
            variables=payload.get("variables"),
            focus_question=payload.get("focus_question"),
            archives=payload.get("archives"),
            archive_ids=payload.get("archive_ids"),
            entity_types=payload.get("entity_types"),
            config=payload.get("config"),
        )
        return ok(result, status_code=202)
    except ValueError as exc:
        return err(exc, status_code=400)
    except Exception as exc:
        return err(exc)


@router.get("/preparations/{prepare_id}")
async def get_worldline_prepare_v2(
    prepare_id: str,
    project_id: str | None = None,
    graph_id: str | None = None,
):
    try:
        run, _ = prepare_service().get_prepare(
            prepare_id,
            project_id=project_id,
            graph_id=graph_id,
        )
        return ok(run | {"events": WorldlinePrepareRepository(get_engine()).list_events(prepare_id)})
    except ValueError as exc:
        return err(exc, status_code=404)
    except Exception as exc:
        return err(exc)


@router.get("/preparations/{prepare_id}/agents")
async def list_worldline_prepare_agents_v2(
    prepare_id: str,
    project_id: str | None = None,
    graph_id: str | None = None,
):
    try:
        agents, run = prepare_service().list_prepare_agents(
            prepare_id,
            project_id=project_id,
            graph_id=graph_id,
        )
        return ok(
            {
                "prepare_id": prepare_id,
                "status": run["status"],
                "agents": [{**item, "prepare_id": prepare_id} for item in agents],
            }
        )
    except ValueError as exc:
        return err(exc, status_code=404)
    except Exception as exc:
        return err(exc)


@router.post("/preparations/{prepare_id}/start")
async def start_worldline_from_prepare_v2(
    prepare_id: str,
    body: StartFromPrepareRequest = Body(default_factory=StartFromPrepareRequest),
):
    try:
        payload = body.model_dump()
        project_id, graph_id = project_graph(payload)
        session, run = prepare_service().start_session(
            prepare_id,
            project_id=project_id,
            graph_id=graph_id,
        )
        return ok(
            {
                "prepare_id": prepare_id,
                "session_id": session.session_id,
                "project_id": session.project_id,
                "graph_id": session.graph_id,
                "started_at": session.created_at,
                "prepare_status": run["status"],
            }
        )
    except ValueError as exc:
        return err(exc, status_code=400)
    except Exception as exc:
        return err(exc)


@router.post("/sessions")
async def create_worldline_session_v2(body: CreateSessionRequest):
    try:
        payload = body.model_dump()
        project_id, graph_id = project_graph(payload)
        session, _ = engine().create_session(
            project_id=project_id,
            graph_id=graph_id,
            label=payload.get("label", ""),
            variables=payload.get("variables", []),
            focus_question=payload.get("focus_question"),
            branch_count=payload.get("branch_count"),
            archives=payload.get("archives"),
            archive_ids=payload.get("archive_ids"),
            entity_types=payload.get("entity_types"),
            config=payload.get("config"),
        )
        return ok(
            {
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
            }
        )
    except ValueError as exc:
        return err(exc, status_code=400)
    except Exception as exc:
        return err(exc)


@router.get("/sessions")
async def list_worldline_sessions_v2(
    project_id: str | None = None,
    graph_id: str | None = None,
    limit: int = 20,
):
    try:
        sessions = engine().list_sessions(project_id=project_id, graph_id=graph_id, limit=limit)
        return ok({"sessions": sessions, "count": len(sessions)})
    except Exception as exc:
        return err(exc)


@router.get("/sessions/{session_id}")
async def get_worldline_session_v2(
    session_id: str,
    project_id: str | None = None,
    graph_id: str | None = None,
):
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


@router.get("/sessions/{session_id}/branches")
async def list_worldline_branches_v2(session_id: str):
    return err("单世界世界线已不再支持分支列表接口，请改用 session 或 timeline 接口", status_code=410)


@router.get("/sessions/{session_id}/comparison")
async def get_worldline_comparison_v2(session_id: str):
    return err("单世界世界线已不再支持分支对比接口，请改用 session 接口读取当前世界", status_code=410)


@router.get("/sessions/{session_id}/timeline")
async def get_worldline_timeline_v2(
    session_id: str,
    project_id: str | None = None,
    graph_id: str | None = None,
    branch_id: str | None = None,
    limit: int = 30,
):
    try:
        session = engine().get_session(session_id, project_id=project_id, graph_id=graph_id)
        if not session:
            return err(f"世界线会话不存在: {session_id}", status_code=404)
        resolve_branch_id(branch_id)
        world = current_world(session)
        return ok(
            {
                "session_id": session_id,
                "branch_id": world.branch_id,
                "events": [event.to_dict() for event in world.timeline[-limit:]],
            }
        )
    except ValueError as exc:
        return err(exc, status_code=400)
    except Exception as exc:
        return err(exc)


@router.get("/sessions/{session_id}/events")
async def list_worldline_events_v2(
    session_id: str,
    project_id: str | None = None,
    graph_id: str | None = None,
    status: str = "candidate",
    step: int | None = None,
):
    try:
        session, _ = session_context(
            session_id,
            {"project_id": project_id, "graph_id": graph_id},
        )
        if not session:
            return err(f"Session not found: {session_id}", status_code=404)
        service = WorldlineEventService(store=_store)
        if status == "candidate":
            events = service.list_candidate_events(session, step=step)
        elif status == "canon":
            events = service.list_canon_events(session)
            if step is not None:
                events = [event for event in events if event.get("step") == step]
        else:
            return err("status must be 'candidate' or 'canon'", status_code=400)
        return ok({"session_id": session_id, "status": status, "events": events, "count": len(events)})
    except ValueError as exc:
        return err(exc, status_code=400)
    except Exception as exc:
        return err(exc)


@router.post("/sessions/{session_id}/event-adoptions")
async def adopt_worldline_events_v2(session_id: str, body: AdoptEventsRequest):
    try:
        payload = body.model_dump()
        event_ids, action = payload.get("event_ids", []), payload.get("action", "")
        if not event_ids or not action:
            return err("event_ids and action are required", status_code=400)
        session, container_dir = session_context(session_id, payload)
        if not session:
            return err(f"Session not found: {session_id}", status_code=404)
        result = WorldlineEventService(store=_store).adopt_events(session, container_dir, event_ids, action)
        world = current_world(session)
        return ok(
            {
                "session_id": session_id,
                **result,
                "current_world": {
                    "current_step": world.current_step,
                    "timeline_size": len(world.timeline),
                    "canon_count": sum(1 for event in world.timeline if event.status == "canon"),
                    "candidate_count": sum(1 for event in world.timeline if event.status == "candidate"),
                },
            }
        )
    except ValueError as exc:
        return err(exc, status_code=400)
    except Exception as exc:
        return err(exc)


@router.post("/sessions/{session_id}/events/{event_id}")
async def edit_worldline_event_v2(session_id: str, event_id: str, body: EditEventRequest):
    try:
        payload = body.model_dump()
        consequence = payload.get("consequence", "").strip()
        if not consequence:
            return err("consequence is required", status_code=400)
        session, container_dir = session_context(session_id, payload)
        if not session:
            return err(f"Session not found: {session_id}", status_code=404)
        return ok(
            {
                "session_id": session_id,
                **WorldlineEventService(store=_store).edit_event(session, container_dir, event_id, consequence),
            }
        )
    except ValueError as exc:
        return err(exc, status_code=400)
    except Exception as exc:
        return err(exc)


@router.post("/sessions/{session_id}/auto-evolutions")
async def start_worldline_auto_evolution_v2(session_id: str, body: AutoEvolveRequest):
    try:
        payload = body.model_dump()
        project_id, graph_id = project_graph(payload)
        tasks = await worldline_auto_evolution_task_service.start_tasks(
            session_id=session_id,
            project_id=project_id,
            graph_id=graph_id,
            branch_ids=payload.get("branch_ids"),
            mode=(payload.get("mode") or "").strip(),
            goal_text=str(payload.get("goal_text") or ""),
            max_steps=payload.get("max_steps"),
        )
        return ok(
            {
                "session_id": session_id,
                "auto_evolution_id": tasks[0]["task_id"] if tasks else None,
                "tasks": tasks,
            },
            status_code=202,
        )
    except ValueError as exc:
        return err(exc, status_code=400)
    except Exception as exc:
        return err(exc)


@router.post("/sessions/{session_id}/auto-evolutions/{auto_evolution_id}/events")
async def stream_worldline_auto_evolution_events_v2(
    session_id: str,
    auto_evolution_id: str,
    body: AutoEvolveRequest,
):
    payload = body.model_dump()

    async def stream():
        project_id, graph_id = project_graph(payload)
        try:
            yield _sse_v2(
                "evolve_start",
                {"session_id": session_id, "auto_evolution_id": auto_evolution_id},
            )
            tasks = await worldline_auto_evolution_task_service.start_tasks(
                session_id=session_id,
                project_id=project_id,
                graph_id=graph_id,
                branch_ids=payload.get("branch_ids"),
                mode=(payload.get("mode") or "").strip(),
                goal_text=str(payload.get("goal_text") or ""),
                max_steps=payload.get("max_steps"),
            )
            yield _sse_v2(
                "evolve_task",
                {
                    "session_id": session_id,
                    "auto_evolution_id": auto_evolution_id,
                    "tasks": tasks,
                },
            )
            yield _sse_v2(
                "done",
                {
                    "session_id": session_id,
                    "auto_evolution_id": auto_evolution_id,
                    "task_count": len(tasks),
                },
            )
        except Exception as exc:
            yield _sse_v2(
                "error",
                {"auto_evolution_id": auto_evolution_id, "message": str(exc)},
            )

    return StreamingResponse(
        stream(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",
            "Connection": "keep-alive",
        },
    )


@router.get("/sessions/{session_id}/agent-actions")
async def list_agent_actions_v2(
    session_id: str,
    project_id: str | None = None,
    graph_id: str | None = None,
    branch_id: str | None = None,
    agent_id: str | None = None,
    status: str | None = None,
    limit: int = 20,
):
    session, container_dir = session_context(
        session_id,
        {"project_id": project_id, "graph_id": graph_id},
    )
    if not session:
        return err(f"世界线会话不存在: {session_id}", status_code=404)
    return ok(
        {
            "session_id": session.session_id,
            "items": runtime_service().list_actions(
                container_dir,
                session.session_id,
                resolve_branch_id(branch_id),
                agent_id,
                status,
                limit,
            ),
        }
    )


@router.get("/sessions/{session_id}/agent-dialogues")
async def list_agent_dialogues_v2(
    session_id: str,
    project_id: str | None = None,
    graph_id: str | None = None,
    branch_id: str | None = None,
    agent_id: str | None = None,
    limit: int = 20,
):
    session, container_dir = session_context(
        session_id,
        {"project_id": project_id, "graph_id": graph_id},
    )
    if not session:
        return err(f"世界线会话不存在: {session_id}", status_code=404)
    return ok(
        {
            "session_id": session.session_id,
            "items": runtime_service().list_dialogues(
                container_dir,
                session.session_id,
                resolve_branch_id(branch_id),
                agent_id,
                limit,
            ),
        }
    )


@router.get("/sessions/{session_id}/agent-history")
async def get_agent_history_v2(
    session_id: str,
    agent_id: str = "",
    project_id: str | None = None,
    graph_id: str | None = None,
    branch_id: str | None = None,
    limit: int = 20,
):
    try:
        session, container_dir, branch = branch_context(
            session_id,
            {"project_id": project_id, "graph_id": graph_id, "branch_id": branch_id},
        )
        if not session:
            return err(f"世界线会话不存在: {session_id}", status_code=404)
        if not agent_id:
            return err("请提供 agent_id", status_code=400)
        return ok(
            {
                "session_id": session.session_id,
                "branch_id": branch.branch_id,
                "agent_id": agent_id,
                **runtime_service().agent_history(
                    container_dir,
                    session.session_id,
                    branch.branch_id,
                    agent_id,
                    limit,
                ),
            }
        )
    except ValueError as exc:
        return err(exc, status_code=400)
    except Exception as exc:
        return err(exc)


@router.get("/sessions/{session_id}/agent-memory")
async def get_agent_memory_v2(
    session_id: str,
    agent_id: str = "",
    project_id: str | None = None,
    graph_id: str | None = None,
    branch_id: str | None = None,
    limit: int = 20,
):
    session, container_dir, branch = branch_context(
        session_id,
        {"project_id": project_id, "graph_id": graph_id, "branch_id": branch_id},
    )
    if not session:
        return err(f"世界线会话不存在: {session_id}", status_code=404)
    agent = runtime_service().resolve_agent(container_dir, session, branch.branch_id, agent_id)
    if not agent:
        return err(f"世界线中不存在 agent: {agent_id}", status_code=404)
    return ok(
        {
            "session_id": session.session_id,
            "branch_id": branch.branch_id,
            "agent_id": agent["agent_id"],
            **memory_service().agent_memories(
                container_dir,
                session.session_id,
                branch.branch_id,
                agent,
                limit,
            ),
        }
    )


@router.get("/sessions/{session_id}/agent-memory-context")
async def get_agent_memory_context_v2(
    session_id: str,
    agent_id: str = "",
    message: str = "",
    project_id: str | None = None,
    graph_id: str | None = None,
    branch_id: str | None = None,
    limit: int = 20,
):
    session, container_dir, branch = branch_context(
        session_id,
        {"project_id": project_id, "graph_id": graph_id, "branch_id": branch_id},
    )
    if not session:
        return err(f"世界线会话不存在: {session_id}", status_code=404)
    agent = runtime_service().resolve_agent(container_dir, session, branch.branch_id, agent_id)
    if not agent:
        return err(f"世界线中不存在 agent: {agent_id}", status_code=404)
    return ok(
        {
            "session_id": session.session_id,
            "branch_id": branch.branch_id,
            "agent_id": agent["agent_id"],
            **memory_service().build_context_bundle(
                container_dir,
                session.session_id,
                branch.branch_id,
                agent,
                message,
                limit,
            ),
        }
    )


@router.get("/sessions/{session_id}/relations")
async def list_relation_history_v2(
    session_id: str,
    project_id: str | None = None,
    graph_id: str | None = None,
    branch_id: str | None = None,
    agent_id: str | None = None,
    limit: int = 20,
):
    session, container_dir = session_context(
        session_id,
        {"project_id": project_id, "graph_id": graph_id},
    )
    if not session:
        return err(f"世界线会话不存在: {session_id}", status_code=404)
    return ok(
        {
            "session_id": session.session_id,
            "items": runtime_service().list_relation_history(
                container_dir,
                session.session_id,
                resolve_branch_id(branch_id),
                agent_id,
                limit,
            ),
        }
    )


@router.get("/sessions/{session_id}/agents/{agent_id}")
async def get_worldline_agent_detail_v2(
    session_id: str,
    agent_id: str,
    project_id: str | None = None,
    graph_id: str | None = None,
    branch_id: str | None = None,
    limit: int = 20,
):
    session, container_dir, branch = branch_context(
        session_id,
        {"project_id": project_id, "graph_id": graph_id, "branch_id": branch_id},
    )
    if not session:
        return err(f"世界线会话不存在: {session_id}", status_code=404)
    agent = runtime_service().resolve_agent(container_dir, session, branch.branch_id, agent_id)
    if not agent:
        return err(f"世界线中不存在 agent: {agent_id}", status_code=404)
    return ok(
        {
            "session_id": session.session_id,
            "branch_id": branch.branch_id,
            "agent_id": agent["agent_id"],
            "baseline_dossier": prepare_service().get_dossier_for_session(
                container_dir,
                session,
                agent["agent_id"],
            ),
            "current_agent": agent,
            "history": runtime_service().agent_history(
                container_dir,
                session.session_id,
                branch.branch_id,
                agent["agent_id"],
                limit,
            ),
            "memories": memory_service().agent_memories(
                container_dir,
                session.session_id,
                branch.branch_id,
                agent,
                limit,
            ),
            "relation_history": runtime_service().list_relation_history(
                container_dir,
                session.session_id,
                branch.branch_id,
                agent["agent_id"],
                limit,
            ),
        }
    )


@router.post("/sessions/{session_id}/commands/advance")
async def advance_worldline_session_v2(session_id: str, body: StepRequest):
    try:
        payload = body.model_dump()
        project_id, graph_id = project_graph(payload)
        steps = int(payload.get("steps", 1))
        session, _, branch = branch_context(session_id, payload)
        if not session:
            return err(f"世界线会话不存在: {session_id}", status_code=404)
        for _ in range(max(1, min(steps, 10))):
            session = engine().step(
                session_id=session_id,
                project_id=project_id,
                graph_id=graph_id,
                branch_id=branch.branch_id,
                steps=1,
                evolution_intensity=payload.get("evolution_intensity", "medium"),
                custom_depth=payload.get("custom_depth"),
            )
            branch = current_world(session)
        return ok(
            {
                "session_id": session.session_id,
                "updated_at": session.updated_at,
                "message": f"世界线已推进 {steps} 步",
                "current_world": current_world_payload(session),
            }
        )
    except ValueError as exc:
        return err(exc, status_code=400)
    except Exception as exc:
        return err(exc)


@router.post("/sessions/{session_id}/commands/inject-variable")
async def inject_variable_v2(session_id: str, body: InjectVariableRequest):
    try:
        payload = body.model_dump()
        project_id, graph_id = project_graph(payload)
        variable = payload.get("variable")
        data = {
            "name": payload.get("name", ""),
            "description": payload.get("description", ""),
            "impact_axis": payload.get("impact_axis", ""),
        }
        if isinstance(variable, str):
            data = {"name": variable.strip(), "description": variable.strip(), "impact_axis": ""}
        elif isinstance(variable, dict):
            data = {
                "name": variable.get("name", ""),
                "description": variable.get("description", ""),
                "impact_axis": variable.get("impact_axis", ""),
            }
        session = engine().inject_variable(
            session_id=session_id,
            project_id=project_id,
            graph_id=graph_id,
            branch_id=payload.get("branch_id"),
            **data,
        )
        return ok(
            {
                "session_id": session.session_id,
                "message": "变量注入成功",
                "world_variables": [item.to_dict() for item in session.world_variables],
                "current_world": current_world_payload(session),
            }
        )
    except ValueError as exc:
        return err(exc, status_code=400)
    except Exception as exc:
        return err(exc)


@router.post("/sessions/{session_id}/commands/agent-actions")
async def inject_agent_action_v2(session_id: str, body: AgentActionRequest):
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
        session, ids = engine().queue_action(
            session_id=session_id,
            agent_id=agent["agent_id"],
            actor=agent["display_name"],
            action=payload.get("action", ""),
            intent=payload.get("intent", ""),
            target=payload.get("target", ""),
            project_id=project_id,
            graph_id=graph_id,
            branch_id=payload.get("branch_id"),
        )
        return ok(
            {
                "session_id": session.session_id,
                "message": "动作已加入世界线待处理队列",
                "action_event_id": ids[0],
                "agent": {
                    "agent_id": agent["agent_id"],
                    "display_name": agent["display_name"],
                    "agent_kind": agent["agent_kind"],
                },
                "current_world": current_world_payload(session),
            }
        )
    except ValueError as exc:
        return err(exc, status_code=400)
    except Exception as exc:
        return err(exc)


@router.post("/sessions/{session_id}/commands/agent-dialogues")
async def agent_dialogue_v2(session_id: str, body: AgentDialogueRequest):
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
        memory = memory_service().build_context_bundle(
            container_dir,
            session.session_id,
            branch.branch_id,
            agent,
            message,
            payload.get("limit", 20),
        )
        result = character_agent_service.generate_reply(
            actor_name=agent["display_name"],
            actor_state=agent["state"],
            message=message,
            recent_events=[item.to_dict() for item in branch.timeline[-4:]],
            branch_summary={
                "branch_id": branch.branch_id,
                "title": branch.title,
                "core_change": branch.core_change,
            },
            mode=(payload.get("mode") or "template").strip(),
            memory_bundle=memory,
            dossier_context=prepare_service().build_dialogue_bundle(container_dir, session, agent),
        )
        dialogue_id = runtime_service().record_dialogue(
            container_dir,
            session,
            branch.branch_id,
            agent,
            message,
            result,
            result["generator_mode"],
            result["model_name"],
            f"{branch.title} | step={branch.current_step} | agent={agent['display_name']} | core={branch.core_change}",
        )
        return ok(
            {
                "session_id": session.session_id,
                "branch_id": branch.branch_id,
                "agent": agent["display_name"],
                "agent_id": agent["agent_id"],
                "dialogue_id": dialogue_id,
                "generator_mode": result["generator_mode"],
                "model_name": result["model_name"],
                "memory_context": memory,
                "result": result,
            }
        )
    except ValueError as exc:
        return err(exc, status_code=400)
    except Exception as exc:
        return err(exc)
