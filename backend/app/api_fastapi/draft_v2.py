"""Resource-oriented draft API v2 routes."""

from __future__ import annotations

import json
import uuid
from typing import Any

from fastapi import APIRouter, Body
from fastapi.responses import StreamingResponse
from pydantic import BaseModel

from app.services.assets.assets_service import AssetsService, PROJECT_SCOPE
from app.services.writer_agent.manuscript_service import ManuscriptService
from app.services.writer_agent.orchestrator import WriterOrchestrator

from .common import err, ok

router = APIRouter(prefix="/drafts", tags=["draft-v2"])


class FinalizeDraftRequest(BaseModel):
    project_id: str = ""
    content: str = ""
    source_scene_id: str | None = None
    insert_after_block_id: str | None = None
    chapter_id: str | None = None
    chapter_tag: str | None = None
    pov_entity_id: str | None = None
    location: str | None = None
    involved_entity_ids: list[str] | None = None
    involved_entities_json: str | None = None


def _new_draft_id() -> str:
    return f"draft_{uuid.uuid4().hex[:12]}"


def _new_revision_id() -> str:
    return f"rev_{uuid.uuid4().hex[:12]}"


def _require_project_id(payload: dict[str, Any]) -> str:
    project_id = str(payload.get("project_id") or "").strip()
    if not project_id:
        raise ValueError("缺少 project_id")
    return project_id


def _asset_title(payload: dict[str, Any], fallback: str) -> str:
    title = payload.get("title") or payload.get("scene_focus") or fallback
    return str(title).strip() or fallback


def _normalize_draft_payload(payload: dict[str, Any]) -> dict[str, Any]:
    normalized = dict(payload)
    normalized["task_type"] = normalized.get("task_type") or "write_scene"
    return normalized


def _normalize_revision_payload(payload: dict[str, Any]) -> dict[str, Any]:
    normalized = _normalize_draft_payload(payload)
    normalized["selected_text"] = (
        normalized.get("selected_text")
        or normalized.get("draft")
        or normalized.get("original_text")
        or ""
    )
    normalized["user_instruction"] = (
        normalized.get("user_instruction")
        or normalized.get("revision_instruction")
        or normalized.get("instruction")
        or ""
    )
    return normalized


def _persist_draft_request(payload: dict[str, Any]) -> dict[str, Any]:
    project_id = _require_project_id(payload)
    draft_id = _new_draft_id()
    asset = AssetsService().create(
        scope=PROJECT_SCOPE,
        project_id=project_id,
        asset_id=draft_id,
        asset_type="draft_session",
        title=_asset_title(payload, f"Draft {draft_id}"),
        summary=str(payload.get("scene_focus") or ""),
        payload={"request": dict(payload)},
        source_kind="draft_v2",
        source_ref=draft_id,
    )
    return {
        "draft_id": draft_id,
        "asset_id": asset["asset_id"],
        "events_url": f"/api/v2/drafts/{draft_id}/events",
    }


def _persist_revision_request(draft_id: str, payload: dict[str, Any]) -> dict[str, Any]:
    project_id = _require_project_id(payload)
    revision_id = _new_revision_id()
    asset = AssetsService().create(
        scope=PROJECT_SCOPE,
        project_id=project_id,
        asset_id=revision_id,
        asset_type="draft_revision",
        title=_asset_title(payload, f"Revision {revision_id}"),
        content=str(
            payload.get("selected_text")
            or payload.get("draft")
            or payload.get("original_text")
            or ""
        ),
        payload={"draft_id": draft_id, "request": dict(payload)},
        source_kind="draft_v2",
        source_ref=draft_id,
    )
    return {
        "draft_id": draft_id,
        "revision_id": revision_id,
        "asset_id": asset["asset_id"],
        "events_url": f"/api/v2/drafts/{draft_id}/revisions/{revision_id}/events",
    }


def _load_draft_request(draft_id: str) -> dict[str, Any]:
    asset = AssetsService().get(draft_id, scope=PROJECT_SCOPE)
    if not asset or asset.get("asset_type") != "draft_session":
        raise LookupError("未找到 draft request")
    request = (asset.get("payload") or {}).get("request")
    if not isinstance(request, dict):
        raise ValueError("draft request 格式无效")
    return dict(request)


def _load_revision_request(draft_id: str, revision_id: str) -> dict[str, Any]:
    asset = AssetsService().get(revision_id, scope=PROJECT_SCOPE)
    if not asset or asset.get("asset_type") != "draft_revision":
        raise LookupError("未找到 revision request")
    payload = asset.get("payload") or {}
    if payload.get("draft_id") != draft_id:
        raise ValueError("revision request 不属于当前 draft")
    request = payload.get("request")
    if not isinstance(request, dict):
        raise ValueError("revision request 格式无效")
    return dict(request)


def _resolve_draft_event_payload(
    draft_id: str,
    body: dict[str, Any] | None,
) -> dict[str, Any]:
    payload = dict(body or {})
    if not str(payload.get("project_id") or "").strip():
        payload = _load_draft_request(draft_id)
    _require_project_id(payload)
    return _normalize_draft_payload(payload)


def _resolve_revision_event_payload(
    draft_id: str,
    revision_id: str,
    body: dict[str, Any] | None,
) -> dict[str, Any]:
    payload = dict(body or {})
    if not str(payload.get("project_id") or "").strip():
        payload = _load_revision_request(draft_id, revision_id)
    _require_project_id(payload)
    return _normalize_revision_payload(payload)


def _involved_entities_json(payload: dict[str, Any]) -> str | None:
    raw = payload.get("involved_entities_json")
    if raw:
        return str(raw)
    involved = payload.get("involved_entity_ids")
    if involved is None:
        return None
    return json.dumps(involved, ensure_ascii=False)


def _sse(event_type: str, data: dict[str, Any]) -> str:
    return (
        f"event: {event_type}\n"
        f"data: {json.dumps({'type': event_type, **data}, ensure_ascii=False)}\n\n"
    )


def _draft_event(draft_id: str, event: dict[str, Any]) -> str:
    event_type = str(event.get("type") or "message")
    return _sse(event_type, {"draft_id": draft_id, **event})


def _revision_event(draft_id: str, revision_id: str, event: dict[str, Any]) -> str:
    event_type = str(event.get("type") or "message")
    return _sse(event_type, {"draft_id": draft_id, "revision_id": revision_id, **event})


@router.post("")
async def create_draft_v2(body: dict[str, Any] = Body(...)):
    try:
        return ok(_persist_draft_request(body), status_code=202)
    except ValueError as exc:
        return err(exc, status_code=400)
    except Exception as exc:
        return err(exc)


@router.post("/{draft_id}/events")
async def stream_draft_generation_events_v2(
    draft_id: str,
    body: dict[str, Any] | None = Body(default=None),
):
    try:
        payload = _resolve_draft_event_payload(draft_id, body)
    except LookupError as exc:
        return err(exc, status_code=404)
    except ValueError as exc:
        return err(exc, status_code=400)
    project_id = str(payload.get("project_id") or "").strip()

    async def events():
        terminated = False
        yield _sse(
            "draft_started",
            {
                "draft_id": draft_id,
                "project_id": project_id,
                "task_type": payload.get("task_type", "write_scene"),
            },
        )
        try:
            async for event in WriterOrchestrator().run(payload):
                if event.get("type") == "done":
                    terminated = True
                yield _draft_event(draft_id, event)
        except Exception as exc:
            yield _sse("error", {"draft_id": draft_id, "message": str(exc)})
        finally:
            if not terminated:
                yield _sse("done", {"draft_id": draft_id})

    return StreamingResponse(
        events(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",
            "Connection": "keep-alive",
        },
    )


@router.post("/{draft_id}/revisions")
async def create_draft_revision_v2(draft_id: str, body: dict[str, Any] = Body(...)):
    try:
        return ok(_persist_revision_request(draft_id, body), status_code=202)
    except ValueError as exc:
        return err(exc, status_code=400)
    except Exception as exc:
        return err(exc)


@router.post("/{draft_id}/revisions/{revision_id}/events")
async def stream_draft_revision_events_v2(
    draft_id: str,
    revision_id: str,
    body: dict[str, Any] | None = Body(default=None),
):
    try:
        payload = _resolve_revision_event_payload(draft_id, revision_id, body)
    except LookupError as exc:
        return err(exc, status_code=404)
    except ValueError as exc:
        return err(exc, status_code=400)
    project_id = str(payload.get("project_id") or "").strip()

    async def events():
        terminated = False
        yield _sse(
            "revision_started",
            {
                "draft_id": draft_id,
                "revision_id": revision_id,
                "project_id": project_id,
                "task_type": payload.get("task_type", "write_scene"),
            },
        )
        try:
            async for event in WriterOrchestrator().run(payload):
                if event.get("type") == "done":
                    terminated = True
                yield _revision_event(draft_id, revision_id, event)
        except Exception as exc:
            yield _sse(
                "error",
                {"draft_id": draft_id, "revision_id": revision_id, "message": str(exc)},
            )
        finally:
            if not terminated:
                yield _sse("done", {"draft_id": draft_id, "revision_id": revision_id})

    return StreamingResponse(
        events(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",
            "Connection": "keep-alive",
        },
    )


@router.post("/{draft_id}/finalizations")
async def finalize_draft_v2(draft_id: str, body: FinalizeDraftRequest):
    try:
        payload = body.model_dump()
        project_id = (payload.get("project_id") or "").strip()
        content = payload.get("content") or ""
        if not project_id:
            return err("缺少 project_id", status_code=400)
        if not content.strip():
            return err("内容不能为空", status_code=400)

        service = ManuscriptService()
        committed = await service.commit(
            project_id,
            content=content,
            source_scene_id=payload.get("source_scene_id"),
            insert_after_block_id=payload.get("insert_after_block_id"),
            chapter_id=payload.get("chapter_id"),
            chapter_tag=payload.get("chapter_tag"),
            pov_entity_id=payload.get("pov_entity_id"),
            location=payload.get("location"),
            involved_entities_json=_involved_entities_json(payload),
        )
        block = service.get_block(project_id, committed["block_id"]) or committed
        return ok({"draft_id": draft_id, "project_id": project_id, "finalization": block})
    except ValueError as exc:
        return err(exc, status_code=400)
    except Exception as exc:
        return err(exc)
