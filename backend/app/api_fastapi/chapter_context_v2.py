"""Resource-oriented chapter context API v2 routes."""

from __future__ import annotations

from fastapi import APIRouter

from app.schemas.novel_schemas import ChapterContextRequest
from app.services.chapter_context_pack_builder import ChapterContextPackBuilder

from .common import err, ok

router = APIRouter(prefix="/chapter-context", tags=["chapter-context-v2"])

_chapter_context_pack_builder = None


def _get_chapter_context_pack_builder():
    global _chapter_context_pack_builder
    if _chapter_context_pack_builder is None:
        _chapter_context_pack_builder = ChapterContextPackBuilder()
    return _chapter_context_pack_builder


@router.get("/options")
async def chapter_context_options_v2(project_id: str = ""):
    try:
        if not project_id.strip():
            return err("请提供 project_id", status_code=400)
        return ok(_get_chapter_context_pack_builder().build_options(project_id))
    except ValueError as exc:
        return err(exc, status_code=400)
    except Exception as exc:
        return err(exc)


@router.post("/builds")
async def build_chapter_context_v2(body: ChapterContextRequest):
    try:
        payload = body.model_dump()
        return ok(_get_chapter_context_pack_builder().build(payload))
    except ValueError as exc:
        return err(exc, status_code=400)
    except Exception as exc:
        return err(exc)
