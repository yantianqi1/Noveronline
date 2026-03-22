"""统一的 LLM 模块路由器。"""

from __future__ import annotations

from typing import Optional

from ..utils.llm_client import LLMClient
from .llm_module_registry import STAGE_TO_MODULE_KEY
from .llm_settings_service import LlmSettingsService


class LlmRouter:
    """根据业务模块绑定解析 LLM 客户端。"""

    def __init__(self, settings_service: Optional[LlmSettingsService] = None):
        self.settings_service = settings_service or LlmSettingsService()

    def build_client(self, module_key: str) -> LLMClient:
        resolved = self.settings_service.resolve_module_binding(module_key)
        return LLMClient(
            api_key=resolved["api_key"],
            base_url=resolved["base_url"],
            model=resolved["model_id"],
        )

    def model_name_for_module(self, module_key: str) -> str:
        resolved = self.settings_service.resolve_module_binding(module_key)
        return resolved["model_id"]

    def model_name_for_stage(self, stage: str) -> str:
        module_key = STAGE_TO_MODULE_KEY.get(stage)
        if not module_key:
            return ""
        return self.model_name_for_module(module_key)
