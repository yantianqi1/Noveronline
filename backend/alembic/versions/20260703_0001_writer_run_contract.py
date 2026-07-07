"""Add writer run and draft contract tables.

Revision ID: 20260703_0001
Revises: 20260419_0006
Create Date: 2026-07-03
"""

from __future__ import annotations

from alembic import op

from app.tables import metadata


revision = "20260703_0001"
down_revision = "20260419_0006"
branch_labels = None
depends_on = None


def upgrade() -> None:
    bind = op.get_bind()
    for table_name in (
        "writer_runs",
        "writer_run_events",
        "writer_drafts",
        "writer_draft_events",
    ):
        metadata.tables[table_name].create(bind, checkfirst=True)


def downgrade() -> None:
    bind = op.get_bind()
    for table_name in (
        "writer_draft_events",
        "writer_drafts",
        "writer_run_events",
        "writer_runs",
    ):
        metadata.tables[table_name].drop(bind, checkfirst=True)
