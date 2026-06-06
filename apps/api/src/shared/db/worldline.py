from sqlalchemy import Boolean, Column, DateTime, ForeignKey, Integer, String, Table, Text

from src.shared.db.base import metadata
from src.shared.db.table_helpers import timestamp_columns


Table(
    "worldline_preparations",
    metadata,
    Column("prepare_id", String(64), primary_key=True),
    Column("project_id", String(64), ForeignKey("projects.project_id"), nullable=True),
    Column("status", String(32), nullable=False),
    Column("session_scope", String(64), nullable=False),
    Column("focus_question", Text, nullable=False),
    Column("started_session_id", String(64), nullable=True),
    *timestamp_columns(),
)

Table(
    "prepared_agent_dossiers",
    metadata,
    Column("prepared_agent_dossier_id", String(64), primary_key=True),
    Column("prepare_id", String(64), ForeignKey("worldline_preparations.prepare_id"), nullable=False),
    Column("agent_id", String(64), nullable=False),
    Column("agent_kind", String(64), nullable=False),
    Column("display_name", String(255), nullable=False),
    Column("template_key", String(128), nullable=True),
    Column("template_version", String(64), nullable=True),
    *timestamp_columns(),
)

Table(
    "worldline_sessions",
    metadata,
    Column("session_id", String(64), primary_key=True),
    Column("project_id", String(64), ForeignKey("projects.project_id"), nullable=True),
    Column("session_scope", String(64), nullable=False),
    Column("simulation_goal", Text, nullable=False),
    Column("focus_question", Text, nullable=False),
    Column("status", String(32), nullable=False),
    Column("created_from_prepare_run_id", String(64), nullable=True),
    *timestamp_columns(),
)

Table(
    "world_states",
    metadata,
    Column("world_state_id", String(64), primary_key=True),
    Column("session_id", String(64), ForeignKey("worldline_sessions.session_id"), nullable=False),
    Column("version_no", Integer, nullable=False),
    Column("is_current", Boolean, nullable=False),
    Column("created_at", DateTime(timezone=True), nullable=False),
)

Table(
    "timeline_events",
    metadata,
    Column("timeline_event_id", String(64), primary_key=True),
    Column("session_id", String(64), ForeignKey("worldline_sessions.session_id"), nullable=False),
    Column("world_state_id", String(64), ForeignKey("world_states.world_state_id"), nullable=False),
    Column("step_no", Integer, nullable=False),
    Column("event_type", String(64), nullable=False),
    Column("title", String(255), nullable=False),
    Column("summary", Text, nullable=False),
    Column("status", String(32), nullable=False),
    Column("created_at", DateTime(timezone=True), nullable=False),
)

Table(
    "session_agents",
    metadata,
    Column("session_agent_id", String(64), primary_key=True),
    Column("session_id", String(64), ForeignKey("worldline_sessions.session_id"), nullable=False),
    Column("agent_id", String(64), nullable=False),
    Column("archive_id", String(64), ForeignKey("archives.archive_id"), nullable=True),
    Column("entity_id", String(64), ForeignKey("entities.entity_id"), nullable=True),
    Column("agent_kind", String(64), nullable=False),
    Column("display_name", String(255), nullable=False),
    Column("role", String(64), nullable=True),
    Column("drive", Text, nullable=True),
    Column("tension", Text, nullable=True),
    Column("status", String(32), nullable=True),
    Column("summary", Text, nullable=True),
    Column("can_chat", Boolean, nullable=False, default=True),
    Column("can_act", Boolean, nullable=False, default=True),
    Column("state_json", Text, nullable=True),
    Column("state_source", String(64), nullable=True),
    Column("state_version", Integer, nullable=True),
    Column("source_ref", String(255), nullable=True),
    Column("last_action_at", DateTime(timezone=True), nullable=True),
    Column("last_dialogue_at", DateTime(timezone=True), nullable=True),
    *timestamp_columns(),
)

Table(
    "agent_actions",
    metadata,
    Column("action_id", String(64), primary_key=True),
    Column("session_id", String(64), ForeignKey("worldline_sessions.session_id"), nullable=False),
    Column("session_agent_id", String(64), ForeignKey("session_agents.session_agent_id"), nullable=False),
    Column("action", Text, nullable=False),
    Column("intent", Text, nullable=False, default=""),
    Column("target", String(255), nullable=False, default=""),
    Column("source", String(64), nullable=False, default=""),
    Column("status", String(32), nullable=False),
    Column("detail_json", Text, nullable=False, default="{}"),
    Column("queued_at", DateTime(timezone=True), nullable=False),
    Column("applied_at", DateTime(timezone=True), nullable=True),
    Column("discarded_at", DateTime(timezone=True), nullable=True),
)

Table(
    "agent_dialogues",
    metadata,
    Column("dialogue_id", String(64), primary_key=True),
    Column("session_id", String(64), ForeignKey("worldline_sessions.session_id"), nullable=False),
    Column("session_agent_id", String(64), ForeignKey("session_agents.session_agent_id"), nullable=False),
    Column("user_message", Text, nullable=False),
    Column("reply", Text, nullable=False, default=""),
    Column("generator_mode", String(64), nullable=False),
    Column("model_name", String(255), nullable=False, default=""),
    Column("context_summary", Text, nullable=False, default=""),
    Column("llm_module_binding_id", String(64), ForeignKey("llm_module_bindings.llm_module_binding_id"), nullable=True),
    Column("created_at", DateTime(timezone=True), nullable=False),
)

Table(
    "agent_state_snapshots",
    metadata,
    Column("snapshot_id", String(64), primary_key=True),
    Column("session_id", String(64), ForeignKey("worldline_sessions.session_id"), nullable=False),
    Column("session_agent_id", String(64), ForeignKey("session_agents.session_agent_id"), nullable=False),
    Column("state_version", Integer, nullable=False),
    Column("status", String(32), nullable=False),
    Column("reason", Text, nullable=False),
    Column("state_json", Text, nullable=False, default="{}"),
    Column("created_at", DateTime(timezone=True), nullable=False),
)

Table(
    "relation_events",
    metadata,
    Column("relation_event_id", String(64), primary_key=True),
    Column("session_id", String(64), ForeignKey("worldline_sessions.session_id"), nullable=False),
    Column("relation_session_agent_id", String(64), ForeignKey("session_agents.session_agent_id"), nullable=True),
    Column("source_session_agent_id", String(64), ForeignKey("session_agents.session_agent_id"), nullable=True),
    Column("target_session_agent_id", String(64), ForeignKey("session_agents.session_agent_id"), nullable=True),
    Column("source_name", String(255), nullable=False),
    Column("target_name", String(255), nullable=False),
    Column("change", String(64), nullable=False),
    Column("note", Text, nullable=False),
    Column("status", String(32), nullable=False),
    Column("last_action", Text, nullable=False, default=""),
    Column("state_json", Text, nullable=False, default="{}"),
    Column("created_at", DateTime(timezone=True), nullable=False),
)
