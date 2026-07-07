"""LLM Facility adapter used by the Pi writer runtime bridge."""

from __future__ import annotations

from typing import Any

from app.services.llm_router import LlmRouter

from .errors import LlmModuleUnboundError


class LlmFacilityAdapter:
    """Resolve runtime model access only through module bindings."""

    def __init__(self, router: LlmRouter | None = None):
        self.router = router or LlmRouter()

    async def build_async_client(
        self,
        *,
        tenant_id: str,
        project_id: str,
        run_id: str,
        module_key: str,
    ):
        try:
            return await self.router.build_async_client(module_key)
        except ValueError as exc:
            raise LlmModuleUnboundError(module_key, str(exc)) from exc

    def binding_summary(
        self,
        *,
        tenant_id: str,
        project_id: str,
        run_id: str,
        module_key: str,
    ) -> dict[str, Any]:
        try:
            resolved = self.router.settings_service.resolve_module_binding(module_key)
        except ValueError as exc:
            raise LlmModuleUnboundError(module_key, str(exc)) from exc
        return {
            "tenant_id": tenant_id,
            "project_id": project_id,
            "run_id": run_id,
            "module_key": module_key,
            "channel_key": resolved["channel_key"],
            "model_id": resolved["model_id"],
            "base_url": resolved["base_url"],
            "max_concurrency": resolved["max_concurrency"],
        }
