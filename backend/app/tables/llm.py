"""LLM facility tables."""

from __future__ import annotations

from .helpers import composite_pk, int_col, table, text_col

llm_channels = table("llm_channels", text_col("channel_key", primary_key=True), text_col("name", nullable=False), text_col("base_url", nullable=False), text_col("api_key", nullable=False), int_col("max_concurrency", nullable=False, default="4"), int_col("is_enabled", nullable=False, default="1"), text_col("created_at", nullable=False), text_col("updated_at", nullable=False), text_col("last_sync_at"), text_col("last_sync_status", nullable=False, default="'idle'"), text_col("last_sync_error"))
llm_models = table("llm_models", text_col("channel_key", nullable=False), text_col("model_id", nullable=False), text_col("owned_by"), text_col("fetched_at", nullable=False), text_col("raw_payload", nullable=False), composite_pk("channel_key", "model_id"))
llm_module_bindings = table("llm_module_bindings", text_col("module_key", primary_key=True), text_col("channel_key", nullable=False), text_col("model_id", nullable=False), text_col("updated_at", nullable=False))
writer_presets_global = table("writer_presets_global", text_col("preset_id", primary_key=True), text_col("project_id"), text_col("name", nullable=False), text_col("description", default="''"), text_col("system_prompt", nullable=False), int_col("is_default", default="0"), text_col("created_at", nullable=False), text_col("updated_at", nullable=False))
