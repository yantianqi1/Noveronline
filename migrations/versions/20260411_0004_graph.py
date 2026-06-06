"""Add graph baseline tables.

Revision ID: 20260411_0004
Revises: 20260411_0003
Create Date: 2026-04-11
"""

from alembic import op
import sqlalchemy as sa


revision = "20260411_0004"
down_revision = "20260411_0003"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "graph_build_runs",
        sa.Column("graph_build_run_id", sa.String(length=64), nullable=False),
        sa.Column("project_id", sa.String(length=64), nullable=False),
        sa.Column("status", sa.String(length=32), nullable=False),
        sa.Column("source_artifact_id", sa.String(length=64), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["project_id"], ["projects.project_id"], name="fk_graph_build_runs_project_id_projects"),
        sa.ForeignKeyConstraint(["source_artifact_id"], ["artifacts.artifact_id"], name="fk_graph_build_runs_source_artifact_id_artifacts"),
        sa.PrimaryKeyConstraint("graph_build_run_id", name="pk_graph_build_runs"),
    )
    op.create_table(
        "graph_nodes",
        sa.Column("graph_node_id", sa.String(length=64), nullable=False),
        sa.Column("project_id", sa.String(length=64), nullable=False),
        sa.Column("canonical_name", sa.String(length=255), nullable=False),
        sa.Column("display_name", sa.String(length=255), nullable=False),
        sa.Column("node_type", sa.String(length=64), nullable=False),
        sa.Column("summary", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["project_id"], ["projects.project_id"], name="fk_graph_nodes_project_id_projects"),
        sa.PrimaryKeyConstraint("graph_node_id", name="pk_graph_nodes"),
    )
    op.create_table(
        "graph_edges",
        sa.Column("graph_edge_id", sa.String(length=64), nullable=False),
        sa.Column("project_id", sa.String(length=64), nullable=False),
        sa.Column("source_node_id", sa.String(length=64), nullable=False),
        sa.Column("target_node_id", sa.String(length=64), nullable=False),
        sa.Column("edge_type", sa.String(length=64), nullable=False),
        sa.Column("summary", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["project_id"], ["projects.project_id"], name="fk_graph_edges_project_id_projects"),
        sa.ForeignKeyConstraint(["source_node_id"], ["graph_nodes.graph_node_id"], name="fk_graph_edges_source_node_id_graph_nodes"),
        sa.ForeignKeyConstraint(["target_node_id"], ["graph_nodes.graph_node_id"], name="fk_graph_edges_target_node_id_graph_nodes"),
        sa.PrimaryKeyConstraint("graph_edge_id", name="pk_graph_edges"),
    )
    op.create_table(
        "graph_template_configs",
        sa.Column("graph_template_config_id", sa.String(length=64), nullable=False),
        sa.Column("project_id", sa.String(length=64), nullable=False),
        sa.Column("template_key", sa.String(length=128), nullable=False),
        sa.Column("status", sa.String(length=32), nullable=False),
        sa.Column("config_artifact_id", sa.String(length=64), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["config_artifact_id"], ["artifacts.artifact_id"], name="fk_graph_template_configs_config_artifact_id_artifacts"),
        sa.ForeignKeyConstraint(["project_id"], ["projects.project_id"], name="fk_graph_template_configs_project_id_projects"),
        sa.PrimaryKeyConstraint("graph_template_config_id", name="pk_graph_template_configs"),
    )


def downgrade() -> None:
    op.drop_table("graph_template_configs")
    op.drop_table("graph_edges")
    op.drop_table("graph_nodes")
    op.drop_table("graph_build_runs")
