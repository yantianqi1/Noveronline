"""Native FastAPI asset routes."""

from __future__ import annotations

from fastapi import APIRouter

from app.models.task import TaskManager
from app.services.assets.assets_service import AssetsService, GLOBAL_SCOPE, PROJECT_SCOPE
from app.services.assets.ingestion_agent import IngestionAgent
from app.services.assets.style_extractor import StyleExtractor

from app.schemas.assets_schemas import (
    AssetSearchRequest,
    BatchCategorizeRequest,
    BatchToggleRequest,
    CreateAssetRequest,
    IngestRequest,
    StyleExtractRequest,
    UpdateAssetRequest,
)

from .common import err, ok

router = APIRouter(prefix="/assets", tags=["assets"])


def _scope(scope: str) -> str:
    if scope not in (GLOBAL_SCOPE, PROJECT_SCOPE):
        raise ValueError(f"scope 必须是 global 或 project，收到 {scope!r}")
    return scope


@router.get("")
async def list_assets(scope: str = "all", project_id: str | None = None, asset_type: str | None = None, category: str | None = None, enabled_only: bool = False, limit: int = 200, offset: int = 0):
    try:
        service = AssetsService()
        data = service.list_merged(project_id=project_id, asset_type=asset_type, category=category, enabled_only=enabled_only, limit=limit) if scope == "all" else service.list(scope=_scope(scope), project_id=project_id, asset_type=asset_type, category=category, enabled_only=enabled_only, limit=limit, offset=offset)
        return ok(data)
    except Exception as exc:
        return err(exc)


@router.post("/search")
async def search_assets(body: AssetSearchRequest):
    try:
        payload = body.model_dump()
        query = payload.get("query", "")
        if not query.strip():
            return err("query 不能为空", status_code=400)
        service = AssetsService()
        scope = payload.get("scope", "all")
        data = service.search_merged(query, project_id=payload.get("project_id"), asset_type=payload.get("asset_type"), category=payload.get("category"), enabled_only=bool(payload.get("enabled_only", True)), limit=int(payload.get("limit", 20))) if scope == "all" else service.search(query, scope=_scope(scope), project_id=payload.get("project_id"), asset_type=payload.get("asset_type"), category=payload.get("category"), enabled_only=bool(payload.get("enabled_only", True)), limit=int(payload.get("limit", 20)))
        return ok(data)
    except Exception as exc:
        return err(exc)


@router.get("/{asset_id}")
async def get_asset(asset_id: str, project_id: str | None = None):
    try:
        asset = AssetsService().find(asset_id, project_id=project_id)
        return ok(asset) if asset else err("未找到资产", status_code=404)
    except Exception as exc:
        return err(exc)


@router.post("")
async def create_asset(body: CreateAssetRequest):
    try:
        payload = body.model_dump()
        return ok(AssetsService().create(scope=_scope(payload.get("scope", GLOBAL_SCOPE)), asset_type=payload["asset_type"], title=payload["title"], project_id=payload.get("project_id"), category=payload.get("category", ""), summary=payload.get("summary", ""), content=payload.get("content", ""), payload=payload.get("payload"), tags=payload.get("tags"), source_kind=payload.get("source_kind", "manual"), source_ref=payload.get("source_ref", ""), enabled=bool(payload.get("enabled", True)), pinned=bool(payload.get("pinned", False))))
    except Exception as exc:
        return err(exc)


@router.put("/{asset_id}")
async def update_asset(asset_id: str, body: UpdateAssetRequest):
    try:
        payload = body.model_dump(exclude_unset=True)
        body_dict = dict(payload)
        scope = _scope(body_dict.pop("scope", GLOBAL_SCOPE))
        project_id = body_dict.pop("project_id", None)
        return ok(AssetsService().update(asset_id, scope=scope, project_id=project_id, **body_dict))
    except Exception as exc:
        return err(exc)


@router.delete("/{asset_id}")
async def delete_asset(asset_id: str, scope: str = GLOBAL_SCOPE, project_id: str | None = None):
    try:
        return ok({"deleted": AssetsService().delete(asset_id, scope=_scope(scope), project_id=project_id)})
    except Exception as exc:
        return err(exc)


@router.post("/batch-toggle")
async def batch_toggle(body: BatchToggleRequest):
    try:
        payload = body.model_dump()
        n = AssetsService().batch_set_enabled(payload.get("asset_ids") or [], bool(payload.get("enabled", True)), scope=_scope(payload.get("scope", GLOBAL_SCOPE)), project_id=payload.get("project_id"))
        return ok({"updated": n})
    except Exception as exc:
        return err(exc)


@router.post("/batch-categorize")
async def batch_categorize(body: BatchCategorizeRequest):
    try:
        payload = body.model_dump()
        n = AssetsService().batch_set_category(payload.get("asset_ids") or [], payload.get("category", ""), scope=_scope(payload.get("scope", GLOBAL_SCOPE)), project_id=payload.get("project_id"))
        return ok({"updated": n})
    except Exception as exc:
        return err(exc)


@router.post("/ingest")
async def ingest_asset(body: IngestRequest):
    try:
        payload = body.model_dump()
        raw_text = payload.get("raw_text") or payload.get("text") or ""
        if not raw_text.strip():
            return err("raw_text 必填", status_code=400)
        task_id = await IngestionAgent().run_background(raw_text, scope=_scope(payload.get("scope", GLOBAL_SCOPE)), project_id=payload.get("project_id"), hint_type=payload.get("hint_type"))
        return ok({"task_id": task_id})
    except Exception as exc:
        return err(exc)


@router.get("/ingest/{task_id}")
async def ingest_status(task_id: str):
    task = await TaskManager().get_task(task_id)
    return ok(task.to_dict()) if task else err("任务不存在", status_code=404)


@router.post("/style-extract")
async def style_extract(body: StyleExtractRequest):
    try:
        payload = body.model_dump()
        text = payload.get("text") or ""
        title = (payload.get("title") or "").strip()
        if not text.strip() or not title:
            return err("text 与 title 必填", status_code=400)
        task_id = await StyleExtractor().extract_background(text, title=title, category=payload.get("category", ""), tags=payload.get("tags") or [], target_chunk_chars=int(payload.get("target_chunk_chars") or 3000), max_chunks=int(payload.get("max_chunks") or 30))
        return ok({"task_id": task_id})
    except Exception as exc:
        return err(exc)


@router.get("/style-extract/{task_id}")
async def style_extract_status(task_id: str):
    task = await TaskManager().get_task(task_id)
    return ok(task.to_dict()) if task else err("任务不存在", status_code=404)
