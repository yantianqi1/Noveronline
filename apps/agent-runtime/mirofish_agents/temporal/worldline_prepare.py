from __future__ import annotations

import json
import os
import time
from datetime import timedelta
from typing import Any, Callable, Protocol
from uuid import NAMESPACE_URL, UUID, uuid5

from temporalio import activity, workflow
from temporalio.common import RetryPolicy

from mirofish_agents.common.context import AgentContext
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


WORLDLINE_PREPARE_WORKFLOW_TYPE = "worldline_preparation"
WORLDLINE_PREPARE_MODULE_KEY = "worldline_agent_prepare"
WORLDLINE_PREPARE_ACTIVITY_RETRY_POLICY = RetryPolicy(
    initial_interval=timedelta(seconds=5),
    backoff_coefficient=2.0,
    maximum_interval=timedelta(minutes=1),
    maximum_attempts=3,
)

_SENSITIVE_KEYS = {
    "api_key",
    "body",
    "body_text",
    "content",
    "content_text",
    "credential_ref",
    "draft",
    "encrypted_api_key",
    "manuscript",
    "private_profile",
    "prompt",
    "raw_content",
    "raw_text",
    "response",
    "runtime_seed_state",
    "source_material",
    "source_text",
    "text",
}
_ACTIVE_STATUSES = {"queued", "running"}
_AGENT_SOURCE_KINDS = {"asset", "entity"}
_CONTEXT_SOURCE_KINDS = _AGENT_SOURCE_KINDS | {"saved_path", "worldline_event"}


class WorldlinePrepareScopeStore(Protocol):
    def load_scope(self, *, context: AgentContext, prepare_id: str) -> dict[str, Any]:
        ...

    def materialize_agents(
        self,
        *,
        context: AgentContext,
        prepare_id: str,
        model_id: str,
        agents: list[dict[str, Any]],
    ) -> dict[str, Any]:
        ...


class WorldlinePrepareLifecycleWriter(Protocol):
    def mark_completed(
        self,
        *,
        context: AgentContext,
        prepare_id: str,
        result: dict[str, Any],
    ) -> None:
        ...

    def mark_failed(
        self,
        *,
        context: AgentContext,
        prepare_id: str,
        code: str,
        message: str,
    ) -> None:
        ...


class WorldlinePrepareRunner(Protocol):
    def run_prepare(self, *, context: AgentContext, prepare_id: str) -> dict[str, Any]:
        ...


class LLMFacilityWorldlinePrepareRunner:
    def __init__(
        self,
        *,
        binding_resolver: ModuleBindingResolver,
        credential_provider: CredentialProvider,
        chat_client: JSONChatClient,
        scope_store: WorldlinePrepareScopeStore,
        telemetry_writer: Any | None = None,
    ) -> None:
        self._binding_resolver = binding_resolver
        self._credential_provider = credential_provider
        self._chat_client = chat_client
        self._scope_store = scope_store
        self._telemetry_writer = telemetry_writer

    def run_prepare(self, *, context: AgentContext, prepare_id: str) -> dict[str, Any]:
        started_at = time.monotonic()
        resolution: ModuleBindingResolution | None = None
        completed_telemetry_recorded = False
        try:
            _required_uuid(context.run_id, "run_id")
            normalized_prepare_id = _required_uuid(prepare_id, "prepare_id")
            scope = self._scope_store.load_scope(context=context, prepare_id=normalized_prepare_id)
            if scope.get("already_completed") is True:
                return {
                    "status": "completed",
                    "prepare_id": normalized_prepare_id,
                    "prepared_agent_count": _positive_int(scope.get("existing_agent_count")),
                    "reused": True,
                }

            selected_agents = _public_records(scope.get("selected_agents"))
            selected_sources = _public_records(scope.get("selected_sources"))
            if not selected_agents:
                raise LLMFacilityError(
                    "WORLDLINE_PREPARATION_SELECTION_MISSING",
                    "worldline preparation requires at least one selected agent",
                )
            if not selected_sources:
                raise LLMFacilityError(
                    "WORLDLINE_PREPARATION_SOURCE_NOT_FOUND",
                    "worldline preparation sources were not found",
                )

            resolution = self._binding_resolver.resolve_module_binding(
                context=context,
                module_key=WORLDLINE_PREPARE_MODULE_KEY,
            )
            _validate_resolution(resolution)
            api_key = self._credential_provider.resolve_api_key(
                context=context,
                credential_ref=resolution.credential_ref,
            )
            if not isinstance(api_key, str) or not api_key.strip():
                raise LLMFacilityError("LLM_CREDENTIAL_UNAVAILABLE", "resolved credential was empty")
            response = self._chat_client.complete_json(
                context=context,
                resolution=resolution,
                api_key=api_key.strip(),
                messages=_prepare_messages(
                    context=context,
                    prepare_id=normalized_prepare_id,
                    goal_summary=_optional_text(scope.get("goal_summary")),
                    selected_agents=selected_agents,
                    selected_sources=selected_sources,
                ),
            )
            agents = _prepared_agents(response.get("prepared_agents"), selected_agents=selected_agents)
            _record_completed_telemetry(
                self._telemetry_writer,
                context=context,
                resolution=resolution,
                usage=_llm_usage(response),
                latency_ms=_latency_ms(started_at),
            )
            completed_telemetry_recorded = True
            persisted = self._scope_store.materialize_agents(
                context=context,
                prepare_id=normalized_prepare_id,
                model_id=resolution.model_id,
                agents=agents,
            )
        except LLMFacilityError as exc:
            if resolution is not None and not completed_telemetry_recorded and exc.code != "LLM_TELEMETRY_WRITE_FAILED":
                try:
                    _record_failed_telemetry(
                        self._telemetry_writer,
                        context=context,
                        resolution=resolution,
                        code=exc.code,
                        message=exc.message,
                        latency_ms=_latency_ms(started_at),
                    )
                except LLMFacilityError as telemetry_exc:
                    return _failed(telemetry_exc.code, telemetry_exc.message)
            return _failed(exc.code, exc.message)
        except Exception:
            if resolution is not None and not completed_telemetry_recorded:
                try:
                    _record_failed_telemetry(
                        self._telemetry_writer,
                        context=context,
                        resolution=resolution,
                        code="LLM_PROVIDER_ERROR",
                        message="worldline prepare provider call failed",
                        latency_ms=_latency_ms(started_at),
                    )
                except LLMFacilityError as telemetry_exc:
                    return _failed(telemetry_exc.code, telemetry_exc.message)
            return _failed("LLM_PROVIDER_ERROR", "worldline prepare provider call failed")

        return {
            "status": "completed",
            "prepare_id": normalized_prepare_id,
            "module_key": WORLDLINE_PREPARE_MODULE_KEY,
            "model_id": resolution.model_id,
            "prepared_agent_count": _positive_int(persisted.get("prepared_agent_count")),
            "reused": bool(persisted.get("reused")),
        }


class PostgresWorldlinePrepareScopeStore:
    def __init__(self, *, connect: Callable[[], Any]) -> None:
        self._connect = connect

    @classmethod
    def from_database_url(cls, database_url: str) -> "PostgresWorldlinePrepareScopeStore":
        try:
            import psycopg
            from psycopg.rows import dict_row
        except ImportError as exc:  # pragma: no cover - runtime packaging guard
            raise RuntimeError("psycopg is required for DATABASE_URL worldline preparation") from exc
        return cls(connect=lambda: psycopg.connect(database_url, row_factory=dict_row))

    def load_scope(self, *, context: AgentContext, prepare_id: str) -> dict[str, Any]:
        if not context.project_id:
            raise LLMFacilityError("VALIDATION_FAILED", "project_id is required for worldline preparation")
        normalized_prepare_id = _required_uuid(prepare_id, "prepare_id")
        normalized_run_id = _required_uuid(context.run_id, "run_id")
        connection = self._connect()
        try:
            set_postgres_tenant_context(connection, context=context)
            with connection.cursor() as cursor:
                cursor.execute(
                    """SELECT
                         preparation.status AS preparation_status,
                         preparation.lifecycle,
                         preparation.goal_summary,
                         COALESCE(preparation.anchor_path_id::text, '') AS anchor_path_id,
                         workflow_run.status AS workflow_status,
                         COALESCE(queued_event.payload_jsonb->'options', '{}'::jsonb)::text AS options_json,
                         (SELECT COUNT(*)::int
                            FROM worldline_prepared_agents prepared_agent
                           WHERE prepared_agent.tenant_id = preparation.tenant_id
                             AND prepared_agent.project_id = preparation.project_id
                             AND prepared_agent.prepare_id = preparation.prepare_id
                             AND prepared_agent.status = 'ready') AS existing_agent_count
                       FROM worldline_preparations preparation
                       JOIN workflow_runs workflow_run
                         ON workflow_run.tenant_id = preparation.tenant_id
                        AND workflow_run.project_id = preparation.project_id
                        AND workflow_run.run_id = preparation.run_id
                        AND workflow_run.workflow_type = 'worldline_preparation'
                       LEFT JOIN LATERAL (
                         SELECT payload_jsonb
                           FROM workflow_events
                          WHERE tenant_id = preparation.tenant_id
                            AND project_id = preparation.project_id
                            AND run_id = preparation.run_id
                            AND workflow_type = 'worldline_preparation'
                            AND event_type = 'workflow.queued'
                          ORDER BY sequence ASC
                          LIMIT 1
                       ) queued_event ON TRUE
                      WHERE preparation.tenant_id = %s
                        AND preparation.project_id = %s
                        AND preparation.prepare_id = %s
                        AND preparation.run_id = %s
                      FOR UPDATE OF preparation, workflow_run""",
                    (context.tenant_id, context.project_id, normalized_prepare_id, normalized_run_id),
                )
                row = cursor.fetchone()
                if row is None:
                    raise LLMFacilityError(
                        "WORLDLINE_PREPARATION_NOT_FOUND",
                        "worldline preparation was not admitted for this tenant/project/run",
                    )
                preparation_status = _row_text(row, "preparation_status")
                lifecycle = _row_text(row, "lifecycle")
                existing_count = _positive_int(_row_get(row, "existing_agent_count"))
                if preparation_status == "completed" and lifecycle == "ready":
                    if existing_count < 1:
                        raise LLMFacilityError(
                            "WORLDLINE_PREPARATION_STATE_INVALID",
                            "ready worldline preparation has no prepared agents",
                        )
                    connection.commit()
                    return {
                        "already_completed": True,
                        "existing_agent_count": existing_count,
                        "goal_summary": _row_text(row, "goal_summary"),
                        "selected_agents": [],
                        "selected_sources": [],
                    }
                workflow_status = _row_text(row, "workflow_status")
                if preparation_status not in _ACTIVE_STATUSES or workflow_status not in _ACTIVE_STATUSES:
                    raise LLMFacilityError(
                        "WORLDLINE_PREPARATION_NOT_ACTIVE",
                        "worldline preparation is not active",
                    )
                options = _json_object(_row_get(row, "options_json"))
                agent_refs = _selection_refs(options, keys=("agent_refs", "selected_agent_refs"), allowed=_AGENT_SOURCE_KINDS)
                if not agent_refs:
                    raise LLMFacilityError(
                        "WORLDLINE_PREPARATION_SELECTION_MISSING",
                        "worldline preparation requires persisted agent_refs",
                    )
                source_refs = _selection_refs(
                    options,
                    keys=("source_refs", "selected_source_refs"),
                    allowed=_CONTEXT_SOURCE_KINDS,
                )
                anchor_path_id = _row_text(row, "anchor_path_id")
                if anchor_path_id:
                    source_refs = _dedupe_refs(
                        [*source_refs, {"source_kind": "saved_path", "source_id": _required_uuid(anchor_path_id, "anchor_path_id")}]
                    )
                selected_agents, selected_sources = self._resolve_sources(
                    cursor,
                    context=context,
                    agent_refs=agent_refs,
                    source_refs=source_refs,
                )
                cursor.execute(
                    """UPDATE worldline_preparations
                          SET status = 'running', updated_at = now()
                        WHERE tenant_id = %s
                          AND project_id = %s
                          AND prepare_id = %s
                          AND run_id = %s
                          AND status IN ('queued', 'running')""",
                    (context.tenant_id, context.project_id, normalized_prepare_id, normalized_run_id),
                )
                cursor.execute(
                    """UPDATE workflow_runs
                          SET status = 'running', progress = GREATEST(progress, 10),
                              message = 'worldline preparation running', updated_at = now()
                        WHERE tenant_id = %s
                          AND project_id = %s
                          AND run_id = %s
                          AND workflow_type = 'worldline_preparation'
                          AND status IN ('queued', 'running')""",
                    (context.tenant_id, context.project_id, normalized_run_id),
                )
            connection.commit()
            return {
                "already_completed": False,
                "existing_agent_count": existing_count,
                "goal_summary": _row_text(row, "goal_summary"),
                "selected_agents": selected_agents,
                "selected_sources": selected_sources,
            }
        except LLMFacilityError:
            _rollback(connection)
            raise
        except Exception as exc:
            _rollback(connection)
            raise LLMFacilityError(
                "WORLDLINE_PREPARATION_SOURCE_LOAD_FAILED",
                "worldline preparation source load failed",
            ) from exc
        finally:
            connection.close()

    def _resolve_sources(
        self,
        cursor: Any,
        *,
        context: AgentContext,
        agent_refs: list[dict[str, str]],
        source_refs: list[dict[str, str]],
    ) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
        all_refs = _dedupe_refs([*agent_refs, *source_refs])
        by_kind = {kind: [ref["source_id"] for ref in all_refs if ref["source_kind"] == kind] for kind in _CONTEXT_SOURCE_KINDS}
        resolved: dict[str, dict[str, Any]] = {}
        if by_kind["asset"]:
            cursor.execute(
                """SELECT asset_id::text AS source_id, title, summary, asset_type, COALESCE(category, '') AS category
                     FROM assets
                    WHERE tenant_id = %s AND project_id = %s AND enabled = true
                      AND asset_id::text = ANY(%s)""",
                (context.tenant_id, context.project_id, by_kind["asset"]),
            )
            for row in cursor.fetchall():
                source_id = _row_text(row, "source_id")
                resolved[f"asset:{source_id}"] = {
                    "selection_ref": f"asset:{source_id}",
                    "source_kind": "asset",
                    "source_id": source_id,
                    "source_asset_id": source_id,
                    "display_name": _row_text(row, "title"),
                    "title": _row_text(row, "title"),
                    "role": _row_text(row, "category") or _row_text(row, "asset_type"),
                    "summary": _row_text(row, "summary"),
                    "asset_type": _row_text(row, "asset_type"),
                    "category": _row_text(row, "category"),
                }
        if by_kind["entity"]:
            requested_entity_ids = list(by_kind["entity"])
            # Web may send story_graph_nodes.node_id as entity:<node_id>; map to
            # entities.entity_id via canonical_entity_id when available.
            cursor.execute(
                """SELECT node_id::text AS node_id, canonical_entity_id::text AS entity_id
                     FROM story_graph_nodes
                    WHERE tenant_id = %s AND project_id = %s
                      AND node_id::text = ANY(%s)
                      AND canonical_entity_id IS NOT NULL""",
                (context.tenant_id, context.project_id, requested_entity_ids),
            )
            node_to_entity: dict[str, str] = {}
            entity_lookup_ids: set[str] = set(requested_entity_ids)
            for row in cursor.fetchall():
                node_id = _row_text(row, "node_id")
                entity_id = _row_text(row, "entity_id")
                if node_id and entity_id:
                    node_to_entity[node_id] = entity_id
                    entity_lookup_ids.add(entity_id)
            cursor.execute(
                """SELECT entity_id::text AS source_id, canonical_name, entity_type, COALESCE(state_summary, '') AS summary
                     FROM entities
                    WHERE tenant_id = %s AND project_id = %s
                      AND entity_id::text = ANY(%s)""",
                (context.tenant_id, context.project_id, list(entity_lookup_ids)),
            )
            entities_by_id: dict[str, dict[str, Any]] = {}
            for row in cursor.fetchall():
                source_id = _row_text(row, "source_id")
                entities_by_id[source_id] = {
                    "source_kind": "entity",
                    "source_id": source_id,
                    "source_asset_id": None,
                    "display_name": _row_text(row, "canonical_name"),
                    "title": _row_text(row, "canonical_name"),
                    "role": _row_text(row, "entity_type"),
                    "summary": _row_text(row, "summary"),
                }
            for requested_id in requested_entity_ids:
                entity = entities_by_id.get(requested_id)
                if entity is None:
                    mapped_entity_id = node_to_entity.get(requested_id)
                    if mapped_entity_id:
                        entity = entities_by_id.get(mapped_entity_id)
                if entity is None:
                    continue
                resolved[f"entity:{requested_id}"] = {
                    **entity,
                    "selection_ref": f"entity:{requested_id}",
                    "source_id": entity["source_id"],
                    "graph_node_id": requested_id if requested_id in node_to_entity else None,
                }
            # Also resolve any leftover graph nodes that lack a mapped entity by
            # using the graph node public fields so selection_ref still works.
            unresolved_node_ids = [
                requested_id
                for requested_id in requested_entity_ids
                if f"entity:{requested_id}" not in resolved
            ]
            if unresolved_node_ids:
                cursor.execute(
                    """SELECT node_id::text AS source_id, title, COALESCE(summary, '') AS summary, node_type
                         FROM story_graph_nodes
                        WHERE tenant_id = %s AND project_id = %s
                          AND node_id::text = ANY(%s)""",
                    (context.tenant_id, context.project_id, unresolved_node_ids),
                )
                for row in cursor.fetchall():
                    source_id = _row_text(row, "source_id")
                    resolved[f"entity:{source_id}"] = {
                        "selection_ref": f"entity:{source_id}",
                        "source_kind": "entity",
                        "source_id": source_id,
                        "source_asset_id": None,
                        "display_name": _row_text(row, "title"),
                        "title": _row_text(row, "title"),
                        "role": _row_text(row, "node_type"),
                        "summary": _row_text(row, "summary"),
                        "graph_node_id": source_id,
                    }
        if by_kind["saved_path"]:
            cursor.execute(
                """SELECT path_id::text AS source_id, title, summary, lifecycle
                     FROM worldline_saved_paths
                    WHERE tenant_id = %s AND project_id = %s
                      AND path_id::text = ANY(%s)""",
                (context.tenant_id, context.project_id, by_kind["saved_path"]),
            )
            for row in cursor.fetchall():
                source_id = _row_text(row, "source_id")
                resolved[f"saved_path:{source_id}"] = {
                    "selection_ref": f"saved_path:{source_id}",
                    "source_kind": "saved_path",
                    "source_id": source_id,
                    "title": _row_text(row, "title"),
                    "summary": _row_text(row, "summary"),
                    "lifecycle": _row_text(row, "lifecycle"),
                }
        if by_kind["worldline_event"]:
            cursor.execute(
                """SELECT event.event_id::text AS source_id, event.title, event.summary, event.kind, event.status
                     FROM worldline_events event
                     JOIN worldline_sessions session
                       ON session.tenant_id = event.tenant_id
                      AND session.project_id = event.project_id
                      AND session.session_id = event.session_id
                    WHERE event.tenant_id = %s AND event.project_id = %s
                      AND event.event_id::text = ANY(%s)
                      AND event.status IN ('candidate', 'canon')""",
                (context.tenant_id, context.project_id, by_kind["worldline_event"]),
            )
            for row in cursor.fetchall():
                source_id = _row_text(row, "source_id")
                resolved[f"worldline_event:{source_id}"] = {
                    "selection_ref": f"worldline_event:{source_id}",
                    "source_kind": "worldline_event",
                    "source_id": source_id,
                    "title": _row_text(row, "title"),
                    "summary": _row_text(row, "summary"),
                    "kind": _row_text(row, "kind"),
                    "status": _row_text(row, "status"),
                }

        missing = [ref for ref in all_refs if _selection_key(ref) not in resolved]
        if missing:
            raise LLMFacilityError(
                "WORLDLINE_PREPARATION_SOURCE_NOT_FOUND",
                "one or more worldline preparation sources were not found in this tenant/project",
            )
        selected_agents = [resolved[_selection_key(ref)] for ref in agent_refs]
        context_refs = _dedupe_refs([*agent_refs, *source_refs])
        selected_sources = [resolved[_selection_key(ref)] for ref in context_refs]
        return _public_records(selected_agents), _public_records(selected_sources)

    def materialize_agents(
        self,
        *,
        context: AgentContext,
        prepare_id: str,
        model_id: str,
        agents: list[dict[str, Any]],
    ) -> dict[str, Any]:
        if not context.project_id:
            raise LLMFacilityError("VALIDATION_FAILED", "project_id is required to materialize prepared agents")
        normalized_prepare_id = _required_uuid(prepare_id, "prepare_id")
        normalized_run_id = _required_uuid(context.run_id, "run_id")
        if not agents:
            raise LLMFacilityError("SCHEMA_VALIDATION_FAILED", "prepared_agents must not be empty")
        connection = self._connect()
        try:
            set_postgres_tenant_context(connection, context=context)
            with connection.cursor() as cursor:
                cursor.execute(
                    """SELECT status, lifecycle
                         FROM worldline_preparations
                        WHERE tenant_id = %s AND project_id = %s AND prepare_id = %s AND run_id = %s
                        FOR UPDATE""",
                    (context.tenant_id, context.project_id, normalized_prepare_id, normalized_run_id),
                )
                scope_row = cursor.fetchone()
                if scope_row is None:
                    raise LLMFacilityError(
                        "WORLDLINE_PREPARATION_NOT_FOUND",
                        "worldline preparation was not admitted for this tenant/project/run",
                    )
                if _row_text(scope_row, "status") == "completed" and _row_text(scope_row, "lifecycle") == "ready":
                    cursor.execute(
                        """SELECT COUNT(*)::int AS prepared_agent_count
                             FROM worldline_prepared_agents
                            WHERE tenant_id = %s AND project_id = %s AND prepare_id = %s AND status = 'ready'""",
                        (context.tenant_id, context.project_id, normalized_prepare_id),
                    )
                    count = _positive_int(_row_get(cursor.fetchone(), "prepared_agent_count"))
                    if count < 1:
                        raise LLMFacilityError(
                            "WORLDLINE_PREPARATION_STATE_INVALID",
                            "ready worldline preparation has no prepared agents",
                        )
                    connection.commit()
                    return {"prepared_agent_count": count, "reused": True}
                if _row_text(scope_row, "status") not in _ACTIVE_STATUSES:
                    raise LLMFacilityError("WORLDLINE_PREPARATION_NOT_ACTIVE", "worldline preparation is not active")
                for agent in agents:
                    cursor.execute(
                        """INSERT INTO worldline_prepared_agents (
                             tenant_id, agent_id, prepare_id, project_id, display_name, role,
                             status, source_asset_id, summary
                           ) VALUES (%s, %s, %s, %s, %s, %s, 'ready', %s, %s)
                           ON CONFLICT (agent_id) DO NOTHING""",
                        (
                            context.tenant_id,
                            _prepared_agent_id(normalized_prepare_id, agent["selection_ref"]),
                            normalized_prepare_id,
                            context.project_id,
                            agent["display_name"],
                            agent["role"],
                            agent.get("source_asset_id"),
                            agent["summary"],
                        ),
                    )
                cursor.execute(
                    """SELECT COUNT(*)::int AS prepared_agent_count
                         FROM worldline_prepared_agents
                        WHERE tenant_id = %s AND project_id = %s AND prepare_id = %s AND status = 'ready'""",
                    (context.tenant_id, context.project_id, normalized_prepare_id),
                )
                count = _positive_int(_row_get(cursor.fetchone(), "prepared_agent_count"))
                if count != len(agents):
                    raise LLMFacilityError(
                        "WORLDLINE_PREPARATION_STATE_INVALID",
                        "prepared agent materialization count is inconsistent",
                    )
                cursor.execute(
                    """UPDATE worldline_preparations
                          SET status = 'completed', lifecycle = 'ready', updated_at = now()
                        WHERE tenant_id = %s AND project_id = %s AND prepare_id = %s AND run_id = %s
                          AND status IN ('queued', 'running')
                        RETURNING prepare_id""",
                    (context.tenant_id, context.project_id, normalized_prepare_id, normalized_run_id),
                )
                if cursor.fetchone() is None:
                    raise LLMFacilityError(
                        "WORLDLINE_PREPARATION_NOT_ACTIVE",
                        "worldline preparation is not active",
                    )
            connection.commit()
            return {"prepared_agent_count": count, "reused": False, "model_id": model_id}
        except LLMFacilityError:
            _rollback(connection)
            raise
        except Exception as exc:
            _rollback(connection)
            raise LLMFacilityError(
                "WORLDLINE_PREPARED_AGENT_WRITE_FAILED",
                "worldline prepared agent write failed",
            ) from exc
        finally:
            connection.close()


class PostgresWorldlinePrepareLifecycleWriter:
    def __init__(self, *, connect: Callable[[], Any]) -> None:
        self._connect = connect

    @classmethod
    def from_database_url(cls, database_url: str) -> "PostgresWorldlinePrepareLifecycleWriter":
        try:
            import psycopg
            from psycopg.rows import dict_row
        except ImportError as exc:  # pragma: no cover - runtime packaging guard
            raise RuntimeError("psycopg is required for DATABASE_URL worldline preparation lifecycle") from exc
        return cls(connect=lambda: psycopg.connect(database_url, row_factory=dict_row))

    def mark_completed(
        self,
        *,
        context: AgentContext,
        prepare_id: str,
        result: dict[str, Any],
    ) -> None:
        count = _positive_int(result.get("prepared_agent_count"))
        if count < 1:
            raise LLMFacilityError(
                "WORLDLINE_PREPARATION_STATE_INVALID",
                "completed worldline preparation requires prepared agents",
            )
        self._persist(
            context=context,
            prepare_id=prepare_id,
            status="completed",
            code=None,
            message=f"worldline preparation completed with {count} prepared agents",
            payload={
                "stage": "worldline_prepare",
                "activity": "worldline_prepare_activity",
                "status": "completed",
                "module_key": WORLDLINE_PREPARE_MODULE_KEY,
                "prepare_id": prepare_id,
                "prepared_agent_count": count,
                "model_id": result.get("model_id"),
                "reused": bool(result.get("reused")),
            },
        )

    def mark_failed(
        self,
        *,
        context: AgentContext,
        prepare_id: str,
        code: str,
        message: str,
    ) -> None:
        self._persist(
            context=context,
            prepare_id=prepare_id,
            status="failed",
            code=code,
            message=_safe_error_message(code, message),
            payload={
                "stage": "worldline_prepare",
                "activity": "worldline_prepare_activity",
                "status": "failed",
                "module_key": WORLDLINE_PREPARE_MODULE_KEY,
                "prepare_id": prepare_id,
                "error_code": code,
                "message": _safe_error_message(code, message),
            },
        )

    def _persist(
        self,
        *,
        context: AgentContext,
        prepare_id: str,
        status: str,
        code: str | None,
        message: str,
        payload: dict[str, Any],
    ) -> None:
        if not context.project_id:
            raise LLMFacilityError("WORKFLOW_RUN_NOT_FOUND", "worldline preparation project is missing")
        normalized_prepare_id = _required_uuid(prepare_id, "prepare_id")
        normalized_run_id = _required_uuid(context.run_id, "run_id")
        event_type = "worldline.stage.completed" if status == "completed" else "worldline.stage.failed"
        encoded_payload = json.dumps(_sanitize(payload), ensure_ascii=False, separators=(",", ":"))
        encoded_result = json.dumps(_public_result(payload), ensure_ascii=False, separators=(",", ":")) if status == "completed" else None
        connection = self._connect()
        try:
            set_postgres_tenant_context(connection, context=context)
            with connection.cursor() as cursor:
                cursor.execute(
                    """SELECT preparation.status AS preparation_status, preparation.lifecycle, workflow_run.status AS workflow_status
                         FROM worldline_preparations preparation
                         JOIN workflow_runs workflow_run
                           ON workflow_run.tenant_id = preparation.tenant_id
                          AND workflow_run.project_id = preparation.project_id
                          AND workflow_run.run_id = preparation.run_id
                          AND workflow_run.workflow_type = 'worldline_preparation'
                        WHERE preparation.tenant_id = %s AND preparation.project_id = %s
                          AND preparation.prepare_id = %s AND preparation.run_id = %s
                        FOR UPDATE OF preparation, workflow_run""",
                    (context.tenant_id, context.project_id, normalized_prepare_id, normalized_run_id),
                )
                row = cursor.fetchone()
                if row is None:
                    raise LLMFacilityError(
                        "WORKFLOW_RUN_NOT_FOUND",
                        "worldline preparation admission parent row is missing",
                    )
                if status == "failed" and _row_text(row, "preparation_status") == "completed":
                    raise LLMFacilityError(
                        "WORLDLINE_PREPARATION_ALREADY_COMPLETED",
                        "completed worldline preparation cannot be marked failed",
                    )
                cursor.execute(
                    """UPDATE workflow_runs
                          SET status = %s, progress = 100, message = %s,
                              result_jsonb = CASE WHEN %s::jsonb IS NULL THEN result_jsonb ELSE %s::jsonb END,
                              error_code = %s, error_message = %s, updated_at = now()
                        WHERE tenant_id = %s AND project_id = %s AND run_id = %s
                          AND workflow_type = 'worldline_preparation'
                          AND status IN ('queued', 'running', 'completed', 'failed')""",
                    (
                        status,
                        message,
                        encoded_result,
                        encoded_result,
                        code,
                        message if code else None,
                        context.tenant_id,
                        context.project_id,
                        normalized_run_id,
                    ),
                )
                cursor.execute(
                    """UPDATE worldline_preparations
                          SET status = %s,
                              lifecycle = CASE WHEN %s = 'completed' THEN 'ready' ELSE lifecycle END,
                              updated_at = now()
                        WHERE tenant_id = %s AND project_id = %s AND prepare_id = %s AND run_id = %s""",
                    (status, status, context.tenant_id, context.project_id, normalized_prepare_id, normalized_run_id),
                )
                cursor.execute(
                    """SELECT 1 FROM workflow_events
                        WHERE tenant_id = %s AND project_id = %s AND run_id = %s
                          AND workflow_type = 'worldline_preparation' AND event_type = %s
                        LIMIT 1""",
                    (context.tenant_id, context.project_id, normalized_run_id, event_type),
                )
                if cursor.fetchone() is None:
                    cursor.execute(
                        """INSERT INTO workflow_events (
                             tenant_id, run_id, workflow_type, project_id, event_type, sequence, payload_jsonb
                           ) VALUES (
                             %s, %s, 'worldline_preparation', %s, %s,
                             (SELECT COALESCE(MAX(sequence), 0) + 1 FROM workflow_events WHERE tenant_id = %s AND run_id = %s),
                             %s::jsonb
                           )""",
                        (
                            context.tenant_id,
                            normalized_run_id,
                            context.project_id,
                            event_type,
                            context.tenant_id,
                            normalized_run_id,
                            encoded_payload,
                        ),
                    )
            connection.commit()
        except LLMFacilityError:
            _rollback(connection)
            raise
        except Exception as exc:
            _rollback(connection)
            raise LLMFacilityError(
                "WORLDLINE_PREPARATION_STATUS_WRITE_FAILED",
                "worldline preparation status write failed",
            ) from exc
        finally:
            connection.close()


@activity.defn
def worldline_prepare_activity(
    payload: dict[str, Any],
    prepare_runner: WorldlinePrepareRunner | None = None,
    lifecycle_writer: WorldlinePrepareLifecycleWriter | None = None,
) -> dict[str, Any]:
    context = AgentContext.model_validate(payload.get("context", payload))
    base = {**context.to_trace_payload(), "workflow_type": WORLDLINE_PREPARE_WORKFLOW_TYPE}
    prepare_id = _optional_text(payload.get("prepare_id"))
    if lifecycle_writer is None:
        try:
            lifecycle_writer = _lifecycle_writer_from_env()
        except Exception:
            lifecycle_writer = None
    validation_error = _validate_activity_context(context=context, prepare_id=prepare_id)
    if validation_error is not None:
        return _activity_failed(
            base=base,
            context=context,
            prepare_id=prepare_id,
            code=validation_error[0],
            message=validation_error[1],
            lifecycle_writer=lifecycle_writer,
            persist=_has_persistable_scope(context=context, prepare_id=prepare_id),
        )
    normalized_prepare_id = _required_uuid(prepare_id, "prepare_id")
    if prepare_runner is None:
        try:
            prepare_runner = _prepare_runner_from_env()
        except Exception:
            prepare_runner = None
    if prepare_runner is None:
        return _activity_failed(
            base=base,
            context=context,
            prepare_id=normalized_prepare_id,
            code="WORLDLINE_PREPARE_RUNNER_UNCONFIGURED",
            message="worldline prepare runner requires a configured database and LLM Facility",
            lifecycle_writer=lifecycle_writer,
        )
    try:
        result = prepare_runner.run_prepare(context=context, prepare_id=normalized_prepare_id)
    except LLMFacilityError as exc:
        result = _failed(exc.code, exc.message)
    except Exception:
        result = _failed("WORLDLINE_PREPARE_FAILED", "worldline prepare runner failed")
    if not isinstance(result, dict) or result.get("status") == "failed":
        error = result.get("error") if isinstance(result, dict) and isinstance(result.get("error"), dict) else {}
        return _activity_failed(
            base=base,
            context=context,
            prepare_id=normalized_prepare_id,
            code=_optional_text(error.get("code")) or "WORLDLINE_PREPARE_FAILED",
            message=_safe_error_message(
                _optional_text(error.get("code")) or "WORLDLINE_PREPARE_FAILED",
                _optional_text(error.get("message")) or "worldline prepare runner failed",
            ),
            lifecycle_writer=lifecycle_writer,
        )
    public_result = _public_result({"prepare_id": normalized_prepare_id, **result})
    state_persisted = False
    if lifecycle_writer is not None:
        try:
            lifecycle_writer.mark_completed(
                context=context,
                prepare_id=normalized_prepare_id,
                result=public_result,
            )
            state_persisted = True
        except LLMFacilityError as exc:
            return {
                **base,
                "status": "failed",
                "stage": "worldline_prepare",
                "module_key": WORLDLINE_PREPARE_MODULE_KEY,
                "prepare_id": normalized_prepare_id,
                "error": {"code": exc.code, "message": _safe_error_message(exc.code, exc.message)},
                "workflow_state_persisted": False,
            }
        except Exception:
            return {
                **base,
                "status": "failed",
                "stage": "worldline_prepare",
                "module_key": WORLDLINE_PREPARE_MODULE_KEY,
                "prepare_id": normalized_prepare_id,
                "error": {
                    "code": "WORLDLINE_PREPARATION_STATUS_WRITE_FAILED",
                    "message": "worldline preparation status write failed",
                },
                "workflow_state_persisted": False,
            }
    return {
        **base,
        "status": "completed",
        "stage": "worldline_prepare",
        "module_key": WORLDLINE_PREPARE_MODULE_KEY,
        **public_result,
        "workflow_state_persisted": state_persisted,
    }


@workflow.defn
class WorldlinePrepareWorkflow:
    @workflow.run
    async def run(self, payload: dict[str, Any]) -> dict[str, Any]:
        return await workflow.execute_activity(
            worldline_prepare_activity,
            payload,
            start_to_close_timeout=timedelta(minutes=30),
            schedule_to_close_timeout=timedelta(hours=3),
            retry_policy=WORLDLINE_PREPARE_ACTIVITY_RETRY_POLICY,
        )


def run_worldline_prepare_workflow_locally(
    payload: dict[str, Any],
    *,
    prepare_runner: WorldlinePrepareRunner | None = None,
    lifecycle_writer: WorldlinePrepareLifecycleWriter | None = None,
) -> dict[str, Any]:
    return worldline_prepare_activity(
        payload,
        prepare_runner=prepare_runner,
        lifecycle_writer=lifecycle_writer,
    )


def _prepare_runner_from_env() -> WorldlinePrepareRunner | None:
    database_url = os.environ.get("DATABASE_URL", "").strip()
    if not database_url:
        return None
    from mirofish_agents.llm_quota import (
        PostgresQuotaStore,
        ProviderQuotaGate,
        QuotaAwareJSONChatClient,
        QuotaEnforcedJSONChatClient,
    )

    return LLMFacilityWorldlinePrepareRunner(
        binding_resolver=PostgresModuleBindingResolver.from_database_url(database_url),
        credential_provider=PostgresCredentialProvider.from_database_url(
            database_url=database_url,
            key_material=os.environ.get("LLM_CREDENTIAL_ENCRYPTION_KEY"),
        ),
        chat_client=QuotaEnforcedJSONChatClient(
            quota_gate=ProviderQuotaGate(PostgresQuotaStore.from_database_url(database_url)),
            stage_prefix="worldline_agent_prepare",
            provider_client=QuotaAwareJSONChatClient(),
        ),
        scope_store=PostgresWorldlinePrepareScopeStore.from_database_url(database_url),
        telemetry_writer=None,
    )


def _lifecycle_writer_from_env() -> WorldlinePrepareLifecycleWriter | None:
    database_url = os.environ.get("DATABASE_URL", "").strip()
    if not database_url:
        return None
    return PostgresWorldlinePrepareLifecycleWriter.from_database_url(database_url)


def _validate_activity_context(*, context: AgentContext, prepare_id: str) -> tuple[str, str] | None:
    if context.workflow_type != WORLDLINE_PREPARE_WORKFLOW_TYPE:
        return "VALIDATION_FAILED", f"workflow_type must be {WORLDLINE_PREPARE_WORKFLOW_TYPE}"
    if context.module_key is not None and context.module_key != WORLDLINE_PREPARE_MODULE_KEY:
        return "VALIDATION_FAILED", f"module_key must be {WORLDLINE_PREPARE_MODULE_KEY}"
    if not context.project_id:
        return "VALIDATION_FAILED", "project_id is required for worldline preparation"
    try:
        _required_uuid(context.run_id, "run_id")
        _required_uuid(prepare_id, "prepare_id")
    except LLMFacilityError as exc:
        return exc.code, exc.message
    if not context.has_permission(WORLDLINE_PREPARE_MODULE_KEY, "run"):
        return "FORBIDDEN", "worldline_agent_prepare run permission is required"
    return None


def _has_persistable_scope(*, context: AgentContext, prepare_id: str) -> bool:
    if not context.project_id:
        return False
    try:
        _required_uuid(context.run_id, "run_id")
        _required_uuid(prepare_id, "prepare_id")
    except LLMFacilityError:
        return False
    return True


def _activity_failed(
    *,
    base: dict[str, Any],
    context: AgentContext,
    prepare_id: str,
    code: str,
    message: str,
    lifecycle_writer: WorldlinePrepareLifecycleWriter | None,
    persist: bool = True,
) -> dict[str, Any]:
    state_persisted = False
    safe_message = _safe_error_message(code, message)
    if persist and lifecycle_writer is not None:
        try:
            lifecycle_writer.mark_failed(
                context=context,
                prepare_id=prepare_id,
                code=code,
                message=safe_message,
            )
            state_persisted = True
        except Exception:
            state_persisted = False
    return {
        **base,
        "status": "failed",
        "stage": "worldline_prepare",
        "module_key": WORLDLINE_PREPARE_MODULE_KEY,
        "prepare_id": prepare_id,
        "error": {"code": code, "message": safe_message},
        "workflow_state_persisted": state_persisted,
    }


def _validate_resolution(resolution: ModuleBindingResolution) -> None:
    if resolution.module_key != WORLDLINE_PREPARE_MODULE_KEY:
        raise LLMFacilityError(
            "LLM_MODULE_UNBOUND",
            "resolved module key does not match worldline_agent_prepare",
        )
    if not resolution.supports_json:
        raise LLMFacilityError(
            "LLM_MODULE_CAPABILITY_MISSING",
            "worldline_agent_prepare requires a JSON-capable model",
        )
    for field_name in ("channel_id", "model_id", "provider", "base_url", "credential_ref"):
        value = getattr(resolution, field_name)
        if not isinstance(value, str) or not value.strip():
            raise LLMFacilityError("LLM_PROVIDER_ERROR", f"resolved LLM module is missing {field_name}")


def _prepare_messages(
    *,
    context: AgentContext,
    prepare_id: str,
    goal_summary: str,
    selected_agents: list[dict[str, Any]],
    selected_sources: list[dict[str, Any]],
) -> list[dict[str, str]]:
    return [
        {
            "role": "system",
            "content": (
                "You prepare character and organization dossiers for a single current-world simulation. "
                "Return one JSON object with prepared_agents. Return exactly one item for every selected agent, "
                "preserve its selection_ref as source_ref, and include display_name, role, and public_profile.summary. "
                "You may reason about private_profile and runtime_seed_state internally, but never place those fields "
                "inside public_profile. Do not create sessions, canon events, saved paths, drafts, or manuscripts."
            ),
        },
        {
            "role": "user",
            "content": json.dumps(
                {
                    "tenant_id": context.tenant_id,
                    "project_id": context.project_id,
                    "run_id": context.run_id,
                    "prepare_id": prepare_id,
                    "goal_summary": goal_summary,
                    "selected_agents": _public_records(selected_agents),
                    "selected_sources": _public_records(selected_sources),
                },
                ensure_ascii=False,
                separators=(",", ":"),
            ),
        },
    ]


def _prepared_agents(value: Any, *, selected_agents: list[dict[str, Any]]) -> list[dict[str, Any]]:
    if not isinstance(value, list) or not value:
        raise LLMFacilityError("SCHEMA_VALIDATION_FAILED", "prepared_agents must be a non-empty array")
    selected = {str(item["selection_ref"]): item for item in selected_agents}
    prepared: dict[str, dict[str, Any]] = {}
    for item in value:
        if not isinstance(item, dict):
            raise LLMFacilityError("SCHEMA_VALIDATION_FAILED", "prepared_agents items must be objects")
        selection_ref = _optional_text(item.get("source_ref"))
        if not selection_ref:
            source_kind = _optional_text(item.get("source_kind")).lower()
            source_id = _optional_text(item.get("source_id"))
            selection_ref = f"{source_kind}:{source_id}" if source_kind and source_id else ""
        source = selected.get(selection_ref)
        if source is None or selection_ref in prepared:
            raise LLMFacilityError(
                "SCHEMA_VALIDATION_FAILED",
                "prepared agent source_ref must uniquely match a selected agent",
            )
        public_profile = item.get("public_profile") if isinstance(item.get("public_profile"), dict) else {}
        summary = _optional_text(public_profile.get("summary")) or _optional_text(item.get("summary"))
        if not summary:
            raise LLMFacilityError("SCHEMA_VALIDATION_FAILED", "prepared agent public summary is required")
        prepared[selection_ref] = {
            "selection_ref": selection_ref,
            "source_kind": source["source_kind"],
            "source_id": source["source_id"],
            "source_asset_id": source.get("source_asset_id"),
            "display_name": _optional_text(item.get("display_name")) or _optional_text(source.get("display_name")),
            "role": _optional_text(item.get("role")) or _optional_text(source.get("role")),
            "summary": summary,
        }
    if set(prepared) != set(selected):
        raise LLMFacilityError(
            "SCHEMA_VALIDATION_FAILED",
            "prepared_agents must cover every selected agent exactly once",
        )
    return [prepared[str(item["selection_ref"])] for item in selected_agents]


def _selection_refs(
    options: dict[str, Any],
    *,
    keys: tuple[str, ...],
    allowed: set[str],
) -> list[dict[str, str]]:
    raw: Any = None
    for key in keys:
        if key in options:
            raw = options[key]
            break
    if raw is None:
        return []
    if not isinstance(raw, list):
        raise LLMFacilityError("WORLDLINE_PREPARATION_SELECTION_INVALID", f"{keys[0]} must be an array")
    refs: list[dict[str, str]] = []
    for item in raw:
        if not isinstance(item, dict):
            raise LLMFacilityError("WORLDLINE_PREPARATION_SELECTION_INVALID", "selection refs must be objects")
        source_kind = _optional_text(item.get("source_kind") or item.get("kind")).lower()
        source_id = _optional_text(item.get("source_id") or item.get("asset_id") or item.get("entity_id"))
        if source_kind == "event":
            source_kind = "worldline_event"
        if source_kind not in allowed:
            raise LLMFacilityError("WORLDLINE_PREPARATION_SELECTION_INVALID", "selection ref kind is unsupported")
        refs.append({"source_kind": source_kind, "source_id": _required_uuid(source_id, "source_id")})
    return _dedupe_refs(refs)


def _dedupe_refs(refs: list[dict[str, str]]) -> list[dict[str, str]]:
    result: list[dict[str, str]] = []
    seen: set[str] = set()
    for ref in refs:
        key = _selection_key(ref)
        if key in seen:
            continue
        seen.add(key)
        result.append(ref)
    return result


def _selection_key(ref: dict[str, str]) -> str:
    return f"{ref['source_kind']}:{ref['source_id']}"


def _public_records(value: Any) -> list[dict[str, Any]]:
    if not isinstance(value, list):
        return []
    result: list[dict[str, Any]] = []
    for item in value:
        sanitized = _sanitize(item)
        if isinstance(sanitized, dict) and sanitized:
            result.append(sanitized)
    return result


def _public_result(value: dict[str, Any]) -> dict[str, Any]:
    sanitized = _sanitize(value)
    return {
        key: sanitized[key]
        for key in ("prepare_id", "prepared_agent_count", "model_id", "reused")
        if key in sanitized and sanitized[key] is not None
    }


def _sanitize(value: Any) -> Any:
    if isinstance(value, dict):
        return {
            str(key): _sanitize(item)
            for key, item in value.items()
            if str(key).strip().lower() not in _SENSITIVE_KEYS
        }
    if isinstance(value, list):
        return [_sanitize(item) for item in value]
    return value


def _json_object(value: Any) -> dict[str, Any]:
    if isinstance(value, dict):
        return value
    if isinstance(value, str):
        try:
            decoded = json.loads(value)
        except json.JSONDecodeError as exc:
            raise LLMFacilityError(
                "WORLDLINE_PREPARATION_SELECTION_INVALID",
                "persisted worldline preparation options are invalid",
            ) from exc
        if isinstance(decoded, dict):
            return decoded
    raise LLMFacilityError(
        "WORLDLINE_PREPARATION_SELECTION_INVALID",
        "persisted worldline preparation options must be an object",
    )


def _prepared_agent_id(prepare_id: str, selection_ref: str) -> str:
    return str(uuid5(NAMESPACE_URL, f"mirofish:worldline-prepare:{prepare_id}:{selection_ref}"))


def _required_uuid(value: Any, field_name: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise LLMFacilityError("VALIDATION_FAILED", f"{field_name} must be a valid UUID")
    try:
        return str(UUID(value.strip()))
    except ValueError as exc:
        raise LLMFacilityError("VALIDATION_FAILED", f"{field_name} must be a valid UUID") from exc


def _optional_text(value: Any) -> str:
    return value.strip() if isinstance(value, str) else ""


def _row_get(row: Any, key: str, index: int = 0) -> Any:
    if row is None:
        return None
    if isinstance(row, dict):
        return row.get(key)
    return row[index]


def _row_text(row: Any, key: str, index: int = 0) -> str:
    return _optional_text(_row_get(row, key, index))


def _positive_int(value: Any) -> int:
    if isinstance(value, bool):
        return 0
    if isinstance(value, int) and value > 0:
        return value
    if isinstance(value, str) and value.isdigit() and int(value) > 0:
        return int(value)
    return 0


def _failed(code: str, message: str) -> dict[str, Any]:
    return {"status": "failed", "error": {"code": code, "message": _safe_error_message(code, message)}}


def _safe_error_message(code: str, message: str) -> str:
    stable = {
        "LLM_PROVIDER_ERROR": "worldline prepare provider call failed",
        "WORLDLINE_PREPARED_AGENT_WRITE_FAILED": "worldline prepared agent write failed",
        "WORLDLINE_PREPARATION_SOURCE_LOAD_FAILED": "worldline preparation source load failed",
        "WORLDLINE_PREPARATION_STATUS_WRITE_FAILED": "worldline preparation status write failed",
        "WORLDLINE_PREPARE_FAILED": "worldline prepare runner failed",
    }
    return stable.get(code, _optional_text(message) or "worldline preparation failed")


def _rollback(connection: Any) -> None:
    try:
        connection.rollback()
    except Exception:
        return


def _latency_ms(started_at: float) -> int:
    return max(0, int((time.monotonic() - started_at) * 1000))


def _llm_usage(response: dict[str, Any]) -> dict[str, int | float | None]:
    usage = response.get("__llm_usage")
    if not isinstance(usage, dict):
        return {"prompt_tokens": None, "completion_tokens": None, "total_tokens": None, "cost_estimate": None}
    return {
        "prompt_tokens": _non_negative_int(usage.get("prompt_tokens")),
        "completion_tokens": _non_negative_int(usage.get("completion_tokens")),
        "total_tokens": _non_negative_int(usage.get("total_tokens")),
        "cost_estimate": _non_negative_number(usage.get("cost_estimate")),
    }


def _non_negative_int(value: Any) -> int | None:
    if isinstance(value, bool):
        return None
    if isinstance(value, int) and value >= 0:
        return value
    return None


def _non_negative_number(value: Any) -> float | None:
    if isinstance(value, bool):
        return None
    if isinstance(value, (int, float)) and value >= 0:
        return float(value)
    return None


def _record_completed_telemetry(
    writer: Any | None,
    *,
    context: AgentContext,
    resolution: ModuleBindingResolution,
    usage: dict[str, int | float | None],
    latency_ms: int,
) -> None:
    if writer is None:
        return
    prompt_tokens = usage.get("prompt_tokens")
    completion_tokens = usage.get("completion_tokens")
    total_tokens = usage.get("total_tokens")
    quantity = total_tokens if isinstance(total_tokens, int) else (
        (prompt_tokens if isinstance(prompt_tokens, int) else 0)
        + (completion_tokens if isinstance(completion_tokens, int) else 0)
    )
    try:
        atomic = getattr(writer, "record_completed_llm_call", None)
        if callable(atomic):
            atomic(
                context=context,
                module_key=resolution.module_key,
                channel_id=resolution.channel_id,
                model_id=resolution.model_id,
                provider=resolution.provider,
                prompt_tokens=prompt_tokens if isinstance(prompt_tokens, int) else None,
                completion_tokens=completion_tokens if isinstance(completion_tokens, int) else None,
                total_tokens=total_tokens if isinstance(total_tokens, int) else None,
                latency_ms=latency_ms,
                cost_estimate=usage.get("cost_estimate"),
                usage_quantity=quantity,
            )
            return
        writer.record_llm_activity(
            context=context,
            module_key=resolution.module_key,
            channel_id=resolution.channel_id,
            model_id=resolution.model_id,
            status="completed",
            prompt_tokens=prompt_tokens,
            completion_tokens=completion_tokens,
            latency_ms=latency_ms,
            cost_estimate=usage.get("cost_estimate"),
            error=None,
        )
    except LLMFacilityError:
        raise
    except Exception as exc:
        raise LLMFacilityError(
            "LLM_TELEMETRY_WRITE_FAILED",
            "worldline prepare telemetry write failed",
        ) from exc


def _record_failed_telemetry(
    writer: Any | None,
    *,
    context: AgentContext,
    resolution: ModuleBindingResolution,
    code: str,
    message: str,
    latency_ms: int,
) -> None:
    if writer is None:
        return
    try:
        writer.record_llm_activity(
            context=context,
            module_key=resolution.module_key,
            channel_id=resolution.channel_id,
            model_id=resolution.model_id,
            status="failed",
            latency_ms=latency_ms,
            error={"code": code, "message": _safe_error_message(code, message)},
        )
    except LLMFacilityError:
        raise
    except Exception as exc:
        raise LLMFacilityError(
            "LLM_TELEMETRY_WRITE_FAILED",
            "worldline prepare telemetry write failed",
        ) from exc
