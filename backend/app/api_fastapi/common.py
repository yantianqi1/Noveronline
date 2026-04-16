"""Shared helpers for native FastAPI API routes."""

from __future__ import annotations

import traceback
from typing import Any

from fastapi import HTTPException
from fastapi.responses import JSONResponse


def ok(data: Any = None, *, status_code: int = 200, count: int | None = None) -> JSONResponse:
    payload = {"success": True, "data": data}
    if count is not None:
        payload["count"] = count
    return JSONResponse(payload, status_code=status_code)


def err(exc: Exception | str, *, status_code: int = 500, debug: bool = True) -> JSONResponse:
    payload = {"success": False, "error": str(exc)}
    if debug and not isinstance(exc, str):
        payload["traceback"] = traceback.format_exc()
    return JSONResponse(payload, status_code=status_code)


def no_store(payload: dict, *, status_code: int = 200) -> JSONResponse:
    return JSONResponse(payload, status_code=status_code, headers={"Cache-Control": "no-store"})


def status_for_value_error(exc: ValueError, *, missing_hint: str = "不存在") -> int:
    return 404 if missing_hint in str(exc) else 400


def require_payload_value(payload: dict, key: str) -> Any:
    value = payload.get(key)
    if value in (None, ""):
        raise HTTPException(status_code=400, detail=f"请提供 {key}")
    return value
