"""Writer-first SaaS run and draft tables."""

from __future__ import annotations

from sqlalchemy import UniqueConstraint

from .helpers import int_col, project_id, table, text_col

writer_runs = table(
    "writer_runs",
    text_col("run_id", primary_key=True),
    text_col("tenant_id", nullable=False),
    project_id(),
    text_col("status", nullable=False),
    text_col("mode", nullable=False, default="'draft'"),
    text_col("chapter_id"),
    text_col("scene_id"),
    text_col("instruction", nullable=False, default="''"),
    text_col("module_key", nullable=False, default="'writer_composer'"),
    text_col("requested_by"),
    text_col("options_json", nullable=False, default="'{}'"),
    text_col("result_json"),
    text_col("error_code"),
    text_col("error_message"),
    text_col("created_at", nullable=False),
    text_col("updated_at", nullable=False),
    text_col("completed_at"),
)

writer_run_events = table(
    "writer_run_events",
    text_col("event_id", primary_key=True),
    text_col("tenant_id", nullable=False),
    project_id(),
    text_col("run_id", nullable=False),
    int_col("event_order", nullable=False),
    text_col("event_type", nullable=False),
    text_col("payload_json", nullable=False, default="'{}'"),
    text_col("created_at", nullable=False),
    UniqueConstraint("run_id", "event_order", name="uq_writer_run_events_run_order"),
)

writer_drafts = table(
    "writer_drafts",
    text_col("draft_id", primary_key=True),
    text_col("tenant_id", nullable=False),
    project_id(),
    text_col("run_id", nullable=False),
    text_col("chapter_id"),
    text_col("scene_id"),
    text_col("status", nullable=False, default="'draft'"),
    text_col("content", nullable=False, default="''"),
    text_col("metadata_json", nullable=False, default="'{}'"),
    text_col("created_by"),
    text_col("adopted_block_id"),
    text_col("created_at", nullable=False),
    text_col("updated_at", nullable=False),
    UniqueConstraint("tenant_id", "run_id", name="uq_writer_drafts_tenant_run"),
)

writer_draft_events = table(
    "writer_draft_events",
    text_col("event_id", primary_key=True),
    text_col("tenant_id", nullable=False),
    text_col("draft_id", nullable=False),
    text_col("event_type", nullable=False),
    text_col("payload_json", nullable=False, default="'{}'"),
    text_col("created_at", nullable=False),
)
