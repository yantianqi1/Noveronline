from __future__ import annotations

import json
import uuid
from typing import Any

from .models import FAMILY_DEPENDENCIES, FamilyPlan, ImportPlan, PlannedRecord, stable_hash
from .source import LegacySource, first_nonempty


IMPORT_NAMESPACE = uuid.UUID("de2b041f-a9c8-5b36-b24e-3cb2c2ca8d2c")
GRAPH_NODE_TYPES = {
    "character",
    "organization",
    "faction",
    "location",
    "artifact",
    "plot_event",
    "plot_thread",
    "world_rule",
    "concept",
    "manuscript_scene",
}


def deterministic_id(
    import_id: str,
    tenant_id: str,
    project_id: str,
    family: str,
    source_key: str,
) -> str:
    return str(
        uuid.uuid5(
            IMPORT_NAMESPACE,
            "\x1f".join((import_id, tenant_id, project_id, family, source_key)),
        )
    )


class LegacyImportPlanner:
    def __init__(
        self,
        source: LegacySource,
        *,
        import_id: str,
        tenant_id: str,
        project_id: str,
        actor_user_id: str,
        source_project_id: str,
    ) -> None:
        for value in (import_id, tenant_id, project_id, actor_user_id):
            uuid.UUID(value)
        self.source = source
        self.import_id = import_id
        self.tenant_id = tenant_id
        self.project_id = project_id
        self.actor_user_id = actor_user_id
        self.source_project_id = source_project_id
        self.fingerprint = source.inspect().fingerprint
        self.families = {name: FamilyPlan(name) for name in FAMILY_DEPENDENCIES}
        self.entity_ids: dict[str, str] = {}
        self.entity_names: dict[str, str] = {}
        self.archive_asset_ids: dict[str, str] = {}
        self.archive_memory_ids: dict[str, str] = {}
        self.chapter_ids: dict[str, str] = {}

    def build(self) -> ImportPlan:
        self._project()
        self._source_artifacts()
        self._entities()
        self._aliases()
        self._evidence()
        self._relationships()
        self._assets()
        self._archive()
        self._graph()
        self._worldline()
        self._writer()
        self._manuscript()
        inspection = self.source.inspect()
        if inspection.fingerprint != self.fingerprint:
            raise RuntimeError("SOURCE_CHANGED_DURING_PLAN")
        return ImportPlan(
            import_id=self.import_id,
            tenant_id=self.tenant_id,
            project_id=self.project_id,
            actor_user_id=self.actor_user_id,
            source_project_id=self.source_project_id,
            source=inspection,
            families=self.families,
        )

    def _id(self, family: str, source_key: Any) -> str:
        return deterministic_id(
            self.import_id,
            self.tenant_id,
            self.project_id,
            family,
            str(source_key),
        )

    def _provenance(self, family: str, source_table: str, source_key: str) -> dict[str, str]:
        return {
            "import_id": self.import_id,
            "source_fingerprint": self.fingerprint,
            "family": family,
            "source_table": source_table,
            "source_key_hash": self._source_key_hash(source_key),
        }

    def _record(
        self,
        family: str,
        table: str,
        key_column: str,
        key: str,
        values: dict[str, Any],
        compare_columns: tuple[str, ...] | None = None,
    ) -> None:
        self.families[family].records.append(
            PlannedRecord(
                family=family,
                table=table,
                key_column=key_column,
                key=key,
                values=values,
                compare_columns=compare_columns or tuple(values),
            )
        )

    def _project(self) -> None:
        rows = self.source.rows("project_meta", self.source_project_id)
        self.families["project"].source_count = len(rows)
        if not rows:
            self.families["project"].reason_codes.append("SOURCE_PROJECT_METADATA_ABSENT")

    def _source_artifacts(self) -> None:
        rows = self.source.rows("project_artifacts", self.source_project_id)
        source_rows = self.source.rows("archive_sources", self.source_project_id)
        family = self.families["source"]
        family.source_count = len(rows) + len(source_rows)
        family.deferred_count = family.source_count
        if rows or source_rows:
            family.reason_codes.append("OBJECT_STORAGE_DESTINATION_REQUIRED")

    def _entities(self) -> None:
        rows = self.source.rows("entities", self.source_project_id)
        family = self.families["entities"]
        family.source_count = len(rows)
        if not rows:
            return
        run_id = self._workflow_run("entities", "legacy-entities")
        for index, row in enumerate(rows):
            source_key = first_nonempty(row, ("entity_id", "name"), str(index))
            entity_id = self._id("entities", source_key)
            name = first_nonempty(row, ("name",), f"legacy-entity-{index + 1}")
            self.entity_ids[source_key] = entity_id
            self.entity_names[source_key] = name
            metadata = self.source.json_value(row.get("profile_json"), {})
            if not isinstance(metadata, dict):
                metadata = {}
            metadata = {**metadata, "legacy_import": self._provenance("entities", "entities", source_key)}
            values = {
                "tenant_id": self.tenant_id,
                "entity_id": entity_id,
                "project_id": self.project_id,
                "source_run_id": run_id,
                "canonical_name": name,
                "entity_type": first_nonempty(row, ("entity_type",), "character"),
                "importance": row.get("importance_tier"),
                "state_summary": row.get("summary"),
                "metadata_jsonb": metadata,
            }
            self._record("entities", "entities", "entity_id", entity_id, values)

    def _aliases(self) -> None:
        rows = self.source.rows("entity_aliases", self.source_project_id)
        family = self.families["aliases"]
        family.source_count = len(rows)
        for index, row in enumerate(rows):
            source_entity = str(row.get("entity_id") or "")
            entity_id = self.entity_ids.get(source_entity)
            if not entity_id:
                family.deferred_count += 1
                family.reason_codes.append("ENTITY_DEPENDENCY_MISSING")
                continue
            alias = first_nonempty(row, ("alias",), f"legacy-alias-{index + 1}")
            alias_id = self._id("aliases", f"{source_entity}:{alias}")
            self._record(
                "aliases",
                "entity_aliases",
                "alias_id",
                alias_id,
                {
                    "tenant_id": self.tenant_id,
                    "alias_id": alias_id,
                    "project_id": self.project_id,
                    "entity_id": entity_id,
                    "alias": alias,
                },
            )

    def _evidence(self) -> None:
        rows = self.source.rows("entity_evidence", self.source_project_id)
        labels = self.source.rows("entity_labels", self.source_project_id)
        relationship_events = self.source.rows("relationship_events", self.source_project_id)
        character_events = self.source.rows("character_events", self.source_project_id)
        relationship_rows = {
            str(row.get("relation_id") or ""): row
            for row in self.source.rows("relationships", self.source_project_id)
            if row.get("relation_id")
        }
        family = self.families["evidence"]
        family.source_count = len(rows) + len(labels) + len(relationship_events) + len(character_events)
        if family.source_count == 0:
            return
        run_id = self._workflow_run("evidence", "legacy-evidence")
        segment_ids: dict[str, str] = {}

        def segment_id(row: dict[str, Any], index: int) -> str:
            source_segment = first_nonempty(row, ("segment_id", "chapter_id"), f"legacy-{index}")
            existing = segment_ids.get(source_segment)
            if existing:
                return existing
            target_segment = self._id("evidence-segment", source_segment)
            segment_ids[source_segment] = target_segment
            excerpt = first_nonempty(row, ("snippet", "evidence", "summary"))
            self._record("evidence", "text_segments", "segment_id", target_segment, {
                "tenant_id": self.tenant_id, "segment_id": target_segment,
                "project_id": self.project_id, "run_id": run_id, "source_file_id": None,
                "segment_order": len(segment_ids) - 1, "chapter_guess": row.get("chapter_id"),
                "title_guess": None, "start_offset": None, "end_offset": None,
                "content_excerpt": excerpt, "object_key": None, "summary": None,
                "metadata_jsonb": {"legacy_import": self._provenance("evidence", "text_segments", source_segment)},
            })
            return target_segment

        for index, row in enumerate(rows):
            source_owner = str(row.get("owner_id") or row.get("entity_id") or "")
            owner_type = first_nonempty(row, ("owner_type",), "entity").strip().lower()
            if owner_type in {"relationship", "relation"}:
                relationship = relationship_rows.get(source_owner)
                source_name = self.entity_names.get(str((relationship or {}).get("source_id") or ""))
                target_name = self.entity_names.get(str((relationship or {}).get("target_id") or ""))
                if not relationship or not source_name or not target_name:
                    self._defer("evidence", "ENTITY_DEPENDENCY_MISSING")
                    continue
                source_key = first_nonempty(row, ("evidence_id",), str(index))
                event_id = self._id("relationship-evidence", source_key)
                evidence_text = first_nonempty(
                    row, ("snippet", "evidence"), "legacy relationship evidence"
                )
                self._record("evidence", "relationship_events", "relationship_event_id", event_id, {
                    "tenant_id": self.tenant_id, "relationship_event_id": event_id,
                    "project_id": self.project_id, "run_id": run_id,
                    "segment_id": segment_id(row, index),
                    "source_entity_name": source_name, "target_entity_name": target_name,
                    "relationship_type": first_nonempty(
                        relationship, ("relation_type",), "related_to"
                    ),
                    "event_summary": evidence_text, "evidence_text": evidence_text,
                    "metadata_jsonb": {
                        "legacy_import": self._provenance(
                            "evidence", "entity_evidence", source_key
                        )
                    },
                })
                continue
            if owner_type not in {"", "entity"}:
                self._defer("evidence", "EVIDENCE_OWNER_TYPE_UNSUPPORTED")
                continue
            entity_id = self.entity_ids.get(source_owner)
            if not entity_id:
                self._defer("evidence", "ENTITY_DEPENDENCY_MISSING")
                continue
            source_key = first_nonempty(row, ("evidence_id",), str(index))
            evidence_id = self._id("entity-evidence", source_key)
            self._record("evidence", "entity_evidence", "evidence_id", evidence_id, {
                "tenant_id": self.tenant_id, "evidence_id": evidence_id,
                "project_id": self.project_id, "entity_id": entity_id, "run_id": run_id,
                "segment_id": segment_id(row, index),
                "evidence_text": first_nonempty(row, ("snippet", "evidence"), "legacy evidence"),
                "source_kind": "legacy_import",
                "metadata_jsonb": {"legacy_import": self._provenance("evidence", "entity_evidence", source_key)},
            })
        for index, row in enumerate(labels):
            entity_id = self.entity_ids.get(str(row.get("entity_id") or ""))
            if not entity_id:
                self._defer("evidence", "ENTITY_DEPENDENCY_MISSING")
                continue
            source_key = f"{row.get('entity_id')}:{row.get('label')}:{index}"
            label_id = self._id("entity-label", source_key)
            self._record("evidence", "entity_labels", "label_id", label_id, {
                "tenant_id": self.tenant_id, "label_id": label_id, "project_id": self.project_id,
                "entity_id": entity_id, "run_id": run_id, "segment_id": segment_id(row, index),
                "label": first_nonempty(row, ("label",), "legacy"),
                "label_type": first_nonempty(row, ("label_type",), "tag"),
                "source_kind": "legacy_import",
                "metadata_jsonb": {"legacy_import": self._provenance("evidence", "entity_labels", source_key)},
            })
        for index, row in enumerate(relationship_events):
            source_name = self.entity_names.get(str(row.get("source_entity_id") or ""))
            target_name = self.entity_names.get(str(row.get("target_entity_id") or ""))
            if not source_name or not target_name:
                self._defer("evidence", "ENTITY_DEPENDENCY_MISSING")
                continue
            source_key = first_nonempty(row, ("event_id",), str(index))
            event_id = self._id("relationship-event", source_key)
            self._record("evidence", "relationship_events", "relationship_event_id", event_id, {
                "tenant_id": self.tenant_id, "relationship_event_id": event_id,
                "project_id": self.project_id, "run_id": run_id, "segment_id": segment_id(row, index),
                "source_entity_name": source_name, "target_entity_name": target_name,
                "relationship_type": first_nonempty(row, ("relation_type",), "related_to"),
                "event_summary": first_nonempty(row, ("trigger_event", "new_state", "evidence"), "legacy relationship event"),
                "evidence_text": row.get("evidence"),
                "metadata_jsonb": {"legacy_import": self._provenance("evidence", "relationship_events", source_key)},
            })
        for index, row in enumerate(character_events):
            entity_name = self.entity_names.get(str(row.get("entity_id") or ""))
            if not entity_name:
                self._defer("evidence", "ENTITY_DEPENDENCY_MISSING")
                continue
            source_key = first_nonempty(row, ("event_id",), str(index))
            event_id = self._id("character-event", source_key)
            self._record("evidence", "character_events", "character_event_id", event_id, {
                "tenant_id": self.tenant_id, "character_event_id": event_id,
                "project_id": self.project_id, "run_id": run_id, "segment_id": segment_id(row, index),
                "entity_name": entity_name,
                "event_summary": first_nonempty(row, ("summary",), "legacy character event"),
                "event_kind": row.get("event_type"), "evidence_text": None,
                "metadata_jsonb": {"legacy_import": self._provenance("evidence", "character_events", source_key)},
            })

    def _relationships(self) -> None:
        rows = self.source.rows("relationships", self.source_project_id)
        family = self.families["relationships"]
        family.source_count = len(rows)
        if not rows:
            return
        run_id = self._workflow_run("relationships", "legacy-relationships")
        for index, row in enumerate(rows):
            source_id = str(row.get("source_id") or "")
            target_id = str(row.get("target_id") or "")
            source_name = self.entity_names.get(source_id)
            target_name = self.entity_names.get(target_id)
            if not source_name or not target_name:
                family.deferred_count += 1
                family.reason_codes.append("ENTITY_DEPENDENCY_MISSING")
                continue
            source_key = first_nonempty(row, ("relation_id",), f"{source_id}:{target_id}:{index}")
            relationship_id = self._id("relationships", source_key)
            metadata = {
                "legacy_import": self._provenance("relationships", "relationships", source_key),
                "trust_level": row.get("trust_level"),
                "power_dynamic": row.get("power_dynamic"),
            }
            self._record(
                "relationships",
                "relationships",
                "relationship_id",
                relationship_id,
                {
                    "tenant_id": self.tenant_id,
                    "relationship_id": relationship_id,
                    "project_id": self.project_id,
                    "source_entity_name": source_name,
                    "target_entity_name": target_name,
                    "relationship_type": first_nonempty(row, ("relation_type",), "related_to"),
                    "summary": row.get("description"),
                    "source_run_id": run_id,
                    "evidence_text": row.get("history"),
                    "metadata_jsonb": metadata,
                },
            )

    def _assets(self) -> None:
        rows = self.source.rows("assets", self.source_project_id)
        family = self.families["assets"]
        family.source_count = len(rows)
        for index, row in enumerate(rows):
            source_key = first_nonempty(row, ("asset_id", "source_ref"), str(index))
            asset_id = self._id("assets", source_key)
            payload = self.source.json_value(row.get("payload_json"), {})
            if not isinstance(payload, dict):
                payload = {}
            payload = {**payload, "legacy_import": self._provenance("assets", "assets", source_key)}
            tags = self.source.json_value(row.get("tags_json"), [])
            if not isinstance(tags, list):
                tags = []
            self._record(
                "assets",
                "assets",
                "asset_id",
                asset_id,
                {
                    "tenant_id": self.tenant_id,
                    "asset_id": asset_id,
                    "project_id": self.project_id,
                    "scope": "project",
                    "asset_type": first_nonempty(row, ("asset_type",), "legacy_material"),
                    "category": row.get("category"),
                    "lifecycle": self._lifecycle(row.get("scope"), row.get("asset_type")),
                    "title": first_nonempty(row, ("title",), f"Legacy asset {index + 1}"),
                    "summary": row.get("summary"),
                    "content_text": row.get("content"),
                    "payload_jsonb": payload,
                    "tags_jsonb": tags,
                    "source_kind": "legacy_import",
                    "source_ref": f"{self.import_id}:assets:{self._source_key_hash(source_key)}",
                    "enabled": bool(row.get("enabled", 1)),
                    "pinned": bool(row.get("pinned", 0)),
                    "created_by": self.actor_user_id,
                },
            )

    def _archive(self) -> None:
        rows = self.source.rows("archive_library", self.source_project_id)
        memories = self.source.rows("archive_agent_memory", self.source_project_id)
        events = self.source.rows("archive_agent_memory_events", self.source_project_id)
        family = self.families["archive"]
        family.source_count = len(rows) + len(memories) + len(events)
        for index, row in enumerate(rows):
            source_key = first_nonempty(row, ("archive_id", "entity_uuid", "entity_id"), str(index))
            asset_id = self._id("archive", source_key)
            self.archive_asset_ids[source_key] = asset_id
            payload = {
                "legacy_import": self._provenance("archive", "archive_library", source_key),
                "entity_type": row.get("entity_type"),
                "agent_kind": row.get("agent_kind"),
                "importance_tier": row.get("importance_tier"),
                "template_key": row.get("template_key"),
                "template_version": row.get("template_version"),
            }
            self._record(
                "archive",
                "assets",
                "asset_id",
                asset_id,
                {
                    "tenant_id": self.tenant_id,
                    "asset_id": asset_id,
                    "project_id": self.project_id,
                    "scope": "project",
                    "asset_type": "archive_profile",
                    "category": row.get("entity_type"),
                    "lifecycle": "canon",
                    "title": first_nonempty(row, ("entity_name",), f"Legacy archive {index + 1}"),
                    "summary": row.get("relationship_summary"),
                    "content_text": None,
                    "payload_jsonb": payload,
                    "tags_jsonb": [],
                    "source_kind": "legacy_import",
                    "source_ref": f"{self.import_id}:archive:{self._source_key_hash(source_key)}",
                    "enabled": True,
                    "pinned": False,
                    "created_by": self.actor_user_id,
                },
            )
        self._archive_memories(memories)
        self._archive_memory_events(events)

    def _archive_memories(self, rows: list[dict[str, Any]]) -> None:
        for index, row in enumerate(rows):
            source_key = first_nonempty(row, ("memory_id",), str(index))
            asset_id = self.archive_asset_ids.get(str(row.get("archive_id") or ""))
            if not asset_id:
                self._defer("archive", "ARCHIVE_ASSET_DEPENDENCY_MISSING")
                continue
            memory_id = self._id("archive-memory", source_key)
            self.archive_memory_ids[source_key] = memory_id
            payload = self.source.json_value(row.get("detail_json"), {})
            if not isinstance(payload, dict):
                payload = {}
            payload = {
                **payload,
                "legacy_import": self._provenance("archive", "archive_agent_memory", source_key),
                "normalized_subject": row.get("normalized_subject"),
                "salience": row.get("salience"),
                "version": row.get("version"),
                "evidence": self.source.json_value(row.get("evidence_json"), []),
            }
            self._record("archive", "archive_memories", "memory_id", memory_id, {
                "tenant_id": self.tenant_id,
                "memory_id": memory_id,
                "asset_id": asset_id,
                "project_id": self.project_id,
                "memory_type": first_nonempty(row, ("memory_type",), "legacy_memory"),
                "status": self._archive_memory_status(row.get("status"), row.get("memory_layer")),
                "summary": row.get("summary"),
                "body_text": None,
                "payload_jsonb": payload,
                "source_kind": "legacy_import",
                "source_ref": f"{self.import_id}:archive-memory:{self._source_key_hash(source_key)}",
                "enabled": str(row.get("status") or "active").lower() not in {"disabled", "deleted"},
                "created_by": self.actor_user_id,
            })

    def _archive_memory_events(self, rows: list[dict[str, Any]]) -> None:
        for index, row in enumerate(rows):
            source_key = first_nonempty(row, ("event_id",), str(index))
            memory_id = self.archive_memory_ids.get(str(row.get("memory_id") or ""))
            asset_id = self.archive_asset_ids.get(str(row.get("archive_id") or ""))
            if not memory_id or not asset_id:
                self._defer("archive", "ARCHIVE_MEMORY_DEPENDENCY_MISSING")
                continue
            event_id = self._id("archive-memory-event", source_key)
            payload = {
                "legacy_import": self._provenance(
                    "archive", "archive_agent_memory_events", source_key
                ),
                "summary": row.get("summary"),
                "normalized_subject": row.get("normalized_subject"),
                "memory_layer": row.get("memory_layer"),
                "version": row.get("version"),
                "evidence": self.source.json_value(row.get("evidence_json"), []),
            }
            self._record("archive", "archive_memory_events", "event_id", event_id, {
                "tenant_id": self.tenant_id,
                "event_id": event_id,
                "memory_id": memory_id,
                "asset_id": asset_id,
                "project_id": self.project_id,
                "event_type": first_nonempty(row, ("event_type",), "legacy_imported"),
                "status": self._archive_event_status(row.get("status")),
                "payload_jsonb": payload,
                "actor_user_id": self.actor_user_id,
            })

    def _graph(self) -> None:
        nodes = self.source.rows("graph_nodes", self.source_project_id)
        edges = self.source.rows("graph_edges", self.source_project_id)
        aliases = self.source.rows("graph_aliases", self.source_project_id)
        labels = self.source.rows("graph_node_labels", self.source_project_id)
        evidence = self.source.rows("graph_evidence", self.source_project_id)
        metadata = self.source.rows("graph_meta", self.source_project_id)
        family = self.families["graph"]
        family.source_count = len(nodes) + len(edges) + len(aliases) + len(labels) + len(evidence) + len(metadata)
        if not (nodes or edges or aliases or labels or evidence or metadata):
            return
        graph_id = self._graph_snapshots(metadata, len(nodes), len(edges))
        node_ids: dict[str, str] = {}
        for index, row in enumerate(nodes):
            source_key = first_nonempty(row, ("uuid", "name"), str(index))
            node_id = self._id("graph-node", source_key)
            node_ids[source_key] = node_id
            attributes = self.source.json_value(row.get("attributes_json"), {})
            if not isinstance(attributes, dict):
                attributes = {}
            node_type = str(attributes.get("node_type") or attributes.get("entity_type") or "concept")
            if node_type not in GRAPH_NODE_TYPES:
                node_type = "concept"
            attributes = {**attributes, "legacy_import": self._provenance("graph", "graph_nodes", source_key)}
            canonical_id = self.entity_ids.get(str(attributes.get("entity_id") or ""))
            self._record(
                "graph",
                "story_graph_nodes",
                "node_id",
                node_id,
                {
                    "tenant_id": self.tenant_id,
                    "node_id": node_id,
                    "project_id": self.project_id,
                    "graph_id": graph_id,
                    "canonical_entity_id": canonical_id,
                    "node_type": node_type,
                    "title": first_nonempty(row, ("name",), f"Legacy node {index + 1}"),
                    "summary": row.get("summary"),
                    "lifecycle": "canon",
                    "importance": 0,
                    "attributes_jsonb": attributes,
                    "evidence_count": 0,
                },
            )
        self._graph_aliases(graph_id, node_ids, aliases)
        self._graph_labels(graph_id, node_ids, labels)
        edge_ids = self._graph_edges(graph_id, node_ids, edges, family)
        self._graph_evidence(graph_id, node_ids, edge_ids, evidence, family)

    def _graph_aliases(self, graph_id: str, node_ids: dict[str, str], rows: list[dict[str, Any]]) -> None:
        for row in rows:
            source_node = str(row.get("node_uuid") or "")
            node_id = node_ids.get(source_node)
            if not node_id:
                self._defer("graph", "GRAPH_NODE_DEPENDENCY_MISSING")
                continue
            alias = str(row.get("alias") or "")
            alias_id = self._id("graph-alias", f"{source_node}:{alias}")
            self._record("graph", "story_graph_node_aliases", "alias_id", alias_id, {
                "tenant_id": self.tenant_id, "alias_id": alias_id, "project_id": self.project_id,
                "graph_id": graph_id, "node_id": node_id, "alias": alias,
                "source_type": "legacy_import", "confidence": None,
            })

    def _graph_snapshots(
        self, metadata: list[dict[str, Any]], node_count: int, edge_count: int
    ) -> str:
        if metadata and all("key" in row for row in metadata):
            values: dict[str, Any] = {}
            for row in metadata:
                key = str(row.get("key") or "").strip()
                if not key:
                    raise RuntimeError("LEGACY_GRAPH_METADATA_KEY_INVALID")
                value = row.get("value")
                if key in values and values[key] != value:
                    raise RuntimeError("LEGACY_GRAPH_METADATA_CONFLICT")
                values[key] = value
            version = self._positive_int(values.get("version", values.get("build_version")), 1)
            status = self._graph_status(values.get("status"), "ready")
            graph_id = self._id("graph", "snapshot")
            self._record_graph_snapshot(
                graph_id, version, status, stable_hash(values), node_count, edge_count
            )
            return graph_id

        snapshots = metadata or [{}]
        ordered = sorted(
            enumerate(snapshots),
            key=lambda item: (self._positive_int(item[1].get("version"), item[0] + 1), item[0]),
        )
        current_graph_id = ""
        for version, (source_index, row) in enumerate(ordered, start=1):
            source_key = first_nonempty(row, ("graph_id",), f"snapshot-{source_index}")
            graph_id = self._id("graph", source_key)
            is_current = version == len(ordered)
            status = self._graph_status(row.get("status"), "ready" if is_current else "archived")
            if not is_current and status == "ready":
                status = "archived"
            self._record_graph_snapshot(
                graph_id,
                version,
                status,
                stable_hash(row) if row else self.fingerprint,
                node_count if is_current else 0,
                edge_count if is_current else 0,
            )
            if is_current:
                current_graph_id = graph_id
        return current_graph_id

    def _record_graph_snapshot(
        self,
        graph_id: str,
        version: int,
        status: str,
        source_version_hash: str,
        node_count: int,
        edge_count: int,
    ) -> None:
        self._record(
            "graph",
            "story_graph_snapshots",
            "graph_id",
            graph_id,
            {
                "tenant_id": self.tenant_id,
                "graph_id": graph_id,
                "project_id": self.project_id,
                "version": version,
                "status": status,
                "build_run_id": None,
                "source_version_hash": source_version_hash,
                "node_count": node_count,
                "edge_count": edge_count,
            },
        )

    def _graph_labels(self, graph_id: str, node_ids: dict[str, str], rows: list[dict[str, Any]]) -> None:
        for row in rows:
            source_node = str(row.get("node_uuid") or "")
            node_id = node_ids.get(source_node)
            if not node_id:
                self._defer("graph", "GRAPH_NODE_DEPENDENCY_MISSING")
                continue
            label = str(row.get("label") or "")
            label_id = self._id("graph-label", f"{source_node}:{label}")
            self._record("graph", "story_graph_node_labels", "label_id", label_id, {
                "tenant_id": self.tenant_id, "label_id": label_id, "project_id": self.project_id,
                "graph_id": graph_id, "node_id": node_id, "label": label,
                "label_type": "tag", "confidence": None,
            })

    def _graph_edges(
        self, graph_id: str, node_ids: dict[str, str], rows: list[dict[str, Any]], family: FamilyPlan
    ) -> dict[str, str]:
        edge_ids: dict[str, str] = {}
        for index, row in enumerate(rows):
            source_key = first_nonempty(row, ("uuid",), str(index))
            source_node = node_ids.get(str(row.get("source_node_uuid") or ""))
            target_node = node_ids.get(str(row.get("target_node_uuid") or ""))
            if not source_node or not target_node:
                self._defer("graph", "GRAPH_NODE_DEPENDENCY_MISSING")
                continue
            edge_id = self._id("graph-edge", source_key)
            edge_ids[source_key] = edge_id
            attributes = self.source.json_value(row.get("attributes_json"), {})
            if not isinstance(attributes, dict):
                attributes = {}
            attributes = {**attributes, "legacy_import": self._provenance("graph", "graph_edges", source_key)}
            self._record("graph", "story_graph_edges", "edge_id", edge_id, {
                "tenant_id": self.tenant_id, "edge_id": edge_id, "project_id": self.project_id,
                "graph_id": graph_id, "source_node_id": source_node, "target_node_id": target_node,
                "edge_type": "relationship", "label": row.get("name"), "summary": row.get("fact"),
                "weight": row.get("weight") or 1, "lifecycle": "canon",
                "attributes_jsonb": attributes, "evidence_count": 0,
            })
        return edge_ids

    def _graph_evidence(
        self,
        graph_id: str,
        node_ids: dict[str, str],
        edge_ids: dict[str, str],
        rows: list[dict[str, Any]],
        family: FamilyPlan,
    ) -> None:
        for index, row in enumerate(rows):
            source_owner = str(row.get("owner_uuid") or "")
            owner_type = "edge" if str(row.get("owner_kind") or "") == "edge" else "node"
            owner_id = (edge_ids if owner_type == "edge" else node_ids).get(source_owner)
            if not owner_id:
                self._defer("graph", "GRAPH_OWNER_DEPENDENCY_MISSING")
                continue
            source_key = f"{owner_type}:{source_owner}:{index}"
            evidence_id = self._id("graph-evidence", source_key)
            self._record("graph", "story_graph_evidence", "evidence_id", evidence_id, {
                "tenant_id": self.tenant_id, "evidence_id": evidence_id, "project_id": self.project_id,
                "graph_id": graph_id, "owner_type": owner_type, "owner_id": owner_id,
                "source_type": "legacy_import", "source_id": f"{self.import_id}:{self._source_key_hash(source_key)}",
                "chapter_id": None, "segment_id": None, "snippet": row.get("snippet"), "confidence": None,
            })

    def _worldline(self) -> None:
        rows = self.source.rows("worldline_sessions", self.source_project_id)
        family = self.families["worldline"]
        branch_state_count = sum(
            len(self.source.rows(table, self.source_project_id))
            for table in (
                "worldline_branches", "agent_registry", "agent_state_snapshots", "agent_states",
                "agent_action_log", "agent_dialogue_log", "agent_episodic_memory", "agent_memory",
                "relation_state_log",
            )
        )
        family.source_count = len(rows) + branch_state_count
        family.unsupported_count += branch_state_count
        if branch_state_count:
            family.reason_codes.append("APPROVED_LEGACY_MULTI_BRANCH_UNSUPPORTED")
        for index, row in enumerate(rows):
            source_key = first_nonempty(row, ("session_id",), str(index))
            run_id = self._workflow_run("worldline", f"worldline:{source_key}")
            session_id = self._id("worldline-session", source_key)
            status = str(row.get("status") or "completed")
            if status not in {"queued", "running", "paused", "completed", "failed", "cancelled"}:
                status = "completed"
            self._record("worldline", "worldline_sessions", "session_id", session_id, {
                "tenant_id": self.tenant_id, "session_id": session_id, "project_id": self.project_id,
                "run_id": run_id, "status": status, "lifecycle": "archived",
                "goal_summary": first_nonempty(row, ("simulation_goal", "focus_question", "label")),
                "anchor_path_id": None, "created_by": self.actor_user_id,
            })
        self._worldline_preparations(family)

    def _worldline_preparations(self, family: FamilyPlan) -> None:
        prepare_rows = self.source.rows("prepare_runs", self.source_project_id)
        dossier_rows = self.source.rows("prepared_agent_dossiers", self.source_project_id)
        family.source_count += len(prepare_rows) + len(dossier_rows)
        prepare_ids: dict[str, str] = {}
        prepare_public = {
            "prepare_id", "project_id", "task_id", "graph_id", "session_scope", "status",
            "stage", "can_start", "goal_summary", "simulation_goal", "focus_question",
            "label", "branch_count", "source_archive_ids_json", "source_project_ids_json",
            "source_archive_count", "started_session_id", "created_at", "updated_at",
        }
        dossier_public = {
            "prepare_id", "project_id", "agent_id", "display_name", "name", "entity_name",
            "role", "agent_role", "agent_kind", "status", "summary", "profile_summary",
            "public_summary", "public_profile_json", "source_archive_id", "source_entity_uuid",
            "importance_tier", "template_key", "template_version", "template_sections_json",
            "created_at", "updated_at",
        }
        prepare_private = {
            "source_summary_json", "source_json", "world_variables_json", "input_payload_json",
            "error", "private_state_json", "prompt",
        }
        dossier_private = {
            "model_name", "validation_errors_json", "private_profile_json",
            "runtime_seed_state_json", "relationship_view_json", "memory_seed_summary_json",
            "source_evidence_summary_json", "private_memory_json",
        }
        private_fields = self._field_count(prepare_rows, prepare_private)
        private_fields += self._field_count(dossier_rows, dossier_private)
        family.unsupported_count += private_fields
        if private_fields:
            family.reason_codes.append("APPROVED_PRIVATE_PREPARATION_STATE_UNSUPPORTED")
        unknown_fields = self._unknown_field_count(prepare_rows, prepare_public | prepare_private)
        unknown_fields += self._unknown_field_count(dossier_rows, dossier_public | dossier_private)
        family.unsupported_count += unknown_fields
        if unknown_fields:
            family.reason_codes.append("UNKNOWN_PREPARATION_FIELD_UNSUPPORTED")
        for index, row in enumerate(prepare_rows):
            source_key = first_nonempty(row, ("prepare_id",), str(index))
            prepare_id = self._id("worldline-preparation", source_key)
            prepare_ids[source_key] = prepare_id
            run_id = self._workflow_run("worldline", f"worldline-prepare:{source_key}")
            source_status = str(row.get("status") or "completed").lower()
            status = source_status if source_status in {"completed", "failed", "cancelled"} else "completed"
            self._record("worldline", "worldline_preparations", "prepare_id", prepare_id, {
                "tenant_id": self.tenant_id, "prepare_id": prepare_id,
                "project_id": self.project_id, "run_id": run_id, "status": status,
                "lifecycle": "archived",
                "goal_summary": first_nonempty(
                    row, ("goal_summary", "simulation_goal", "focus_question", "label")
                ),
                "anchor_path_id": None, "created_by": self.actor_user_id,
            })
        for index, row in enumerate(dossier_rows):
            source_prepare = str(row.get("prepare_id") or "")
            prepare_id = prepare_ids.get(source_prepare)
            if not prepare_id:
                self._defer("worldline", "WORLDLINE_PREPARATION_DEPENDENCY_MISSING")
                continue
            source_key = first_nonempty(row, ("agent_id",), str(index))
            agent_id = self._id("worldline-prepared-agent", f"{source_prepare}:{source_key}")
            self._record("worldline", "worldline_prepared_agents", "agent_id", agent_id, {
                "tenant_id": self.tenant_id, "agent_id": agent_id,
                "prepare_id": prepare_id, "project_id": self.project_id,
                "display_name": first_nonempty(
                    row, ("display_name", "name", "entity_name"), f"Legacy agent {index + 1}"
                ),
                "role": first_nonempty(row, ("role", "agent_role", "agent_kind")),
                "status": "archived",
                "source_asset_id": self.archive_asset_ids.get(
                    str(row.get("source_archive_id") or "")
                ),
                "summary": self._prepared_agent_summary(row),
            })

    def _writer(self) -> None:
        runs = self.source.rows("writer_runs", self.source_project_id)
        drafts = self.source.rows("writer_drafts", self.source_project_id)
        family = self.families["writer"]
        run_events = self.source.rows("writer_run_events", self.source_project_id)
        draft_events = self.source.rows("writer_draft_events", self.source_project_id)
        structure_count = len(run_events) + len(draft_events)
        migrated_structure_count = sum(
            len(self.source.rows(table, self.source_project_id))
            for table in ("book_plans", "outline_versions", "scenes", "dedup_index")
        )
        chapter_count = len(self.source.rows("chapter_content", self.source_project_id)) + len(
            self.source.rows("chapter_meta", self.source_project_id)
        )
        family.source_count = (
            len(runs) + len(drafts) + structure_count + migrated_structure_count + chapter_count
        )
        family.unsupported_count += len(draft_events)
        if draft_events:
            family.reason_codes.append("APPROVED_TRANSIENT_WRITER_EVENT_HISTORY_UNSUPPORTED")
        self._writer_chapters()
        self._writer_structures()
        run_ids: dict[str, str] = {}
        for index, row in enumerate(runs):
            source_key = first_nonempty(row, ("run_id",), str(index))
            run_id = self._id("writer-run", source_key)
            run_ids[source_key] = run_id
            workflow_run_id = self._writer_workflow_run(source_key, row)
            mode = str(row.get("mode") or "draft")
            if mode not in {"draft", "continue", "outline", "review"}:
                mode = "draft"
            options = self.source.json_value(row.get("options_json"), {})
            if not isinstance(options, dict):
                options = {}
            options = {**options, "legacy_import": self._provenance("writer", "writer_runs", source_key)}
            self._record("writer", "writer_runs", "run_id", run_id, {
                "tenant_id": self.tenant_id, "run_id": run_id, "workflow_run_id": workflow_run_id,
                "project_id": self.project_id, "chapter_id": None, "scene_id": None,
                "mode": mode, "status": str(row.get("status") or "completed"),
                "module_key": first_nonempty(row, ("module_key",), "writer_composer"),
                "instruction": str(row.get("instruction") or ""), "options_jsonb": options,
                "error_code": row.get("error_code"), "error_message": None, "created_by": self.actor_user_id,
            })
        self._writer_run_events(run_events, run_ids)
        for index, row in enumerate(drafts):
            source_run = str(row.get("run_id") or "")
            run_id = run_ids.get(source_run)
            if not run_id:
                self._defer("writer", "WRITER_RUN_DEPENDENCY_MISSING")
                continue
            source_key = first_nonempty(row, ("draft_id",), str(index))
            draft_id = self._id("writer-draft", source_key)
            content = str(row.get("content") or "")
            status = str(row.get("status") or "candidate")
            if status not in {"candidate", "adopted", "rejected"}:
                status = "candidate"
            self._record("writer", "writer_drafts", "draft_id", draft_id, {
                "tenant_id": self.tenant_id, "draft_id": draft_id, "run_id": run_id,
                "project_id": self.project_id, "chapter_id": None, "scene_id": None,
                "content_text": content, "word_count": len(content), "status": status,
                "adopted_block_id": None,
            })

    def _writer_workflow_run(self, source_key: str, row: dict[str, Any]) -> str:
        run_id = self._id("workflow-run", f"writer:{source_key}")
        status = str(row.get("status") or "completed").lower()
        if status not in {"queued", "running", "paused", "completed", "failed", "cancelled"}:
            status = "completed"
        progress = 100 if status == "completed" else 0
        self._record("writer", "workflow_runs", "run_id", run_id, {
            "tenant_id": self.tenant_id, "run_id": run_id, "workflow_type": "writer_run",
            "project_id": self.project_id, "status": status, "progress": progress,
            "message": "legacy writer run", "started_by": self.actor_user_id,
            "result_jsonb": {
                "import_id": self.import_id,
                "source_fingerprint": self.fingerprint,
                "family": "writer",
            },
            "error_code": row.get("error_code"), "error_message": None,
        })
        return run_id

    def _writer_run_events(
        self, rows: list[dict[str, Any]], writer_run_ids: dict[str, str]
    ) -> None:
        sequences: dict[str, int] = {}
        workflow_ids = {
            source_key: self._id("workflow-run", f"writer:{source_key}")
            for source_key in writer_run_ids
        }
        for index, row in enumerate(rows):
            source_run = str(row.get("run_id") or "")
            workflow_run_id = workflow_ids.get(source_run)
            if not workflow_run_id:
                self._defer("writer", "WRITER_RUN_DEPENDENCY_MISSING")
                continue
            sequences[source_run] = sequences.get(source_run, 0) + 1
            source_key = first_nonempty(row, ("event_id",), str(index))
            event_id = self._id("writer-run-event", f"{source_run}:{source_key}:{index}")
            payload = self._writer_event_payload(row)
            self._record("writer", "workflow_events", "event_id", event_id, {
                "tenant_id": self.tenant_id, "event_id": event_id,
                "run_id": workflow_run_id, "workflow_type": "writer_run",
                "project_id": self.project_id, "event_type": "writer.legacy.event",
                "sequence": sequences[source_run], "payload_jsonb": payload,
            })

    @staticmethod
    def _writer_event_payload(row: dict[str, Any]) -> dict[str, Any]:
        payload: dict[str, Any] = {}
        aliases = {
            "lifecycle": ("lifecycle",),
            "status": ("status",),
            "tool": ("tool", "tool_name"),
            "count": ("count", "item_count", "word_count", "token_count"),
            "error_code": ("error_code", "code"),
        }
        for target, candidates in aliases.items():
            value = next((row.get(name) for name in candidates if row.get(name) not in (None, "")), None)
            if value is None or isinstance(value, (dict, list, tuple, set)):
                continue
            if target == "count":
                try:
                    value = int(value)
                except (TypeError, ValueError):
                    continue
            elif not isinstance(value, (str, int, float, bool)):
                continue
            payload[target] = value
        return payload

    @staticmethod
    def _field_count(rows: list[dict[str, Any]], fields: set[str]) -> int:
        return sum(
            1
            for row in rows
            for key, value in row.items()
            if key in fields and value not in (None, "", [], {})
        )

    @staticmethod
    def _unknown_field_count(rows: list[dict[str, Any]], known_fields: set[str]) -> int:
        return sum(
            1
            for row in rows
            for key, value in row.items()
            if key not in known_fields and value not in (None, "", [], {})
        )

    def _prepared_agent_summary(self, row: dict[str, Any]) -> str:
        summary = first_nonempty(row, ("summary", "profile_summary", "public_summary"))
        if summary:
            return summary
        profile = self.source.json_value(row.get("public_profile_json"), {})
        if not isinstance(profile, dict):
            return ""
        return first_nonempty(
            profile, ("summary", "public_summary", "description", "bio")
        )

    def _writer_chapters(self) -> None:
        metadata_rows = self.source.rows("chapter_meta", self.source_project_id)
        metadata = {str(row.get("chapter_id") or ""): row for row in metadata_rows}
        content_rows = self.source.rows("chapter_content", self.source_project_id)
        content_keys = [first_nonempty(row, ("chapter_id",), str(index)) for index, row in enumerate(content_rows)]
        metadata_only = [
            str(row.get("chapter_id") or "")
            for row in metadata_rows
            if str(row.get("chapter_id") or "") not in set(content_keys)
        ]
        ordered_keys = content_keys + metadata_only
        content = {key: row for key, row in zip(content_keys, content_rows)}
        used_orders = {
            self._nonnegative_int(row.get("chapter_order"), index)
            for index, row in enumerate(content_rows)
        }
        next_order = max(used_orders, default=-1) + 1
        for index, source_key in enumerate(ordered_keys):
            row = content.get(source_key, {})
            chapter_id = self._id("chapter", source_key)
            self.chapter_ids[source_key] = chapter_id
            meta = metadata.get(source_key, {})
            outline = self.source.json_value(meta.get("outline_json"), [])
            status = str(row.get("status") or ("planned" if not row else "drafting")).lower()
            status = {
                "draft": "drafting", "candidate": "drafting", "final": "completed",
                "published": "completed",
            }.get(status, status)
            if status not in {"planned", "drafting", "review", "completed", "archived"}:
                status = "drafting"
            chapter_order = self._nonnegative_int(row.get("chapter_order"), next_order)
            if not row:
                next_order += 1
            self._record("writer", "chapters", "chapter_id", chapter_id, {
                "tenant_id": self.tenant_id, "project_id": self.project_id,
                "chapter_id": chapter_id, "chapter_order": chapter_order,
                "title": first_nonempty(row, ("title",), f"Chapter {index + 1}"),
                "status": status, "brief": meta.get("summary"),
                "outline": json.dumps(outline, ensure_ascii=False, sort_keys=True),
                "content_text": str(row.get("content") or "") if row else None,
                "created_by": self.actor_user_id, "updated_by": self.actor_user_id,
            })

    def _writer_structures(self) -> None:
        for index, row in enumerate(self.source.rows("book_plans", self.source_project_id)):
            source_key = first_nonempty(row, ("plan_id",), str(index))
            plan_id = self._id("book-plan", source_key)
            status = str(row.get("status") or "draft")
            if status not in {"draft", "active", "completed", "archived"}:
                status = "draft"
            planning = {
                "legacy_import": self._provenance("writer", "book_plans", source_key),
                "per_chapter_word_target": row.get("per_chapter_word_target"),
                "word_tolerance_pct": row.get("word_tolerance_pct"),
                "global_brief": row.get("global_brief"),
                "start_chapter_order": row.get("start_chapter_order"),
            }
            self._record("writer", "book_plans", "book_plan_id", plan_id, {
                "tenant_id": self.tenant_id, "project_id": self.project_id,
                "book_plan_id": plan_id,
                "title": first_nonempty(row, ("title",), f"Legacy book plan {index + 1}"),
                "status": status, "premise": row.get("overall_direction"),
                "target_chapter_count": row.get("chapter_count"), "planning_jsonb": planning,
                "created_by": self.actor_user_id, "updated_by": self.actor_user_id,
            })
        versions: dict[str, int] = {}
        for index, row in enumerate(self.source.rows("outline_versions", self.source_project_id)):
            source_key = first_nonempty(row, ("version_id",), str(index))
            source_chapter = str(row.get("chapter_id") or "")
            chapter_id = self.chapter_ids.get(source_chapter)
            if not chapter_id:
                self._defer("writer", "CHAPTER_DEPENDENCY_MISSING")
                continue
            versions[source_chapter] = versions.get(source_chapter, 0) + 1
            outline = self.source.json_value(row.get("outline_json"), {})
            outline_id = self._id("outline-version", source_key)
            self._record("writer", "outline_versions", "outline_version_id", outline_id, {
                "tenant_id": self.tenant_id, "project_id": self.project_id,
                "outline_version_id": outline_id, "scope_type": "chapter", "scope_id": chapter_id,
                "version_number": versions[source_chapter], "lifecycle": "candidate",
                "title": first_nonempty(row, ("label",), f"Legacy outline {versions[source_chapter]}"),
                "outline_text": json.dumps(outline, ensure_ascii=False, sort_keys=True),
                "restored_from_version_id": None, "created_by": self.actor_user_id,
            })
        for index, row in enumerate(self.source.rows("scenes", self.source_project_id)):
            source_key = first_nonempty(row, ("scene_id",), str(index))
            chapter_id = self.chapter_ids.get(str(row.get("chapter_id") or ""))
            if not chapter_id:
                self._defer("writer", "CHAPTER_DEPENDENCY_MISSING")
                continue
            scene_id = self._id("scene", source_key)
            status = str(row.get("status") or "drafting")
            status = {"draft": "drafting", "final": "completed"}.get(status, status)
            if status not in {"planned", "drafting", "review", "completed", "archived"}:
                status = "drafting"
            self._record("writer", "scenes", "scene_id", scene_id, {
                "tenant_id": self.tenant_id, "project_id": self.project_id, "scene_id": scene_id,
                "chapter_id": chapter_id, "scene_order": int(row.get("scene_order") or index),
                "title": first_nonempty(row, ("title",), f"Scene {index + 1}"),
                "status": status, "brief": row.get("location"),
                "outline": row.get("writing_brief_json"), "content_text": row.get("content"),
                "created_by": self.actor_user_id, "updated_by": self.actor_user_id,
            })
        for index, row in enumerate(self.source.rows("dedup_index", self.source_project_id)):
            source_key = first_nonempty(row, ("id",), str(index))
            pattern = first_nonempty(row, ("pattern_text",), f"legacy-pattern-{index}")
            pattern_id = self._id("dedup-pattern", source_key)
            kind = str(row.get("pattern_type") or "phrase")
            if kind not in {"phrase", "sentence_shape", "transition", "description"}:
                kind = "phrase"
            self._record("writer", "writer_dedup_patterns", "pattern_id", pattern_id, {
                "tenant_id": self.tenant_id, "pattern_id": pattern_id, "project_id": self.project_id,
                "pattern_text": pattern, "normalized_pattern": " ".join(pattern.lower().split()),
                "pattern_kind": kind, "lifecycle": "candidate", "enabled": False,
                "occurrence_count": int(row.get("count") or 1),
            })

    def _manuscript(self) -> None:
        rows = self.source.rows("chapter_content", self.source_project_id)
        family = self.families["manuscript"]
        family.source_count = len(rows)
        for index, row in enumerate(rows):
            source_key = first_nonempty(row, ("chapter_id",), str(index))
            block_id = self._id("manuscript", source_key)
            chapter_id = self.chapter_ids.get(source_key)
            content = str(row.get("content") or "")
            self._record("manuscript", "manuscript_blocks", "block_id", block_id, {
                "tenant_id": self.tenant_id, "block_id": block_id, "project_id": self.project_id,
                "chapter_id": chapter_id, "source_draft_id": None,
                "block_order": int(row.get("chapter_order") or index + 1),
                "content_text": content, "word_count": int(row.get("word_count") or len(content)),
                "pov_entity_id": None, "created_by": self.actor_user_id,
            })

    def _workflow_run(self, family: str, source_key: str) -> str:
        run_id = self._id("workflow-run", source_key)
        values = {
            "tenant_id": self.tenant_id,
            "run_id": run_id,
            "workflow_type": "legacy_import",
            "project_id": self.project_id,
            "status": "completed",
            "progress": 100,
            "message": "legacy import",
            "started_by": self.actor_user_id,
            "result_jsonb": {
                "import_id": self.import_id,
                "source_fingerprint": self.fingerprint,
                "family": family,
            },
        }
        existing = {record.key for record in self.families[family].records if record.table == "workflow_runs"}
        if run_id not in existing:
            self._record(family, "workflow_runs", "run_id", run_id, values)
        return run_id

    def _defer(self, family: str, reason: str) -> None:
        self.families[family].deferred_count += 1
        self.families[family].reason_codes.append(reason)

    @staticmethod
    def _source_key_hash(source_key: str) -> str:
        import hashlib

        return hashlib.sha256(source_key.encode()).hexdigest()

    @staticmethod
    def _positive_int(value: Any, default: int) -> int:
        try:
            parsed = int(value)
        except (TypeError, ValueError):
            return default
        return parsed if parsed > 0 else default

    @staticmethod
    def _nonnegative_int(value: Any, default: int) -> int:
        try:
            parsed = int(value)
        except (TypeError, ValueError):
            return default
        return parsed if parsed >= 0 else default

    @staticmethod
    def _graph_status(value: Any, default: str) -> str:
        status = str(value or default).lower()
        return status if status in {"building", "ready", "failed", "archived"} else default

    @staticmethod
    def _lifecycle(scope: Any, asset_type: Any) -> str:
        value = str(scope or "").lower()
        if value in {"seed", "candidate", "canon", "material", "simulation", "draft", "manuscript", "archived"}:
            return value
        if str(asset_type or "").lower() in {"chapter", "manuscript"}:
            return "manuscript"
        return "material"

    @staticmethod
    def _archive_memory_status(status: Any, memory_layer: Any) -> str:
        value = str(status or "active").lower()
        if value in {"rejected", "archived"}:
            return value
        if str(memory_layer or "").lower() == "canon" and value == "active":
            return "canon"
        return "candidate"

    @staticmethod
    def _archive_event_status(status: Any) -> str:
        value = str(status or "recorded").lower()
        mapping = {"active": "recorded", "canon": "accepted", "archived": "recorded"}
        value = mapping.get(value, value)
        return value if value in {"recorded", "candidate", "accepted", "rejected", "failed"} else "recorded"
