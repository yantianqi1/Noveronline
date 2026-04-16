"""SQLite FTS5 table and trigger DDL for search indexes."""

from __future__ import annotations

from sqlalchemy import DDL, event

from .base import metadata

FTS_TABLE_DDL = (
    "CREATE VIRTUAL TABLE IF NOT EXISTS entities_fts USING fts5(name, summary, core_drive, hidden_tension, speech_style, personality_traits_json, values_text, fears_text, content='entities', content_rowid='rowid')",
    "CREATE VIRTUAL TABLE IF NOT EXISTS chapter_content_fts USING fts5(title, content, content='chapter_content', content_rowid='rowid')",
    "CREATE VIRTUAL TABLE IF NOT EXISTS scenes_fts USING fts5(title, content, content='scenes', content_rowid='rowid')",
    "CREATE VIRTUAL TABLE IF NOT EXISTS agent_memory_fts USING fts5(summary, detail_json, content='agent_memory', content_rowid='rowid')",
    "CREATE VIRTUAL TABLE IF NOT EXISTS relationships_fts USING fts5(description, history, conflict_trigger, power_dynamic, content='relationships', content_rowid='rowid')",
    "CREATE VIRTUAL TABLE IF NOT EXISTS plot_threads_fts USING fts5(thread_key, detail, content='plot_threads', content_rowid='rowid')",
    "CREATE VIRTUAL TABLE IF NOT EXISTS narrative_arcs_fts USING fts5(summary, content='narrative_arcs', content_rowid='rowid')",
    "CREATE VIRTUAL TABLE IF NOT EXISTS entity_evidence_fts USING fts5(snippet, content='entity_evidence', content_rowid='rowid')",
    "CREATE VIRTUAL TABLE IF NOT EXISTS character_events_fts USING fts5(summary, content='character_events', content_rowid='rowid')",
    "CREATE VIRTUAL TABLE IF NOT EXISTS relationship_events_fts USING fts5(trigger_event, evidence, content='relationship_events', content_rowid='rowid')",
    "CREATE VIRTUAL TABLE IF NOT EXISTS thread_lifecycle_fts USING fts5(thread_key, detail, resolution_detail, content='thread_lifecycle', content_rowid='rowid')",
    "CREATE VIRTUAL TABLE IF NOT EXISTS world_rule_evidence_fts USING fts5(fact_text, evidence_snippet, content='world_rule_evidence', content_rowid='rowid')",
    "CREATE VIRTUAL TABLE IF NOT EXISTS consistency_notes_fts USING fts5(note_text, content='consistency_notes', content_rowid='rowid')",
    "CREATE VIRTUAL TABLE IF NOT EXISTS volume_summaries_fts USING fts5(summary, content='volume_summaries', content_rowid='rowid')",
    "CREATE VIRTUAL TABLE IF NOT EXISTS segment_summaries_fts USING fts5(summary, content='segment_summaries', content_rowid='rowid')",
    "CREATE VIRTUAL TABLE IF NOT EXISTS assets_fts USING fts5(title, summary, content, category, tags_json, content='assets', content_rowid='rowid', tokenize='trigram')",
    "CREATE VIRTUAL TABLE IF NOT EXISTS global_index_fts USING fts5(title, body, tags, entity_type, content='global_index', content_rowid='rowid', tokenize='trigram')",
)


def register_sqlite_fts() -> None:
    for statement in FTS_TABLE_DDL:
        event.listen(metadata, "after_create", DDL(statement).execute_if(dialect="sqlite"))


register_sqlite_fts()
