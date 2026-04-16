"""Unified global search table."""

from __future__ import annotations

from .helpers import composite_pk, project_id, table, text_col

global_index = table("global_index", text_col("source", nullable=False), text_col("source_ref", nullable=False), project_id(nullable=True), text_col("entity_type", nullable=False, default="''"), text_col("title", nullable=False, default="''"), text_col("body", nullable=False, default="''"), text_col("tags", nullable=False, default="''"), text_col("updated_at", nullable=False, default="''"), text_col("payload_json", nullable=False, default="'{}'"), composite_pk("source", "source_ref"))
