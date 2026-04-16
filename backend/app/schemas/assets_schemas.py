"""Pydantic request schemas for /api/assets routes."""

from __future__ import annotations

from typing import Any

from ._base import AllowExtraBase


class AssetSearchRequest(AllowExtraBase):
    query: str
    scope: str = "all"
    project_id: str | None = None
    asset_type: str | None = None
    category: str | None = None
    enabled_only: bool = True
    limit: int = 20


class CreateAssetRequest(AllowExtraBase):
    asset_type: str
    title: str
    scope: str = "global"
    project_id: str | None = None
    category: str = ""
    summary: str = ""
    content: str = ""
    payload: dict[str, Any] | None = None
    tags: list[str] | None = None
    source_kind: str = "manual"
    source_ref: str = ""
    enabled: bool = True
    pinned: bool = False


class UpdateAssetRequest(AllowExtraBase):
    scope: str = "global"
    project_id: str | None = None


class BatchToggleRequest(AllowExtraBase):
    asset_ids: list[str]
    enabled: bool = True
    scope: str = "global"
    project_id: str | None = None


class BatchCategorizeRequest(AllowExtraBase):
    asset_ids: list[str]
    category: str = ""
    scope: str = "global"
    project_id: str | None = None


class IngestRequest(AllowExtraBase):
    raw_text: str = ""
    text: str = ""
    scope: str = "global"
    project_id: str | None = None
    hint_type: str | None = None


class StyleExtractRequest(AllowExtraBase):
    text: str
    title: str
    category: str = ""
    tags: list[str] = []
    target_chunk_chars: int = 3000
    max_chunks: int = 30
