from fastapi import APIRouter, Header, HTTPException, Query, Request
from pydantic import BaseModel
from sqlalchemy import select

from src.bootstrap.database import resolve_database_engine
from src.modules.archive.memory_review_service import adopt_archive_memory, reject_archive_memory
from src.shared.db.base import metadata
from src.shared.schemas import ErrorResponse

router = APIRouter(tags=["archive"])


class MemoryReviewCommand(BaseModel):
    memory_id: str


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


def _error(trace_id: str, status_code: int, code: str, message: str, details: dict) -> HTTPException:
    return HTTPException(
        status_code=status_code,
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


@router.get("/archives", responses={501: {"model": ErrorResponse}})
def list_archives(
    request: Request,
    q: str | None = Query(default=None),
    project_id: str | None = Query(default=None),
    x_trace_id: str | None = Header(default=None),
) -> dict:
    engine = resolve_database_engine(request.app)
    archives = metadata.tables["archives"]
    entities = metadata.tables["entities"]
    projects = metadata.tables["projects"]
    stmt = (
        select(
            archives.c.archive_id,
            archives.c.project_id,
            archives.c.archive_type,
            archives.c.agent_kind,
            archives.c.importance_tier,
            archives.c.selected_importance_tier,
            archives.c.template_key,
            archives.c.template_version,
            entities.c.entity_id,
            entities.c.entity_uuid,
            entities.c.canonical_name,
            entities.c.display_name,
            entities.c.entity_kind,
            projects.c.name.label("project_name"),
        )
        .join(entities, archives.c.entity_id == entities.c.entity_id)
        .join(projects, archives.c.project_id == projects.c.project_id)
    )
    if project_id:
        stmt = stmt.where(archives.c.project_id == project_id)
    with engine.connect() as connection:
        rows = connection.execute(stmt).all()
    items = []
    for row in rows:
        if q and q not in row.display_name and q not in row.project_name:
            continue
        items.append(
            {
                "archive_id": row.archive_id,
                "project_id": row.project_id,
                "project_name": row.project_name,
                "entity_id": row.entity_id,
                "entity_uuid": row.entity_uuid,
                "entity_name": row.display_name,
                "entity_type": row.entity_kind,
                "archive_type": row.archive_type,
                "agent_kind": row.agent_kind,
                "importance_tier": row.importance_tier,
                "selected_importance_tier": row.selected_importance_tier,
                "template_key": row.template_key,
                "template_version": row.template_version,
            }
        )
    return {"data": {"count": len(items), "items": items}, "meta": {"trace_id": x_trace_id or "trace-not-provided", "version": "v2"}}


@router.get("/archives/{archive_id}", responses={501: {"model": ErrorResponse}})
def get_archive(archive_id: str, request: Request, x_trace_id: str | None = Header(default=None)) -> dict:
    engine = resolve_database_engine(request.app)
    archives = metadata.tables["archives"]
    entities = metadata.tables["entities"]
    stmt = (
        select(
            archives.c.archive_id,
            archives.c.project_id,
            archives.c.archive_type,
            archives.c.agent_kind,
            archives.c.importance_tier,
            archives.c.selected_importance_tier,
            archives.c.template_key,
            archives.c.template_version,
            entities.c.entity_uuid,
            entities.c.display_name,
            entities.c.entity_kind,
            entities.c.summary,
        )
        .join(entities, archives.c.entity_id == entities.c.entity_id)
        .where(archives.c.archive_id == archive_id)
    )
    with engine.connect() as connection:
        row = connection.execute(stmt).first()
    if row is None:
        raise _not_implemented(x_trace_id or "trace-not-provided", "archive_not_found", "Archive not found", {"archive_id": archive_id})
    return {
        "data": {
            "archive_id": row.archive_id,
            "project_id": row.project_id,
            "entity_uuid": row.entity_uuid,
            "entity_name": row.display_name,
            "entity_type": row.entity_kind,
            "summary": row.summary,
            "archive_type": row.archive_type,
            "agent_kind": row.agent_kind,
            "importance_tier": row.importance_tier,
            "selected_importance_tier": row.selected_importance_tier,
            "template_key": row.template_key,
            "template_version": row.template_version,
        },
        "meta": {"trace_id": x_trace_id or "trace-not-provided", "version": "v2"},
    }


@router.get("/archives/{archive_id}/memories", responses={501: {"model": ErrorResponse}})
def list_archive_memories(archive_id: str, request: Request, x_trace_id: str | None = Header(default=None)) -> dict:
    engine = resolve_database_engine(request.app)
    stmt = select(metadata.tables["memories"]).where(metadata.tables["memories"].c.archive_id == archive_id)
    with engine.connect() as connection:
        rows = connection.execute(stmt).all()
    items = [
        {
            "memory_id": row.memory_id,
            "archive_id": row.archive_id,
            "memory_type": row.memory_type,
            "memory_layer": row.memory_layer,
            "status": row.status,
            "normalized_subject": row.normalized_subject,
            "summary": row.summary,
        }
        for row in rows
    ]
    return {"data": {"count": len(items), "items": items}, "meta": {"trace_id": x_trace_id or "trace-not-provided", "version": "v2"}}


@router.get("/archives/{archive_id}/memory-events", responses={501: {"model": ErrorResponse}})
def list_archive_memory_events(archive_id: str, request: Request, x_trace_id: str | None = Header(default=None)) -> dict:
    engine = resolve_database_engine(request.app)
    stmt = select(metadata.tables["memory_events"]).where(metadata.tables["memory_events"].c.archive_id == archive_id)
    with engine.connect() as connection:
        rows = connection.execute(stmt).all()
    items = [
        {
            "memory_event_id": row.memory_event_id,
            "memory_id": row.memory_id,
            "archive_id": row.archive_id,
            "event_type": row.event_type,
            "actor_type": row.actor_type,
            "actor_ref": row.actor_ref,
            "created_at": row.created_at.isoformat() if hasattr(row.created_at, "isoformat") else row.created_at,
        }
        for row in rows
    ]
    return {"data": {"count": len(items), "items": items}, "meta": {"trace_id": x_trace_id or "trace-not-provided", "version": "v2"}}


@router.post("/archives/{archive_id}/memory-adoptions", responses={501: {"model": ErrorResponse}})
def adopt_archive_memory_route(
    archive_id: str,
    payload: MemoryReviewCommand,
    request: Request,
    x_trace_id: str | None = Header(default=None),
) -> dict:
    engine = resolve_database_engine(request.app)
    try:
        data = adopt_archive_memory(engine, archive_id, payload.memory_id, x_trace_id or "trace-not-provided")
    except ValueError as exc:
        message = str(exc)
        if "不存在" in message:
            raise _error(x_trace_id or "trace-not-provided", 404, "archive_memory_not_found", message, {"archive_id": archive_id, "memory_id": payload.memory_id})
        raise _error(x_trace_id or "trace-not-provided", 400, "archive_memory_adoption_invalid", message, {"archive_id": archive_id, "memory_id": payload.memory_id})
    return {"data": data, "meta": {"trace_id": x_trace_id or "trace-not-provided", "version": "v2"}}


@router.post("/archives/{archive_id}/memory-rejections", responses={501: {"model": ErrorResponse}})
def reject_archive_memory_route(
    archive_id: str,
    payload: MemoryReviewCommand,
    request: Request,
    x_trace_id: str | None = Header(default=None),
) -> dict:
    engine = resolve_database_engine(request.app)
    try:
        data = reject_archive_memory(engine, archive_id, payload.memory_id, x_trace_id or "trace-not-provided")
    except ValueError as exc:
        message = str(exc)
        if "不存在" in message:
            raise _error(x_trace_id or "trace-not-provided", 404, "archive_memory_not_found", message, {"archive_id": archive_id, "memory_id": payload.memory_id})
        raise _error(x_trace_id or "trace-not-provided", 400, "archive_memory_rejection_invalid", message, {"archive_id": archive_id, "memory_id": payload.memory_id})
    return {"data": data, "meta": {"trace_id": x_trace_id or "trace-not-provided", "version": "v2"}}


@router.post("/archive-maintenance/reindex", responses={501: {"model": ErrorResponse}})
def reindex_archive_library(x_trace_id: str | None = Header(default=None)) -> dict:
    raise _not_implemented(x_trace_id or "trace-not-provided", "archive_reindex_not_implemented", "Archive reindex contract is frozen, implementation lands next", {})
