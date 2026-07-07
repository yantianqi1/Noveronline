"""SaaS-style writer run compatibility API."""

from __future__ import annotations

import asyncio
import json
import uuid
from typing import Any

from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse, StreamingResponse

from app.database import get_engine
from app.repositories.writer_run_repo import LOCAL_TENANT_ID, LOCAL_USER_ID, WriterRunRepository
from app.services.pi_writer_runtime import PiWriterRuntime
from app.services.pi_writer_runtime.errors import LlmModuleUnboundError, WriterRunError

router = APIRouter(tags=["writer-runs-v1"])


def _error_response(
    *,
    code: str,
    message: str,
    status_code: int,
    details: dict[str, Any] | None = None,
) -> JSONResponse:
    return JSONResponse(
        {
            "error": {
                "code": code,
                "message": message,
                "details": details or {},
                "request_id": f"req_{uuid.uuid4().hex}",
            }
        },
        status_code=status_code,
    )


def _ok(data: Any, *, status_code: int = 200) -> JSONResponse:
    return JSONResponse({"success": True, "data": data}, status_code=status_code)


@router.post("/projects/{project_id}/writer-runs")
async def create_writer_run(project_id: str, body: dict[str, Any]):
    repo = WriterRunRepository(get_engine())
    tenant_id = body.get("tenant_id") or LOCAL_TENANT_ID
    requested_by = body.get("requested_by") or LOCAL_USER_ID
    options = dict(body.get("options") or {})
    for key in (
        "selected_asset_ids",
        "worldline_path_ids",
        "character_names",
        "graph_node_names",
        "asset_query",
        "world_rule_query",
    ):
        if key in body and key not in options:
            options[key] = body[key]
    module_key = options.get("module_key") or "writer_composer"
    run = repo.create_run(
        tenant_id=tenant_id,
        project_id=project_id,
        started_by=requested_by,
        mode=body.get("mode") or "draft",
        instruction=body.get("instruction") or "",
        module_key=module_key,
        chapter_id=body.get("chapter_id"),
        scene_id=body.get("scene_id"),
        options=options,
    )
    runtime = PiWriterRuntime(repo=repo)
    try:
        runtime.check_binding(
            tenant_id=tenant_id,
            project_id=project_id,
            run_id=run["run_id"],
            module_key=module_key,
        )
    except LlmModuleUnboundError as exc:
        details = {**exc.details, "run_id": run["run_id"]}
        repo.mark_failed(
            tenant_id,
            run["run_id"],
            code=exc.code,
            message=str(exc),
            details=details,
        )
        repo.append_event(
            tenant_id=tenant_id,
            project_id=project_id,
            run_id=run["run_id"],
            event_type="writer.run.failed",
            payload={"code": exc.code, "message": str(exc), "module_key": module_key},
        )
        return _error_response(
            code=exc.code,
            message=str(exc),
            status_code=424,
            details=details,
        )
    asyncio.create_task(runtime.run(run))
    return _ok({**run, "status": "pending"}, status_code=202)


@router.get("/writer-runs/{run_id}")
async def get_writer_run(run_id: str, tenant_id: str = LOCAL_TENANT_ID):
    run = WriterRunRepository(get_engine()).get_run(tenant_id, run_id)
    if run is None:
        return _error_response(
            code="NOT_FOUND",
            message=f"writer run not found: {run_id}",
            status_code=404,
        )
    return _ok(run)


@router.get("/writer-runs/{run_id}/events")
async def get_writer_run_events(request: Request, run_id: str, tenant_id: str = LOCAL_TENANT_ID):
    repo = WriterRunRepository(get_engine())
    events = repo.list_events(tenant_id, run_id)
    if "text/event-stream" not in request.headers.get("accept", ""):
        return _ok(events)

    async def stream():
        sent = 0
        terminal_types = {
            "writer.run.completed",
            "writer.run.failed",
            "writer.run.cancelled",
        }
        while True:
            if await request.is_disconnected():
                return
            current_events = repo.list_events(tenant_id, run_id)
            for event in current_events[sent:]:
                sent += 1
                yield f"id: {event['event_id']}\n"
                yield "event: workflow.event\n"
                yield f"data: {json.dumps(event, ensure_ascii=False)}\n\n"
                if event["type"] in terminal_types:
                    return
            await asyncio.sleep(0.5)

    return StreamingResponse(stream(), media_type="text/event-stream")


@router.post("/writer-runs/{run_id}/cancel")
async def cancel_writer_run(run_id: str, body: dict[str, Any] | None = None):
    tenant_id = (body or {}).get("tenant_id") or LOCAL_TENANT_ID
    repo = WriterRunRepository(get_engine())
    run = repo.get_run(tenant_id, run_id)
    if run is None:
        return _error_response(code="NOT_FOUND", message=f"writer run not found: {run_id}", status_code=404)
    repo.mark_cancelled(tenant_id, run_id)
    repo.append_event(
        tenant_id=tenant_id,
        project_id=run["project_id"],
        run_id=run_id,
        event_type="writer.run.cancelled",
        payload={},
    )
    return _ok({"run_id": run_id, "status": "cancelled"})


@router.post("/drafts/{draft_id}/adoptions")
async def adopt_draft(draft_id: str, body: dict[str, Any] | None = None):
    tenant_id = (body or {}).get("tenant_id") or LOCAL_TENANT_ID
    adopted_by = (body or {}).get("adopted_by") or LOCAL_USER_ID
    repo = WriterRunRepository(get_engine())
    try:
        result = repo.adopt_draft_to_manuscript(
            tenant_id=tenant_id,
            draft_id=draft_id,
            adopted_by=adopted_by,
        )
    except ValueError as exc:
        return _error_response(code="NOT_FOUND", message=str(exc), status_code=404)
    except WriterRunError as exc:
        return _error_response(code=exc.code, message=str(exc), status_code=400, details=exc.details)
    return _ok(result, status_code=201)
