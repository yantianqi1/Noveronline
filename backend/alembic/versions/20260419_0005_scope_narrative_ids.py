"""scope narrative arc and volume ids by project

Revision ID: 20260419_0005
Revises: 20260419_0004
Create Date: 2026-06-08

``arc_id`` and ``volume_id`` are generated as project-local identifiers
(``arc_001``, ``vol_001``). They must therefore be scoped by ``project_id`` in
the database primary key; otherwise the second project to run seed analysis
silently loses narrative rows.
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op


revision = "20260419_0005"
down_revision = "20260419_0004"
branch_labels = None
depends_on = None


def upgrade() -> None:
    _ensure_composite_pk(
        "narrative_arcs",
        (
            ("project_id", "VARCHAR", "NOT NULL", None),
            ("arc_id", "VARCHAR", "NOT NULL", None),
            ("summary", "VARCHAR", "NOT NULL", None),
            ("covered_segments_json", "VARCHAR", "", "'[]'"),
            ("created_at", "VARCHAR", "NOT NULL", None),
        ),
        ("project_id", "arc_id"),
    )
    _ensure_composite_pk(
        "volume_summaries",
        (
            ("project_id", "VARCHAR", "NOT NULL", None),
            ("volume_id", "VARCHAR", "NOT NULL", None),
            ("volume_order", "INTEGER", "NOT NULL", None),
            ("summary", "VARCHAR", "NOT NULL", None),
            ("covered_arcs_json", "VARCHAR", "", "'[]'"),
            ("created_at", "VARCHAR", "NOT NULL", None),
        ),
        ("project_id", "volume_id"),
    )


def downgrade() -> None:
    _ensure_composite_pk(
        "narrative_arcs",
        (
            ("arc_id", "VARCHAR", "NOT NULL", None),
            ("project_id", "VARCHAR", "NOT NULL", None),
            ("summary", "VARCHAR", "NOT NULL", None),
            ("covered_segments_json", "VARCHAR", "", "'[]'"),
            ("created_at", "VARCHAR", "NOT NULL", None),
        ),
        ("arc_id",),
    )
    _ensure_composite_pk(
        "volume_summaries",
        (
            ("volume_id", "VARCHAR", "NOT NULL", None),
            ("project_id", "VARCHAR", "NOT NULL", None),
            ("volume_order", "INTEGER", "NOT NULL", None),
            ("summary", "VARCHAR", "NOT NULL", None),
            ("covered_arcs_json", "VARCHAR", "", "'[]'"),
            ("created_at", "VARCHAR", "NOT NULL", None),
        ),
        ("volume_id",),
    )


def _ensure_composite_pk(
    table_name: str,
    columns: tuple[tuple[str, str, str, str | None], ...],
    pk_columns: tuple[str, ...],
) -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    if table_name not in set(inspector.get_table_names()):
        return
    current_pk = tuple(inspector.get_pk_constraint(table_name).get("constrained_columns") or ())
    if current_pk == pk_columns:
        return
    if bind.dialect.name == "sqlite":
        _rebuild_sqlite_table(table_name, columns, pk_columns)
        return
    pk_name = inspector.get_pk_constraint(table_name).get("name") or f"pk_{table_name}"
    op.drop_constraint(pk_name, table_name, type_="primary")
    op.create_primary_key(pk_name, table_name, list(pk_columns))


def _rebuild_sqlite_table(
    table_name: str,
    columns: tuple[tuple[str, str, str, str | None], ...],
    pk_columns: tuple[str, ...],
) -> None:
    bind = op.get_bind()
    tmp_table = f"{table_name}__pk_scope_tmp"
    column_defs = []
    for name, col_type, nullable, default in columns:
        default_sql = f" DEFAULT {default}" if default is not None else ""
        column_defs.append(f"{name} {col_type} {nullable}{default_sql}".strip())
    column_defs.append(f"PRIMARY KEY ({', '.join(pk_columns)})")
    column_names = ", ".join(name for name, *_ in columns)
    bind.execute(sa.text(f"DROP TABLE IF EXISTS {tmp_table}"))
    bind.execute(sa.text(f"CREATE TABLE {tmp_table} ({', '.join(column_defs)})"))
    bind.execute(
        sa.text(
            f"INSERT OR IGNORE INTO {tmp_table} ({column_names}) "
            f"SELECT {column_names} FROM {table_name}"
        )
    )
    bind.execute(sa.text(f"DROP TABLE {table_name}"))
    bind.execute(sa.text(f"ALTER TABLE {tmp_table} RENAME TO {table_name}"))
    _rebuild_fts(table_name)


def _rebuild_fts(table_name: str) -> None:
    fts_table = f"{table_name}_fts"
    bind = op.get_bind()
    existing = {
        row[0]
        for row in bind.execute(
            sa.text("SELECT name FROM sqlite_master WHERE type='table' AND name=:name"),
            {"name": fts_table},
        )
    }
    if fts_table in existing:
        bind.execute(sa.text(f"INSERT INTO {fts_table}({fts_table}) VALUES ('rebuild')"))
