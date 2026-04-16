"""Migrate legacy per-project SQLite stores into the unified database."""

from __future__ import annotations

import argparse
from pathlib import Path

from app.config import Settings
from app import database_compat as dbapi
from app.database import create_engine_from_settings, init_db
from app.tables import metadata


def migrate_legacy_data(upload_root: Path, database_url: str | None = None) -> dict[str, int]:
    settings = Settings(DATABASE_URL=database_url or Settings().DATABASE_URL)
    engine = create_engine_from_settings(settings)
    init_db(engine)
    counts: dict[str, int] = {}
    for project_dir in _project_dirs(upload_root):
        project_id = project_dir.name
        for db_name in ("novel.sqlite3", "story_graph.sqlite3"):
            source = project_dir / db_name
            if source.exists():
                _copy_database(source, dbapi.Connection(engine.raw_connection()), project_id, counts)
    return counts


def _project_dirs(upload_root: Path) -> list[Path]:
    projects_root = upload_root / "projects"
    if not projects_root.exists():
        return []
    return [path for path in projects_root.iterdir() if path.is_dir()]


def _copy_database(source: Path, target, project_id: str, counts: dict[str, int]) -> None:
    try:
        source_conn = dbapi.connect(str(source))
        source_conn.row_factory = dbapi.Row
        target.row_factory = dbapi.Row
        for table_name in _copyable_tables(source_conn):
            copied = _copy_table(source_conn, target, table_name, project_id)
            counts[table_name] = counts.get(table_name, 0) + copied
        target.commit()
    finally:
        source_conn.close()
        target.close()


def _copyable_tables(connection: dbapi.Connection) -> list[str]:
    rows = connection.execute(
        "SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%'"
    ).fetchall()
    return [row["name"] for row in rows if row["name"] in metadata.tables]


def _copy_table(source, target, table_name: str, project_id: str) -> int:
    columns = [row["name"] for row in source.execute(f"PRAGMA table_info({table_name})").fetchall()]
    rows = source.execute(f"SELECT * FROM {table_name}").fetchall()
    if not rows:
        return 0
    target_columns = _target_columns(table_name, columns)
    placeholders = ", ".join("?" for _ in target_columns)
    column_sql = ", ".join(target_columns)
    target.execute(f"DELETE FROM {table_name} WHERE project_id = ?", (project_id,))
    values = [_row_values(row, target_columns, project_id) for row in rows]
    target.executemany(f"INSERT INTO {table_name} ({column_sql}) VALUES ({placeholders})", values)
    return len(rows)


def _target_columns(table_name: str, source_columns: list[str]) -> list[str]:
    table = metadata.tables[table_name]
    columns = [column for column in source_columns if column in table.c]
    if "project_id" in table.c and "project_id" not in columns:
        return ["project_id", *columns]
    return columns


def _row_values(row, columns: list[str], project_id: str) -> tuple:
    return tuple(project_id if column == "project_id" and column not in row.keys() else row[column] for column in columns)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--upload-root", default="uploads")
    parser.add_argument("--database-url", default=None)
    args = parser.parse_args()
    counts = migrate_legacy_data(Path(args.upload_root), args.database_url)
    for table_name, count in sorted(counts.items()):
        print(f"{table_name}: {count}")


if __name__ == "__main__":
    main()
