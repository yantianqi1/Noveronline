"""Archive library tables."""

from __future__ import annotations

from .helpers import float_col, int_col, project_id, table, text_col

archive_library = table(
    "archive_library",
    text_col("archive_id", primary_key=True), project_id(), text_col("project_name", nullable=False),
    text_col("entity_uuid", nullable=False), text_col("entity_name", nullable=False),
    text_col("entity_type", nullable=False), text_col("agent_kind", nullable=False, default="'generic'"),
    text_col("importance_tier", nullable=False), text_col("recommended_importance_tier", nullable=False, default="'supporting'"),
    text_col("selected_importance_tier", nullable=False, default="'supporting'"),
    text_col("template_key", nullable=False, default="'generic.supporting.v1'"),
    text_col("template_version", nullable=False, default="'v1'"), text_col("entity_role", nullable=False),
    text_col("core_drive", nullable=False), text_col("surface_mask", nullable=False),
    text_col("hidden_tension", nullable=False), text_col("relationship_summary", nullable=False),
    text_col("agent_behavior_hint", nullable=False), text_col("human_ai_relation_tag", nullable=False),
    int_col("can_act_as_agent", nullable=False, default="1"), text_col("notable_risks_json", nullable=False, default="'[]'"),
    text_col("template_sections_json", nullable=False, default="'[]'"),
    text_col("template_payload_json", nullable=False, default="'{}'"),
    text_col("template_metadata_json", nullable=False, default="'{}'"),
    text_col("synced_at", nullable=False),
)
archive_sources = table("archive_sources", project_id(), text_col("project_name", nullable=False), text_col("file_path", nullable=False), float_col("file_mtime", nullable=False), text_col("synced_at", nullable=False),)
archive_sources.append_constraint(__import__("sqlalchemy").PrimaryKeyConstraint("project_id"))
archive_agent_memory = table("archive_agent_memory", text_col("memory_id", primary_key=True), project_id(), text_col("archive_id", nullable=False), text_col("agent_id", nullable=False), text_col("memory_type", nullable=False), text_col("normalized_subject", nullable=False), text_col("summary", nullable=False), text_col("detail_json", nullable=False), text_col("source_kind", nullable=False), text_col("source_ref_id", nullable=False), float_col("salience", nullable=False, default="0"), text_col("memory_layer", nullable=False, default="'canon'"), text_col("status", nullable=False, default="'active'"), int_col("version", nullable=False, default="1"), text_col("parent_memory_id", nullable=False, default="''"), text_col("source_session_id", nullable=False, default="''"), text_col("source_branch_id", nullable=False, default="''"), text_col("evidence_json", nullable=False, default="'[]'"), text_col("adopted_at"), text_col("rejected_at"), text_col("created_at", nullable=False), text_col("updated_at", nullable=False))
archive_agent_memory_events = table("archive_agent_memory_events", text_col("event_id", primary_key=True), project_id(), text_col("memory_id", nullable=False), text_col("archive_id", nullable=False), text_col("normalized_subject", nullable=False), text_col("memory_type", nullable=False), text_col("event_type", nullable=False), text_col("memory_layer", nullable=False), text_col("status", nullable=False), int_col("version", nullable=False, default="1"), text_col("parent_memory_id", nullable=False, default="''"), text_col("source_session_id", nullable=False, default="''"), text_col("source_branch_id", nullable=False, default="''"), text_col("summary", nullable=False, default="''"), text_col("evidence_json", nullable=False, default="'[]'"), text_col("created_at", nullable=False))
