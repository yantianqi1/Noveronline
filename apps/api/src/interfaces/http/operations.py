import json

from fastapi import APIRouter, Header, HTTPException, Request
from fastapi.responses import StreamingResponse

from src.bootstrap.database import resolve_database_engine
from src.modules.operations.query_service import fetch_operation, fetch_operation_events, fetch_operation_step
from src.shared.schemas import ErrorResponse, OperationResource

router = APIRouter(prefix="/operations", tags=["operations"])


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


@router.get(
    "/{operation_id}",
    response_model=OperationResource,
    responses={501: {"model": ErrorResponse}},
)
def get_operation(operation_id: str, request: Request, x_trace_id: str | None = Header(default=None)) -> OperationResource:
    engine = resolve_database_engine(request.app)
    operation = fetch_operation(engine, operation_id, x_trace_id or "trace-not-provided")
    if operation is None:
        raise _not_found(x_trace_id or "trace-not-provided", "operation_not_found", "Operation not found", {"operation_id": operation_id})
    return OperationResource.model_validate(operation)


@router.get(
    "/{operation_id}/steps/{step_id}",
    response_model=OperationResource,
    responses={501: {"model": ErrorResponse}},
)
def get_operation_step(
    operation_id: str,
    step_id: str,
    request: Request,
    x_trace_id: str | None = Header(default=None),
) -> OperationResource:
    engine = resolve_database_engine(request.app)
    operation, operation_exists = fetch_operation_step(engine, operation_id, step_id, x_trace_id or "trace-not-provided")
    if not operation_exists:
        raise _not_found(x_trace_id or "trace-not-provided", "operation_not_found", "Operation not found", {"operation_id": operation_id})
    if operation is None:
        raise _not_found(
            x_trace_id or "trace-not-provided",
            "operation_step_not_found",
            "Operation step not found",
            {"operation_id": operation_id, "step_id": step_id},
        )
    return OperationResource.model_validate(operation)


@router.get(
    "/{operation_id}/events",
    responses={501: {"model": ErrorResponse}},
)
def list_operation_events(operation_id: str, request: Request, x_trace_id: str | None = Header(default=None)) -> list[dict]:
    engine = resolve_database_engine(request.app)
    events = fetch_operation_events(engine, operation_id)
    if events is None:
        raise _not_found(x_trace_id or "trace-not-provided", "operation_not_found", "Operation not found", {"operation_id": operation_id})
    return events


@router.get(
    "/{operation_id}/stream",
    responses={501: {"model": ErrorResponse}},
)
def stream_operation_events(
    operation_id: str,
    request: Request,
    x_trace_id: str | None = Header(default=None),
    last_event_id: str | None = Header(default=None, alias="Last-Event-ID"),
) -> StreamingResponse:
    engine = resolve_database_engine(request.app)
    events = fetch_operation_events(engine, operation_id)
    if events is None:
        raise _not_found(x_trace_id or "trace-not-provided", "operation_not_found", "Operation not found", {"operation_id": operation_id})

    def _generate():
        should_emit = last_event_id is None
        for item in events:
            if not should_emit:
                should_emit = item["event_id"] == last_event_id
                continue
            payload = json.dumps(item, ensure_ascii=False)
            yield f"id: {item['event_id']}\nevent: {item['type']}\ndata: {payload}\n\n"

    return StreamingResponse(_generate(), media_type="text/event-stream")
