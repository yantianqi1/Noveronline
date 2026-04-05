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
import uuid
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
        -- Structured fields from agent_profiles.json
        speech_style TEXT,
        verbal_habits_json TEXT DEFAULT '[]',
        example_quotes_json TEXT DEFAULT '[]',
        personality_traits_json TEXT DEFAULT '[]',
        values_text TEXT,
        fears_text TEXT,
        decision_pattern TEXT,
        skills_json TEXT DEFAULT '[]',
        limitations_json TEXT DEFAULT '[]',
        resources_text TEXT,
        knowledge_boundary_json TEXT DEFAULT '{}',
        ultimate_goal TEXT,
        current_objective TEXT,
        -- Fields from archive_library
        agent_behavior_hint TEXT,
        relationship_summary_text TEXT,
        notable_risks_json TEXT DEFAULT '[]',
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
        key_events_json TEXT DEFAULT '[]',
        character_state_updates_json TEXT DEFAULT '[]',
        relationship_updates_json TEXT DEFAULT '[]',
        start_anchor TEXT DEFAULT '',
        end_anchor TEXT DEFAULT '',
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
    # -- Plot threads layer --
    """
    CREATE TABLE IF NOT EXISTS plot_threads (
        thread_id TEXT PRIMARY KEY,
        project_id TEXT NOT NULL,
        thread_key TEXT NOT NULL,
        status TEXT NOT NULL DEFAULT 'open',
        detail TEXT NOT NULL DEFAULT '',
        source_chapter TEXT,
        created_at TEXT NOT NULL,
        updated_at TEXT NOT NULL
    )
    """,
    # -- Narrative arcs & project meta --
    """
    CREATE TABLE IF NOT EXISTS narrative_arcs (
        arc_id TEXT PRIMARY KEY,
        project_id TEXT NOT NULL,
        summary TEXT NOT NULL,
        covered_segments_json TEXT DEFAULT '[]',
        created_at TEXT NOT NULL
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS project_meta (
        project_id TEXT PRIMARY KEY,
        narrative_phase TEXT,
        total_segments INTEGER DEFAULT 0,
        updated_at TEXT NOT NULL
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
    # -- Manuscript layer --
    """
    CREATE TABLE IF NOT EXISTS manuscript_blocks (
        block_id              TEXT PRIMARY KEY,
        project_id            TEXT NOT NULL,
        block_order           INTEGER NOT NULL,
        content               TEXT NOT NULL,
        word_count            INTEGER DEFAULT 0,
        chapter_tag           TEXT,
        source_scene_id       TEXT,
        summary               TEXT,
        open_threads_json     TEXT,
        pov_entity_id         TEXT,
        involved_entities_json TEXT,
        location              TEXT,
        narrative_note        TEXT,
        committed_at          TEXT NOT NULL,
        UNIQUE(project_id, block_order)
    )
    """,
    # -- Timeline tables --
    """
    CREATE TABLE IF NOT EXISTS character_events (
        event_id TEXT PRIMARY KEY,
        project_id TEXT NOT NULL,
        entity_id TEXT NOT NULL,
        segment_id TEXT NOT NULL DEFAULT '',
        chapter_order INTEGER DEFAULT 0,
        event_type TEXT NOT NULL DEFAULT 'action',
        summary TEXT NOT NULL,
        detail_json TEXT DEFAULT '{}',
        created_at TEXT NOT NULL
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS relationship_events (
        event_id TEXT PRIMARY KEY,
        project_id TEXT NOT NULL,
        source_entity_id TEXT NOT NULL,
        target_entity_id TEXT NOT NULL,
        segment_id TEXT NOT NULL DEFAULT '',
        chapter_order INTEGER DEFAULT 0,
        relation_type TEXT DEFAULT '',
        previous_state TEXT DEFAULT '',
        new_state TEXT DEFAULT '',
        trigger_event TEXT DEFAULT '',
        emotional_shift TEXT DEFAULT '',
        power_shift TEXT DEFAULT '',
        evidence TEXT DEFAULT '',
        created_at TEXT NOT NULL
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS thread_lifecycle (
        lifecycle_id TEXT PRIMARY KEY,
        project_id TEXT NOT NULL,
        thread_key TEXT NOT NULL,
        segment_id TEXT NOT NULL DEFAULT '',
        chapter_order INTEGER DEFAULT 0,
        status TEXT NOT NULL DEFAULT 'open',
        detail TEXT DEFAULT '',
        resolution_detail TEXT DEFAULT '',
        created_at TEXT NOT NULL
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS world_rule_evidence (
        evidence_id TEXT PRIMARY KEY,
        project_id TEXT NOT NULL,
        fact_text TEXT NOT NULL,
        segment_id TEXT NOT NULL DEFAULT '',
        chapter_order INTEGER DEFAULT 0,
        evidence_snippet TEXT DEFAULT '',
        created_at TEXT NOT NULL
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS consistency_notes (
        note_id TEXT PRIMARY KEY,
        project_id TEXT NOT NULL,
        segment_id TEXT NOT NULL DEFAULT '',
        chapter_order INTEGER DEFAULT 0,
        note_text TEXT NOT NULL,
        created_at TEXT NOT NULL
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS outline_versions (
        version_id   TEXT PRIMARY KEY,
        chapter_id   TEXT NOT NULL REFERENCES chapter_content ON DELETE CASCADE,
        outline_json TEXT NOT NULL,
        label        TEXT DEFAULT '',
        created_at   TEXT NOT NULL
    )
    """,
)

FTS_STATEMENTS = (
    # -- Core FTS (expanded) --
    """
    CREATE VIRTUAL TABLE IF NOT EXISTS entities_fts USING fts5(
        name, summary, core_drive, hidden_tension,
        speech_style, personality_traits_json, values_text, fears_text,
        content=entities, tokenize='trigram'
    )
    """,
    """
    CREATE VIRTUAL TABLE IF NOT EXISTS chapter_content_fts USING fts5(
        title, content,
        content=chapter_content, tokenize='trigram'
    )
    """,
    """
    CREATE VIRTUAL TABLE IF NOT EXISTS scenes_fts USING fts5(
        title, content,
        content=scenes, tokenize='trigram'
    )
    """,
    """
    CREATE VIRTUAL TABLE IF NOT EXISTS agent_memory_fts USING fts5(
        summary, detail_json,
        content=agent_memory, tokenize='trigram'
    )
    """,
    """
    CREATE VIRTUAL TABLE IF NOT EXISTS manuscript_fts USING fts5(
        content, summary,
        content=manuscript_blocks, tokenize='trigram'
    )
    """,
    # -- New FTS tables --
    """
    CREATE VIRTUAL TABLE IF NOT EXISTS relationships_fts USING fts5(
        description, history, conflict_trigger, power_dynamic,
        content=relationships, tokenize='trigram'
    )
    """,
    """
    CREATE VIRTUAL TABLE IF NOT EXISTS plot_threads_fts USING fts5(
        thread_key, detail,
        content=plot_threads, tokenize='trigram'
    )
    """,
    """
    CREATE VIRTUAL TABLE IF NOT EXISTS narrative_arcs_fts USING fts5(
        summary,
        content=narrative_arcs, tokenize='trigram'
    )
    """,
    """
    CREATE VIRTUAL TABLE IF NOT EXISTS entity_evidence_fts USING fts5(
        snippet,
        content=entity_evidence, tokenize='trigram'
    )
    """,
    """
    CREATE VIRTUAL TABLE IF NOT EXISTS character_events_fts USING fts5(
        summary,
        content=character_events, tokenize='trigram'
    )
    """,
    """
    CREATE VIRTUAL TABLE IF NOT EXISTS relationship_events_fts USING fts5(
        trigger_event, evidence,
        content=relationship_events, tokenize='trigram'
    )
    """,
    """
    CREATE VIRTUAL TABLE IF NOT EXISTS thread_lifecycle_fts USING fts5(
        thread_key, detail, resolution_detail,
        content=thread_lifecycle, tokenize='trigram'
    )
    """,
    """
    CREATE VIRTUAL TABLE IF NOT EXISTS world_rule_evidence_fts USING fts5(
        fact_text, evidence_snippet,
        content=world_rule_evidence, tokenize='trigram'
    )
    """,
    """
    CREATE VIRTUAL TABLE IF NOT EXISTS consistency_notes_fts USING fts5(
        note_text,
        content=consistency_notes, tokenize='trigram'
    )
    """,
)

TRIGGER_STATEMENTS = (
    # -- entities FTS triggers (expanded: 8 columns) --
    """
    CREATE TRIGGER IF NOT EXISTS entities_ai AFTER INSERT ON entities BEGIN
        INSERT INTO entities_fts(rowid, name, summary, core_drive, hidden_tension, speech_style, personality_traits_json, values_text, fears_text)
        VALUES (new.rowid, new.name, new.summary, new.core_drive, new.hidden_tension, new.speech_style, new.personality_traits_json, new.values_text, new.fears_text);
    END
    """,
    """
    CREATE TRIGGER IF NOT EXISTS entities_au AFTER UPDATE ON entities BEGIN
        INSERT INTO entities_fts(entities_fts, rowid, name, summary, core_drive, hidden_tension, speech_style, personality_traits_json, values_text, fears_text)
        VALUES ('delete', old.rowid, old.name, old.summary, old.core_drive, old.hidden_tension, old.speech_style, old.personality_traits_json, old.values_text, old.fears_text);
        INSERT INTO entities_fts(rowid, name, summary, core_drive, hidden_tension, speech_style, personality_traits_json, values_text, fears_text)
        VALUES (new.rowid, new.name, new.summary, new.core_drive, new.hidden_tension, new.speech_style, new.personality_traits_json, new.values_text, new.fears_text);
    END
    """,
    """
    CREATE TRIGGER IF NOT EXISTS entities_ad AFTER DELETE ON entities BEGIN
        INSERT INTO entities_fts(entities_fts, rowid, name, summary, core_drive, hidden_tension, speech_style, personality_traits_json, values_text, fears_text)
        VALUES ('delete', old.rowid, old.name, old.summary, old.core_drive, old.hidden_tension, old.speech_style, old.personality_traits_json, old.values_text, old.fears_text);
    END
    """,
    # -- chapter_content FTS triggers --
    """
    CREATE TRIGGER IF NOT EXISTS chapter_content_ai AFTER INSERT ON chapter_content BEGIN
        INSERT INTO chapter_content_fts(rowid, title, content) VALUES (new.rowid, new.title, new.content);
    END
    """,
    """
    CREATE TRIGGER IF NOT EXISTS chapter_content_au AFTER UPDATE ON chapter_content BEGIN
        INSERT INTO chapter_content_fts(chapter_content_fts, rowid, title, content) VALUES ('delete', old.rowid, old.title, old.content);
        INSERT INTO chapter_content_fts(rowid, title, content) VALUES (new.rowid, new.title, new.content);
    END
    """,
    """
    CREATE TRIGGER IF NOT EXISTS chapter_content_ad AFTER DELETE ON chapter_content BEGIN
        INSERT INTO chapter_content_fts(chapter_content_fts, rowid, title, content) VALUES ('delete', old.rowid, old.title, old.content);
    END
    """,
    # -- scenes FTS triggers --
    """
    CREATE TRIGGER IF NOT EXISTS scenes_ai AFTER INSERT ON scenes BEGIN
        INSERT INTO scenes_fts(rowid, title, content) VALUES (new.rowid, new.title, new.content);
    END
    """,
    """
    CREATE TRIGGER IF NOT EXISTS scenes_au AFTER UPDATE ON scenes BEGIN
        INSERT INTO scenes_fts(scenes_fts, rowid, title, content) VALUES ('delete', old.rowid, old.title, old.content);
        INSERT INTO scenes_fts(rowid, title, content) VALUES (new.rowid, new.title, new.content);
    END
    """,
    """
    CREATE TRIGGER IF NOT EXISTS scenes_ad AFTER DELETE ON scenes BEGIN
        INSERT INTO scenes_fts(scenes_fts, rowid, title, content) VALUES ('delete', old.rowid, old.title, old.content);
    END
    """,
    # -- agent_memory FTS triggers (expanded: +detail_json) --
    """
    CREATE TRIGGER IF NOT EXISTS agent_memory_ai AFTER INSERT ON agent_memory BEGIN
        INSERT INTO agent_memory_fts(rowid, summary, detail_json) VALUES (new.rowid, new.summary, new.detail_json);
    END
    """,
    """
    CREATE TRIGGER IF NOT EXISTS agent_memory_au AFTER UPDATE ON agent_memory BEGIN
        INSERT INTO agent_memory_fts(agent_memory_fts, rowid, summary, detail_json) VALUES ('delete', old.rowid, old.summary, old.detail_json);
        INSERT INTO agent_memory_fts(rowid, summary, detail_json) VALUES (new.rowid, new.summary, new.detail_json);
    END
    """,
    """
    CREATE TRIGGER IF NOT EXISTS agent_memory_ad AFTER DELETE ON agent_memory BEGIN
        INSERT INTO agent_memory_fts(agent_memory_fts, rowid, summary, detail_json) VALUES ('delete', old.rowid, old.summary, old.detail_json);
    END
    """,
    # -- manuscript_blocks FTS triggers --
    """
    CREATE TRIGGER IF NOT EXISTS manuscript_ai AFTER INSERT ON manuscript_blocks BEGIN
        INSERT INTO manuscript_fts(rowid, content, summary) VALUES (new.rowid, new.content, new.summary);
    END
    """,
    """
    CREATE TRIGGER IF NOT EXISTS manuscript_au AFTER UPDATE ON manuscript_blocks BEGIN
        INSERT INTO manuscript_fts(manuscript_fts, rowid, content, summary) VALUES ('delete', old.rowid, old.content, old.summary);
        INSERT INTO manuscript_fts(rowid, content, summary) VALUES (new.rowid, new.content, new.summary);
    END
    """,
    """
    CREATE TRIGGER IF NOT EXISTS manuscript_ad AFTER DELETE ON manuscript_blocks BEGIN
        INSERT INTO manuscript_fts(manuscript_fts, rowid, content, summary) VALUES ('delete', old.rowid, old.content, old.summary);
    END
    """,
    # -- relationships FTS triggers --
    """
    CREATE TRIGGER IF NOT EXISTS relationships_ai AFTER INSERT ON relationships BEGIN
        INSERT INTO relationships_fts(rowid, description, history, conflict_trigger, power_dynamic)
        VALUES (new.rowid, new.description, new.history, new.conflict_trigger, new.power_dynamic);
    END
    """,
    """
    CREATE TRIGGER IF NOT EXISTS relationships_au AFTER UPDATE ON relationships BEGIN
        INSERT INTO relationships_fts(relationships_fts, rowid, description, history, conflict_trigger, power_dynamic)
        VALUES ('delete', old.rowid, old.description, old.history, old.conflict_trigger, old.power_dynamic);
        INSERT INTO relationships_fts(rowid, description, history, conflict_trigger, power_dynamic)
        VALUES (new.rowid, new.description, new.history, new.conflict_trigger, new.power_dynamic);
    END
    """,
    """
    CREATE TRIGGER IF NOT EXISTS relationships_ad AFTER DELETE ON relationships BEGIN
        INSERT INTO relationships_fts(relationships_fts, rowid, description, history, conflict_trigger, power_dynamic)
        VALUES ('delete', old.rowid, old.description, old.history, old.conflict_trigger, old.power_dynamic);
    END
    """,
    # -- plot_threads FTS triggers --
    """
    CREATE TRIGGER IF NOT EXISTS plot_threads_ai AFTER INSERT ON plot_threads BEGIN
        INSERT INTO plot_threads_fts(rowid, thread_key, detail) VALUES (new.rowid, new.thread_key, new.detail);
    END
    """,
    """
    CREATE TRIGGER IF NOT EXISTS plot_threads_au AFTER UPDATE ON plot_threads BEGIN
        INSERT INTO plot_threads_fts(plot_threads_fts, rowid, thread_key, detail) VALUES ('delete', old.rowid, old.thread_key, old.detail);
        INSERT INTO plot_threads_fts(rowid, thread_key, detail) VALUES (new.rowid, new.thread_key, new.detail);
    END
    """,
    """
    CREATE TRIGGER IF NOT EXISTS plot_threads_ad AFTER DELETE ON plot_threads BEGIN
        INSERT INTO plot_threads_fts(plot_threads_fts, rowid, thread_key, detail) VALUES ('delete', old.rowid, old.thread_key, old.detail);
    END
    """,
    # -- narrative_arcs FTS triggers --
    """
    CREATE TRIGGER IF NOT EXISTS narrative_arcs_ai AFTER INSERT ON narrative_arcs BEGIN
        INSERT INTO narrative_arcs_fts(rowid, summary) VALUES (new.rowid, new.summary);
    END
    """,
    """
    CREATE TRIGGER IF NOT EXISTS narrative_arcs_au AFTER UPDATE ON narrative_arcs BEGIN
        INSERT INTO narrative_arcs_fts(narrative_arcs_fts, rowid, summary) VALUES ('delete', old.rowid, old.summary);
        INSERT INTO narrative_arcs_fts(rowid, summary) VALUES (new.rowid, new.summary);
    END
    """,
    """
    CREATE TRIGGER IF NOT EXISTS narrative_arcs_ad AFTER DELETE ON narrative_arcs BEGIN
        INSERT INTO narrative_arcs_fts(narrative_arcs_fts, rowid, summary) VALUES ('delete', old.rowid, old.summary);
    END
    """,
    # -- entity_evidence FTS triggers --
    """
    CREATE TRIGGER IF NOT EXISTS entity_evidence_ai AFTER INSERT ON entity_evidence BEGIN
        INSERT INTO entity_evidence_fts(rowid, snippet) VALUES (new.rowid, new.snippet);
    END
    """,
    """
    CREATE TRIGGER IF NOT EXISTS entity_evidence_au AFTER UPDATE ON entity_evidence BEGIN
        INSERT INTO entity_evidence_fts(entity_evidence_fts, rowid, snippet) VALUES ('delete', old.rowid, old.snippet);
        INSERT INTO entity_evidence_fts(rowid, snippet) VALUES (new.rowid, new.snippet);
    END
    """,
    """
    CREATE TRIGGER IF NOT EXISTS entity_evidence_ad AFTER DELETE ON entity_evidence BEGIN
        INSERT INTO entity_evidence_fts(entity_evidence_fts, rowid, snippet) VALUES ('delete', old.rowid, old.snippet);
    END
    """,
    # -- character_events FTS triggers --
    """
    CREATE TRIGGER IF NOT EXISTS character_events_ai AFTER INSERT ON character_events BEGIN
        INSERT INTO character_events_fts(rowid, summary) VALUES (new.rowid, new.summary);
    END
    """,
    """
    CREATE TRIGGER IF NOT EXISTS character_events_au AFTER UPDATE ON character_events BEGIN
        INSERT INTO character_events_fts(character_events_fts, rowid, summary) VALUES ('delete', old.rowid, old.summary);
        INSERT INTO character_events_fts(rowid, summary) VALUES (new.rowid, new.summary);
    END
    """,
    """
    CREATE TRIGGER IF NOT EXISTS character_events_ad AFTER DELETE ON character_events BEGIN
        INSERT INTO character_events_fts(character_events_fts, rowid, summary) VALUES ('delete', old.rowid, old.summary);
    END
    """,
    # -- relationship_events FTS triggers --
    """
    CREATE TRIGGER IF NOT EXISTS relationship_events_ai AFTER INSERT ON relationship_events BEGIN
        INSERT INTO relationship_events_fts(rowid, trigger_event, evidence) VALUES (new.rowid, new.trigger_event, new.evidence);
    END
    """,
    """
    CREATE TRIGGER IF NOT EXISTS relationship_events_au AFTER UPDATE ON relationship_events BEGIN
        INSERT INTO relationship_events_fts(relationship_events_fts, rowid, trigger_event, evidence) VALUES ('delete', old.rowid, old.trigger_event, old.evidence);
        INSERT INTO relationship_events_fts(rowid, trigger_event, evidence) VALUES (new.rowid, new.trigger_event, new.evidence);
    END
    """,
    """
    CREATE TRIGGER IF NOT EXISTS relationship_events_ad AFTER DELETE ON relationship_events BEGIN
        INSERT INTO relationship_events_fts(relationship_events_fts, rowid, trigger_event, evidence) VALUES ('delete', old.rowid, old.trigger_event, old.evidence);
    END
    """,
    # -- thread_lifecycle FTS triggers --
    """
    CREATE TRIGGER IF NOT EXISTS thread_lifecycle_ai AFTER INSERT ON thread_lifecycle BEGIN
        INSERT INTO thread_lifecycle_fts(rowid, thread_key, detail, resolution_detail) VALUES (new.rowid, new.thread_key, new.detail, new.resolution_detail);
    END
    """,
    """
    CREATE TRIGGER IF NOT EXISTS thread_lifecycle_au AFTER UPDATE ON thread_lifecycle BEGIN
        INSERT INTO thread_lifecycle_fts(thread_lifecycle_fts, rowid, thread_key, detail, resolution_detail) VALUES ('delete', old.rowid, old.thread_key, old.detail, old.resolution_detail);
        INSERT INTO thread_lifecycle_fts(rowid, thread_key, detail, resolution_detail) VALUES (new.rowid, new.thread_key, new.detail, new.resolution_detail);
    END
    """,
    """
    CREATE TRIGGER IF NOT EXISTS thread_lifecycle_ad AFTER DELETE ON thread_lifecycle BEGIN
        INSERT INTO thread_lifecycle_fts(thread_lifecycle_fts, rowid, thread_key, detail, resolution_detail) VALUES ('delete', old.rowid, old.thread_key, old.detail, old.resolution_detail);
    END
    """,
    # -- world_rule_evidence FTS triggers --
    """
    CREATE TRIGGER IF NOT EXISTS world_rule_evidence_ai AFTER INSERT ON world_rule_evidence BEGIN
        INSERT INTO world_rule_evidence_fts(rowid, fact_text, evidence_snippet) VALUES (new.rowid, new.fact_text, new.evidence_snippet);
    END
    """,
    """
    CREATE TRIGGER IF NOT EXISTS world_rule_evidence_au AFTER UPDATE ON world_rule_evidence BEGIN
        INSERT INTO world_rule_evidence_fts(world_rule_evidence_fts, rowid, fact_text, evidence_snippet) VALUES ('delete', old.rowid, old.fact_text, old.evidence_snippet);
        INSERT INTO world_rule_evidence_fts(rowid, fact_text, evidence_snippet) VALUES (new.rowid, new.fact_text, new.evidence_snippet);
    END
    """,
    """
    CREATE TRIGGER IF NOT EXISTS world_rule_evidence_ad AFTER DELETE ON world_rule_evidence BEGIN
        INSERT INTO world_rule_evidence_fts(world_rule_evidence_fts, rowid, fact_text, evidence_snippet) VALUES ('delete', old.rowid, old.fact_text, old.evidence_snippet);
    END
    """,
    # -- consistency_notes FTS triggers --
    """
    CREATE TRIGGER IF NOT EXISTS consistency_notes_ai AFTER INSERT ON consistency_notes BEGIN
        INSERT INTO consistency_notes_fts(rowid, note_text) VALUES (new.rowid, new.note_text);
    END
    """,
    """
    CREATE TRIGGER IF NOT EXISTS consistency_notes_au AFTER UPDATE ON consistency_notes BEGIN
        INSERT INTO consistency_notes_fts(consistency_notes_fts, rowid, note_text) VALUES ('delete', old.rowid, old.note_text);
        INSERT INTO consistency_notes_fts(rowid, note_text) VALUES (new.rowid, new.note_text);
    END
    """,
    """
    CREATE TRIGGER IF NOT EXISTS consistency_notes_ad AFTER DELETE ON consistency_notes BEGIN
        INSERT INTO consistency_notes_fts(consistency_notes_fts, rowid, note_text) VALUES ('delete', old.rowid, old.note_text);
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
    "CREATE INDEX IF NOT EXISTS idx_mb_project ON manuscript_blocks(project_id, block_order)",
    # 关系复合索引：get_relationship() 的 OR 双向查询
    "CREATE INDEX IF NOT EXISTS idx_relationships_src_tgt ON relationships(source_id, target_id)",
    # Agent 状态复合索引：get_world_state() 按 session+entity 过滤
    "CREATE INDEX IF NOT EXISTS idx_agent_states_session_entity ON agent_states(session_id, entity_id)",
    # Agent 记忆复合索引：按 session+entity 检索记忆
    "CREATE INDEX IF NOT EXISTS idx_agent_memory_session_entity ON agent_memory(session_id, entity_id)",
    # 实体证据索引：按 owner 查证据
    "CREATE INDEX IF NOT EXISTS idx_entity_evidence_owner ON entity_evidence(owner_id, owner_type)",
    # 稿件章标签索引：get_manuscript_stats() 的 DISTINCT chapter_tag 查询
    "CREATE INDEX IF NOT EXISTS idx_mb_chapter_tag ON manuscript_blocks(project_id, chapter_tag)",
    # -- Timeline table indexes --
    "CREATE INDEX IF NOT EXISTS idx_char_events_entity ON character_events(entity_id, segment_id)",
    "CREATE INDEX IF NOT EXISTS idx_char_events_project ON character_events(project_id, chapter_order)",
    "CREATE INDEX IF NOT EXISTS idx_rel_events_pair ON relationship_events(source_entity_id, target_entity_id)",
    "CREATE INDEX IF NOT EXISTS idx_rel_events_project ON relationship_events(project_id, chapter_order)",
    "CREATE INDEX IF NOT EXISTS idx_thread_lc_key ON thread_lifecycle(project_id, thread_key)",
    "CREATE INDEX IF NOT EXISTS idx_world_rule_ev_project ON world_rule_evidence(project_id)",
    "CREATE INDEX IF NOT EXISTS idx_consistency_project ON consistency_notes(project_id, segment_id)",
    "CREATE INDEX IF NOT EXISTS idx_outline_versions_chapter ON outline_versions(chapter_id, created_at DESC)",
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

    _FTS_TABLE_NAMES = (
        "entities_fts", "chapter_content_fts", "scenes_fts",
        "agent_memory_fts", "manuscript_fts",
        "relationships_fts", "plot_threads_fts", "narrative_arcs_fts",
        "entity_evidence_fts",
        "character_events_fts", "relationship_events_fts",
        "thread_lifecycle_fts", "world_rule_evidence_fts",
        "consistency_notes_fts",
    )
    _FTS_TRIGGER_NAMES = (
        "entities_ai", "entities_au", "entities_ad",
        "chapter_content_ai", "chapter_content_au", "chapter_content_ad",
        "scenes_ai", "scenes_au", "scenes_ad",
        "agent_memory_ai", "agent_memory_au", "agent_memory_ad",
        "manuscript_ai", "manuscript_au", "manuscript_ad",
        "relationships_ai", "relationships_au", "relationships_ad",
        "plot_threads_ai", "plot_threads_au", "plot_threads_ad",
        "narrative_arcs_ai", "narrative_arcs_au", "narrative_arcs_ad",
        "entity_evidence_ai", "entity_evidence_au", "entity_evidence_ad",
        "character_events_ai", "character_events_au", "character_events_ad",
        "relationship_events_ai", "relationship_events_au", "relationship_events_ad",
        "thread_lifecycle_ai", "thread_lifecycle_au", "thread_lifecycle_ad",
        "world_rule_evidence_ai", "world_rule_evidence_au", "world_rule_evidence_ad",
        "consistency_notes_ai", "consistency_notes_au", "consistency_notes_ad",
    )

    # Columns that may not exist in older databases.  Each entry is
    # (table, column, type_with_default).  ``ensure_schema`` will
    # ``ALTER TABLE ADD COLUMN`` for any that are missing.
    _SCHEMA_MIGRATIONS: list[tuple[str, str, str]] = [
        # entities enrichment (Phase 1)
        ("entities", "speech_style", "TEXT"),
        ("entities", "verbal_habits_json", "TEXT DEFAULT '[]'"),
        ("entities", "example_quotes_json", "TEXT DEFAULT '[]'"),
        ("entities", "personality_traits_json", "TEXT DEFAULT '[]'"),
        ("entities", "values_text", "TEXT"),
        ("entities", "fears_text", "TEXT"),
        ("entities", "decision_pattern", "TEXT"),
        ("entities", "skills_json", "TEXT DEFAULT '[]'"),
        ("entities", "limitations_json", "TEXT DEFAULT '[]'"),
        ("entities", "resources_text", "TEXT"),
        ("entities", "knowledge_boundary_json", "TEXT DEFAULT '{}'"),
        ("entities", "ultimate_goal", "TEXT"),
        ("entities", "current_objective", "TEXT"),
        ("entities", "agent_behavior_hint", "TEXT"),
        ("entities", "relationship_summary_text", "TEXT"),
        ("entities", "notable_risks_json", "TEXT DEFAULT '[]'"),
        # chapter_meta enrichment (Phase 3)
        ("chapter_meta", "key_events_json", "TEXT DEFAULT '[]'"),
        ("chapter_meta", "character_state_updates_json", "TEXT DEFAULT '[]'"),
        ("chapter_meta", "relationship_updates_json", "TEXT DEFAULT '[]'"),
        ("chapter_meta", "start_anchor", "TEXT DEFAULT ''"),
        ("chapter_meta", "end_anchor", "TEXT DEFAULT ''"),
    ]

    def ensure_schema(self, project_id: str) -> None:
        self._ensure_parent_dir(project_id)
        with self.connect(project_id) as conn:
            for stmt in TABLE_STATEMENTS:
                conn.execute(stmt)
            # Add columns that may be missing in older databases
            self._apply_schema_migrations(conn)
            # Migrate FTS tables from unicode61 → trigram if needed
            self._migrate_fts_tokenizer(conn)
            for stmt in FTS_STATEMENTS:
                conn.execute(stmt)
            for stmt in TRIGGER_STATEMENTS:
                conn.execute(stmt)
            for stmt in INDEX_STATEMENTS:
                conn.execute(stmt)
            conn.commit()

    def _apply_schema_migrations(self, conn: sqlite3.Connection) -> None:
        """Add columns that were introduced after initial schema creation."""
        cache: dict[str, set[str]] = {}
        for table, column, col_type in self._SCHEMA_MIGRATIONS:
            if table not in cache:
                cache[table] = {
                    row[1]
                    for row in conn.execute(f"PRAGMA table_info({table})").fetchall()
                }
            if column not in cache[table]:
                conn.execute(f"ALTER TABLE {table} ADD COLUMN {column} {col_type}")
                cache[table].add(column)

    def _migrate_fts_tokenizer(self, conn: sqlite3.Connection) -> None:
        """Drop and recreate FTS tables if they use the old unicode61 tokenizer
        or if the schema has changed (e.g., column count expanded)."""
        row = conn.execute(
            "SELECT sql FROM sqlite_master WHERE type='table' AND name='entities_fts'"
        ).fetchone()
        if row is None:
            return  # No FTS tables yet, nothing to migrate
        sql = row[0] or ""
        needs_rebuild = False
        if "trigram" not in sql:
            needs_rebuild = True  # Old tokenizer
        elif "speech_style" not in sql:
            needs_rebuild = True  # Old column set (pre-expansion)
        # Check if any new FTS tables are missing
        existing = {r[0] for r in conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name LIKE '%_fts'"
        ).fetchall()}
        for name in self._FTS_TABLE_NAMES:
            if name not in existing:
                needs_rebuild = True
                break
        if not needs_rebuild:
            return
        # Drop all FTS tables and triggers, they'll be recreated
        for name in self._FTS_TRIGGER_NAMES:
            conn.execute(f"DROP TRIGGER IF EXISTS {name}")
        for name in self._FTS_TABLE_NAMES:
            conn.execute(f"DROP TABLE IF EXISTS {name}")

    def rebuild_fts(self, project_id: str) -> None:
        """Rebuild all FTS indexes from source tables. Call after bulk data import."""
        self.ensure_schema(project_id)
        with self.connect(project_id) as conn:
            for name in self._FTS_TABLE_NAMES:
                try:
                    conn.execute(f"INSERT INTO {name}({name}) VALUES ('rebuild')")
                except Exception:
                    pass  # table may not exist yet
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

    _CHAPTER_META_COLS = (
        "cm.summary, cm.outline_json, cm.timeline_note, cm.open_threads_json, "
        "cm.pov_character, cm.key_events_json, cm.character_state_updates_json, "
        "cm.relationship_updates_json, cm.start_anchor, cm.end_anchor"
    )

    def get_chapter(
        self,
        project_id: str,
        chapter_order: int,
        include_content: bool = False,
    ) -> dict[str, Any] | None:
        self.ensure_schema(project_id)
        with self.connect(project_id) as conn:
            if include_content:
                cols = f"cc.*, {self._CHAPTER_META_COLS}"
            else:
                cols = (
                    "cc.chapter_id, cc.project_id, cc.chapter_order, cc.title, "
                    f"cc.word_count, cc.status, cc.created_at, cc.updated_at, "
                    f"{self._CHAPTER_META_COLS}"
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
                f"""
                SELECT cc.chapter_id, cc.project_id, cc.chapter_order, cc.title,
                       cc.word_count, cc.status, cc.created_at, cc.updated_at,
                       {self._CHAPTER_META_COLS}
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

    # -- outline versions ---------------------------------------------------

    def save_outline_version(
        self, project_id: str, chapter_id: str, outline_json: str, label: str = "",
    ) -> str:
        """Snapshot an outline into the version history. Returns version_id."""
        self.ensure_schema(project_id)
        version_id = f"ov_{uuid.uuid4().hex[:12]}"
        now = _now()
        with self.connect(project_id) as conn:
            conn.execute(
                """
                INSERT INTO outline_versions (version_id, chapter_id, outline_json, label, created_at)
                VALUES (?, ?, ?, ?, ?)
                """,
                (version_id, chapter_id, outline_json, label, now),
            )
            # Enforce max 20 versions per chapter
            conn.execute(
                """
                DELETE FROM outline_versions
                WHERE version_id IN (
                    SELECT version_id FROM outline_versions
                    WHERE chapter_id = ?
                    ORDER BY created_at DESC
                    LIMIT -1 OFFSET 20
                )
                """,
                (chapter_id,),
            )
            conn.commit()
        return version_id

    def list_outline_versions(self, project_id: str, chapter_id: str) -> list[dict[str, Any]]:
        """List version metadata (without outline_json body) for a chapter."""
        self.ensure_schema(project_id)
        with self.connect(project_id) as conn:
            rows = conn.execute(
                """
                SELECT version_id, chapter_id, label, created_at
                FROM outline_versions
                WHERE chapter_id = ?
                ORDER BY created_at DESC
                """,
                (chapter_id,),
            ).fetchall()
            return _rows_to_dicts(rows)

    def get_outline_version(self, project_id: str, version_id: str) -> dict[str, Any] | None:
        """Get a single version including its outline_json."""
        self.ensure_schema(project_id)
        with self.connect(project_id) as conn:
            row = conn.execute(
                "SELECT * FROM outline_versions WHERE version_id = ?",
                (version_id,),
            ).fetchone()
            return _row_to_dict(row)

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

    @staticmethod
    def _fts_match_param(query: str) -> str:
        """Build FTS5 MATCH parameter for trigram tokenizer.

        Splits multi-word queries into individual phrase terms joined by OR,
        so "元锦儿 周君武" becomes '"元锦儿" OR "周君武"'.
        This allows partial matches — any term hitting is enough.
        """
        terms = query.split()
        parts = []
        for t in terms:
            if len(t) < 2:
                continue  # skip single-char terms
            safe = t.replace('"', '""')
            parts.append(f'"{safe}"')
        if not parts:
            safe = query.replace('"', '""')
            return f'"{safe}"'
        return " OR ".join(parts)

    def search_fts(
        self,
        project_id: str,
        query: str,
        scope: str = "all",
        limit: int = 10,
    ) -> list[dict[str, Any]]:
        self.ensure_schema(project_id)
        results: list[dict[str, Any]] = []
        # Use LIKE fallback when no term reaches the trigram minimum (2 chars)
        has_trigram_term = any(len(t) >= 2 for t in query.split())
        use_like = not has_trigram_term
        # Build per-term LIKE params for OR-based matching
        like_terms = [t for t in query.split() if len(t) >= 2]
        like_param = f"%{query}%"  # fallback for single-term
        fts_param = self._fts_match_param(query)

        with self.connect(project_id) as conn:
            if scope in ("entities", "all"):
                if use_like:
                    rows = conn.execute(
                        """
                        SELECT entity_id, name,
                               SUBSTR(summary, 1, 80) AS snippet
                        FROM entities
                        WHERE name LIKE ? OR summary LIKE ? OR core_drive LIKE ? OR hidden_tension LIKE ?
                        LIMIT ?
                        """,
                        (like_param, like_param, like_param, like_param, limit),
                    ).fetchall()
                else:
                    rows = conn.execute(
                        """
                        SELECT e.entity_id, e.name,
                               snippet(entities_fts, 1, '<b>', '</b>', '...', 32) AS snippet
                        FROM entities_fts
                        JOIN entities e ON e.rowid = entities_fts.rowid
                        WHERE entities_fts MATCH ?
                        LIMIT ?
                        """,
                        (fts_param, limit),
                    ).fetchall()
                for r in rows:
                    results.append({
                        "source": "entities",
                        "name": r["name"],
                        "snippet": r["snippet"] or "",
                    })

            if scope in ("chapters", "all"):
                if use_like:
                    rows = conn.execute(
                        """
                        SELECT chapter_id, title,
                               SUBSTR(content, MAX(1, INSTR(content, ?) - 30), 80) AS snippet
                        FROM chapter_content
                        WHERE project_id = ? AND (title LIKE ? OR content LIKE ?)
                        LIMIT ?
                        """,
                        (query, project_id, like_param, like_param, limit),
                    ).fetchall()
                else:
                    rows = conn.execute(
                        """
                        SELECT cc.chapter_id, cc.title,
                               snippet(chapter_content_fts, 1, '<b>', '</b>', '...', 32) AS snippet
                        FROM chapter_content_fts
                        JOIN chapter_content cc ON cc.rowid = chapter_content_fts.rowid
                        WHERE chapter_content_fts MATCH ?
                        LIMIT ?
                        """,
                        (fts_param, limit),
                    ).fetchall()
                for r in rows:
                    results.append({
                        "source": "chapters",
                        "title": r["title"],
                        "snippet": r["snippet"] or "",
                    })
                # Also search chapter_meta.summary (segment-level context)
                meta_rows = conn.execute(
                    """
                    SELECT cm.chapter_id, cc.title, cc.chapter_order,
                           SUBSTR(cm.summary, MAX(1, INSTR(cm.summary, ?) - 40), 120) AS snippet
                    FROM chapter_meta cm
                    JOIN chapter_content cc ON cc.chapter_id = cm.chapter_id
                    WHERE cm.summary LIKE ?
                    LIMIT ?
                    """,
                    (query, like_param, limit),
                ).fetchall()
                for r in meta_rows:
                    results.append({
                        "source": "chapter_summary",
                        "name": f"第{r['chapter_order']}章 {r['title']}",
                        "snippet": r["snippet"] or "",
                    })

            if scope in ("scenes", "all"):
                if use_like:
                    rows = conn.execute(
                        """
                        SELECT scene_id, title,
                               SUBSTR(content, MAX(1, INSTR(content, ?) - 30), 80) AS snippet
                        FROM scenes
                        WHERE title LIKE ? OR content LIKE ?
                        LIMIT ?
                        """,
                        (query, like_param, like_param, limit),
                    ).fetchall()
                else:
                    rows = conn.execute(
                        """
                        SELECT s.scene_id, s.title,
                               snippet(scenes_fts, 1, '<b>', '</b>', '...', 32) AS snippet
                        FROM scenes_fts
                        JOIN scenes s ON s.rowid = scenes_fts.rowid
                        WHERE scenes_fts MATCH ?
                        LIMIT ?
                        """,
                        (fts_param, limit),
                    ).fetchall()
                for r in rows:
                    results.append({
                        "source": "scenes",
                        "title": r["title"],
                        "snippet": r["snippet"] or "",
                    })

            if scope in ("memory", "all"):
                if use_like:
                    rows = conn.execute(
                        """
                        SELECT memory_id,
                               SUBSTR(summary, MAX(1, INSTR(summary, ?) - 30), 80) AS snippet
                        FROM agent_memory
                        WHERE summary LIKE ?
                        LIMIT ?
                        """,
                        (query, like_param, limit),
                    ).fetchall()
                else:
                    rows = conn.execute(
                        """
                        SELECT am.memory_id,
                               snippet(agent_memory_fts, 0, '<b>', '</b>', '...', 32) AS snippet
                        FROM agent_memory_fts
                        JOIN agent_memory am ON am.rowid = agent_memory_fts.rowid
                        WHERE agent_memory_fts MATCH ?
                        LIMIT ?
                        """,
                        (fts_param, limit),
                    ).fetchall()
                for r in rows:
                    results.append({
                        "source": "memory",
                        "name": r["memory_id"],
                        "snippet": r["snippet"] or "",
                    })

            # -- New FTS scopes --

            if scope in ("relationships", "all"):
                try:
                    # FTS search on description/history/trigger text
                    rows = conn.execute(
                        """
                        SELECT r.relation_id, r.source_id, r.target_id, r.description, r.relation_type,
                               snippet(relationships_fts, 0, '<b>', '</b>', '...', 48) AS snippet
                        FROM relationships_fts
                        JOIN relationships r ON r.rowid = relationships_fts.rowid
                        WHERE relationships_fts MATCH ?
                        LIMIT ?
                        """,
                        (fts_param, limit),
                    ).fetchall()
                    for r in rows:
                        # Resolve entity names for display
                        src_name = conn.execute("SELECT name FROM entities WHERE entity_id = ?", (r["source_id"],)).fetchone()
                        tgt_name = conn.execute("SELECT name FROM entities WHERE entity_id = ?", (r["target_id"],)).fetchone()
                        src = src_name[0] if src_name else r["source_id"]
                        tgt = tgt_name[0] if tgt_name else r["target_id"]
                        results.append({
                            "source": "relationships",
                            "name": f"{src} ↔ {tgt}",
                            "snippet": f"[{r['relation_type'] or ''}] {r['description'] or ''}" if not r["snippet"] else r["snippet"],
                        })
                    # Also find relationships by entity name (resolve name→id, query by source/target)
                    entity_row = conn.execute("SELECT entity_id FROM entities WHERE name LIKE ?", (like_param,)).fetchone()
                    if entity_row:
                        eid = entity_row[0]
                        id_rows = conn.execute(
                            """SELECT r.source_id, r.target_id, r.relation_type, r.description
                               FROM relationships r
                               WHERE r.source_id = ? OR r.target_id = ?
                               LIMIT ?""",
                            (eid, eid, limit),
                        ).fetchall()
                        existing_pairs = {(r["source_id"], r["target_id"]) for r in rows}
                        for r in id_rows:
                            if (r["source_id"], r["target_id"]) in existing_pairs:
                                continue
                            src_name = conn.execute("SELECT name FROM entities WHERE entity_id = ?", (r["source_id"],)).fetchone()
                            tgt_name = conn.execute("SELECT name FROM entities WHERE entity_id = ?", (r["target_id"],)).fetchone()
                            src = src_name[0] if src_name else r["source_id"]
                            tgt = tgt_name[0] if tgt_name else r["target_id"]
                            results.append({
                                "source": "relationships",
                                "name": f"{src} ↔ {tgt}",
                                "snippet": f"[{r['relation_type'] or ''}] {r['description'] or ''}",
                            })
                except Exception:
                    pass  # table may not exist in older DBs

            if scope in ("threads", "all"):
                try:
                    rows = conn.execute(
                        """
                        SELECT pt.thread_id, pt.thread_key,
                               snippet(plot_threads_fts, 1, '<b>', '</b>', '...', 48) AS snippet
                        FROM plot_threads_fts
                        JOIN plot_threads pt ON pt.rowid = plot_threads_fts.rowid
                        WHERE plot_threads_fts MATCH ?
                        LIMIT ?
                        """,
                        (fts_param, limit),
                    ).fetchall()
                    for r in rows:
                        results.append({
                            "source": "threads",
                            "name": r["thread_key"],
                            "snippet": r["snippet"] or "",
                        })
                except Exception:
                    pass

                try:
                    rows = conn.execute(
                        """
                        SELECT tl.lifecycle_id, tl.thread_key, tl.status,
                               snippet(thread_lifecycle_fts, 1, '<b>', '</b>', '...', 48) AS snippet
                        FROM thread_lifecycle_fts
                        JOIN thread_lifecycle tl ON tl.rowid = thread_lifecycle_fts.rowid
                        WHERE thread_lifecycle_fts MATCH ?
                        LIMIT ?
                        """,
                        (fts_param, limit),
                    ).fetchall()
                    for r in rows:
                        results.append({
                            "source": "thread_lifecycle",
                            "name": f"{r['thread_key']} [{r['status']}]",
                            "snippet": r["snippet"] or "",
                        })
                except Exception:
                    pass

            if scope in ("evidence", "all"):
                try:
                    rows = conn.execute(
                        """
                        SELECT ee.evidence_id, ee.owner_id,
                               snippet(entity_evidence_fts, 0, '<b>', '</b>', '...', 48) AS snippet
                        FROM entity_evidence_fts
                        JOIN entity_evidence ee ON ee.rowid = entity_evidence_fts.rowid
                        WHERE entity_evidence_fts MATCH ?
                        LIMIT ?
                        """,
                        (fts_param, limit),
                    ).fetchall()
                    for r in rows:
                        results.append({
                            "source": "evidence",
                            "name": r["owner_id"],
                            "snippet": r["snippet"] or "",
                        })
                except Exception:
                    pass

                try:
                    rows = conn.execute(
                        """
                        SELECT wre.evidence_id, wre.fact_text,
                               snippet(world_rule_evidence_fts, 1, '<b>', '</b>', '...', 48) AS snippet
                        FROM world_rule_evidence_fts
                        JOIN world_rule_evidence wre ON wre.rowid = world_rule_evidence_fts.rowid
                        WHERE world_rule_evidence_fts MATCH ?
                        LIMIT ?
                        """,
                        (fts_param, limit),
                    ).fetchall()
                    for r in rows:
                        results.append({
                            "source": "world_rules",
                            "name": r["fact_text"][:60],
                            "snippet": r["snippet"] or "",
                        })
                except Exception:
                    pass

            if scope in ("timeline", "all"):
                try:
                    rows = conn.execute(
                        """
                        SELECT ce.event_id, ce.entity_id, ce.event_type,
                               snippet(character_events_fts, 0, '<b>', '</b>', '...', 48) AS snippet
                        FROM character_events_fts
                        JOIN character_events ce ON ce.rowid = character_events_fts.rowid
                        WHERE character_events_fts MATCH ?
                        LIMIT ?
                        """,
                        (fts_param, limit),
                    ).fetchall()
                    for r in rows:
                        results.append({
                            "source": "character_timeline",
                            "name": f"{r['entity_id']} [{r['event_type']}]",
                            "snippet": r["snippet"] or "",
                        })
                except Exception:
                    pass

                try:
                    rows = conn.execute(
                        """
                        SELECT re.event_id, re.source_entity_id, re.target_entity_id,
                               snippet(relationship_events_fts, 0, '<b>', '</b>', '...', 48) AS snippet
                        FROM relationship_events_fts
                        JOIN relationship_events re ON re.rowid = relationship_events_fts.rowid
                        WHERE relationship_events_fts MATCH ?
                        LIMIT ?
                        """,
                        (fts_param, limit),
                    ).fetchall()
                    for r in rows:
                        results.append({
                            "source": "relationship_timeline",
                            "name": f"{r['source_entity_id']} → {r['target_entity_id']}",
                            "snippet": r["snippet"] or "",
                        })
                except Exception:
                    pass

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
    ) -> list[dict[str, Any]]:
        """Return open threads as dicts with ``thread_key``, ``status``, ``detail``.

        Prefers the rich ``plot_threads`` table when populated; falls back to
        the legacy ``chapter_meta.open_threads_json`` aggregation.
        """
        self.ensure_schema(project_id)
        with self.connect(project_id) as conn:
            # Try rich plot_threads table first
            pt_rows = conn.execute(
                """
                SELECT thread_key, status, detail
                FROM plot_threads
                WHERE project_id = ?
                ORDER BY updated_at DESC
                """,
                (project_id,),
            ).fetchall()
            if pt_rows:
                return _rows_to_dicts(pt_rows)

            # Fallback: legacy chapter_meta aggregation
            threads: list[dict[str, Any]] = []
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
                            for item in parsed:
                                if isinstance(item, str):
                                    threads.append({"thread_key": item, "status": "open", "detail": ""})
                                elif isinstance(item, dict):
                                    threads.append(item)
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

    # ======================================================================
    # Manuscript blocks
    # ======================================================================

    _BLOCK_ORDER_GAP = 10

    def commit_manuscript_block(
        self,
        project_id: str,
        content: str,
        source_scene_id: str | None = None,
        insert_after_block_id: str | None = None,
    ) -> dict[str, Any]:
        """Append (or insert) a new manuscript block and return it."""
        self.ensure_schema(project_id)
        block_id = f"mb_{uuid.uuid4().hex[:12]}"
        now = _now()
        word_count = len(content)

        with self.connect(project_id) as conn:
            if insert_after_block_id:
                # Insert after a specific block
                ref = conn.execute(
                    "SELECT block_order FROM manuscript_blocks WHERE block_id = ?",
                    (insert_after_block_id,),
                ).fetchone()
                if ref is None:
                    # Fallback to append
                    block_order = self._next_block_order(conn, project_id)
                else:
                    ref_order = ref["block_order"]
                    nxt = conn.execute(
                        "SELECT MIN(block_order) AS nxt FROM manuscript_blocks "
                        "WHERE project_id = ? AND block_order > ?",
                        (project_id, ref_order),
                    ).fetchone()
                    if nxt and nxt["nxt"] is not None:
                        gap = nxt["nxt"] - ref_order
                        if gap > 1:
                            block_order = ref_order + gap // 2
                        else:
                            # No gap — renumber all blocks after ref
                            self._renumber_blocks(conn, project_id)
                            ref2 = conn.execute(
                                "SELECT block_order FROM manuscript_blocks WHERE block_id = ?",
                                (insert_after_block_id,),
                            ).fetchone()
                            block_order = ref2["block_order"] + self._BLOCK_ORDER_GAP // 2
                    else:
                        block_order = ref_order + self._BLOCK_ORDER_GAP
            else:
                block_order = self._next_block_order(conn, project_id)

            conn.execute(
                """
                INSERT INTO manuscript_blocks
                    (block_id, project_id, block_order, content, word_count,
                     source_scene_id, committed_at)
                VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                (block_id, project_id, block_order, content, word_count,
                 source_scene_id, now),
            )
            conn.commit()

        return {
            "block_id": block_id,
            "block_order": block_order,
            "word_count": word_count,
            "committed_at": now,
        }

    def _next_block_order(self, conn: sqlite3.Connection, project_id: str) -> int:
        row = conn.execute(
            "SELECT COALESCE(MAX(block_order), 0) AS mx FROM manuscript_blocks WHERE project_id = ?",
            (project_id,),
        ).fetchone()
        return (row["mx"] if row else 0) + self._BLOCK_ORDER_GAP

    def _renumber_blocks(self, conn: sqlite3.Connection, project_id: str) -> None:
        rows = conn.execute(
            "SELECT block_id FROM manuscript_blocks WHERE project_id = ? ORDER BY block_order",
            (project_id,),
        ).fetchall()
        for idx, r in enumerate(rows):
            conn.execute(
                "UPDATE manuscript_blocks SET block_order = ? WHERE block_id = ?",
                ((idx + 1) * self._BLOCK_ORDER_GAP, r["block_id"]),
            )

    def list_manuscript_blocks(
        self, project_id: str, include_content: bool = True
    ) -> list[dict[str, Any]]:
        self.ensure_schema(project_id)
        cols = "*" if include_content else (
            "block_id, project_id, block_order, word_count, chapter_tag, "
            "source_scene_id, summary, open_threads_json, pov_entity_id, "
            "involved_entities_json, location, narrative_note, committed_at"
        )
        with self.connect(project_id) as conn:
            rows = conn.execute(
                f"SELECT {cols} FROM manuscript_blocks WHERE project_id = ? ORDER BY block_order",
                (project_id,),
            ).fetchall()
            return _rows_to_dicts(rows)

    def get_manuscript_block(self, project_id: str, block_id: str) -> dict[str, Any] | None:
        self.ensure_schema(project_id)
        with self.connect(project_id) as conn:
            row = conn.execute(
                "SELECT * FROM manuscript_blocks WHERE block_id = ?", (block_id,)
            ).fetchone()
            return _row_to_dict(row)

    def update_manuscript_block(
        self, project_id: str, block_id: str, **kwargs: Any
    ) -> None:
        self.ensure_schema(project_id)
        allowed = {
            "content", "chapter_tag", "summary", "open_threads_json",
            "pov_entity_id", "involved_entities_json", "location", "narrative_note",
        }
        updates = {k: v for k, v in kwargs.items() if k in allowed}
        if not updates:
            return
        if "content" in updates:
            updates["word_count"] = len(updates["content"])
        set_clause = ", ".join(f"{k} = ?" for k in updates)
        with self.connect(project_id) as conn:
            conn.execute(
                f"UPDATE manuscript_blocks SET {set_clause} WHERE block_id = ?",
                (*updates.values(), block_id),
            )
            conn.commit()

    def delete_manuscript_block(self, project_id: str, block_id: str) -> None:
        self.ensure_schema(project_id)
        with self.connect(project_id) as conn:
            conn.execute(
                "DELETE FROM manuscript_blocks WHERE block_id = ?", (block_id,)
            )
            conn.commit()

    def reorder_manuscript_blocks(
        self, project_id: str, block_ids: list[str]
    ) -> None:
        self.ensure_schema(project_id)
        with self.connect(project_id) as conn:
            # Shift to negative temporaries to avoid UNIQUE conflicts
            for idx, bid in enumerate(block_ids):
                conn.execute(
                    "UPDATE manuscript_blocks SET block_order = ? WHERE block_id = ? AND project_id = ?",
                    (-(idx + 1), bid, project_id),
                )
            # Now assign final positions
            for idx, bid in enumerate(block_ids):
                conn.execute(
                    "UPDATE manuscript_blocks SET block_order = ? WHERE block_id = ? AND project_id = ?",
                    ((idx + 1) * self._BLOCK_ORDER_GAP, bid, project_id),
                )
            conn.commit()

    def tag_manuscript_blocks(
        self, project_id: str, block_ids: list[str], chapter_tag: str
    ) -> int:
        self.ensure_schema(project_id)
        with self.connect(project_id) as conn:
            placeholders = ", ".join("?" for _ in block_ids)
            conn.execute(
                f"UPDATE manuscript_blocks SET chapter_tag = ? WHERE block_id IN ({placeholders}) AND project_id = ?",
                (chapter_tag, *block_ids, project_id),
            )
            conn.commit()
            return len(block_ids)

    def get_manuscript_stats(self, project_id: str) -> dict[str, Any]:
        self.ensure_schema(project_id)
        with self.connect(project_id) as conn:
            row = conn.execute(
                "SELECT COUNT(*) AS total_blocks, COALESCE(SUM(word_count), 0) AS total_words "
                "FROM manuscript_blocks WHERE project_id = ?",
                (project_id,),
            ).fetchone()
            tags_rows = conn.execute(
                "SELECT DISTINCT chapter_tag FROM manuscript_blocks "
                "WHERE project_id = ? AND chapter_tag IS NOT NULL ORDER BY block_order",
                (project_id,),
            ).fetchall()
            return {
                "total_blocks": row["total_blocks"],
                "total_words": row["total_words"],
                "chapter_tags": [r["chapter_tag"] for r in tags_rows],
            }

    def search_manuscript_fts(
        self, project_id: str, query: str, limit: int = 10
    ) -> list[dict[str, Any]]:
        self.ensure_schema(project_id)
        with self.connect(project_id) as conn:
            has_trigram_term = any(len(t) >= 2 for t in query.split())
            if not has_trigram_term:
                like_param = f"%{query}%"
                rows = conn.execute(
                    """
                    SELECT block_id, block_order, chapter_tag, word_count,
                           SUBSTR(content, MAX(1, INSTR(content, ?) - 30), 96) AS snippet
                    FROM manuscript_blocks
                    WHERE project_id = ? AND (content LIKE ? OR summary LIKE ?)
                    ORDER BY block_order
                    LIMIT ?
                    """,
                    (query, project_id, like_param, like_param, limit),
                ).fetchall()
            else:
                fts_param = self._fts_match_param(query)
                rows = conn.execute(
                    """
                    SELECT mb.block_id, mb.block_order, mb.chapter_tag, mb.word_count,
                           snippet(manuscript_fts, 0, '<b>', '</b>', '...', 48) AS snippet
                    FROM manuscript_fts
                    JOIN manuscript_blocks mb ON mb.rowid = manuscript_fts.rowid
                    WHERE manuscript_fts MATCH ? AND mb.project_id = ?
                    LIMIT ?
                    """,
                    (fts_param, project_id, limit),
                ).fetchall()
            return _rows_to_dicts(rows)

    def export_manuscript(self, project_id: str) -> str:
        """Return full manuscript text, blocks joined by double newlines."""
        self.ensure_schema(project_id)
        with self.connect(project_id) as conn:
            rows = conn.execute(
                "SELECT content FROM manuscript_blocks WHERE project_id = ? ORDER BY block_order",
                (project_id,),
            ).fetchall()
            return "\n\n".join(r["content"] for r in rows)

    def get_manuscript_continuation_blocks(
        self, project_id: str, limit: int = 50
    ) -> list[dict[str, Any]]:
        """Return recent manuscript blocks (newest first) for continuation context building."""
        self.ensure_schema(project_id)
        with self.connect(project_id) as conn:
            rows = conn.execute(
                "SELECT * FROM manuscript_blocks WHERE project_id = ? ORDER BY block_order DESC LIMIT ?",
                (project_id, limit),
            ).fetchall()
            return _rows_to_dicts(rows)
