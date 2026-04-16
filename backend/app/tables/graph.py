"""Local story graph tables in the unified database."""

from __future__ import annotations

from .helpers import composite_pk, int_col, project_id, table, text_col

graph_meta = table("graph_meta", project_id(), text_col("key", nullable=False), text_col("value", nullable=False), composite_pk("project_id", "key"))
graph_nodes = table("graph_nodes", project_id(), text_col("uuid", nullable=False), text_col("name", nullable=False), text_col("summary", nullable=False), text_col("attributes_json", nullable=False), text_col("evidence_refs_json", nullable=False), composite_pk("project_id", "uuid"))
graph_node_labels = table("graph_node_labels", project_id(), text_col("node_uuid", nullable=False), text_col("label", nullable=False), composite_pk("project_id", "node_uuid", "label"))
graph_aliases = table("graph_aliases", project_id(), text_col("alias", nullable=False), text_col("node_uuid", nullable=False), composite_pk("project_id", "alias", "node_uuid"))
graph_edges = table("graph_edges", project_id(), text_col("uuid", nullable=False), text_col("name", nullable=False), text_col("fact", nullable=False), text_col("source_node_uuid", nullable=False), text_col("target_node_uuid", nullable=False), text_col("attributes_json", nullable=False), int_col("weight", nullable=False), text_col("evidence_refs_json", nullable=False), composite_pk("project_id", "uuid"))
graph_evidence = table("graph_evidence", project_id(), text_col("owner_kind", nullable=False), text_col("owner_uuid", nullable=False), text_col("chapter_id", nullable=False), text_col("block_id", nullable=False), text_col("snippet", nullable=False))
