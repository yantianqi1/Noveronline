"""Story graph repository.

Replaces local_story_graph_storage.py with SQLAlchemy Core access
through the unified database engine.

Tables: graph_meta, graph_nodes, graph_node_labels, graph_aliases,
        graph_edges, graph_evidence
"""

from __future__ import annotations

import json
from typing import Any

from sqlalchemy import Engine, and_, delete, insert, select

from app.tables.graph import (
    graph_aliases,
    graph_edges,
    graph_evidence,
    graph_meta,
    graph_node_labels,
    graph_nodes,
)

from .base import ProjectScopedRepository


class GraphRepository(ProjectScopedRepository):
    def __init__(self, engine: Engine):
        super().__init__(engine, graph_nodes)
        self.meta = ProjectScopedRepository(engine, graph_meta)
        self.edges = ProjectScopedRepository(engine, graph_edges)

    # ------------------------------------------------------------------
    # 1. has_graph
    # ------------------------------------------------------------------

    def has_graph(self, project_id: str) -> bool:
        """Check whether graph_meta contains any row for *project_id*."""
        return self.meta.exists(project_id)

    # ------------------------------------------------------------------
    # 2. save_snapshot (transactional DELETE-then-INSERT)
    # ------------------------------------------------------------------

    def save_snapshot(
        self,
        project_id: str,
        graph_id: str,
        snapshot_data: dict[str, Any],
    ) -> None:
        """Persist a full graph snapshot inside a single transaction.

        ``snapshot_data`` is the dict produced by ``GraphSnapshot.to_dict()``
        and must contain ``nodes``, ``edges``, and top-level metadata keys
        (``graph_name``, ``built_at``, ``build_version``).
        """
        with self.connect() as conn:
            # --- delete old data for this project (order matters for FK-like deps) ---
            for tbl in (graph_evidence, graph_aliases, graph_node_labels,
                        graph_edges, graph_nodes, graph_meta):
                conn.execute(delete(tbl).where(tbl.c.project_id == project_id))

            # --- graph_meta (key/value pairs) ---
            meta_payload = {
                "graph_id": graph_id,
                "project_id": project_id,
                "graph_name": snapshot_data.get("graph_name", ""),
                "built_at": snapshot_data.get("built_at", ""),
                "build_version": snapshot_data.get("build_version", ""),
            }
            for key, value in meta_payload.items():
                conn.execute(
                    insert(graph_meta).values(
                        project_id=project_id, key=key, value=str(value),
                    )
                )

            # --- nodes, labels, aliases, node evidence ---
            for node in snapshot_data.get("nodes", []):
                attrs_json = json.dumps(node.get("attributes", {}), ensure_ascii=False)
                ev_refs_json = json.dumps(node.get("evidence_refs", []), ensure_ascii=False)

                conn.execute(
                    insert(graph_nodes).values(
                        project_id=project_id,
                        uuid=node["uuid"],
                        name=node["name"],
                        summary=node.get("summary", ""),
                        attributes_json=attrs_json,
                        evidence_refs_json=ev_refs_json,
                    )
                )

                for label in node.get("labels", []):
                    conn.execute(
                        insert(graph_node_labels).values(
                            project_id=project_id,
                            node_uuid=node["uuid"],
                            label=label,
                        )
                    )

                aliases = [
                    str(a).strip()
                    for a in node.get("attributes", {}).get("aliases", [])
                    if str(a).strip()
                ]
                for alias in aliases:
                    conn.execute(
                        insert(graph_aliases).values(
                            project_id=project_id,
                            alias=alias,
                            node_uuid=node["uuid"],
                        )
                    )

                self._insert_evidence(conn, project_id, "node", node["uuid"],
                                      node.get("evidence_refs", []))

            # --- edges + edge evidence ---
            for edge in snapshot_data.get("edges", []):
                attrs_json = json.dumps(edge.get("attributes", {}), ensure_ascii=False)
                ev_refs_json = json.dumps(edge.get("evidence_refs", []), ensure_ascii=False)

                conn.execute(
                    insert(graph_edges).values(
                        project_id=project_id,
                        uuid=edge["uuid"],
                        name=edge["name"],
                        fact=edge.get("fact", ""),
                        source_node_uuid=edge["source_node_uuid"],
                        target_node_uuid=edge["target_node_uuid"],
                        attributes_json=attrs_json,
                        weight=int(edge.get("weight", 0)),
                        evidence_refs_json=ev_refs_json,
                    )
                )

                self._insert_evidence(conn, project_id, "edge", edge["uuid"],
                                      edge.get("evidence_refs", []))

    # ------------------------------------------------------------------
    # 3. load_snapshot  (graph_meta rows as a flat dict)
    # ------------------------------------------------------------------

    def load_snapshot(self, project_id: str) -> dict[str, Any] | None:
        """Return graph_meta key/value pairs as a flat dict, or None."""
        rows = self.meta.list_by_project(project_id, limit=100)
        if not rows:
            return None
        return {row["key"]: row["value"] for row in rows}

    # ------------------------------------------------------------------
    # 4. load_all_nodes  (LEFT JOIN graph_node_labels, aggregate labels)
    # ------------------------------------------------------------------

    def load_all_nodes(self, project_id: str) -> list[dict[str, Any]]:
        with self.connect() as conn:
            node_rows = conn.execute(
                select(graph_nodes)
                .where(graph_nodes.c.project_id == project_id)
                .order_by(graph_nodes.c.name)
            ).fetchall()

            label_rows = conn.execute(
                select(graph_node_labels.c.node_uuid, graph_node_labels.c.label)
                .where(graph_node_labels.c.project_id == project_id)
                .order_by(graph_node_labels.c.label)
            ).fetchall()

        labels_map: dict[str, list[str]] = {}
        for row in label_rows:
            labels_map.setdefault(row.node_uuid, []).append(row.label)

        return [
            {
                "uuid": r.uuid,
                "name": r.name,
                "labels": labels_map.get(r.uuid, []),
                "summary": r.summary,
                "attributes": json.loads(r.attributes_json),
                "evidence_refs": json.loads(r.evidence_refs_json),
            }
            for r in node_rows
        ]

    # ------------------------------------------------------------------
    # 5. load_all_edges
    # ------------------------------------------------------------------

    def load_all_edges(self, project_id: str) -> list[dict[str, Any]]:
        with self.connect() as conn:
            rows = conn.execute(
                select(graph_edges)
                .where(graph_edges.c.project_id == project_id)
                .order_by(graph_edges.c.name, graph_edges.c.uuid)
            ).fetchall()

        return [
            {
                "uuid": r.uuid,
                "name": r.name,
                "fact": r.fact,
                "source_node_uuid": r.source_node_uuid,
                "target_node_uuid": r.target_node_uuid,
                "attributes": json.loads(r.attributes_json),
                "weight": int(r.weight),
                "evidence_refs": json.loads(r.evidence_refs_json),
            }
            for r in rows
        ]

    # ------------------------------------------------------------------
    # 6. load_node  (single node + labels + aliases)
    # ------------------------------------------------------------------

    def load_node(self, project_id: str, node_uuid: str) -> dict[str, Any] | None:
        with self.connect() as conn:
            row = conn.execute(
                select(graph_nodes).where(
                    and_(
                        graph_nodes.c.project_id == project_id,
                        graph_nodes.c.uuid == node_uuid,
                    )
                ).limit(1)
            ).fetchone()
            if row is None:
                return None

            label_rows = conn.execute(
                select(graph_node_labels.c.label).where(
                    and_(
                        graph_node_labels.c.project_id == project_id,
                        graph_node_labels.c.node_uuid == node_uuid,
                    )
                ).order_by(graph_node_labels.c.label)
            ).fetchall()

            alias_rows = conn.execute(
                select(graph_aliases.c.alias).where(
                    and_(
                        graph_aliases.c.project_id == project_id,
                        graph_aliases.c.node_uuid == node_uuid,
                    )
                ).order_by(graph_aliases.c.alias)
            ).fetchall()

        return {
            "uuid": row.uuid,
            "name": row.name,
            "labels": [r.label for r in label_rows],
            "aliases": [r.alias for r in alias_rows],
            "summary": row.summary,
            "attributes": json.loads(row.attributes_json),
            "evidence_refs": json.loads(row.evidence_refs_json),
        }

    # ------------------------------------------------------------------
    # 7. load_node_edges
    # ------------------------------------------------------------------

    def load_node_edges(
        self, project_id: str, node_uuid: str,
    ) -> list[dict[str, Any]]:
        with self.connect() as conn:
            rows = conn.execute(
                select(graph_edges).where(
                    and_(
                        graph_edges.c.project_id == project_id,
                        (graph_edges.c.source_node_uuid == node_uuid)
                        | (graph_edges.c.target_node_uuid == node_uuid),
                    )
                ).order_by(graph_edges.c.name, graph_edges.c.uuid)
            ).fetchall()

        return [
            {
                "uuid": r.uuid,
                "name": r.name,
                "fact": r.fact,
                "source_node_uuid": r.source_node_uuid,
                "target_node_uuid": r.target_node_uuid,
                "attributes": json.loads(r.attributes_json),
                "weight": int(r.weight),
                "evidence_refs": json.loads(r.evidence_refs_json),
            }
            for r in rows
        ]

    # ------------------------------------------------------------------
    # 8. delete_graph
    # ------------------------------------------------------------------

    def delete_graph(self, project_id: str) -> None:
        """Delete all graph data for *project_id* across every graph table."""
        with self.connect() as conn:
            for tbl in (graph_evidence, graph_aliases, graph_node_labels,
                        graph_edges, graph_nodes, graph_meta):
                conn.execute(delete(tbl).where(tbl.c.project_id == project_id))

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _insert_evidence(
        conn,
        project_id: str,
        owner_kind: str,
        owner_uuid: str,
        items: list[dict[str, Any]],
    ) -> None:
        for item in items:
            conn.execute(
                insert(graph_evidence).values(
                    project_id=project_id,
                    owner_kind=owner_kind,
                    owner_uuid=owner_uuid,
                    chapter_id=str(item.get("chapter_id") or ""),
                    block_id=str(item.get("block_id") or ""),
                    snippet=str(item.get("snippet") or ""),
                )
            )
