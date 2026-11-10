"""FastAPI API key middleware for privileged LLM writes."""

from __future__ import annotations

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import JSONResponse, Response
from fastapi import HTTPException

from ..config import Settings

LLM_WRITE_METHODS = {"POST", "PUT", "PATCH", "DELETE"}
LLM_WRITE_PREFIXES = (
	"/api/llm/channels",
	"/api/llm/module-bindings",
)
LEGACY_API_PREFIXES = ("/api", "/v1")


class ApiKeyAuthMiddleware(BaseHTTPMiddleware):
    def __init__(self, app, settings: Settings):
        super().__init__(app)
        self._settings = settings


    async def dispatch(self, request: Request, call_next) -> Response:
        if self._requires_auth(request) and not self._settings.ADMIN_SECRET:
            return JSONResponse(
                status_code=503,
                content={"success": False, "error": "legacy API authentication is not configured"},
            )
        if self._requires_auth(request) and not self._is_authorized(request):
            return JSONResponse(
                status_code=401,
                content={"success": False, "error": "Unauthorized"},
            )
        return await call_next(request)


    def _requires_auth(self, request: Request) -> bool:
        if not self._settings.DEBUG and request.url.path.startswith(LEGACY_API_PREFIXES):
            return True
        if not self._settings.ADMIN_SECRET:
            return False
        if request.method not in LLM_WRITE_METHODS:
            return False
        return request.url.path.startswith(LLM_WRITE_PREFIXES)

    def _is_authorized(self, request: Request) -> bool:
        expected = f"Bearer {self._settings.ADMIN_SECRET}"
        return request.headers.get("authorization") == expected


async def require_admin(request: Request) -> None:
    """Protect privileged legacy routes at the route boundary.

    The middleware above remains for backwards compatibility with the original
    ``/api/llm`` routes, but route dependencies are required as well because
    the same router is mounted below ``/api/v2``.  Local debug runs may omit
    the secret; production-like runs fail closed instead of silently disabling
    the control.
    """
    settings = request.app.state.settings
    secret = str(getattr(settings, "ADMIN_SECRET", "") or "").strip()
    if not secret:
        if bool(getattr(settings, "DEBUG", False)):
            return
        raise HTTPException(status_code=503, detail="admin authentication is not configured")
    expected = f"Bearer {secret}"
    if request.headers.get("authorization") != expected:
        raise HTTPException(status_code=401, detail="Unauthorized")
