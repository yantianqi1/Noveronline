"""FastAPI exception handlers with the legacy JSON error shape."""

from __future__ import annotations

import traceback

from fastapi import FastAPI, HTTPException, Request
from fastapi.exception_handlers import http_exception_handler
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse

from ..config import Settings


def register_exception_handlers(app: FastAPI, settings: Settings) -> None:
    @app.exception_handler(HTTPException)
    async def handle_http_exception(request: Request, exc: HTTPException):
        return await http_exception_handler(request, exc)

    @app.exception_handler(RequestValidationError)
    async def handle_validation_error(request: Request, exc: RequestValidationError):
        detail = exc.errors()
        messages = []
        for err in detail:
            loc = " → ".join(str(part) for part in err.get("loc", []))
            messages.append(f"{loc}: {err.get('msg', '')}")
        return JSONResponse(
            status_code=400,
            content={"success": False, "error": "; ".join(messages), "detail": detail},
        )

    @app.exception_handler(Exception)
    async def handle_unhandled_exception(request: Request, exc: Exception):
        payload = _error_payload(exc, settings.DEBUG)
        return JSONResponse(status_code=500, content=payload)


def _error_payload(exc: Exception, debug: bool) -> dict:
    payload = {"success": False, "error": str(exc)}
    if debug:
        payload["traceback"] = traceback.format_exc()
    return payload
