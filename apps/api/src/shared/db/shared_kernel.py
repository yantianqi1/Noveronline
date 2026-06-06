from sqlalchemy import Column, DateTime, ForeignKey, Integer, String, Table, Text

from src.shared.db.base import metadata
from src.shared.db.table_helpers import timestamp_columns


Table(
    "workspaces",
    metadata,
    Column("workspace_id", String(64), primary_key=True),
    Column("name", String(255), nullable=False),
    *timestamp_columns(),
)

Table(
    "workspace_settings",
    metadata,
    Column("workspace_id", String(64), ForeignKey("workspaces.workspace_id"), primary_key=True),
    Column("reviewer_rules_text", Text, nullable=True),
    Column("updated_at", DateTime(timezone=True), nullable=False),
)

Table(
    "artifact_objects",
    metadata,
    Column("artifact_object_id", String(64), primary_key=True),
    Column("bucket", String(255), nullable=False),
    Column("storage_key", String(512), nullable=False, unique=True),
    Column("source_relative_path", String(512), nullable=False),
    Column("sha256", String(64), nullable=False),
    Column("size_bytes", Integer, nullable=False),
    Column("content_type", String(128), nullable=True),
    *timestamp_columns(),
)

Table(
    "projects",
    metadata,
    Column("project_id", String(64), primary_key=True),
    Column("workspace_id", String(64), ForeignKey("workspaces.workspace_id"), nullable=False),
    Column("name", String(255), nullable=False),
    Column("legacy_status", String(64), nullable=True),
    Column("analysis_summary", Text, nullable=True),
    *timestamp_columns(),
)

Table(
    "manuscripts",
    metadata,
    Column("manuscript_id", String(64), primary_key=True),
    Column("project_id", String(64), ForeignKey("projects.project_id"), nullable=False),
    Column("artifact_object_id", String(64), ForeignKey("artifact_objects.artifact_object_id"), nullable=False),
    Column("original_filename", String(255), nullable=False),
    Column("content_type", String(128), nullable=False),
    Column("storage_key", String(512), nullable=False),
    Column("size_bytes", Integer, nullable=False),
    *timestamp_columns(),
)

Table(
    "artifacts",
    metadata,
    Column("artifact_id", String(64), primary_key=True),
    Column("project_id", String(64), ForeignKey("projects.project_id"), nullable=False),
    Column("artifact_object_id", String(64), ForeignKey("artifact_objects.artifact_object_id"), nullable=False),
    Column("artifact_type", String(128), nullable=False),
    Column("semantic_type", String(128), nullable=True),
    Column("storage_key", String(512), nullable=False),
    Column("sha256", String(64), nullable=False),
    Column("size_bytes", Integer, nullable=True),
    Column("content_type", String(128), nullable=True),
    *timestamp_columns(),
)

Table(
    "workflow_runs",
    metadata,
    Column("workflow_run_id", String(64), primary_key=True),
    Column("project_id", String(64), ForeignKey("projects.project_id"), nullable=True),
    Column("legacy_task_id", String(128), nullable=True),
    Column("workflow_type", String(128), nullable=False),
    Column("status", String(32), nullable=False),
    Column("progress_percent", Integer, nullable=False, default=0),
    Column("last_message", Text, nullable=True),
    Column("input_snapshot", Text, nullable=True),
    Column("last_error", Text, nullable=True),
    *timestamp_columns(),
)

Table(
    "workflow_steps",
    metadata,
    Column("workflow_step_id", String(64), primary_key=True),
    Column("workflow_run_id", String(64), ForeignKey("workflow_runs.workflow_run_id"), nullable=False),
    Column("step_key", String(128), nullable=False),
    Column("stage", String(128), nullable=False),
    Column("status", String(32), nullable=False),
    Column("progress_percent", Integer, nullable=False, default=0),
    Column("message", Text, nullable=True),
    Column("started_at", DateTime(timezone=True), nullable=True),
    Column("finished_at", DateTime(timezone=True), nullable=True),
    Column("elapsed_ms", Integer, nullable=True),
)

Table(
    "workflow_events",
    metadata,
    Column("workflow_event_id", String(64), primary_key=True),
    Column("workflow_run_id", String(64), ForeignKey("workflow_runs.workflow_run_id"), nullable=False),
    Column("event_type", String(64), nullable=False),
    Column("stage", String(128), nullable=True),
    Column("level", String(32), nullable=True),
    Column("status", String(32), nullable=True),
    Column("title", String(255), nullable=False),
    Column("detail", Text, nullable=True),
    Column("payload_json", Text, nullable=False),
    Column("emitted_at", DateTime(timezone=True), nullable=False),
)
