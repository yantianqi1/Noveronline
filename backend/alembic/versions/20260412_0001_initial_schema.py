"""initial unified schema

Revision ID: 20260412_0001
Revises:
Create Date: 2026-04-12
"""

from __future__ import annotations

import re

from alembic import op
from sqlalchemy import text

from app.tables import metadata
from app.tables.fts import FTS_TABLE_DDL, FTS_TRIGGER_DDL

revision = "20260412_0001"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    metadata.create_all(op.get_bind())


def downgrade() -> None:
    bind = op.get_bind()
    # FTS5 virtual tables and their triggers live outside ``metadata`` (they
    # are registered via a ``DDL`` event listener in ``app.tables.fts``).
    # ``metadata.drop_all`` therefore leaves behind the virtual tables and
    # their auto-generated side tables (``*_docsize`` / ``*_config`` /
    # ``*_data`` / ``*_idx``). Drop them explicitly before tearing down the
    # regular schema so downgrade is a true inverse of upgrade.
    if bind.dialect.name == "sqlite":
        for trigger_stmt in FTS_TRIGGER_DDL:
            match = re.search(r"CREATE TRIGGER IF NOT EXISTS (\w+)", trigger_stmt)
            if match:
                bind.execute(text(f"DROP TRIGGER IF EXISTS {match.group(1)}"))
        for table_stmt in FTS_TABLE_DDL:
            match = re.search(r"CREATE VIRTUAL TABLE IF NOT EXISTS (\w+)", table_stmt)
            if match:
                bind.execute(text(f"DROP TABLE IF EXISTS {match.group(1)}"))
    metadata.drop_all(bind)
