"""本地图谱 JSON 真源与 SQLite 索引存储。"""

from __future__ import annotations

import json
import os
import sqlite3
from pathlib import Path
from typing import Any, Dict, List, Optional

from ..models.project import ProjectManager
from .local_story_graph_models import GraphSnapshot
from .local_story_graph_support import project_id_from_graph_id


GRAPH_JSON_FILENAME = "story_graph.json"
GRAPH_DB_FILENAME = "story_graph.sqlite3"
GRAPH_JSON_TEMP = "story_graph.json.tmp"
GRAPH_DB_TEMP = "story_graph.sqlite3.tmp"

GRAPH_SCHEMA = (
    "CREATE TABLE graph_meta (key TEXT PRIMARY KEY, value TEXT NOT NULL)",
    "CREATE TABLE graph_nodes (uuid TEXT PRIMARY KEY, name TEXT NOT NULL, summary TEXT NOT NULL, attributes_json TEXT NOT NULL, evidence_refs_json TEXT NOT NULL)",
    "CREATE TABLE graph_node_labels (node_uuid TEXT NOT NULL, label TEXT NOT NULL, PRIMARY KEY (node_uuid, label))",
    "CREATE TABLE graph_aliases (alias TEXT NOT NULL, node_uuid TEXT NOT NULL, PRIMARY KEY (alias, node_uuid))",
    "CREATE TABLE graph_edges (uuid TEXT PRIMARY KEY, name TEXT NOT NULL, fact TEXT NOT NULL, source_node_uuid TEXT NOT NULL, target_node_uuid TEXT NOT NULL, attributes_json TEXT NOT NULL, weight INTEGER NOT NULL, evidence_refs_json TEXT NOT NULL)",
    "CREATE TABLE graph_evidence (owner_kind TEXT NOT NULL, owner_uuid TEXT NOT NULL, chapter_id TEXT NOT NULL, block_id TEXT NOT NULL, snippet TEXT NOT NULL)",
    "CREATE INDEX idx_graph_aliases_alias ON graph_aliases(alias)",
    "CREATE INDEX idx_graph_labels_label ON graph_node_labels(label)",
    "CREATE INDEX idx_graph_edges_source ON graph_edges(source_node_uuid)",
    "CREATE INDEX idx_graph_edges_target ON graph_edges(target_node_uuid)",
    "CREATE INDEX idx_graph_evidence_owner ON graph_evidence(owner_kind, owner_uuid)",
)


class LocalStoryGraphStorage:
    def graph_json_path(self, project_id: str) -> str:
        return ProjectManager._get_project_json_path(project_id, GRAPH_JSON_FILENAME)

    def graph_db_path(self, project_id: str) -> str:
        return ProjectManager._get_project_json_path(project_id, GRAPH_DB_FILENAME)

    def has_graph(self, project_id: str) -> bool:
        return os.path.exists(self.graph_json_path(project_id)) and os.path.exists(self.graph_db_path(project_id))

    def save_snapshot(self, project_id: str, snapshot: GraphSnapshot) -> None:
        project_dir = ProjectManager._get_project_dir(project_id)
        json_path = self.graph_json_path(project_id)
        db_path = self.graph_db_path(project_id)
        json_temp = os.path.join(project_dir, GRAPH_JSON_TEMP)
        db_temp = os.path.join(project_dir, GRAPH_DB_TEMP)
        self._write_json(json_temp, snapshot.to_dict())
        self._write_db(db_temp, snapshot)
        os.replace(json_temp, json_path)
        os.replace(db_temp, db_path)

    def load_snapshot(self, graph_id: str) -> Dict[str, Any]:
        project_id = self.resolve_project_id(graph_id)
        path = self.graph_json_path(project_id)
        if not os.path.exists(path):
            raise ValueError(f"图谱不存在: {graph_id}")
        with open(path, "r", encoding="utf-8") as file_obj:
            return json.load(file_obj)

    def load_all_nodes(self, graph_id: str) -> List[Dict[str, Any]]:
        rows = self._query_rows(graph_id, "SELECT * FROM graph_nodes ORDER BY name")
        labels = self._labels_by_node(graph_id)
        return [
            {
                "uuid": row["uuid"],
                "name": row["name"],
                "labels": labels.get(row["uuid"], []),
                "summary": row["summary"],
                "attributes": json.loads(row["attributes_json"]),
                "evidence_refs": json.loads(row["evidence_refs_json"]),
            }
            for row in rows
        ]

    def load_all_edges(self, graph_id: str) -> List[Dict[str, Any]]:
        rows = self._query_rows(graph_id, "SELECT * FROM graph_edges ORDER BY name, uuid")
        return [
            {
                "uuid": row["uuid"],
                "name": row["name"],
                "fact": row["fact"],
                "source_node_uuid": row["source_node_uuid"],
                "target_node_uuid": row["target_node_uuid"],
                "attributes": json.loads(row["attributes_json"]),
                "weight": int(row["weight"]),
                "evidence_refs": json.loads(row["evidence_refs_json"]),
            }
            for row in rows
        ]

    def load_node(self, graph_id: str, node_uuid: str) -> Optional[Dict[str, Any]]:
        rows = self._query_rows(graph_id, "SELECT * FROM graph_nodes WHERE uuid = ?", (node_uuid,))
        if not rows:
            return None
        labels = self._labels_by_node(graph_id)
        row = rows[0]
        return {
            "uuid": row["uuid"],
            "name": row["name"],
            "labels": labels.get(row["uuid"], []),
            "summary": row["summary"],
            "attributes": json.loads(row["attributes_json"]),
            "evidence_refs": json.loads(row["evidence_refs_json"]),
        }

    def load_node_edges(self, graph_id: str, node_uuid: str) -> List[Dict[str, Any]]:
        query = "SELECT * FROM graph_edges WHERE source_node_uuid = ? OR target_node_uuid = ? ORDER BY name, uuid"
        return self._query_edges(graph_id, query, (node_uuid, node_uuid))

    def resolve_project_id(self, graph_id: str) -> str:
        project_id = project_id_from_graph_id(graph_id)
        project = ProjectManager.get_project(project_id)
        if project:
            return project.project_id
        for item in ProjectManager.list_projects(limit=1000):
            if item.graph_id == graph_id:
                return item.project_id
        raise ValueError(f"未找到图谱所属项目: {graph_id}")

    def _query_edges(self, graph_id: str, query: str, params: tuple[Any, ...]) -> List[Dict[str, Any]]:
        rows = self._query_rows(graph_id, query, params)
        return [
            {
                "uuid": row["uuid"],
                "name": row["name"],
                "fact": row["fact"],
                "source_node_uuid": row["source_node_uuid"],
                "target_node_uuid": row["target_node_uuid"],
                "attributes": json.loads(row["attributes_json"]),
                "weight": int(row["weight"]),
                "evidence_refs": json.loads(row["evidence_refs_json"]),
            }
            for row in rows
        ]

    def _labels_by_node(self, graph_id: str) -> Dict[str, List[str]]:
        rows = self._query_rows(graph_id, "SELECT node_uuid, label FROM graph_node_labels ORDER BY label")
        labels: Dict[str, List[str]] = {}
        for row in rows:
            labels.setdefault(row["node_uuid"], []).append(row["label"])
        return labels

    def _query_rows(self, graph_id: str, query: str, params: tuple[Any, ...] = ()) -> List[sqlite3.Row]:
        project_id = self.resolve_project_id(graph_id)
        connection = sqlite3.connect(self.graph_db_path(project_id))
        connection.row_factory = sqlite3.Row
        try:
            return list(connection.execute(query, params).fetchall())
        finally:
            connection.close()

    def _write_json(self, path: str, payload: Dict[str, Any]) -> None:
        with open(path, "w", encoding="utf-8") as file_obj:
            json.dump(payload, file_obj, ensure_ascii=False, indent=2)

    def _write_db(self, path: str, snapshot: GraphSnapshot) -> None:
        if os.path.exists(path):
            os.remove(path)
        connection = sqlite3.connect(path)
        try:
            for statement in GRAPH_SCHEMA:
                connection.execute(statement)
            self._insert_meta(connection, snapshot)
            self._insert_nodes(connection, snapshot.to_dict()["nodes"])
            self._insert_edges(connection, snapshot.to_dict()["edges"])
            connection.commit()
        finally:
            connection.close()

    def _insert_meta(self, connection: sqlite3.Connection, snapshot: GraphSnapshot) -> None:
        payload = {
            "graph_id": snapshot.graph_id,
            "project_id": snapshot.project_id,
            "graph_name": snapshot.graph_name,
            "built_at": snapshot.built_at,
            "build_version": snapshot.build_version,
        }
        connection.executemany(
            "INSERT INTO graph_meta (key, value) VALUES (?, ?)",
            list(payload.items()),
        )

    def _insert_nodes(self, connection: sqlite3.Connection, nodes: List[Dict[str, Any]]) -> None:
        for node in nodes:
            connection.execute(
                "INSERT INTO graph_nodes VALUES (?, ?, ?, ?, ?)",
                (
                    node["uuid"],
                    node["name"],
                    node["summary"],
                    json.dumps(node["attributes"], ensure_ascii=False),
                    json.dumps(node["evidence_refs"], ensure_ascii=False),
                ),
            )
            connection.executemany(
                "INSERT INTO graph_node_labels VALUES (?, ?)",
                [(node["uuid"], label) for label in node["labels"]],
            )
            aliases = [str(item).strip() for item in node["attributes"].get("aliases", []) if str(item).strip()]
            connection.executemany(
                "INSERT INTO graph_aliases VALUES (?, ?)",
                [(alias, node["uuid"]) for alias in aliases],
            )
            self._insert_evidence(connection, "node", node["uuid"], node["evidence_refs"])

    def _insert_edges(self, connection: sqlite3.Connection, edges: List[Dict[str, Any]]) -> None:
        for edge in edges:
            connection.execute(
                "INSERT INTO graph_edges VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
                (
                    edge["uuid"],
                    edge["name"],
                    edge["fact"],
                    edge["source_node_uuid"],
                    edge["target_node_uuid"],
                    json.dumps(edge["attributes"], ensure_ascii=False),
                    int(edge["weight"]),
                    json.dumps(edge["evidence_refs"], ensure_ascii=False),
                ),
            )
            self._insert_evidence(connection, "edge", edge["uuid"], edge["evidence_refs"])

    def _insert_evidence(self, connection: sqlite3.Connection, owner_kind: str, owner_uuid: str, items: List[Dict[str, Any]]) -> None:
        rows = [
            (
                owner_kind,
                owner_uuid,
                str(item.get("chapter_id") or ""),
                str(item.get("block_id") or ""),
                str(item.get("snippet") or ""),
            )
            for item in items
        ]
        connection.executemany("INSERT INTO graph_evidence VALUES (?, ?, ?, ?, ?)", rows)
