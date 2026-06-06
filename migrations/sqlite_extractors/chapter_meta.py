from __future__ import annotations

import sqlite3
from pathlib import Path


def _fetch_rows(database_path: Path, query: str) -> tuple[dict, ...]:
    connection = sqlite3.connect(database_path)
    connection.row_factory = sqlite3.Row
    try:
        rows = connection.execute(query).fetchall()
    finally:
        connection.close()
    return tuple(dict(row) for row in rows)


def list_chapter_meta(database_path: Path) -> tuple[dict, ...]:
    return _fetch_rows(
        database_path,
        """
        select project_id, chapter_order, chapter_id, title, summary_text, timeline_note, created_at, updated_at
        from chapter_meta
        order by project_id asc, chapter_order asc
        """,
    )


def list_chapter_history_items(database_path: Path) -> tuple[dict, ...]:
    return _fetch_rows(
        database_path,
        """
        select project_id, chapter_order, chapter_id, item_type, subject_key, summary_text, created_at, updated_at
        from chapter_history_item
        order by project_id asc, chapter_order asc, created_at asc
        """,
    )
