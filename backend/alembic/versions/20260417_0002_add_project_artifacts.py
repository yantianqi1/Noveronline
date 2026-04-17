"""add project_artifacts table

Revision ID: 20260417_0002
Revises: 20260417_0001
Create Date: 2026-04-17

Introduces ``project_artifacts`` as the unified DB landing zone for
per-project JSON payloads (seed_analysis / ontology / agent_profiles /
reviewer_rules / story_memory / reading_notes / chapter_segments /
chapter_continuity / consistency_report / narrative_archives). The table
is a simple key-value store keyed by (project_id, artifact_key) with a
TEXT ``payload_json`` column holding the serialized JSON. Phase G /
Task 8 uses this table so runtime services stop reading
``uploads/projects/<pid>/*.json`` via ``ProjectManager.load_project_json``.
"""

from __future__ import annotations

from alembic import op

from app.tables import metadata


revision = "20260417_0002"
down_revision = "20260417_0001"
branch_labels = None
depends_on = None


def upgrade() -> None:
    project_artifacts = metadata.tables["project_artifacts"]
    project_artifacts.create(op.get_bind(), checkfirst=True)


def downgrade() -> None:
    project_artifacts = metadata.tables["project_artifacts"]
    project_artifacts.drop(op.get_bind(), checkfirst=True)
