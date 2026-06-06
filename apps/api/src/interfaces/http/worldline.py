from fastapi import APIRouter, Header, HTTPException, Query, Request
from sqlalchemy import select

from src.bootstrap.database import resolve_database_engine
from src.modules.worldline.memory_query_service import fetch_agent_memory, fetch_agent_memory_context
from src.modules.worldline.query_service import (
    fetch_agent_actions,
    fetch_agent_dialogues,
    fetch_agent_history,
    fetch_relation_history,
    fetch_session_agent,
    fetch_session_events,
)
from src.shared.db.base import metadata
from src.shared.schemas import ErrorResponse

router = APIRouter(prefix="/worldlines", tags=["worldline"])

def _not_implemented(trace_id: str, code: str, message: str, details: dict) -> HTTPException:
    return HTTPException(
        status_code=501,
        detail={
            "trace_id": trace_id,
            "error": {
                "code": code,
                "message": message,
                "details": details,
                "retryable": False,
            },
        },
    )


def _not_found(trace_id: str, code: str, message: str, details: dict) -> HTTPException:
    return HTTPException(
        status_code=404,
        detail={
            "trace_id": trace_id,
            "error": {
                "code": code,
                "message": message,
                "details": details,
                "retryable": False,
            },
        },
    )
@router.post("/preparations", responses={501: {"model": ErrorResponse}})
def create_preparation(x_trace_id: str | None = Header(default=None)) -> dict:
    raise _not_implemented(x_trace_id or "trace-not-provided", "worldline_preparation_not_implemented", "Worldline preparation contract is frozen, implementation lands next", {})
@router.get("/preparations/{preparation_id}", responses={501: {"model": ErrorResponse}})
def get_preparation(preparation_id: str, request: Request, x_trace_id: str | None = Header(default=None)) -> dict:
    engine = resolve_database_engine(request.app)
    stmt = select(metadata.tables["worldline_preparations"]).where(
        metadata.tables["worldline_preparations"].c.prepare_id == preparation_id
    )
    with engine.connect() as connection:
        row = connection.execute(stmt).first()
    if row is None:
        raise HTTPException(
            status_code=404,
            detail={
                "trace_id": x_trace_id or "trace-not-provided",
                "error": {
                    "code": "worldline_preparation_not_found",
                    "message": "Worldline preparation not found",
                    "details": {"preparation_id": preparation_id},
                    "retryable": False,
                },
            },
        )
    return {
        "data": {
            "prepare_id": row.prepare_id,
            "project_id": row.project_id,
            "status": row.status,
            "session_scope": row.session_scope,
            "focus_question": row.focus_question,
            "started_session_id": row.started_session_id,
        },
        "meta": {"trace_id": x_trace_id or "trace-not-provided", "version": "v2"},
    }
@router.get("/preparations/{preparation_id}/agents", responses={501: {"model": ErrorResponse}})
def get_preparation_agents(preparation_id: str, request: Request, x_trace_id: str | None = Header(default=None)) -> dict:
    engine = resolve_database_engine(request.app)
    stmt = select(metadata.tables["prepared_agent_dossiers"]).where(
        metadata.tables["prepared_agent_dossiers"].c.prepare_id == preparation_id
    )
    with engine.connect() as connection:
        rows = connection.execute(stmt).all()
    items = [
        {
            "prepared_agent_dossier_id": row.prepared_agent_dossier_id,
            "prepare_id": row.prepare_id,
            "agent_id": row.agent_id,
            "agent_kind": row.agent_kind,
            "display_name": row.display_name,
            "template_key": row.template_key,
            "template_version": row.template_version,
        }
        for row in rows
    ]
    return {"data": {"count": len(items), "items": items}, "meta": {"trace_id": x_trace_id or "trace-not-provided", "version": "v2"}}
@router.post("/preparations/{preparation_id}/start", responses={501: {"model": ErrorResponse}})
def start_preparation(preparation_id: str, x_trace_id: str | None = Header(default=None)) -> dict:
    raise _not_implemented(x_trace_id or "trace-not-provided", "worldline_preparation_start_not_implemented", "Worldline preparation start contract is frozen, implementation lands next", {"preparation_id": preparation_id})
@router.post("/sessions", responses={501: {"model": ErrorResponse}})
def create_worldline_session(x_trace_id: str | None = Header(default=None)) -> dict:
    raise _not_implemented(x_trace_id or "trace-not-provided", "worldline_session_create_not_implemented", "Worldline session contract is frozen, implementation lands next", {})
@router.get("/sessions", responses={501: {"model": ErrorResponse}})
def list_worldline_sessions(request: Request, x_trace_id: str | None = Header(default=None)) -> dict:
    engine = resolve_database_engine(request.app)
    with engine.connect() as connection:
        rows = connection.execute(select(metadata.tables["worldline_sessions"])).all()
    items = [
        {
            "session_id": row.session_id,
            "project_id": row.project_id,
            "session_scope": row.session_scope,
            "simulation_goal": row.simulation_goal,
            "focus_question": row.focus_question,
            "status": row.status,
        }
        for row in rows
    ]
    return {"data": {"count": len(items), "items": items}, "meta": {"trace_id": x_trace_id or "trace-not-provided", "version": "v2"}}
@router.get("/sessions/{session_id}", responses={501: {"model": ErrorResponse}})
def get_worldline_session(session_id: str, request: Request, x_trace_id: str | None = Header(default=None)) -> dict:
    engine = resolve_database_engine(request.app)
    stmt = select(metadata.tables["worldline_sessions"]).where(
        metadata.tables["worldline_sessions"].c.session_id == session_id
    )
    with engine.connect() as connection:
        row = connection.execute(stmt).first()
    if row is None:
        raise HTTPException(
            status_code=404,
            detail={
                "trace_id": x_trace_id or "trace-not-provided",
                "error": {
                    "code": "worldline_session_not_found",
                    "message": "Worldline session not found",
                    "details": {"session_id": session_id},
                    "retryable": False,
                },
            },
        )
    return {
        "data": {
            "session_id": row.session_id,
            "project_id": row.project_id,
            "session_scope": row.session_scope,
            "simulation_goal": row.simulation_goal,
            "focus_question": row.focus_question,
            "status": row.status,
            "created_from_prepare_run_id": row.created_from_prepare_run_id,
        },
        "meta": {"trace_id": x_trace_id or "trace-not-provided", "version": "v2"},
    }
@router.get("/sessions/{session_id}/timeline", responses={501: {"model": ErrorResponse}})
def get_worldline_timeline(session_id: str, request: Request, x_trace_id: str | None = Header(default=None)) -> dict:
    engine = resolve_database_engine(request.app)
    stmt = (
        select(metadata.tables["timeline_events"])
        .where(metadata.tables["timeline_events"].c.session_id == session_id)
        .order_by(metadata.tables["timeline_events"].c.step_no.asc())
    )
    with engine.connect() as connection:
        rows = connection.execute(stmt).all()
    items = [
        {
            "timeline_event_id": row.timeline_event_id,
            "session_id": row.session_id,
            "world_state_id": row.world_state_id,
            "step_no": row.step_no,
            "event_type": row.event_type,
            "title": row.title,
            "summary": row.summary,
            "status": row.status,
            "created_at": row.created_at.isoformat() if hasattr(row.created_at, "isoformat") else row.created_at,
        }
        for row in rows
    ]
    return {"data": {"count": len(items), "items": items}, "meta": {"trace_id": x_trace_id or "trace-not-provided", "version": "v2"}}
@router.post("/sessions/{session_id}/commands/advance", responses={501: {"model": ErrorResponse}})
def advance_worldline(session_id: str, x_trace_id: str | None = Header(default=None)) -> dict:
    raise _not_implemented(x_trace_id or "trace-not-provided", "worldline_advance_not_implemented", "Worldline advance contract is frozen, implementation lands next", {"session_id": session_id})


@router.post("/sessions/{session_id}/commands/inject-variable", responses={501: {"model": ErrorResponse}})
def inject_worldline_variable(session_id: str, x_trace_id: str | None = Header(default=None)) -> dict:
    raise _not_implemented(x_trace_id or "trace-not-provided", "worldline_variable_injection_not_implemented", "Worldline variable injection contract is frozen, implementation lands next", {"session_id": session_id})


@router.post("/sessions/{session_id}/commands/agent-actions", responses={501: {"model": ErrorResponse}})
def create_agent_action(session_id: str, x_trace_id: str | None = Header(default=None)) -> dict:
    raise _not_implemented(x_trace_id or "trace-not-provided", "worldline_agent_action_not_implemented", "Worldline agent action contract is frozen, implementation lands next", {"session_id": session_id})


@router.post("/sessions/{session_id}/commands/agent-dialogues", responses={501: {"model": ErrorResponse}})
def create_agent_dialogue(session_id: str, x_trace_id: str | None = Header(default=None)) -> dict:
    raise _not_implemented(x_trace_id or "trace-not-provided", "worldline_agent_dialogue_not_implemented", "Worldline agent dialogue contract is frozen, implementation lands next", {"session_id": session_id})


@router.get("/sessions/{session_id}/agents/{agent_id}", responses={501: {"model": ErrorResponse}})
def get_session_agent(session_id: str, agent_id: str, request: Request, x_trace_id: str | None = Header(default=None)) -> dict:
    engine = resolve_database_engine(request.app)
    item = fetch_session_agent(engine, session_id, agent_id)
    if item is None:
        raise _not_found(x_trace_id or "trace-not-provided", "worldline_agent_not_found", "Worldline agent not found", {"session_id": session_id, "agent_id": agent_id})
    return {"data": item, "meta": {"trace_id": x_trace_id or "trace-not-provided", "version": "v2"}}


@router.get("/sessions/{session_id}/agent-history", responses={501: {"model": ErrorResponse}})
def get_agent_history(session_id: str, request: Request, agent_id: str = Query(...), x_trace_id: str | None = Header(default=None)) -> dict:
    engine = resolve_database_engine(request.app)
    item = fetch_agent_history(engine, session_id, agent_id)
    if item is None:
        raise _not_found(x_trace_id or "trace-not-provided", "worldline_agent_not_found", "Worldline agent not found", {"session_id": session_id, "agent_id": agent_id})
    return {"data": item, "meta": {"trace_id": x_trace_id or "trace-not-provided", "version": "v2"}}


@router.get("/sessions/{session_id}/agent-actions", responses={501: {"model": ErrorResponse}})
def list_agent_actions(session_id: str, request: Request, agent_id: str | None = Query(default=None), x_trace_id: str | None = Header(default=None)) -> dict:
    engine = resolve_database_engine(request.app)
    items = fetch_agent_actions(engine, session_id, agent_id)
    if items is None:
        raise _not_found(x_trace_id or "trace-not-provided", "worldline_agent_not_found", "Worldline agent not found", {"session_id": session_id, "agent_id": agent_id})
    return {"data": {"count": len(items), "items": items}, "meta": {"trace_id": x_trace_id or "trace-not-provided", "version": "v2"}}


@router.get("/sessions/{session_id}/agent-memory", responses={501: {"model": ErrorResponse}})
def get_agent_memory(session_id: str, request: Request, agent_id: str = Query(...), x_trace_id: str | None = Header(default=None)) -> dict:
    engine = resolve_database_engine(request.app)
    item = fetch_agent_memory(engine, session_id, agent_id)
    if item is None:
        raise _not_found(x_trace_id or "trace-not-provided", "worldline_agent_not_found", "Worldline agent not found", {"session_id": session_id, "agent_id": agent_id})
    return {"data": item, "meta": {"trace_id": x_trace_id or "trace-not-provided", "version": "v2"}}


@router.get("/sessions/{session_id}/agent-memory-context", responses={501: {"model": ErrorResponse}})
def get_agent_memory_context(session_id: str, request: Request, agent_id: str = Query(...), message: str | None = Query(default=None), x_trace_id: str | None = Header(default=None)) -> dict:
    engine = resolve_database_engine(request.app)
    item = fetch_agent_memory_context(engine, session_id, agent_id, message)
    if item is None:
        raise _not_found(x_trace_id or "trace-not-provided", "worldline_agent_not_found", "Worldline agent not found", {"session_id": session_id, "agent_id": agent_id})
    return {"data": item, "meta": {"trace_id": x_trace_id or "trace-not-provided", "version": "v2"}}


@router.get("/sessions/{session_id}/agent-dialogues", responses={501: {"model": ErrorResponse}})
def list_agent_dialogues(session_id: str, request: Request, agent_id: str | None = Query(default=None), x_trace_id: str | None = Header(default=None)) -> dict:
    engine = resolve_database_engine(request.app)
    items = fetch_agent_dialogues(engine, session_id, agent_id)
    if items is None:
        raise _not_found(x_trace_id or "trace-not-provided", "worldline_agent_not_found", "Worldline agent not found", {"session_id": session_id, "agent_id": agent_id})
    return {"data": {"count": len(items), "items": items}, "meta": {"trace_id": x_trace_id or "trace-not-provided", "version": "v2"}}


@router.get("/sessions/{session_id}/relations", responses={501: {"model": ErrorResponse}})
def get_relation_history(session_id: str, request: Request, agent_id: str | None = Query(default=None), x_trace_id: str | None = Header(default=None)) -> dict:
    engine = resolve_database_engine(request.app)
    items = fetch_relation_history(engine, session_id, agent_id)
    if items is None:
        raise _not_found(x_trace_id or "trace-not-provided", "worldline_agent_not_found", "Worldline agent not found", {"session_id": session_id, "agent_id": agent_id})
    return {"data": {"count": len(items), "items": items}, "meta": {"trace_id": x_trace_id or "trace-not-provided", "version": "v2"}}


@router.get("/sessions/{session_id}/events", responses={501: {"model": ErrorResponse}})
def list_worldline_events(session_id: str, request: Request, status: str | None = Query(default=None), x_trace_id: str | None = Header(default=None)) -> dict:
    engine = resolve_database_engine(request.app)
    items = fetch_session_events(engine, session_id, status)
    return {"data": {"count": len(items), "items": items}, "meta": {"trace_id": x_trace_id or "trace-not-provided", "version": "v2"}}


@router.post("/sessions/{session_id}/auto-evolutions", responses={501: {"model": ErrorResponse}})
def start_auto_evolution(session_id: str, x_trace_id: str | None = Header(default=None)) -> dict:
    raise _not_implemented(x_trace_id or "trace-not-provided", "worldline_auto_evolution_not_implemented", "Worldline auto-evolution contract is frozen, implementation lands next", {"session_id": session_id})


@router.post("/sessions/{session_id}/auto-evolutions/{auto_evolution_id}/events", responses={501: {"model": ErrorResponse}})
def stream_auto_evolution(session_id: str, auto_evolution_id: str, x_trace_id: str | None = Header(default=None)) -> dict:
    raise _not_implemented(x_trace_id or "trace-not-provided", "worldline_auto_evolution_events_not_implemented", "Worldline auto-evolution events contract is frozen, implementation lands next", {"session_id": session_id, "auto_evolution_id": auto_evolution_id})
