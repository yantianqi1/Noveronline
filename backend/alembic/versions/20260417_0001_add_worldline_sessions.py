"""add worldline_sessions table

Revision ID: 20260417_0001
Revises: 20260412_0001
Create Date: 2026-04-17

Introduces ``worldline_sessions`` so ``WorldStateStore`` can persist
session metadata + full JSON payload in the unified database instead
of the per-project filesystem layout under
``uploads/projects/<pid>/worldlines/sessions/<sid>/session.json``.
"""

from __future__ import annotations

from alembic import op

from app.tables import metadata


revision = "20260417_0001"
down_revision = "20260412_0001"
branch_labels = None
depends_on = None


def upgrade() -> None:
    worldline_sessions = metadata.tables["worldline_sessions"]
    worldline_sessions.create(op.get_bind(), checkfirst=True)


def downgrade() -> None:
    worldline_sessions = metadata.tables["worldline_sessions"]
    worldline_sessions.drop(op.get_bind(), checkfirst=True)
