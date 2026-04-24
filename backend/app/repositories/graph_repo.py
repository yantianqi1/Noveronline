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
    # 9. lookup_node_by_name_or_alias  (writer-agent fuzzy resolution)
    # ------------------------------------------------------------------

    def lookup_node_by_name_or_alias(
        self, project_id: str, name: str,
    ) -> dict[str, Any] | None:
        """Find a node by exact ``name`` or one of its aliases.

        Replaces the writer agent's raw-SQL fallback for fuzzy name resolution
        (``tool_executors._lookup_graph_node_by_name``). Returns a compact
        payload (not the full snapshot) because callers only need uuid/name/
        summary to decide whether to rehydrate via other repos.

        ``matched_via`` is ``"graph_node"`` when the direct name lookup hit,
        and ``"graph_alias"`` when the alias table redirected to a canonical.
        """
        if not name:
            return None
        with self.connect() as conn:
            row = conn.execute(
                select(graph_nodes.c.uuid, graph_nodes.c.name, graph_nodes.c.summary)
                .where(
                    and_(
                        graph_nodes.c.project_id == project_id,
                        graph_nodes.c.name == name,
                    )
                )
                .limit(1)
            ).fetchone()
            if row is not None:
                return {
                    "uuid": row.uuid,
                    "name": row.name,
                    "summary": row.summary or "",
                    "matched_via": "graph_node",
                }
            alias_row = conn.execute(
                select(graph_aliases.c.node_uuid)
                .where(
                    and_(
                        graph_aliases.c.project_id == project_id,
                        graph_aliases.c.alias == name,
                    )
                )
                .limit(1)
            ).fetchone()
            if alias_row is None:
                return None
            node_row = conn.execute(
                select(graph_nodes.c.uuid, graph_nodes.c.name, graph_nodes.c.summary)
                .where(
                    and_(
                        graph_nodes.c.project_id == project_id,
                        graph_nodes.c.uuid == alias_row.node_uuid,
                    )
                )
                .limit(1)
            ).fetchone()
            if node_row is None:
                return None
            return {
                "uuid": node_row.uuid,
                "name": node_row.name,
                "summary": node_row.summary or "",
                "matched_via": "graph_alias",
            }

    # ------------------------------------------------------------------
    # 10. find_graph_candidates  (substring + single-char decomposition)
    # ------------------------------------------------------------------

    def find_graph_candidates(
        self, project_id: str, name: str, *, limit: int = 5,
    ) -> list[dict[str, Any]]:
        """Fuzzy candidate search across graph_nodes + graph_aliases.

        Substring match first; if still under *limit* hits and the query is
        multi-char CJK, decompose into single CJK characters and search each.
        Caller is responsible for merging archive-table hits — this repo only
        covers graph data.

        Each candidate carries ``{canonical_name, source, summary, why}`` so
        the writer agent's suggestion block can render a human-readable
        disambiguation prompt.
        """
        if not name:
            return []
        pattern = f"%{name}%"
        out: list[dict[str, Any]] = []
        seen: set[str] = set()

        def _push(canonical: str, source: str, summary: str, why: str) -> None:
            if not canonical or canonical in seen:
                return
            seen.add(canonical)
            out.append(
                {
                    "canonical_name": canonical,
                    "source": source,
                    "summary": (summary or "")[:120],
                    "why": why,
                }
            )

        with self.connect() as conn:
            for row in conn.execute(
                select(graph_nodes.c.name, graph_nodes.c.summary)
                .where(
                    and_(
                        graph_nodes.c.project_id == project_id,
                        graph_nodes.c.name.like(pattern),
                    )
                )
                .limit(15)
            ).fetchall():
                _push(row.name, "graph_node", row.summary or "", f"名字含「{name}」")

            for row in conn.execute(
                select(
                    graph_aliases.c.alias.label("alias"),
                    graph_nodes.c.name.label("canonical_name"),
                    graph_nodes.c.summary.label("summary"),
                )
                .select_from(
                    graph_aliases.join(
                        graph_nodes,
                        and_(
                            graph_aliases.c.project_id == graph_nodes.c.project_id,
                            graph_aliases.c.node_uuid == graph_nodes.c.uuid,
                        ),
                    )
                )
                .where(
                    and_(
                        graph_aliases.c.project_id == project_id,
                        graph_aliases.c.alias.like(pattern),
                    )
                )
                .limit(15)
            ).fetchall():
                _push(
                    row.canonical_name,
                    "graph_alias",
                    row.summary or "",
                    f"别名「{row.alias}」含「{name}」",
                )

            if len(out) < limit and len(name) >= 2:
                cjk_chars = [c for c in name if _is_cjk_char(c)]
                for ch in cjk_chars[:2]:
                    if len(out) >= limit * 2:
                        break
                    char_pat = f"%{ch}%"
                    for row in conn.execute(
                        select(graph_nodes.c.name, graph_nodes.c.summary)
                        .where(
                            and_(
                                graph_nodes.c.project_id == project_id,
                                graph_nodes.c.name.like(char_pat),
                                # Cap to plausible names; seed pipeline sometimes
                                # dumps plot-fact strings into graph_nodes.name.
                                # SQLite LENGTH() counts characters, not bytes.
                            )
                        )
                        .limit(10)
                    ).fetchall():
                        if len(row.name) > 10:
                            continue
                        _push(
                            row.name,
                            "graph_node",
                            row.summary or "",
                            f"含单字「{ch}」（与「{name}」共享）",
                        )
        return out[:limit]

    # ------------------------------------------------------------------
    # 11. find_edges_between  (ordered by weight DESC)
    # ------------------------------------------------------------------

    def find_edges_between(
        self,
        project_id: str,
        uuid_a: str,
        uuid_b: str,
        *,
        limit: int = 15,
    ) -> list[dict[str, Any]]:
        """All edges between two nodes in either direction, strongest first."""
        if not uuid_a or not uuid_b:
            return []
        stmt = (
            select(
                graph_edges.c.name,
                graph_edges.c.fact,
                graph_edges.c.source_node_uuid,
                graph_edges.c.target_node_uuid,
                graph_edges.c.weight,
            )
            .where(
                and_(
                    graph_edges.c.project_id == project_id,
                    (
                        (graph_edges.c.source_node_uuid == uuid_a)
                        & (graph_edges.c.target_node_uuid == uuid_b)
                    )
                    | (
                        (graph_edges.c.source_node_uuid == uuid_b)
                        & (graph_edges.c.target_node_uuid == uuid_a)
                    ),
                )
            )
            .order_by(graph_edges.c.weight.desc())
            .limit(limit)
        )
        with self.connect() as conn:
            rows = conn.execute(stmt).fetchall()
        return [
            {
                "name": r.name,
                "fact": r.fact or "",
                "source_node_uuid": r.source_node_uuid,
                "target_node_uuid": r.target_node_uuid,
                "weight": int(r.weight or 0),
            }
            for r in rows
        ]

    # ------------------------------------------------------------------
    # 12. get_node_labels  (labels only, not the full node row)
    # ------------------------------------------------------------------

    def get_node_labels(
        self, project_id: str, node_uuid: str, *, limit: int = 8,
    ) -> list[str]:
        if not node_uuid:
            return []
        stmt = (
            select(graph_node_labels.c.label)
            .where(
                and_(
                    graph_node_labels.c.project_id == project_id,
                    graph_node_labels.c.node_uuid == node_uuid,
                )
            )
            .order_by(graph_node_labels.c.label)
            .limit(limit)
        )
        with self.connect() as conn:
            return [r.label for r in conn.execute(stmt).fetchall()]

    # ------------------------------------------------------------------
    # 13. find_nodes_by_label  (e.g. PlotEvent, Conflict)
    # ------------------------------------------------------------------

    def find_nodes_by_label(
        self, project_id: str, label: str, *, name_contains: str | None = None,
        limit: int = 5,
    ) -> list[dict[str, Any]]:
        """Nodes tagged with *label*, optionally filtered by name substring.

        Returns compact dicts with ``uuid / name / summary / attributes``
        (attributes pre-parsed from JSON).
        """
        if not label:
            return []
        join = graph_nodes.join(
            graph_node_labels,
            and_(
                graph_nodes.c.project_id == graph_node_labels.c.project_id,
                graph_nodes.c.uuid == graph_node_labels.c.node_uuid,
            ),
        )
        clauses = [
            graph_nodes.c.project_id == project_id,
            graph_node_labels.c.label == label,
        ]
        if name_contains:
            clauses.append(graph_nodes.c.name.like(f"%{name_contains}%"))
        stmt = (
            select(
                graph_nodes.c.uuid,
                graph_nodes.c.name,
                graph_nodes.c.summary,
                graph_nodes.c.attributes_json,
            )
            .select_from(join)
            .where(and_(*clauses))
            .order_by(graph_nodes.c.name)
            .limit(limit)
        )
        with self.connect() as conn:
            rows = conn.execute(stmt).fetchall()
        return [
            {
                "uuid": r.uuid,
                "name": r.name,
                "summary": r.summary or "",
                "attributes": json.loads(r.attributes_json) if r.attributes_json else {},
            }
            for r in rows
        ]

    # ------------------------------------------------------------------
    # 14. get_neighbors_with_labels  (neighbor rollup for relationship network)
    # ------------------------------------------------------------------

    def get_neighbors_with_labels(
        self, project_id: str, node_uuid: str, *, limit: int = 30,
    ) -> list[dict[str, Any]]:
        """Return neighbor summaries for a node: the edge + opposite-end node + labels.

        Used by the writer agent's ``query_relationship_network`` tool. Caller
        filters by ``label`` (e.g. "Character") after the fact — this keeps the
        repo query simple and the filter logic in one place.
        """
        if not node_uuid:
            return []
        edge_stmt = (
            select(
                graph_edges.c.name.label("edge_name"),
                graph_edges.c.fact.label("edge_fact"),
                graph_edges.c.weight.label("edge_weight"),
                graph_edges.c.source_node_uuid,
                graph_edges.c.target_node_uuid,
            )
            .where(
                and_(
                    graph_edges.c.project_id == project_id,
                    (graph_edges.c.source_node_uuid == node_uuid)
                    | (graph_edges.c.target_node_uuid == node_uuid),
                )
            )
            .order_by(graph_edges.c.weight.desc())
            .limit(limit * 2)  # over-fetch; label filter may drop some
        )
        with self.connect() as conn:
            edge_rows = conn.execute(edge_stmt).fetchall()
            if not edge_rows:
                return []

            # Collect opposite-end uuids
            other_uuids: list[str] = []
            for r in edge_rows:
                other = (
                    r.target_node_uuid
                    if r.source_node_uuid == node_uuid
                    else r.source_node_uuid
                )
                if other not in other_uuids:
                    other_uuids.append(other)

            # Bulk-load neighbor nodes and their labels
            node_rows = conn.execute(
                select(graph_nodes.c.uuid, graph_nodes.c.name, graph_nodes.c.summary)
                .where(
                    and_(
                        graph_nodes.c.project_id == project_id,
                        graph_nodes.c.uuid.in_(other_uuids),
                    )
                )
            ).fetchall()
            nodes_map = {n.uuid: n for n in node_rows}

            label_rows = conn.execute(
                select(graph_node_labels.c.node_uuid, graph_node_labels.c.label)
                .where(
                    and_(
                        graph_node_labels.c.project_id == project_id,
                        graph_node_labels.c.node_uuid.in_(other_uuids),
                    )
                )
            ).fetchall()
            labels_map: dict[str, list[str]] = {}
            for lr in label_rows:
                labels_map.setdefault(lr.node_uuid, []).append(lr.label)

        out: list[dict[str, Any]] = []
        for r in edge_rows:
            other_uuid = (
                r.target_node_uuid
                if r.source_node_uuid == node_uuid
                else r.source_node_uuid
            )
            node = nodes_map.get(other_uuid)
            if node is None:
                continue
            direction = "outgoing" if r.source_node_uuid == node_uuid else "incoming"
            out.append(
                {
                    "neighbor_uuid": other_uuid,
                    "neighbor_name": node.name,
                    "neighbor_summary": node.summary or "",
                    "neighbor_labels": labels_map.get(other_uuid, []),
                    "edge_name": r.edge_name,
                    "edge_fact": r.edge_fact or "",
                    "edge_weight": int(r.edge_weight or 0),
                    "direction": direction,
                }
            )
            if len(out) >= limit:
                break
        return out


# ----------------------------------------------------------------------
# Module-level helpers
# ----------------------------------------------------------------------


def _is_cjk_char(ch: str) -> bool:
    """Narrow CJK check — only Han Unified Ideographs + extension A."""
    if not ch or len(ch) != 1:
        return False
    code = ord(ch)
    return 0x4E00 <= code <= 0x9FFF or 0x3400 <= code <= 0x4DBF

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
