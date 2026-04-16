"""LLM 设施配置服务。"""

from __future__ import annotations

import json
import uuid
from datetime import datetime
from typing import Any, Dict, List, Optional

from openai import OpenAI

from ..config import Config
from ..database import get_engine
from ..repositories.llm_repo import LlmRepository
from .llm_concurrency_service import llm_concurrency_service
from .llm_module_registry import get_llm_module, list_llm_modules


def _now() -> str:
    return datetime.now().isoformat(timespec="seconds")


class LlmSettingsService:
    """渠道、模型缓存和模块绑定的统一管理入口。"""

    def __init__(
        self,
        repo: Optional[LlmRepository] = None,
        openai_factory: Any = None,
        concurrency_service=None,
    ):
        self._repo = repo or LlmRepository(get_engine())
        self.openai_factory = openai_factory or OpenAI
        self.concurrency_service = concurrency_service or llm_concurrency_service

    async def get_snapshot(self) -> Dict[str, Any]:
        channels = self._repo.list_channels()
        bindings_rows = self._repo.list_bindings()
        bindings_map: Dict[str, Dict[str, Any]] = {
            b["module_key"]: b for b in bindings_rows
        }
        all_models = self._repo.list_models()
        models_by_channel: Dict[str, List[Dict[str, Any]]] = {}
        for m in all_models:
            models_by_channel.setdefault(m["channel_key"], []).append(
                {"model_id": m["model_id"], "owned_by": m["owned_by"], "fetched_at": m["fetched_at"]}
            )
        modules = []
        for module in list_llm_modules():
            module["binding"] = bindings_map.get(module["module_key"])
            modules.append(module)
        for channel in channels:
            await self.concurrency_service.set_limit(
                channel["channel_key"],
                channel["max_concurrency"],
            )
            channel.update(self._serialize_channel_fields(channel))
            channel["models"] = models_by_channel.get(channel["channel_key"], [])
            channel["runtime"] = await self._runtime_payload(channel["channel_key"])
        return {"modules": modules, "channels": channels}

    async def create_channel(self, payload: Dict[str, Any]) -> Dict[str, Any]:
        name = self._require_text(payload, "name")
        base_url = self._require_text(payload, "base_url")
        api_key = self._require_text(payload, "api_key")
        max_concurrency = self._resolve_max_concurrency(payload)
        channel_key = f"channel_{uuid.uuid4().hex[:12]}"
        timestamp = _now()
        self._repo.upsert_channel({
            "channel_key": channel_key,
            "name": name,
            "base_url": base_url,
            "api_key": api_key,
            "max_concurrency": max_concurrency,
            "is_enabled": self._bool_to_int(payload.get("is_enabled", True)),
            "created_at": timestamp,
            "updated_at": timestamp,
            "last_sync_status": "idle",
        })
        await self.concurrency_service.set_limit(channel_key, max_concurrency)
        return await self._snapshot_channel(channel_key)

    async def update_channel(self, channel_key: str, payload: Dict[str, Any]) -> Dict[str, Any]:
        row = self._repo.get_channel(channel_key)
        if not row:
            raise ValueError(f"渠道不存在: {channel_key}")
        updated = {
            "channel_key": channel_key,
            "name": self._optional_text(payload, "name") or row["name"],
            "base_url": self._optional_text(payload, "base_url") or row["base_url"],
            "api_key": self._optional_text(payload, "api_key") or row["api_key"],
            "max_concurrency": self._resolve_max_concurrency(
                payload,
                current_value=row["max_concurrency"],
            ),
            "is_enabled": self._bool_to_int(payload.get("is_enabled", bool(row["is_enabled"]))),
            "updated_at": _now(),
        }
        self._repo.upsert_channel(updated)
        await self.concurrency_service.set_limit(
            channel_key,
            updated["max_concurrency"],
        )
        return await self._snapshot_channel(channel_key)

    def delete_channel(self, channel_key: str) -> Dict[str, Any]:
        count = self._repo.delete_channel(channel_key)
        if count == 0:
            raise ValueError(f"渠道不存在: {channel_key}")
        return {"channel_key": channel_key, "deleted": True}

    async def sync_models(self, channel_key: str) -> Dict[str, Any]:
        row = self._repo.get_channel(channel_key)
        if not row:
            raise ValueError(f"渠道不存在: {channel_key}")
        try:
            await self.concurrency_service.set_limit(
                row["channel_key"],
                row["max_concurrency"],
            )
            async with self.concurrency_service.async_slot(row["channel_key"]):
                models = self._fetch_models_from_upstream(
                    row["base_url"],
                    row["api_key"],
                )
        except Exception as exc:
            self._mark_sync_failed(channel_key, str(exc))
            raise
        timestamp = _now()
        model_rows = [
            {
                "model_id": item["model_id"],
                "owned_by": item.get("owned_by"),
                "fetched_at": timestamp,
                "raw_payload": json.dumps(item["raw_payload"], ensure_ascii=False),
            }
            for item in models
        ]
        self._repo.sync_models(channel_key, model_rows)
        self._repo.upsert_channel({
            "channel_key": channel_key,
            "last_sync_at": timestamp,
            "last_sync_status": "success",
            "last_sync_error": None,
            "updated_at": timestamp,
        })
        return await self._snapshot_channel(channel_key)

    def set_module_binding(self, module_key: str, payload: Dict[str, Any]) -> Dict[str, Any]:
        get_llm_module(module_key)
        channel_key = self._require_text(payload, "channel_key")
        model_id = self._require_text(payload, "model_id")
        timestamp = _now()
        channel = self._repo.get_channel(channel_key)
        if not channel:
            raise ValueError(f"渠道不存在: {channel_key}")
        if not bool(channel["is_enabled"]):
            raise ValueError("渠道已停用，请先启用后再绑定模型")
        if not self._repo.get_model(channel_key, model_id):
            raise ValueError("模型未同步，请先同步该渠道的模型列表")
        self._repo.upsert_binding({
            "module_key": module_key,
            "channel_key": channel_key,
            "model_id": model_id,
            "updated_at": timestamp,
        })
        binding = self._repo.get_binding(module_key)
        return binding

    def delete_module_binding(self, module_key: str) -> Dict[str, Any]:
        get_llm_module(module_key)
        count = self._repo.delete_binding(module_key)
        if count == 0:
            raise ValueError(f"模块绑定不存在: {module_key}")
        return {"module_key": module_key, "deleted": True}

    def resolve_module_binding(self, module_key: str) -> Dict[str, Any]:
        module = get_llm_module(module_key)
        binding = self._repo.get_binding(module_key)
        if not binding:
            raise ValueError(
                f"{module.label} 未配置 LLM 渠道和模型；请先在全局设施面板完成绑定，或显式传入 use_llm=False"
            )
        channel = self._repo.get_channel(binding["channel_key"])
        if not channel:
            raise ValueError(f"{module.label} 绑定的渠道已不存在；请重新在全局设施面板配置")
        if not bool(channel["is_enabled"]):
            raise ValueError(f"{module.label} 绑定的渠道已停用；请先在全局设施面板启用渠道或重新绑定")
        return {
            "module_key": module_key,
            "module_label": module.label,
            "channel_key": channel["channel_key"],
            "channel_name": channel["name"],
            "base_url": channel["base_url"],
            "api_key": channel["api_key"],
            "model_id": binding["model_id"],
            "max_concurrency": channel["max_concurrency"],
        }

    def _fetch_models_from_upstream(self, base_url: str, api_key: str) -> List[Dict[str, Any]]:
        client = self.openai_factory(
            api_key=api_key,
            base_url=base_url,
            timeout=Config.LLM_REQUEST_TIMEOUT_SECONDS,
        )
        response = client.models.list()
        return [self._normalize_model(item) for item in getattr(response, "data", [])]

    def _mark_sync_failed(self, channel_key: str, error_message: str) -> None:
        timestamp = _now()
        self._repo.upsert_channel({
            "channel_key": channel_key,
            "last_sync_at": timestamp,
            "last_sync_status": "failed",
            "last_sync_error": error_message,
            "updated_at": timestamp,
        })

    async def _snapshot_channel(self, channel_key: str) -> Dict[str, Any]:
        row = self._repo.get_channel(channel_key)
        if not row:
            raise ValueError(f"渠道不存在: {channel_key}")
        channel = self._serialize_channel_fields(row)
        await self.concurrency_service.set_limit(
            channel_key,
            channel["max_concurrency"],
        )
        models = self._repo.list_models(channel_key)
        channel["models"] = [
            {"model_id": m["model_id"], "owned_by": m["owned_by"], "fetched_at": m["fetched_at"]}
            for m in models
        ]
        channel["runtime"] = await self._runtime_payload(channel_key)
        return channel

    def _serialize_channel_fields(self, row: Dict[str, Any]) -> Dict[str, Any]:
        return {
            "channel_key": row["channel_key"],
            "name": row["name"],
            "base_url": row["base_url"],
            "max_concurrency": int(row["max_concurrency"]),
            "is_enabled": bool(row["is_enabled"]),
            "created_at": row["created_at"],
            "updated_at": row["updated_at"],
            "last_sync_at": row.get("last_sync_at"),
            "last_sync_status": row.get("last_sync_status"),
            "last_sync_error": row.get("last_sync_error"),
            "api_key_masked": self._mask_api_key(row["api_key"]),
        }

    def _normalize_model(self, item: Any) -> Dict[str, Any]:
        raw_payload = item.model_dump() if hasattr(item, "model_dump") else dict(item.__dict__)
        return {
            "model_id": getattr(item, "id", ""),
            "owned_by": getattr(item, "owned_by", None),
            "raw_payload": raw_payload,
        }

    def _mask_api_key(self, api_key: str) -> str:
        if len(api_key) <= 8:
            return "*" * len(api_key)
        return f"{api_key[:3]}***{api_key[-4:]}"

    def _require_text(self, payload: Dict[str, Any], field_name: str) -> str:
        value = self._optional_text(payload, field_name)
        if not value:
            raise ValueError(f"请提供 {field_name}")
        return value

    def _optional_text(self, payload: Dict[str, Any], field_name: str) -> Optional[str]:
        value = payload.get(field_name)
        if value is None:
            return None
        text = str(value).strip()
        return text or None

    def _bool_to_int(self, value: Any) -> int:
        return 1 if bool(value) else 0

    def _resolve_max_concurrency(
        self,
        payload: Dict[str, Any],
        current_value: int = 4,
    ) -> int:
        raw_value = payload.get("max_concurrency", current_value)
        try:
            value = int(raw_value)
        except (TypeError, ValueError) as exc:
            raise ValueError("max_concurrency 必须是整数") from exc
        if value < 1:
            raise ValueError("max_concurrency 必须大于等于 1")
        return value

    async def _runtime_payload(self, channel_key: str) -> Dict[str, int]:
        snapshot = await self.concurrency_service.snapshot(channel_key)
        return {
            "inflight": snapshot["inflight"],
            "waiting": snapshot["waiting"],
        }
