"""add classification_map table with seed data

Revision ID: 20260418_0001
Revises: 20260417_0002
Create Date: 2026-04-18

Persists the (source, entity_type) -> (category, lifecycle) taxonomy that
was previously hard-coded in ``services/assets/unified_asset_view.py``.
The table uses ``entity_type = '*'`` as the source-level fallback row, so
``classify()`` can resolve any pair with two queries at most.

Phase 1 / Task 5 of the asset-library unification plan.
"""

from __future__ import annotations

from alembic import op
from sqlalchemy import text

from app.tables import metadata


revision = "20260418_0001"
down_revision = "20260417_0002"
branch_labels = None
depends_on = None


# Seed matches the constants in
# backend/app/services/assets/unified_asset_view.py (CATEGORY_MAP,
# LIFECYCLE_MAP, _FALLBACK_CATEGORY_BY_SOURCE, LEGACY_ENTITY_TYPE_ALIASES).
# Keep these in sync; the migration test (Phase 5) will assert equality.
_SEED_ROWS: list[tuple[str, str, str, str]] = [
    # (source, entity_type, category, lifecycle)
    # -- archive --------------------------------------------------------
    ("archive", "character", "characters", "canon"),
    ("archive", "organization", "characters", "canon"),
    ("archive", "faction", "characters", "canon"),
    ("archive", "relationship", "relationships", "canon"),
    ("archive", "*", "characters", "canon"),
    # -- novel_db -------------------------------------------------------
    ("novel_db", "character", "characters", "canon"),
    ("novel_db", "organization", "characters", "canon"),
    ("novel_db", "faction", "characters", "canon"),
    ("novel_db", "relationship", "relationships", "canon"),
    ("novel_db", "plot_thread", "plot", "canon"),
    ("novel_db", "scene", "plot", "canon"),
    ("novel_db", "world_rule", "world", "canon"),
    ("novel_db", "entity", "characters", "canon"),  # legacy alias
    ("novel_db", "*", "other", "canon"),
    # -- seed -----------------------------------------------------------
    ("seed", "seed_character", "characters", "seed"),
    ("seed", "seed_world_rule", "world", "seed"),
    ("seed", "seed_plot_thread", "plot", "seed"),
    ("seed", "seed_agent_profile", "characters", "seed"),
    ("seed", "*", "other", "seed"),
    # -- assets ---------------------------------------------------------
    ("assets", "writing_style", "materials", "material"),
    ("assets", "author_style", "materials", "material"),
    ("assets", "character_archetype", "materials", "material"),
    ("assets", "prompt_template", "materials", "material"),
    ("assets", "plot_template", "materials", "material"),
    ("assets", "manuscript_block", "materials", "material"),
    ("assets", "note", "materials", "material"),
    ("assets", "world_rule", "world", "material"),
    ("assets", "worldview", "world", "material"),
    ("assets", "*", "materials", "material"),
    # -- worldline / story_graph fallbacks ------------------------------
    ("worldline", "*", "other", "simulation"),
    ("story_graph", "*", "other", "graph"),
]


def upgrade() -> None:
    bind = op.get_bind()
    classification_map = metadata.tables["classification_map"]
    classification_map.create(bind, checkfirst=True)
    # Seed. Use INSERT OR IGNORE so re-running on an already-seeded DB is a
    # no-op (keeps the migration idempotent under startup auto-upgrade).
    dialect = bind.dialect.name
    if dialect == "sqlite":
        stmt = text(
            "INSERT OR IGNORE INTO classification_map "
            "(source, entity_type, category, lifecycle) VALUES "
            "(:source, :entity_type, :category, :lifecycle)"
        )
    else:
        # Postgres-friendly upsert
        stmt = text(
            "INSERT INTO classification_map "
            "(source, entity_type, category, lifecycle) VALUES "
            "(:source, :entity_type, :category, :lifecycle) "
            "ON CONFLICT (source, entity_type) DO NOTHING"
        )
    for source, entity_type, category, lifecycle in _SEED_ROWS:
        bind.execute(
            stmt,
            {
                "source": source,
                "entity_type": entity_type,
                "category": category,
                "lifecycle": lifecycle,
            },
        )


def downgrade() -> None:
    classification_map = metadata.tables["classification_map"]
    classification_map.drop(op.get_bind(), checkfirst=True)
