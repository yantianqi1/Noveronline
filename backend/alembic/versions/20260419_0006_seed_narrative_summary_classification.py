"""classify seed narrative summary asset types

Revision ID: 20260419_0006
Revises: 20260419_0005
Create Date: 2026-06-08
"""

from __future__ import annotations

from alembic import op
from sqlalchemy import inspect, text


revision = "20260419_0006"
down_revision = "20260419_0005"
branch_labels = None
depends_on = None


_ROWS = (
    ("seed", "seed_arc_summary", "plot", "seed"),
    ("seed", "seed_key_event", "plot", "seed"),
    ("seed", "seed_ontology_entity", "world", "seed"),
    ("seed", "seed_segment_summary", "plot", "seed"),
    ("seed", "seed_volume_summary", "plot", "seed"),
)


def upgrade() -> None:
    bind = op.get_bind()
    if "classification_map" not in inspect(bind).get_table_names():
        return
    if bind.dialect.name == "sqlite":
        stmt = text(
            "INSERT OR IGNORE INTO classification_map "
            "(source, entity_type, category, lifecycle) "
            "VALUES (:source, :entity_type, :category, :lifecycle)"
        )
    else:
        stmt = text(
            "INSERT INTO classification_map "
            "(source, entity_type, category, lifecycle) "
            "VALUES (:source, :entity_type, :category, :lifecycle) "
            "ON CONFLICT (source, entity_type) DO NOTHING"
        )
    for source, entity_type, category, lifecycle in _ROWS:
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
    bind = op.get_bind()
    if "classification_map" not in inspect(bind).get_table_names():
        return
    bind.execute(
        text(
            "DELETE FROM classification_map "
            "WHERE source = 'seed' "
            "AND entity_type IN ("
            "'seed_arc_summary', 'seed_key_event', 'seed_ontology_entity', "
            "'seed_segment_summary', 'seed_volume_summary'"
            ")"
        )
    )
