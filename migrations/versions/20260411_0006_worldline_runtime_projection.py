"""Expand worldline runtime projection tables.

Revision ID: 20260411_0006
Revises: 20260411_0005
Create Date: 2026-04-11
"""

from alembic import op
import sqlalchemy as sa


revision = "20260411_0006"
down_revision = "20260411_0005"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("session_agents", sa.Column("agent_id", sa.String(length=64), nullable=False, server_default=""))
    op.add_column("session_agents", sa.Column("role", sa.String(length=64), nullable=True))
    op.add_column("session_agents", sa.Column("drive", sa.Text(), nullable=True))
    op.add_column("session_agents", sa.Column("tension", sa.Text(), nullable=True))
    op.add_column("session_agents", sa.Column("status", sa.String(length=32), nullable=True))
    op.add_column("session_agents", sa.Column("summary", sa.Text(), nullable=True))
    op.add_column("session_agents", sa.Column("can_chat", sa.Boolean(), nullable=False, server_default=sa.true()))
    op.add_column("session_agents", sa.Column("can_act", sa.Boolean(), nullable=False, server_default=sa.true()))
    op.add_column("session_agents", sa.Column("state_json", sa.Text(), nullable=True))
    op.add_column("session_agents", sa.Column("state_source", sa.String(length=64), nullable=True))
    op.add_column("session_agents", sa.Column("state_version", sa.Integer(), nullable=True))
    op.add_column("session_agents", sa.Column("source_ref", sa.String(length=255), nullable=True))
    op.add_column("session_agents", sa.Column("last_action_at", sa.DateTime(timezone=True), nullable=True))
    op.add_column("session_agents", sa.Column("last_dialogue_at", sa.DateTime(timezone=True), nullable=True))

    op.add_column("agent_actions", sa.Column("intent", sa.Text(), nullable=False, server_default=""))
    op.add_column("agent_actions", sa.Column("target", sa.String(length=255), nullable=False, server_default=""))
    op.add_column("agent_actions", sa.Column("source", sa.String(length=64), nullable=False, server_default=""))
    op.add_column("agent_actions", sa.Column("detail_json", sa.Text(), nullable=False, server_default="{}"))
    op.add_column("agent_actions", sa.Column("applied_at", sa.DateTime(timezone=True), nullable=True))
    op.add_column("agent_actions", sa.Column("discarded_at", sa.DateTime(timezone=True), nullable=True))

    op.add_column("agent_dialogues", sa.Column("reply", sa.Text(), nullable=False, server_default=""))
    op.add_column("agent_dialogues", sa.Column("model_name", sa.String(length=255), nullable=False, server_default=""))
    op.add_column("agent_dialogues", sa.Column("context_summary", sa.Text(), nullable=False, server_default=""))

    op.create_table(
        "agent_state_snapshots",
        sa.Column("snapshot_id", sa.String(length=64), nullable=False),
        sa.Column("session_id", sa.String(length=64), nullable=False),
        sa.Column("session_agent_id", sa.String(length=64), nullable=False),
        sa.Column("state_version", sa.Integer(), nullable=False),
        sa.Column("status", sa.String(length=32), nullable=False),
        sa.Column("reason", sa.Text(), nullable=False),
        sa.Column("state_json", sa.Text(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(
            ["session_agent_id"], ["session_agents.session_agent_id"], name="fk_agent_state_snapshots_session_agent_id_session_agents"
        ),
        sa.ForeignKeyConstraint(
            ["session_id"], ["worldline_sessions.session_id"], name="fk_agent_state_snapshots_session_id_worldline_sessions"
        ),
        sa.PrimaryKeyConstraint("snapshot_id", name="pk_agent_state_snapshots"),
    )

    op.create_table(
        "relation_events",
        sa.Column("relation_event_id", sa.String(length=64), nullable=False),
        sa.Column("session_id", sa.String(length=64), nullable=False),
        sa.Column("relation_session_agent_id", sa.String(length=64), nullable=True),
        sa.Column("source_session_agent_id", sa.String(length=64), nullable=True),
        sa.Column("target_session_agent_id", sa.String(length=64), nullable=True),
        sa.Column("source_name", sa.String(length=255), nullable=False),
        sa.Column("target_name", sa.String(length=255), nullable=False),
        sa.Column("change", sa.String(length=64), nullable=False),
        sa.Column("note", sa.Text(), nullable=False),
        sa.Column("status", sa.String(length=32), nullable=False),
        sa.Column("last_action", sa.Text(), nullable=False),
        sa.Column("state_json", sa.Text(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(
            ["relation_session_agent_id"], ["session_agents.session_agent_id"], name="fk_relation_events_relation_session_agent_id_session_agents"
        ),
        sa.ForeignKeyConstraint(
            ["session_id"], ["worldline_sessions.session_id"], name="fk_relation_events_session_id_worldline_sessions"
        ),
        sa.ForeignKeyConstraint(
            ["source_session_agent_id"], ["session_agents.session_agent_id"], name="fk_relation_events_source_session_agent_id_session_agents"
        ),
        sa.ForeignKeyConstraint(
            ["target_session_agent_id"], ["session_agents.session_agent_id"], name="fk_relation_events_target_session_agent_id_session_agents"
        ),
        sa.PrimaryKeyConstraint("relation_event_id", name="pk_relation_events"),
    )


def downgrade() -> None:
    op.drop_table("relation_events")
    op.drop_table("agent_state_snapshots")

    op.drop_column("agent_dialogues", "context_summary")
    op.drop_column("agent_dialogues", "model_name")
    op.drop_column("agent_dialogues", "reply")

    op.drop_column("agent_actions", "discarded_at")
    op.drop_column("agent_actions", "applied_at")
    op.drop_column("agent_actions", "detail_json")
    op.drop_column("agent_actions", "source")
    op.drop_column("agent_actions", "target")
    op.drop_column("agent_actions", "intent")

    op.drop_column("session_agents", "last_dialogue_at")
    op.drop_column("session_agents", "last_action_at")
    op.drop_column("session_agents", "source_ref")
    op.drop_column("session_agents", "state_version")
    op.drop_column("session_agents", "state_source")
    op.drop_column("session_agents", "state_json")
    op.drop_column("session_agents", "can_act")
    op.drop_column("session_agents", "can_chat")
    op.drop_column("session_agents", "summary")
    op.drop_column("session_agents", "status")
    op.drop_column("session_agents", "tension")
    op.drop_column("session_agents", "drive")
    op.drop_column("session_agents", "role")
    op.drop_column("session_agents", "agent_id")
