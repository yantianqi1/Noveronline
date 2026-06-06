"""Add writer and chapter baseline tables.

Revision ID: 20260411_0003
Revises: 20260411_0002
Create Date: 2026-04-11
"""

from alembic import op
import sqlalchemy as sa


revision = "20260411_0003"
down_revision = "20260411_0002"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "chapters",
        sa.Column("chapter_id", sa.String(length=64), nullable=False),
        sa.Column("project_id", sa.String(length=64), nullable=False),
        sa.Column("chapter_order", sa.Integer(), nullable=False),
        sa.Column("title", sa.String(length=255), nullable=False),
        sa.Column("summary_text", sa.Text(), nullable=False),
        sa.Column("timeline_note", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["project_id"], ["projects.project_id"], name="fk_chapters_project_id_projects"),
        sa.PrimaryKeyConstraint("chapter_id", name="pk_chapters"),
    )
    op.create_table(
        "chapter_history_items",
        sa.Column("chapter_history_item_id", sa.String(length=64), nullable=False),
        sa.Column("project_id", sa.String(length=64), nullable=False),
        sa.Column("chapter_id", sa.String(length=64), nullable=False),
        sa.Column("chapter_order", sa.Integer(), nullable=False),
        sa.Column("item_type", sa.String(length=64), nullable=False),
        sa.Column("subject_key", sa.String(length=255), nullable=True),
        sa.Column("summary_text", sa.Text(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["chapter_id"], ["chapters.chapter_id"], name="fk_chapter_history_items_chapter_id_chapters"),
        sa.ForeignKeyConstraint(["project_id"], ["projects.project_id"], name="fk_chapter_history_items_project_id_projects"),
        sa.PrimaryKeyConstraint("chapter_history_item_id", name="pk_chapter_history_items"),
    )
    op.create_table(
        "draft_runs",
        sa.Column("draft_run_id", sa.String(length=64), nullable=False),
        sa.Column("project_id", sa.String(length=64), nullable=False),
        sa.Column("session_id", sa.String(length=64), nullable=True),
        sa.Column("scope_type", sa.String(length=64), nullable=False),
        sa.Column("scope_ref_id", sa.String(length=64), nullable=False),
        sa.Column("chapter_order", sa.Integer(), nullable=False),
        sa.Column("chapter_id", sa.String(length=64), nullable=False),
        sa.Column("status", sa.String(length=32), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["project_id"], ["projects.project_id"], name="fk_draft_runs_project_id_projects"),
        sa.ForeignKeyConstraint(["session_id"], ["worldline_sessions.session_id"], name="fk_draft_runs_session_id_worldline_sessions"),
        sa.PrimaryKeyConstraint("draft_run_id", name="pk_draft_runs"),
    )
    op.create_table(
        "draft_run_steps",
        sa.Column("draft_run_step_id", sa.String(length=64), nullable=False),
        sa.Column("draft_run_id", sa.String(length=64), nullable=False),
        sa.Column("step_key", sa.String(length=128), nullable=False),
        sa.Column("agent_name", sa.String(length=128), nullable=False),
        sa.Column("status", sa.String(length=32), nullable=False),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("finished_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(["draft_run_id"], ["draft_runs.draft_run_id"], name="fk_draft_run_steps_draft_run_id_draft_runs"),
        sa.PrimaryKeyConstraint("draft_run_step_id", name="pk_draft_run_steps"),
    )
    op.create_table(
        "draft_revisions",
        sa.Column("draft_revision_id", sa.String(length=64), nullable=False),
        sa.Column("draft_run_id", sa.String(length=64), nullable=False),
        sa.Column("revision_no", sa.Integer(), nullable=False),
        sa.Column("body_artifact_id", sa.String(length=64), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["body_artifact_id"], ["artifacts.artifact_id"], name="fk_draft_revisions_body_artifact_id_artifacts"),
        sa.ForeignKeyConstraint(["draft_run_id"], ["draft_runs.draft_run_id"], name="fk_draft_revisions_draft_run_id_draft_runs"),
        sa.PrimaryKeyConstraint("draft_revision_id", name="pk_draft_revisions"),
    )
    op.create_table(
        "draft_reviews",
        sa.Column("draft_review_id", sa.String(length=64), nullable=False),
        sa.Column("draft_run_id", sa.String(length=64), nullable=False),
        sa.Column("revision_no", sa.Integer(), nullable=False),
        sa.Column("passed", sa.Boolean(), nullable=False),
        sa.Column("score", sa.Integer(), nullable=False),
        sa.Column("overall_assessment", sa.Text(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["draft_run_id"], ["draft_runs.draft_run_id"], name="fk_draft_reviews_draft_run_id_draft_runs"),
        sa.PrimaryKeyConstraint("draft_review_id", name="pk_draft_reviews"),
    )
    op.create_table(
        "finalized_chapters",
        sa.Column("finalized_chapter_id", sa.String(length=64), nullable=False),
        sa.Column("project_id", sa.String(length=64), nullable=False),
        sa.Column("chapter_order", sa.Integer(), nullable=False),
        sa.Column("chapter_id", sa.String(length=64), nullable=False),
        sa.Column("title", sa.String(length=255), nullable=False),
        sa.Column("source_draft_run_id", sa.String(length=64), nullable=True),
        sa.Column("body_artifact_id", sa.String(length=64), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["body_artifact_id"], ["artifacts.artifact_id"], name="fk_finalized_chapters_body_artifact_id_artifacts"),
        sa.ForeignKeyConstraint(["project_id"], ["projects.project_id"], name="fk_finalized_chapters_project_id_projects"),
        sa.ForeignKeyConstraint(["source_draft_run_id"], ["draft_runs.draft_run_id"], name="fk_finalized_chapters_source_draft_run_id_draft_runs"),
        sa.PrimaryKeyConstraint("finalized_chapter_id", name="pk_finalized_chapters"),
    )


def downgrade() -> None:
    op.drop_table("finalized_chapters")
    op.drop_table("draft_reviews")
    op.drop_table("draft_revisions")
    op.drop_table("draft_run_steps")
    op.drop_table("draft_runs")
    op.drop_table("chapter_history_items")
    op.drop_table("chapters")
