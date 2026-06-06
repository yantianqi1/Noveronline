"""Add workflow event log table.

Revision ID: 20260412_0007
Revises: 20260411_0006
Create Date: 2026-04-12
"""

from alembic import op
import sqlalchemy as sa


revision = "20260412_0007"
down_revision = "20260411_0006"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "workflow_events",
        sa.Column("workflow_event_id", sa.String(length=64), nullable=False),
        sa.Column("workflow_run_id", sa.String(length=64), nullable=False),
        sa.Column("event_type", sa.String(length=64), nullable=False),
        sa.Column("stage", sa.String(length=128), nullable=True),
        sa.Column("level", sa.String(length=32), nullable=True),
        sa.Column("status", sa.String(length=32), nullable=True),
        sa.Column("title", sa.String(length=255), nullable=False),
        sa.Column("detail", sa.Text(), nullable=True),
        sa.Column("payload_json", sa.Text(), nullable=False),
        sa.Column("emitted_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["workflow_run_id"], ["workflow_runs.workflow_run_id"], name="fk_workflow_events_workflow_run_id_workflow_runs"),
        sa.PrimaryKeyConstraint("workflow_event_id", name="pk_workflow_events"),
    )


def downgrade() -> None:
    op.drop_table("workflow_events")
