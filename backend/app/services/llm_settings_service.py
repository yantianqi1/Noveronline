"""LLM 设施配置服务。"""

from __future__ import annotations

import json
import uuid
from datetime import datetime
from typing import Any, Dict, List, Optional

from openai import OpenAI

from ..config import Config
from .llm_module_registry import get_llm_module, list_llm_modules
from .llm_storage import LlmStorage


def _now() -> str:
    return datetime.now().isoformat(timespec="seconds")


class LlmSettingsService:
    """渠道、模型缓存和模块绑定的统一管理入口。"""

    def __init__(
        self,
        storage: Optional[LlmStorage] = None,
        openai_factory: Any = None,
    ):
        self.storage = storage or LlmStorage()
        self.openai_factory = openai_factory or OpenAI

    def get_snapshot(self) -> Dict[str, Any]:
        with self.storage.connect() as connection:
            channels = self._list_channels(connection)
            bindings = self._list_bindings(connection)
            models_by_channel = self._list_models_by_channel(connection)
        modules = []
        for module in list_llm_modules():
            module["binding"] = bindings.get(module["module_key"])
            modules.append(module)
        for channel in channels:
            channel["models"] = models_by_channel.get(channel["channel_key"], [])
        return {"modules": modules, "channels": channels}

    def create_channel(self, payload: Dict[str, Any]) -> Dict[str, Any]:
        name = self._require_text(payload, "name")
        base_url = self._require_text(payload, "base_url")
        api_key = self._require_text(payload, "api_key")
        channel_key = f"channel_{uuid.uuid4().hex[:12]}"
        timestamp = _now()
        with self.storage.connect() as connection:
            connection.execute(
                """
                INSERT INTO llm_channels (
                    channel_key, name, base_url, api_key, is_enabled,
                    created_at, updated_at, last_sync_status
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    channel_key,
                    name,
                    base_url,
                    api_key,
                    self._bool_to_int(payload.get("is_enabled", True)),
                    timestamp,
                    timestamp,
                    "idle",
                ),
            )
            connection.commit()
            return self._snapshot_channel(connection, channel_key)

    def update_channel(self, channel_key: str, payload: Dict[str, Any]) -> Dict[str, Any]:
        with self.storage.connect() as connection:
            row = self._get_channel_row(connection, channel_key)
            if not row:
                raise ValueError(f"渠道不存在: {channel_key}")
            updated = {
                "name": self._optional_text(payload, "name") or row["name"],
                "base_url": self._optional_text(payload, "base_url") or row["base_url"],
                "api_key": self._optional_text(payload, "api_key") or row["api_key"],
                "is_enabled": self._bool_to_int(payload.get("is_enabled", bool(row["is_enabled"]))),
                "updated_at": _now(),
            }
            connection.execute(
                """
                UPDATE llm_channels
                SET name = ?, base_url = ?, api_key = ?, is_enabled = ?, updated_at = ?
                WHERE channel_key = ?
                """,
                (
                    updated["name"],
                    updated["base_url"],
                    updated["api_key"],
                    updated["is_enabled"],
                    updated["updated_at"],
                    channel_key,
                ),
            )
            connection.commit()
            return self._snapshot_channel(connection, channel_key)

    def delete_channel(self, channel_key: str) -> Dict[str, Any]:
        with self.storage.connect() as connection:
            result = connection.execute(
                "DELETE FROM llm_channels WHERE channel_key = ?",
                (channel_key,),
            )
            connection.commit()
        if result.rowcount == 0:
            raise ValueError(f"渠道不存在: {channel_key}")
        return {"channel_key": channel_key, "deleted": True}

    def sync_models(self, channel_key: str) -> Dict[str, Any]:
        with self.storage.connect() as connection:
            row = self._get_channel_row(connection, channel_key)
            if not row:
                raise ValueError(f"渠道不存在: {channel_key}")
        try:
            models = self._fetch_models_from_upstream(row["base_url"], row["api_key"])
        except Exception as exc:
            self._mark_sync_failed(channel_key, str(exc))
            raise
        timestamp = _now()
        with self.storage.connect() as connection:
            connection.execute("DELETE FROM llm_models WHERE channel_key = ?", (channel_key,))
            for item in models:
                connection.execute(
                    """
                    INSERT INTO llm_models (channel_key, model_id, owned_by, fetched_at, raw_payload)
                    VALUES (?, ?, ?, ?, ?)
                    """,
                    (
                        channel_key,
                        item["model_id"],
                        item.get("owned_by"),
                        timestamp,
                        json.dumps(item["raw_payload"], ensure_ascii=False),
                    ),
                )
            connection.execute(
                """
                UPDATE llm_channels
                SET last_sync_at = ?, last_sync_status = ?, last_sync_error = NULL, updated_at = ?
                WHERE channel_key = ?
                """,
                (timestamp, "success", timestamp, channel_key),
            )
            connection.commit()
            return self._snapshot_channel(connection, channel_key)

    def set_module_binding(self, module_key: str, payload: Dict[str, Any]) -> Dict[str, Any]:
        get_llm_module(module_key)
        channel_key = self._require_text(payload, "channel_key")
        model_id = self._require_text(payload, "model_id")
        timestamp = _now()
        with self.storage.connect() as connection:
            if not self._get_channel_row(connection, channel_key):
                raise ValueError(f"渠道不存在: {channel_key}")
            if not self._model_exists(connection, channel_key, model_id):
                raise ValueError("模型未同步，请先同步该渠道的模型列表")
            connection.execute(
                """
                INSERT INTO llm_module_bindings (module_key, channel_key, model_id, updated_at)
                VALUES (?, ?, ?, ?)
                ON CONFLICT(module_key) DO UPDATE SET
                    channel_key = excluded.channel_key,
                    model_id = excluded.model_id,
                    updated_at = excluded.updated_at
                """,
                (module_key, channel_key, model_id, timestamp),
            )
            connection.commit()
            bindings = self._list_bindings(connection)
            return bindings[module_key]

    def resolve_module_binding(self, module_key: str) -> Dict[str, Any]:
        module = get_llm_module(module_key)
        with self.storage.connect() as connection:
            binding = self._get_binding_row(connection, module_key)
            if not binding:
                raise ValueError(
                    f"{module.label} 未配置 LLM 渠道和模型；请先在全局设施面板完成绑定，或显式传入 use_llm=False"
                )
            channel = self._get_channel_row(connection, binding["channel_key"])
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
        with self.storage.connect() as connection:
            connection.execute(
                """
                UPDATE llm_channels
                SET last_sync_at = ?, last_sync_status = ?, last_sync_error = ?, updated_at = ?
                WHERE channel_key = ?
                """,
                (timestamp, "failed", error_message, timestamp, channel_key),
            )
            connection.commit()

    def _list_channels(self, connection) -> List[Dict[str, Any]]:
        rows = connection.execute("SELECT * FROM llm_channels ORDER BY created_at DESC").fetchall()
        return [self._serialize_channel(row) for row in rows]

    def _list_models_by_channel(self, connection) -> Dict[str, List[Dict[str, Any]]]:
        rows = connection.execute("SELECT * FROM llm_models ORDER BY model_id ASC").fetchall()
        grouped: Dict[str, List[Dict[str, Any]]] = {}
        for row in rows:
            grouped.setdefault(row["channel_key"], []).append(
                {"model_id": row["model_id"], "owned_by": row["owned_by"], "fetched_at": row["fetched_at"]}
            )
        return grouped

    def _list_bindings(self, connection) -> Dict[str, Dict[str, Any]]:
        rows = connection.execute("SELECT * FROM llm_module_bindings").fetchall()
        return {
            row["module_key"]: {
                "module_key": row["module_key"],
                "channel_key": row["channel_key"],
                "model_id": row["model_id"],
                "updated_at": row["updated_at"],
            }
            for row in rows
        }

    def _snapshot_channel(self, connection, channel_key: str) -> Dict[str, Any]:
        row = self._get_channel_row(connection, channel_key)
        if not row:
            raise ValueError(f"渠道不存在: {channel_key}")
        channel = self._serialize_channel(row)
        channel["models"] = self._list_models_by_channel(connection).get(channel_key, [])
        return channel

    def _get_channel_row(self, connection, channel_key: str):
        return connection.execute("SELECT * FROM llm_channels WHERE channel_key = ?", (channel_key,)).fetchone()

    def _get_binding_row(self, connection, module_key: str):
        return connection.execute(
            "SELECT * FROM llm_module_bindings WHERE module_key = ?",
            (module_key,),
        ).fetchone()

    def _model_exists(self, connection, channel_key: str, model_id: str) -> bool:
        row = connection.execute(
            "SELECT 1 FROM llm_models WHERE channel_key = ? AND model_id = ?",
            (channel_key, model_id),
        ).fetchone()
        return row is not None

    def _serialize_channel(self, row) -> Dict[str, Any]:
        return {
            "channel_key": row["channel_key"],
            "name": row["name"],
            "base_url": row["base_url"],
            "is_enabled": bool(row["is_enabled"]),
            "created_at": row["created_at"],
            "updated_at": row["updated_at"],
            "last_sync_at": row["last_sync_at"],
            "last_sync_status": row["last_sync_status"],
            "last_sync_error": row["last_sync_error"],
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
