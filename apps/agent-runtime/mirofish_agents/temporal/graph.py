from __future__ import annotations

import hashlib
import json
import math
import os
import re
import unicodedata
import uuid
from datetime import timedelta
from typing import Any, Callable, Protocol

from temporalio import activity, workflow

from mirofish_agents.common.context import AgentContext
from mirofish_agents.llm_quota import PostgresQuotaStore, ProviderQuotaGate, QuotaAwareJSONChatClient
from mirofish_agents.seed.sequential_reader import (
    CredentialProvider,
    JSONChatClient,
    LLMFacilityError,
    ModuleBindingResolution,
    ModuleBindingResolver,
    PostgresCredentialProvider,
    PostgresModuleBindingResolver,
    set_postgres_tenant_context,
)


GRAPH_TASK_QUEUE = "graph-heavy"
STORY_GRAPH_BUILD_MODULE_KEY = "story_graph_build"
GRAPH_BOND_GENERATION_MODULE_KEY = "graph_bond_generator"
STORY_GRAPH_BUILD_WORKFLOW_TYPE = "story_graph_build"
STORY_GRAPH_BOND_GENERATION_WORKFLOW_TYPE = "story_graph_bond_generation"
GRAPH_LAYOUT_SCHEMA_VERSION = 2
GRAPH_LAYOUT_DEFAULT_VIEWPORT_NODE_BUDGET = 300
GRAPH_LAYOUT_NODE_WIDTH = 180
GRAPH_LAYOUT_NODE_HEIGHT = 112
GRAPH_LAYOUT_CLUSTER_GAP = 160
SENSITIVE_GRAPH_KEYS = {
    "api_key",
    "body",
    "content",
    "content_text",
    "credential_ref",
    "draft",
    "encrypted_api_key",
    "evidence_text",
    "manuscript",
    "involvednodeids",
    "involved_node_ids",
    "node_ids",
    "nodeids",
    "prompt",
    "raw_content",
    "rawcontent",
    "raw_text",
    "rawtext",
    "response",
    "seed_analysis_body",
    "seedanalysisbody",
    "selectednodeids",
    "selected_node_ids",
    "snippet",
    "source_text",
    "sourcetext",
    "text",
}
SENSITIVE_GRAPH_VALUE_MARKERS = (
    "api key",
    "api_key",
    "bearer ",
    "credential",
    "prompt:",
    "raw text",
    "raw_text",
    "snippet",
    "sk-",
)
_SCRUBBED_GRAPH_VALUE = object()


class WorkflowEventWriter(Protocol):
    def write_event(
        self,
        *,
        tenant_id: str,
        project_id: str | None,
        run_id: str,
        event_type: str,
        payload: dict[str, Any],
    ) -> None:
        ...


class WorkflowRunStatusWriter(Protocol):
    def mark_completed(
        self,
        *,
        context: AgentContext,
        result: dict[str, Any],
    ) -> None:
        ...

    def mark_failed(
        self,
        *,
        context: AgentContext,
        code: str,
        message: str,
    ) -> None:
        ...


class StoryGraphBuilder(Protocol):
    def build(
        self,
        *,
        context: AgentContext,
        mode: str,
        options: dict[str, Any],
    ) -> dict[str, Any]:
        ...


class GraphBondGenerationRunner(Protocol):
    def generate(
        self,
        *,
        context: AgentContext,
        graph_id: str | None,
        node_ids: list[str],
        focus: str | None,
        options: dict[str, Any],
    ) -> dict[str, Any]:
        ...


class GraphBondCandidateWriter(Protocol):
    def write_candidates(
        self,
        *,
        context: AgentContext,
        candidate_batch_id: str,
        model_id: str | None,
        candidates: list[dict[str, Any]],
    ) -> dict[str, Any]:
        ...


class LLMFacilityGraphBondGenerationRunner:
    def __init__(
        self,
        *,
        binding_resolver: ModuleBindingResolver,
        credential_provider: CredentialProvider,
        chat_client: JSONChatClient,
        candidate_writer: GraphBondCandidateWriter,
        quota_gate: ProviderQuotaGate | None = None,
    ) -> None:
        self._binding_resolver = binding_resolver
        self._credential_provider = credential_provider
        self._chat_client = chat_client
        self._candidate_writer = candidate_writer
        self._quota_gate = quota_gate

    def generate(
        self,
        *,
        context: AgentContext,
        graph_id: str | None,
        node_ids: list[str],
        focus: str | None,
        options: dict[str, Any],
    ) -> dict[str, Any]:
        try:
            resolution = self._binding_resolver.resolve_module_binding(
                context=context,
                module_key=GRAPH_BOND_GENERATION_MODULE_KEY,
            )
            _validate_graph_bond_resolution(resolution)
            api_key = self._credential_provider.resolve_api_key(
                context=context,
                credential_ref=resolution.credential_ref,
            )
            if not isinstance(api_key, str) or not api_key.strip():
                raise LLMFacilityError("LLM_CREDENTIAL_UNAVAILABLE", "resolved credential was empty")
            messages = _graph_bond_messages(
                context=context,
                graph_id=graph_id,
                node_ids=node_ids,
                focus=focus,
                options=options,
            )
            if self._quota_gate is None:
                response_json = self._chat_client.complete_json(
                    context=context,
                    resolution=resolution,
                    api_key=api_key.strip(),
                    messages=messages,
                )
                candidates = _graph_bond_candidate_assets(
                    response_json,
                    forbidden_values=[*node_ids, focus],
                )
            else:
                candidates = self._quota_gate.execute_json(
                    context=context,
                    resolution=resolution,
                    stage="bond_generation",
                    call_index=0,
                    input_texts=[message["content"] for message in messages],
                    provider=lambda provider_call_id: self._chat_client.complete_json(
                        context=context,
                        resolution=resolution,
                        api_key=api_key.strip(),
                        messages=messages,
                        provider_call_id=provider_call_id,
                    ),
                    validate=lambda response: _graph_bond_candidate_assets(
                        response,
                        forbidden_values=[*node_ids, focus],
                    ),
                )
            candidate_batch_id = f"graph-bond:{context.run_id}"
            persisted = self._candidate_writer.write_candidates(
                context=context,
                candidate_batch_id=candidate_batch_id,
                model_id=resolution.model_id,
                candidates=candidates,
            )
        except LLMFacilityError as exc:
            return _bond_runner_failed(exc.code, exc.message)
        except Exception:
            return _bond_runner_failed("LLM_PROVIDER_ERROR", "graph bond provider call failed")

        return {
            "status": "completed",
            "module_key": GRAPH_BOND_GENERATION_MODULE_KEY,
            "model_id": resolution.model_id,
            "candidate_batch_id": candidate_batch_id,
            "candidate_count": persisted.get("candidate_count", len(candidates)),
            "bond_candidate_count": persisted.get("bond_candidate_count", _count_candidates(candidates, "graph_bond")),
            "plot_thread_candidate_count": persisted.get(
                "plot_thread_candidate_count",
                _count_candidates(candidates, "plot_thread"),
            ),
            "conflict_trigger_count": persisted.get(
                "conflict_trigger_count",
                _count_candidates(candidates, "conflict_trigger"),
            ),
        }


class PostgresGraphBondCandidateWriter:
    def __init__(self, *, connect: Callable[[], Any], source_kind: str = "graph_bond_generation") -> None:
        self._connect = connect
        self._source_kind = _required_text(source_kind, "source_kind")

    @classmethod
    def from_database_url(
        cls,
        database_url: str,
        *,
        source_kind: str = "graph_bond_generation",
    ) -> "PostgresGraphBondCandidateWriter":
        try:
            import psycopg
        except ImportError as exc:  # pragma: no cover - depends on optional runtime packaging
            raise RuntimeError("psycopg is required for DATABASE_URL graph bond candidate writes") from exc

        return cls(connect=lambda: psycopg.connect(database_url), source_kind=source_kind)

    def write_candidates(
        self,
        *,
        context: AgentContext,
        candidate_batch_id: str,
        model_id: str | None,
        candidates: list[dict[str, Any]],
    ) -> dict[str, Any]:
        if context.project_id is None:
            raise LLMFacilityError("VALIDATION_FAILED", "project_id is required to write graph bond candidates")
        normalized_batch_id = _required_text(candidate_batch_id, "candidate_batch_id")
        normalized_candidates = _graph_bond_candidate_list(candidates)
        connection = self._connect()
        try:
            set_postgres_tenant_context(connection, context=context)
            with connection.cursor() as cursor:
                for index, candidate in enumerate(normalized_candidates):
                    payload = _sanitize_graph_value(
                        candidate.get("payload") if isinstance(candidate.get("payload"), dict) else {}
                    )
                    if model_id:
                        payload["model_id"] = model_id
                    payload["source_run_id"] = context.run_id
                    source_ref = f"{normalized_batch_id}:{index + 1}"
                    cursor.execute(
                        """INSERT INTO assets (
                             tenant_id, project_id, scope, asset_type, category, lifecycle,
                             title, summary, content_text, payload_jsonb, tags_jsonb,
                             source_kind, source_ref, enabled, pinned, created_by
                           )
                           VALUES (
                             %s, %s, 'project', %s, %s, 'candidate',
                             %s, %s, %s, %s::jsonb, %s::jsonb,
                             %s, %s, true, false, %s
                           )
                           ON CONFLICT (tenant_id, project_id, source_kind, source_ref, asset_type, title)
                           DO UPDATE SET
                             category = EXCLUDED.category,
                             lifecycle = 'candidate',
                             summary = EXCLUDED.summary,
                             content_text = EXCLUDED.content_text,
                             payload_jsonb = EXCLUDED.payload_jsonb,
                             tags_jsonb = EXCLUDED.tags_jsonb,
                             enabled = true,
                             updated_at = now()
                           RETURNING asset_id""",
                        (
                            context.tenant_id,
                            context.project_id,
                            candidate["asset_type"],
                            candidate.get("category"),
                            candidate["title"],
                            candidate.get("summary"),
                            candidate.get("summary"),
                            json.dumps(payload, ensure_ascii=False, separators=(",", ":")),
                            json.dumps(candidate.get("tags", []), ensure_ascii=False, separators=(",", ":")),
                            self._source_kind,
                            source_ref,
                            _uuid_or_none(context.actor_user_id),
                        ),
                    )
                    cursor.fetchone()
            connection.commit()
        except LLMFacilityError:
            _rollback_connection(connection)
            raise
        except Exception as exc:
            _rollback_connection(connection)
            raise LLMFacilityError("GRAPH_BOND_CANDIDATE_WRITE_FAILED", "graph bond candidate write failed") from exc
        finally:
            connection.close()
        return {
            "status": "completed",
            "candidate_batch_id": normalized_batch_id,
            "candidate_count": len(normalized_candidates),
            "bond_candidate_count": _count_candidates(normalized_candidates, "graph_bond"),
            "plot_thread_candidate_count": _count_candidates(normalized_candidates, "plot_thread"),
            "conflict_trigger_count": _count_candidates(normalized_candidates, "conflict_trigger"),
        }


class PostgresWorkflowRunStatusWriter:
    def __init__(self, *, connect: Callable[[], Any]) -> None:
        self._connect = connect

    @classmethod
    def from_database_url(cls, database_url: str) -> "PostgresWorkflowRunStatusWriter":
        try:
            import psycopg
            from psycopg.rows import dict_row
        except ImportError as exc:  # pragma: no cover - depends on optional runtime packaging
            raise RuntimeError("psycopg is required for DATABASE_URL workflow status writes") from exc

        return cls(connect=lambda: psycopg.connect(database_url, row_factory=dict_row))

    def mark_completed(
        self,
        *,
        context: AgentContext,
        result: dict[str, Any],
    ) -> None:
        public_result = (
            _public_bond_generation_result(result)
            if context.workflow_type == STORY_GRAPH_BOND_GENERATION_WORKFLOW_TYPE
            else _public_workflow_status_result(result)
        )
        self._update_status(
            context=context,
            status="completed",
            result=public_result,
            code=None,
            message=None,
        )

    def mark_failed(
        self,
        *,
        context: AgentContext,
        code: str,
        message: str,
    ) -> None:
        self._update_status(
            context=context,
            status="failed",
            result=None,
            code=code,
            message=message,
        )

    def _update_status(
        self,
        *,
        context: AgentContext,
        status: str,
        result: dict[str, Any] | None,
        code: str | None,
        message: str | None,
    ) -> None:
        if not context.project_id:
            raise RuntimeError("WORKFLOW_RUN_NOT_FOUND: project_id is required to update workflow status")
        connection = self._connect()
        try:
            set_postgres_tenant_context(connection, context=context)
            with connection.cursor() as cursor:
                cursor.execute(
                    """WITH workflow_update AS (
                         UPDATE workflow_runs
                            SET status = %s,
                                progress = CASE WHEN %s IN ('completed', 'failed') THEN 100 ELSE progress END,
                                message = %s,
                                result_jsonb = CASE
                                  WHEN %s::jsonb IS NULL THEN result_jsonb
                                  ELSE %s::jsonb
                                END,
                                error_code = %s,
                                error_message = %s,
                                updated_at = now()
                          WHERE tenant_id = %s
                            AND project_id = %s
                            AND run_id = %s
                            AND workflow_type = %s
                         RETURNING 1
                       )
                       SELECT COUNT(*)::int AS workflow_updated FROM workflow_update""",
                    (
                        status,
                        status,
                        _workflow_status_message(status, result, message),
                        json.dumps(result, ensure_ascii=False, separators=(",", ":")) if result is not None else None,
                        json.dumps(result, ensure_ascii=False, separators=(",", ":")) if result is not None else None,
                        code,
                        message,
                        context.tenant_id,
                        context.project_id,
                        context.run_id,
                        context.workflow_type,
                    ),
                )
                row = cursor.fetchone()
            connection.commit()
        except Exception:
            _rollback_connection(connection)
            raise
        finally:
            connection.close()
        if _count_value(_row_value(row, "workflow_updated", 0)) < 1:
            raise RuntimeError("WORKFLOW_RUN_NOT_FOUND: story graph workflow admission parent row is missing")


class PostgresStoryGraphBuilder:
    def __init__(self, *, connect: Callable[[], Any]) -> None:
        self._connect = connect

    @classmethod
    def from_database_url(cls, database_url: str) -> "PostgresStoryGraphBuilder":
        try:
            import psycopg
            from psycopg.rows import dict_row
        except ImportError as exc:  # pragma: no cover - depends on optional runtime packaging
            raise RuntimeError("psycopg is required for DATABASE_URL story graph builds") from exc

        return cls(connect=lambda: psycopg.connect(database_url, row_factory=dict_row))

    def build(
        self,
        *,
        context: AgentContext,
        mode: str,
        options: dict[str, Any],
    ) -> dict[str, Any]:
        if not context.project_id:
            raise ValueError("project_id is required to build a story graph")
        graph_id = str(uuid.uuid4())
        safe_options = _sanitize_graph_value(options)
        connection = self._connect()
        try:
            set_postgres_tenant_context(connection, context=context)
            with connection.cursor() as cursor:
                entities = self._fetch_entities(cursor, context)
                aliases = self._fetch_entity_aliases(cursor, context)
                labels = self._fetch_entity_labels(cursor, context)
                relationships = self._fetch_relationships(cursor, context)
                plot_threads = self._fetch_plot_threads(cursor, context)
                world_rules = self._fetch_world_rules(cursor, context)
                assets = self._fetch_assets(cursor, context)
                version = self._next_snapshot_version(cursor, context)

                nodes = self._build_nodes(
                    graph_id=graph_id,
                    entities=entities,
                    aliases=aliases,
                    plot_threads=plot_threads,
                    world_rules=world_rules,
                    assets=assets,
                )
                edges = self._build_edges(
                    graph_id=graph_id,
                    relationships=relationships,
                    node_by_entity_name=_entity_name_index(nodes),
                )
                clusters = _assign_graph_clusters(graph_id=graph_id, nodes=nodes, edges=edges)
                source_hash = _source_version_hash(
                    {
                        "nodes": [_graph_node_hash_record(node) for node in nodes],
                        "edges": [_graph_edge_hash_record(edge) for edge in edges],
                        "mode": mode,
                        "options": safe_options,
                    }
                )
                self._insert_snapshot(
                    cursor,
                    context=context,
                    graph_id=graph_id,
                    version=version,
                    source_hash=source_hash,
                    node_count=len(nodes),
                    edge_count=len(edges),
                )
                self._insert_clusters(cursor, context=context, graph_id=graph_id, clusters=clusters)
                self._insert_nodes(cursor, context=context, nodes=nodes)
                self._insert_aliases(cursor, context=context, graph_id=graph_id, nodes=nodes, aliases=aliases)
                self._insert_labels(cursor, context=context, graph_id=graph_id, nodes=nodes, labels=labels)
                self._insert_edges(cursor, context=context, edges=edges)
                evidence_count = self._insert_evidence(
                    cursor,
                    context=context,
                    graph_id=graph_id,
                    nodes=nodes,
                    edges=edges,
                )
                layout_count = self._insert_layout(
                    cursor,
                    context=context,
                    graph_id=graph_id,
                    nodes=nodes,
                    edges=edges,
                    clusters=clusters,
                    options=safe_options if isinstance(safe_options, dict) else {},
                )
                self._mark_snapshot_ready(cursor, context=context, graph_id=graph_id, node_count=len(nodes), edge_count=len(edges))
            connection.commit()
        except Exception:
            _rollback_connection(connection)
            raise
        finally:
            connection.close()
        return {
            "status": "completed",
            "module_key": STORY_GRAPH_BUILD_MODULE_KEY,
            "graph_id": graph_id,
            "node_count": len(nodes),
            "edge_count": len(edges),
            "evidence_count": evidence_count,
            "layout_count": layout_count,
            "cluster_count": len(clusters),
        }

    def _fetch_entities(self, cursor: Any, context: AgentContext) -> list[dict[str, Any]]:
        cursor.execute(
            """SELECT entity_id, canonical_name, entity_type, importance, state_summary,
                      first_seen_segment_id, metadata_jsonb
               FROM entities
               WHERE tenant_id = %s AND project_id = %s
               ORDER BY canonical_name""",
            (context.tenant_id, context.project_id),
        )
        return _rows(cursor.fetchall())

    def _fetch_entity_aliases(self, cursor: Any, context: AgentContext) -> list[dict[str, Any]]:
        cursor.execute(
            """SELECT entity_id, alias
               FROM entity_aliases
               WHERE tenant_id = %s AND project_id = %s
               ORDER BY alias""",
            (context.tenant_id, context.project_id),
        )
        return _rows(cursor.fetchall())

    def _fetch_entity_labels(self, cursor: Any, context: AgentContext) -> list[dict[str, Any]]:
        cursor.execute(
            """SELECT entity_id, label, label_type
               FROM entity_labels
               WHERE tenant_id = %s AND project_id = %s
               ORDER BY label_type, label""",
            (context.tenant_id, context.project_id),
        )
        return _rows(cursor.fetchall())

    def _fetch_relationships(self, cursor: Any, context: AgentContext) -> list[dict[str, Any]]:
        cursor.execute(
            """SELECT relationship_id, source_entity_name, target_entity_name, relationship_type,
                      summary, first_seen_segment_id, metadata_jsonb
               FROM relationships
               WHERE tenant_id = %s AND project_id = %s
               ORDER BY source_entity_name, target_entity_name, relationship_type""",
            (context.tenant_id, context.project_id),
        )
        return _rows(cursor.fetchall())

    def _fetch_plot_threads(self, cursor: Any, context: AgentContext) -> list[dict[str, Any]]:
        cursor.execute(
            """SELECT thread_id, title, status, summary, first_seen_segment_id, metadata_jsonb
               FROM plot_threads
               WHERE tenant_id = %s AND project_id = %s
               ORDER BY title""",
            (context.tenant_id, context.project_id),
        )
        return _rows(cursor.fetchall())

    def _fetch_world_rules(self, cursor: Any, context: AgentContext) -> list[dict[str, Any]]:
        cursor.execute(
            """SELECT rule_evidence_id, rule_text, category, confidence, segment_id, metadata_jsonb
               FROM world_rule_evidence
               WHERE tenant_id = %s AND project_id = %s
               ORDER BY rule_text""",
            (context.tenant_id, context.project_id),
        )
        return _rows(cursor.fetchall())

    def _fetch_assets(self, cursor: Any, context: AgentContext) -> list[dict[str, Any]]:
        cursor.execute(
            """SELECT asset_id, asset_type, category, lifecycle, title, summary, payload_jsonb, tags_jsonb
               FROM assets
               WHERE tenant_id = %s
                 AND project_id = %s
                 AND enabled = true
                 AND lifecycle IN ('seed', 'canon', 'manuscript', 'material')
                 AND asset_type IN ('archive_entity', 'artifact', 'location', 'concept')
               ORDER BY title""",
            (context.tenant_id, context.project_id),
        )
        return _rows(cursor.fetchall())

    def _next_snapshot_version(self, cursor: Any, context: AgentContext) -> int:
        cursor.execute(
            """SELECT COALESCE(max(version), 0) + 1 AS next_version
               FROM story_graph_snapshots
               WHERE tenant_id = %s AND project_id = %s""",
            (context.tenant_id, context.project_id),
        )
        row = cursor.fetchone()
        value = _row_value(row, "next_version", 0)
        return max(1, int(value or 1))

    def _build_nodes(
        self,
        *,
        graph_id: str,
        entities: list[dict[str, Any]],
        aliases: list[dict[str, Any]],
        plot_threads: list[dict[str, Any]],
        world_rules: list[dict[str, Any]],
        assets: list[dict[str, Any]],
    ) -> list[dict[str, Any]]:
        nodes = _merge_entity_nodes(graph_id=graph_id, entities=entities, aliases=aliases)
        nodes.extend(_merge_plot_thread_nodes(graph_id=graph_id, rows=plot_threads))
        nodes.extend(_merge_world_rule_nodes(graph_id=graph_id, rows=world_rules))
        _merge_asset_nodes(graph_id=graph_id, nodes=nodes, rows=assets)
        return sorted(nodes, key=_graph_node_sort_key)

    def _build_edges(
        self,
        *,
        graph_id: str,
        relationships: list[dict[str, Any]],
        node_by_entity_name: dict[str, dict[str, Any]],
    ) -> list[dict[str, Any]]:
        edges: list[dict[str, Any]] = []
        edge_by_key: dict[str, dict[str, Any]] = {}
        for row in relationships:
            source = node_by_entity_name.get(_semantic_text_key(row.get("source_entity_name")))
            target = node_by_entity_name.get(_semantic_text_key(row.get("target_entity_name")))
            if source is None or target is None:
                continue
            if source["node_id"] == target["node_id"]:
                continue
            edge_type = _graph_edge_type(row.get("relationship_type"))
            label = _optional_text(row.get("relationship_type"))
            stable_key = ":".join(
                (
                    "relationship",
                    source["stable_identity"],
                    target["stable_identity"],
                    edge_type,
                    _semantic_text_key(label),
                )
            )
            existing = edge_by_key.get(stable_key)
            evidence = {
                "source_type": "relationship",
                "source_id": str(row.get("relationship_id")),
                "segment_id": row.get("first_seen_segment_id"),
                "confidence": None,
            }
            if existing is not None:
                existing["weight"] += 1
                existing["source_ids"].append(str(row.get("relationship_id")))
                _append_unique_evidence(existing["evidence"], evidence)
                if existing["summary"] is None:
                    existing["summary"] = _optional_text(row.get("summary"))
                existing["attributes"]["source_count"] = len(existing["source_ids"])
                continue
            edge = {
                    "edge_id": _snapshot_graph_uuid(graph_id, "edge", stable_key),
                    "graph_id": graph_id,
                    "source_node_id": source["node_id"],
                    "target_node_id": target["node_id"],
                    "source_type": "relationship",
                    "source_id": str(row.get("relationship_id")),
                    "source_ids": [str(row.get("relationship_id"))],
                    "stable_identity": stable_key,
                    "edge_type": edge_type,
                    "label": label,
                    "summary": _optional_text(row.get("summary")),
                    "weight": 1,
                    "lifecycle": "seed",
                    "attributes": _sanitize_graph_value(
                        {
                            "source_type": "relationship",
                            "relationship_type": row.get("relationship_type"),
                            "stable_identity": stable_key,
                            "source_count": 1,
                            "metadata": row.get("metadata_jsonb") or {},
                        }
                    ),
                    "evidence": [evidence],
                }
            edges.append(edge)
            edge_by_key[stable_key] = edge
        return sorted(edges, key=lambda edge: edge["stable_identity"])

    def _insert_snapshot(
        self,
        cursor: Any,
        *,
        context: AgentContext,
        graph_id: str,
        version: int,
        source_hash: str,
        node_count: int,
        edge_count: int,
    ) -> None:
        cursor.execute(
            """INSERT INTO story_graph_snapshots (
                 tenant_id, graph_id, project_id, version, status, build_run_id,
                 source_version_hash, node_count, edge_count
               )
               VALUES (%s, %s, %s, %s, 'building', %s, %s, %s, %s)""",
            (
                context.tenant_id,
                graph_id,
                context.project_id,
                version,
                _uuid_or_none(context.run_id),
                source_hash,
                node_count,
                edge_count,
            ),
        )

    def _insert_clusters(
        self,
        cursor: Any,
        *,
        context: AgentContext,
        graph_id: str,
        clusters: list[dict[str, Any]],
    ) -> None:
        for cluster in clusters:
            cursor.execute(
                """INSERT INTO story_graph_clusters (
                     tenant_id, project_id, graph_id, cluster_id, cluster_key, title, summary, node_count, payload_jsonb
                   )
                   VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s::jsonb)
                   ON CONFLICT (tenant_id, project_id, graph_id, cluster_key)
                   DO UPDATE SET node_count = EXCLUDED.node_count, payload_jsonb = EXCLUDED.payload_jsonb, updated_at = now()""",
                (
                    context.tenant_id,
                    context.project_id,
                    graph_id,
                    cluster["cluster_id"],
                    cluster["cluster_key"],
                    cluster["title"],
                    cluster["summary"],
                    cluster["node_count"],
                    json.dumps(cluster["payload"], ensure_ascii=False, separators=(",", ":")),
                ),
            )

    def _insert_nodes(self, cursor: Any, *, context: AgentContext, nodes: list[dict[str, Any]]) -> None:
        for node in nodes:
            cursor.execute(
                """INSERT INTO story_graph_nodes (
                     tenant_id, project_id, graph_id, node_id, canonical_entity_id, node_type,
                     title, summary, lifecycle, importance, cluster_id, attributes_jsonb, evidence_count
                   )
                   VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s::jsonb, %s)""",
                (
                    context.tenant_id,
                    context.project_id,
                    node["graph_id"],
                    node["node_id"],
                    _uuid_or_none(node.get("canonical_entity_id")),
                    node["node_type"],
                    node["title"],
                    node["summary"],
                    node["lifecycle"],
                    node["importance"],
                    node["cluster_id"],
                    json.dumps(node["attributes"], ensure_ascii=False, separators=(",", ":")),
                    len(node["evidence"]),
                ),
            )

    def _insert_aliases(
        self,
        cursor: Any,
        *,
        context: AgentContext,
        graph_id: str,
        nodes: list[dict[str, Any]],
        aliases: list[dict[str, Any]],
    ) -> None:
        node_by_entity_id = {
            entity_id: node
            for node in nodes
            if node["source_type"] == "entity"
            for entity_id in node.get("entity_source_ids", [node["source_id"]])
        }
        for row in aliases:
            node = node_by_entity_id.get(str(row.get("entity_id")))
            alias = _optional_text(row.get("alias"))
            if node is None or alias is None:
                continue
            cursor.execute(
                """INSERT INTO story_graph_node_aliases (
                     tenant_id, project_id, graph_id, node_id, alias, source_type, confidence
                   )
                   VALUES (%s, %s, %s, %s, %s, 'entity_alias', NULL)
                   ON CONFLICT (tenant_id, project_id, graph_id, node_id, alias)
                   DO NOTHING""",
                (context.tenant_id, context.project_id, graph_id, node["node_id"], alias),
            )

    def _insert_labels(
        self,
        cursor: Any,
        *,
        context: AgentContext,
        graph_id: str,
        nodes: list[dict[str, Any]],
        labels: list[dict[str, Any]],
    ) -> None:
        node_by_entity_id = {
            entity_id: node
            for node in nodes
            if node["source_type"] == "entity"
            for entity_id in node.get("entity_source_ids", [node["source_id"]])
        }
        for row in labels:
            node = node_by_entity_id.get(str(row.get("entity_id")))
            label = _optional_text(row.get("label"))
            if node is None or label is None:
                continue
            cursor.execute(
                """INSERT INTO story_graph_node_labels (
                     tenant_id, project_id, graph_id, node_id, label, label_type, confidence
                   )
                   VALUES (%s, %s, %s, %s, %s, %s, NULL)
                   ON CONFLICT (tenant_id, project_id, graph_id, node_id, label_type, label)
                   DO NOTHING""",
                (
                    context.tenant_id,
                    context.project_id,
                    graph_id,
                    node["node_id"],
                    label,
                    _optional_text(row.get("label_type")) or "tag",
                ),
            )

    def _insert_edges(self, cursor: Any, *, context: AgentContext, edges: list[dict[str, Any]]) -> None:
        for edge in edges:
            cursor.execute(
                """INSERT INTO story_graph_edges (
                     tenant_id, project_id, graph_id, edge_id, source_node_id, target_node_id,
                     edge_type, label, summary, weight, lifecycle, attributes_jsonb, evidence_count
                   )
                   VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s::jsonb, %s)""",
                (
                    context.tenant_id,
                    context.project_id,
                    edge["graph_id"],
                    edge["edge_id"],
                    edge["source_node_id"],
                    edge["target_node_id"],
                    edge["edge_type"],
                    edge["label"],
                    edge["summary"],
                    edge["weight"],
                    edge["lifecycle"],
                    json.dumps(edge["attributes"], ensure_ascii=False, separators=(",", ":")),
                    len(edge["evidence"]),
                ),
            )

    def _insert_evidence(
        self,
        cursor: Any,
        *,
        context: AgentContext,
        graph_id: str,
        nodes: list[dict[str, Any]],
        edges: list[dict[str, Any]],
    ) -> int:
        count = 0
        for owner_type, items in (("node", nodes), ("edge", edges)):
            for item in items:
                owner_id = item["node_id"] if owner_type == "node" else item["edge_id"]
                for evidence in item["evidence"]:
                    cursor.execute(
                        """INSERT INTO story_graph_evidence (
                             tenant_id, project_id, graph_id, owner_type, owner_id,
                             source_type, source_id, chapter_id, segment_id, snippet, confidence
                           )
                           VALUES (%s, %s, %s, %s, %s, %s, %s, NULL, %s, NULL, %s)""",
                        (
                            context.tenant_id,
                            context.project_id,
                            graph_id,
                            owner_type,
                            owner_id,
                            evidence["source_type"],
                            evidence["source_id"],
                            _uuid_or_none(evidence.get("segment_id")),
                            evidence.get("confidence"),
                        ),
                    )
                    count += 1
        return count

    def _insert_layout(
        self,
        cursor: Any,
        *,
        context: AgentContext,
        graph_id: str,
        nodes: list[dict[str, Any]],
        edges: list[dict[str, Any]],
        clusters: list[dict[str, Any]],
        options: dict[str, Any],
    ) -> int:
        layout = _deterministic_cluster_layout(
            nodes=nodes,
            edges=edges,
            clusters=clusters,
            viewport_node_budget=_viewport_node_budget(options),
        )
        cursor.execute(
            """INSERT INTO story_graph_layouts (
                 tenant_id, project_id, graph_id, view_id, layout_jsonb, created_by
               )
               VALUES (%s, %s, %s, 'world', %s::jsonb, %s)
               ON CONFLICT (tenant_id, project_id, graph_id, view_id)
               DO UPDATE SET layout_jsonb = EXCLUDED.layout_jsonb, updated_at = now()""",
            (
                context.tenant_id,
                context.project_id,
                graph_id,
                json.dumps(layout, ensure_ascii=False, separators=(",", ":")),
                _uuid_or_none(context.actor_user_id),
            ),
        )
        return 1

    def _mark_snapshot_ready(
        self,
        cursor: Any,
        *,
        context: AgentContext,
        graph_id: str,
        node_count: int,
        edge_count: int,
    ) -> None:
        cursor.execute(
            """UPDATE story_graph_snapshots
               SET status = 'ready', node_count = %s, edge_count = %s, updated_at = now()
               WHERE tenant_id = %s AND project_id = %s AND graph_id = %s""",
            (node_count, edge_count, context.tenant_id, context.project_id, graph_id),
        )


def _base_payload(context: AgentContext) -> dict[str, Any]:
    return {
        **context.to_trace_payload(),
        "workflow_type": STORY_GRAPH_BUILD_WORKFLOW_TYPE,
    }


def _bond_base_payload(context: AgentContext) -> dict[str, Any]:
    return {
        **context.to_trace_payload(),
        "workflow_type": STORY_GRAPH_BOND_GENERATION_WORKFLOW_TYPE,
    }


def _sanitize_graph_value(value: Any, *, forbidden_values: list[str | None] | tuple[str | None, ...] = ()) -> Any:
    sanitized = _sanitize_graph_value_inner(value, forbidden_values=forbidden_values)
    if sanitized is _SCRUBBED_GRAPH_VALUE:
        return None
    return sanitized


def _sanitize_graph_value_inner(value: Any, *, forbidden_values: list[str | None] | tuple[str | None, ...]) -> Any:
    if isinstance(value, dict):
        sanitized: dict[str, Any] = {}
        for key, item in value.items():
            normalized_key = str(key).strip().lower()
            compact_key = normalized_key.replace("_", "").replace("-", "").replace(" ", "")
            if not normalized_key or normalized_key in SENSITIVE_GRAPH_KEYS or compact_key in SENSITIVE_GRAPH_KEYS:
                continue
            sanitized_item = _sanitize_graph_value_inner(item, forbidden_values=forbidden_values)
            if sanitized_item is _SCRUBBED_GRAPH_VALUE:
                continue
            sanitized[str(key)] = sanitized_item
        return sanitized
    if isinstance(value, list):
        sanitized_items = []
        for item in value:
            sanitized_item = _sanitize_graph_value_inner(item, forbidden_values=forbidden_values)
            if sanitized_item is not _SCRUBBED_GRAPH_VALUE:
                sanitized_items.append(sanitized_item)
        return sanitized_items
    if isinstance(value, str) and _has_sensitive_graph_value(value, forbidden_values=forbidden_values):
        return _SCRUBBED_GRAPH_VALUE
    return value


def _has_sensitive_graph_value(
    value: str,
    *,
    forbidden_values: list[str | None] | tuple[str | None, ...] = (),
) -> bool:
    normalized = value.strip().lower()
    if not normalized:
        return False
    if "node-" in normalized:
        return True
    if any(marker in normalized for marker in SENSITIVE_GRAPH_VALUE_MARKERS):
        return True
    for forbidden in forbidden_values:
        if isinstance(forbidden, str) and forbidden.strip() and forbidden.strip().lower() in normalized:
            return True
    return False


def _write_event(
    writer: WorkflowEventWriter | None,
    *,
    context: AgentContext,
    event_type: str,
    payload: dict[str, Any],
) -> bool:
    if writer is None:
        return False
    writer.write_event(
        tenant_id=context.tenant_id,
        project_id=context.project_id,
        run_id=context.run_id,
        event_type=event_type,
        payload=_sanitize_graph_value(payload),
    )
    return True


def _failed_result(
    *,
    base: dict[str, Any],
    context: AgentContext,
    code: str,
    message: str,
    workflow_event_writer: WorkflowEventWriter | None,
    workflow_status_writer: WorkflowRunStatusWriter | None = None,
) -> dict[str, Any]:
    workflow_status_persisted = _mark_workflow_failed(
        workflow_status_writer,
        context=context,
        code=code,
        message=message,
    )
    event_persisted = _write_event(
        workflow_event_writer,
        context=context,
        event_type="graph.stage.failed",
        payload={
            "stage": "story_graph_build",
            "activity": "story_graph_build_activity",
            "status": "failed",
            "error_code": code,
            "message": message,
        },
    )
    return {
        **base,
        "status": "failed",
        "stage": "story_graph_build",
        "module_key": STORY_GRAPH_BUILD_MODULE_KEY,
        "error": {
            "code": code,
            "message": message,
        },
        "stage_event_persisted": event_persisted,
        "workflow_status_persisted": workflow_status_persisted,
    }


def _bond_failed_result(
    *,
    base: dict[str, Any],
    context: AgentContext,
    code: str,
    message: str,
    workflow_event_writer: WorkflowEventWriter | None,
    workflow_status_writer: WorkflowRunStatusWriter | None = None,
) -> dict[str, Any]:
    workflow_status_persisted = _mark_workflow_failed(
        workflow_status_writer,
        context=context,
        code=code,
        message=message,
    )
    event_persisted = _write_event(
        workflow_event_writer,
        context=context,
        event_type="graph.stage.failed",
        payload={
            "stage": "graph_bond_generation",
            "activity": "graph_bond_generation_activity",
            "status": "failed",
            "error_code": code,
            "message": message,
        },
    )
    return {
        **base,
        "status": "failed",
        "stage": "graph_bond_generation",
        "module_key": GRAPH_BOND_GENERATION_MODULE_KEY,
        "error": {
            "code": code,
            "message": message,
        },
        "stage_event_persisted": event_persisted,
        "workflow_status_persisted": workflow_status_persisted,
    }


def _normalize_mode(value: Any) -> str:
    if not isinstance(value, str) or not value.strip():
        return "full"
    return value.strip()


def _story_graph_builder_from_env() -> StoryGraphBuilder | None:
    database_url = os.environ.get("DATABASE_URL")
    if not database_url:
        return None
    return PostgresStoryGraphBuilder.from_database_url(database_url)


def _workflow_status_writer_from_env() -> WorkflowRunStatusWriter | None:
    database_url = os.environ.get("DATABASE_URL")
    if not database_url:
        return None
    return PostgresWorkflowRunStatusWriter.from_database_url(database_url)


def _graph_bond_runner_from_env() -> GraphBondGenerationRunner | None:
    database_url = os.environ.get("DATABASE_URL")
    if not database_url:
        return None
    return LLMFacilityGraphBondGenerationRunner(
        binding_resolver=PostgresModuleBindingResolver.from_database_url(database_url),
        credential_provider=PostgresCredentialProvider.from_database_url(
            database_url=database_url,
            key_material=os.environ.get("LLM_CREDENTIAL_ENCRYPTION_KEY"),
        ),
        chat_client=QuotaAwareJSONChatClient(),
        candidate_writer=PostgresGraphBondCandidateWriter.from_database_url(database_url),
        quota_gate=ProviderQuotaGate(PostgresQuotaStore.from_database_url(database_url)),
    )


def _validate_graph_bond_resolution(resolution: ModuleBindingResolution) -> None:
    if resolution.module_key != GRAPH_BOND_GENERATION_MODULE_KEY:
        raise LLMFacilityError("LLM_MODULE_UNBOUND", "resolved module key does not match graph_bond_generator")
    if not resolution.supports_json:
        raise LLMFacilityError("LLM_MODULE_CAPABILITY_MISSING", "graph_bond_generator requires a JSON-capable model")
    for field_name in ("channel_id", "model_id", "provider", "base_url", "credential_ref"):
        value = getattr(resolution, field_name)
        if not isinstance(value, str) or not value.strip():
            raise LLMFacilityError("LLM_PROVIDER_ERROR", f"resolved LLM module is missing {field_name}")


def _graph_bond_messages(
    *,
    context: AgentContext,
    graph_id: str | None,
    node_ids: list[str],
    focus: str | None,
    options: dict[str, Any],
) -> list[dict[str, str]]:
    if len(node_ids) < 2:
        raise LLMFacilityError("VALIDATION_FAILED", "at least two graph node ids are required")
    return [
        {
            "role": "system",
            "content": (
                "You are the MiroFish graph_bond_generator module. Return one JSON object with arrays named "
                "bonds, plot_threads, and conflict_triggers. Each item must include title and summary. "
                "Each bonds item must also include source_entity_name, target_entity_name, and "
                "relationship_type so it can be explicitly adopted into canon later. "
                "Optional fields may include kind, thread_type, trigger_type, confidence, tags, and "
                "evidence_assumptions as public summaries only. Do not include prompt, raw story text, "
                "evidence snippets, node ids, credentials, provider metadata, drafts, manuscripts, or API keys."
            ),
        },
        {
            "role": "user",
            "content": json.dumps(
                {
                    "tenant_id": context.tenant_id,
                    "project_id": context.project_id,
                    "run_id": context.run_id,
                    "module_key": GRAPH_BOND_GENERATION_MODULE_KEY,
                    "graph_id": graph_id,
                    "selected_node_ids": node_ids,
                    "focus": focus,
                    "options": _sanitize_graph_value(options),
                },
                ensure_ascii=False,
                separators=(",", ":"),
            ),
        },
    ]


def _graph_bond_candidate_assets(
    response_json: dict[str, Any],
    *,
    forbidden_values: list[str | None] | tuple[str | None, ...] = (),
) -> list[dict[str, Any]]:
    candidates: list[dict[str, Any]] = []
    candidates.extend(
        _proposal_candidates(
            response_json.get("bonds"),
            asset_type="graph_bond",
            category="relationship",
            payload_kind_key="kind",
            forbidden_values=forbidden_values,
        )
    )
    candidates.extend(
        _proposal_candidates(
            response_json.get("plot_threads"),
            asset_type="plot_thread",
            category="plot",
            payload_kind_key="thread_type",
            forbidden_values=forbidden_values,
        )
    )
    candidates.extend(
        _proposal_candidates(
            response_json.get("conflict_triggers"),
            asset_type="conflict_trigger",
            category="plot",
            payload_kind_key="trigger_type",
            forbidden_values=forbidden_values,
        )
    )
    if not candidates:
        raise LLMFacilityError("SCHEMA_VALIDATION_FAILED", "graph bond generation returned no candidates")
    return candidates


def _proposal_candidates(
    value: Any,
    *,
    asset_type: str,
    category: str,
    payload_kind_key: str,
    forbidden_values: list[str | None] | tuple[str | None, ...] = (),
) -> list[dict[str, Any]]:
    if value is None:
        return []
    if not isinstance(value, list):
        raise LLMFacilityError("SCHEMA_VALIDATION_FAILED", "graph bond candidate groups must be arrays")
    candidates: list[dict[str, Any]] = []
    for item in value:
        if not isinstance(item, dict):
            raise LLMFacilityError("SCHEMA_VALIDATION_FAILED", "graph bond candidates must be objects")
        title = _required_graph_bond_text(item.get("title"), "title", forbidden_values=forbidden_values)
        summary = _required_graph_bond_text(item.get("summary"), "summary", forbidden_values=forbidden_values)
        payload = _candidate_public_payload(
            item,
            asset_type=asset_type,
            payload_kind_key=payload_kind_key,
            forbidden_values=forbidden_values,
        )
        if asset_type == "graph_bond":
            payload["source_entity_name"] = _required_graph_bond_text(
                item.get("source_entity_name"),
                "source_entity_name",
                forbidden_values=forbidden_values,
            )
            payload["target_entity_name"] = _required_graph_bond_text(
                item.get("target_entity_name"),
                "target_entity_name",
                forbidden_values=forbidden_values,
            )
            payload["relationship_type"] = _required_graph_bond_text(
                item.get("relationship_type"),
                "relationship_type",
                forbidden_values=forbidden_values,
            )
        candidates.append(
            {
                "asset_type": asset_type,
                "category": category,
                "title": title,
                "summary": summary,
                "tags": _graph_bond_tags(item.get("tags"), asset_type, forbidden_values=forbidden_values),
                "payload": payload,
            }
        )
    return candidates


def _candidate_public_payload(
    item: dict[str, Any],
    *,
    asset_type: str,
    payload_kind_key: str,
    forbidden_values: list[str | None] | tuple[str | None, ...] = (),
) -> dict[str, Any]:
    payload = _sanitize_graph_value(
        {
            key: value
            for key, value in item.items()
            if key not in {"asset_type", "category", "title", "summary", "tags"}
        },
        forbidden_values=forbidden_values,
    )
    if not isinstance(payload, dict):
        payload = {}
    payload["proposal_type"] = asset_type
    kind = _optional_graph_bond_text(item.get(payload_kind_key), forbidden_values=forbidden_values)
    if kind:
        payload[payload_kind_key] = kind
    confidence = _confidence_value(item.get("confidence"))
    if confidence is not None:
        payload["confidence"] = confidence
    return payload


def _graph_bond_tags(
    value: Any,
    asset_type: str,
    *,
    forbidden_values: list[str | None] | tuple[str | None, ...] = (),
) -> list[str]:
    tags = ["story_graph", asset_type]
    if isinstance(value, list):
        for item in value:
            if isinstance(item, str) and item.strip() and not _has_sensitive_graph_value(item, forbidden_values=forbidden_values):
                tag = item.strip()
                if tag not in tags:
                    tags.append(tag)
    return tags


def _required_graph_bond_text(
    value: Any,
    field_name: str,
    *,
    forbidden_values: list[str | None] | tuple[str | None, ...] = (),
) -> str:
    if not isinstance(value, str) or not value.strip():
        raise LLMFacilityError("SCHEMA_VALIDATION_FAILED", f"graph bond candidate {field_name} is required")
    text = value.strip()
    if _has_sensitive_graph_value(text, forbidden_values=forbidden_values):
        raise LLMFacilityError("SCHEMA_VALIDATION_FAILED", f"graph bond candidate {field_name} contains unsafe text")
    return text


def _optional_graph_bond_text(
    value: Any,
    *,
    forbidden_values: list[str | None] | tuple[str | None, ...] = (),
) -> str | None:
    text = _optional_text(value)
    if text is None or _has_sensitive_graph_value(text, forbidden_values=forbidden_values):
        return None
    return text


def _graph_bond_candidate_list(candidates: list[dict[str, Any]]) -> list[dict[str, Any]]:
    normalized = []
    for candidate in candidates:
        if not isinstance(candidate, dict):
            raise LLMFacilityError("SCHEMA_VALIDATION_FAILED", "graph bond candidates must be objects")
        asset_type = _required_text(candidate.get("asset_type"), "asset_type")
        if asset_type not in {"graph_bond", "plot_thread", "conflict_trigger"}:
            raise LLMFacilityError("SCHEMA_VALIDATION_FAILED", "unsupported graph bond candidate asset_type")
        normalized.append(
            {
                "asset_type": asset_type,
                "category": _optional_text(candidate.get("category")),
                "title": _required_graph_bond_text(candidate.get("title"), "title"),
                "summary": _optional_graph_bond_text(candidate.get("summary")),
                "tags": _graph_bond_tags(candidate.get("tags"), asset_type),
                "payload": _sanitize_graph_value(
                    candidate.get("payload") if isinstance(candidate.get("payload"), dict) else {}
                ),
            }
        )
    if not normalized:
        raise LLMFacilityError("SCHEMA_VALIDATION_FAILED", "graph bond generation returned no candidates")
    return normalized


def _count_candidates(candidates: list[dict[str, Any]], asset_type: str) -> int:
    return sum(1 for candidate in candidates if candidate.get("asset_type") == asset_type)


def _confidence_value(value: Any) -> float | None:
    if isinstance(value, bool) or value is None:
        return None
    if isinstance(value, (int, float)):
        return max(0.0, min(1.0, float(value)))
    return None


def _bond_runner_failed(code: str, message: str) -> dict[str, Any]:
    return {
        "status": "failed",
        "module_key": GRAPH_BOND_GENERATION_MODULE_KEY,
        "error": {
            "code": code,
            "message": message,
        },
    }


@activity.defn
def story_graph_build_activity(
    payload: dict[str, Any],
    graph_builder: StoryGraphBuilder | None = None,
    workflow_event_writer: WorkflowEventWriter | None = None,
    workflow_status_writer: WorkflowRunStatusWriter | None = None,
) -> dict[str, Any]:
    context = AgentContext.model_validate(payload.get("context", payload))
    base = _base_payload(context)
    if workflow_status_writer is None:
        try:
            workflow_status_writer = _workflow_status_writer_from_env()
        except Exception:
            workflow_status_writer = None
    if not context.has_permission(STORY_GRAPH_BUILD_MODULE_KEY, "run"):
        return _failed_result(
            base=base,
            context=context,
            code="FORBIDDEN",
            message="story_graph_build run permission is required",
            workflow_event_writer=workflow_event_writer,
            workflow_status_writer=workflow_status_writer,
        )
    if context.module_key is not None and context.module_key != STORY_GRAPH_BUILD_MODULE_KEY:
        return _failed_result(
            base=base,
            context=context,
            code="VALIDATION_FAILED",
            message=f"module_key must be {STORY_GRAPH_BUILD_MODULE_KEY}",
            workflow_event_writer=workflow_event_writer,
            workflow_status_writer=workflow_status_writer,
        )
    mode = _normalize_mode(payload.get("mode"))
    options = payload.get("options") if isinstance(payload.get("options"), dict) else {}
    if graph_builder is None:
        try:
            graph_builder = _story_graph_builder_from_env()
        except Exception:
            return _failed_result(
                base=base,
                context=context,
                code="STORY_GRAPH_BUILDER_UNCONFIGURED",
                message="story graph builder requires DB-backed canon source configuration",
                workflow_event_writer=workflow_event_writer,
                workflow_status_writer=workflow_status_writer,
            )
    if graph_builder is None:
        return _failed_result(
            base=base,
            context=context,
            code="STORY_GRAPH_BUILDER_UNCONFIGURED",
            message="story graph builder requires DB-backed canon source configuration",
            workflow_event_writer=workflow_event_writer,
            workflow_status_writer=workflow_status_writer,
        )
    try:
        result = graph_builder.build(
            context=context,
            mode=mode,
            options=_sanitize_graph_value(options),
        )
    except Exception:
        return _failed_result(
            base=base,
            context=context,
            code="STORY_GRAPH_BUILD_FAILED",
            message="story graph build failed",
            workflow_event_writer=workflow_event_writer,
            workflow_status_writer=workflow_status_writer,
        )
    if result.get("status") != "completed":
        return _failed_result(
            base=base,
            context=context,
            code="STORY_GRAPH_BUILD_FAILED",
            message="story graph build failed",
            workflow_event_writer=workflow_event_writer,
            workflow_status_writer=workflow_status_writer,
        )
    public_result = _sanitize_graph_value(result)
    status_result = _public_workflow_status_result(public_result)
    try:
        _mark_workflow_completed(workflow_status_writer, context=context, result=status_result)
        workflow_status_persisted = workflow_status_writer is not None
    except Exception:
        return _failed_result(
            base=base,
            context=context,
            code="WORKFLOW_RUN_NOT_FOUND",
            message="story graph workflow admission parent row is missing",
            workflow_event_writer=workflow_event_writer,
            workflow_status_writer=None,
        )
    _write_event(
        workflow_event_writer,
        context=context,
        event_type="graph.stage.completed",
        payload={
            "stage": "story_graph_build",
            "status": "completed",
            "graph_id": public_result.get("graph_id"),
            "node_count": public_result.get("node_count", 0),
            "edge_count": public_result.get("edge_count", 0),
        },
    )
    return {
        **base,
        "status": "completed",
        "stage": "story_graph_build",
        "module_key": STORY_GRAPH_BUILD_MODULE_KEY,
        "graph_id": public_result.get("graph_id"),
        "node_count": public_result.get("node_count", 0),
        "edge_count": public_result.get("edge_count", 0),
        "layout_count": public_result.get("layout_count", 0),
        "cluster_count": public_result.get("cluster_count", 0),
        "workflow_status_persisted": workflow_status_persisted,
    }


def _normalize_node_ids(value: Any) -> list[str]:
    if not isinstance(value, list):
        return []
    normalized: list[str] = []
    seen: set[str] = set()
    for item in value:
        if not isinstance(item, str):
            continue
        node_id = item.strip()
        if not node_id or node_id in seen:
            continue
        seen.add(node_id)
        normalized.append(node_id)
    return normalized


def _public_bond_generation_result(result: dict[str, Any]) -> dict[str, Any]:
    public = _sanitize_graph_value(result)
    return {
        "candidate_batch_id": public.get("candidate_batch_id"),
        "candidate_count": _count_value(public.get("candidate_count")),
        "bond_candidate_count": _count_value(public.get("bond_candidate_count")),
        "plot_thread_candidate_count": _count_value(public.get("plot_thread_candidate_count")),
        "conflict_trigger_count": _count_value(public.get("conflict_trigger_count")),
        "model_id": public.get("model_id"),
    }


@activity.defn
def graph_bond_generation_activity(
    payload: dict[str, Any],
    bond_runner: GraphBondGenerationRunner | None = None,
    workflow_event_writer: WorkflowEventWriter | None = None,
    workflow_status_writer: WorkflowRunStatusWriter | None = None,
) -> dict[str, Any]:
    context = AgentContext.model_validate(payload.get("context", payload))
    base = _bond_base_payload(context)
    if workflow_status_writer is None:
        try:
            workflow_status_writer = _workflow_status_writer_from_env()
        except Exception:
            workflow_status_writer = None
    if context.workflow_type != STORY_GRAPH_BOND_GENERATION_WORKFLOW_TYPE:
        return _bond_failed_result(
            base=base,
            context=context,
            code="VALIDATION_FAILED",
            message=f"workflow_type must be {STORY_GRAPH_BOND_GENERATION_WORKFLOW_TYPE}",
            workflow_event_writer=workflow_event_writer,
            workflow_status_writer=workflow_status_writer,
        )
    if not context.project_id:
        return _bond_failed_result(
            base=base,
            context=context,
            code="VALIDATION_FAILED",
            message="project_id is required",
            workflow_event_writer=workflow_event_writer,
            workflow_status_writer=workflow_status_writer,
        )
    if context.module_key != GRAPH_BOND_GENERATION_MODULE_KEY:
        return _bond_failed_result(
            base=base,
            context=context,
            code="VALIDATION_FAILED",
            message=f"module_key must be {GRAPH_BOND_GENERATION_MODULE_KEY}",
            workflow_event_writer=workflow_event_writer,
            workflow_status_writer=workflow_status_writer,
        )
    if not context.has_permission(GRAPH_BOND_GENERATION_MODULE_KEY, "run"):
        return _bond_failed_result(
            base=base,
            context=context,
            code="FORBIDDEN",
            message="graph_bond_generator run permission is required",
            workflow_event_writer=workflow_event_writer,
            workflow_status_writer=workflow_status_writer,
        )
    node_ids = _normalize_node_ids(payload.get("node_ids"))
    if len(node_ids) < 2:
        return _bond_failed_result(
            base=base,
            context=context,
            code="VALIDATION_FAILED",
            message="at least two graph node ids are required",
            workflow_event_writer=workflow_event_writer,
            workflow_status_writer=workflow_status_writer,
        )
    if bond_runner is None:
        try:
            bond_runner = _graph_bond_runner_from_env()
        except Exception:
            return _bond_failed_result(
                base=base,
                context=context,
                code="GRAPH_BOND_RUNNER_UNCONFIGURED",
                message="graph bond generation runner requires LLM Facility-backed configuration",
                workflow_event_writer=workflow_event_writer,
                workflow_status_writer=workflow_status_writer,
            )
    if bond_runner is None:
        return _bond_failed_result(
            base=base,
            context=context,
            code="GRAPH_BOND_RUNNER_UNCONFIGURED",
            message="graph bond generation runner requires LLM Facility-backed configuration",
            workflow_event_writer=workflow_event_writer,
            workflow_status_writer=workflow_status_writer,
        )
    graph_id = _optional_text(payload.get("graph_id"))
    focus = _optional_text(payload.get("focus"))
    options = payload.get("options") if isinstance(payload.get("options"), dict) else {}
    try:
        result = bond_runner.generate(
            context=context,
            graph_id=graph_id,
            node_ids=node_ids,
            focus=focus,
            options=_sanitize_graph_value(options),
        )
    except Exception:
        return _bond_failed_result(
            base=base,
            context=context,
            code="GRAPH_BOND_GENERATION_FAILED",
            message="graph bond generation failed",
            workflow_event_writer=workflow_event_writer,
            workflow_status_writer=workflow_status_writer,
        )
    if result.get("status") != "completed":
        error = result.get("error") if isinstance(result.get("error"), dict) else {}
        return _bond_failed_result(
            base=base,
            context=context,
            code=_optional_text(error.get("code")) or "GRAPH_BOND_GENERATION_FAILED",
            message=_optional_text(error.get("message")) or "graph bond generation failed",
            workflow_event_writer=workflow_event_writer,
            workflow_status_writer=workflow_status_writer,
        )
    public_result = _public_bond_generation_result(result)
    try:
        _mark_workflow_completed(workflow_status_writer, context=context, result=public_result)
        workflow_status_persisted = workflow_status_writer is not None
    except Exception:
        return _bond_failed_result(
            base=base,
            context=context,
            code="WORKFLOW_RUN_NOT_FOUND",
            message="story graph bond workflow admission parent row is missing",
            workflow_event_writer=workflow_event_writer,
            workflow_status_writer=None,
        )
    _write_event(
        workflow_event_writer,
        context=context,
        event_type="graph.stage.completed",
        payload={
            "stage": "graph_bond_generation",
            "status": "completed",
            "candidate_batch_id": public_result.get("candidate_batch_id"),
            "bond_candidate_count": public_result.get("bond_candidate_count", 0),
            "plot_thread_candidate_count": public_result.get("plot_thread_candidate_count", 0),
            "conflict_trigger_count": public_result.get("conflict_trigger_count", 0),
            "model_id": public_result.get("model_id"),
        },
    )
    return {
        **base,
        "status": "completed",
        "stage": "graph_bond_generation",
        "module_key": GRAPH_BOND_GENERATION_MODULE_KEY,
        **public_result,
        "workflow_status_persisted": workflow_status_persisted,
    }


def _rows(rows: Any) -> list[dict[str, Any]]:
    return [dict(row) for row in rows or []]


def _row_value(row: Any, key: str, index: int = 0) -> Any:
    if row is None:
        return None
    if isinstance(row, dict):
        return row.get(key)
    return row[index]


def _count_value(value: Any) -> int:
    try:
        return int(value or 0)
    except (TypeError, ValueError):
        return 0


def _required_text(value: Any, field_name: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{field_name} is required")
    return value.strip()


def _optional_text(value: Any) -> str | None:
    if value is None:
        return None
    if not isinstance(value, str) or not value.strip():
        return None
    return value.strip()


def _uuid_or_none(value: Any) -> str | None:
    if not isinstance(value, str) or not value.strip():
        return None
    try:
        return str(uuid.UUID(value.strip()))
    except ValueError:
        return None


def _rollback_connection(connection: Any) -> None:
    try:
        connection.rollback()
    except Exception:
        return


def _semantic_text_key(value: Any) -> str:
    normalized = unicodedata.normalize("NFKC", str(value or "")).casefold().strip()
    return re.sub(r"[\W_]+", "", normalized, flags=re.UNICODE)


def _snapshot_graph_uuid(graph_id: str, kind: str, stable_identity: str) -> str:
    return str(uuid.uuid5(uuid.UUID(graph_id), f"{kind}:{stable_identity}"))


def _append_unique_evidence(evidence: list[dict[str, Any]], candidate: dict[str, Any]) -> None:
    identity = (
        candidate.get("source_type"),
        candidate.get("source_id"),
        candidate.get("segment_id"),
    )
    if any(
        (item.get("source_type"), item.get("source_id"), item.get("segment_id")) == identity
        for item in evidence
    ):
        return
    evidence.append(candidate)


def _entity_aliases_by_id(aliases: list[dict[str, Any]]) -> dict[str, list[str]]:
    result: dict[str, list[str]] = {}
    for row in aliases:
        entity_id = str(row.get("entity_id") or "")
        alias = _optional_text(row.get("alias"))
        if not entity_id or alias is None:
            continue
        values = result.setdefault(entity_id, [])
        if alias not in values:
            values.append(alias)
    for values in result.values():
        values.sort(key=_semantic_text_key)
    return result


def _merge_entity_nodes(
    *,
    graph_id: str,
    entities: list[dict[str, Any]],
    aliases: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    ordered = sorted(entities, key=lambda row: str(row.get("entity_id") or ""))
    if not ordered:
        return []
    aliases_by_id = _entity_aliases_by_id(aliases)
    parents = list(range(len(ordered)))

    def find(index: int) -> int:
        while parents[index] != index:
            parents[index] = parents[parents[index]]
            index = parents[index]
        return index

    def union(left: int, right: int) -> None:
        left_root = find(left)
        right_root = find(right)
        if left_root == right_root:
            return
        parents[max(left_root, right_root)] = min(left_root, right_root)

    key_owner: dict[tuple[str, str], int] = {}
    for index, row in enumerate(ordered):
        entity_id = str(row.get("entity_id") or "")
        node_type = _graph_node_type(row.get("entity_type"))
        names = [_required_text(row.get("canonical_name"), "canonical_name"), *aliases_by_id.get(entity_id, [])]
        for name in names:
            key = _semantic_text_key(name)
            if not key:
                continue
            owner = key_owner.get((node_type, key))
            if owner is None:
                key_owner[(node_type, key)] = index
            else:
                union(index, owner)

    groups: dict[int, list[dict[str, Any]]] = {}
    for index, row in enumerate(ordered):
        groups.setdefault(find(index), []).append(row)

    nodes: list[dict[str, Any]] = []
    for rows in groups.values():
        rows.sort(key=lambda row: str(row.get("entity_id") or ""))
        canonical = max(
            rows,
            key=lambda row: (_importance_score(row.get("importance")), -len(str(row.get("canonical_name") or ""))),
        )
        source_ids = [str(row.get("entity_id")) for row in rows]
        stable_identity = f"entity:{source_ids[0]}"
        node_type = _graph_node_type(canonical.get("entity_type"))
        evidence: list[dict[str, Any]] = []
        for row in rows:
            _append_unique_evidence(
                evidence,
                {
                    "source_type": "entity",
                    "source_id": str(row.get("entity_id")),
                    "segment_id": row.get("first_seen_segment_id"),
                    "confidence": None,
                },
            )
        public_aliases = sorted(
            {
                name
                for row in rows
                for name in [
                    _required_text(row.get("canonical_name"), "canonical_name"),
                    *aliases_by_id.get(str(row.get("entity_id")), []),
                ]
                if name != _required_text(canonical.get("canonical_name"), "canonical_name")
            },
            key=_semantic_text_key,
        )
        nodes.append(
            {
                "node_id": _snapshot_graph_uuid(graph_id, "node", stable_identity),
                "graph_id": graph_id,
                "source_type": "entity",
                "source_id": source_ids[0],
                "entity_source_ids": source_ids,
                "canonical_entity_id": source_ids[0],
                "stable_identity": stable_identity,
                "node_type": node_type,
                "title": _required_text(canonical.get("canonical_name"), "canonical_name"),
                "summary": next((_optional_text(row.get("state_summary")) for row in rows if _optional_text(row.get("state_summary"))), None),
                "lifecycle": "seed",
                "importance": max(_importance_score(row.get("importance")) for row in rows),
                "cluster_key": node_type,
                "cluster_id": None,
                "attributes": _sanitize_graph_value(
                    {
                        "source_type": "entity",
                        "stable_identity": stable_identity,
                        "entity_type": canonical.get("entity_type"),
                        "merged_source_count": len(rows),
                        "aliases": public_aliases,
                        "metadata": canonical.get("metadata_jsonb") or {},
                    }
                ),
                "evidence": evidence,
            }
        )
    return nodes


def _merge_plot_thread_nodes(*, graph_id: str, rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    grouped: dict[str, list[dict[str, Any]]] = {}
    for row in rows:
        title = _required_text(row.get("title"), "thread title")
        grouped.setdefault(_semantic_text_key(title), []).append(row)
    nodes: list[dict[str, Any]] = []
    for title_key, matches in sorted(grouped.items()):
        matches.sort(key=lambda row: str(row.get("thread_id") or ""))
        canonical = matches[0]
        stable_identity = f"plot_thread:{title_key}"
        evidence: list[dict[str, Any]] = []
        for row in matches:
            _append_unique_evidence(
                evidence,
                {
                    "source_type": "plot_thread",
                    "source_id": str(row.get("thread_id")),
                    "segment_id": row.get("first_seen_segment_id"),
                    "confidence": None,
                },
            )
        nodes.append(
            {
                "node_id": _snapshot_graph_uuid(graph_id, "node", stable_identity),
                "graph_id": graph_id,
                "source_type": "plot_thread",
                "source_id": str(canonical.get("thread_id")),
                "stable_identity": stable_identity,
                "canonical_entity_id": None,
                "node_type": "plot_thread",
                "title": _required_text(canonical.get("title"), "thread title"),
                "summary": next((_optional_text(row.get("summary")) for row in matches if _optional_text(row.get("summary"))), None),
                "lifecycle": "seed",
                "importance": 0.7,
                "cluster_key": "plot_thread",
                "cluster_id": None,
                "attributes": _sanitize_graph_value(
                    {
                        "source_type": "plot_thread",
                        "stable_identity": stable_identity,
                        "status": canonical.get("status"),
                        "merged_source_count": len(matches),
                    }
                ),
                "evidence": evidence,
            }
        )
    return nodes


def _merge_world_rule_nodes(*, graph_id: str, rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    grouped: dict[str, list[dict[str, Any]]] = {}
    for row in rows:
        title = _required_text(row.get("rule_text"), "rule_text")
        grouped.setdefault(_semantic_text_key(title), []).append(row)
    nodes: list[dict[str, Any]] = []
    for title_key, matches in sorted(grouped.items()):
        matches.sort(key=lambda row: str(row.get("rule_evidence_id") or ""))
        canonical = max(matches, key=lambda row: float(row.get("confidence") or 0.5))
        stable_identity = f"world_rule:{title_key}"
        evidence: list[dict[str, Any]] = []
        for row in matches:
            _append_unique_evidence(
                evidence,
                {
                    "source_type": "world_rule",
                    "source_id": str(row.get("rule_evidence_id")),
                    "segment_id": row.get("segment_id"),
                    "confidence": row.get("confidence"),
                },
            )
        nodes.append(
            {
                "node_id": _snapshot_graph_uuid(graph_id, "node", stable_identity),
                "graph_id": graph_id,
                "source_type": "world_rule",
                "source_id": str(canonical.get("rule_evidence_id")),
                "stable_identity": stable_identity,
                "canonical_entity_id": None,
                "node_type": "world_rule",
                "title": _required_text(canonical.get("rule_text"), "rule_text"),
                "summary": _optional_text(canonical.get("category")),
                "lifecycle": "seed",
                "importance": max(float(row.get("confidence") or 0.5) for row in matches),
                "cluster_key": "world_rule",
                "cluster_id": None,
                "attributes": _sanitize_graph_value(
                    {
                        "source_type": "world_rule",
                        "stable_identity": stable_identity,
                        "category": canonical.get("category"),
                        "merged_source_count": len(matches),
                    }
                ),
                "evidence": evidence,
            }
        )
    return nodes


def _merge_asset_nodes(*, graph_id: str, nodes: list[dict[str, Any]], rows: list[dict[str, Any]]) -> None:
    entity_by_source_id = {
        source_id: node
        for node in nodes
        if node["source_type"] == "entity"
        for source_id in node.get("entity_source_ids", [node["source_id"]])
    }
    for row in sorted(rows, key=lambda item: str(item.get("asset_id") or "")):
        asset_id = str(row.get("asset_id") or "")
        payload = row.get("payload_jsonb") if isinstance(row.get("payload_jsonb"), dict) else {}
        linked_entity_id = str(payload.get("canonical_entity_id") or payload.get("entity_id") or "")
        linked = entity_by_source_id.get(linked_entity_id)
        evidence = {
            "source_type": "asset",
            "source_id": asset_id,
            "segment_id": None,
            "confidence": None,
        }
        if linked is not None:
            _append_unique_evidence(linked["evidence"], evidence)
            linked["importance"] = max(linked["importance"], 0.4)
            linked["lifecycle"] = _more_canonical_lifecycle(linked["lifecycle"], _graph_lifecycle(row.get("lifecycle")))
            attributes = linked["attributes"] if isinstance(linked.get("attributes"), dict) else {}
            attributes["linked_asset_count"] = int(attributes.get("linked_asset_count") or 0) + 1
            linked["attributes"] = _sanitize_graph_value(attributes)
            continue
        stable_identity = f"asset:{asset_id}"
        node_type = _asset_node_type(row.get("asset_type"))
        nodes.append(
            {
                "node_id": _snapshot_graph_uuid(graph_id, "node", stable_identity),
                "graph_id": graph_id,
                "source_type": "asset",
                "source_id": asset_id,
                "stable_identity": stable_identity,
                "canonical_entity_id": None,
                "node_type": node_type,
                "title": _required_text(row.get("title"), "asset title"),
                "summary": _optional_text(row.get("summary")),
                "lifecycle": _graph_lifecycle(row.get("lifecycle")),
                "importance": 0.4,
                "cluster_key": node_type,
                "cluster_id": None,
                "attributes": _sanitize_graph_value(
                    {
                        "source_type": "asset",
                        "stable_identity": stable_identity,
                        "asset_type": row.get("asset_type"),
                        "category": row.get("category"),
                        "payload": payload,
                        "tags": row.get("tags_jsonb") or [],
                    }
                ),
                "evidence": [evidence],
            }
        )


def _more_canonical_lifecycle(left: str, right: str) -> str:
    rank = {"archived": 0, "candidate": 1, "seed": 2, "simulation": 3, "manuscript": 4, "canon": 5}
    return max((left, right), key=lambda item: rank.get(item, 0))


def _entity_name_index(nodes: list[dict[str, Any]]) -> dict[str, dict[str, Any]]:
    result: dict[str, dict[str, Any]] = {}
    for node in nodes:
        if node.get("source_type") != "entity":
            continue
        names = [node.get("title"), *(node.get("attributes", {}).get("aliases", []) or [])]
        for name in names:
            key = _semantic_text_key(name)
            if key:
                result[key] = node
    return result


def _graph_node_sort_key(node: dict[str, Any]) -> tuple[Any, ...]:
    return (-float(node.get("importance") or 0), node.get("node_type") or "", node.get("stable_identity") or "")


def _assign_graph_clusters(
    *,
    graph_id: str,
    nodes: list[dict[str, Any]],
    edges: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    node_by_id = {node["node_id"]: node for node in nodes}
    adjacency: dict[str, set[str]] = {node_id: set() for node_id in node_by_id}
    degree: dict[str, int] = {node_id: 0 for node_id in node_by_id}
    for edge in edges:
        source_id = edge["source_node_id"]
        target_id = edge["target_node_id"]
        if source_id not in adjacency or target_id not in adjacency:
            continue
        adjacency[source_id].add(target_id)
        adjacency[target_id].add(source_id)
        degree[source_id] += 1
        degree[target_id] += 1

    visited: set[str] = set()
    cluster_groups: list[tuple[str, str, list[dict[str, Any]]]] = []
    isolated_by_type: dict[str, list[dict[str, Any]]] = {}
    for node in sorted(nodes, key=lambda item: item["stable_identity"]):
        node_id = node["node_id"]
        if node_id in visited:
            continue
        if not adjacency[node_id]:
            visited.add(node_id)
            isolated_by_type.setdefault(node["node_type"], []).append(node)
            continue
        stack = [node_id]
        component: list[dict[str, Any]] = []
        while stack:
            current_id = stack.pop()
            if current_id in visited:
                continue
            visited.add(current_id)
            component.append(node_by_id[current_id])
            stack.extend(sorted(adjacency[current_id] - visited, reverse=True))
        stable_key = min(item["stable_identity"] for item in component)
        cluster_groups.append((f"network:{stable_key}", "relationship_component", component))
    for node_type, group in sorted(isolated_by_type.items()):
        cluster_groups.append((f"type:{node_type}", "node_type_bucket", group))

    clusters: list[dict[str, Any]] = []
    for cluster_key, strategy, group in sorted(cluster_groups, key=lambda item: item[0]):
        cluster_id = _snapshot_graph_uuid(graph_id, "cluster", cluster_key)
        for node in group:
            node["cluster_id"] = cluster_id
            node["cluster_key"] = cluster_key
            node["degree"] = degree[node["node_id"]]
            node["importance"] = min(1.0, float(node["importance"]) + min(0.2, degree[node["node_id"]] * 0.02))
        importance = max((float(node["importance"]) for node in group), default=0.0)
        clusters.append(
            {
                "cluster_id": cluster_id,
                "cluster_key": cluster_key,
                "title": _cluster_title(cluster_key),
                "summary": f"{len(group)} public graph nodes grouped by {strategy.replace('_', ' ')}",
                "node_count": len(group),
                "importance": importance,
                "nodes": sorted(group, key=_graph_node_sort_key),
                "payload": {
                    "stable_identity": cluster_key,
                    "strategy": strategy,
                    "importance": importance,
                    "node_types": sorted({node["node_type"] for node in group}),
                },
            }
        )
    return sorted(clusters, key=lambda cluster: (-cluster["importance"], cluster["cluster_key"]))


def _deterministic_cluster_layout(
    *,
    nodes: list[dict[str, Any]],
    edges: list[dict[str, Any]],
    clusters: list[dict[str, Any]],
    viewport_node_budget: int,
) -> dict[str, Any]:
    layout_nodes: list[dict[str, Any]] = []
    layout_clusters: list[dict[str, Any]] = []
    row_y = 0
    cluster_index = 0
    while cluster_index < len(clusters):
        row = clusters[cluster_index : cluster_index + 3]
        row_layout: list[tuple[dict[str, Any], int, int]] = []
        x = 0
        row_height = 0
        for cluster in row:
            count = max(1, cluster["node_count"])
            columns = max(1, math.ceil(math.sqrt(count)))
            rows = math.ceil(count / columns)
            width = max(280, columns * GRAPH_LAYOUT_NODE_WIDTH + (columns + 1) * 28)
            height = max(180, rows * GRAPH_LAYOUT_NODE_HEIGHT + (rows + 1) * 24 + 44)
            row_layout.append((cluster, x, width))
            x += width + GRAPH_LAYOUT_CLUSTER_GAP
            row_height = max(row_height, height)
        for cluster, cluster_x, width in row_layout:
            count = max(1, cluster["node_count"])
            columns = max(1, math.ceil(math.sqrt(count)))
            rows = math.ceil(count / columns)
            height = max(180, rows * GRAPH_LAYOUT_NODE_HEIGHT + (rows + 1) * 24 + 44)
            layout_clusters.append(
                {
                    "cluster_id": cluster["cluster_id"],
                    "cluster_key": cluster["cluster_key"],
                    "x": cluster_x,
                    "y": row_y,
                    "width": width,
                    "height": height,
                    "node_count": cluster["node_count"],
                }
            )
            for node_index, node in enumerate(cluster["nodes"]):
                layout_nodes.append(
                    {
                        "node_id": node["node_id"],
                        "x": cluster_x + 28 + (node_index % columns) * GRAPH_LAYOUT_NODE_WIDTH,
                        "y": row_y + 68 + (node_index // columns) * GRAPH_LAYOUT_NODE_HEIGHT,
                        "node_type": node["node_type"],
                        "cluster_id": cluster["cluster_id"],
                        "cluster_key": cluster["cluster_key"],
                        "importance": node["importance"],
                        "degree": node.get("degree", 0),
                    }
                )
        row_y += row_height + GRAPH_LAYOUT_CLUSTER_GAP
        cluster_index += 3
    return {
        "view_id": "world",
        "schema_version": GRAPH_LAYOUT_SCHEMA_VERSION,
        "strategy": "deterministic_cluster_grid",
        "node_count": len(nodes),
        "edge_count": len(edges),
        "nodes": layout_nodes,
        "clusters": layout_clusters,
        "viewport": {
            "mode": "cluster_overview" if len(nodes) > viewport_node_budget else "expanded",
            "total_node_count": len(nodes),
            "total_cluster_count": len(clusters),
            "recommended_page_size": viewport_node_budget,
            "omitted_node_count": 0,
            "strategy_basis": "all node positions persisted; cluster overview recommended when the interactive node budget is exceeded",
        },
    }


def _viewport_node_budget(options: dict[str, Any]) -> int:
    value = options.get("viewport_node_budget")
    if isinstance(value, bool):
        return GRAPH_LAYOUT_DEFAULT_VIEWPORT_NODE_BUDGET
    try:
        parsed = int(value)
    except (TypeError, ValueError):
        return GRAPH_LAYOUT_DEFAULT_VIEWPORT_NODE_BUDGET
    return parsed if parsed > 0 else GRAPH_LAYOUT_DEFAULT_VIEWPORT_NODE_BUDGET


def _graph_node_hash_record(node: dict[str, Any]) -> dict[str, Any]:
    return {
        "stable_identity": node.get("stable_identity"),
        "node_type": node.get("node_type"),
        "title": node.get("title"),
        "summary": node.get("summary"),
        "lifecycle": node.get("lifecycle"),
        "importance": node.get("importance"),
        "attributes": node.get("attributes"),
        "evidence": node.get("evidence"),
    }


def _graph_edge_hash_record(edge: dict[str, Any]) -> dict[str, Any]:
    return {
        "stable_identity": edge.get("stable_identity"),
        "edge_type": edge.get("edge_type"),
        "label": edge.get("label"),
        "summary": edge.get("summary"),
        "weight": edge.get("weight"),
        "evidence": edge.get("evidence"),
    }


def _graph_node_type(value: Any) -> str:
    normalized = str(value or "").strip().lower()
    if normalized in {"character", "organization", "faction", "location", "artifact", "concept"}:
        return normalized
    return "concept"


def _asset_node_type(value: Any) -> str:
    normalized = str(value or "").strip().lower()
    if normalized in {"location", "artifact", "concept"}:
        return normalized
    return "artifact"


def _graph_edge_type(value: Any) -> str:
    normalized = str(value or "").strip().lower()
    if normalized in {
        "relationship",
        "participates_in",
        "belongs_to",
        "opposes",
        "constrained_by",
        "causes",
        "reveals",
        "foreshadows",
        "located_in",
        "mentions",
    }:
        return normalized
    if normalized in {"enemy", "rival", "conflict", "opponent"}:
        return "opposes"
    return "relationship"


def _graph_lifecycle(value: Any) -> str:
    normalized = str(value or "").strip().lower()
    if normalized in {"seed", "candidate", "canon", "simulation", "manuscript", "archived"}:
        return normalized
    if normalized == "material":
        return "canon"
    return "seed"


def _importance_score(value: Any) -> float:
    normalized = str(value or "").strip().lower()
    if normalized in {"critical", "high", "major", "main"}:
        return 0.9
    if normalized in {"medium", "normal", "supporting"}:
        return 0.6
    if normalized in {"low", "minor"}:
        return 0.3
    try:
        return max(0.0, min(1.0, float(value)))
    except (TypeError, ValueError):
        return 0.5


def _public_workflow_status_result(result: dict[str, Any]) -> dict[str, Any]:
    public = _sanitize_graph_value(result)
    return {
        "graph_id": public.get("graph_id"),
        "node_count": _count_value(public.get("node_count")),
        "edge_count": _count_value(public.get("edge_count")),
        "layout_count": _count_value(public.get("layout_count")),
        "cluster_count": _count_value(public.get("cluster_count")),
    }


def _workflow_status_message(status: str, result: dict[str, Any] | None, message: str | None) -> str:
    if status == "completed" and result is not None:
        if _is_graph_bond_generation_result(result):
            return (
                "graph bond candidates ready: "
                f"{_count_value(result.get('candidate_count'))} candidates, "
                f"{_count_value(result.get('bond_candidate_count'))} bonds, "
                f"{_count_value(result.get('plot_thread_candidate_count'))} threads, "
                f"{_count_value(result.get('conflict_trigger_count'))} triggers"
            )
        return f"story graph ready: {result.get('node_count', 0)} nodes, {result.get('edge_count', 0)} edges"
    if message:
        return message
    return "story graph build failed"


def _is_graph_bond_generation_result(result: dict[str, Any]) -> bool:
    return any(
        key in result
        for key in (
            "candidate_batch_id",
            "candidate_count",
            "bond_candidate_count",
            "plot_thread_candidate_count",
            "conflict_trigger_count",
        )
    )


def _mark_workflow_completed(
    writer: WorkflowRunStatusWriter | None,
    *,
    context: AgentContext,
    result: dict[str, Any],
) -> bool:
    if writer is None:
        return False
    writer.mark_completed(context=context, result=result)
    return True


def _mark_workflow_failed(
    writer: WorkflowRunStatusWriter | None,
    *,
    context: AgentContext,
    code: str,
    message: str,
) -> bool:
    if writer is None:
        return False
    try:
        writer.mark_failed(context=context, code=code, message=message)
    except Exception:
        return False
    return True


def _cluster_title(cluster_key: str) -> str:
    return cluster_key.replace("_", " ").title()


def _source_version_hash(value: dict[str, Any]) -> str:
    encoded = json.dumps(_sanitize_graph_value(value), ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(encoded.encode("utf-8")).hexdigest()


@workflow.defn
class StoryGraphBuildWorkflow:
    @workflow.run
    async def run(self, payload: dict[str, Any]) -> dict[str, Any]:
        return await workflow.execute_activity(
            story_graph_build_activity,
            payload,
            start_to_close_timeout=timedelta(minutes=30),
            schedule_to_close_timeout=timedelta(hours=2),
        )


@workflow.defn
class GraphBondGenerationWorkflow:
    @workflow.run
    async def run(self, payload: dict[str, Any]) -> dict[str, Any]:
        return await workflow.execute_activity(
            graph_bond_generation_activity,
            payload,
            start_to_close_timeout=timedelta(minutes=30),
            schedule_to_close_timeout=timedelta(hours=2),
        )


def worker_spec() -> dict[str, list[str] | str]:
    return {
        "task_queue": GRAPH_TASK_QUEUE,
        "workflows": [StoryGraphBuildWorkflow.__name__, GraphBondGenerationWorkflow.__name__],
        "activities": [story_graph_build_activity.__name__, graph_bond_generation_activity.__name__],
    }
