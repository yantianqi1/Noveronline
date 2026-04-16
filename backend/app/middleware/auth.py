"""FastAPI API key middleware for privileged LLM writes."""

from __future__ import annotations

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import JSONResponse, Response

from ..config import Settings

LLM_WRITE_METHODS = {"POST", "PUT", "PATCH", "DELETE"}
LLM_WRITE_PREFIXES = (
    "/api/llm/channels",
    "/api/llm/module-bindings",
)


class ApiKeyAuthMiddleware(BaseHTTPMiddleware):
    def __init__(self, app, settings: Settings):
        super().__init__(app)
        self._settings = settings

    async def dispatch(self, request: Request, call_next) -> Response:
        if self._requires_auth(request) and not self._is_authorized(request):
            return JSONResponse(
                status_code=401,
                content={"success": False, "error": "Unauthorized"},
            )
        return await call_next(request)

    def _requires_auth(self, request: Request) -> bool:
        if not self._settings.ADMIN_SECRET:
            return False
        if request.method not in LLM_WRITE_METHODS:
            return False
        return request.url.path.startswith(LLM_WRITE_PREFIXES)

    def _is_authorized(self, request: Request) -> bool:
        expected = f"Bearer {self._settings.ADMIN_SECRET}"
        return request.headers.get("authorization") == expected
