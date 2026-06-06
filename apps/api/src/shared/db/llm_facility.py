from sqlalchemy import Boolean, Column, DateTime, ForeignKey, Integer, String, Table

from src.shared.db.base import metadata
from src.shared.db.table_helpers import timestamp_columns


Table(
    "llm_providers",
    metadata,
    Column("llm_provider_id", String(64), primary_key=True),
    Column("provider_key", String(128), nullable=False, unique=True),
    Column("provider_type", String(64), nullable=False),
    Column("name", String(255), nullable=False),
    Column("base_url", String(512), nullable=False),
    Column("auth_secret_ref", String(255), nullable=False),
    Column("status", String(32), nullable=False),
    *timestamp_columns(),
)

Table(
    "llm_channels",
    metadata,
    Column("llm_channel_id", String(64), primary_key=True),
    Column("llm_provider_id", String(64), ForeignKey("llm_providers.llm_provider_id"), nullable=False),
    Column("channel_key", String(128), nullable=False, unique=True),
    Column("name", String(255), nullable=False),
    Column("max_concurrency", Integer, nullable=False),
    Column("timeout_ms", Integer, nullable=False),
    Column("is_enabled", Boolean, nullable=False),
    *timestamp_columns(),
)

Table(
    "llm_models",
    metadata,
    Column("llm_model_id", String(64), primary_key=True),
    Column("llm_channel_id", String(64), ForeignKey("llm_channels.llm_channel_id"), nullable=False),
    Column("provider_model_id", String(255), nullable=False),
    Column("display_name", String(255), nullable=False),
    Column("synced_at", DateTime(timezone=True), nullable=False),
)

Table(
    "llm_module_bindings",
    metadata,
    Column("llm_module_binding_id", String(64), primary_key=True),
    Column("module_key", String(128), nullable=False, unique=True),
    Column("llm_channel_id", String(64), ForeignKey("llm_channels.llm_channel_id"), nullable=False),
    Column("llm_model_id", String(64), ForeignKey("llm_models.llm_model_id"), nullable=False),
    Column("updated_at", DateTime(timezone=True), nullable=False),
)
