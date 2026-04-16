"""Pydantic request schemas for /api/llm routes."""

from __future__ import annotations

from ._base import AllowExtraBase


class CreateChannelRequest(AllowExtraBase):
    name: str
    base_url: str
    api_key: str
    is_enabled: bool = True
    max_concurrency: int = 5


class UpdateChannelRequest(AllowExtraBase):
    name: str | None = None
    base_url: str | None = None
    api_key: str | None = None
    is_enabled: bool | None = None
    max_concurrency: int | None = None


class ModuleBindingRequest(AllowExtraBase):
    channel_key: str
    model_id: str
