"""Asset library tables."""

from __future__ import annotations

from .helpers import composite_pk, int_col, project_id, table, text_col

assets = table("assets", text_col("asset_id", primary_key=True), project_id(nullable=True), text_col("scope", nullable=False), text_col("asset_type", nullable=False), text_col("category", nullable=False, default="''"), text_col("title", nullable=False), text_col("summary", nullable=False, default="''"), text_col("content", nullable=False, default="''"), text_col("payload_json", nullable=False, default="'{}'"), text_col("tags_json", nullable=False, default="'[]'"), text_col("source_kind", nullable=False, default="''"), text_col("source_ref", nullable=False, default="''"), int_col("enabled", nullable=False, default="1"), int_col("pinned", nullable=False, default="0"), int_col("word_count", nullable=False, default="0"), text_col("created_at", nullable=False), text_col("updated_at", nullable=False))
asset_links = table("asset_links", project_id(nullable=True), text_col("src_asset_id", nullable=False), text_col("dst_asset_id", nullable=False), text_col("relation", nullable=False), text_col("created_at", nullable=False), composite_pk("src_asset_id", "dst_asset_id", "relation"))
