from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import JSONResponse

from src.interfaces.http.archive import router as archive_router
from src.bootstrap.settings import AppSettings
from src.interfaces.http.graph import router as graph_router
from src.interfaces.http.health import router as health_router
from src.interfaces.http.llm import router as llm_router
from src.interfaces.http.operations import router as operations_router
from src.interfaces.http.worldline import router as worldline_router
from src.interfaces.http.worldline_commands import router as worldline_commands_router
from src.interfaces.http.workspaces import router as workspaces_router
from src.interfaces.http.writer import router as writer_router


def create_app(settings: AppSettings | None = None) -> FastAPI:
    app_settings = settings or AppSettings()
    app = FastAPI(
        title=app_settings.app_name,
        version="0.1.0",
        docs_url=f"{app_settings.api_prefix}/docs",
        openapi_url=f"{app_settings.api_prefix}/openapi.json",
    )
    app.state.settings = app_settings

    @app.exception_handler(HTTPException)
    async def handle_http_exception(_: Request, exc: HTTPException) -> JSONResponse:
        if isinstance(exc.detail, dict) and "error" in exc.detail and "trace_id" in exc.detail:
            return JSONResponse(status_code=exc.status_code, content=exc.detail)
        return JSONResponse(
            status_code=exc.status_code,
            content={
                "trace_id": "trace-not-provided",
                "error": {
                    "code": "http_exception",
                    "message": str(exc.detail),
                    "details": {},
                    "retryable": False,
                },
            },
        )

    app.include_router(archive_router, prefix=app_settings.api_prefix)
    app.include_router(health_router, prefix=app_settings.api_prefix)
    app.include_router(graph_router, prefix=app_settings.api_prefix)
    app.include_router(llm_router, prefix=app_settings.api_prefix)
    app.include_router(operations_router, prefix=app_settings.api_prefix)
    app.include_router(worldline_router, prefix=app_settings.api_prefix)
    app.include_router(worldline_commands_router, prefix=app_settings.api_prefix)
    app.include_router(workspaces_router, prefix=app_settings.api_prefix)
    app.include_router(writer_router, prefix=app_settings.api_prefix)
    return app
