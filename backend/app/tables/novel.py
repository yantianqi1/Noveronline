"""Unified novel-writing tables."""

from __future__ import annotations

from sqlalchemy import UniqueConstraint

from .helpers import composite_pk, float_col, int_col, project_id, table, text_col

entities = table(
    "entities",
    text_col("entity_id", nullable=False), project_id(), text_col("name", nullable=False),
    text_col("entity_type", nullable=False), text_col("importance_tier", default="'minor'"),
    text_col("summary"), text_col("core_drive"), text_col("surface_mask"),
    text_col("hidden_tension"), text_col("profile_json", nullable=False, default="'{}'"),
    text_col("speech_style"), text_col("verbal_habits_json", default="'[]'"),
    text_col("example_quotes_json", default="'[]'"), text_col("personality_traits_json", default="'[]'"),
    text_col("values_text"), text_col("fears_text"), text_col("decision_pattern"),
    text_col("skills_json", default="'[]'"), text_col("limitations_json", default="'[]'"),
    text_col("resources_text"), text_col("knowledge_boundary_json", default="'{}'"),
    text_col("ultimate_goal"), text_col("current_objective"), text_col("mask_behavior"),
    text_col("emotional_baseline"), text_col("cognitive_biases_json", default="'[]'"),
    text_col("agent_behavior_hint"), text_col("relationship_summary_text"),
    text_col("notable_risks_json", default="'[]'"), text_col("created_at", nullable=False),
    text_col("updated_at", nullable=False), composite_pk("project_id", "entity_id"),
)
entity_aliases = table("entity_aliases", project_id(), text_col("alias", nullable=False), text_col("entity_id", nullable=False), composite_pk("project_id", "alias", "entity_id"))
entity_labels = table("entity_labels", project_id(), text_col("entity_id", nullable=False), text_col("label", nullable=False), composite_pk("project_id", "entity_id", "label"))
relationships = table(
    "relationships",
    text_col("relation_id", primary_key=True), project_id(), text_col("source_id", nullable=False),
    text_col("target_id", nullable=False), text_col("relation_type", nullable=False),
    text_col("description"), float_col("trust_level"), text_col("power_dynamic"),
    text_col("history"), text_col("conflict_trigger"), text_col("updated_at", nullable=False),
)
entity_evidence = table(
    "entity_evidence",
    text_col("evidence_id", primary_key=True), project_id(), text_col("owner_id", nullable=False),
    text_col("owner_type", nullable=False), text_col("chapter_id"), text_col("snippet", nullable=False),
    text_col("created_at", nullable=False),
)
chapter_content = table(
    "chapter_content",
    text_col("chapter_id", primary_key=True), project_id(), int_col("chapter_order", nullable=False),
    text_col("title", default="''"), text_col("content", nullable=False, default="''"),
    int_col("word_count", default="0"), text_col("status", default="'draft'"),
    text_col("created_at", nullable=False), text_col("updated_at", nullable=False),
    UniqueConstraint("project_id", "chapter_order"),
)
chapter_meta = table(
    "chapter_meta",
    text_col("chapter_id", primary_key=True), project_id(), text_col("summary", default="''"),
    text_col("outline_json", default="'[]'"), text_col("timeline_note", default="''"),
    text_col("open_threads_json", default="'[]'"), text_col("pov_character"),
    text_col("key_events_json", default="'[]'"), text_col("character_state_updates_json", default="'[]'"),
    text_col("relationship_updates_json", default="'[]'"), text_col("start_anchor", default="''"),
    text_col("end_anchor", default="''"), text_col("updated_at", nullable=False),
)
scenes = table(
    "scenes",
    text_col("scene_id", primary_key=True), project_id(), text_col("chapter_id", nullable=False),
    int_col("scene_order", nullable=False), text_col("title", default="''"),
    text_col("content", nullable=False, default="''"), int_col("word_count", default="0"),
    text_col("pov_entity_id"), text_col("location"), text_col("involved_entities_json", default="'[]'"),
    text_col("status", default="'draft'"), text_col("writing_brief_json"),
    text_col("created_at", nullable=False), text_col("updated_at", nullable=False),
    UniqueConstraint("chapter_id", "scene_order"),
)
sessions = table("sessions", text_col("session_id", primary_key=True), project_id(), text_col("session_type", nullable=False), text_col("title"), text_col("focus_question"), text_col("status", default="'running'"), text_col("config_json", default="'{}'"), text_col("created_at", nullable=False), text_col("updated_at", nullable=False))
worldline_branches = table("worldline_branches", project_id(), text_col("branch_id", nullable=False), text_col("session_id", nullable=False), text_col("title", nullable=False, default="''"), text_col("core_change", nullable=False, default="''"), text_col("narrative_value", default="''"), int_col("current_step", default="0"), text_col("status", default="'running'"), text_col("evolution_intensity", default="'medium'"), int_col("evolution_depth", default="3"), text_col("key_agents_json", default="'[]'"), text_col("expected_conflicts_json", default="'[]'"), text_col("actor_states_json", default="'{}'"), text_col("organization_states_json", default="'{}'"), text_col("relationship_states_json", default="'[]'"), text_col("created_at", nullable=False), text_col("updated_at", nullable=False), composite_pk("project_id", "session_id", "branch_id"))
agent_states = table("agent_states", text_col("state_id", primary_key=True), project_id(), text_col("session_id", nullable=False), text_col("branch_id", nullable=False, default="'main'"), text_col("entity_id", nullable=False), text_col("state_json", nullable=False), text_col("status", default="'active'"), int_col("version", default="1"), text_col("updated_at", nullable=False))
agent_memory = table("agent_memory", text_col("memory_id", primary_key=True), project_id(), text_col("session_id", nullable=False), text_col("branch_id", nullable=False, default="'main'"), text_col("entity_id", nullable=False), text_col("memory_type", nullable=False), text_col("summary", nullable=False), text_col("detail_json"), float_col("salience", default="0"), text_col("source_kind"), text_col("created_at", nullable=False))
world_events = table("world_events", text_col("event_id", primary_key=True), project_id(), text_col("session_id", nullable=False), text_col("branch_id", nullable=False, default="'main'"), int_col("step", nullable=False), text_col("title", nullable=False), text_col("summary", nullable=False), text_col("event_type"), text_col("driving_entities_json", default="'[]'"), text_col("state_changes_json", default="'[]'"), text_col("status", default="'canon'"), text_col("created_at", nullable=False))
plot_threads = table("plot_threads", text_col("thread_id", primary_key=True), project_id(), text_col("thread_key", nullable=False), text_col("status", nullable=False, default="'open'"), text_col("detail", nullable=False, default="''"), text_col("source_chapter"), text_col("created_at", nullable=False), text_col("updated_at", nullable=False))
narrative_arcs = table("narrative_arcs", text_col("arc_id", primary_key=True), project_id(), text_col("summary", nullable=False), text_col("covered_segments_json", default="'[]'"), text_col("created_at", nullable=False))
project_meta = table("project_meta", project_id(), text_col("narrative_phase"), int_col("total_segments", default="0"), text_col("updated_at", nullable=False), composite_pk("project_id"))
writer_presets = table("writer_presets", text_col("preset_id", primary_key=True), project_id(nullable=True), text_col("name", nullable=False), text_col("description", default="''"), text_col("system_prompt", nullable=False), int_col("is_default", default="0"), text_col("created_at", nullable=False), text_col("updated_at", nullable=False))
character_events = table("character_events", text_col("event_id", primary_key=True), project_id(), text_col("entity_id", nullable=False), text_col("segment_id", nullable=False, default="''"), int_col("chapter_order", default="0"), text_col("event_type", nullable=False, default="'action'"), text_col("summary", nullable=False), text_col("detail_json", default="'{}'"), text_col("created_at", nullable=False))
relationship_events = table("relationship_events", text_col("event_id", primary_key=True), project_id(), text_col("source_entity_id", nullable=False), text_col("target_entity_id", nullable=False), text_col("segment_id", nullable=False, default="''"), int_col("chapter_order", default="0"), text_col("relation_type", default="''"), text_col("previous_state", default="''"), text_col("new_state", default="''"), text_col("trigger_event", default="''"), text_col("emotional_shift", default="''"), text_col("power_shift", default="''"), text_col("evidence", default="''"), text_col("created_at", nullable=False))
thread_lifecycle = table("thread_lifecycle", text_col("lifecycle_id", primary_key=True), project_id(), text_col("thread_key", nullable=False), text_col("segment_id", nullable=False, default="''"), int_col("chapter_order", default="0"), text_col("status", nullable=False, default="'open'"), text_col("detail", default="''"), text_col("resolution_detail", default="''"), text_col("created_at", nullable=False))
world_rule_evidence = table("world_rule_evidence", text_col("evidence_id", primary_key=True), project_id(), text_col("fact_text", nullable=False), text_col("segment_id", nullable=False, default="''"), int_col("chapter_order", default="0"), text_col("evidence_snippet", default="''"), text_col("created_at", nullable=False))
consistency_notes = table("consistency_notes", text_col("note_id", primary_key=True), project_id(), text_col("segment_id", nullable=False, default="''"), int_col("chapter_order", default="0"), text_col("note_text", nullable=False), text_col("created_at", nullable=False))
volume_summaries = table("volume_summaries", text_col("volume_id", primary_key=True), project_id(), int_col("volume_order", nullable=False), text_col("summary", nullable=False), text_col("covered_arcs_json", default="'[]'"), text_col("created_at", nullable=False))
segment_summaries = table("segment_summaries", project_id(), text_col("segment_id", nullable=False), int_col("segment_order", nullable=False, default="0"), text_col("summary", nullable=False), text_col("created_at", nullable=False), composite_pk("project_id", "segment_id"))
outline_versions = table("outline_versions", text_col("version_id", primary_key=True), project_id(), text_col("chapter_id", nullable=False), text_col("outline_json", nullable=False), text_col("label", default="''"), text_col("created_at", nullable=False))
thread_entity_links = table("thread_entity_links", project_id(), text_col("thread_id", nullable=False), text_col("entity_id", nullable=False), text_col("role", default="'involved'"), text_col("created_at", nullable=False), composite_pk("project_id", "thread_id", "entity_id"))
rule_entity_links = table("rule_entity_links", project_id(), text_col("evidence_id", nullable=False), text_col("entity_id", nullable=False), text_col("relevance", default="'constrains'"), text_col("created_at", nullable=False), composite_pk("project_id", "evidence_id", "entity_id"))
book_plans = table(
    "book_plans",
    text_col("plan_id", primary_key=True), project_id(),
    text_col("title", default="''"),
    int_col("chapter_count", nullable=False, default="1"),
    int_col("per_chapter_word_target", nullable=False, default="3000"),
    int_col("word_tolerance_pct", nullable=False, default="10"),
    text_col("overall_direction", default="''"),
    text_col("global_brief", default="''"),
    int_col("start_chapter_order", nullable=False, default="1"),
    text_col("forbidden_lexicon_asset_ids", default="'[]'"),
    text_col("style_asset_ids", default="'[]'"),
    text_col("preset_id"),
    text_col("status", nullable=False, default="'draft'"),
    int_col("current_chapter_order", default="0"),
    text_col("last_stage", default="''"),
    text_col("outline_version_ids", default="'[]'"),
    text_col("chapter_ids", default="'[]'"),
    text_col("error_log", default="'[]'"),
    text_col("retrieval_summary", default="''"),
    text_col("created_at", nullable=False), text_col("updated_at", nullable=False),
)
