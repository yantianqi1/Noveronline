from __future__ import annotations

from fastapi import APIRouter, Header, HTTPException, Request
from pydantic import BaseModel

from src.bootstrap.database import resolve_database_engine
from src.modules.worldline.event_command_service import adopt_worldline_events, edit_worldline_event
from src.shared.schemas import ErrorResponse


router = APIRouter(prefix="/worldlines", tags=["worldline"])


class EventAdoptionCommand(BaseModel):
    event_ids: list[str]
    action: str


class EventEditCommand(BaseModel):
    summary: str
    title: str | None = None


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


@router.post("/sessions/{session_id}/event-adoptions", responses={501: {"model": ErrorResponse}})
def adopt_events(
    session_id: str,
    payload: EventAdoptionCommand,
    request: Request,
    x_trace_id: str | None = Header(default=None),
) -> dict:
    engine = resolve_database_engine(request.app)
    try:
        data = adopt_worldline_events(engine, session_id, payload.event_ids, payload.action)
    except ValueError as exc:
        message = str(exc)
        status_code = 404 if "not found" in message.lower() else 400
        raise _error(
            x_trace_id or "trace-not-provided",
            status_code,
            "worldline_event_adoption_invalid",
            message,
            {"session_id": session_id, "event_ids": payload.event_ids, "action": payload.action},
        )
    return {"data": data, "meta": {"trace_id": x_trace_id or "trace-not-provided", "version": "v2"}}


@router.patch("/sessions/{session_id}/events/{event_id}", responses={501: {"model": ErrorResponse}})
def edit_event(
    session_id: str,
    event_id: str,
    payload: EventEditCommand,
    request: Request,
    x_trace_id: str | None = Header(default=None),
) -> dict:
    engine = resolve_database_engine(request.app)
    try:
        data = edit_worldline_event(engine, session_id, event_id, payload.summary, payload.title)
    except ValueError as exc:
        message = str(exc)
        status_code = 404 if "not found" in message.lower() else 400
        raise _error(
            x_trace_id or "trace-not-provided",
            status_code,
            "worldline_event_edit_invalid",
            message,
            {"session_id": session_id, "event_id": event_id},
        )
    return {"data": data, "meta": {"trace_id": x_trace_id or "trace-not-provided", "version": "v2"}}
