"""Native FastAPI routers."""

from fastapi import APIRouter

from .archive import router as archive_router
from .archive_v2 import router as archive_v2_router
from .assets import router as assets_router
from .chapter_context_v2 import router as chapter_context_v2_router
from .draft_v2 import router as draft_v2_router
from .llm import router as llm_router
from .novel import router as novel_router
from .project import router as project_router
from .unified_assets import router as unified_assets_router
from .worldline import router as worldline_router
from .worldline_v2 import router as worldline_v2_router
from .writer_agent import router as writer_agent_router
from .writer_runs_v1 import router as writer_runs_v1_router

api_router = APIRouter(prefix="/api")
api_router.include_router(project_router)
api_router.include_router(novel_router)
api_router.include_router(llm_router)
api_router.include_router(archive_router)
api_router.include_router(assets_router)
api_router.include_router(unified_assets_router)
api_router.include_router(worldline_router)
api_router.include_router(writer_agent_router)

api_v2_router = APIRouter(prefix="/api/v2")
api_v2_router.include_router(llm_router)
api_v2_router.include_router(archive_v2_router)
api_v2_router.include_router(chapter_context_v2_router)
api_v2_router.include_router(draft_v2_router)
api_v2_router.include_router(worldline_v2_router)

api_v1_router = APIRouter(prefix="/api/v1")
api_v1_router.include_router(writer_runs_v1_router)

public_v1_router = APIRouter(prefix="/v1")
public_v1_router.include_router(writer_runs_v1_router)

__all__ = ["api_router", "api_v2_router", "api_v1_router", "public_v1_router"]
