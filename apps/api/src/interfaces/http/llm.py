from fastapi import APIRouter, Header, HTTPException, Request
from pydantic import BaseModel
from sqlalchemy import select

from src.bootstrap.database import resolve_database_engine
from src.modules.llm.command_service import (
    bind_llm_module,
    create_llm_channel,
    delete_llm_channel,
    delete_llm_module_binding,
    update_llm_channel,
)
from src.shared.db.base import metadata
from src.shared.schemas import ErrorResponse

router = APIRouter(prefix="/llm", tags=["llm"])


class LlmChannelCommand(BaseModel):
    name: str
    base_url: str
    api_key: str | None = None
    is_enabled: bool = True
    max_concurrency: int = 4
    timeout_ms: int = 60000


class LlmChannelUpdateCommand(BaseModel):
    name: str | None = None
    base_url: str | None = None
    api_key: str | None = None
    is_enabled: bool | None = None
    max_concurrency: int | None = None
    timeout_ms: int | None = None


class LlmBindingCommand(BaseModel):
    llm_channel_id: str
    llm_model_id: str


def _not_implemented(trace_id: str, code: str, message: str, details: dict) -> HTTPException:
    return HTTPException(
        status_code=501,
        detail={
            "trace_id": trace_id,
            "error": {
                "code": code,
                "message": message,
                "details": details,
                "retryable": False,
            },
        },
    )


def _error(trace_id: str, status_code: int, code: str, message: str, details: dict) -> HTTPException:
    return HTTPException(
        status_code=status_code,
        detail={
            "trace_id": trace_id,
            "error": {
                "code": code,
                "message": message,
                "details": details,
                "retryable": False,
            },
        },
    )


@router.get("/settings", responses={501: {"model": ErrorResponse}})
def get_llm_settings(request: Request, x_trace_id: str | None = Header(default=None)) -> dict:
    engine = resolve_database_engine(request.app)
    with engine.connect() as connection:
        providers = connection.execute(select(metadata.tables["llm_providers"])).all()
        channels = connection.execute(select(metadata.tables["llm_channels"])).all()
        models = connection.execute(select(metadata.tables["llm_models"])).all()
        bindings = connection.execute(select(metadata.tables["llm_module_bindings"])).all()

    model_groups: dict[str, list[dict]] = {}
    for row in models:
        model_groups.setdefault(row.llm_channel_id, []).append(
            {
                "llm_model_id": row.llm_model_id,
                "provider_model_id": row.provider_model_id,
                "display_name": row.display_name,
                "synced_at": row.synced_at.isoformat() if hasattr(row.synced_at, "isoformat") else row.synced_at,
            }
        )

    channel_payload = [
        {
            "llm_channel_id": row.llm_channel_id,
            "llm_provider_id": row.llm_provider_id,
            "channel_key": row.channel_key,
            "name": row.name,
            "max_concurrency": row.max_concurrency,
            "timeout_ms": row.timeout_ms,
            "is_enabled": row.is_enabled,
            "models": model_groups.get(row.llm_channel_id, []),
        }
        for row in channels
    ]
    return {
        "data": {
            "providers": [
                {
                    "llm_provider_id": row.llm_provider_id,
                    "provider_key": row.provider_key,
                    "provider_type": row.provider_type,
                    "name": row.name,
                    "base_url": row.base_url,
                    "status": row.status,
                }
                for row in providers
            ],
            "channels": channel_payload,
            "modules": [
                {
                    "llm_module_binding_id": row.llm_module_binding_id,
                    "module_key": row.module_key,
                    "llm_channel_id": row.llm_channel_id,
                    "llm_model_id": row.llm_model_id,
                    "updated_at": row.updated_at.isoformat() if hasattr(row.updated_at, "isoformat") else row.updated_at,
                }
                for row in bindings
            ],
        },
        "meta": {"trace_id": x_trace_id or "trace-not-provided", "version": "v2"},
    }


@router.post("/channels", status_code=201, responses={501: {"model": ErrorResponse}})
def create_llm_channel_route(payload: LlmChannelCommand, request: Request, x_trace_id: str | None = Header(default=None)) -> dict:
    engine = resolve_database_engine(request.app)
    try:
        data = create_llm_channel(engine, payload.model_dump())
    except ValueError as exc:
        raise _error(x_trace_id or "trace-not-provided", 400, "llm_channel_create_invalid", str(exc), {})
    return {"data": data, "meta": {"trace_id": x_trace_id or "trace-not-provided", "version": "v2"}}


@router.patch("/channels/{channel_key}", responses={501: {"model": ErrorResponse}})
def update_llm_channel_route(
    channel_key: str,
    payload: LlmChannelUpdateCommand,
    request: Request,
    x_trace_id: str | None = Header(default=None),
) -> dict:
    engine = resolve_database_engine(request.app)
    try:
        data = update_llm_channel(engine, channel_key, payload.model_dump(exclude_none=True))
    except ValueError as exc:
        message = str(exc)
        status_code = 404 if "不存在" in message else 400
        raise _error(x_trace_id or "trace-not-provided", status_code, "llm_channel_update_invalid", message, {"channel_key": channel_key})
    return {"data": data, "meta": {"trace_id": x_trace_id or "trace-not-provided", "version": "v2"}}


@router.delete("/channels/{channel_key}", responses={501: {"model": ErrorResponse}})
def delete_llm_channel_route(channel_key: str, request: Request, x_trace_id: str | None = Header(default=None)) -> dict:
    engine = resolve_database_engine(request.app)
    try:
        data = delete_llm_channel(engine, channel_key)
    except ValueError as exc:
        raise _error(
            x_trace_id or "trace-not-provided",
            404,
            "llm_channel_delete_invalid",
            str(exc),
            {"channel_key": channel_key},
        )
    return {"data": data, "meta": {"trace_id": x_trace_id or "trace-not-provided", "version": "v2"}}


@router.post("/channels/{channel_key}/model-syncs", responses={501: {"model": ErrorResponse}})
def sync_llm_models(channel_key: str, x_trace_id: str | None = Header(default=None)) -> dict:
    raise _not_implemented(
        x_trace_id or "trace-not-provided",
        "llm_model_sync_not_implemented",
        "LLM model sync contract is frozen, workflow implementation lands next",
        {"channel_key": channel_key},
    )


@router.put("/module-bindings/{module_key}", responses={501: {"model": ErrorResponse}})
def bind_llm_module_route(
    module_key: str,
    payload: LlmBindingCommand,
    request: Request,
    x_trace_id: str | None = Header(default=None),
) -> dict:
    engine = resolve_database_engine(request.app)
    try:
        data = bind_llm_module(engine, module_key, payload.model_dump())
    except ValueError as exc:
        message = str(exc)
        status_code = 404 if "不存在" in message else 400
        raise _error(x_trace_id or "trace-not-provided", status_code, "llm_binding_invalid", message, {"module_key": module_key})
    return {"data": data, "meta": {"trace_id": x_trace_id or "trace-not-provided", "version": "v2"}}


@router.delete("/module-bindings/{module_key}", responses={501: {"model": ErrorResponse}})
def delete_llm_module_binding_route(
    module_key: str,
    request: Request,
    x_trace_id: str | None = Header(default=None),
) -> dict:
    engine = resolve_database_engine(request.app)
    try:
        data = delete_llm_module_binding(engine, module_key)
    except ValueError as exc:
        raise _error(
            x_trace_id or "trace-not-provided",
            404,
            "llm_binding_delete_invalid",
            str(exc),
            {"module_key": module_key},
        )
    return {"data": data, "meta": {"trace_id": x_trace_id or "trace-not-provided", "version": "v2"}}


@router.get("/activity", responses={501: {"model": ErrorResponse}})
def get_llm_activity(x_trace_id: str | None = Header(default=None)) -> dict:
    return {
        "data": {"items": []},
        "meta": {"trace_id": x_trace_id or "trace-not-provided", "version": "v2"},
    }
