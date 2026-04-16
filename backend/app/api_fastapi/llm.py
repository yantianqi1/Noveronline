"""Native FastAPI LLM facility routes."""

from __future__ import annotations

from fastapi import APIRouter

from app.services.llm_activity_tracker import llm_activity_tracker
from app.services.llm_concurrency_service import llm_concurrency_service
from app.services.llm_settings_service import LlmSettingsService

from app.schemas.llm_schemas import CreateChannelRequest, ModuleBindingRequest, UpdateChannelRequest

from .common import err, ok, status_for_value_error

router = APIRouter(prefix="/llm", tags=["llm"])


@router.get("/settings")
async def get_llm_settings():
    try:
        return ok(await LlmSettingsService().get_snapshot())
    except Exception as exc:
        return err(exc)


@router.post("/channels")
async def create_llm_channel(body: CreateChannelRequest):
    try:
        payload = body.model_dump()
        return ok(await LlmSettingsService().create_channel(payload), status_code=201)
    except ValueError as exc:
        return err(exc, status_code=400)
    except Exception as exc:
        return err(exc)


@router.patch("/channels/{channel_key}")
async def update_llm_channel(channel_key: str, body: UpdateChannelRequest):
    try:
        payload = body.model_dump(exclude_none=True)
        return ok(await LlmSettingsService().update_channel(channel_key, payload))
    except ValueError as exc:
        return err(exc, status_code=400)
    except Exception as exc:
        return err(exc)


@router.delete("/channels/{channel_key}")
async def delete_llm_channel(channel_key: str):
    try:
        return ok(LlmSettingsService().delete_channel(channel_key))
    except ValueError as exc:
        return err(exc, status_code=404)
    except Exception as exc:
        return err(exc)


@router.post("/channels/{channel_key}/sync-models")
async def sync_llm_channel_models(channel_key: str):
    try:
        return ok(await LlmSettingsService().sync_models(channel_key))
    except ValueError as exc:
        return err(exc, status_code=400)
    except Exception as exc:
        return err(exc)


@router.put("/module-bindings/{module_key}")
async def update_llm_module_binding(module_key: str, body: ModuleBindingRequest):
    try:
        payload = body.model_dump()
        return ok(LlmSettingsService().set_module_binding(module_key, payload))
    except ValueError as exc:
        return err(exc, status_code=400)
    except Exception as exc:
        return err(exc)


@router.delete("/module-bindings/{module_key}")
async def delete_llm_module_binding(module_key: str):
    try:
        return ok(LlmSettingsService().delete_module_binding(module_key))
    except ValueError as exc:
        return err(exc, status_code=status_for_value_error(exc))
    except Exception as exc:
        return err(exc)


@router.get("/activity")
async def get_llm_activity():
    try:
        calls = await llm_activity_tracker.snapshot()
        seen = {item["channel_key"] for item in calls if item["channel_key"]}
        seen.update(await llm_concurrency_service.channel_keys())
        channels = {}
        for key in seen:
            if key:
                channels[key] = await llm_concurrency_service.snapshot(key)
        return ok({"calls": calls, "channels": channels, "total_active": len(calls)})
    except Exception as exc:
        return err(exc)
