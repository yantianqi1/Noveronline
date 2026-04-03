"""Unified SQLite data access layer for novel writing.

Manages a per-project ``novel.sqlite3`` database with tables spanning
settings (entities, relationships), content (chapters, scenes),
worldline (sessions, agent states, memory, events), presets,
and FTS5 full-text search.
"""

from __future__ import annotations

import json
import os
import sqlite3
from contextlib import contextmanager
from datetime import datetime, timezone
from typing import Any, Iterator

from ...config import Config

# ---------------------------------------------------------------------------
# Schema DDL
# ---------------------------------------------------------------------------

TABLE_STATEMENTS = (
    # -- Settings layer --
    """
    CREATE TABLE IF NOT EXISTS entities (
        entity_id TEXT PRIMARY KEY,
        project_id TEXT NOT NULL,
        name TEXT NOT NULL,
        entity_type TEXT NOT NULL,
        importance_tier TEXT DEFAULT 'minor',
        summary TEXT,
        core_drive TEXT,
        surface_mask TEXT,
        hidden_tension TEXT,
        profile_json TEXT NOT NULL DEFAULT '{}',
        created_at TEXT NOT NULL,
        updated_at TEXT NOT NULL
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS entity_aliases (
        alias TEXT NOT NULL,
        entity_id TEXT NOT NULL REFERENCES entities ON DELETE CASCADE,
        PRIMARY KEY (alias, entity_id)
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS entity_labels (
        entity_id TEXT NOT NULL REFERENCES entities ON DELETE CASCADE,
        label TEXT NOT NULL,
        PRIMARY KEY (entity_id, label)
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS relationships (
        relation_id TEXT PRIMARY KEY,
        source_id TEXT NOT NULL REFERENCES entities ON DELETE CASCADE,
        target_id TEXT NOT NULL REFERENCES entities ON DELETE CASCADE,
        relation_type TEXT NOT NULL,
        description TEXT,
        trust_level REAL,
        power_dynamic TEXT,
        history TEXT,
        conflict_trigger TEXT,
        updated_at TEXT NOT NULL
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS entity_evidence (
        evidence_id TEXT PRIMARY KEY,
        owner_id TEXT NOT NULL,
        owner_type TEXT NOT NULL,
        chapter_id TEXT,
        snippet TEXT NOT NULL,
        created_at TEXT NOT NULL
    )
    """,
    # -- Content layer --
    """
    CREATE TABLE IF NOT EXISTS chapter_content (
        chapter_id TEXT PRIMARY KEY,
        project_id TEXT NOT NULL,
        chapter_order INTEGER NOT NULL,
        title TEXT DEFAULT '',
        content TEXT NOT NULL DEFAULT '',
        word_count INTEGER DEFAULT 0,
        status TEXT DEFAULT 'draft',
        created_at TEXT NOT NULL,
        updated_at TEXT NOT NULL,
        UNIQUE(project_id, chapter_order)
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS chapter_meta (
        chapter_id TEXT PRIMARY KEY REFERENCES chapter_content ON DELETE CASCADE,
        summary TEXT DEFAULT '',
        outline_json TEXT DEFAULT '[]',
        timeline_note TEXT DEFAULT '',
        open_threads_json TEXT DEFAULT '[]',
        pov_character TEXT,
        updated_at TEXT NOT NULL
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS scenes (
        scene_id TEXT PRIMARY KEY,
        chapter_id TEXT NOT NULL REFERENCES chapter_content ON DELETE CASCADE,
        scene_order INTEGER NOT NULL,
        title TEXT DEFAULT '',
        content TEXT NOT NULL DEFAULT '',
        word_count INTEGER DEFAULT 0,
        pov_entity_id TEXT,
        location TEXT,
        involved_entities_json TEXT DEFAULT '[]',
        status TEXT DEFAULT 'draft',
        writing_brief_json TEXT,
        created_at TEXT NOT NULL,
        updated_at TEXT NOT NULL,
        UNIQUE(chapter_id, scene_order)
    )
    """,
    # -- Worldline layer --
    """
    CREATE TABLE IF NOT EXISTS sessions (
        session_id TEXT PRIMARY KEY,
        project_id TEXT NOT NULL,
        session_type TEXT NOT NULL,
        title TEXT,
        focus_question TEXT,
        status TEXT DEFAULT 'running',
        config_json TEXT DEFAULT '{}',
        created_at TEXT NOT NULL,
        updated_at TEXT NOT NULL
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS agent_states (
        state_id TEXT PRIMARY KEY,
        session_id TEXT NOT NULL REFERENCES sessions ON DELETE CASCADE,
        entity_id TEXT NOT NULL,
        state_json TEXT NOT NULL,
        status TEXT DEFAULT 'active',
        version INTEGER DEFAULT 1,
        updated_at TEXT NOT NULL
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS agent_memory (
        memory_id TEXT PRIMARY KEY,
        session_id TEXT NOT NULL REFERENCES sessions ON DELETE CASCADE,
        entity_id TEXT NOT NULL,
        memory_type TEXT NOT NULL,
        summary TEXT NOT NULL,
        detail_json TEXT,
        salience REAL DEFAULT 0,
        source_kind TEXT,
        created_at TEXT NOT NULL
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS world_events (
        event_id TEXT PRIMARY KEY,
        session_id TEXT NOT NULL REFERENCES sessions ON DELETE CASCADE,
        step INTEGER NOT NULL,
        title TEXT NOT NULL,
        summary TEXT NOT NULL,
        event_type TEXT,
        driving_entities_json TEXT DEFAULT '[]',
        state_changes_json TEXT DEFAULT '[]',
        status TEXT DEFAULT 'canon',
        created_at TEXT NOT NULL
    )
    """,
    # -- Preset layer --
    """
    CREATE TABLE IF NOT EXISTS writer_presets (
        preset_id TEXT PRIMARY KEY,
        project_id TEXT,
        name TEXT NOT NULL,
        description TEXT DEFAULT '',
        system_prompt TEXT NOT NULL,
        is_default INTEGER DEFAULT 0,
        created_at TEXT NOT NULL,
        updated_at TEXT NOT NULL
    )
    """,
)

FTS_STATEMENTS = (
    """
    CREATE VIRTUAL TABLE IF NOT EXISTS entities_fts USING fts5(
        name, summary, core_drive, hidden_tension,
        content=entities, tokenize='unicode61'
    )
    """,
    """
    CREATE VIRTUAL TABLE IF NOT EXISTS chapter_content_fts USING fts5(
        title, content,
        content=chapter_content, tokenize='unicode61'
    )
    """,
    """
    CREATE VIRTUAL TABLE IF NOT EXISTS scenes_fts USING fts5(
        title, content,
        content=scenes, tokenize='unicode61'
    )
    """,
    """
    CREATE VIRTUAL TABLE IF NOT EXISTS agent_memory_fts USING fts5(
        summary,
        content=agent_memory, tokenize='unicode61'
    )
    """,
)

TRIGGER_STATEMENTS = (
    # -- entities FTS triggers --
    """
    CREATE TRIGGER IF NOT EXISTS entities_ai AFTER INSERT ON entities BEGIN
        INSERT INTO entities_fts(rowid, name, summary, core_drive, hidden_tension)
        VALUES (new.rowid, new.name, new.summary, new.core_drive, new.hidden_tension);
    END
    """,
    """
    CREATE TRIGGER IF NOT EXISTS entities_au AFTER UPDATE ON entities BEGIN
        INSERT INTO entities_fts(entities_fts, rowid, name, summary, core_drive, hidden_tension)
        VALUES ('delete', old.rowid, old.name, old.summary, old.core_drive, old.hidden_tension);
        INSERT INTO entities_fts(rowid, name, summary, core_drive, hidden_tension)
        VALUES (new.rowid, new.name, new.summary, new.core_drive, new.hidden_tension);
    END
    """,
    """
    CREATE TRIGGER IF NOT EXISTS entities_ad AFTER DELETE ON entities BEGIN
        INSERT INTO entities_fts(entities_fts, rowid, name, summary, core_drive, hidden_tension)
        VALUES ('delete', old.rowid, old.name, old.summary, old.core_drive, old.hidden_tension);
    END
    """,
    # -- chapter_content FTS triggers --
    """
    CREATE TRIGGER IF NOT EXISTS chapter_content_ai AFTER INSERT ON chapter_content BEGIN
        INSERT INTO chapter_content_fts(rowid, title, content)
        VALUES (new.rowid, new.title, new.content);
    END
    """,
    """
    CREATE TRIGGER IF NOT EXISTS chapter_content_au AFTER UPDATE ON chapter_content BEGIN
        INSERT INTO chapter_content_fts(chapter_content_fts, rowid, title, content)
        VALUES ('delete', old.rowid, old.title, old.content);
        INSERT INTO chapter_content_fts(rowid, title, content)
        VALUES (new.rowid, new.title, new.content);
    END
    """,
    """
    CREATE TRIGGER IF NOT EXISTS chapter_content_ad AFTER DELETE ON chapter_content BEGIN
        INSERT INTO chapter_content_fts(chapter_content_fts, rowid, title, content)
        VALUES ('delete', old.rowid, old.title, old.content);
    END
    """,
    # -- scenes FTS triggers --
    """
    CREATE TRIGGER IF NOT EXISTS scenes_ai AFTER INSERT ON scenes BEGIN
        INSERT INTO scenes_fts(rowid, title, content)
        VALUES (new.rowid, new.title, new.content);
    END
    """,
    """
    CREATE TRIGGER IF NOT EXISTS scenes_au AFTER UPDATE ON scenes BEGIN
        INSERT INTO scenes_fts(scenes_fts, rowid, title, content)
        VALUES ('delete', old.rowid, old.title, old.content);
        INSERT INTO scenes_fts(rowid, title, content)
        VALUES (new.rowid, new.title, new.content);
    END
    """,
    """
    CREATE TRIGGER IF NOT EXISTS scenes_ad AFTER DELETE ON scenes BEGIN
        INSERT INTO scenes_fts(scenes_fts, rowid, title, content)
        VALUES ('delete', old.rowid, old.title, old.content);
    END
    """,
    # -- agent_memory FTS triggers --
    """
    CREATE TRIGGER IF NOT EXISTS agent_memory_ai AFTER INSERT ON agent_memory BEGIN
        INSERT INTO agent_memory_fts(rowid, summary)
        VALUES (new.rowid, new.summary);
    END
    """,
    """
    CREATE TRIGGER IF NOT EXISTS agent_memory_au AFTER UPDATE ON agent_memory BEGIN
        INSERT INTO agent_memory_fts(agent_memory_fts, rowid, summary)
        VALUES ('delete', old.rowid, old.summary);
        INSERT INTO agent_memory_fts(rowid, summary)
        VALUES (new.rowid, new.summary);
    END
    """,
    """
    CREATE TRIGGER IF NOT EXISTS agent_memory_ad AFTER DELETE ON agent_memory BEGIN
        INSERT INTO agent_memory_fts(agent_memory_fts, rowid, summary)
        VALUES ('delete', old.rowid, old.summary);
    END
    """,
)

INDEX_STATEMENTS = (
    "CREATE INDEX IF NOT EXISTS idx_entities_name ON entities(name)",
    "CREATE INDEX IF NOT EXISTS idx_entities_type ON entities(entity_type)",
    "CREATE INDEX IF NOT EXISTS idx_entities_importance ON entities(importance_tier)",
    "CREATE INDEX IF NOT EXISTS idx_entity_aliases_entity ON entity_aliases(entity_id)",
    "CREATE INDEX IF NOT EXISTS idx_relationships_source ON relationships(source_id)",
    "CREATE INDEX IF NOT EXISTS idx_relationships_target ON relationships(target_id)",
    "CREATE INDEX IF NOT EXISTS idx_chapter_content_order ON chapter_content(project_id, chapter_order)",
    "CREATE INDEX IF NOT EXISTS idx_scenes_chapter ON scenes(chapter_id, scene_order)",
    "CREATE INDEX IF NOT EXISTS idx_agent_states_session ON agent_states(session_id)",
    "CREATE INDEX IF NOT EXISTS idx_agent_memory_session ON agent_memory(session_id)",
    "CREATE INDEX IF NOT EXISTS idx_world_events_session ON world_events(session_id, step)",
    "CREATE INDEX IF NOT EXISTS idx_writer_presets_project ON writer_presets(project_id)",
)

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _row_to_dict(row: sqlite3.Row | None) -> dict[str, Any] | None:
    if row is None:
        return None
    return dict(row)


def _rows_to_dicts(rows: list[sqlite3.Row]) -> list[dict[str, Any]]:
    return [dict(r) for r in rows]


# ---------------------------------------------------------------------------
# NovelDB
# ---------------------------------------------------------------------------

class NovelDB:
    """Per-project novel database access layer.

    Stateless: every public method opens its own connection via the
    ``connect()`` context manager, following the pattern established in
    ``archive_library_storage.py``.
    """

    def __init__(self) -> None:
        self._uploads_dir: str = Config.UPLOAD_FOLDER

    # -- path helpers -------------------------------------------------------

    def _db_path(self, project_id: str) -> str:
        return os.path.join(
            self._uploads_dir, "projects", project_id, "novel.sqlite3"
        )

    def _ensure_parent_dir(self, project_id: str) -> None:
        os.makedirs(os.path.dirname(self._db_path(project_id)), exist_ok=True)

    # -- connection ---------------------------------------------------------

    @contextmanager
    def connect(self, project_id: str) -> Iterator[sqlite3.Connection]:
        self._ensure_parent_dir(project_id)
        conn = sqlite3.connect(self._db_path(project_id))
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA foreign_keys = ON")
        try:
            yield conn
        finally:
            conn.close()

    # -- schema -------------------------------------------------------------

    def ensure_schema(self, project_id: str) -> None:
        self._ensure_parent_dir(project_id)
        with self.connect(project_id) as conn:
            for stmt in TABLE_STATEMENTS:
                conn.execute(stmt)
            for stmt in FTS_STATEMENTS:
                conn.execute(stmt)
            for stmt in TRIGGER_STATEMENTS:
                conn.execute(stmt)
            for stmt in INDEX_STATEMENTS:
                conn.execute(stmt)
            conn.commit()

    # ======================================================================
    # Entity queries
    # ======================================================================

    def get_entity(
        self,
        project_id: str,
        name: str,
        entity_type: str | None = None,
    ) -> dict[str, Any] | None:
        """Look up an entity by exact name, then by alias."""
        self.ensure_schema(project_id)
        with self.connect(project_id) as conn:
            # Try exact name match
            sql = "SELECT * FROM entities WHERE name = ?"
            params: list[Any] = [name]
            if entity_type is not None:
                sql += " AND entity_type = ?"
                params.append(entity_type)
            row = conn.execute(sql, params).fetchone()
            if row is not None:
                return _row_to_dict(row)

            # Fallback: alias lookup
            sql = (
                "SELECT e.* FROM entities e "
                "JOIN entity_aliases a ON a.entity_id = e.entity_id "
                "WHERE a.alias = ?"
            )
            params = [name]
            if entity_type is not None:
                sql += " AND e.entity_type = ?"
                params.append(entity_type)
            row = conn.execute(sql, params).fetchone()
            return _row_to_dict(row)

    # ======================================================================
    # Relationship queries
    # ======================================================================

    def get_relationship(
        self,
        project_id: str,
        entity_a_name: str,
        entity_b_name: str,
    ) -> list[dict[str, Any]]:
        """Get relationships between two entities (bidirectional)."""
        entity_a = self.get_entity(project_id, entity_a_name)
        entity_b = self.get_entity(project_id, entity_b_name)
        if entity_a is None or entity_b is None:
            return []
        a_id = entity_a["entity_id"]
        b_id = entity_b["entity_id"]
        with self.connect(project_id) as conn:
            rows = conn.execute(
                """
                SELECT * FROM relationships
                WHERE (source_id = ? AND target_id = ?)
                   OR (source_id = ? AND target_id = ?)
                """,
                (a_id, b_id, b_id, a_id),
            ).fetchall()
            return _rows_to_dicts(rows)

    # ======================================================================
    # Chapter queries
    # ======================================================================

    def get_chapter(
        self,
        project_id: str,
        chapter_order: int,
        include_content: bool = False,
    ) -> dict[str, Any] | None:
        self.ensure_schema(project_id)
        with self.connect(project_id) as conn:
            if include_content:
                cols = "cc.*, cm.summary, cm.outline_json, cm.timeline_note, cm.open_threads_json, cm.pov_character"
            else:
                cols = (
                    "cc.chapter_id, cc.project_id, cc.chapter_order, cc.title, "
                    "cc.word_count, cc.status, cc.created_at, cc.updated_at, "
                    "cm.summary, cm.outline_json, cm.timeline_note, cm.open_threads_json, cm.pov_character"
                )
            row = conn.execute(
                f"""
                SELECT {cols}
                FROM chapter_content cc
                LEFT JOIN chapter_meta cm ON cm.chapter_id = cc.chapter_id
                WHERE cc.project_id = ? AND cc.chapter_order = ?
                """,
                (project_id, chapter_order),
            ).fetchone()
            return _row_to_dict(row)

    def list_chapters(self, project_id: str) -> list[dict[str, Any]]:
        self.ensure_schema(project_id)
        with self.connect(project_id) as conn:
            rows = conn.execute(
                """
                SELECT cc.chapter_id, cc.project_id, cc.chapter_order, cc.title,
                       cc.word_count, cc.status, cc.created_at, cc.updated_at,
                       cm.summary, cm.outline_json, cm.timeline_note,
                       cm.open_threads_json, cm.pov_character
                FROM chapter_content cc
                LEFT JOIN chapter_meta cm ON cm.chapter_id = cc.chapter_id
                WHERE cc.project_id = ?
                ORDER BY cc.chapter_order
                """,
                (project_id,),
            ).fetchall()
            return _rows_to_dicts(rows)

    def create_chapter(
        self,
        project_id: str,
        chapter_id: str,
        chapter_order: int,
        title: str = "",
    ) -> None:
        self.ensure_schema(project_id)
        now = _now()
        with self.connect(project_id) as conn:
            conn.execute(
                """
                INSERT INTO chapter_content
                    (chapter_id, project_id, chapter_order, title, content, word_count, status, created_at, updated_at)
                VALUES (?, ?, ?, ?, '', 0, 'draft', ?, ?)
                """,
                (chapter_id, project_id, chapter_order, title, now, now),
            )
            conn.execute(
                """
                INSERT INTO chapter_meta (chapter_id, updated_at)
                VALUES (?, ?)
                """,
                (chapter_id, now),
            )
            conn.commit()

    def update_chapter(self, project_id: str, chapter_id: str, **kwargs: Any) -> None:
        self.ensure_schema(project_id)
        now = _now()
        content_cols = {
            "chapter_order", "title", "content", "word_count", "status",
        }
        meta_cols = {
            "summary", "outline_json", "timeline_note",
            "open_threads_json", "pov_character",
        }
        with self.connect(project_id) as conn:
            cc_updates = {k: v for k, v in kwargs.items() if k in content_cols}
            if cc_updates:
                cc_updates["updated_at"] = now
                set_clause = ", ".join(f"{k} = ?" for k in cc_updates)
                conn.execute(
                    f"UPDATE chapter_content SET {set_clause} WHERE chapter_id = ?",
                    (*cc_updates.values(), chapter_id),
                )

            cm_updates = {k: v for k, v in kwargs.items() if k in meta_cols}
            if cm_updates:
                cm_updates["updated_at"] = now
                set_clause = ", ".join(f"{k} = ?" for k in cm_updates)
                conn.execute(
                    f"UPDATE chapter_meta SET {set_clause} WHERE chapter_id = ?",
                    (*cm_updates.values(), chapter_id),
                )
            conn.commit()

    def delete_chapter(self, project_id: str, chapter_id: str) -> None:
        self.ensure_schema(project_id)
        with self.connect(project_id) as conn:
            conn.execute("DELETE FROM chapter_content WHERE chapter_id = ?", (chapter_id,))
            conn.commit()

    # ======================================================================
    # Scene queries
    # ======================================================================

    def list_scenes(
        self, project_id: str, chapter_id: str
    ) -> list[dict[str, Any]]:
        self.ensure_schema(project_id)
        with self.connect(project_id) as conn:
            rows = conn.execute(
                """
                SELECT scene_id, scene_order, title, word_count, status
                FROM scenes
                WHERE chapter_id = ?
                ORDER BY scene_order
                """,
                (chapter_id,),
            ).fetchall()
            return _rows_to_dicts(rows)

    def get_scene(
        self, project_id: str, scene_id: str
    ) -> dict[str, Any] | None:
        self.ensure_schema(project_id)
        with self.connect(project_id) as conn:
            row = conn.execute(
                "SELECT * FROM scenes WHERE scene_id = ?", (scene_id,)
            ).fetchone()
            return _row_to_dict(row)

    def ensure_chapter(self, project_id: str, chapter_id: str, chapter_order: int = 0) -> None:
        """Create a chapter_content row if it doesn't exist yet."""
        self.ensure_schema(project_id)
        now = _now()
        with self.connect(project_id) as conn:
            existing = conn.execute(
                "SELECT 1 FROM chapter_content WHERE chapter_id = ?", (chapter_id,)
            ).fetchone()
            if existing:
                return
            # Auto-assign chapter_order if not provided
            if not chapter_order:
                row = conn.execute(
                    "SELECT COALESCE(MAX(chapter_order), 0) + 1 FROM chapter_content WHERE project_id = ?",
                    (project_id,),
                ).fetchone()
                chapter_order = row[0] if row else 1
            conn.execute(
                """
                INSERT INTO chapter_content
                    (chapter_id, project_id, chapter_order, title, content,
                     word_count, status, created_at, updated_at)
                VALUES (?, ?, ?, ?, '', 0, 'draft', ?, ?)
                """,
                (chapter_id, project_id, chapter_order, "", now, now),
            )
            conn.execute(
                "INSERT OR IGNORE INTO chapter_meta (chapter_id, updated_at) VALUES (?, ?)",
                (chapter_id, now),
            )
            conn.commit()

    def upsert_scene(
        self,
        project_id: str,
        scene_id: str,
        chapter_id: str,
        scene_order: int,
        title: str = "",
        content: str = "",
        pov_entity_id: str | None = None,
        location: str | None = None,
        involved_entities_json: str = "[]",
        status: str = "draft",
        writing_brief_json: str | None = None,
    ) -> None:
        self.ensure_schema(project_id)
        now = _now()
        word_count = len(content)
        with self.connect(project_id) as conn:
            conn.execute(
                """
                INSERT OR REPLACE INTO scenes
                    (scene_id, chapter_id, scene_order, title, content, word_count,
                     pov_entity_id, location, involved_entities_json, status,
                     writing_brief_json, created_at, updated_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    scene_id, chapter_id, scene_order, title, content,
                    word_count, pov_entity_id, location,
                    involved_entities_json, status, writing_brief_json,
                    now, now,
                ),
            )
            conn.commit()

    def delete_scene(self, project_id: str, scene_id: str) -> None:
        self.ensure_schema(project_id)
        with self.connect(project_id) as conn:
            conn.execute("DELETE FROM scenes WHERE scene_id = ?", (scene_id,))
            conn.commit()

    def reorder_scenes(
        self, project_id: str, chapter_id: str, scene_ids: list[str]
    ) -> None:
        self.ensure_schema(project_id)
        now = _now()
        with self.connect(project_id) as conn:
            # Shift all to negative temporaries to avoid UNIQUE conflicts
            for idx, sid in enumerate(scene_ids):
                conn.execute(
                    "UPDATE scenes SET scene_order = ?, updated_at = ? WHERE scene_id = ? AND chapter_id = ?",
                    (-(idx + 1), now, sid, chapter_id),
                )
            # Now assign final positions
            for idx, sid in enumerate(scene_ids):
                conn.execute(
                    "UPDATE scenes SET scene_order = ? WHERE scene_id = ? AND chapter_id = ?",
                    (idx, sid, chapter_id),
                )
            conn.commit()

    def get_recent_scenes(
        self,
        project_id: str,
        chapter_id: str,
        scene_order: int,
        count: int = 2,
    ) -> list[dict[str, Any]]:
        """Get *count* scenes before *scene_order*, crossing chapter boundaries."""
        self.ensure_schema(project_id)
        result: list[dict[str, Any]] = []
        with self.connect(project_id) as conn:
            # Scenes in current chapter before the given position
            rows = conn.execute(
                """
                SELECT * FROM scenes
                WHERE chapter_id = ? AND scene_order < ?
                ORDER BY scene_order DESC
                LIMIT ?
                """,
                (chapter_id, scene_order, count),
            ).fetchall()
            result.extend(_rows_to_dicts(rows))

            if len(result) < count:
                # Find the previous chapter
                cur_chapter = conn.execute(
                    "SELECT * FROM chapter_content WHERE chapter_id = ?",
                    (chapter_id,),
                ).fetchone()
                if cur_chapter is not None:
                    prev_chapter = conn.execute(
                        """
                        SELECT * FROM chapter_content
                        WHERE project_id = ? AND chapter_order < ?
                        ORDER BY chapter_order DESC
                        LIMIT 1
                        """,
                        (project_id, cur_chapter["chapter_order"]),
                    ).fetchone()
                    if prev_chapter is not None:
                        remaining = count - len(result)
                        extra = conn.execute(
                            """
                            SELECT * FROM scenes
                            WHERE chapter_id = ?
                            ORDER BY scene_order DESC
                            LIMIT ?
                            """,
                            (prev_chapter["chapter_id"], remaining),
                        ).fetchall()
                        result.extend(_rows_to_dicts(extra))

        # Return in chronological order (ascending scene_order)
        result.reverse()
        return result

    # ======================================================================
    # FTS search
    # ======================================================================

    def search_fts(
        self,
        project_id: str,
        query: str,
        scope: str = "all",
        limit: int = 10,
    ) -> list[dict[str, Any]]:
        self.ensure_schema(project_id)
        results: list[dict[str, Any]] = []
        with self.connect(project_id) as conn:
            if scope in ("entities", "all"):
                rows = conn.execute(
                    """
                    SELECT e.entity_id, e.name, snippet(entities_fts, 1, '<b>', '</b>', '...', 32) AS snippet
                    FROM entities_fts
                    JOIN entities e ON e.rowid = entities_fts.rowid
                    WHERE entities_fts MATCH ?
                    LIMIT ?
                    """,
                    (query, limit),
                ).fetchall()
                for r in rows:
                    results.append({
                        "source": "entities",
                        "name": r["name"],
                        "snippet": r["snippet"],
                    })

            if scope in ("chapters", "all"):
                rows = conn.execute(
                    """
                    SELECT cc.chapter_id, cc.title,
                           snippet(chapter_content_fts, 1, '<b>', '</b>', '...', 32) AS snippet
                    FROM chapter_content_fts
                    JOIN chapter_content cc ON cc.rowid = chapter_content_fts.rowid
                    WHERE chapter_content_fts MATCH ?
                    LIMIT ?
                    """,
                    (query, limit),
                ).fetchall()
                for r in rows:
                    results.append({
                        "source": "chapters",
                        "title": r["title"],
                        "snippet": r["snippet"],
                    })

            if scope in ("scenes", "all"):
                rows = conn.execute(
                    """
                    SELECT s.scene_id, s.title,
                           snippet(scenes_fts, 1, '<b>', '</b>', '...', 32) AS snippet
                    FROM scenes_fts
                    JOIN scenes s ON s.rowid = scenes_fts.rowid
                    WHERE scenes_fts MATCH ?
                    LIMIT ?
                    """,
                    (query, limit),
                ).fetchall()
                for r in rows:
                    results.append({
                        "source": "scenes",
                        "title": r["title"],
                        "snippet": r["snippet"],
                    })

            if scope in ("memory", "all"):
                rows = conn.execute(
                    """
                    SELECT am.memory_id,
                           snippet(agent_memory_fts, 0, '<b>', '</b>', '...', 32) AS snippet
                    FROM agent_memory_fts
                    JOIN agent_memory am ON am.rowid = agent_memory_fts.rowid
                    WHERE agent_memory_fts MATCH ?
                    LIMIT ?
                    """,
                    (query, limit),
                ).fetchall()
                for r in rows:
                    results.append({
                        "source": "memory",
                        "name": r["memory_id"],
                        "snippet": r["snippet"],
                    })

        return results

    # ======================================================================
    # World state
    # ======================================================================

    def get_world_state(
        self,
        project_id: str,
        session_id: str,
        entity_id: str | None = None,
    ) -> dict[str, Any]:
        self.ensure_schema(project_id)
        with self.connect(project_id) as conn:
            session_row = conn.execute(
                "SELECT * FROM sessions WHERE session_id = ?", (session_id,)
            ).fetchone()
            session = _row_to_dict(session_row)

            if entity_id is not None:
                state_rows = conn.execute(
                    "SELECT * FROM agent_states WHERE session_id = ? AND entity_id = ?",
                    (session_id, entity_id),
                ).fetchall()
            else:
                state_rows = conn.execute(
                    "SELECT * FROM agent_states WHERE session_id = ?",
                    (session_id,),
                ).fetchall()

            events = conn.execute(
                """
                SELECT * FROM world_events
                WHERE session_id = ?
                ORDER BY step DESC
                LIMIT 10
                """,
                (session_id,),
            ).fetchall()

            return {
                "session": session,
                "agent_states": _rows_to_dicts(state_rows),
                "recent_events": _rows_to_dicts(events),
            }

    # ======================================================================
    # Open threads
    # ======================================================================

    def get_open_threads(
        self, project_id: str, up_to_chapter: int
    ) -> list[str]:
        self.ensure_schema(project_id)
        threads: list[str] = []
        with self.connect(project_id) as conn:
            rows = conn.execute(
                """
                SELECT cm.open_threads_json
                FROM chapter_meta cm
                JOIN chapter_content cc ON cc.chapter_id = cm.chapter_id
                WHERE cc.project_id = ? AND cc.chapter_order <= ?
                ORDER BY cc.chapter_order
                """,
                (project_id, up_to_chapter),
            ).fetchall()
            for r in rows:
                raw = r["open_threads_json"]
                if raw:
                    try:
                        parsed = json.loads(raw)
                        if isinstance(parsed, list):
                            threads.extend(parsed)
                    except (json.JSONDecodeError, TypeError):
                        pass
        return threads

    # ======================================================================
    # Preset CRUD
    # ======================================================================

    def list_presets(self, project_id: str) -> list[dict[str, Any]]:
        self.ensure_schema(project_id)
        with self.connect(project_id) as conn:
            rows = conn.execute(
                "SELECT * FROM writer_presets WHERE project_id = ? OR project_id IS NULL",
                (project_id,),
            ).fetchall()
            return _rows_to_dicts(rows)

    def create_preset(
        self,
        project_id: str | None,
        preset_id: str,
        name: str,
        system_prompt: str,
        description: str = "",
        is_default: int = 0,
    ) -> None:
        # Use the project_id to resolve the DB; fall back to a provided one
        db_project = project_id or "__global__"
        self.ensure_schema(db_project)
        now = _now()
        with self.connect(db_project) as conn:
            conn.execute(
                """
                INSERT INTO writer_presets
                    (preset_id, project_id, name, description, system_prompt, is_default, created_at, updated_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (preset_id, project_id, name, description, system_prompt, is_default, now, now),
            )
            conn.commit()

    def update_preset(self, project_id: str, preset_id: str, **kwargs: Any) -> None:
        self.ensure_schema(project_id)
        now = _now()
        allowed = {"name", "description", "system_prompt", "is_default"}
        updates = {k: v for k, v in kwargs.items() if k in allowed}
        if not updates:
            return
        updates["updated_at"] = now
        set_clause = ", ".join(f"{k} = ?" for k in updates)
        with self.connect(project_id) as conn:
            conn.execute(
                f"UPDATE writer_presets SET {set_clause} WHERE preset_id = ?",
                (*updates.values(), preset_id),
            )
            conn.commit()

    def delete_preset(self, project_id: str, preset_id: str) -> None:
        self.ensure_schema(project_id)
        with self.connect(project_id) as conn:
            conn.execute("DELETE FROM writer_presets WHERE preset_id = ?", (preset_id,))
            conn.commit()

    # ======================================================================
    # Compile chapter
    # ======================================================================

    def compile_chapter(self, project_id: str, chapter_id: str) -> None:
        """Concatenate all scenes into chapter_content.content."""
        self.ensure_schema(project_id)
        with self.connect(project_id) as conn:
            rows = conn.execute(
                "SELECT content FROM scenes WHERE chapter_id = ? ORDER BY scene_order",
                (chapter_id,),
            ).fetchall()
            full_content = "\n\n".join(r["content"] for r in rows)
            word_count = len(full_content)
            now = _now()
            conn.execute(
                "UPDATE chapter_content SET content = ?, word_count = ?, updated_at = ? WHERE chapter_id = ?",
                (full_content, word_count, now, chapter_id),
            )
            conn.commit()
