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
    "worldline_branches",
    "sessions",
    "chapter_meta",
    "chapter_content",
    "entities",
    "plot_threads",
    "narrative_arcs",
    "project_meta",
    # Timeline tables
    "character_events",
    "relationship_events",
    "thread_lifecycle",
    "world_rule_evidence",
    "consistency_notes",
    "volume_summaries",
    "segment_summaries",
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
                     profile_json,
                     agent_behavior_hint, relationship_summary_text,
                     notable_risks_json,
                     created_at, updated_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
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
                    row["agent_behavior_hint"] or None,
                    row["relationship_summary"] or None,
                    row["notable_risks_json"] or "[]",
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

        # Pre-load chapter_history_items grouped by chapter_order for outline building
        history_by_chapter: dict[int, list[dict]] = {}
        if _table_exists(src, "chapter_history_item"):
            history_rows = src.execute(
                "SELECT * FROM chapter_history_item WHERE project_id = ? ORDER BY chapter_order, id",
                (project_id,),
            ).fetchall()
            for h in history_rows:
                ch_order = h["chapter_order"]
                history_by_chapter.setdefault(ch_order, []).append(dict(h))

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

            # Build outline_json, key_events, character_state_updates,
            # relationship_updates from chapter_history_items
            ch_order = row["chapter_order"]
            items = history_by_chapter.get(ch_order, [])
            outline_entries = []
            key_events = []
            char_state_updates = []
            rel_updates = []
            pov_candidates: dict[str, int] = {}

            for item in items:
                item_type = item.get("item_type", "")
                subject = item.get("subject_key", "")
                summary = item.get("summary_text", "")
                related = item.get("related_entities_json", "[]")

                outline_entries.append({
                    "type": item_type,
                    "key": subject,
                    "summary": summary,
                })

                if item_type in ("event", "key_event"):
                    key_events.append({"summary": summary})
                elif item_type in ("character_state", "character_state_update"):
                    char_state_updates.append({
                        "name": subject,
                        "summary": summary,
                    })
                    # Track character mentions for POV inference
                    if subject:
                        pov_candidates[subject] = pov_candidates.get(subject, 0) + 1
                elif item_type in ("relationship", "relationship_update"):
                    rel_updates.append({
                        "key": subject,
                        "summary": summary,
                    })

                # Also count related entities for POV inference
                try:
                    related_list = json.loads(related) if related else []
                    if isinstance(related_list, list):
                        for ent in related_list:
                            ent_name = ent if isinstance(ent, str) else ent.get("name", "")
                            if ent_name:
                                pov_candidates[ent_name] = pov_candidates.get(ent_name, 0) + 1
                except (json.JSONDecodeError, TypeError):
                    pass

            # Infer POV character: most-mentioned character in this chapter's history
            pov_character = None
            if pov_candidates:
                pov_character = max(pov_candidates, key=pov_candidates.get)

            conn.execute(
                """
                INSERT OR IGNORE INTO chapter_meta
                    (chapter_id, summary, outline_json, timeline_note,
                     open_threads_json, pov_character,
                     key_events_json, character_state_updates_json,
                     relationship_updates_json,
                     start_anchor, end_anchor, updated_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    chapter_id,
                    row["summary_text"] or "",
                    json.dumps(outline_entries, ensure_ascii=False) if outline_entries else "[]",
                    row["timeline_note"] or "",
                    row["open_threads_json"] or "[]",
                    pov_character,
                    json.dumps(key_events, ensure_ascii=False) if key_events else "[]",
                    json.dumps(char_state_updates, ensure_ascii=False) if char_state_updates else "[]",
                    json.dumps(rel_updates, ensure_ascii=False) if rel_updates else "[]",
                    row["start_anchor"] or "",
                    row["end_anchor"] or "",
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
                # Use edge weight as trust_level (interaction frequency)
                weight = None
                try:
                    weight = float(edge["weight"]) if edge["weight"] else None
                except (TypeError, ValueError):
                    pass
                conn.execute(
                    """
                    INSERT OR IGNORE INTO relationships
                        (relation_id, source_id, target_id, relation_type,
                         description, trust_level, updated_at)
                    VALUES (?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        edge["uuid"],
                        source_id,
                        target_id,
                        edge["name"],
                        edge["fact"] or "",
                        weight,
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
                        (state_id, session_id, branch_id, entity_id, state_json,
                         status, version, updated_at)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        state_id,
                        agent["session_id"],
                        agent["branch_id"],
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
                        (memory_id, session_id, branch_id, entity_id, memory_type,
                         summary, detail_json, salience, source_kind,
                         created_at)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        mem["memory_id"],
                        mem["session_id"],
                        mem["branch_id"],
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
# 6b. session.json  -->  worldline_branches + world_events (timeline)
# ---------------------------------------------------------------------------

def _migrate_worldline_branches(
    project_id: str,
    conn: sqlite3.Connection,
    counts: dict[str, int],
) -> None:
    """Migrate branch metadata and timeline events from session.json files."""
    sessions_dir = os.path.join(
        _project_dir(project_id), "worldlines", "sessions"
    )
    if not os.path.isdir(sessions_dir):
        logger.info("worldlines/sessions dir not found for project %s, skipping", project_id)
        return

    from ...models.worldline import WorldlineSession

    now = _now()
    for entry in os.listdir(sessions_dir):
        session_file = os.path.join(sessions_dir, entry, "session.json")
        if not os.path.isfile(session_file):
            continue
        try:
            with open(session_file, "r", encoding="utf-8") as f:
                data = json.load(f)
        except (json.JSONDecodeError, OSError) as exc:
            logger.warning("Failed to read %s: %s", session_file, exc)
            continue

        session = WorldlineSession.from_dict(data)

        # Ensure session row exists
        conn.execute(
            """
            INSERT OR IGNORE INTO sessions
                (session_id, project_id, session_type, title,
                 focus_question, status, config_json, created_at, updated_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                session.session_id, project_id, "worldline",
                session.label or session.simulation_goal,
                session.focus_question,
                session.status, "{}",
                session.created_at or now,
                session.updated_at or now,
            ),
        )

        for branch in session.branches:
            conn.execute(
                """
                INSERT OR REPLACE INTO worldline_branches
                    (branch_id, session_id, title, core_change, narrative_value,
                     current_step, status, evolution_intensity, evolution_depth,
                     key_agents_json, expected_conflicts_json,
                     actor_states_json, organization_states_json,
                     relationship_states_json, created_at, updated_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    branch.branch_id, session.session_id,
                    branch.title, branch.core_change, branch.narrative_value,
                    branch.current_step, branch.status,
                    branch.evolution_intensity, branch.evolution_depth,
                    json.dumps(branch.key_agents, ensure_ascii=False),
                    json.dumps(branch.expected_conflicts, ensure_ascii=False),
                    json.dumps(branch.actor_states, ensure_ascii=False),
                    json.dumps(branch.organization_states, ensure_ascii=False),
                    json.dumps([rs if isinstance(rs, dict) else {}
                                for rs in branch.relationship_states],
                               ensure_ascii=False),
                    branch.created_at or now,
                    branch.updated_at or now,
                ),
            )
            counts["worldline_branches"] = counts.get("worldline_branches", 0) + 1

            for event in branch.timeline:
                conn.execute(
                    """
                    INSERT OR IGNORE INTO world_events
                        (event_id, session_id, branch_id, step, title, summary,
                         event_type, driving_entities_json, state_changes_json,
                         status, created_at)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        event.event_id, session.session_id, branch.branch_id,
                        event.step, event.title, event.summary,
                        getattr(event, "event_type", None) or "",
                        json.dumps(
                            getattr(event, "driving_entities", []) or [],
                            ensure_ascii=False,
                        ),
                        json.dumps(
                            getattr(event, "state_changes", []) or [],
                            ensure_ascii=False,
                        ),
                        event.status or "canon",
                        event.created_at or now,
                    ),
                )
                counts["world_events"] = counts.get("world_events", 0) + 1

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
# 8. seed_analysis.json → entities + relationships
# ---------------------------------------------------------------------------

def _migrate_seed_analysis(
    project_id: str,
    conn: sqlite3.Connection,
    counts: dict[str, int],
) -> dict[str, str]:
    """Populate entities and relationships from seed_analysis.json.

    Returns mapping name → entity_id for downstream enrichment.
    """
    path = os.path.join(_project_dir(project_id), "seed_analysis.json")
    name_to_id: dict[str, str] = {}
    if not os.path.isfile(path):
        return name_to_id

    with open(path, encoding="utf-8") as f:
        data = json.load(f)

    now = _now()

    # characters → entities
    for char in data.get("characters", []):
        name = char.get("name", "")
        if not name:
            continue
        import hashlib
        entity_id = f"seed_char_{hashlib.sha1(name.encode()).hexdigest()[:12]}"
        name_to_id[name] = entity_id

        traits = char.get("personality_traits", [])
        goals = char.get("evidence", [])
        core_drive = "；".join(traits[:5]) if traits else ""
        summary = char.get("identity_hint", "") or char.get("profile_summary", "")

        conn.execute(
            """
            INSERT OR IGNORE INTO entities
                (entity_id, project_id, name, entity_type, importance_tier,
                 summary, core_drive, profile_json, created_at, updated_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                entity_id, project_id, name, "character",
                char.get("importance_tier", "minor"),
                summary, core_drive,
                json.dumps(char, ensure_ascii=False),
                now, now,
            ),
        )
        counts["entities"] = counts.get("entities", 0) + 1

        # aliases
        conn.execute(
            "INSERT OR IGNORE INTO entity_aliases (alias, entity_id) VALUES (?, ?)",
            (name, entity_id),
        )
        for alias in char.get("aliases", []):
            if alias and alias != name:
                conn.execute(
                    "INSERT OR IGNORE INTO entity_aliases (alias, entity_id) VALUES (?, ?)",
                    (alias, entity_id),
                )
                counts["entity_aliases"] = counts.get("entity_aliases", 0) + 1

    # organizations → entities
    for org in data.get("organizations", []):
        name = org.get("name", "")
        if not name:
            continue
        import hashlib
        entity_id = f"seed_org_{hashlib.sha1(name.encode()).hexdigest()[:12]}"
        name_to_id[name] = entity_id

        conn.execute(
            """
            INSERT OR IGNORE INTO entities
                (entity_id, project_id, name, entity_type, importance_tier,
                 summary, profile_json, created_at, updated_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                entity_id, project_id, name, "organization",
                org.get("importance_tier", "supporting"),
                org.get("summary", ""),
                json.dumps(org, ensure_ascii=False),
                now, now,
            ),
        )
        counts["entities"] = counts.get("entities", 0) + 1
        conn.execute(
            "INSERT OR IGNORE INTO entity_aliases (alias, entity_id) VALUES (?, ?)",
            (name, entity_id),
        )

    # relations → relationships
    for rel in data.get("relations", []):
        source = rel.get("source", "")
        target = rel.get("target", "")
        source_id = name_to_id.get(source)
        target_id = name_to_id.get(target)
        if not source_id or not target_id:
            continue

        import hashlib
        rel_id = f"seed_rel_{hashlib.sha1(f'{source}|{target}'.encode()).hexdigest()[:12]}"
        evidence = rel.get("evidence", [])
        evolution = rel.get("evolution_chain", [])

        conn.execute(
            """
            INSERT OR IGNORE INTO relationships
                (relation_id, source_id, target_id, relation_type,
                 description, history, updated_at)
            VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            (
                rel_id, source_id, target_id,
                rel.get("relation_type", "co_occurrence"),
                "；".join(evidence[:5]),
                json.dumps(evolution, ensure_ascii=False) if evolution else "",
                now,
            ),
        )
        counts["relationships"] = counts.get("relationships", 0) + 1

    conn.commit()
    return name_to_id


# ---------------------------------------------------------------------------
# 9. agent_profiles.json → entities (enrich profile_json)
# ---------------------------------------------------------------------------

def _migrate_agent_profiles(
    project_id: str,
    conn: sqlite3.Connection,
    counts: dict[str, int],
    name_to_id: dict[str, str],
) -> None:
    """Enrich entity profile_json with detailed agent profiles."""
    path = os.path.join(_project_dir(project_id), "agent_profiles.json")
    if not os.path.isfile(path):
        return

    with open(path, encoding="utf-8") as f:
        data = json.load(f)

    now = _now()
    profiles = data.get("profiles", {})

    for name, profile in profiles.items():
        entity_id = name_to_id.get(name)
        if not entity_id:
            continue

        profile_json = json.dumps(profile, ensure_ascii=False)

        # Extract structured fields from profile
        personality = profile.get("personality", {})
        speech = profile.get("speech", {})
        motivation = profile.get("motivation", {})
        capabilities = profile.get("capabilities", {})
        knowledge = profile.get("knowledge_boundary", {})

        core_drive = motivation.get("ultimate_goal", "")
        hidden_tension = motivation.get("internal_conflict", "")

        # Build speech_style from style + tone_range
        style = speech.get("style", "")
        tone_range = speech.get("tone_range", "")
        speech_style = f"{style}（{tone_range}）" if style and tone_range else style

        conn.execute(
            """
            UPDATE entities
            SET profile_json = ?,
                core_drive = COALESCE(NULLIF(?, ''), core_drive),
                hidden_tension = COALESCE(NULLIF(?, ''), hidden_tension),
                surface_mask = COALESCE(NULLIF(?, ''), surface_mask),
                speech_style = COALESCE(NULLIF(?, ''), speech_style),
                verbal_habits_json = ?,
                example_quotes_json = ?,
                personality_traits_json = ?,
                values_text = COALESCE(NULLIF(?, ''), values_text),
                fears_text = COALESCE(NULLIF(?, ''), fears_text),
                decision_pattern = COALESCE(NULLIF(?, ''), decision_pattern),
                skills_json = ?,
                limitations_json = ?,
                resources_text = COALESCE(NULLIF(?, ''), resources_text),
                knowledge_boundary_json = ?,
                ultimate_goal = COALESCE(NULLIF(?, ''), ultimate_goal),
                current_objective = COALESCE(NULLIF(?, ''), current_objective),
                mask_behavior = COALESCE(NULLIF(?, ''), mask_behavior),
                emotional_baseline = COALESCE(NULLIF(?, ''), emotional_baseline),
                cognitive_biases_json = ?,
                updated_at = ?
            WHERE entity_id = ?
            """,
            (
                profile_json,
                core_drive,
                hidden_tension,
                speech.get("style", ""),
                speech_style,
                json.dumps(speech.get("verbal_habits", []), ensure_ascii=False),
                json.dumps(speech.get("example_quotes", []), ensure_ascii=False),
                json.dumps(personality.get("core_traits", []), ensure_ascii=False),
                personality.get("values", ""),
                personality.get("fears", ""),
                personality.get("decision_pattern", ""),
                json.dumps(capabilities.get("skills", []), ensure_ascii=False),
                json.dumps(capabilities.get("limitations", []), ensure_ascii=False),
                capabilities.get("resources", ""),
                json.dumps(knowledge, ensure_ascii=False) if knowledge else "{}",
                motivation.get("ultimate_goal", ""),
                motivation.get("current_objective", ""),
                personality.get("mask_behavior", ""),
                personality.get("emotional_baseline", ""),
                json.dumps(knowledge.get("cognitive_biases", []), ensure_ascii=False),
                now,
                entity_id,
            ),
        )
        counts["agent_profiles_enriched"] = counts.get("agent_profiles_enriched", 0) + 1

    conn.commit()


# ---------------------------------------------------------------------------
# 10. reading_notes.json → entity_evidence + agent_memory (world rules)
# ---------------------------------------------------------------------------

def _migrate_reading_notes(
    project_id: str,
    conn: sqlite3.Connection,
    counts: dict[str, int],
    name_to_id: dict[str, str],
) -> None:
    """Import evidence quotes and world rules from reading notes."""
    path = os.path.join(_project_dir(project_id), "reading_notes.json")
    if not os.path.isfile(path):
        return

    with open(path, encoding="utf-8") as f:
        raw = json.load(f)

    # ReadingNotesManager saves with top-level wrapper; actual notes are under "notes"
    notes = raw.get("notes", raw)
    now = _now()
    core_facts = notes.get("core_facts", {})

    # character quote_examples → entity_evidence
    for name, data in core_facts.get("characters", {}).items():
        entity_id = name_to_id.get(name)
        if not entity_id:
            continue
        for idx, quote in enumerate(data.get("quote_examples", [])):
            if not quote:
                continue
            import hashlib
            ev_id = f"ev_{hashlib.sha1(f'{name}:{idx}:{quote[:40]}'.encode()).hexdigest()[:12]}"
            conn.execute(
                """
                INSERT OR IGNORE INTO entity_evidence
                    (evidence_id, owner_id, owner_type, snippet, created_at)
                VALUES (?, ?, ?, ?, ?)
                """,
                (ev_id, entity_id, "character", quote, now),
            )
            counts["entity_evidence"] = counts.get("entity_evidence", 0) + 1

    # world_rules → agent_memory (type=world_rule, searchable via FTS)
    world_rules = core_facts.get("world_rules", [])
    if world_rules:
        # Create a synthetic session for world rules
        session_id = f"__seed_world_rules__{project_id}"
        conn.execute(
            """
            INSERT OR IGNORE INTO sessions
                (session_id, project_id, session_type, title, status,
                 config_json, created_at, updated_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (session_id, project_id, "seed_import", "Seed world rules", "completed", "{}", now, now),
        )
        for idx, rule in enumerate(world_rules):
            fact = rule.get("fact", "") if isinstance(rule, dict) else str(rule)
            if not fact:
                continue
            import hashlib
            mem_id = f"wr_{hashlib.sha1(f'rule:{idx}:{fact[:40]}'.encode()).hexdigest()[:12]}"
            conn.execute(
                """
                INSERT OR IGNORE INTO agent_memory
                    (memory_id, session_id, entity_id, memory_type,
                     summary, detail_json, salience, source_kind, created_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (mem_id, session_id, "", "world_rule", fact, "{}", 0.8, "seed_extraction", now),
            )
            counts["agent_memory"] = counts.get("agent_memory", 0) + 1

    conn.commit()


# ---------------------------------------------------------------------------
# 11. reading_notes.json relationship_graph → enrich relationships
# ---------------------------------------------------------------------------

def _enrich_relationships_from_reading_notes(
    project_id: str,
    conn: sqlite3.Connection,
    counts: dict[str, int],
    name_to_id: dict[str, str],
) -> None:
    """Fill conflict_trigger, history, description from reading_notes relationship_graph."""
    path = os.path.join(_project_dir(project_id), "reading_notes.json")
    if not os.path.isfile(path):
        return

    with open(path, encoding="utf-8") as f:
        raw = json.load(f)

    notes = raw.get("notes", raw)
    rel_graph = notes.get("relationship_graph", [])
    if not rel_graph:
        return

    enriched = 0
    for entry in rel_graph:
        source_name = entry.get("source", "")
        target_name = entry.get("target", "")
        source_id = name_to_id.get(source_name)
        target_id = name_to_id.get(target_name)
        if not source_id or not target_id:
            continue

        trigger = entry.get("trigger", "")
        previous_state = entry.get("previous_state", "")
        evidence = entry.get("evidence", "")

        # Try both directions
        row = conn.execute(
            """
            SELECT relation_id, conflict_trigger, history, description
            FROM relationships
            WHERE (source_id = ? AND target_id = ?)
               OR (source_id = ? AND target_id = ?)
            LIMIT 1
            """,
            (source_id, target_id, target_id, source_id),
        ).fetchone()

        if row:
            updates = []
            params: list = []
            if trigger and not row["conflict_trigger"]:
                updates.append("conflict_trigger = ?")
                params.append(trigger)
            if previous_state:
                old_history = row["history"] or ""
                new_history = f"{old_history}；{previous_state}" if old_history else previous_state
                updates.append("history = ?")
                params.append(new_history)
            if evidence:
                old_desc = row["description"] or ""
                new_desc = f"{old_desc}；{evidence}" if old_desc else evidence
                updates.append("description = ?")
                params.append(new_desc)
            if updates:
                params.append(row["relation_id"])
                conn.execute(
                    f"UPDATE relationships SET {', '.join(updates)} WHERE relation_id = ?",
                    params,
                )
                enriched += 1

    if enriched:
        conn.commit()
    counts["relationships_enriched_notes"] = enriched


# ---------------------------------------------------------------------------
# 12. agent_profiles.json relationships → enrich power_dynamic / history
# ---------------------------------------------------------------------------

def _enrich_relationships_from_agent_profiles(
    project_id: str,
    conn: sqlite3.Connection,
    counts: dict[str, int],
    name_to_id: dict[str, str],
) -> None:
    """Fill power_dynamic and history from agent_profiles relationship entries."""
    path = os.path.join(_project_dir(project_id), "agent_profiles.json")
    if not os.path.isfile(path):
        return

    with open(path, encoding="utf-8") as f:
        data = json.load(f)

    profiles = data.get("profiles", {})
    enriched = 0

    for char_name, profile in profiles.items():
        char_id = name_to_id.get(char_name)
        if not char_id:
            continue

        relationships = profile.get("relationships", [])
        if not isinstance(relationships, list):
            continue

        for rel in relationships:
            target_name = rel.get("target", "")
            target_id = name_to_id.get(target_name)
            if not target_id:
                continue

            attitude = rel.get("attitude", "")
            evolution = rel.get("evolution", "")

            row = conn.execute(
                """
                SELECT relation_id, power_dynamic, history
                FROM relationships
                WHERE (source_id = ? AND target_id = ?)
                   OR (source_id = ? AND target_id = ?)
                LIMIT 1
                """,
                (char_id, target_id, target_id, char_id),
            ).fetchone()

            if row:
                updates = []
                params: list = []
                if attitude and not row["power_dynamic"]:
                    updates.append("power_dynamic = ?")
                    params.append(attitude)
                if evolution:
                    old_history = row["history"] or ""
                    new_history = f"{old_history}；{evolution}" if old_history else evolution
                    updates.append("history = ?")
                    params.append(new_history)
                if updates:
                    params.append(row["relation_id"])
                    conn.execute(
                        f"UPDATE relationships SET {', '.join(updates)} WHERE relation_id = ?",
                        params,
                    )
                    enriched += 1

    if enriched:
        conn.commit()
    counts["relationships_enriched_profiles"] = enriched


# ---------------------------------------------------------------------------
# 13. reading_notes.json plot_state → plot_threads + narrative_arcs + project_meta
# ---------------------------------------------------------------------------

def _migrate_plot_state(
    project_id: str,
    conn: sqlite3.Connection,
    counts: dict[str, int],
) -> None:
    """Import plot threads, arc summaries, and narrative phase from reading_notes."""
    path = os.path.join(_project_dir(project_id), "reading_notes.json")
    if not os.path.isfile(path):
        return

    with open(path, encoding="utf-8") as f:
        raw = json.load(f)

    notes = raw.get("notes", raw)
    plot_state = notes.get("plot_state", {})
    if not plot_state:
        return

    now = _now()
    import hashlib

    # -- plot_threads --
    open_threads = plot_state.get("open_threads", [])
    for idx, entry in enumerate(open_threads):
        if isinstance(entry, str):
            thread_key = entry
            status = "open"
            detail = ""
        elif isinstance(entry, dict):
            thread_key = entry.get("thread", entry.get("thread_key", ""))
            status = entry.get("status", "open")
            detail = entry.get("detail", "")
        else:
            continue
        if not thread_key:
            continue
        thread_id = f"pt_{hashlib.sha1(f'{project_id}:{idx}:{thread_key[:40]}'.encode()).hexdigest()[:12]}"
        conn.execute(
            """
            INSERT OR IGNORE INTO plot_threads
                (thread_id, project_id, thread_key, status, detail,
                 created_at, updated_at)
            VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            (thread_id, project_id, thread_key, status, detail, now, now),
        )
        counts["plot_threads"] = counts.get("plot_threads", 0) + 1

    # -- narrative_arcs --
    arc_summaries = plot_state.get("arc_summaries", [])
    for idx, arc in enumerate(arc_summaries):
        if isinstance(arc, str):
            summary = arc
            covered = []
        elif isinstance(arc, dict):
            summary = arc.get("summary", "")
            covered = arc.get("covered_segments", [])
        else:
            continue
        if not summary:
            continue
        arc_id = f"arc_{hashlib.sha1(f'{project_id}:{idx}:{summary[:40]}'.encode()).hexdigest()[:12]}"
        conn.execute(
            """
            INSERT OR IGNORE INTO narrative_arcs
                (arc_id, project_id, summary, covered_segments_json, created_at)
            VALUES (?, ?, ?, ?, ?)
            """,
            (arc_id, project_id, summary,
             json.dumps(covered, ensure_ascii=False) if covered else "[]",
             now),
        )
        counts["narrative_arcs"] = counts.get("narrative_arcs", 0) + 1

    # -- volume_summaries --
    volume_summaries = plot_state.get("volume_summaries", [])
    for idx, vol in enumerate(volume_summaries):
        if isinstance(vol, str):
            summary = vol
            covered = "[]"
            vid = f"vol_{idx:03d}"
        elif isinstance(vol, dict):
            summary = vol.get("summary", "")
            covered = json.dumps(vol.get("covered_arcs", []), ensure_ascii=False)
            vid = vol.get("volume_id", f"vol_{idx:03d}")
        else:
            continue
        if not summary:
            continue
        conn.execute(
            "INSERT OR IGNORE INTO volume_summaries (volume_id, project_id, volume_order, summary, covered_arcs_json, created_at) VALUES (?,?,?,?,?,?)",
            (vid, project_id, idx, summary, covered, now),
        )
    conn.commit()
    counts["volume_summaries"] = len(volume_summaries)

    # -- project_meta --
    narrative_phase = plot_state.get("narrative_phase", "")
    # Count actual total segments from reading notes top level
    all_segs = raw.get("all_segment_summaries", [])
    if not all_segs:
        # Fallback: try to count from segment_summaries.json
        seg_path = os.path.join(_project_dir(project_id), "segment_summaries.json")
        if os.path.isfile(seg_path):
            try:
                with open(seg_path, encoding="utf-8") as sf:
                    seg_data = json.load(sf)
                seg_items = seg_data.get("summaries", seg_data) if isinstance(seg_data, dict) else seg_data
                total_segments = len(seg_items) if isinstance(seg_items, list) else 0
            except Exception:
                total_segments = len(plot_state.get("recent_segment_summaries", []))
        else:
            total_segments = len(plot_state.get("recent_segment_summaries", []))
    else:
        total_segments = len(all_segs)
    conn.execute(
        """
        INSERT OR REPLACE INTO project_meta
            (project_id, narrative_phase, total_segments, updated_at)
        VALUES (?, ?, ?, ?)
        """,
        (project_id, narrative_phase or None, total_segments, now),
    )

    conn.commit()


# ---------------------------------------------------------------------------
# 14. segment_summaries.json + reading_notes core_facts -> chapter_meta summary
# ---------------------------------------------------------------------------

def _migrate_segment_summaries(
    project_id: str,
    conn: sqlite3.Connection,
    counts: dict[str, int],
) -> None:
    """Map segment-level summaries to chapters and populate chapter_meta.summary.

    Data sources:
    - segment_summaries.json: per-segment narrative summaries
    - reading_notes.json: core_facts (key setting facts)
    - chapter_segments.json: chapter→segment mapping via sentence_ids
    - smart_segments.json: segment→sentence_id mapping
    """
    proj_dir = _project_dir(project_id)
    now = _now()

    # --- Load segment summaries ---
    seg_summaries: dict[str, str] = {}
    seg_path = os.path.join(proj_dir, "segment_summaries.json")
    if os.path.exists(seg_path):
        try:
            with open(seg_path, "r", encoding="utf-8") as f:
                data = json.load(f)
            items = data.get("summaries", data) if isinstance(data, dict) else data
            if isinstance(items, list):
                for item in items:
                    sid = item.get("segment_id", "")
                    summary = item.get("summary", "")
                    if sid and summary:
                        seg_summaries[sid] = summary
        except (json.JSONDecodeError, OSError):
            pass

    if not seg_summaries:
        logger.info("No segment summaries found for project %s, skipping step 14", project_id)
        return

    # --- Load smart_segments to map segment_id -> chapter orders ---
    seg_to_chapters: dict[str, list[int]] = {}
    smart_path = os.path.join(proj_dir, "smart_segments.json")
    if os.path.exists(smart_path):
        try:
            with open(smart_path, "r", encoding="utf-8") as f:
                smart_data = json.load(f)
            segments = smart_data if isinstance(smart_data, list) else smart_data.get("segments", [])
            for seg in segments:
                sid = seg.get("segment_id", "")
                # smart_segments embeds full chapter objects
                seg_chapters = seg.get("chapters", [])
                orders = [int(ch.get("order", 0)) for ch in seg_chapters if isinstance(ch, dict)]
                if sid and orders:
                    seg_to_chapters[sid] = orders
        except (json.JSONDecodeError, OSError):
            pass

    # --- Map chapters to their segment summary ---
    chapter_to_summary: dict[int, str] = {}

    if seg_to_chapters:
        for sid, orders in seg_to_chapters.items():
            if sid in seg_summaries:
                for ch_order in orders:
                    chapter_to_summary[int(ch_order)] = seg_summaries[sid]
    else:
        # Fallback: load chapter_segments.json and distribute evenly
        chapters_path = os.path.join(proj_dir, "chapter_segments.json")
        chapters: list[dict] = []
        if os.path.exists(chapters_path):
            try:
                with open(chapters_path, "r", encoding="utf-8") as f:
                    cs_data = json.load(f)
                chapters = cs_data if isinstance(cs_data, list) else cs_data.get("chapters", [])
            except (json.JSONDecodeError, OSError):
                pass
        if chapters:
            seg_ids_sorted = sorted(seg_summaries.keys())
            chapters_per_seg = max(1, len(chapters) // len(seg_ids_sorted))
            for seg_idx, sid in enumerate(seg_ids_sorted):
                start_ch = seg_idx * chapters_per_seg
                end_ch = min(len(chapters), (seg_idx + 1) * chapters_per_seg)
                if seg_idx == len(seg_ids_sorted) - 1:
                    end_ch = len(chapters)
                for ch_idx in range(start_ch, end_ch):
                    ch_order = chapters[ch_idx].get("order", ch_idx)
                    chapter_to_summary[int(ch_order)] = seg_summaries[sid]

    # --- Load core_facts from reading_notes ---
    core_facts_text = ""
    rn_path = os.path.join(proj_dir, "reading_notes.json")
    if os.path.exists(rn_path):
        try:
            with open(rn_path, "r", encoding="utf-8") as f:
                rn_data = json.load(f)
            notes = rn_data.get("notes", rn_data) if isinstance(rn_data, dict) else rn_data
            if isinstance(notes, dict):
                facts = notes.get("core_facts", [])
                if isinstance(facts, list):
                    core_facts_text = "；".join(str(f) for f in facts[:30])
        except (json.JSONDecodeError, OSError):
            pass

    # --- Write to chapter_meta.summary ---
    updated = 0
    for ch_order, summary in chapter_to_summary.items():
        # Check if chapter_content exists for this order
        row = conn.execute(
            "SELECT chapter_id FROM chapter_content WHERE project_id = ? AND chapter_order = ?",
            (project_id, ch_order),
        ).fetchone()
        if not row:
            continue
        chapter_id = row["chapter_id"]

        # Ensure chapter_meta row exists
        conn.execute(
            "INSERT OR IGNORE INTO chapter_meta (chapter_id, updated_at) VALUES (?, ?)",
            (chapter_id, now),
        )

        # Update summary (only if currently empty)
        existing = conn.execute(
            "SELECT summary FROM chapter_meta WHERE chapter_id = ?",
            (chapter_id,),
        ).fetchone()
        if existing and existing["summary"]:
            continue

        conn.execute(
            "UPDATE chapter_meta SET summary = ?, updated_at = ? WHERE chapter_id = ?",
            (summary, now, chapter_id),
        )
        updated += 1

    # --- Store core_facts as a special "chapter 0" context ---
    if core_facts_text:
        ctx_chapter_id = f"ctx_core_facts_{project_id}"
        conn.execute(
            """
            INSERT OR REPLACE INTO chapter_content
                (chapter_id, project_id, chapter_order, title, content,
                 word_count, status, created_at, updated_at)
            VALUES (?, ?, 0, ?, ?, ?, 'system', ?, ?)
            """,
            (ctx_chapter_id, project_id, "核心设定事实",
             core_facts_text, len(core_facts_text), now, now),
        )
        updated += 1

    conn.commit()
    counts["segment_summaries"] = updated
    logger.info("Migrated %d chapter summaries for project %s", updated, project_id)


def _migrate_full_segment_summaries(
    project_id: str,
    conn: sqlite3.Connection,
    counts: dict[str, int],
) -> None:
    """Preserve full per-segment summaries in segment_summaries table."""
    seg_path = os.path.join(_project_dir(project_id), "segment_summaries.json")
    if not os.path.isfile(seg_path):
        return
    with open(seg_path, encoding="utf-8") as f:
        data = json.load(f)
    items = data.get("summaries", data) if isinstance(data, dict) else data
    if not isinstance(items, list):
        return

    now = _now()
    inserted = 0
    for idx, item in enumerate(items):
        if isinstance(item, dict):
            seg_id = item.get("segment_id", f"seg_{idx:03d}")
            summary = item.get("summary", "")
        elif isinstance(item, str):
            seg_id = f"seg_{idx:03d}"
            summary = item
        else:
            continue
        if not summary:
            continue
        conn.execute(
            "INSERT OR IGNORE INTO segment_summaries (segment_id, project_id, segment_order, summary, created_at) VALUES (?,?,?,?,?)",
            (seg_id, project_id, idx, summary, now),
        )
        inserted += 1
    conn.commit()
    counts["segment_summaries_full"] = inserted
    logger.info("Migrated %d full segment summaries for project %s", inserted, project_id)


def _migrate_key_locations(
    project_id: str,
    conn: sqlite3.Connection,
    counts: dict[str, int],
    name_to_id: dict[str, str],
) -> None:
    """Import key_locations from reading_notes as location entities."""
    path = os.path.join(_project_dir(project_id), "reading_notes.json")
    if not os.path.isfile(path):
        return
    with open(path, encoding="utf-8") as f:
        raw = json.load(f)

    notes = raw.get("notes", raw)
    locations = notes.get("core_facts", {}).get("key_locations", {})
    if not locations:
        return

    import hashlib
    now = _now()
    inserted = 0
    for name, data in locations.items():
        if not name or name in name_to_id:
            continue
        eid = f"e_{hashlib.sha1(name.encode()).hexdigest()[:12]}"
        summary = ""
        profile = {}
        if isinstance(data, dict):
            summary = data.get("description", data.get("summary", ""))
            profile = data
        elif isinstance(data, str):
            summary = data
        conn.execute(
            """INSERT OR IGNORE INTO entities
               (entity_id, project_id, name, entity_type, importance_tier, summary, profile_json, created_at, updated_at)
               VALUES (?,?,?,?,?,?,?,?,?)""",
            (eid, project_id, name, "location", "minor", summary,
             json.dumps(profile, ensure_ascii=False), now, now),
        )
        name_to_id[name] = eid
        inserted += 1
    conn.commit()
    counts["key_locations"] = inserted
    logger.info("Migrated %d key locations for project %s", inserted, project_id)


# ---------------------------------------------------------------------------
# 15. reading_notes characters → character_events
# ---------------------------------------------------------------------------

def _migrate_character_events(
    project_id: str,
    conn: sqlite3.Connection,
    counts: dict[str, int],
    name_to_id: dict[str, str],
) -> None:
    """Build character event timeline from reading notes character data."""
    path = os.path.join(_project_dir(project_id), "reading_notes.json")
    if not os.path.isfile(path):
        return
    with open(path, encoding="utf-8") as f:
        raw = json.load(f)
    notes = raw.get("notes", raw)
    now = _now()
    inserted = 0
    import hashlib

    for name, data in notes.get("core_facts", {}).get("characters", {}).items():
        entity_id = name_to_id.get(name, "")
        segments_seen = data.get("segments_seen", [])

        # key_actions → action events
        for idx, action in enumerate(data.get("key_actions", [])):
            if not action:
                continue
            seg = segments_seen[idx] if idx < len(segments_seen) else ""
            eid = f"ce_{hashlib.sha1(f'{name}:action:{idx}:{action[:30]}'.encode()).hexdigest()[:12]}"
            conn.execute(
                "INSERT OR IGNORE INTO character_events (event_id, project_id, entity_id, segment_id, event_type, summary, created_at) VALUES (?,?,?,?,?,?,?)",
                (eid, project_id, entity_id, seg, "action", action, now),
            )
            inserted += 1

        # knowledge_gained → knowledge events
        for idx, know in enumerate(data.get("knowledge_gained", [])):
            if not know:
                continue
            seg = segments_seen[idx] if idx < len(segments_seen) else ""
            eid = f"ce_{hashlib.sha1(f'{name}:know:{idx}:{know[:30]}'.encode()).hexdigest()[:12]}"
            conn.execute(
                "INSERT OR IGNORE INTO character_events (event_id, project_id, entity_id, segment_id, event_type, summary, created_at) VALUES (?,?,?,?,?,?,?)",
                (eid, project_id, entity_id, seg, "knowledge", know, now),
            )
            inserted += 1

        # status_history → state_change events
        for sh in data.get("status_history", []):
            status = sh.get("status", "")
            seg = sh.get("segment_id", "")
            if not status:
                continue
            eid = f"ce_{hashlib.sha1(f'{name}:status:{seg}:{status}'.encode()).hexdigest()[:12]}"
            conn.execute(
                "INSERT OR IGNORE INTO character_events (event_id, project_id, entity_id, segment_id, event_type, summary, created_at) VALUES (?,?,?,?,?,?,?)",
                (eid, project_id, entity_id, seg, "state_change", f"状态变更: {status}", now),
            )
            inserted += 1

    conn.commit()
    counts["character_events"] = inserted
    logger.info("Migrated %d character events for project %s", inserted, project_id)


# ---------------------------------------------------------------------------
# 16. reading_notes relationship_graph → relationship_events
# ---------------------------------------------------------------------------

def _migrate_relationship_events(
    project_id: str,
    conn: sqlite3.Connection,
    counts: dict[str, int],
    name_to_id: dict[str, str],
) -> None:
    """Build relationship event timeline from reading notes."""
    path = os.path.join(_project_dir(project_id), "reading_notes.json")
    if not os.path.isfile(path):
        return
    with open(path, encoding="utf-8") as f:
        raw = json.load(f)
    notes = raw.get("notes", raw)
    now = _now()
    inserted = 0
    import hashlib

    for entry in notes.get("relationship_graph", []):
        source = entry.get("source", "")
        target = entry.get("target", "")
        seg = entry.get("segment_id", "")
        trigger = entry.get("trigger", "")
        evidence = entry.get("evidence", "")
        relation = entry.get("relation", "")
        prev = entry.get("previous_state", "")

        src_id = name_to_id.get(source, source)
        tgt_id = name_to_id.get(target, target)

        eid = f"re_{hashlib.sha1(f'{source}:{target}:{seg}:{trigger[:30]}'.encode()).hexdigest()[:12]}"
        conn.execute(
            """INSERT OR IGNORE INTO relationship_events
               (event_id, project_id, source_entity_id, target_entity_id,
                segment_id, relation_type, previous_state, new_state,
                trigger_event, evidence, created_at)
               VALUES (?,?,?,?,?,?,?,?,?,?,?)""",
            (eid, project_id, src_id, tgt_id, seg, relation, prev, relation, trigger, evidence, now),
        )
        inserted += 1

    conn.commit()
    counts["relationship_events"] = inserted
    logger.info("Migrated %d relationship events for project %s", inserted, project_id)


# ---------------------------------------------------------------------------
# 17. plot_state → thread_lifecycle
# ---------------------------------------------------------------------------

def _migrate_thread_lifecycle(
    project_id: str,
    conn: sqlite3.Connection,
    counts: dict[str, int],
) -> None:
    """Build thread lifecycle from plot_state open/resolved threads."""
    path = os.path.join(_project_dir(project_id), "reading_notes.json")
    if not os.path.isfile(path):
        return
    with open(path, encoding="utf-8") as f:
        raw = json.load(f)
    notes = raw.get("notes", raw)
    now = _now()
    inserted = 0
    import hashlib

    plot_state = notes.get("plot_state", {})

    for thread in plot_state.get("open_threads", []):
        key = thread.get("thread", "")
        if not key:
            continue
        lid = f"tl_{hashlib.sha1(f'{key}:open'.encode()).hexdigest()[:12]}"
        conn.execute(
            "INSERT OR IGNORE INTO thread_lifecycle (lifecycle_id, project_id, thread_key, status, detail, created_at) VALUES (?,?,?,?,?,?)",
            (lid, project_id, key, thread.get("status", "open"), thread.get("detail", ""), now),
        )
        inserted += 1

    for thread in plot_state.get("resolved_threads", []):
        key = thread.get("thread", "")
        if not key:
            continue
        lid = f"tl_{hashlib.sha1(f'{key}:resolved'.encode()).hexdigest()[:12]}"
        seg = thread.get("resolved_segment_id", "")
        conn.execute(
            "INSERT OR IGNORE INTO thread_lifecycle (lifecycle_id, project_id, thread_key, segment_id, status, detail, resolution_detail, created_at) VALUES (?,?,?,?,?,?,?,?)",
            (lid, project_id, key, seg, "resolved", thread.get("detail", ""), thread.get("resolution_detail", ""), now),
        )
        inserted += 1

    conn.commit()
    counts["thread_lifecycle"] = inserted
    logger.info("Migrated %d thread lifecycle entries for project %s", inserted, project_id)


# ---------------------------------------------------------------------------
# 18. world_rules → world_rule_evidence
# ---------------------------------------------------------------------------

def _migrate_world_rule_evidence(
    project_id: str,
    conn: sqlite3.Connection,
    counts: dict[str, int],
) -> None:
    """Populate world rule evidence chain from reading notes."""
    path = os.path.join(_project_dir(project_id), "reading_notes.json")
    if not os.path.isfile(path):
        return
    with open(path, encoding="utf-8") as f:
        raw = json.load(f)
    notes = raw.get("notes", raw)
    now = _now()
    inserted = 0
    import hashlib

    for rule in notes.get("core_facts", {}).get("world_rules", []):
        fact = rule.get("fact", "") if isinstance(rule, dict) else str(rule)
        evidence = rule.get("evidence", "") if isinstance(rule, dict) else ""
        if not fact:
            continue
        eid = f"wre_{hashlib.sha1(f'{fact[:40]}:{evidence[:20]}'.encode()).hexdigest()[:12]}"
        conn.execute(
            "INSERT OR IGNORE INTO world_rule_evidence (evidence_id, project_id, fact_text, evidence_snippet, created_at) VALUES (?,?,?,?,?)",
            (eid, project_id, fact, evidence, now),
        )
        inserted += 1

    conn.commit()
    counts["world_rule_evidence"] = inserted
    logger.info("Migrated %d world rule evidence entries for project %s", inserted, project_id)


# ---------------------------------------------------------------------------
# 19. reading_notes characters → enrich entities (bypass agent_profiles)
# ---------------------------------------------------------------------------

def _enrich_entities_from_reading_notes(
    project_id: str,
    conn: sqlite3.Connection,
    counts: dict[str, int],
    name_to_id: dict[str, str],
) -> None:
    """Fill empty entity profile fields from reading notes character data."""
    path = os.path.join(_project_dir(project_id), "reading_notes.json")
    if not os.path.isfile(path):
        return
    with open(path, encoding="utf-8") as f:
        raw = json.load(f)
    notes = raw.get("notes", raw)
    updated = 0

    for name, data in notes.get("core_facts", {}).get("characters", {}).items():
        entity_id = name_to_id.get(name)
        if not entity_id:
            continue

        # Check what's currently empty
        row = conn.execute(
            "SELECT speech_style, personality_traits_json, example_quotes_json FROM entities WHERE entity_id = ?",
            (entity_id,),
        ).fetchone()
        if not row:
            continue

        updates = {}
        if not row[0] and data.get("speech_style"):
            updates["speech_style"] = data["speech_style"]
        if not row[1] and data.get("personality_traits"):
            updates["personality_traits_json"] = json.dumps(data["personality_traits"], ensure_ascii=False)
        if not row[2] and data.get("quote_examples"):
            updates["example_quotes_json"] = json.dumps(data["quote_examples"][:10], ensure_ascii=False)

        if updates:
            set_clause = ", ".join(f"{k} = ?" for k in updates)
            conn.execute(
                f"UPDATE entities SET {set_clause} WHERE entity_id = ?",
                (*updates.values(), entity_id),
            )
            updated += 1

    conn.commit()
    counts["entity_enrichment"] = updated
    logger.info("Enriched %d entities from reading notes for project %s", updated, project_id)


# ---------------------------------------------------------------------------
# 20. consistency_notes → consistency_notes table
# ---------------------------------------------------------------------------

def _migrate_consistency_notes_data(
    project_id: str,
    conn: sqlite3.Connection,
    counts: dict[str, int],
) -> None:
    """Import consistency notes from reading notes."""
    path = os.path.join(_project_dir(project_id), "reading_notes.json")
    if not os.path.isfile(path):
        return
    with open(path, encoding="utf-8") as f:
        raw = json.load(f)
    notes = raw.get("notes", raw)
    now = _now()
    inserted = 0
    import hashlib

    for entry in notes.get("core_facts", {}).get("consistency_notes", []):
        if isinstance(entry, dict):
            text = entry.get("note", "")
            seg = entry.get("segment_id", "")
        else:
            text = str(entry)
            seg = ""
        if not text:
            continue
        nid = f"cn_{hashlib.sha1(f'{text[:40]}:{seg}'.encode()).hexdigest()[:12]}"
        conn.execute(
            "INSERT OR IGNORE INTO consistency_notes (note_id, project_id, segment_id, note_text, created_at) VALUES (?,?,?,?,?)",
            (nid, project_id, seg, text, now),
        )
        inserted += 1

    conn.commit()
    counts["consistency_notes"] = inserted
    logger.info("Migrated %d consistency notes for project %s", inserted, project_id)


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

        # 6b: session.json -> worldline_branches + world_events (timeline)
        _migrate_worldline_branches(project_id, conn, counts)

        # 7: chapter_segments.json -> chapter_content (fill content)
        _migrate_chapter_segments(project_id, conn, counts)

        # 8: seed_analysis.json -> entities + relationships (new pipeline)
        name_to_id = _migrate_seed_analysis(project_id, conn, counts)

        # 9: agent_profiles.json -> entities (enrich profile_json)
        _migrate_agent_profiles(project_id, conn, counts, name_to_id)

        # 10: reading_notes.json -> entity_evidence + agent_memory
        _migrate_reading_notes(project_id, conn, counts, name_to_id)

        # 11: reading_notes.json relationship_graph -> enrich relationships
        _enrich_relationships_from_reading_notes(project_id, conn, counts, name_to_id)

        # 12: agent_profiles.json relationships -> enrich power_dynamic / history
        _enrich_relationships_from_agent_profiles(project_id, conn, counts, name_to_id)

        # 13: reading_notes.json plot_state -> plot_threads + narrative_arcs + project_meta
        _migrate_plot_state(project_id, conn, counts)

        # 14: segment_summaries.json + reading_notes core_facts -> chapter_meta summary
        _migrate_segment_summaries(project_id, conn, counts)

        # 14b: full segment summaries -> segment_summaries table
        _migrate_full_segment_summaries(project_id, conn, counts)

        # 14c: key_locations -> entities (type=location)
        _migrate_key_locations(project_id, conn, counts, name_to_id)

        # 15: reading_notes characters -> character_events timeline
        _migrate_character_events(project_id, conn, counts, name_to_id)

        # 16: reading_notes relationship_graph -> relationship_events timeline
        _migrate_relationship_events(project_id, conn, counts, name_to_id)

        # 17: plot_state -> thread_lifecycle
        _migrate_thread_lifecycle(project_id, conn, counts)

        # 18: world_rules -> world_rule_evidence
        _migrate_world_rule_evidence(project_id, conn, counts)

        # 19: reading_notes characters -> enrich entity profile fields
        _enrich_entities_from_reading_notes(project_id, conn, counts, name_to_id)

        # 20: reading_notes consistency_notes -> consistency_notes table
        _migrate_consistency_notes_data(project_id, conn, counts)

        # 21: build entity associations (thread_entity_links + rule_entity_links)
        _build_entity_associations(project_id, conn, counts)

    # 22: back-fill manuscript_blocks.chapter_id from chapter_tag
    counts["manuscript_chapter_ids"] = migrate_manuscript_chapter_ids(project_id)

    # Rebuild all FTS indexes after bulk import
    db.rebuild_fts(project_id)

    logger.info("Migration complete for project %s: %s", project_id, counts)
    return counts


# ======================================================================
# 21. Build entity associations from text matching
# ======================================================================


def _build_entity_associations(
    project_id: str,
    conn: sqlite3.Connection,
    counts: dict[str, int],
) -> None:
    """Scan plot_threads and world_rule_evidence text for entity names, create links.

    Uses substring matching — Chinese character names (2-3 chars) are distinctive
    enough that false positives are rare and harmless (only adds extra context).
    """
    # 1. Build name → entity_id lookup from entities + entity_aliases.
    #    Prefer archive_ IDs (from archive migration) over seed_char_ / node::
    #    because query_entity returns archive_ IDs to the agent.
    name_map: dict[str, str] = {}

    def _prefer_archive(current: str | None, candidate: str) -> str:
        if current is None:
            return candidate
        # archive_ IDs take priority
        if candidate.startswith("archive_") and not current.startswith("archive_"):
            return candidate
        return current

    for row in conn.execute(
        "SELECT entity_id, name FROM entities WHERE project_id = ?",
        (project_id,),
    ):
        name = row[1]
        if name and len(name) >= 2:
            name_map[name] = _prefer_archive(name_map.get(name), row[0])
    for row in conn.execute(
        "SELECT a.alias, a.entity_id FROM entity_aliases a "
        "JOIN entities e ON a.entity_id = e.entity_id "
        "WHERE e.project_id = ?",
        (project_id,),
    ):
        alias = row[0]
        if alias and len(alias) >= 2:
            name_map[alias] = _prefer_archive(name_map.get(alias), row[1])

    if not name_map:
        return

    now = _now()
    thread_links = 0
    rule_links = 0

    # 2. Scan plot_threads
    for row in conn.execute(
        "SELECT thread_id, thread_key, detail FROM plot_threads WHERE project_id = ?",
        (project_id,),
    ):
        text = (row[1] or "") + " " + (row[2] or "")
        for name, eid in name_map.items():
            if name in text:
                conn.execute(
                    "INSERT OR IGNORE INTO thread_entity_links "
                    "(thread_id, entity_id, role, created_at) VALUES (?,?,?,?)",
                    (row[0], eid, "involved", now),
                )
                thread_links += 1

    # 3. Scan thread_lifecycle for richer detail text
    for row in conn.execute(
        "SELECT tl.thread_key, tl.detail, tl.resolution_detail "
        "FROM thread_lifecycle tl WHERE tl.project_id = ?",
        (project_id,),
    ):
        text = (row[1] or "") + " " + (row[2] or "")
        thread_key = row[0] or ""
        # Find matching plot_thread by key
        pt_row = conn.execute(
            "SELECT thread_id FROM plot_threads WHERE project_id = ? AND thread_key = ?",
            (project_id, thread_key),
        ).fetchone()
        if not pt_row:
            continue
        for name, eid in name_map.items():
            if name in text:
                conn.execute(
                    "INSERT OR IGNORE INTO thread_entity_links "
                    "(thread_id, entity_id, role, created_at) VALUES (?,?,?,?)",
                    (pt_row[0], eid, "involved", now),
                )
                thread_links += 1

    # 4. Scan world_rule_evidence
    for row in conn.execute(
        "SELECT evidence_id, fact_text, evidence_snippet "
        "FROM world_rule_evidence WHERE project_id = ?",
        (project_id,),
    ):
        text = (row[1] or "") + " " + (row[2] or "")
        for name, eid in name_map.items():
            if name in text:
                conn.execute(
                    "INSERT OR IGNORE INTO rule_entity_links "
                    "(evidence_id, entity_id, relevance, created_at) VALUES (?,?,?,?)",
                    (row[0], eid, "constrains", now),
                )
                rule_links += 1

    conn.commit()
    counts["thread_entity_links"] = thread_links
    counts["rule_entity_links"] = rule_links
    logger.info(
        "Built entity associations for project %s: %d thread links, %d rule links",
        project_id, thread_links, rule_links,
    )


# ======================================================================
# 22. Populate manuscript_blocks.chapter_id from chapter_tag strings
# ======================================================================


def migrate_manuscript_chapter_ids(project_id: str) -> int:
    """Back-fill ``chapter_id`` on manuscript blocks that only have ``chapter_tag``.

    Parses the ``"第N章 · title"`` format to match against ``chapter_content`` rows.
    If no matching chapter exists, creates one.  Idempotent — safe to run repeatedly.

    Returns the number of blocks updated.
    """
    import re

    db = NovelDB()
    db.ensure_schema(project_id)
    updated = 0

    with db.connect(project_id) as conn:
        # Find blocks that have a chapter_tag but no chapter_id
        orphan_rows = conn.execute(
            "SELECT block_id, chapter_tag FROM manuscript_blocks "
            "WHERE project_id = ? AND chapter_tag IS NOT NULL AND chapter_id IS NULL",
            (project_id,),
        ).fetchall()
        if not orphan_rows:
            return 0

        # Build lookup: chapter_order -> chapter_id, title -> chapter_id
        chapters = conn.execute(
            "SELECT chapter_id, chapter_order, title FROM chapter_content WHERE project_id = ?",
            (project_id,),
        ).fetchall()
        order_map: dict[int, str] = {r["chapter_order"]: r["chapter_id"] for r in chapters}
        title_map: dict[str, str] = {r["title"]: r["chapter_id"] for r in chapters if r["title"]}

        tag_pattern = re.compile(r"^第(\d+)章\s*·\s*(.+)$")
        now = _now()

        for row in orphan_rows:
            tag = row["chapter_tag"]
            chapter_id = None

            m = tag_pattern.match(tag)
            if m:
                order = int(m.group(1))
                title = m.group(2).strip()
                # Try matching by order first, then by title
                chapter_id = order_map.get(order) or title_map.get(title)
                if not chapter_id:
                    # Create a new chapter
                    chapter_id = f"ch_{__import__('uuid').uuid4().hex[:12]}"
                    conn.execute(
                        "INSERT INTO chapter_content "
                        "(chapter_id, project_id, chapter_order, title, content, created_at, updated_at) "
                        "VALUES (?, ?, ?, ?, '', ?, ?)",
                        (chapter_id, project_id, order, title, now, now),
                    )
                    order_map[order] = chapter_id
                    title_map[title] = chapter_id
            else:
                # Unparseable tag — try title match, or create chapter with raw tag as title
                chapter_id = title_map.get(tag)
                if not chapter_id:
                    next_order = max(order_map.keys(), default=0) + 1
                    chapter_id = f"ch_{__import__('uuid').uuid4().hex[:12]}"
                    conn.execute(
                        "INSERT INTO chapter_content "
                        "(chapter_id, project_id, chapter_order, title, content, created_at, updated_at) "
                        "VALUES (?, ?, ?, ?, '', ?, ?)",
                        (chapter_id, project_id, next_order, tag, now, now),
                    )
                    order_map[next_order] = chapter_id
                    title_map[tag] = chapter_id

            conn.execute(
                "UPDATE manuscript_blocks SET chapter_id = ? WHERE block_id = ?",
                (chapter_id, row["block_id"]),
            )
            updated += 1

        conn.commit()

    logger.info(
        "Migrated %d manuscript blocks to chapter_id for project %s",
        updated, project_id,
    )
    return updated
