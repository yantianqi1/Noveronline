"""Resource-oriented archive API v2 routes."""

from __future__ import annotations

from fastapi import APIRouter
from pydantic import BaseModel

from app.services.archive_library_service import ArchiveLibraryService
from app.services.archive_memory_review_service import ArchiveMemoryReviewService

from .archive import MEMORY_LAYERS, MEMORY_STATUSES, _csv
from .common import err, ok, status_for_value_error

router = APIRouter(tags=["archive-v2"])


class MemoryCommandRequest(BaseModel):
    memory_id: str


@router.get("/archives")
async def list_archives_v2(
    q: str = "",
    project_id: str = "",
    entity_type: str = "",
    agent_kind: str = "",
    importance_tier: str = "",
    template_key: str = "",
    limit: int = 20,
    offset: int = 0,
):
    try:
        return ok(
            ArchiveLibraryService().list_archives(
                q,
                project_id,
                entity_type,
                agent_kind,
                importance_tier,
                template_key,
                limit,
                offset,
            )
        )
    except Exception as exc:
        return err(exc)


@router.get("/archives/{archive_id}")
async def get_archive_v2(archive_id: str):
    try:
        return ok(ArchiveLibraryService().get_archive(archive_id))
    except ValueError as exc:
        return err(exc, status_code=404)
    except Exception as exc:
        return err(exc)


@router.post("/archive-maintenance/reindex")
async def reindex_archives_v2():
    try:
        return ok({"count": ArchiveLibraryService().reindex()})
    except Exception as exc:
        return err(exc)


@router.get("/archives/{archive_id}/memories")
async def list_archive_memories_v2(
    archive_id: str,
    layer: str = "",
    status: str = "active",
    include_candidates: bool = True,
):
    try:
        ArchiveLibraryService().get_archive(archive_id)
        layers = _csv(layer, MEMORY_LAYERS, "layer")
        statuses = _csv(status, MEMORY_STATUSES, "status") or ("active",)
        return ok(
            ArchiveMemoryReviewService().list_memory(
                archive_id,
                include_candidates,
                layers or None,
                statuses,
            )
        )
    except ValueError as exc:
        return err(exc, status_code=status_for_value_error(exc))
    except Exception as exc:
        return err(exc)


@router.get("/archives/{archive_id}/memory-events")
async def archive_memory_events_v2(
    archive_id: str,
    memory_id: str = "",
    normalized_subject: str = "",
):
    try:
        ArchiveLibraryService().get_archive(archive_id)
        return ok(
            ArchiveMemoryReviewService().timeline(
                archive_id,
                memory_id,
                normalized_subject,
            )
        )
    except ValueError as exc:
        return err(exc, status_code=status_for_value_error(exc))
    except Exception as exc:
        return err(exc)


@router.post("/archives/{archive_id}/memory-adoptions")
async def adopt_archive_memory_v2(archive_id: str, body: MemoryCommandRequest):
    try:
        ArchiveLibraryService().get_archive(archive_id)
        return ok(ArchiveMemoryReviewService().adopt(archive_id, body.memory_id))
    except ValueError as exc:
        return err(exc, status_code=status_for_value_error(exc))
    except Exception as exc:
        return err(exc)


@router.post("/archives/{archive_id}/memory-rejections")
async def reject_archive_memory_v2(archive_id: str, body: MemoryCommandRequest):
    try:
        ArchiveLibraryService().get_archive(archive_id)
        return ok(ArchiveMemoryReviewService().reject(archive_id, body.memory_id))
    except ValueError as exc:
        return err(exc, status_code=status_for_value_error(exc))
    except Exception as exc:
        return err(exc)
