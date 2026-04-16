"""Native FastAPI routers."""

from fastapi import APIRouter

from .archive import router as archive_router
from .assets import router as assets_router
from .llm import router as llm_router
from .novel import router as novel_router
from .project import router as project_router
from .unified_assets import router as unified_assets_router
from .worldline import router as worldline_router
from .writer_agent import router as writer_agent_router

api_router = APIRouter(prefix="/api")
api_router.include_router(project_router)
api_router.include_router(novel_router)
api_router.include_router(llm_router)
api_router.include_router(archive_router)
api_router.include_router(assets_router)
api_router.include_router(unified_assets_router)
api_router.include_router(worldline_router)
api_router.include_router(writer_agent_router)

__all__ = ["api_router"]
