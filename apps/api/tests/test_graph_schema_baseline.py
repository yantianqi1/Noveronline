import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from src.shared.db.base import metadata


def test_graph_tables_are_registered():
    expected_tables = {
        "graph_build_runs",
        "graph_nodes",
        "graph_edges",
        "graph_template_configs",
    }

    assert expected_tables.issubset(set(metadata.tables))


def test_graph_key_columns_exist():
    graph_build_runs = metadata.tables["graph_build_runs"]
    graph_nodes = metadata.tables["graph_nodes"]
    graph_edges = metadata.tables["graph_edges"]
    graph_template_configs = metadata.tables["graph_template_configs"]

    assert {"graph_build_run_id", "project_id", "status", "source_artifact_id"}.issubset(
        graph_build_runs.columns.keys()
    )
    assert {"graph_node_id", "project_id", "canonical_name", "node_type"}.issubset(graph_nodes.columns.keys())
    assert {"graph_edge_id", "project_id", "source_node_id", "target_node_id", "edge_type"}.issubset(
        graph_edges.columns.keys()
    )
    assert {"graph_template_config_id", "project_id", "template_key", "status"}.issubset(
        graph_template_configs.columns.keys()
    )
