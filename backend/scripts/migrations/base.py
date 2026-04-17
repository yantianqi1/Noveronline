"""Shared migration context, base class, and SQLite copy helper."""

from __future__ import annotations

import sqlite3
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from sqlalchemy import Engine, and_, delete, insert

from app.tables import metadata


@dataclass
class MigrationContext:
    """Inputs shared by every migrator invocation.

    ``project_id`` is ``None`` when executing global (non-project) migrators.
    ``report`` accumulates per-domain row counts across runs.
    """

    upload_root: Path
    engine: Engine
    project_id: str | None = None
    dry_run: bool = False
    replace_project: bool = True
    report: dict[str, dict[str, int]] = field(default_factory=dict)

    def record(self, scope_key: str, counts: dict[str, int]) -> None:
        if counts:
            self.report[scope_key] = counts


class BaseDomainMigrator(ABC):
    """Contract for a single legacy domain migrator."""

    domain_name: str = ""
    is_project_scoped: bool = True

    @abstractmethod
    def migrate(self, ctx: MigrationContext) -> dict[str, int]:
        """Return ``{table_name: row_count}`` for rows actually written."""

    def _scope_key(self, ctx: MigrationContext) -> str:
        scope = ctx.project_id if self.is_project_scoped else "__global__"
        return f"{self.domain_name}:{scope}"

    def run(self, ctx: MigrationContext) -> dict[str, int]:
        counts = self.migrate(ctx)
        ctx.record(self._scope_key(ctx), counts)
        return counts


def copy_sqlite_into_unified(
    *,
    source_path: Path,
    engine: Engine,
    project_id: str | None = None,
    dry_run: bool = False,
    only_tables: set[str] | None = None,
) -> dict[str, int]:
    """Copy rows from a legacy SQLite file into their unified tables.

    Idempotency model:
    * ``project_id`` set: DELETE unified rows WHERE project_id = X, then INSERT.
    * ``project_id`` is None (global): DELETE each row by its primary-key
      tuple (from the source) before INSERT. Rows in unified that do not
      exist in source are left untouched.
    """
    if not source_path.exists():
        return {}

    counts: dict[str, int] = {}
    with sqlite3.connect(source_path) as src:
        src.row_factory = sqlite3.Row
        table_names = _copyable_tables(src, only_tables=only_tables)
        if not table_names:
            return {}
        if dry_run:
            for table_name in table_names:
                row_count = src.execute(f"SELECT COUNT(*) FROM {table_name}").fetchone()[0] or 0
                if row_count:
                    counts[table_name] = row_count
            return counts

        with engine.begin() as conn:
            for table_name in table_names:
                n = _copy_one_table(src, conn, table_name, project_id)
                if n:
                    counts[table_name] = n
    return counts


def _copyable_tables(source_conn: sqlite3.Connection, only_tables: set[str] | None) -> list[str]:
    rows = source_conn.execute(
        "SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%' ORDER BY name"
    ).fetchall()
    names: list[str] = []
    for row in rows:
        name = row[0]
        if name not in metadata.tables:
            continue
        if only_tables is not None and name not in only_tables:
            continue
        names.append(name)
    return names


def _source_columns(source_conn: sqlite3.Connection, table_name: str) -> list[str]:
    return [row[1] for row in source_conn.execute(f"PRAGMA table_info({table_name})").fetchall()]


def _copy_one_table(
    src_conn: sqlite3.Connection,
    target_conn,
    table_name: str,
    project_id: str | None,
) -> int:
    table = metadata.tables[table_name]
    source_columns = _source_columns(src_conn, table_name)
    matching_columns = [col for col in source_columns if col in table.c]
    has_pid_in_table = "project_id" in table.c
    has_pid_in_source = "project_id" in source_columns

    rows = src_conn.execute(f"SELECT * FROM {table_name}").fetchall()
    if not rows:
        return 0

    row_dicts: list[dict[str, Any]] = []
    for row in rows:
        data: dict[str, Any] = {col: row[col] for col in matching_columns}
        if has_pid_in_table and not has_pid_in_source and project_id:
            data["project_id"] = project_id
        row_dicts.append(data)

    if project_id and has_pid_in_table:
        target_conn.execute(delete(table).where(table.c.project_id == project_id))
    else:
        pk_cols = [col.name for col in table.primary_key.columns]
        if pk_cols:
            for data in row_dicts:
                clauses = [table.c[col] == data.get(col) for col in pk_cols if col in table.c]
                if clauses:
                    target_conn.execute(delete(table).where(and_(*clauses)))

    target_conn.execute(insert(table), row_dicts)
    return len(row_dicts)


__all__ = [
    "BaseDomainMigrator",
    "MigrationContext",
    "copy_sqlite_into_unified",
]
