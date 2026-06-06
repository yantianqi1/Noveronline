"""Add llm facility and worldline baseline tables.

Revision ID: 20260411_0002
Revises: 20260411_0001
Create Date: 2026-04-11
"""

from alembic import op
import sqlalchemy as sa


revision = "20260411_0002"
down_revision = "20260411_0001"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "llm_providers",
        sa.Column("llm_provider_id", sa.String(length=64), nullable=False),
        sa.Column("provider_key", sa.String(length=128), nullable=False),
        sa.Column("provider_type", sa.String(length=64), nullable=False),
        sa.Column("name", sa.String(length=255), nullable=False),
        sa.Column("base_url", sa.String(length=512), nullable=False),
        sa.Column("auth_secret_ref", sa.String(length=255), nullable=False),
        sa.Column("status", sa.String(length=32), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("llm_provider_id", name="pk_llm_providers"),
        sa.UniqueConstraint("provider_key", name="uq_llm_providers_provider_key"),
    )
    op.create_table(
        "llm_channels",
        sa.Column("llm_channel_id", sa.String(length=64), nullable=False),
        sa.Column("llm_provider_id", sa.String(length=64), nullable=False),
        sa.Column("channel_key", sa.String(length=128), nullable=False),
        sa.Column("name", sa.String(length=255), nullable=False),
        sa.Column("max_concurrency", sa.Integer(), nullable=False),
        sa.Column("timeout_ms", sa.Integer(), nullable=False),
        sa.Column("is_enabled", sa.Boolean(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(
            ["llm_provider_id"], ["llm_providers.llm_provider_id"], name="fk_llm_channels_llm_provider_id_llm_providers"
        ),
        sa.PrimaryKeyConstraint("llm_channel_id", name="pk_llm_channels"),
        sa.UniqueConstraint("channel_key", name="uq_llm_channels_channel_key"),
    )
    op.create_table(
        "llm_models",
        sa.Column("llm_model_id", sa.String(length=64), nullable=False),
        sa.Column("llm_channel_id", sa.String(length=64), nullable=False),
        sa.Column("provider_model_id", sa.String(length=255), nullable=False),
        sa.Column("display_name", sa.String(length=255), nullable=False),
        sa.Column("synced_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["llm_channel_id"], ["llm_channels.llm_channel_id"], name="fk_llm_models_llm_channel_id_llm_channels"),
        sa.PrimaryKeyConstraint("llm_model_id", name="pk_llm_models"),
    )
    op.create_table(
        "llm_module_bindings",
        sa.Column("llm_module_binding_id", sa.String(length=64), nullable=False),
        sa.Column("module_key", sa.String(length=128), nullable=False),
        sa.Column("llm_channel_id", sa.String(length=64), nullable=False),
        sa.Column("llm_model_id", sa.String(length=64), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["llm_channel_id"], ["llm_channels.llm_channel_id"], name="fk_llm_module_bindings_llm_channel_id_llm_channels"),
        sa.ForeignKeyConstraint(["llm_model_id"], ["llm_models.llm_model_id"], name="fk_llm_module_bindings_llm_model_id_llm_models"),
        sa.PrimaryKeyConstraint("llm_module_binding_id", name="pk_llm_module_bindings"),
        sa.UniqueConstraint("module_key", name="uq_llm_module_bindings_module_key"),
    )
    op.create_table(
        "worldline_preparations",
        sa.Column("prepare_id", sa.String(length=64), nullable=False),
        sa.Column("project_id", sa.String(length=64), nullable=True),
        sa.Column("status", sa.String(length=32), nullable=False),
        sa.Column("session_scope", sa.String(length=64), nullable=False),
        sa.Column("focus_question", sa.Text(), nullable=False),
        sa.Column("started_session_id", sa.String(length=64), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["project_id"], ["projects.project_id"], name="fk_worldline_preparations_project_id_projects"),
        sa.PrimaryKeyConstraint("prepare_id", name="pk_worldline_preparations"),
    )
    op.create_table(
        "prepared_agent_dossiers",
        sa.Column("prepared_agent_dossier_id", sa.String(length=64), nullable=False),
        sa.Column("prepare_id", sa.String(length=64), nullable=False),
        sa.Column("agent_id", sa.String(length=64), nullable=False),
        sa.Column("agent_kind", sa.String(length=64), nullable=False),
        sa.Column("display_name", sa.String(length=255), nullable=False),
        sa.Column("template_key", sa.String(length=128), nullable=True),
        sa.Column("template_version", sa.String(length=64), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(
            ["prepare_id"],
            ["worldline_preparations.prepare_id"],
            name="fk_prepared_agent_dossiers_prepare_id_worldline_preparations",
        ),
        sa.PrimaryKeyConstraint("prepared_agent_dossier_id", name="pk_prepared_agent_dossiers"),
    )
    op.create_table(
        "worldline_sessions",
        sa.Column("session_id", sa.String(length=64), nullable=False),
        sa.Column("project_id", sa.String(length=64), nullable=True),
        sa.Column("session_scope", sa.String(length=64), nullable=False),
        sa.Column("simulation_goal", sa.Text(), nullable=False),
        sa.Column("focus_question", sa.Text(), nullable=False),
        sa.Column("status", sa.String(length=32), nullable=False),
        sa.Column("created_from_prepare_run_id", sa.String(length=64), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["project_id"], ["projects.project_id"], name="fk_worldline_sessions_project_id_projects"),
        sa.PrimaryKeyConstraint("session_id", name="pk_worldline_sessions"),
    )
    op.create_table(
        "world_states",
        sa.Column("world_state_id", sa.String(length=64), nullable=False),
        sa.Column("session_id", sa.String(length=64), nullable=False),
        sa.Column("version_no", sa.Integer(), nullable=False),
        sa.Column("is_current", sa.Boolean(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["session_id"], ["worldline_sessions.session_id"], name="fk_world_states_session_id_worldline_sessions"),
        sa.PrimaryKeyConstraint("world_state_id", name="pk_world_states"),
    )
    op.create_table(
        "timeline_events",
        sa.Column("timeline_event_id", sa.String(length=64), nullable=False),
        sa.Column("session_id", sa.String(length=64), nullable=False),
        sa.Column("world_state_id", sa.String(length=64), nullable=False),
        sa.Column("step_no", sa.Integer(), nullable=False),
        sa.Column("event_type", sa.String(length=64), nullable=False),
        sa.Column("title", sa.String(length=255), nullable=False),
        sa.Column("summary", sa.Text(), nullable=False),
        sa.Column("status", sa.String(length=32), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["session_id"], ["worldline_sessions.session_id"], name="fk_timeline_events_session_id_worldline_sessions"),
        sa.ForeignKeyConstraint(["world_state_id"], ["world_states.world_state_id"], name="fk_timeline_events_world_state_id_world_states"),
        sa.PrimaryKeyConstraint("timeline_event_id", name="pk_timeline_events"),
    )
    op.create_table(
        "session_agents",
        sa.Column("session_agent_id", sa.String(length=64), nullable=False),
        sa.Column("session_id", sa.String(length=64), nullable=False),
        sa.Column("archive_id", sa.String(length=64), nullable=True),
        sa.Column("entity_id", sa.String(length=64), nullable=True),
        sa.Column("agent_kind", sa.String(length=64), nullable=False),
        sa.Column("display_name", sa.String(length=255), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["archive_id"], ["archives.archive_id"], name="fk_session_agents_archive_id_archives"),
        sa.ForeignKeyConstraint(["entity_id"], ["entities.entity_id"], name="fk_session_agents_entity_id_entities"),
        sa.ForeignKeyConstraint(["session_id"], ["worldline_sessions.session_id"], name="fk_session_agents_session_id_worldline_sessions"),
        sa.PrimaryKeyConstraint("session_agent_id", name="pk_session_agents"),
    )
    op.create_table(
        "agent_actions",
        sa.Column("action_id", sa.String(length=64), nullable=False),
        sa.Column("session_id", sa.String(length=64), nullable=False),
        sa.Column("session_agent_id", sa.String(length=64), nullable=False),
        sa.Column("action", sa.Text(), nullable=False),
        sa.Column("status", sa.String(length=32), nullable=False),
        sa.Column("queued_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["session_agent_id"], ["session_agents.session_agent_id"], name="fk_agent_actions_session_agent_id_session_agents"),
        sa.ForeignKeyConstraint(["session_id"], ["worldline_sessions.session_id"], name="fk_agent_actions_session_id_worldline_sessions"),
        sa.PrimaryKeyConstraint("action_id", name="pk_agent_actions"),
    )
    op.create_table(
        "agent_dialogues",
        sa.Column("dialogue_id", sa.String(length=64), nullable=False),
        sa.Column("session_id", sa.String(length=64), nullable=False),
        sa.Column("session_agent_id", sa.String(length=64), nullable=False),
        sa.Column("user_message", sa.Text(), nullable=False),
        sa.Column("generator_mode", sa.String(length=64), nullable=False),
        sa.Column("llm_module_binding_id", sa.String(length=64), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["llm_module_binding_id"], ["llm_module_bindings.llm_module_binding_id"], name="fk_agent_dialogues_llm_module_binding_id_llm_module_bindings"),
        sa.ForeignKeyConstraint(["session_agent_id"], ["session_agents.session_agent_id"], name="fk_agent_dialogues_session_agent_id_session_agents"),
        sa.ForeignKeyConstraint(["session_id"], ["worldline_sessions.session_id"], name="fk_agent_dialogues_session_id_worldline_sessions"),
        sa.PrimaryKeyConstraint("dialogue_id", name="pk_agent_dialogues"),
    )


def downgrade() -> None:
    op.drop_table("agent_dialogues")
    op.drop_table("agent_actions")
    op.drop_table("session_agents")
    op.drop_table("timeline_events")
    op.drop_table("world_states")
    op.drop_table("worldline_sessions")
    op.drop_table("prepared_agent_dossiers")
    op.drop_table("worldline_preparations")
    op.drop_table("llm_module_bindings")
    op.drop_table("llm_models")
    op.drop_table("llm_channels")
    op.drop_table("llm_providers")
