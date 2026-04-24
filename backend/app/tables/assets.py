"""Asset library tables."""

from __future__ import annotations

from .helpers import composite_pk, int_col, project_id, table, text_col

# ``assets`` is the unified store for all resource rows. As of P5 of the
# asset-library refactor it also absorbs ``archive_library`` — entity
# archives live here with ``asset_type='archive_entity'`` and use the
# extra columns below (entity_*, template_*, *_tier, *_json). Non-archive
# rows leave those columns NULL.
assets = table(
    "assets",
    text_col("asset_id", primary_key=True),
    project_id(nullable=True),
    text_col("scope", nullable=False),
    text_col("asset_type", nullable=False),
    text_col("category", nullable=False, default="''"),
    text_col("title", nullable=False),
    text_col("summary", nullable=False, default="''"),
    text_col("content", nullable=False, default="''"),
    text_col("payload_json", nullable=False, default="'{}'"),
    text_col("tags_json", nullable=False, default="'[]'"),
    text_col("source_kind", nullable=False, default="''"),
    text_col("source_ref", nullable=False, default="''"),
    int_col("enabled", nullable=False, default="1"),
    int_col("pinned", nullable=False, default="0"),
    int_col("word_count", nullable=False, default="0"),
    text_col("created_at", nullable=False),
    text_col("updated_at", nullable=False),
    # Archive-specific columns (nullable; populated only when
    # asset_type='archive_entity'). Added in migration 20260419_0002.
    text_col("entity_uuid"),
    text_col("entity_name"),
    text_col("entity_type"),
    text_col("agent_kind"),
    text_col("importance_tier"),
    text_col("recommended_importance_tier"),
    text_col("selected_importance_tier"),
    text_col("template_key"),
    text_col("template_version"),
    text_col("entity_role"),
    text_col("core_drive"),
    text_col("surface_mask"),
    text_col("hidden_tension"),
    text_col("relationship_summary"),
    text_col("agent_behavior_hint"),
    text_col("human_ai_relation_tag"),
    int_col("can_act_as_agent"),
    text_col("notable_risks_json"),
    text_col("template_sections_json"),
    text_col("template_payload_json"),
    text_col("template_metadata_json"),
    text_col("entity_id"),
    text_col("synced_at"),
)
asset_links = table("asset_links", project_id(nullable=True), text_col("src_asset_id", nullable=False), text_col("dst_asset_id", nullable=False), text_col("relation", nullable=False), text_col("created_at", nullable=False), composite_pk("src_asset_id", "dst_asset_id", "relation"))

# Persistent (source, entity_type) -> (category, lifecycle) mapping.
# entity_type = "*" marks the source-level fallback row used when a specific
# (source, entity_type) pair is absent. See unified_asset_view.classify().
classification_map = table(
    "classification_map",
    text_col("source", nullable=False),
    text_col("entity_type", nullable=False),
    text_col("category", nullable=False),
    text_col("lifecycle", nullable=False),
    composite_pk("source", "entity_type"),
)
