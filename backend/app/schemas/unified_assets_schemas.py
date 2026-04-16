"""Pydantic request schemas for /api/unified-assets routes."""

from __future__ import annotations

from ._base import AllowExtraBase


class ReindexRequest(AllowExtraBase):
    project_id: str
