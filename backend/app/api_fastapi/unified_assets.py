"""Native FastAPI unified asset routes."""

from __future__ import annotations

from fastapi import APIRouter

from app.services.assets.global_search_indexer import GlobalSearchIndexer
from app.services.assets.unified_asset_view import ALL_SOURCES, UnifiedAssetView

from app.schemas.unified_assets_schemas import ReindexRequest

from .common import err, ok

router = APIRouter(prefix="/unified-assets", tags=["unified-assets"])


def _split_csv(value: str | None) -> list[str]:
    return [item.strip() for item in str(value or "").split(",") if item.strip()]


@router.get("")
async def list_unified(project_id: str | None = None, source: str | None = None, entity_type: str | None = None, scope: str | None = None, q: str | None = None, page: int = 1, page_size: int = 50):
    try:
        return ok(UnifiedAssetView().list(project_id=project_id, sources=_split_csv(source) or None, entity_types=_split_csv(entity_type) or None, scope=scope, q=q, page=page, page_size=page_size))
    except Exception as exc:
        return err(exc)


@router.get("/facets")
async def facets_unified(project_id: str | None = None):
    try:
        return ok(UnifiedAssetView().facets(project_id=project_id))
    except Exception as exc:
        return err(exc)


@router.get("/search")
async def search_unified(q: str = "", project_id: str | None = None, source: str | None = None, entity_type: str | None = None, limit: int = 50, offset: int = 0):
    try:
        if not q.strip():
            return err("q 不能为空", status_code=400)
        indexer = GlobalSearchIndexer()
        if project_id:
            with indexer._connect() as conn:
                row = conn.execute("SELECT COUNT(*) AS n FROM global_index WHERE project_id = ?", (project_id,)).fetchone()
            if row and row["n"] == 0:
                indexer.reindex_project(project_id)
        return ok(indexer.search(q, project_id=project_id, sources=_split_csv(source) or None, entity_types=_split_csv(entity_type) or None, limit=limit, offset=offset))
    except Exception as exc:
        return err(exc)


@router.post("/reindex")
async def reindex_unified(body: ReindexRequest):
    try:
        project_id = body.project_id
        if not project_id:
            return err("project_id 必填", status_code=400)
        return ok({"indexed": GlobalSearchIndexer().reindex_project(project_id)})
    except Exception as exc:
        return err(exc)


@router.get("/sources")
async def list_sources():
    return ok(list(ALL_SOURCES))


@router.get("/{source}/{ref:path}")
async def get_unified(source: str, ref: str, project_id: str | None = None):
    try:
        item = UnifiedAssetView().get(source, ref, project_id=project_id)
        return ok(item) if item else err("未找到资产", status_code=404)
    except Exception as exc:
        return err(exc)
