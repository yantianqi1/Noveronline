"""Migrate scattered SQLite databases and JSON files into unified novel.sqlite3.

Consolidates data from up to 6 source locations per project (plus one global
database) into the per-project ``novel.sqlite3`` managed by :class:`NovelDB`.

Usage::

    from app.services.writer_agent.novel_db_migration import migrate_project
    summary = migrate_project("some-project-id")
    # {"entities": 12, "relationships": 5, ...}
"""

from __future__ import annotations

import json
import logging
import os
import sqlite3
from contextlib import contextmanager
from datetime import datetime, timezone
from typing import Any, Iterator

from ...config import Config
from .novel_db import NovelDB

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


@contextmanager
def _open_readonly(db_path: str) -> Iterator[sqlite3.Connection]:
    """Open an existing SQLite database in read-only mode."""
    conn = sqlite3.connect(f"file:{db_path}?mode=ro", uri=True)
    conn.row_factory = sqlite3.Row
    try:
        yield conn
    finally:
        conn.close()


def _table_exists(conn: sqlite3.Connection, table: str) -> bool:
    row = conn.execute(
        "SELECT 1 FROM sqlite_master WHERE type='table' AND name=?",
        (table,),
    ).fetchone()
    return row is not None


def _uploads_dir() -> str:
    return Config.UPLOAD_FOLDER


def _system_db(filename: str) -> str:
    return os.path.join(_uploads_dir(), "system", filename)


def _project_dir(project_id: str) -> str:
    return os.path.join(_uploads_dir(), "projects", project_id)


# ---------------------------------------------------------------------------
# Clear target tables (idempotent reset)
# ---------------------------------------------------------------------------

_CLEAR_ORDER = (
    "entity_evidence",
    "entity_labels",
    "entity_aliases",
    "relationships",
    "agent_memory",
    "agent_states",
    "world_events",
    "sessions",
    "chapter_meta",
    "chapter_content",
    "entities",
)


def _clear_tables(conn: sqlite3.Connection) -> None:
    """Delete all rows from migration-managed tables."""
    conn.execute("PRAGMA foreign_keys = OFF")
    for table in _CLEAR_ORDER:
        conn.execute(f"DELETE FROM {table}")
    conn.execute("PRAGMA foreign_keys = ON")
    conn.commit()


# ---------------------------------------------------------------------------
# 1. archive_library  -->  entities + entity_aliases
# ---------------------------------------------------------------------------

def _migrate_archive_library(
    project_id: str,
    conn: sqlite3.Connection,
    counts: dict[str, int],
) -> dict[str, str]:
    """Returns mapping of archive_id -> entity_id for downstream use."""
    db_path = _system_db(Config.ARCHIVE_LIBRARY_DB_FILENAME)
    entity_map: dict[str, str] = {}  # archive_id -> entity_id
    if not os.path.exists(db_path):
        logger.info("archive_library.sqlite3 not found, skipping")
        return entity_map

    now = _now()
    with _open_readonly(db_path) as src:
        if not _table_exists(src, "archive_library"):
            return entity_map

        rows = src.execute(
            "SELECT * FROM archive_library WHERE project_id = ?",
            (project_id,),
        ).fetchall()

        for row in rows:
            entity_id = row["archive_id"]
            importance = (
                row["selected_importance_tier"]
                if row["selected_importance_tier"]
                else row["importance_tier"]
            )
            conn.execute(
                """
                INSERT OR IGNORE INTO entities
                    (entity_id, project_id, name, entity_type, importance_tier,
                     summary, core_drive, surface_mask, hidden_tension,
                     profile_json, created_at, updated_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    entity_id,
                    project_id,
                    row["entity_name"],
                    row["entity_type"],
                    importance or "minor",
                    row["entity_role"],
                    row["core_drive"],
                    row["surface_mask"],
                    row["hidden_tension"],
                    row["template_payload_json"] or "{}",
                    row["synced_at"] or now,
                    row["synced_at"] or now,
                ),
            )
            entity_map[entity_id] = entity_id
            counts["entities"] = counts.get("entities", 0) + 1

            # Insert entity name as an alias for lookup convenience
            conn.execute(
                "INSERT OR IGNORE INTO entity_aliases (alias, entity_id) VALUES (?, ?)",
                (row["entity_name"], entity_id),
            )
            counts["entity_aliases"] = counts.get("entity_aliases", 0) + 1

    conn.commit()
    return entity_map


# ---------------------------------------------------------------------------
# 2. archive_agent_memory  -->  agent_memory
# ---------------------------------------------------------------------------

def _migrate_archive_agent_memory(
    project_id: str,
    conn: sqlite3.Connection,
    counts: dict[str, int],
    entity_map: dict[str, str],
) -> None:
    db_path = _system_db(Config.ARCHIVE_LIBRARY_DB_FILENAME)
    if not os.path.exists(db_path):
        return

    with _open_readonly(db_path) as src:
        if not _table_exists(src, "archive_agent_memory"):
            return

        # Only migrate memories for archives belonging to this project
        archive_ids = list(entity_map.keys())
        if not archive_ids:
            return

        placeholders = ",".join("?" for _ in archive_ids)
        rows = src.execute(
            f"SELECT * FROM archive_agent_memory WHERE archive_id IN ({placeholders})",
            archive_ids,
        ).fetchall()

        for row in rows:
            # Use a synthetic session_id for canon-layer memories
            session_id = f"__archive_canon__{project_id}"
            conn.execute(
                """
                INSERT OR IGNORE INTO sessions
                    (session_id, project_id, session_type, title, status,
                     config_json, created_at, updated_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    session_id, project_id, "archive_canon",
                    "Archive canon memory", "completed", "{}",
                    _now(), _now(),
                ),
            )
            conn.execute(
                """
                INSERT OR IGNORE INTO agent_memory
                    (memory_id, session_id, entity_id, memory_type,
                     summary, detail_json, salience, source_kind, created_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    row["memory_id"],
                    session_id,
                    row["archive_id"],  # entity_id = archive_id
                    row["memory_type"],
                    row["summary"],
                    row["detail_json"] or "{}",
                    row["salience"],
                    row["source_kind"],
                    row["created_at"],
                ),
            )
            counts["agent_memory"] = counts.get("agent_memory", 0) + 1

    conn.commit()


# ---------------------------------------------------------------------------
# 3. chapter_meta.sqlite3  -->  chapter_content + chapter_meta
# ---------------------------------------------------------------------------

def _migrate_chapter_meta(
    project_id: str,
    conn: sqlite3.Connection,
    counts: dict[str, int],
) -> None:
    db_path = _system_db("chapter_meta.sqlite3")
    if not os.path.exists(db_path):
        logger.info("chapter_meta.sqlite3 not found, skipping")
        return

    now = _now()
    with _open_readonly(db_path) as src:
        if not _table_exists(src, "chapter_meta"):
            return

        rows = src.execute(
            "SELECT * FROM chapter_meta WHERE project_id = ? ORDER BY chapter_order",
            (project_id,),
        ).fetchall()

        for row in rows:
            chapter_id = row["chapter_id"] or f"ch_{project_id}_{row['chapter_order']}"
            conn.execute(
                """
                INSERT OR IGNORE INTO chapter_content
                    (chapter_id, project_id, chapter_order, title, content,
                     word_count, status, created_at, updated_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    chapter_id,
                    project_id,
                    row["chapter_order"],
                    row["title"] or "",
                    "",  # content filled later from chapter_segments.json
                    0,
                    "draft",
                    row["created_at"] or now,
                    row["updated_at"] or now,
                ),
            )
            conn.execute(
                """
                INSERT OR IGNORE INTO chapter_meta
                    (chapter_id, summary, outline_json, timeline_note,
                     open_threads_json, pov_character, updated_at)
                VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    chapter_id,
                    row["summary_text"] or "",
                    "[]",
                    row["timeline_note"] or "",
                    row["open_threads_json"] or "[]",
                    None,
                    row["updated_at"] or now,
                ),
            )
            counts["chapter_content"] = counts.get("chapter_content", 0) + 1
            counts["chapter_meta"] = counts.get("chapter_meta", 0) + 1

    conn.commit()


# ---------------------------------------------------------------------------
# 4. chapter_history_item  -->  world_events
# ---------------------------------------------------------------------------

def _migrate_chapter_history_items(
    project_id: str,
    conn: sqlite3.Connection,
    counts: dict[str, int],
) -> None:
    db_path = _system_db("chapter_meta.sqlite3")
    if not os.path.exists(db_path):
        return

    now = _now()
    with _open_readonly(db_path) as src:
        if not _table_exists(src, "chapter_history_item"):
            return

        rows = src.execute(
            "SELECT * FROM chapter_history_item WHERE project_id = ? ORDER BY chapter_order",
            (project_id,),
        ).fetchall()

        if not rows:
            return

        # Create a synthetic session for chapter history events
        session_id = f"__chapter_history__{project_id}"
        conn.execute(
            """
            INSERT OR IGNORE INTO sessions
                (session_id, project_id, session_type, title, status,
                 config_json, created_at, updated_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                session_id, project_id, "chapter_history",
                "Chapter history events", "completed", "{}",
                now, now,
            ),
        )

        for row in rows:
            event_id = f"evt_chi_{row['id']}"
            conn.execute(
                """
                INSERT OR IGNORE INTO world_events
                    (event_id, session_id, step, title, summary,
                     event_type, driving_entities_json, state_changes_json,
                     status, created_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    event_id,
                    session_id,
                    row["chapter_order"],
                    row["subject_key"] or row["item_type"],
                    row["summary_text"] or "",
                    row["item_type"],  # item_type -> event_type
                    row["related_entities_json"] or "[]",
                    "[]",
                    "canon",
                    row["created_at"] or now,
                ),
            )
            counts["world_events"] = counts.get("world_events", 0) + 1

    conn.commit()


# ---------------------------------------------------------------------------
# 5. story_graph.sqlite3  -->  entities (supplement) + relationships +
#                               entity_evidence + entity_aliases + entity_labels
# ---------------------------------------------------------------------------

def _migrate_story_graph(
    project_id: str,
    conn: sqlite3.Connection,
    counts: dict[str, int],
) -> None:
    db_path = os.path.join(_project_dir(project_id), "story_graph.sqlite3")
    if not os.path.exists(db_path):
        logger.info("story_graph.sqlite3 not found for project %s, skipping", project_id)
        return

    now = _now()
    with _open_readonly(db_path) as src:
        # -- Build a set of existing entity names (case-insensitive) --
        existing_names: set[str] = set()
        for row in conn.execute("SELECT name FROM entities").fetchall():
            existing_names.add(row["name"].lower())

        # -- graph_nodes -> entities (supplement only) --
        node_uuid_to_entity_id: dict[str, str] = {}
        if _table_exists(src, "graph_nodes"):
            nodes = src.execute("SELECT * FROM graph_nodes").fetchall()
            for node in nodes:
                # Check if this entity already exists (from archive)
                existing = conn.execute(
                    "SELECT entity_id FROM entities WHERE LOWER(name) = ?",
                    (node["name"].lower(),),
                ).fetchone()

                if existing:
                    node_uuid_to_entity_id[node["uuid"]] = existing["entity_id"]
                else:
                    entity_id = node["uuid"]
                    attrs = {}
                    try:
                        attrs = json.loads(node["attributes_json"]) if node["attributes_json"] else {}
                    except (json.JSONDecodeError, TypeError):
                        pass

                    entity_type = "character"
                    # Try to infer type from labels
                    if _table_exists(src, "graph_node_labels"):
                        label_rows = src.execute(
                            "SELECT label FROM graph_node_labels WHERE node_uuid = ?",
                            (node["uuid"],),
                        ).fetchall()
                        labels = [r["label"] for r in label_rows]
                        for label in labels:
                            ll = label.lower()
                            if ll in ("organization", "faction", "group"):
                                entity_type = "organization"
                                break
                            if ll in ("location", "place"):
                                entity_type = "location"
                                break
                            if ll in ("item", "artifact", "object"):
                                entity_type = "item"
                                break

                    conn.execute(
                        """
                        INSERT OR IGNORE INTO entities
                            (entity_id, project_id, name, entity_type,
                             importance_tier, summary, profile_json,
                             created_at, updated_at)
                        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                        """,
                        (
                            entity_id,
                            project_id,
                            node["name"],
                            entity_type,
                            "minor",
                            node["summary"] or "",
                            json.dumps(attrs, ensure_ascii=False),
                            now, now,
                        ),
                    )
                    node_uuid_to_entity_id[node["uuid"]] = entity_id
                    existing_names.add(node["name"].lower())
                    counts["entities"] = counts.get("entities", 0) + 1

        # -- graph_edges -> relationships --
        if _table_exists(src, "graph_edges"):
            edges = src.execute("SELECT * FROM graph_edges").fetchall()
            for edge in edges:
                source_id = node_uuid_to_entity_id.get(edge["source_node_uuid"])
                target_id = node_uuid_to_entity_id.get(edge["target_node_uuid"])
                if not source_id or not target_id:
                    continue
                conn.execute(
                    """
                    INSERT OR IGNORE INTO relationships
                        (relation_id, source_id, target_id, relation_type,
                         description, updated_at)
                    VALUES (?, ?, ?, ?, ?, ?)
                    """,
                    (
                        edge["uuid"],
                        source_id,
                        target_id,
                        edge["name"],
                        edge["fact"] or "",
                        now,
                    ),
                )
                counts["relationships"] = counts.get("relationships", 0) + 1

        # -- graph_evidence -> entity_evidence --
        if _table_exists(src, "graph_evidence"):
            evidence_rows = src.execute("SELECT * FROM graph_evidence").fetchall()
            for idx, ev in enumerate(evidence_rows):
                owner_id = node_uuid_to_entity_id.get(ev["owner_uuid"], ev["owner_uuid"])
                evidence_id = f"ev_{ev['owner_kind']}_{ev['owner_uuid']}_{idx}"
                conn.execute(
                    """
                    INSERT OR IGNORE INTO entity_evidence
                        (evidence_id, owner_id, owner_type, chapter_id,
                         snippet, created_at)
                    VALUES (?, ?, ?, ?, ?, ?)
                    """,
                    (
                        evidence_id,
                        owner_id,
                        ev["owner_kind"],
                        ev["chapter_id"] or "",
                        ev["snippet"] or "",
                        now,
                    ),
                )
                counts["entity_evidence"] = counts.get("entity_evidence", 0) + 1

        # -- graph_aliases -> entity_aliases --
        if _table_exists(src, "graph_aliases"):
            alias_rows = src.execute("SELECT * FROM graph_aliases").fetchall()
            for al in alias_rows:
                entity_id = node_uuid_to_entity_id.get(al["node_uuid"])
                if not entity_id:
                    continue
                conn.execute(
                    "INSERT OR IGNORE INTO entity_aliases (alias, entity_id) VALUES (?, ?)",
                    (al["alias"], entity_id),
                )
                counts["entity_aliases"] = counts.get("entity_aliases", 0) + 1

        # -- graph_node_labels -> entity_labels --
        if _table_exists(src, "graph_node_labels"):
            label_rows = src.execute("SELECT * FROM graph_node_labels").fetchall()
            for lb in label_rows:
                entity_id = node_uuid_to_entity_id.get(lb["node_uuid"])
                if not entity_id:
                    continue
                conn.execute(
                    "INSERT OR IGNORE INTO entity_labels (entity_id, label) VALUES (?, ?)",
                    (entity_id, lb["label"]),
                )
                counts["entity_labels"] = counts.get("entity_labels", 0) + 1

    conn.commit()


# ---------------------------------------------------------------------------
# 6. runtime.sqlite3  -->  agent_states + agent_memory
# ---------------------------------------------------------------------------

def _migrate_worldline_runtime(
    project_id: str,
    conn: sqlite3.Connection,
    counts: dict[str, int],
) -> None:
    db_path = os.path.join(
        _project_dir(project_id), "worldlines", "runtime.sqlite3"
    )
    if not os.path.exists(db_path):
        logger.info("runtime.sqlite3 not found for project %s, skipping", project_id)
        return

    now = _now()
    with _open_readonly(db_path) as src:
        # -- agent_registry -> agent_states --
        if _table_exists(src, "agent_registry"):
            agents = src.execute("SELECT * FROM agent_registry").fetchall()
            # Collect unique session IDs and ensure sessions exist
            session_ids: set[str] = set()
            for agent in agents:
                sid = agent["session_id"]
                if sid not in session_ids:
                    session_ids.add(sid)
                    conn.execute(
                        """
                        INSERT OR IGNORE INTO sessions
                            (session_id, project_id, session_type, title,
                             status, config_json, created_at, updated_at)
                        VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                        """,
                        (
                            sid, project_id, "worldline",
                            f"Worldline session {sid}", "completed", "{}",
                            agent["created_at"] or now,
                            agent["updated_at"] or now,
                        ),
                    )

            for agent in agents:
                state_id = f"as_{agent['session_id']}_{agent['branch_id']}_{agent['agent_id']}"
                entity_id = agent["source_archive_id"] or agent["agent_id"]
                conn.execute(
                    """
                    INSERT OR IGNORE INTO agent_states
                        (state_id, session_id, entity_id, state_json,
                         status, version, updated_at)
                    VALUES (?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        state_id,
                        agent["session_id"],
                        entity_id,
                        agent["state_json"] or "{}",
                        agent["status"] or "active",
                        agent["state_version"],
                        agent["updated_at"] or now,
                    ),
                )
                counts["agent_states"] = counts.get("agent_states", 0) + 1

        # -- agent_episodic_memory -> agent_memory --
        if _table_exists(src, "agent_episodic_memory"):
            memories = src.execute("SELECT * FROM agent_episodic_memory").fetchall()
            for mem in memories:
                # Ensure the session exists
                conn.execute(
                    """
                    INSERT OR IGNORE INTO sessions
                        (session_id, project_id, session_type, title,
                         status, config_json, created_at, updated_at)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        mem["session_id"], project_id, "worldline",
                        f"Worldline session {mem['session_id']}",
                        "completed", "{}", mem["created_at"] or now, now,
                    ),
                )
                entity_id = mem["archive_id"] or mem["agent_id"]
                conn.execute(
                    """
                    INSERT OR IGNORE INTO agent_memory
                        (memory_id, session_id, entity_id, memory_type,
                         summary, detail_json, salience, source_kind,
                         created_at)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        mem["memory_id"],
                        mem["session_id"],
                        entity_id,
                        mem["memory_type"],
                        mem["summary"],
                        mem["detail_json"] or "{}",
                        mem["salience"],
                        mem["source_kind"],
                        mem["created_at"],
                    ),
                )
                counts["agent_memory"] = counts.get("agent_memory", 0) + 1

    conn.commit()


# ---------------------------------------------------------------------------
# 7. chapter_segments.json  -->  chapter_content (fill content)
# ---------------------------------------------------------------------------

def _migrate_chapter_segments(
    project_id: str,
    conn: sqlite3.Connection,
    counts: dict[str, int],
) -> None:
    json_path = os.path.join(_project_dir(project_id), "chapter_segments.json")
    if not os.path.exists(json_path):
        logger.info("chapter_segments.json not found for project %s, skipping", project_id)
        return

    now = _now()
    try:
        with open(json_path, "r", encoding="utf-8") as f:
            data = json.load(f)
    except (json.JSONDecodeError, OSError) as exc:
        logger.warning("Failed to read chapter_segments.json: %s", exc)
        return

    chapters = data if isinstance(data, list) else data.get("chapters", [])

    for idx, chapter in enumerate(chapters):
        if not isinstance(chapter, dict):
            continue
        content = chapter.get("content", "")
        if not content:
            continue

        chapter_order = chapter.get("chapter_order", chapter.get("index", idx))
        # Try to find existing chapter_content row by order
        existing = conn.execute(
            "SELECT chapter_id FROM chapter_content WHERE project_id = ? AND chapter_order = ?",
            (project_id, chapter_order),
        ).fetchone()

        if existing:
            word_count = len(content)
            conn.execute(
                """
                UPDATE chapter_content
                SET content = ?, word_count = ?, updated_at = ?
                WHERE chapter_id = ?
                """,
                (content, word_count, now, existing["chapter_id"]),
            )
        else:
            chapter_id = chapter.get("chapter_id", f"ch_seg_{project_id}_{chapter_order}")
            title = chapter.get("title", "")
            word_count = len(content)
            conn.execute(
                """
                INSERT OR IGNORE INTO chapter_content
                    (chapter_id, project_id, chapter_order, title, content,
                     word_count, status, created_at, updated_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    chapter_id, project_id, chapter_order, title,
                    content, word_count, "draft", now, now,
                ),
            )
            # Also create a minimal chapter_meta row
            conn.execute(
                "INSERT OR IGNORE INTO chapter_meta (chapter_id, updated_at) VALUES (?, ?)",
                (chapter_id, now),
            )
            counts["chapter_content"] = counts.get("chapter_content", 0) + 1

        counts["chapter_segments"] = counts.get("chapter_segments", 0) + 1

    conn.commit()


# ---------------------------------------------------------------------------
# Public entry point
# ---------------------------------------------------------------------------

def migrate_project(project_id: str) -> dict[str, int]:
    """Migrate all legacy data for *project_id* into ``novel.sqlite3``.

    Returns a summary dict with counts per table, e.g.
    ``{"entities": 12, "relationships": 5, ...}``.

    The migration is idempotent: target tables are cleared before inserting.
    Source databases are never modified.
    """
    logger.info("Starting migration for project %s", project_id)
    counts: dict[str, int] = {}

    db = NovelDB()
    db.ensure_schema(project_id)

    with db.connect(project_id) as conn:
        _clear_tables(conn)

        # 1 + 2: archive_library -> entities / entity_aliases
        entity_map = _migrate_archive_library(project_id, conn, counts)

        # 2b: archive_agent_memory -> agent_memory
        _migrate_archive_agent_memory(project_id, conn, counts, entity_map)

        # 3: chapter_meta.sqlite3 -> chapter_content + chapter_meta
        _migrate_chapter_meta(project_id, conn, counts)

        # 4: chapter_history_item -> world_events
        _migrate_chapter_history_items(project_id, conn, counts)

        # 5: story_graph.sqlite3 -> entities (supplement) + relationships +
        #    entity_evidence + entity_aliases + entity_labels
        _migrate_story_graph(project_id, conn, counts)

        # 6: runtime.sqlite3 -> agent_states + agent_memory
        _migrate_worldline_runtime(project_id, conn, counts)

        # 7: chapter_segments.json -> chapter_content (fill content)
        _migrate_chapter_segments(project_id, conn, counts)

    logger.info("Migration complete for project %s: %s", project_id, counts)
    return counts
