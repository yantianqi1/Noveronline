"""Create shared kernel baseline tables.

Revision ID: 20260411_0001
Revises:
Create Date: 2026-04-11
"""

from alembic import op
import sqlalchemy as sa


revision = "20260411_0001"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "artifact_objects",
        sa.Column("artifact_object_id", sa.String(length=64), nullable=False),
        sa.Column("bucket", sa.String(length=255), nullable=False),
        sa.Column("storage_key", sa.String(length=512), nullable=False),
        sa.Column("source_relative_path", sa.String(length=512), nullable=False),
        sa.Column("sha256", sa.String(length=64), nullable=False),
        sa.Column("size_bytes", sa.Integer(), nullable=False),
        sa.Column("content_type", sa.String(length=128), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("artifact_object_id", name="pk_artifact_objects"),
        sa.UniqueConstraint("storage_key", name="uq_artifact_objects_storage_key"),
    )
    op.create_table(
        "workspaces",
        sa.Column("workspace_id", sa.String(length=64), nullable=False),
        sa.Column("name", sa.String(length=255), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("workspace_id", name="pk_workspaces"),
    )
    op.create_table(
        "projects",
        sa.Column("project_id", sa.String(length=64), nullable=False),
        sa.Column("workspace_id", sa.String(length=64), nullable=False),
        sa.Column("name", sa.String(length=255), nullable=False),
        sa.Column("legacy_status", sa.String(length=64), nullable=True),
        sa.Column("analysis_summary", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["workspace_id"], ["workspaces.workspace_id"], name="fk_projects_workspace_id_workspaces"),
        sa.PrimaryKeyConstraint("project_id", name="pk_projects"),
    )
    op.create_table(
        "manuscripts",
        sa.Column("manuscript_id", sa.String(length=64), nullable=False),
        sa.Column("project_id", sa.String(length=64), nullable=False),
        sa.Column("artifact_object_id", sa.String(length=64), nullable=False),
        sa.Column("original_filename", sa.String(length=255), nullable=False),
        sa.Column("content_type", sa.String(length=128), nullable=False),
        sa.Column("storage_key", sa.String(length=512), nullable=False),
        sa.Column("size_bytes", sa.Integer(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(
            ["artifact_object_id"],
            ["artifact_objects.artifact_object_id"],
            name="fk_manuscripts_artifact_object_id_artifact_objects",
        ),
        sa.ForeignKeyConstraint(["project_id"], ["projects.project_id"], name="fk_manuscripts_project_id_projects"),
        sa.PrimaryKeyConstraint("manuscript_id", name="pk_manuscripts"),
    )
    op.create_table(
        "artifacts",
        sa.Column("artifact_id", sa.String(length=64), nullable=False),
        sa.Column("project_id", sa.String(length=64), nullable=False),
        sa.Column("artifact_object_id", sa.String(length=64), nullable=False),
        sa.Column("artifact_type", sa.String(length=128), nullable=False),
        sa.Column("semantic_type", sa.String(length=128), nullable=True),
        sa.Column("storage_key", sa.String(length=512), nullable=False),
        sa.Column("sha256", sa.String(length=64), nullable=False),
        sa.Column("size_bytes", sa.Integer(), nullable=True),
        sa.Column("content_type", sa.String(length=128), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(
            ["artifact_object_id"],
            ["artifact_objects.artifact_object_id"],
            name="fk_artifacts_artifact_object_id_artifact_objects",
        ),
        sa.ForeignKeyConstraint(["project_id"], ["projects.project_id"], name="fk_artifacts_project_id_projects"),
        sa.PrimaryKeyConstraint("artifact_id", name="pk_artifacts"),
    )
    op.create_table(
        "entities",
        sa.Column("entity_id", sa.String(length=64), nullable=False),
        sa.Column("project_id", sa.String(length=64), nullable=False),
        sa.Column("entity_uuid", sa.String(length=128), nullable=True),
        sa.Column("entity_kind", sa.String(length=64), nullable=False),
        sa.Column("canonical_name", sa.String(length=255), nullable=False),
        sa.Column("display_name", sa.String(length=255), nullable=False),
        sa.Column("summary", sa.Text(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["project_id"], ["projects.project_id"], name="fk_entities_project_id_projects"),
        sa.PrimaryKeyConstraint("entity_id", name="pk_entities"),
    )
    op.create_table(
        "archives",
        sa.Column("archive_id", sa.String(length=64), nullable=False),
        sa.Column("project_id", sa.String(length=64), nullable=False),
        sa.Column("entity_id", sa.String(length=64), nullable=False),
        sa.Column("archive_type", sa.String(length=64), nullable=False),
        sa.Column("agent_kind", sa.String(length=64), nullable=False),
        sa.Column("importance_tier", sa.String(length=64), nullable=False),
        sa.Column("selected_importance_tier", sa.String(length=64), nullable=False),
        sa.Column("template_key", sa.String(length=128), nullable=False),
        sa.Column("template_version", sa.String(length=64), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["entity_id"], ["entities.entity_id"], name="fk_archives_entity_id_entities"),
        sa.ForeignKeyConstraint(["project_id"], ["projects.project_id"], name="fk_archives_project_id_projects"),
        sa.PrimaryKeyConstraint("archive_id", name="pk_archives"),
    )
    op.create_table(
        "memories",
        sa.Column("memory_id", sa.String(length=64), nullable=False),
        sa.Column("project_id", sa.String(length=64), nullable=False),
        sa.Column("archive_id", sa.String(length=64), nullable=False),
        sa.Column("memory_type", sa.String(length=64), nullable=False),
        sa.Column("memory_layer", sa.String(length=32), nullable=False),
        sa.Column("status", sa.String(length=32), nullable=False),
        sa.Column("normalized_subject", sa.String(length=255), nullable=False),
        sa.Column("summary", sa.Text(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["archive_id"], ["archives.archive_id"], name="fk_memories_archive_id_archives"),
        sa.ForeignKeyConstraint(["project_id"], ["projects.project_id"], name="fk_memories_project_id_projects"),
        sa.PrimaryKeyConstraint("memory_id", name="pk_memories"),
    )
    op.create_table(
        "memory_events",
        sa.Column("memory_event_id", sa.String(length=64), nullable=False),
        sa.Column("memory_id", sa.String(length=64), nullable=False),
        sa.Column("archive_id", sa.String(length=64), nullable=False),
        sa.Column("event_type", sa.String(length=64), nullable=False),
        sa.Column("actor_type", sa.String(length=64), nullable=False),
        sa.Column("actor_ref", sa.String(length=255), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["archive_id"], ["archives.archive_id"], name="fk_memory_events_archive_id_archives"),
        sa.ForeignKeyConstraint(["memory_id"], ["memories.memory_id"], name="fk_memory_events_memory_id_memories"),
        sa.PrimaryKeyConstraint("memory_event_id", name="pk_memory_events"),
    )
    op.create_table(
        "workflow_runs",
        sa.Column("workflow_run_id", sa.String(length=64), nullable=False),
        sa.Column("project_id", sa.String(length=64), nullable=True),
        sa.Column("legacy_task_id", sa.String(length=128), nullable=True),
        sa.Column("workflow_type", sa.String(length=128), nullable=False),
        sa.Column("status", sa.String(length=32), nullable=False),
        sa.Column("progress_percent", sa.Integer(), nullable=False),
        sa.Column("last_message", sa.Text(), nullable=True),
        sa.Column("input_snapshot", sa.Text(), nullable=True),
        sa.Column("last_error", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["project_id"], ["projects.project_id"], name="fk_workflow_runs_project_id_projects"),
        sa.PrimaryKeyConstraint("workflow_run_id", name="pk_workflow_runs"),
    )
    op.create_table(
        "workflow_steps",
        sa.Column("workflow_step_id", sa.String(length=64), nullable=False),
        sa.Column("workflow_run_id", sa.String(length=64), nullable=False),
        sa.Column("step_key", sa.String(length=128), nullable=False),
        sa.Column("stage", sa.String(length=128), nullable=False),
        sa.Column("status", sa.String(length=32), nullable=False),
        sa.Column("progress_percent", sa.Integer(), nullable=False),
        sa.Column("message", sa.Text(), nullable=True),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("finished_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("elapsed_ms", sa.Integer(), nullable=True),
        sa.ForeignKeyConstraint(
            ["workflow_run_id"],
            ["workflow_runs.workflow_run_id"],
            name="fk_workflow_steps_workflow_run_id_workflow_runs",
        ),
        sa.PrimaryKeyConstraint("workflow_step_id", name="pk_workflow_steps"),
    )


def downgrade() -> None:
    op.drop_table("workflow_steps")
    op.drop_table("workflow_runs")
    op.drop_table("memory_events")
    op.drop_table("memories")
    op.drop_table("archives")
    op.drop_table("entities")
    op.drop_table("artifacts")
    op.drop_table("manuscripts")
    op.drop_table("projects")
    op.drop_table("workspaces")
    op.drop_table("artifact_objects")
