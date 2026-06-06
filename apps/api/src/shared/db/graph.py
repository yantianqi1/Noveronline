from sqlalchemy import Column, ForeignKey, String, Table, Text

from src.shared.db.base import metadata
from src.shared.db.table_helpers import timestamp_columns


Table(
    "graph_build_runs",
    metadata,
    Column("graph_build_run_id", String(64), primary_key=True),
    Column("project_id", String(64), ForeignKey("projects.project_id"), nullable=False),
    Column("status", String(32), nullable=False),
    Column("source_artifact_id", String(64), ForeignKey("artifacts.artifact_id"), nullable=True),
    *timestamp_columns(),
)

Table(
    "graph_nodes",
    metadata,
    Column("graph_node_id", String(64), primary_key=True),
    Column("project_id", String(64), ForeignKey("projects.project_id"), nullable=False),
    Column("canonical_name", String(255), nullable=False),
    Column("display_name", String(255), nullable=False),
    Column("node_type", String(64), nullable=False),
    Column("summary", Text, nullable=True),
    *timestamp_columns(),
)

Table(
    "graph_edges",
    metadata,
    Column("graph_edge_id", String(64), primary_key=True),
    Column("project_id", String(64), ForeignKey("projects.project_id"), nullable=False),
    Column("source_node_id", String(64), ForeignKey("graph_nodes.graph_node_id"), nullable=False),
    Column("target_node_id", String(64), ForeignKey("graph_nodes.graph_node_id"), nullable=False),
    Column("edge_type", String(64), nullable=False),
    Column("summary", Text, nullable=True),
    *timestamp_columns(),
)

Table(
    "graph_template_configs",
    metadata,
    Column("graph_template_config_id", String(64), primary_key=True),
    Column("project_id", String(64), ForeignKey("projects.project_id"), nullable=False),
    Column("template_key", String(128), nullable=False),
    Column("status", String(32), nullable=False),
    Column("config_artifact_id", String(64), ForeignKey("artifacts.artifact_id"), nullable=True),
    *timestamp_columns(),
)
