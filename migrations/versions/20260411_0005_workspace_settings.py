"""Add workspace settings table.

Revision ID: 20260411_0005
Revises: 20260411_0004
Create Date: 2026-04-11
"""

from alembic import op
import sqlalchemy as sa


revision = "20260411_0005"
down_revision = "20260411_0004"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "workspace_settings",
        sa.Column("workspace_id", sa.String(length=64), nullable=False),
        sa.Column("reviewer_rules_text", sa.Text(), nullable=True),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["workspace_id"], ["workspaces.workspace_id"], name="fk_workspace_settings_workspace_id_workspaces"),
        sa.PrimaryKeyConstraint("workspace_id", name="pk_workspace_settings"),
    )


def downgrade() -> None:
    op.drop_table("workspace_settings")
