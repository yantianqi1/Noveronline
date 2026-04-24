"""add dedup_index table for writer agent anti-repetition

Revision ID: 20260418_0003
Revises: 20260418_0002
Create Date: 2026-04-18

Stores prose patterns (opening phrases, figurative phrases, action verbs,
sentence starters, scene templates) already used per project. Populated
after each scene commit by the LLM-based DedupExtractor; consumed by the
writer agent as anti-repetition constraints before the next generation.

A composite UNIQUE on (project_id, pattern_type, pattern_text) makes
re-inserts of the same pattern collapse into a ``count`` bump instead of
creating duplicate rows, so the repository can implement "seen N times"
thresholding cheaply.
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

from app.tables import metadata


revision = "20260418_0003"
down_revision = "20260418_0002"
branch_labels = None
depends_on = None


def upgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)

    if "dedup_index" not in set(inspector.get_table_names()):
        dedup_index = metadata.tables["dedup_index"]
        dedup_index.create(bind, checkfirst=True)

    # Helpful secondary index for chapter-scoped purges and range queries
    # (get_constraints filters by chapter_order). No-op if already present.
    existing_indexes = {idx["name"] for idx in inspector.get_indexes("dedup_index")} if "dedup_index" in set(inspector.get_table_names()) else set()
    if "ix_dedup_project_chapter" not in existing_indexes:
        op.create_index(
            "ix_dedup_project_chapter",
            "dedup_index",
            ["project_id", "chapter_order"],
        )


def downgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    if "dedup_index" in set(inspector.get_table_names()):
        existing_indexes = {idx["name"] for idx in inspector.get_indexes("dedup_index")}
        if "ix_dedup_project_chapter" in existing_indexes:
            op.drop_index("ix_dedup_project_chapter", table_name="dedup_index")
        op.drop_table("dedup_index")
