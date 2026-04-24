"""Unit tests for GraphRepository additions (Task 3 of 2026-04-19 writer-agent optimization).

These methods replace raw ``text()`` SQL in writer_agent/tool_executors.py.
"""

from __future__ import annotations

import json

from sqlalchemy import create_engine, insert

from app.database import init_db
from app.repositories.graph_repo import GraphRepository
from app.tables.graph import (
    graph_aliases,
    graph_edges,
    graph_node_labels,
    graph_nodes,
)


def _build_engine():
    engine = create_engine("sqlite:///:memory:", future=True)
    init_db(engine)
    return engine


def _seed_nodes(engine, project_id: str, nodes: list[dict]) -> None:
    """Minimal seed helper that bypasses save_snapshot for per-test control."""
    with engine.begin() as conn:
        for n in nodes:
            conn.execute(
                insert(graph_nodes).values(
                    project_id=project_id,
                    uuid=n["uuid"],
                    name=n["name"],
                    summary=n.get("summary", ""),
                    attributes_json=json.dumps(n.get("attributes", {}), ensure_ascii=False),
                    evidence_refs_json="[]",
                )
            )
            for label in n.get("labels", []):
                conn.execute(
                    insert(graph_node_labels).values(
                        project_id=project_id,
                        node_uuid=n["uuid"],
                        label=label,
                    )
                )
            for alias in n.get("aliases", []):
                conn.execute(
                    insert(graph_aliases).values(
                        project_id=project_id,
                        alias=alias,
                        node_uuid=n["uuid"],
                    )
                )


def _seed_edges(engine, project_id: str, edges: list[dict]) -> None:
    with engine.begin() as conn:
        for e in edges:
            conn.execute(
                insert(graph_edges).values(
                    project_id=project_id,
                    uuid=e["uuid"],
                    name=e["name"],
                    fact=e.get("fact", ""),
                    source_node_uuid=e["source"],
                    target_node_uuid=e["target"],
                    attributes_json="{}",
                    weight=int(e.get("weight", 1)),
                    evidence_refs_json="[]",
                )
            )


# ---------------------------------------------------------------------------
# lookup_node_by_name_or_alias
# ---------------------------------------------------------------------------


def test_lookup_node_by_name_exact_match():
    engine = _build_engine()
    repo = GraphRepository(engine)
    _seed_nodes(engine, "p", [{"uuid": "n1", "name": "陈迹", "summary": "主角"}])

    result = repo.lookup_node_by_name_or_alias("p", "陈迹")
    assert result is not None
    assert result["uuid"] == "n1"
    assert result["name"] == "陈迹"
    assert result["matched_via"] == "graph_node"


def test_lookup_node_by_alias_redirects_to_canonical():
    engine = _build_engine()
    repo = GraphRepository(engine)
    _seed_nodes(
        engine, "p",
        [{"uuid": "n1", "name": "朱灵韵", "summary": "主角", "aliases": ["白鲤"]}],
    )

    result = repo.lookup_node_by_name_or_alias("p", "白鲤")
    assert result is not None
    assert result["name"] == "朱灵韵"  # canonical
    assert result["matched_via"] == "graph_alias"


def test_lookup_node_returns_none_on_miss():
    engine = _build_engine()
    repo = GraphRepository(engine)
    assert repo.lookup_node_by_name_or_alias("p", "不存在") is None
    assert repo.lookup_node_by_name_or_alias("p", "") is None


def test_lookup_node_respects_project_scope():
    engine = _build_engine()
    repo = GraphRepository(engine)
    _seed_nodes(engine, "p1", [{"uuid": "n1", "name": "陈迹"}])
    _seed_nodes(engine, "p2", [{"uuid": "n2", "name": "其他"}])

    assert repo.lookup_node_by_name_or_alias("p1", "其他") is None
    assert repo.lookup_node_by_name_or_alias("p2", "陈迹") is None


# ---------------------------------------------------------------------------
# find_graph_candidates
# ---------------------------------------------------------------------------


def test_find_graph_candidates_substring_in_name():
    engine = _build_engine()
    repo = GraphRepository(engine)
    _seed_nodes(
        engine, "p",
        [
            {"uuid": "n1", "name": "陈迹", "summary": "主角"},
            {"uuid": "n2", "name": "陈老夫人", "summary": "陈迹之母"},
            {"uuid": "n3", "name": "无关节点"},
        ],
    )
    results = repo.find_graph_candidates("p", "陈")
    names = [r["canonical_name"] for r in results]
    assert "陈迹" in names
    assert "陈老夫人" in names
    assert "无关节点" not in names


def test_find_graph_candidates_alias_substring():
    engine = _build_engine()
    repo = GraphRepository(engine)
    _seed_nodes(
        engine, "p",
        [{"uuid": "n1", "name": "朱灵韵", "aliases": ["白鲤", "银鱼"]}],
    )
    results = repo.find_graph_candidates("p", "白")
    assert len(results) >= 1
    assert results[0]["canonical_name"] == "朱灵韵"
    assert "白鲤" in results[0]["why"]
    assert results[0]["source"] == "graph_alias"


def test_find_graph_candidates_single_char_decomposition_for_multichar_name():
    engine = _build_engine()
    repo = GraphRepository(engine)
    _seed_nodes(
        engine, "p",
        [
            {"uuid": "n1", "name": "陈迹"},
            {"uuid": "n2", "name": "陈老夫人"},
            {"uuid": "n3", "name": "苏白"},
        ],
    )
    # Exact "陈苏" doesn't exist; fall back to single chars: "陈" + "苏"
    results = repo.find_graph_candidates("p", "陈苏", limit=5)
    names = [r["canonical_name"] for r in results]
    # Both 陈-containing and 苏-containing nodes should surface
    assert "陈迹" in names or "陈老夫人" in names
    assert "苏白" in names


def test_find_graph_candidates_respects_limit():
    engine = _build_engine()
    repo = GraphRepository(engine)
    _seed_nodes(
        engine, "p",
        [{"uuid": f"n{i}", "name": f"人物{i}"} for i in range(10)],
    )
    results = repo.find_graph_candidates("p", "人物", limit=3)
    assert len(results) == 3


# ---------------------------------------------------------------------------
# find_edges_between
# ---------------------------------------------------------------------------


def test_find_edges_between_covers_both_directions():
    engine = _build_engine()
    repo = GraphRepository(engine)
    _seed_nodes(engine, "p", [
        {"uuid": "a", "name": "A"},
        {"uuid": "b", "name": "B"},
    ])
    _seed_edges(engine, "p", [
        {"uuid": "e1", "name": "敌对", "source": "a", "target": "b", "weight": 5},
        {"uuid": "e2", "name": "暗恋", "source": "b", "target": "a", "weight": 2},
    ])

    edges = repo.find_edges_between("p", "a", "b")
    assert len(edges) == 2
    # Ordered by weight DESC
    assert edges[0]["weight"] == 5
    assert edges[1]["weight"] == 2


def test_find_edges_between_empty_when_no_edges():
    engine = _build_engine()
    repo = GraphRepository(engine)
    _seed_nodes(engine, "p", [
        {"uuid": "a", "name": "A"},
        {"uuid": "b", "name": "B"},
    ])
    assert repo.find_edges_between("p", "a", "b") == []


def test_find_edges_between_blank_uuids_returns_empty():
    engine = _build_engine()
    repo = GraphRepository(engine)
    assert repo.find_edges_between("p", "", "b") == []


# ---------------------------------------------------------------------------
# get_node_labels
# ---------------------------------------------------------------------------


def test_get_node_labels_returns_sorted_list():
    engine = _build_engine()
    repo = GraphRepository(engine)
    _seed_nodes(engine, "p", [
        {"uuid": "n1", "name": "X", "labels": ["Character", "Protagonist"]},
    ])
    labels = repo.get_node_labels("p", "n1")
    assert "Character" in labels
    assert "Protagonist" in labels


def test_get_node_labels_empty_for_unknown_node():
    engine = _build_engine()
    repo = GraphRepository(engine)
    assert repo.get_node_labels("p", "missing") == []
    assert repo.get_node_labels("p", "") == []


# ---------------------------------------------------------------------------
# find_nodes_by_label
# ---------------------------------------------------------------------------


def test_find_nodes_by_label_filters_correctly():
    engine = _build_engine()
    repo = GraphRepository(engine)
    _seed_nodes(engine, "p", [
        {"uuid": "n1", "name": "开场战役", "labels": ["PlotEvent"]},
        {"uuid": "n2", "name": "主角", "labels": ["Character"]},
        {"uuid": "n3", "name": "二次战役", "labels": ["PlotEvent"]},
    ])

    events = repo.find_nodes_by_label("p", "PlotEvent")
    names = [e["name"] for e in events]
    assert "开场战役" in names
    assert "二次战役" in names
    assert "主角" not in names


def test_find_nodes_by_label_with_name_contains_filter():
    engine = _build_engine()
    repo = GraphRepository(engine)
    _seed_nodes(engine, "p", [
        {"uuid": "n1", "name": "开场战役", "labels": ["PlotEvent"]},
        {"uuid": "n2", "name": "二次战役", "labels": ["PlotEvent"]},
        {"uuid": "n3", "name": "最终决战", "labels": ["PlotEvent"]},
    ])

    events = repo.find_nodes_by_label("p", "PlotEvent", name_contains="战役")
    names = [e["name"] for e in events]
    assert "开场战役" in names
    assert "二次战役" in names
    assert "最终决战" not in names


# ---------------------------------------------------------------------------
# get_neighbors_with_labels
# ---------------------------------------------------------------------------


def test_get_neighbors_with_labels_rolls_up_neighbor_data():
    engine = _build_engine()
    repo = GraphRepository(engine)
    _seed_nodes(engine, "p", [
        {"uuid": "hero", "name": "主角", "labels": ["Character"]},
        {"uuid": "friend", "name": "朋友", "labels": ["Character"], "summary": "好友"},
        {"uuid": "artifact", "name": "神剑", "labels": ["Artifact"]},
    ])
    _seed_edges(engine, "p", [
        {"uuid": "e1", "name": "友谊", "source": "hero", "target": "friend", "weight": 5, "fact": "结义"},
        {"uuid": "e2", "name": "持有", "source": "hero", "target": "artifact", "weight": 3},
    ])

    neighbors = repo.get_neighbors_with_labels("p", "hero")
    # Order by edge_weight DESC: friend first (5), artifact second (3)
    assert neighbors[0]["neighbor_name"] == "朋友"
    assert neighbors[0]["neighbor_labels"] == ["Character"]
    assert neighbors[0]["edge_name"] == "友谊"
    assert neighbors[0]["edge_fact"] == "结义"
    assert neighbors[0]["direction"] == "outgoing"
    assert neighbors[1]["neighbor_name"] == "神剑"
    assert neighbors[1]["neighbor_labels"] == ["Artifact"]


def test_get_neighbors_with_labels_handles_incoming_edges():
    engine = _build_engine()
    repo = GraphRepository(engine)
    _seed_nodes(engine, "p", [
        {"uuid": "hero", "name": "主角"},
        {"uuid": "enemy", "name": "反派"},
    ])
    _seed_edges(engine, "p", [
        {"uuid": "e1", "name": "追杀", "source": "enemy", "target": "hero", "weight": 9},
    ])

    neighbors = repo.get_neighbors_with_labels("p", "hero")
    assert neighbors[0]["neighbor_name"] == "反派"
    assert neighbors[0]["direction"] == "incoming"


def test_get_neighbors_with_labels_empty_for_isolated_node():
    engine = _build_engine()
    repo = GraphRepository(engine)
    _seed_nodes(engine, "p", [{"uuid": "lonely", "name": "孤独者"}])
    assert repo.get_neighbors_with_labels("p", "lonely") == []
