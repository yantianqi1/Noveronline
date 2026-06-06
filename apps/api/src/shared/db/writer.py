from sqlalchemy import Boolean, Column, DateTime, ForeignKey, Integer, String, Table, Text

from src.shared.db.base import metadata
from src.shared.db.table_helpers import timestamp_columns


Table(
    "chapters",
    metadata,
    Column("chapter_id", String(64), primary_key=True),
    Column("project_id", String(64), ForeignKey("projects.project_id"), nullable=False),
    Column("chapter_order", Integer, nullable=False),
    Column("title", String(255), nullable=False),
    Column("summary_text", Text, nullable=False),
    Column("timeline_note", Text, nullable=True),
    *timestamp_columns(),
)

Table(
    "chapter_history_items",
    metadata,
    Column("chapter_history_item_id", String(64), primary_key=True),
    Column("project_id", String(64), ForeignKey("projects.project_id"), nullable=False),
    Column("chapter_id", String(64), ForeignKey("chapters.chapter_id"), nullable=False),
    Column("chapter_order", Integer, nullable=False),
    Column("item_type", String(64), nullable=False),
    Column("subject_key", String(255), nullable=True),
    Column("summary_text", Text, nullable=False),
    *timestamp_columns(),
)

Table(
    "draft_runs",
    metadata,
    Column("draft_run_id", String(64), primary_key=True),
    Column("project_id", String(64), ForeignKey("projects.project_id"), nullable=False),
    Column("session_id", String(64), ForeignKey("worldline_sessions.session_id"), nullable=True),
    Column("scope_type", String(64), nullable=False),
    Column("scope_ref_id", String(64), nullable=False),
    Column("chapter_order", Integer, nullable=False),
    Column("chapter_id", String(64), nullable=False),
    Column("status", String(32), nullable=False),
    *timestamp_columns(),
)

Table(
    "draft_run_steps",
    metadata,
    Column("draft_run_step_id", String(64), primary_key=True),
    Column("draft_run_id", String(64), ForeignKey("draft_runs.draft_run_id"), nullable=False),
    Column("step_key", String(128), nullable=False),
    Column("agent_name", String(128), nullable=False),
    Column("status", String(32), nullable=False),
    Column("started_at", DateTime(timezone=True), nullable=True),
    Column("finished_at", DateTime(timezone=True), nullable=True),
)

Table(
    "draft_revisions",
    metadata,
    Column("draft_revision_id", String(64), primary_key=True),
    Column("draft_run_id", String(64), ForeignKey("draft_runs.draft_run_id"), nullable=False),
    Column("revision_no", Integer, nullable=False),
    Column("body_artifact_id", String(64), ForeignKey("artifacts.artifact_id"), nullable=False),
    Column("created_at", DateTime(timezone=True), nullable=False),
)

Table(
    "draft_reviews",
    metadata,
    Column("draft_review_id", String(64), primary_key=True),
    Column("draft_run_id", String(64), ForeignKey("draft_runs.draft_run_id"), nullable=False),
    Column("revision_no", Integer, nullable=False),
    Column("passed", Boolean, nullable=False),
    Column("score", Integer, nullable=False),
    Column("overall_assessment", Text, nullable=False),
    Column("created_at", DateTime(timezone=True), nullable=False),
)

Table(
    "finalized_chapters",
    metadata,
    Column("finalized_chapter_id", String(64), primary_key=True),
    Column("project_id", String(64), ForeignKey("projects.project_id"), nullable=False),
    Column("chapter_order", Integer, nullable=False),
    Column("chapter_id", String(64), nullable=False),
    Column("title", String(255), nullable=False),
    Column("source_draft_run_id", String(64), ForeignKey("draft_runs.draft_run_id"), nullable=True),
    Column("body_artifact_id", String(64), ForeignKey("artifacts.artifact_id"), nullable=False),
    *timestamp_columns(),
)
