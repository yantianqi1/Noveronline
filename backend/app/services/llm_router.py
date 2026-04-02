"""统一的 LLM 模块路由器。"""

from __future__ import annotations

from typing import Optional

from .llm_activity_tracker import llm_activity_tracker as _default_activity_tracker
from .llm_concurrency_service import llm_concurrency_service
from ..utils.llm_client import LLMClient
from .llm_module_registry import STAGE_TO_MODULE_KEY
from .llm_settings_service import LlmSettingsService


class LlmRouter:
    """根据业务模块绑定解析 LLM 客户端。"""

    def __init__(
        self,
        settings_service: Optional[LlmSettingsService] = None,
        concurrency_service=None,
        activity_tracker=None,
    ):
        self.settings_service = settings_service or LlmSettingsService()
        self.concurrency_service = concurrency_service or llm_concurrency_service
        self.activity_tracker = activity_tracker or _default_activity_tracker

    def build_client(self, module_key: str) -> LLMClient:
        resolved = self.settings_service.resolve_module_binding(module_key)
        self.concurrency_service.set_limit(
            resolved["channel_key"],
            resolved["max_concurrency"],
        )
        return LLMClient(
            api_key=resolved["api_key"],
            base_url=resolved["base_url"],
            model=resolved["model_id"],
            channel_key=resolved["channel_key"],
            max_concurrency=resolved["max_concurrency"],
            concurrency_service=self.concurrency_service,
            module_key=module_key,
            activity_tracker=self.activity_tracker,
        )

    def model_name_for_module(self, module_key: str) -> str:
        resolved = self.settings_service.resolve_module_binding(module_key)
        return resolved["model_id"]

    def model_name_for_stage(self, stage: str) -> str:
        module_key = STAGE_TO_MODULE_KEY.get(stage)
        if not module_key:
            return ""
        return self.model_name_for_module(module_key)
