from __future__ import annotations

import re
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
SCHEMA_PATH = ROOT / "infra" / "postgres" / "migrations" / "0001_core_saas.sql"


def _schema_sql() -> str:
    return SCHEMA_PATH.read_text(encoding="utf-8")


def _table_block(sql: str, table_name: str) -> str:
    match = re.search(
        rf"CREATE TABLE IF NOT EXISTS {table_name}\s*\((.*?)\);",
        sql,
        flags=re.IGNORECASE | re.DOTALL,
    )
    assert match, f"{table_name} table is missing"
    return match.group(1)


def test_core_saas_schema_declares_minimum_phase3_tables() -> None:
    sql = _schema_sql()
    for table_name in (
        "users",
        "user_sessions",
        "tenants",
        "tenant_memberships",
        "project_members",
        "projects",
        "audit_logs",
        "usage_events",
        "resource_locks",
        "workflow_runs",
        "workflow_events",
        "agent_traces",
        "agent_trace_events",
        "llm_channels",
        "llm_models",
        "llm_module_bindings",
        "llm_activity",
        "source_files",
        "project_text_artifacts",
        "text_segments",
        "reading_passes",
        "reading_segment_notes",
        "entities",
        "entity_aliases",
        "entity_labels",
        "entity_evidence",
        "relationships",
        "relationship_events",
        "character_events",
        "world_events",
        "plot_threads",
        "thread_lifecycle",
        "narrative_arcs",
        "volume_summaries",
        "world_rule_evidence",
        "consistency_notes",
        "segment_summaries",
        "seed_analysis_snapshots",
        "seed_ontology_snapshots",
        "seed_entity_resolution_snapshots",
        "project_readiness_snapshots",
        "assets",
        "archive_memories",
        "archive_memory_events",
        "global_search_index",
        "story_graph_snapshots",
        "story_graph_nodes",
        "story_graph_node_aliases",
        "story_graph_node_labels",
        "story_graph_edges",
        "story_graph_evidence",
        "story_graph_layouts",
        "story_graph_clusters",
        "worldline_sessions",
        "worldline_preparations",
        "worldline_prepared_agents",
        "worldline_variables",
        "worldline_events",
        "worldline_event_adoptions",
        "worldline_saved_paths",
        "character_interaction_sessions",
        "character_interaction_turns",
        "writer_runs",
        "writer_drafts",
        "manuscript_blocks",
    ):
        assert f"CREATE TABLE IF NOT EXISTS {table_name}" in sql


def test_tenant_business_tables_have_tenant_id_and_timestamps() -> None:
    sql = _schema_sql()
    for table_name in (
        "tenant_memberships",
        "project_members",
        "projects",
        "audit_logs",
        "usage_events",
        "resource_locks",
        "workflow_runs",
        "workflow_events",
        "agent_traces",
        "agent_trace_events",
        "llm_channels",
        "llm_models",
        "llm_module_bindings",
        "llm_activity",
        "source_files",
        "project_text_artifacts",
        "text_segments",
        "reading_passes",
        "reading_segment_notes",
        "entities",
        "entity_aliases",
        "entity_labels",
        "entity_evidence",
        "relationships",
        "relationship_events",
        "character_events",
        "world_events",
        "plot_threads",
        "thread_lifecycle",
        "narrative_arcs",
        "volume_summaries",
        "world_rule_evidence",
        "consistency_notes",
        "segment_summaries",
        "seed_analysis_snapshots",
        "seed_ontology_snapshots",
        "seed_entity_resolution_snapshots",
        "project_readiness_snapshots",
        "assets",
        "archive_memories",
        "archive_memory_events",
        "global_search_index",
        "story_graph_snapshots",
        "story_graph_nodes",
        "story_graph_node_aliases",
        "story_graph_node_labels",
        "story_graph_edges",
        "story_graph_evidence",
        "story_graph_layouts",
        "story_graph_clusters",
        "worldline_sessions",
        "worldline_preparations",
        "worldline_prepared_agents",
        "worldline_variables",
        "worldline_events",
        "worldline_event_adoptions",
        "worldline_saved_paths",
        "character_interaction_sessions",
        "character_interaction_turns",
        "writer_runs",
        "writer_drafts",
        "manuscript_blocks",
    ):
        table_sql = _table_block(sql, table_name)
        assert re.search(r"\btenant_id\s+UUID\b", table_sql, re.IGNORECASE)
        assert re.search(r"\bcreated_at\s+TIMESTAMPTZ\b", table_sql, re.IGNORECASE)

    for table_name in (
        "project_members",
        "projects",
        "workflow_runs",
        "workflow_events",
        "agent_traces",
        "llm_module_bindings",
        "llm_activity",
        "source_files",
        "project_text_artifacts",
        "text_segments",
        "reading_passes",
        "reading_segment_notes",
        "entities",
        "entity_aliases",
        "entity_labels",
        "entity_evidence",
        "relationships",
        "relationship_events",
        "character_events",
        "world_events",
        "plot_threads",
        "thread_lifecycle",
        "narrative_arcs",
        "volume_summaries",
        "world_rule_evidence",
        "consistency_notes",
        "segment_summaries",
        "seed_analysis_snapshots",
        "seed_ontology_snapshots",
        "seed_entity_resolution_snapshots",
        "project_readiness_snapshots",
        "assets",
        "archive_memories",
        "archive_memory_events",
        "global_search_index",
        "story_graph_snapshots",
        "story_graph_nodes",
        "story_graph_node_aliases",
        "story_graph_node_labels",
        "story_graph_edges",
        "story_graph_evidence",
        "story_graph_layouts",
        "story_graph_clusters",
        "worldline_sessions",
        "worldline_preparations",
        "worldline_prepared_agents",
        "worldline_variables",
        "worldline_events",
        "worldline_event_adoptions",
        "worldline_saved_paths",
        "character_interaction_sessions",
        "character_interaction_turns",
        "writer_runs",
        "writer_drafts",
        "manuscript_blocks",
    ):
        table_sql = _table_block(sql, table_name)
        assert re.search(r"\bproject_id\s+UUID\b", table_sql, re.IGNORECASE)


def test_llm_facility_schema_keeps_keys_encrypted_and_activity_queryable() -> None:
    sql = _schema_sql()

    channels_sql = _table_block(sql, "llm_channels")
    assert "encrypted_api_key" in channels_sql
    assert not re.search(r"\bapi_key\s+TEXT\b", channels_sql, re.IGNORECASE)
    assert "max_concurrency" in channels_sql

    bindings_sql = _table_block(sql, "llm_module_bindings")
    assert re.search(r"\bmodule_key\s+TEXT\b", bindings_sql, re.IGNORECASE)
    assert re.search(r"\bchannel_id\s+UUID\b", bindings_sql, re.IGNORECASE)
    assert re.search(r"\bmodel_id\s+TEXT\b", bindings_sql, re.IGNORECASE)
    assert "settings_jsonb" in bindings_sql

    activity_sql = _table_block(sql, "llm_activity")
    for column in ("run_id", "module_key", "channel_id", "model_id", "status"):
        assert column in activity_sql

    assert "idx_llm_activity_tenant_project_run" in sql


def test_source_file_schema_supports_seed_upload_admission_without_object_credentials() -> None:
    sql = _schema_sql()

    source_files_sql = _table_block(sql, "source_files")
    for column in (
        "file_id",
        "project_id",
        "upload_id",
        "object_key",
        "filename",
        "mime_type",
        "size_bytes",
        "sha256",
        "purpose",
        "parse_status",
        "created_by",
    ):
        assert column in source_files_sql
    assert "'uploaded'" in source_files_sql
    assert not re.search(r"\bapi_key\s+TEXT\b", source_files_sql, re.IGNORECASE)
    assert "presigned" not in source_files_sql.lower()
    assert "idx_source_files_tenant_project" in sql
    assert "idx_source_files_upload" in sql

    text_artifacts_sql = _table_block(sql, "project_text_artifacts")
    for column in ("artifact_id", "artifact_type", "object_key", "char_count", "line_count", "sha256"):
        assert column in text_artifacts_sql
    assert "UNIQUE (tenant_id, project_id, run_id, artifact_type, object_key)" in text_artifacts_sql
    assert "idx_project_text_artifacts_tenant_project" in sql


def test_seed_parse_segment_upsert_indexes_are_backfilled_for_existing_tables() -> None:
    sql = _schema_sql()

    assert (
        "CREATE UNIQUE INDEX idx_project_text_artifacts_upsert_unique\n"
        "    ON project_text_artifacts (tenant_id, project_id, run_id, artifact_type, object_key)"
        in sql
    )
    assert (
        "CREATE UNIQUE INDEX idx_text_segments_upsert_unique\n"
        "    ON text_segments (tenant_id, project_id, run_id, segment_order)"
        in sql
    )


def test_asset_search_schema_supports_seed_projection() -> None:
    sql = _schema_sql()

    assets_sql = _table_block(sql, "assets")
    for column in (
        "asset_id",
        "project_id",
        "scope",
        "asset_type",
        "category",
        "lifecycle",
        "title",
        "summary",
        "content_text",
        "payload_jsonb",
        "tags_jsonb",
        "source_kind",
        "source_ref",
        "enabled",
        "pinned",
    ):
        assert column in assets_sql
    assert "UNIQUE (tenant_id, project_id, source_kind, source_ref, asset_type, title)" in assets_sql
    assert "idx_assets_tenant_project_type" in sql
    assert "idx_assets_tenant_project_source" in sql

    search_sql = _table_block(sql, "global_search_index")
    for column in (
        "search_document_id",
        "source",
        "source_ref",
        "project_id",
        "entity_type",
        "title",
        "body",
        "tags_jsonb",
        "payload_jsonb",
    ):
        assert column in search_sql
    assert "UNIQUE (tenant_id, project_id, source, source_ref)" in search_sql
    assert "idx_global_search_index_tenant_project" in sql


def test_story_graph_schema_supports_snapshot_nodes_edges_and_evidence() -> None:
    sql = _schema_sql()

    snapshots_sql = _table_block(sql, "story_graph_snapshots")
    for column in (
        "graph_id",
        "project_id",
        "version",
        "status",
        "build_run_id",
        "source_version_hash",
        "node_count",
        "edge_count",
    ):
        assert column in snapshots_sql
    assert "UNIQUE (tenant_id, project_id, version)" in snapshots_sql
    assert "idx_story_graph_snapshots_current" in sql

    nodes_sql = _table_block(sql, "story_graph_nodes")
    for column in (
        "graph_id",
        "node_id",
        "canonical_entity_id",
        "node_type",
        "title",
        "summary",
        "lifecycle",
        "importance",
        "cluster_id",
        "attributes_jsonb",
        "evidence_count",
    ):
        assert column in nodes_sql
    assert "idx_story_graph_nodes_tenant_project_graph" in sql

    aliases_sql = _table_block(sql, "story_graph_node_aliases")
    for column in (
        "alias_id",
        "project_id",
        "graph_id",
        "node_id",
        "alias",
        "source_type",
        "confidence",
    ):
        assert column in aliases_sql
    assert "UNIQUE (tenant_id, project_id, graph_id, node_id, alias)" in aliases_sql
    assert "idx_story_graph_node_aliases_node" in sql

    labels_sql = _table_block(sql, "story_graph_node_labels")
    for column in (
        "label_id",
        "project_id",
        "graph_id",
        "node_id",
        "label",
        "label_type",
        "confidence",
    ):
        assert column in labels_sql
    assert "UNIQUE (tenant_id, project_id, graph_id, node_id, label_type, label)" in labels_sql
    assert "idx_story_graph_node_labels_node" in sql

    edges_sql = _table_block(sql, "story_graph_edges")
    for column in (
        "graph_id",
        "edge_id",
        "source_node_id",
        "target_node_id",
        "edge_type",
        "label",
        "summary",
        "weight",
        "lifecycle",
        "attributes_jsonb",
        "evidence_count",
    ):
        assert column in edges_sql
    assert "idx_story_graph_edges_tenant_project_graph" in sql

    evidence_sql = _table_block(sql, "story_graph_evidence")
    for column in (
        "graph_id",
        "evidence_id",
        "owner_type",
        "owner_id",
        "source_type",
        "source_id",
        "chapter_id",
        "segment_id",
        "snippet",
        "confidence",
    ):
        assert column in evidence_sql

    for table_name in (
        "story_graph_snapshots",
        "story_graph_nodes",
        "story_graph_node_aliases",
        "story_graph_node_labels",
        "story_graph_edges",
        "story_graph_evidence",
        "story_graph_layouts",
        "story_graph_clusters",
    ):
        assert f"ALTER TABLE {table_name} ENABLE ROW LEVEL SECURITY" in sql
        assert f"CREATE POLICY tenant_isolation_{table_name}" in sql
        assert f"GRANT SELECT, INSERT, UPDATE, DELETE ON {table_name} TO mirofish_app" in sql


def test_worldline_saved_paths_schema_supports_writer_picker_without_private_payloads() -> None:
    sql = _schema_sql()
    paths_sql = _table_block(sql, "worldline_saved_paths")

    for column in (
        "path_id",
        "session_id",
        "project_id",
        "title",
        "summary",
        "lifecycle",
        "selected_event_ids_jsonb",
        "writer_instruction",
        "created_by",
        "created_at",
        "updated_at",
    ):
        assert column in paths_sql

    for forbidden in (
        "body_text",
        "content_text",
        "prompt",
        "response",
        "api_key",
        "encrypted_api_key",
        "credential_ref",
    ):
        assert forbidden not in paths_sql

    assert "idx_worldline_saved_paths_tenant_project" in sql
    assert "idx_worldline_saved_paths_session" in sql
    assert "ALTER TABLE worldline_saved_paths ENABLE ROW LEVEL SECURITY" in sql
    assert "ALTER TABLE worldline_saved_paths FORCE ROW LEVEL SECURITY" in sql
    assert "CREATE POLICY tenant_isolation_worldline_saved_paths" in sql
    assert "GRANT SELECT, INSERT, UPDATE, DELETE ON worldline_saved_paths TO mirofish_app" in sql


def test_character_console_schema_supports_metadata_only_interactions_and_turns() -> None:
    sql = _schema_sql()
    sessions_sql = _table_block(sql, "character_interaction_sessions")
    turns_sql = _table_block(sql, "character_interaction_turns")

    for column in (
        "interaction_id",
        "project_id",
        "worldline_session_id",
        "anchor_type",
        "anchor_id",
        "pov_agent_id",
        "mode",
        "status",
        "title",
        "summary",
        "metadata_jsonb",
        "created_by",
        "created_at",
        "updated_at",
    ):
        assert column in sessions_sql

    for column in (
        "turn_id",
        "interaction_id",
        "project_id",
        "turn_order",
        "actor_type",
        "actor_id",
        "turn_kind",
        "summary",
        "action_jsonb",
        "world_state_delta_jsonb",
        "trace_id",
        "created_by",
        "created_at",
    ):
        assert column in turns_sql

    assert (
        "FOREIGN KEY (tenant_id, project_id, worldline_session_id) REFERENCES worldline_sessions(tenant_id, project_id, session_id) ON DELETE SET NULL (worldline_session_id)"
        in sessions_sql
    )
    assert "worldline_sessions(session_id)" not in sessions_sql
    assert (
        "FOREIGN KEY (tenant_id, project_id, interaction_id) REFERENCES character_interaction_sessions(tenant_id, project_id, interaction_id) ON DELETE CASCADE"
        in turns_sql
    )
    assert "UNIQUE (tenant_id, project_id, interaction_id)" in sessions_sql
    assert "UNIQUE (tenant_id, project_id, interaction_id, turn_order)" in turns_sql
    assert (
        "CHECK (anchor_type IN ('', 'worldline_session', 'worldline_event', 'saved_path', 'chapter', 'scene', 'graph_node', 'plot_thread'))"
        in sessions_sql
    )
    assert "CHECK (mode IN ('first_person', 'director_assisted', 'dialogue', 'replay'))" in sessions_sql
    assert "CHECK (actor_type IN ('user', 'agent', 'director', 'system'))" in turns_sql
    assert (
        "CHECK (turn_kind IN ('action', 'dialogue', 'thought', 'director_note', 'system_note'))"
        in turns_sql
    )
    assert "director_feedback" not in turns_sql

    for table_sql in (sessions_sql, turns_sql):
        for forbidden in (
            "input_text",
            "output_text",
            "body_text",
            "content_text",
            "prompt",
            "response",
            "api_key",
            "encrypted_api_key",
            "credential_ref",
            "manuscript",
            "draft",
        ):
            assert forbidden not in table_sql

    for table_name in ("character_interaction_sessions", "character_interaction_turns"):
        assert f"ALTER TABLE {table_name} ENABLE ROW LEVEL SECURITY" in sql
        assert f"ALTER TABLE {table_name} FORCE ROW LEVEL SECURITY" in sql
        assert f"CREATE POLICY tenant_isolation_{table_name}" in sql
        assert f"GRANT SELECT, INSERT, UPDATE, DELETE ON {table_name} TO mirofish_app" in sql

    assert "idx_character_interaction_sessions_project" in sql
    assert "idx_character_interaction_sessions_worldline" in sql
    assert "idx_character_interaction_turns_interaction" in sql


def test_worldline_sessions_schema_supports_session_admission_without_private_payloads() -> None:
    sql = _schema_sql()
    sessions_sql = _table_block(sql, "worldline_sessions")

    for column in (
        "session_id",
        "project_id",
        "run_id",
        "status",
        "lifecycle",
        "goal_summary",
        "anchor_path_id",
        "created_by",
        "created_at",
        "updated_at",
    ):
        assert column in sessions_sql

    assert "workflow_runs(run_id)" in sessions_sql
    assert "UNIQUE (tenant_id, project_id, session_id)" in sessions_sql

    for forbidden in (
        "body_text",
        "content_text",
        "prompt",
        "response",
        "api_key",
        "encrypted_api_key",
        "credential_ref",
        "manuscript",
        "draft",
    ):
        assert forbidden not in sessions_sql

    assert "idx_worldline_sessions_tenant_project" in sql
    assert "idx_worldline_sessions_run" in sql
    assert "ALTER TABLE worldline_sessions ENABLE ROW LEVEL SECURITY" in sql
    assert "ALTER TABLE worldline_sessions FORCE ROW LEVEL SECURITY" in sql
    assert "CREATE POLICY tenant_isolation_worldline_sessions" in sql
    assert "GRANT SELECT, INSERT, UPDATE, DELETE ON worldline_sessions TO mirofish_app" in sql


def test_worldline_variables_schema_supports_metadata_only_injection() -> None:
    sql = _schema_sql()
    variables_sql = _table_block(sql, "worldline_variables")

    for column in (
        "variable_id",
        "session_id",
        "project_id",
        "name",
        "description",
        "impact_axis",
        "locked",
        "source",
        "created_by",
        "created_at",
        "updated_at",
    ):
        assert column in variables_sql

    assert "worldline_sessions(session_id)" in variables_sql
    assert "UNIQUE (tenant_id, project_id, session_id, variable_id)" in variables_sql

    for forbidden in (
        "body_text",
        "content_text",
        "prompt",
        "response",
        "api_key",
        "encrypted_api_key",
        "credential_ref",
        "manuscript",
        "draft",
    ):
        assert forbidden not in variables_sql

    assert "idx_worldline_variables_session" in sql
    assert "idx_worldline_variables_project" in sql
    assert "ALTER TABLE worldline_variables ENABLE ROW LEVEL SECURITY" in sql
    assert "ALTER TABLE worldline_variables FORCE ROW LEVEL SECURITY" in sql
    assert "CREATE POLICY tenant_isolation_worldline_variables" in sql
    assert "GRANT SELECT, INSERT, UPDATE, DELETE ON worldline_variables TO mirofish_app" in sql


def test_worldline_events_schema_supports_metadata_only_candidate_read_side() -> None:
    sql = _schema_sql()
    events_sql = _table_block(sql, "worldline_events")

    for column in (
        "event_id",
        "session_id",
        "project_id",
        "step",
        "title",
        "summary",
        "kind",
        "status",
        "lifecycle",
        "confidence",
        "involved_agent_ids_jsonb",
        "state_changes_jsonb",
        "source_run_id",
        "created_by",
        "created_at",
        "updated_at",
    ):
        assert column in events_sql

    assert "worldline_sessions(session_id)" in events_sql
    assert "UNIQUE (tenant_id, project_id, session_id, event_id)" in events_sql
    assert "CHECK (status IN ('candidate', 'canon', 'rejected'))" in events_sql

    for forbidden in (
        "body_text",
        "content_text",
        "prompt",
        "response",
        "api_key",
        "encrypted_api_key",
        "credential_ref",
        "manuscript",
        "draft",
    ):
        assert forbidden not in events_sql

    assert "idx_worldline_events_session_status" in sql
    assert "idx_worldline_events_project" in sql
    assert "ALTER TABLE worldline_events ENABLE ROW LEVEL SECURITY" in sql
    assert "ALTER TABLE worldline_events FORCE ROW LEVEL SECURITY" in sql
    assert "CREATE POLICY tenant_isolation_worldline_events" in sql
    assert "GRANT SELECT, INSERT, UPDATE, DELETE ON worldline_events TO mirofish_app" in sql


def test_worldline_event_adoptions_schema_supports_explicit_metadata_only_adoption() -> None:
    sql = _schema_sql()
    adoptions_sql = _table_block(sql, "worldline_event_adoptions")

    for column in (
        "adoption_id",
        "event_id",
        "session_id",
        "project_id",
        "from_status",
        "to_status",
        "note",
        "adopted_by",
        "created_at",
    ):
        assert column in adoptions_sql

    assert "worldline_events(event_id)" in adoptions_sql
    assert "worldline_sessions(session_id)" in adoptions_sql
    assert "CHECK (from_status IN ('candidate'))" in adoptions_sql
    assert "CHECK (to_status IN ('canon'))" in adoptions_sql

    for forbidden in (
        "body_text",
        "content_text",
        "prompt",
        "response",
        "api_key",
        "encrypted_api_key",
        "credential_ref",
        "manuscript",
        "draft",
    ):
        assert forbidden not in adoptions_sql

    assert "idx_worldline_event_adoptions_event" in sql
    assert "idx_worldline_event_adoptions_session" in sql
    assert "ALTER TABLE worldline_event_adoptions ENABLE ROW LEVEL SECURITY" in sql
    assert "ALTER TABLE worldline_event_adoptions FORCE ROW LEVEL SECURITY" in sql
    assert "CREATE POLICY tenant_isolation_worldline_event_adoptions" in sql
    assert "GRANT SELECT, INSERT, UPDATE, DELETE ON worldline_event_adoptions TO mirofish_app" in sql


def test_seed_canon_schema_supports_segments_and_reading_notes() -> None:
    sql = _schema_sql()

    segments_sql = _table_block(sql, "text_segments")
    for column in (
        "segment_id",
        "project_id",
        "run_id",
        "source_file_id",
        "segment_order",
        "chapter_guess",
        "title_guess",
        "start_offset",
        "end_offset",
        "content_excerpt",
        "object_key",
        "summary",
        "metadata_jsonb",
    ):
        assert column in segments_sql
    assert "workflow_runs(run_id)" in segments_sql
    assert "source_files(file_id)" in segments_sql
    assert "idx_text_segments_tenant_project_run_order" in sql
    assert "idx_text_segments_source_file_order" in sql

    passes_sql = _table_block(sql, "reading_passes")
    for column in (
        "pass_id",
        "project_id",
        "run_id",
        "pass_type",
        "status",
        "module_key",
        "model_id",
        "started_at",
        "completed_at",
        "metadata_jsonb",
    ):
        assert column in passes_sql
    assert "workflow_runs(run_id)" in passes_sql
    assert "idx_reading_passes_tenant_project_run" in sql

    notes_sql = _table_block(sql, "reading_segment_notes")
    for column in (
        "note_id",
        "project_id",
        "run_id",
        "segment_id",
        "pass_id",
        "payload_jsonb",
        "summary",
        "created_at",
    ):
        assert column in notes_sql
    assert "text_segments(segment_id)" in notes_sql
    assert "reading_passes(pass_id)" in notes_sql
    assert "idx_reading_segment_notes_tenant_run_segment" in sql
    assert "idx_reading_segment_notes_pass" in sql


def test_seed_canon_schema_supports_runtime_fact_persistence() -> None:
    sql = _schema_sql()

    entities_sql = _table_block(sql, "entities")
    for column in (
        "entity_id",
        "project_id",
        "source_run_id",
        "canonical_name",
        "entity_type",
        "importance",
        "state_summary",
        "first_seen_segment_id",
        "metadata_jsonb",
    ):
        assert column in entities_sql
    assert "workflow_runs(run_id)" in entities_sql
    assert "text_segments(segment_id)" in entities_sql
    assert "UNIQUE (tenant_id, project_id, canonical_name)" in entities_sql

    aliases_sql = _table_block(sql, "entity_aliases")
    for column in ("alias_id", "project_id", "entity_id", "alias"):
        assert column in aliases_sql
    assert "entities(entity_id)" in aliases_sql
    assert "UNIQUE (tenant_id, entity_id, alias)" in aliases_sql

    labels_sql = _table_block(sql, "entity_labels")
    for column in (
        "label_id",
        "project_id",
        "entity_id",
        "run_id",
        "segment_id",
        "label",
        "label_type",
        "source_kind",
        "metadata_jsonb",
    ):
        assert column in labels_sql
    assert "entities(entity_id)" in labels_sql
    assert "workflow_runs(run_id)" in labels_sql
    assert "text_segments(segment_id)" in labels_sql
    assert "UNIQUE (tenant_id, entity_id, run_id, segment_id, label, source_kind)" in labels_sql

    evidence_sql = _table_block(sql, "entity_evidence")
    for column in ("evidence_id", "project_id", "entity_id", "run_id", "segment_id", "evidence_text", "source_kind"):
        assert column in evidence_sql
    assert "workflow_runs(run_id)" in evidence_sql
    assert "text_segments(segment_id)" in evidence_sql

    relationships_sql = _table_block(sql, "relationships")
    for column in (
        "relationship_id",
        "project_id",
        "source_entity_name",
        "target_entity_name",
        "relationship_type",
        "summary",
        "source_run_id",
        "first_seen_segment_id",
        "evidence_text",
    ):
        assert column in relationships_sql
    assert "workflow_runs(run_id)" in relationships_sql
    assert "text_segments(segment_id)" in relationships_sql
    assert "UNIQUE (tenant_id, project_id, source_entity_name, target_entity_name, relationship_type)" in relationships_sql

    relationship_events_sql = _table_block(sql, "relationship_events")
    for column in (
        "relationship_event_id",
        "project_id",
        "run_id",
        "segment_id",
        "source_entity_name",
        "target_entity_name",
        "relationship_type",
        "event_summary",
        "evidence_text",
    ):
        assert column in relationship_events_sql
    assert "workflow_runs(run_id)" in relationship_events_sql
    assert "text_segments(segment_id)" in relationship_events_sql
    assert "UNIQUE (tenant_id, project_id, run_id, segment_id, source_entity_name, target_entity_name, relationship_type, event_summary)" in relationship_events_sql

    character_events_sql = _table_block(sql, "character_events")
    for column in (
        "character_event_id",
        "project_id",
        "run_id",
        "segment_id",
        "entity_name",
        "event_summary",
        "event_kind",
        "evidence_text",
    ):
        assert column in character_events_sql
    assert "workflow_runs(run_id)" in character_events_sql
    assert "text_segments(segment_id)" in character_events_sql
    assert "UNIQUE (tenant_id, project_id, run_id, segment_id, entity_name, event_summary)" in character_events_sql

    world_events_sql = _table_block(sql, "world_events")
    for column in (
        "world_event_id",
        "project_id",
        "run_id",
        "segment_id",
        "event_summary",
        "event_kind",
        "evidence_text",
    ):
        assert column in world_events_sql
    assert "workflow_runs(run_id)" in world_events_sql
    assert "text_segments(segment_id)" in world_events_sql
    assert "UNIQUE (tenant_id, project_id, run_id, segment_id, event_summary)" in world_events_sql

    threads_sql = _table_block(sql, "plot_threads")
    for column in (
        "thread_id",
        "project_id",
        "source_run_id",
        "title",
        "status",
        "summary",
        "first_seen_segment_id",
        "evidence_text",
    ):
        assert column in threads_sql
    assert "workflow_runs(run_id)" in threads_sql
    assert "text_segments(segment_id)" in threads_sql
    assert "UNIQUE (tenant_id, project_id, title)" in threads_sql

    thread_lifecycle_sql = _table_block(sql, "thread_lifecycle")
    for column in (
        "thread_lifecycle_id",
        "project_id",
        "thread_id",
        "run_id",
        "segment_id",
        "status",
        "summary",
        "evidence_text",
    ):
        assert column in thread_lifecycle_sql
    assert "plot_threads(thread_id)" in thread_lifecycle_sql
    assert "workflow_runs(run_id)" in thread_lifecycle_sql
    assert "text_segments(segment_id)" in thread_lifecycle_sql
    assert "UNIQUE (tenant_id, project_id, thread_id, run_id, segment_id, status)" in thread_lifecycle_sql

    narrative_arcs_sql = _table_block(sql, "narrative_arcs")
    for column in (
        "narrative_arc_id",
        "project_id",
        "run_id",
        "segment_id",
        "title",
        "arc_type",
        "summary",
        "evidence_text",
    ):
        assert column in narrative_arcs_sql
    assert "workflow_runs(run_id)" in narrative_arcs_sql
    assert "text_segments(segment_id)" in narrative_arcs_sql
    assert "UNIQUE (tenant_id, project_id, run_id, segment_id, title)" in narrative_arcs_sql

    volume_summaries_sql = _table_block(sql, "volume_summaries")
    for column in (
        "volume_summary_id",
        "project_id",
        "run_id",
        "segment_id",
        "volume_key",
        "title",
        "summary",
        "evidence_text",
        "source_kind",
        "metadata_jsonb",
    ):
        assert column in volume_summaries_sql
    assert "workflow_runs(run_id)" in volume_summaries_sql
    assert "text_segments(segment_id)" in volume_summaries_sql
    assert "UNIQUE (tenant_id, project_id, run_id, segment_id, volume_key, source_kind)" in volume_summaries_sql

    rules_sql = _table_block(sql, "world_rule_evidence")
    for column in ("rule_evidence_id", "project_id", "run_id", "segment_id", "rule_text", "evidence_text", "category"):
        assert column in rules_sql
    assert "workflow_runs(run_id)" in rules_sql
    assert "text_segments(segment_id)" in rules_sql
    assert "UNIQUE (tenant_id, project_id, run_id, segment_id, rule_text)" in rules_sql

    consistency_sql = _table_block(sql, "consistency_notes")
    for column in (
        "consistency_note_id",
        "project_id",
        "run_id",
        "segment_id",
        "note_type",
        "severity",
        "summary",
        "evidence_text",
    ):
        assert column in consistency_sql
    assert "workflow_runs(run_id)" in consistency_sql
    assert "text_segments(segment_id)" in consistency_sql
    assert "UNIQUE (tenant_id, project_id, run_id, segment_id, note_type, summary)" in consistency_sql

    segment_summaries_sql = _table_block(sql, "segment_summaries")
    for column in (
        "segment_summary_id",
        "project_id",
        "run_id",
        "segment_id",
        "summary",
        "source_kind",
        "metadata_jsonb",
    ):
        assert column in segment_summaries_sql
    assert "workflow_runs(run_id)" in segment_summaries_sql
    assert "text_segments(segment_id)" in segment_summaries_sql
    assert "UNIQUE (tenant_id, project_id, run_id, segment_id, source_kind)" in segment_summaries_sql

    seed_analysis_sql = _table_block(sql, "seed_analysis_snapshots")
    for column in (
        "seed_analysis_snapshot_id",
        "project_id",
        "run_id",
        "module_key",
        "model_id",
        "analysis_jsonb",
        "summary_count",
        "segment_count",
        "metadata_jsonb",
    ):
        assert column in seed_analysis_sql
    assert "workflow_runs(run_id)" in seed_analysis_sql
    assert "UNIQUE (tenant_id, project_id, run_id, module_key)" in seed_analysis_sql

    seed_ontology_sql = _table_block(sql, "seed_ontology_snapshots")
    for column in (
        "seed_ontology_snapshot_id",
        "project_id",
        "run_id",
        "module_key",
        "model_id",
        "ontology_jsonb",
        "entity_type_count",
        "relationship_type_count",
        "world_rule_type_count",
        "metadata_jsonb",
    ):
        assert column in seed_ontology_sql
    assert "workflow_runs(run_id)" in seed_ontology_sql
    assert "UNIQUE (tenant_id, project_id, run_id, module_key)" in seed_ontology_sql
    assert "prompt" not in seed_ontology_sql.lower()
    assert "api_key" not in seed_ontology_sql.lower()
    assert "credential_ref" not in seed_ontology_sql.lower()

    seed_entity_resolution_sql = _table_block(sql, "seed_entity_resolution_snapshots")
    for column in (
        "seed_entity_resolution_snapshot_id",
        "project_id",
        "run_id",
        "module_key",
        "model_id",
        "resolution_jsonb",
        "merged_entity_count",
        "alias_count",
        "conflict_count",
        "metadata_jsonb",
    ):
        assert column in seed_entity_resolution_sql
    assert "workflow_runs(run_id)" in seed_entity_resolution_sql
    assert "UNIQUE (tenant_id, project_id, run_id, module_key)" in seed_entity_resolution_sql
    assert "prompt" not in seed_entity_resolution_sql.lower()
    assert "api_key" not in seed_entity_resolution_sql.lower()
    assert "credential_ref" not in seed_entity_resolution_sql.lower()

    readiness_sql = _table_block(sql, "project_readiness_snapshots")
    for column in (
        "project_readiness_snapshot_id",
        "project_id",
        "run_id",
        "ready_asset_count",
        "ready_entity_count",
        "ready_relationship_count",
        "ready_world_rule_count",
        "metadata_jsonb",
    ):
        assert column in readiness_sql
    assert "workflow_runs(run_id)" in readiness_sql
    assert "UNIQUE (tenant_id, project_id, run_id)" in readiness_sql
    assert "readiness_report" not in readiness_sql

    assert "idx_entities_tenant_project_name" in sql
    assert "idx_entity_labels_tenant_project_entity" in sql
    assert "idx_entity_evidence_tenant_project_entity" in sql
    assert "idx_relationships_tenant_project_source" in sql
    assert "idx_relationship_events_tenant_project_run" in sql
    assert "idx_character_events_tenant_project_run" in sql
    assert "idx_world_events_tenant_project_run" in sql
    assert "idx_plot_threads_tenant_project_status" in sql
    assert "idx_thread_lifecycle_tenant_project_run" in sql
    assert "idx_narrative_arcs_tenant_project_run" in sql
    assert "idx_volume_summaries_tenant_project_run" in sql
    assert "idx_world_rule_evidence_tenant_project_run" in sql
    assert "idx_consistency_notes_tenant_project_run" in sql
    assert "idx_segment_summaries_tenant_project_run" in sql
    assert "idx_seed_analysis_snapshots_tenant_project_run" in sql
    assert "idx_seed_ontology_snapshots_tenant_project_run" in sql
    assert "idx_project_readiness_snapshots_tenant_project_run" in sql


def test_agent_trace_schema_supports_redaction_and_run_queries() -> None:
    sql = _schema_sql()

    traces_sql = _table_block(sql, "agent_traces")
    for column in ("trace_id", "run_id", "project_id", "module_key", "agent_name", "status"):
        assert column in traces_sql

    events_sql = _table_block(sql, "agent_trace_events")
    for column in ("trace_id", "event_order", "event_type", "payload_jsonb", "redaction_level"):
        assert column in events_sql

    assert "idx_agent_traces_tenant_project_run" in sql
    assert "idx_agent_trace_events_trace_order" in sql


def test_user_sessions_schema_supports_server_side_session_revocation() -> None:
    sql = _schema_sql()

    sessions_sql = _table_block(sql, "user_sessions")
    for column in (
        "user_session_id",
        "user_id",
        "token_hash",
        "status",
        "expires_at",
        "revoked_at",
        "last_seen_at",
        "created_at",
        "updated_at",
    ):
        assert column in sessions_sql

    assert "token_hash TEXT NOT NULL UNIQUE" in sessions_sql
    assert "CHECK (status IN ('active', 'revoked', 'expired'))" in sessions_sql
    assert "REFERENCES users(user_id) ON DELETE CASCADE" in sessions_sql
    assert "idx_user_sessions_user_status" in sql
    assert "idx_user_sessions_token_hash" in sql
    assert "GRANT SELECT, INSERT, UPDATE, DELETE ON user_sessions TO mirofish_app" in sql

    forbidden = sessions_sql.lower()
    for field in (
        "api_key",
        "encrypted",
        "credential_ref",
        "object_key",
        "content_text",
        "draft",
        "manuscript",
        "prompt",
        "response",
        "session_token",
    ):
        assert field not in forbidden


def test_rls_is_enabled_for_tenant_scoped_tables() -> None:
    sql = _schema_sql()
    for table_name in (
        "tenant_memberships",
        "project_members",
        "projects",
        "audit_logs",
        "usage_events",
        "resource_locks",
        "workflow_runs",
        "workflow_events",
        "agent_traces",
        "agent_trace_events",
        "llm_channels",
        "llm_models",
        "llm_module_bindings",
        "llm_activity",
        "source_files",
        "project_text_artifacts",
        "text_segments",
        "reading_passes",
        "reading_segment_notes",
        "entities",
        "entity_aliases",
        "entity_labels",
        "entity_evidence",
        "relationships",
        "relationship_events",
        "character_events",
        "world_events",
        "plot_threads",
        "thread_lifecycle",
        "narrative_arcs",
        "volume_summaries",
        "world_rule_evidence",
        "consistency_notes",
        "segment_summaries",
        "seed_analysis_snapshots",
        "seed_ontology_snapshots",
        "project_readiness_snapshots",
        "assets",
        "global_search_index",
        "worldline_saved_paths",
        "worldline_variables",
        "worldline_events",
        "writer_runs",
        "writer_drafts",
        "manuscript_blocks",
    ):
        assert f"ALTER TABLE {table_name} ENABLE ROW LEVEL SECURITY;" in sql
        assert f"ALTER TABLE {table_name} FORCE ROW LEVEL SECURITY;" in sql
        assert f"CREATE POLICY tenant_isolation_{table_name}" in sql
        assert f"ON {table_name}" in sql


def test_rls_uses_transaction_scoped_tenant_context_without_bypass() -> None:
    sql = _schema_sql()
    assert "app.current_tenant_id" in sql
    assert "SET LOCAL app.current_tenant_id" in sql
    assert "NULLIF(current_setting('app.current_tenant_id', true), '')::UUID" in sql
    assert "CREATE ROLE mirofish_app NOLOGIN" in sql
    assert "GRANT SELECT, INSERT, UPDATE, DELETE ON ALL TABLES IN SCHEMA public TO mirofish_app" in sql
    assert "GRANT EXECUTE ON FUNCTION app_set_tenant_context(UUID, UUID, BOOLEAN) TO mirofish_app" in sql
    assert "DISABLE ROW LEVEL SECURITY" not in sql
    assert "BYPASSRLS" not in sql
