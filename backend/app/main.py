"""FastAPI application entrypoint for the backend rewrite."""

from __future__ import annotations

from contextlib import asynccontextmanager
from collections.abc import AsyncIterator

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware

from .config import Config, Settings
from .database import create_engine_from_settings, init_db
from .middleware import ApiKeyAuthMiddleware, register_exception_handlers

SERVICE_NAME = "MiroFish-Novel Backend"


def create_app(settings: Settings | None = None) -> FastAPI:
    app_settings = settings or Settings()
    engine = create_engine_from_settings(app_settings)
    app = FastAPI(title=SERVICE_NAME, lifespan=_lifespan(engine))
    app.state.settings = app_settings
    app.state.engine = engine
    _register_middleware(app, app_settings)
    register_exception_handlers(app, app_settings)
    _register_core_routes(app)
    _register_api_routes(app)
    return app


def _lifespan(engine):
    @asynccontextmanager
    async def lifespan(app: FastAPI) -> AsyncIterator[None]:
        # Production/dev runtime goes through alembic so the schema lifecycle
        # stays owned by migration revisions. Tests bypass this via the
        # ``_unified_db_bootstrap`` conftest fixture, which calls
        # ``init_db(..., use_alembic=False)`` for a fast per-test create_all.
        init_db(engine, use_alembic=True)
        yield
        engine.dispose()

    return lifespan


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
