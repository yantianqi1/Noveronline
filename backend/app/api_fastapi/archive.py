"""Native FastAPI archive routes.

Deprecation note (2026-04-19, asset-library refactor P3):
  The ``/api/archive/library/*`` URL space is slated for removal in P5
  once ``archive_library`` merges into the ``assets`` table. Frontend
  consumers now import from ``@/api/assets`` (archive.ts was deleted).
  New code should not add routes here — use ``api_fastapi/assets.py``
  or ``api_fastapi/unified_assets.py`` and accept a ``source=archive``
  filter when needed.

  The ``/library/reindex`` endpoint stays because tests
  (``test_archive_library_api.py``) still use it to backfill legacy
  ``narrative_archives.json`` artifacts into the DB. It will retire
  together with the legacy JSON path in Phase G.
"""

from __future__ import annotations

from fastapi import APIRouter

from app.services.archive_library_service import ArchiveLibraryService
from app.services.archive_memory_review_service import ArchiveMemoryReviewService

from .common import err, ok, status_for_value_error

router = APIRouter(prefix="/archive", tags=["archive"])
MEMORY_LAYERS = {"canon", "candidate", "experiment"}
MEMORY_STATUSES = {"active", "superseded", "rejected"}


def _csv(raw: str, allowed: set[str], field: str) -> tuple[str, ...]:
    values = tuple(item.strip() for item in str(raw or "").split(",") if item.strip())
    invalid = [item for item in values if item not in allowed]
    if invalid:
        raise ValueError(f"{field} 不支持: {', '.join(invalid)}")
    return values


@router.get("/library")
async def list_archive_library(q: str = "", project_id: str = "", entity_type: str = "", agent_kind: str = "", importance_tier: str = "", template_key: str = "", limit: int = 20, offset: int = 0):
    try:
        return ok(ArchiveLibraryService().list_archives(q, project_id, entity_type, agent_kind, importance_tier, template_key, limit, offset))
    except Exception as exc:
        return err(exc)


@router.get("/library/{archive_id}")
async def get_archive_library_item(archive_id: str):
    try:
        return ok(ArchiveLibraryService().get_archive(archive_id))
    except ValueError as exc:
        return err(exc, status_code=404)
    except Exception as exc:
        return err(exc)


@router.post("/library/reindex")
async def reindex_archive_library():
    try:
        return ok({"count": ArchiveLibraryService().reindex()})
    except Exception as exc:
        return err(exc)


@router.get("/library/{archive_id}/memory")
async def list_archive_memory(archive_id: str, layer: str = "", status: str = "active", include_candidates: bool = True):
    try:
        ArchiveLibraryService().get_archive(archive_id)
        layers = _csv(layer, MEMORY_LAYERS, "layer")
        statuses = _csv(status, MEMORY_STATUSES, "status") or ("active",)
        return ok(ArchiveMemoryReviewService().list_memory(archive_id, include_candidates, layers or None, statuses))
    except ValueError as exc:
        return err(exc, status_code=status_for_value_error(exc))
    except Exception as exc:
        return err(exc)


@router.get("/library/{archive_id}/memory/timeline")
async def archive_memory_timeline(archive_id: str, memory_id: str = "", normalized_subject: str = ""):
    try:
        ArchiveLibraryService().get_archive(archive_id)
        return ok(ArchiveMemoryReviewService().timeline(archive_id, memory_id, normalized_subject))
    except ValueError as exc:
        return err(exc, status_code=status_for_value_error(exc))
    except Exception as exc:
        return err(exc)


@router.post("/library/{archive_id}/memory/{memory_id}/adopt")
async def adopt_archive_memory(archive_id: str, memory_id: str):
    try:
        ArchiveLibraryService().get_archive(archive_id)
        return ok(ArchiveMemoryReviewService().adopt(archive_id, memory_id))
    except ValueError as exc:
        return err(exc, status_code=status_for_value_error(exc))
    except Exception as exc:
        return err(exc)


@router.post("/library/{archive_id}/memory/{memory_id}/reject")
async def reject_archive_memory(archive_id: str, memory_id: str):
    try:
        ArchiveLibraryService().get_archive(archive_id)
        return ok(ArchiveMemoryReviewService().reject(archive_id, memory_id))
    except ValueError as exc:
        return err(exc, status_code=status_for_value_error(exc))
    except Exception as exc:
        return err(exc)
