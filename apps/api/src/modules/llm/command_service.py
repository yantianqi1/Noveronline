from __future__ import annotations

from datetime import datetime, timezone
import uuid

from sqlalchemy import select
from sqlalchemy.engine import Engine

from src.shared.db.base import metadata


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _mask_secret(value: str) -> str:
    if len(value) <= 8:
        return "*" * len(value)
    return f"{value[:3]}***{value[-4:]}"


def _inline_secret_ref(api_key: str) -> str:
    return f"inline-secret:{api_key}"


def _extract_secret(ref: str) -> str:
    return ref.removeprefix("inline-secret:")


def _require_text(payload: dict, field_name: str) -> str:
    value = str(payload.get(field_name, "")).strip()
    if not value:
        raise ValueError(f"请提供 {field_name}")
    return value


def _resolve_max_concurrency(payload: dict, current_value: int | None = None) -> int:
    raw_value = payload.get("max_concurrency", current_value if current_value is not None else 4)
    try:
        value = int(raw_value)
    except (TypeError, ValueError) as exc:
        raise ValueError("max_concurrency 必须是整数") from exc
    if value < 1:
        raise ValueError("max_concurrency 必须大于等于 1")
    return value


def _fetch_channel(connection, channel_key: str):
    channels = metadata.tables["llm_channels"]
    stmt = select(channels).where(channels.c.channel_key == channel_key)
    return connection.execute(stmt).first()


def _snapshot_channel(connection, channel_key: str) -> dict:
    channels = metadata.tables["llm_channels"]
    providers = metadata.tables["llm_providers"]
    stmt = (
        select(channels, providers.c.provider_key, providers.c.base_url, providers.c.auth_secret_ref, providers.c.status)
        .join(providers, channels.c.llm_provider_id == providers.c.llm_provider_id)
        .where(channels.c.channel_key == channel_key)
    )
    row = connection.execute(stmt).first()
    if row is None:
        raise ValueError(f"渠道不存在: {channel_key}")
    return {
        "llm_channel_id": row.llm_channel_id,
        "llm_provider_id": row.llm_provider_id,
        "channel_key": row.channel_key,
        "provider_key": row.provider_key,
        "name": row.name,
        "base_url": row.base_url,
        "api_key_masked": _mask_secret(_extract_secret(row.auth_secret_ref)),
        "max_concurrency": row.max_concurrency,
        "timeout_ms": row.timeout_ms,
        "is_enabled": row.is_enabled,
        "status": row.status,
    }


def create_llm_channel(engine: Engine, payload: dict) -> dict:
    name = _require_text(payload, "name")
    base_url = _require_text(payload, "base_url")
    api_key = _require_text(payload, "api_key")
    max_concurrency = _resolve_max_concurrency(payload)
    now = _now()
    channel_key = f"channel_{uuid.uuid4().hex[:12]}"
    provider_id = f"provider_{uuid.uuid4().hex[:12]}"
    channel_id = f"channel_{uuid.uuid4().hex[:12]}"
    with engine.begin() as connection:
        providers = metadata.tables["llm_providers"]
        channels = metadata.tables["llm_channels"]
        connection.execute(
            providers.insert().values(
                llm_provider_id=provider_id,
                provider_key=channel_key,
                provider_type="openai-compatible",
                name=name,
                base_url=base_url,
                auth_secret_ref=_inline_secret_ref(api_key),
                status="active" if payload.get("is_enabled", True) else "disabled",
                created_at=now,
                updated_at=now,
            )
        )
        connection.execute(
            channels.insert().values(
                llm_channel_id=channel_id,
                llm_provider_id=provider_id,
                channel_key=channel_key,
                name=name,
                max_concurrency=max_concurrency,
                timeout_ms=int(payload.get("timeout_ms", 60000)),
                is_enabled=bool(payload.get("is_enabled", True)),
                created_at=now,
                updated_at=now,
            )
        )
        return _snapshot_channel(connection, channel_key)


def update_llm_channel(engine: Engine, channel_key: str, payload: dict) -> dict:
    now = _now()
    with engine.begin() as connection:
        row = _fetch_channel(connection, channel_key)
        if row is None:
            raise ValueError(f"渠道不存在: {channel_key}")
        providers = metadata.tables["llm_providers"]
        channels = metadata.tables["llm_channels"]
        provider_row = connection.execute(
            select(providers).where(providers.c.llm_provider_id == row.llm_provider_id)
        ).first()
        channel_values = {
            "name": str(payload.get("name", row.name)).strip() or row.name,
            "max_concurrency": _resolve_max_concurrency(payload, row.max_concurrency),
            "timeout_ms": int(payload.get("timeout_ms", row.timeout_ms)),
            "is_enabled": bool(payload.get("is_enabled", row.is_enabled)),
            "updated_at": now,
        }
        provider_values = {
            "name": channel_values["name"],
            "base_url": str(payload.get("base_url", provider_row.base_url)).strip() or provider_row.base_url,
            "auth_secret_ref": _inline_secret_ref(payload["api_key"]) if payload.get("api_key") else provider_row.auth_secret_ref,
            "status": "active" if channel_values["is_enabled"] else "disabled",
            "updated_at": now,
        }
        connection.execute(
            channels.update().where(channels.c.channel_key == channel_key).values(**channel_values)
        )
        connection.execute(
            providers.update().where(providers.c.llm_provider_id == row.llm_provider_id).values(**provider_values)
        )
        return _snapshot_channel(connection, channel_key)


def bind_llm_module(engine: Engine, module_key: str, payload: dict) -> dict:
    channel_id = _require_text(payload, "llm_channel_id")
    model_id = _require_text(payload, "llm_model_id")
    bindings = metadata.tables["llm_module_bindings"]
    channels = metadata.tables["llm_channels"]
    models = metadata.tables["llm_models"]
    now = _now()
    with engine.begin() as connection:
        channel = connection.execute(
            select(channels).where(channels.c.llm_channel_id == channel_id)
        ).first()
        if channel is None:
            raise ValueError("渠道不存在")
        if not channel.is_enabled:
            raise ValueError("渠道已停用，请先启用后再绑定模型")
        model = connection.execute(
            select(models).where(
                models.c.llm_model_id == model_id,
                models.c.llm_channel_id == channel_id,
            )
        ).first()
        if model is None:
            raise ValueError("模型未同步，请先同步该渠道的模型列表")
        existing = connection.execute(
            select(bindings).where(bindings.c.module_key == module_key)
        ).first()
        values = {
            "module_key": module_key,
            "llm_channel_id": channel_id,
            "llm_model_id": model_id,
            "updated_at": now,
        }
        if existing is None:
            values["llm_module_binding_id"] = f"binding_{uuid.uuid4().hex[:12]}"
            connection.execute(bindings.insert().values(**values))
        else:
            connection.execute(
                bindings.update().where(bindings.c.module_key == module_key).values(**values)
            )
            values["llm_module_binding_id"] = existing.llm_module_binding_id
        return {
            "llm_module_binding_id": values["llm_module_binding_id"],
            "module_key": module_key,
            "llm_channel_id": channel_id,
            "llm_model_id": model_id,
            "updated_at": now.isoformat(),
        }


def delete_llm_module_binding(engine: Engine, module_key: str) -> dict:
    bindings = metadata.tables["llm_module_bindings"]
    with engine.begin() as connection:
        existing = connection.execute(
            select(bindings).where(bindings.c.module_key == module_key)
        ).first()
        if existing is None:
            raise ValueError("模块绑定不存在")
        connection.execute(bindings.delete().where(bindings.c.module_key == module_key))
    return {"module_key": module_key, "deleted": True}


def delete_llm_channel(engine: Engine, channel_key: str) -> dict:
    providers = metadata.tables["llm_providers"]
    channels = metadata.tables["llm_channels"]
    models = metadata.tables["llm_models"]
    bindings = metadata.tables["llm_module_bindings"]
    with engine.begin() as connection:
        channel = _fetch_channel(connection, channel_key)
        if channel is None:
            raise ValueError("渠道不存在")
        connection.execute(
            bindings.delete().where(bindings.c.llm_channel_id == channel.llm_channel_id)
        )
        connection.execute(
            models.delete().where(models.c.llm_channel_id == channel.llm_channel_id)
        )
        connection.execute(
            channels.delete().where(channels.c.channel_key == channel_key)
        )
        connection.execute(
            providers.delete().where(providers.c.llm_provider_id == channel.llm_provider_id)
        )
    return {"channel_key": channel_key, "deleted": True}
