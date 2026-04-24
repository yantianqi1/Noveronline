"""FastAPI application entrypoint for the backend rewrite."""

from __future__ import annotations

import asyncio
import logging
from contextlib import asynccontextmanager
from collections.abc import AsyncIterator

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware

from .config import Config, Settings
from .database import create_engine_from_settings, init_db
from .middleware import ApiKeyAuthMiddleware, register_exception_handlers

SERVICE_NAME = "MiroFish-Novel Backend"
logger = logging.getLogger(__name__)


def create_app(settings: Settings | None = None) -> FastAPI:
    app_settings = settings or Settings()
    engine = create_engine_from_settings(app_settings)
    app = FastAPI(title=SERVICE_NAME, lifespan=_lifespan(engine, app_settings))
    app.state.settings = app_settings
    app.state.engine = engine
    _register_middleware(app, app_settings)
    register_exception_handlers(app, app_settings)
    _register_core_routes(app)
    _register_api_routes(app)
    return app


def _lifespan(engine, settings: Settings):
    @asynccontextmanager
    async def lifespan(app: FastAPI) -> AsyncIterator[None]:
        # Production/dev runtime goes through alembic so the schema lifecycle
        # stays owned by migration revisions. Tests bypass this via the
        # ``_unified_db_bootstrap`` conftest fixture, which calls
        # ``init_db(..., use_alembic=False)`` for a fast per-test create_all.
        init_db(engine, use_alembic=True)
        stale_ids = _recover_stale_tasks(engine)
        backfill_task = None
        if settings.GLOBAL_DATA_BACKFILL_ON_STARTUP:
            backfill_task = asyncio.create_task(
                _run_global_data_backfill(settings.GLOBAL_DATA_BACKFILL_USE_LLM)
            )
        resume_task = None
        if settings.SEED_AUTO_RESUME_ON_STARTUP and stale_ids:
            resume_task = asyncio.create_task(_auto_resume_seed_tasks(stale_ids))
        try:
            yield
        finally:
            if backfill_task is not None and not backfill_task.done():
                backfill_task.cancel()
            if resume_task is not None and not resume_task.done():
                resume_task.cancel()
            engine.dispose()

    return lifespan


def _recover_stale_tasks(engine) -> list[str]:
    """Fail any task left in pending/processing state by a previous run.

    Without this, the frontend's rejoin path would happily poll a zombie
    task (DB row still says processing but no Python thread is driving it)
    and never surface an error. Marking stale tasks as failed on startup
    lets the UI show "任务已中断" and route the user into the 重新开始 path.

    Also resets any project whose ``seed_task_id``/``graph_build_task_id``
    pointed at a now-failed task back to a terminal status (FAILED) so the
    project list accurately reflects reality.

    Returns the list of task_ids that were marked failed, so the caller
    (lifespan) can optionally kick off auto-resume for resumable projects.
    """
    from .repositories.task_repo import TaskRepository
    from .models.project import ProjectManager, ProjectStatus

    try:
        repo = TaskRepository(engine)
        stale_ids = repo.mark_stale_tasks_failed(
            "后端进程已重启或异常终止，任务未能完成。请点击 重新开始 或 断点续传。"
        )
        if not stale_ids:
            logger.info("Startup task recovery: no stale tasks to clean up.")
            return []
        logger.warning(
            "Startup task recovery: marked %d stale task(s) as failed: %s",
            len(stale_ids), stale_ids,
        )
        # Reconcile project status for any project that referenced a stale task.
        stale_set = set(stale_ids)
        for project in ProjectManager.list_projects(limit=500):
            changed = False
            if project.seed_task_id and project.seed_task_id in stale_set:
                if project.status == ProjectStatus.SEED_PROCESSING:
                    project.status = ProjectStatus.FAILED
                    project.error = (
                        project.error
                        or "种子分析任务未完成（后端已重启）。请重新开始或断点续传。"
                    )
                    changed = True
            if project.graph_build_task_id and project.graph_build_task_id in stale_set:
                if project.status == ProjectStatus.GRAPH_BUILDING:
                    project.status = ProjectStatus.FAILED
                    project.error = (
                        project.error
                        or "图谱构建任务未完成（后端已重启）。请重新构建。"
                    )
                    changed = True
            if changed:
                ProjectManager.save_project(project)
                logger.info("Reset project %s to failed after task recovery", project.project_id)
        return stale_ids
    except Exception:  # noqa: BLE001
        logger.exception("Startup task recovery failed — continuing boot anyway")
        return []


async def _auto_resume_seed_tasks(stale_ids: list[str]) -> None:
    """Kick off ``create_retry_task`` for projects whose seed task was just marked stale.

    Only resumable projects (``smart_segments.json`` already written) are picked
    up — stage 1 cannot be resumed, so if segmentation never finished we leave
    the project in FAILED for the user to "重新开始".
    """
    from .models.project import ProjectManager, ProjectStatus
    from .models.task import TaskManager
    from .services.seed_extract_task_service import SeedExtractTaskService

    if not stale_ids:
        return
    try:
        TaskManager()._ensure_loop()
        stale_set = set(stale_ids)
        service = SeedExtractTaskService()
        resumed = 0
        for project in ProjectManager.list_projects(limit=500):
            if project.status != ProjectStatus.FAILED:
                continue
            # _recover_stale_tasks 保留了旧 seed_task_id（只翻 status）；只有当
            # 这个 id 仍然指向刚被标记 stale 的那个僵尸，或者已经被清空时，才
            # 允许我们接管。若指向一个 stale_set 之外的新 task，说明另一路
            # 已经触发了 retry，不要再抢。
            if project.seed_task_id and project.seed_task_id not in stale_set:
                continue
            segments = ProjectManager.load_project_json(
                project.project_id, "smart_segments.json",
            )
            if not segments or not segments.get("segments"):
                continue
            try:
                new_task_id = await service.create_retry_task(project.project_id)
            except Exception:  # noqa: BLE001
                logger.exception(
                    "Auto-resume failed to enqueue retry for project %s",
                    project.project_id,
                )
                continue
            resumed += 1
            logger.info(
                "Auto-resumed seed task for project %s → task %s",
                project.project_id, new_task_id,
            )
        if resumed == 0:
            logger.info("Auto-resume: no resumable seed projects found.")
    except asyncio.CancelledError:
        raise
    except Exception:  # noqa: BLE001
        logger.exception("Auto-resume sweep failed")


async def _run_global_data_backfill(use_llm: bool) -> None:
    """后台扫描需要回填的项目，不阻塞启动。"""
    try:
        from .models.task import TaskManager
        from .services.global_data_linker import GlobalDataLinker

        TaskManager()._ensure_loop()
        results = await asyncio.to_thread(
            GlobalDataLinker().backfill_missing, use_llm=use_llm,
        )
        if results:
            logger.info("Global data backfill ran for %d project(s): %s", len(results), results)
        else:
            logger.info("Global data backfill: no projects need backfill.")
    except asyncio.CancelledError:
        raise
    except Exception:  # noqa: BLE001
        logger.exception("Global data backfill failed")


def _register_middleware(app: FastAPI, settings: Settings) -> None:
    app.add_middleware(
        CORSMiddleware,
        allow_origins=[],
        allow_origin_regex=".*",
        allow_credentials=False,
        allow_methods=["*"],
        allow_headers=["*"],
        allow_private_network=True,
    )
    app.middleware("http")(_private_network_cors)
    app.add_middleware(ApiKeyAuthMiddleware, settings=settings)


async def _private_network_cors(request: Request, call_next):
    response = await call_next(request)
    origin = request.headers.get("origin")
    if origin:
        response.headers["Access-Control-Allow-Origin"] = origin
    if request.headers.get("access-control-request-private-network"):
        response.headers["Access-Control-Allow-Private-Network"] = "true"
    return response


def _register_core_routes(app: FastAPI) -> None:
    @app.get("/health")
    async def health() -> dict:
        return {"status": "ok", "service": SERVICE_NAME}


def _register_api_routes(app: FastAPI) -> None:
    from .api_fastapi import api_router

    app.include_router(api_router)


app = create_app()
