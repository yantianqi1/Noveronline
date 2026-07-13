from __future__ import annotations

import json
import os
import time
from uuid import UUID
from datetime import timedelta
from typing import Any, Callable, Protocol

from temporalio import activity, workflow

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
from mirofish_agents.temporal.worldline_prepare import (
    LLMFacilityWorldlinePrepareRunner,
    PostgresWorldlinePrepareLifecycleWriter,
    PostgresWorldlinePrepareScopeStore,
    WORLDLINE_PREPARE_MODULE_KEY,
    WORLDLINE_PREPARE_WORKFLOW_TYPE,
    WorldlinePrepareWorkflow,
    run_worldline_prepare_workflow_locally,
    worldline_prepare_activity,
)


WORLDLINE_TASK_QUEUE = "worldline-interactive"
WORLDLINE_STEP_WORKFLOW_TYPE = "worldline_step"
WORLDLINE_AUTO_EVOLUTION_WORKFLOW_TYPE = "worldline_auto_evolution"
WORLDLINE_STEP_MODULE_KEY = "worldline_director"
SENSITIVE_WORLDLINE_KEYS = {
    "api_key",
    "body",
    "body_text",
    "canon_body",
    "content",
    "content_text",
    "credential_ref",
    "draft",
    "encrypted_api_key",
    "event_body",
    "manuscript",
    "private_profile",
    "prompt",
    "raw_content",
    "raw_text",
    "response",
    "source_material",
    "source_text",
    "text",
}


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
        session_id: str,
        code: str,
        message: str,
    ) -> None:
        ...


class WorldlineStepRunner(Protocol):
    def run_step(
        self,
        *,
        context: AgentContext,
        session_id: str,
        mode: str,
        options: dict[str, Any],
    ) -> dict[str, Any]:
        ...


class WorldlineCandidateEventWriter(Protocol):
    def write_candidate_events(
        self,
        *,
        context: AgentContext,
        session_id: str,
        source_run_id: str,
        model_id: str | None,
        mode: str,
        events: list[dict[str, Any]],
        source_step_index: int = 1,
        workflow_type: str = WORLDLINE_STEP_WORKFLOW_TYPE,
    ) -> dict[str, Any]:
        ...


class WorldlineSourceLoader(Protocol):
    def load_sources(
        self,
        *,
        context: AgentContext,
        session_id: str,
        source_refs: list[dict[str, Any]],
    ) -> list[dict[str, Any]]:
        ...


class LLMTelemetryWriter(Protocol):
    def record_llm_activity(
        self,
        *,
        context: AgentContext,
        module_key: str,
        channel_id: str,
        model_id: str,
        status: str,
        prompt_tokens: int | None = None,
        completion_tokens: int | None = None,
        latency_ms: int | None = None,
        cost_estimate: float | None = None,
        error: dict[str, Any] | None = None,
    ) -> None:
        ...

    def record_usage_event(
        self,
        *,
        context: AgentContext,
        module_key: str,
        usage_type: str,
        quantity: int,
        unit: str,
        metadata: dict[str, Any],
    ) -> None:
        ...


class LLMFacilityWorldlineStepRunner:
    def __init__(
        self,
        *,
        binding_resolver: ModuleBindingResolver,
        credential_provider: CredentialProvider,
        chat_client: JSONChatClient,
        candidate_event_writer: WorldlineCandidateEventWriter,
        telemetry_writer: LLMTelemetryWriter | None = None,
        source_loader: WorldlineSourceLoader | None = None,
    ) -> None:
        self._binding_resolver = binding_resolver
        self._credential_provider = credential_provider
        self._chat_client = chat_client
        self._candidate_event_writer = candidate_event_writer
        self._telemetry_writer = telemetry_writer
        self._source_loader = source_loader

    def run_step(
        self,
        *,
        context: AgentContext,
        session_id: str,
        mode: str,
        options: dict[str, Any],
    ) -> dict[str, Any]:
        started_at = time.monotonic()
        resolution: ModuleBindingResolution | None = None
        completed_telemetry_recorded = False
        try:
            source_run_id = _required_uuid_text(context.run_id, "run_id")
            source_step_index = (
                _source_step_index(options)
                if context.workflow_type == WORLDLINE_AUTO_EVOLUTION_WORKFLOW_TYPE
                else 1
            )
            runtime_options = dict(options)
            if context.workflow_type != WORLDLINE_AUTO_EVOLUTION_WORKFLOW_TYPE:
                runtime_options.pop("source_step_index", None)
            replayed = _read_candidate_replay(
                self._candidate_event_writer,
                context=context,
                session_id=session_id,
                source_run_id=source_run_id,
                source_step_index=source_step_index,
                workflow_type=context.workflow_type,
            )
            if replayed is not None:
                replay_result = {
                    "status": "completed",
                    "module_key": WORLDLINE_STEP_MODULE_KEY,
                    "model_id": replayed.get("model_id"),
                    "session_id": session_id,
                    "mode": mode,
                    "candidate_event_count": replayed["candidate_event_count"],
                    "step": replayed["step"],
                }
                if context.workflow_type == WORLDLINE_AUTO_EVOLUTION_WORKFLOW_TYPE:
                    replay_result.update(source_step_index=source_step_index, replayed=True)
                return replay_result
            source_refs = _source_refs(runtime_options)
            source_summaries = self._load_source_summaries(
                context=context,
                session_id=session_id,
                source_refs=source_refs,
            )
            resolution = self._binding_resolver.resolve_module_binding(
                context=context,
                module_key=WORLDLINE_STEP_MODULE_KEY,
            )
            _validate_worldline_resolution(resolution)
            api_key = self._credential_provider.resolve_api_key(
                context=context,
                credential_ref=resolution.credential_ref,
            )
            if not isinstance(api_key, str) or not api_key.strip():
                raise LLMFacilityError("LLM_CREDENTIAL_UNAVAILABLE", "resolved credential was empty")
            response_json = self._chat_client.complete_json(
                context=context,
                resolution=resolution,
                api_key=api_key.strip(),
                messages=_worldline_step_messages(
                    context=context,
                    session_id=session_id,
                    mode=mode,
                    options=runtime_options,
                    source_summaries=source_summaries,
                ),
            )
            usage = _llm_usage_from_response(response_json)
            requested_step = _step_number(runtime_options)
            candidate_events = [
                _candidate_event(candidate, step=requested_step)
                for candidate in _candidate_event_list(response_json.get("candidate_events"))
            ]
            _record_completed_llm_telemetry(
                self._telemetry_writer,
                context=context,
                resolution=resolution,
                usage=usage,
                latency_ms=_latency_ms(started_at),
            )
            completed_telemetry_recorded = True
            try:
                writer_args = {
                    "context": context,
                    "session_id": session_id,
                    "source_run_id": source_run_id,
                    "model_id": resolution.model_id,
                    "mode": mode,
                    "events": candidate_events,
                }
                if context.workflow_type == WORLDLINE_AUTO_EVOLUTION_WORKFLOW_TYPE:
                    writer_args.update(
                        source_step_index=source_step_index,
                        workflow_type=context.workflow_type,
                    )
                persisted = self._candidate_event_writer.write_candidate_events(**writer_args)
            except LLMFacilityError:
                raise
            except Exception as exc:
                raise LLMFacilityError(
                    "WORLDLINE_CANDIDATE_EVENT_WRITE_FAILED",
                    "worldline candidate event write failed",
                ) from exc
        except LLMFacilityError as exc:
            if resolution is not None and not completed_telemetry_recorded and exc.code != "LLM_TELEMETRY_WRITE_FAILED":
                try:
                    _record_failed_llm_telemetry(
                        self._telemetry_writer,
                        context=context,
                        resolution=resolution,
                        code=exc.code,
                        message=exc.message,
                        latency_ms=_latency_ms(started_at),
                    )
                except LLMFacilityError as telemetry_exc:
                    return _runner_failed(telemetry_exc.code, telemetry_exc.message)
            return _runner_failed(exc.code, exc.message)
        except Exception:
            if resolution is not None:
                try:
                    _record_failed_llm_telemetry(
                        self._telemetry_writer,
                        context=context,
                        resolution=resolution,
                        code="LLM_PROVIDER_ERROR",
                        message="worldline provider call failed",
                        latency_ms=_latency_ms(started_at),
                    )
                except LLMFacilityError as telemetry_exc:
                    return _runner_failed(telemetry_exc.code, telemetry_exc.message)
            return _runner_failed("LLM_PROVIDER_ERROR", "worldline provider call failed")

        step = _positive_int(persisted.get("step"), default=requested_step)
        public_result = {
            "status": "completed",
            "module_key": WORLDLINE_STEP_MODULE_KEY,
            "model_id": resolution.model_id,
            "session_id": session_id,
            "mode": mode,
            "candidate_event_count": persisted.get("candidate_event_count", len(candidate_events)),
            "step": step,
        }
        if context.workflow_type == WORLDLINE_AUTO_EVOLUTION_WORKFLOW_TYPE:
            public_result["source_step_index"] = source_step_index
            public_result["replayed"] = bool(persisted.get("replayed"))
        return public_result

    def _load_source_summaries(
        self,
        *,
        context: AgentContext,
        session_id: str,
        source_refs: list[dict[str, Any]],
    ) -> list[dict[str, Any]]:
        if not source_refs:
            return []
        if self._source_loader is None:
            raise LLMFacilityError(
                "WORLDLINE_SOURCE_LOADER_UNCONFIGURED",
                "worldline source loader is required when source_refs are provided",
            )
        try:
            loaded = self._source_loader.load_sources(
                context=context,
                session_id=session_id,
                source_refs=source_refs,
            )
        except LLMFacilityError:
            raise
        except Exception as exc:
            raise LLMFacilityError(
                "WORLDLINE_SOURCE_LOAD_FAILED",
                "worldline source load failed",
            ) from exc
        summaries = _source_summaries(loaded)
        if not summaries:
            raise LLMFacilityError(
                "WORLDLINE_SOURCE_NOT_FOUND",
                "worldline source_refs did not resolve to public summaries",
            )
        return summaries


class PostgresWorldlineCandidateEventWriter:
    def __init__(self, *, connect: Callable[[], Any]) -> None:
        self._connect = connect

    @classmethod
    def from_database_url(cls, database_url: str) -> "PostgresWorldlineCandidateEventWriter":
        try:
            import psycopg
        except ImportError as exc:  # pragma: no cover - depends on optional runtime packaging
            raise RuntimeError("psycopg is required for DATABASE_URL worldline candidate event writes") from exc

        return cls(connect=lambda: psycopg.connect(database_url))

    def read_candidate_events(
        self,
        *,
        context: AgentContext,
        session_id: str,
        source_run_id: str,
        source_step_index: int = 1,
        workflow_type: str = WORLDLINE_STEP_WORKFLOW_TYPE,
    ) -> dict[str, Any] | None:
        if not context.project_id:
            raise LLMFacilityError("VALIDATION_FAILED", "project_id is required to read worldline candidate events")
        normalized_session_id = _required_text(session_id, "session_id")
        normalized_source_run_id = _required_uuid_text(source_run_id, "source_run_id")
        normalized_source_step_index = _required_positive_int(source_step_index, "source_step_index")
        normalized_workflow_type = _worldline_runtime_workflow_type(workflow_type)
        connection = self._connect()
        try:
            set_postgres_tenant_context(connection, context=context)
            with connection.cursor() as cursor:
                cursor.execute(
                    """SELECT COUNT(*)::int AS event_count,
                              COALESCE(MIN(step), 0)::int AS min_step,
                              COALESCE(MAX(step), 0)::int AS max_step,
                              MAX(NULLIF(state_changes_jsonb->>'model_id', '')) AS model_id
                         FROM worldline_events
                        WHERE tenant_id = %s
                          AND project_id = %s
                          AND session_id = %s
                          AND source_run_id = %s
                          AND (
                            %s = 'worldline_step'
                            OR state_changes_jsonb->>'source_step_index' = %s
                          )""",
                    (
                        context.tenant_id,
                        context.project_id,
                        normalized_session_id,
                        normalized_source_run_id,
                        normalized_workflow_type,
                        str(normalized_source_step_index),
                    ),
                )
                row = cursor.fetchone()
        except LLMFacilityError:
            _rollback_quietly(connection)
            raise
        except Exception as exc:
            _rollback_quietly(connection)
            raise LLMFacilityError(
                "WORLDLINE_CANDIDATE_EVENT_READ_FAILED",
                "worldline candidate event replay read failed",
            ) from exc
        finally:
            connection.close()
        event_count = _count_value(_row_value(row, "event_count", 0))
        if event_count == 0:
            return None
        min_step = _count_value(_row_value(row, "min_step", 1))
        max_step = _count_value(_row_value(row, "max_step", 2))
        if min_step < 1 or min_step != max_step:
            raise LLMFacilityError(
                "WORLDLINE_STEP_STATE_INVALID",
                "worldline step candidate state is inconsistent",
            )
        return {
            "candidate_event_count": event_count,
            "step": min_step,
            "model_id": _optional_text(_row_value(row, "model_id", 3)) or None,
            "source_step_index": normalized_source_step_index,
            "replayed": True,
        }

    def write_candidate_events(
        self,
        *,
        context: AgentContext,
        session_id: str,
        source_run_id: str,
        model_id: str | None,
        mode: str,
        events: list[dict[str, Any]],
        source_step_index: int = 1,
        workflow_type: str = WORLDLINE_STEP_WORKFLOW_TYPE,
    ) -> dict[str, Any]:
        if not context.project_id:
            raise LLMFacilityError("VALIDATION_FAILED", "project_id is required to write worldline candidate events")
        normalized_session_id = _required_text(session_id, "session_id")
        normalized_source_run_id = _required_uuid_text(source_run_id, "source_run_id")
        normalized_source_step_index = _required_positive_int(source_step_index, "source_step_index")
        normalized_workflow_type = _worldline_runtime_workflow_type(workflow_type)
        normalized_events = [_candidate_event(event, step=_step_from_event(event)) for event in events]
        connection = self._connect()
        try:
            set_postgres_tenant_context(connection, context=context)
            with connection.cursor() as cursor:
                step, existing_count = self._lock_and_resolve_step(
                    cursor,
                    context=context,
                    session_id=normalized_session_id,
                    source_run_id=normalized_source_run_id,
                    source_step_index=normalized_source_step_index,
                    workflow_type=normalized_workflow_type,
                )
                if existing_count > 0:
                    connection.commit()
                    replayed_result = {
                        "status": "completed",
                        "candidate_event_count": existing_count,
                        "step": step,
                    }
                    if normalized_workflow_type == WORLDLINE_AUTO_EVOLUTION_WORKFLOW_TYPE:
                        replayed_result.update(
                            source_step_index=normalized_source_step_index,
                            replayed=True,
                        )
                    return replayed_result
                for event in normalized_events:
                    cursor.execute(
                        """INSERT INTO worldline_events (
                             tenant_id, session_id, project_id, step, title, summary, kind,
                             status, lifecycle, confidence, involved_agent_ids_jsonb,
                             state_changes_jsonb, source_run_id, created_by
                           )
                           SELECT
                             worldline_sessions.tenant_id,
                             worldline_sessions.session_id,
                             worldline_sessions.project_id,
                             %s, %s, %s, %s,
                             'candidate', 'simulation', %s, %s::jsonb,
                             %s::jsonb, %s, %s
                           FROM worldline_sessions
                           WHERE worldline_sessions.tenant_id = %s
                             AND worldline_sessions.project_id = %s
                             AND worldline_sessions.session_id = %s
                           RETURNING event_id""",
                        (
                            step,
                            event["title"],
                            event["summary"],
                            event["kind"],
                            event.get("confidence"),
                            json.dumps(event["involved_agent_ids"], ensure_ascii=False, separators=(",", ":")),
                            json.dumps(
                                _state_changes_payload(
                                    event=event,
                                    model_id=model_id,
                                    mode=mode,
                                    source_step_index=normalized_source_step_index,
                                    workflow_type=normalized_workflow_type,
                                ),
                                ensure_ascii=False,
                                separators=(",", ":"),
                            ),
                            normalized_source_run_id,
                            _uuid_or_none(context.actor_user_id),
                            context.tenant_id,
                            context.project_id,
                            normalized_session_id,
                        ),
                    )
                    if cursor.fetchone() is None:
                        raise LLMFacilityError(
                            "WORLDLINE_SESSION_NOT_FOUND",
                            "worldline session was not admitted for this tenant/project",
                        )
            connection.commit()
        except LLMFacilityError:
            _rollback_quietly(connection)
            raise
        except Exception as exc:
            _rollback_quietly(connection)
            raise LLMFacilityError(
                "WORLDLINE_CANDIDATE_EVENT_WRITE_FAILED",
                "worldline candidate event write failed",
            ) from exc
        finally:
            connection.close()
        result = {
            "status": "completed",
            "candidate_event_count": len(normalized_events),
            "step": step,
        }
        if normalized_workflow_type == WORLDLINE_AUTO_EVOLUTION_WORKFLOW_TYPE:
            result.update(source_step_index=normalized_source_step_index, replayed=False)
        return result

    @staticmethod
    def _lock_and_resolve_step(
        cursor: Any,
        *,
        context: AgentContext,
        session_id: str,
        source_run_id: str,
        source_step_index: int,
        workflow_type: str,
    ) -> tuple[int, int]:
        cursor.execute(
            """SELECT status
                 FROM worldline_sessions
                WHERE tenant_id = %s
                  AND project_id = %s
                  AND session_id = %s
                FOR UPDATE""",
            (context.tenant_id, context.project_id, session_id),
        )
        if cursor.fetchone() is None:
            raise LLMFacilityError(
                "WORLDLINE_SESSION_NOT_FOUND",
                "worldline session was not admitted for this tenant/project",
            )
        cursor.execute(
            """SELECT COUNT(*)::int AS event_count,
                      COALESCE(MIN(step), 0)::int AS min_step,
                      COALESCE(MAX(step), 0)::int AS max_step
                 FROM worldline_events
                WHERE tenant_id = %s
                  AND project_id = %s
                  AND session_id = %s
                  AND source_run_id = %s
                  AND (
                    %s = 'worldline_step'
                    OR state_changes_jsonb->>'source_step_index' = %s
                  )""",
            (
                context.tenant_id,
                context.project_id,
                session_id,
                source_run_id,
                workflow_type,
                str(source_step_index),
            ),
        )
        existing = cursor.fetchone()
        existing_count = _count_value(_row_value(existing, "event_count", 0))
        min_step = _count_value(_row_value(existing, "min_step", 1))
        max_step = _count_value(_row_value(existing, "max_step", 2))
        if existing_count > 0:
            if min_step < 1 or min_step != max_step:
                raise LLMFacilityError(
                    "WORLDLINE_STEP_STATE_INVALID",
                    "worldline step candidate state is inconsistent",
                )
            return min_step, existing_count
        cursor.execute(
            """SELECT 1
                 FROM workflow_runs AS workflow_run
                 JOIN workflow_events AS queued_event
                   ON queued_event.tenant_id = workflow_run.tenant_id
                  AND queued_event.run_id = workflow_run.run_id
                  AND queued_event.workflow_type = workflow_run.workflow_type
                WHERE workflow_run.tenant_id = %s
                  AND workflow_run.project_id = %s
                  AND workflow_run.run_id = %s
                  AND workflow_run.workflow_type = %s
                  AND workflow_run.status IN ('queued', 'running')
                  AND queued_event.event_type = 'workflow.queued'
                  AND queued_event.payload_jsonb->>'session_id' = %s
                LIMIT 1""",
            (context.tenant_id, context.project_id, source_run_id, workflow_type, session_id),
        )
        if cursor.fetchone() is None:
            raise LLMFacilityError(
                _inactive_worldline_workflow_code(workflow_type),
                _inactive_worldline_workflow_message(workflow_type),
            )
        cursor.execute(
            """SELECT COALESCE(MAX(step), 0)::int + 1 AS next_step
                 FROM worldline_events
                WHERE tenant_id = %s
                  AND project_id = %s
                  AND session_id = %s""",
            (context.tenant_id, context.project_id, session_id),
        )
        next_step = _count_value(_row_value(cursor.fetchone(), "next_step", 0))
        if next_step < 1:
            raise LLMFacilityError(
                "WORLDLINE_STEP_STATE_INVALID",
                "worldline step could not be allocated",
            )
        return next_step, 0


class PostgresWorldlineSourceLoader:
    def __init__(self, *, connect: Callable[[], Any]) -> None:
        self._connect = connect

    @classmethod
    def from_database_url(cls, database_url: str) -> "PostgresWorldlineSourceLoader":
        try:
            import psycopg
            from psycopg.rows import dict_row
        except ImportError as exc:  # pragma: no cover - depends on optional runtime packaging
            raise RuntimeError("psycopg is required for DATABASE_URL worldline source loading") from exc

        return cls(connect=lambda: psycopg.connect(database_url, row_factory=dict_row))

    def load_sources(
        self,
        *,
        context: AgentContext,
        session_id: str,
        source_refs: list[dict[str, Any]],
    ) -> list[dict[str, Any]]:
        if not context.project_id:
            raise LLMFacilityError("VALIDATION_FAILED", "project_id is required to load worldline sources")
        normalized_session_id = _required_text(session_id, "session_id")
        asset_ids, event_ids = _worldline_source_ref_ids(source_refs)
        if not asset_ids and not event_ids:
            raise LLMFacilityError("WORLDLINE_SOURCE_REF_INVALID", "worldline source_refs did not include supported references")

        connection = self._connect()
        try:
            set_postgres_tenant_context(connection, context=context)
            summaries: list[dict[str, Any]] = []
            with connection.cursor() as cursor:
                if asset_ids:
                    cursor.execute(
                        """SELECT
                             'asset' AS source_kind,
                             asset_id::text AS source_ref,
                             title,
                             summary,
                             asset_type,
                             category
                           FROM assets
                           WHERE tenant_id = %s
                             AND project_id = %s
                             AND enabled = true
                             AND asset_id::text = ANY(%s)""",
                        (
                            context.tenant_id,
                            context.project_id,
                            asset_ids,
                        ),
                    )
                    summaries.extend(_public_source_summaries(cursor.fetchall()))
                if event_ids:
                    cursor.execute(
                        """SELECT
                             'worldline_event' AS source_kind,
                             worldline_events.event_id::text AS source_ref,
                             worldline_events.title,
                             worldline_events.summary,
                             worldline_events.kind,
                             worldline_events.status
                           FROM worldline_events
                           JOIN worldline_sessions
                             ON worldline_sessions.tenant_id = worldline_events.tenant_id
                            AND worldline_sessions.project_id = worldline_events.project_id
                            AND worldline_sessions.session_id = worldline_events.session_id
                           WHERE worldline_sessions.tenant_id = %s
                             AND worldline_sessions.project_id = %s
                             AND worldline_sessions.session_id = %s
                             AND worldline_events.event_id::text = ANY(%s)
                             AND worldline_events.status IN ('candidate', 'canon')""",
                        (
                            context.tenant_id,
                            context.project_id,
                            normalized_session_id,
                            event_ids,
                        ),
                    )
                    summaries.extend(_public_source_summaries(cursor.fetchall()))
        except LLMFacilityError:
            _rollback_quietly(connection)
            raise
        except Exception as exc:
            _rollback_quietly(connection)
            raise LLMFacilityError("WORLDLINE_SOURCE_LOAD_FAILED", "worldline source load failed") from exc
        finally:
            connection.close()
        return summaries


class PostgresLLMTelemetryWriter:
    def __init__(self, *, connect: Callable[[], Any]) -> None:
        self._connect = connect

    @classmethod
    def from_database_url(cls, database_url: str) -> "PostgresLLMTelemetryWriter":
        try:
            import psycopg
        except ImportError as exc:  # pragma: no cover - depends on optional runtime packaging
            raise RuntimeError("psycopg is required for DATABASE_URL worldline LLM telemetry writes") from exc

        return cls(connect=lambda: psycopg.connect(database_url))

    def record_llm_activity(
        self,
        *,
        context: AgentContext,
        module_key: str,
        channel_id: str,
        model_id: str,
        status: str,
        prompt_tokens: int | None = None,
        completion_tokens: int | None = None,
        latency_ms: int | None = None,
        cost_estimate: float | None = None,
        error: dict[str, Any] | None = None,
    ) -> None:
        connection = self._connect()
        try:
            set_postgres_tenant_context(connection, context=context)
            with connection.cursor() as cursor:
                cursor.execute(
                    """INSERT INTO llm_activity (
                         tenant_id, project_id, run_id, module_key, channel_id, model_id, status,
                         prompt_tokens, completion_tokens, latency_ms, cost_estimate, error_jsonb
                       ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s::jsonb)""",
                    (
                        context.tenant_id,
                        context.project_id,
                        context.run_id,
                        module_key,
                        channel_id,
                        model_id,
                        status,
                        prompt_tokens,
                        completion_tokens,
                        latency_ms,
                        cost_estimate,
                        json.dumps(
                            _sanitize_worldline_value(error),
                            ensure_ascii=False,
                            separators=(",", ":"),
                        )
                        if error
                        else None,
                    ),
                )
            connection.commit()
        except Exception as exc:
            _rollback_quietly(connection)
            raise LLMFacilityError("LLM_TELEMETRY_WRITE_FAILED", "worldline LLM activity write failed") from exc
        finally:
            connection.close()

    def record_usage_event(
        self,
        *,
        context: AgentContext,
        module_key: str,
        usage_type: str,
        quantity: int,
        unit: str,
        metadata: dict[str, Any],
    ) -> None:
        connection = self._connect()
        try:
            set_postgres_tenant_context(connection, context=context)
            with connection.cursor() as cursor:
                cursor.execute(
                    """INSERT INTO usage_events (
                         tenant_id, project_id, run_id, module_key, usage_type, quantity, unit, metadata_jsonb
                       ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s::jsonb)""",
                    (
                        context.tenant_id,
                        context.project_id,
                        context.run_id,
                        module_key,
                        usage_type,
                        quantity,
                        unit,
                        json.dumps(_sanitize_worldline_value(metadata), ensure_ascii=False, separators=(",", ":")),
                    ),
                )
            connection.commit()
        except Exception as exc:
            _rollback_quietly(connection)
            raise LLMFacilityError("LLM_TELEMETRY_WRITE_FAILED", "worldline usage event write failed") from exc
        finally:
            connection.close()

    def record_completed_llm_call(
        self,
        *,
        context: AgentContext,
        module_key: str,
        channel_id: str,
        model_id: str,
        provider: str,
        prompt_tokens: int | None = None,
        completion_tokens: int | None = None,
        total_tokens: int | None = None,
        latency_ms: int | None = None,
        cost_estimate: float | None = None,
        usage_quantity: int = 0,
    ) -> None:
        connection = self._connect()
        try:
            set_postgres_tenant_context(connection, context=context)
            with connection.cursor() as cursor:
                cursor.execute(
                    """INSERT INTO llm_activity (
                         tenant_id, project_id, run_id, module_key, channel_id, model_id, status,
                         prompt_tokens, completion_tokens, latency_ms, cost_estimate, error_jsonb
                       ) VALUES (%s, %s, %s, %s, %s, %s, 'completed', %s, %s, %s, %s, NULL::jsonb)""",
                    (
                        context.tenant_id,
                        context.project_id,
                        context.run_id,
                        module_key,
                        channel_id,
                        model_id,
                        prompt_tokens,
                        completion_tokens,
                        latency_ms,
                        cost_estimate,
                    ),
                )
                if usage_quantity > 0:
                    cursor.execute(
                        """INSERT INTO usage_events (
                             tenant_id, project_id, run_id, module_key, usage_type, quantity, unit, metadata_jsonb
                           ) VALUES (%s, %s, %s, %s, 'llm_tokens', %s, 'tokens', %s::jsonb)""",
                        (
                            context.tenant_id,
                            context.project_id,
                            context.run_id,
                            module_key,
                            usage_quantity,
                            json.dumps(
                                _sanitize_worldline_value(
                                    {
                                        "channel_id": channel_id,
                                        "model_id": model_id,
                                        "provider": provider,
                                        "prompt_tokens": prompt_tokens,
                                        "completion_tokens": completion_tokens,
                                        "total_tokens": total_tokens,
                                        "cost_estimate": cost_estimate,
                                    }
                                ),
                                ensure_ascii=False,
                                separators=(",", ":"),
                            ),
                        ),
                    )
            connection.commit()
        except Exception as exc:
            _rollback_quietly(connection)
            raise LLMFacilityError("LLM_TELEMETRY_WRITE_FAILED", "worldline completed telemetry write failed") from exc
        finally:
            connection.close()


class PostgresWorkflowEventWriter:
    def __init__(self, *, connect: Callable[[], Any]) -> None:
        self._connect = connect

    @classmethod
    def from_database_url(cls, database_url: str) -> "PostgresWorkflowEventWriter":
        try:
            import psycopg
        except ImportError as exc:  # pragma: no cover - depends on optional runtime packaging
            raise RuntimeError("psycopg is required for DATABASE_URL worldline event writes") from exc

        return cls(connect=lambda: psycopg.connect(database_url))

    def write_event(
        self,
        *,
        tenant_id: str,
        project_id: str | None,
        run_id: str,
        event_type: str,
        payload: dict[str, Any],
    ) -> None:
        sanitized_payload = _sanitize_worldline_value(payload)
        if event_type.startswith("worldline.auto_evolution."):
            self._write_auto_evolution_event(
                tenant_id=tenant_id,
                project_id=project_id,
                run_id=run_id,
                event_type=event_type,
                payload=sanitized_payload,
            )
            return
        connection = self._connect()
        missing_parent = False
        try:
            _set_postgres_tenant_context_for_ids(connection, tenant_id=tenant_id)
            with connection.cursor() as cursor:
                cursor.execute(
                    """WITH admitted_run AS (
                         SELECT tenant_id, project_id, run_id, workflow_type
                           FROM workflow_runs
                          WHERE tenant_id = %s
                            AND project_id = %s
                            AND run_id = %s
                            AND workflow_type = 'worldline_step'
                       )
                       INSERT INTO workflow_events (
                         tenant_id, run_id, workflow_type, project_id, event_type, sequence, payload_jsonb
                       )
                       SELECT
                         admitted_run.tenant_id,
                         admitted_run.run_id,
                         admitted_run.workflow_type,
                         admitted_run.project_id,
                         %s,
                         COALESCE((
                           SELECT MAX(sequence)
                             FROM workflow_events
                            WHERE tenant_id = admitted_run.tenant_id
                              AND run_id = admitted_run.run_id
                         ), 0) + 1,
                         %s::jsonb
                       FROM admitted_run
                       RETURNING event_id""",
                    (
                        tenant_id,
                        project_id,
                        run_id,
                        event_type,
                        json.dumps(sanitized_payload, ensure_ascii=False, separators=(",", ":")),
                    ),
                )
                missing_parent = cursor.fetchone() is None
            if missing_parent:
                _rollback_quietly(connection)
            else:
                connection.commit()
        except Exception as exc:
            if missing_parent:
                raise
            _rollback_quietly(connection)
            raise RuntimeError("WORKFLOW_EVENT_WRITE_FAILED: worldline workflow event write failed") from exc
        finally:
            connection.close()
        if missing_parent:
            raise RuntimeError("WORKFLOW_RUN_NOT_FOUND: worldline step admission parent row is missing")

    def _write_auto_evolution_event(
        self,
        *,
        tenant_id: str,
        project_id: str | None,
        run_id: str,
        event_type: str,
        payload: dict[str, Any],
    ) -> None:
        source_step_index = payload.get("source_step_index")
        identity = str(source_step_index) if isinstance(source_step_index, int) else None
        connection = self._connect()
        parent_count = 0
        event_count = 0
        try:
            _set_postgres_tenant_context_for_ids(connection, tenant_id=tenant_id)
            with connection.cursor() as cursor:
                cursor.execute(
                    """WITH admitted_run AS MATERIALIZED (
                         SELECT tenant_id, project_id, run_id, workflow_type
                           FROM workflow_runs
                          WHERE tenant_id = %s
                            AND project_id = %s
                            AND run_id = %s
                            AND workflow_type = 'worldline_auto_evolution'
                          FOR UPDATE
                       ),
                       existing_event AS MATERIALIZED (
                         SELECT 1
                           FROM workflow_events
                           JOIN admitted_run
                             ON admitted_run.tenant_id = workflow_events.tenant_id
                            AND admitted_run.run_id = workflow_events.run_id
                            AND admitted_run.workflow_type = workflow_events.workflow_type
                          WHERE workflow_events.event_type = %s
                            AND (
                              %s::text IS NULL
                              OR workflow_events.payload_jsonb->>'source_step_index' = %s::text
                            )
                       ),
                       event_insert AS (
                         INSERT INTO workflow_events (
                           tenant_id, run_id, workflow_type, project_id, event_type, sequence, payload_jsonb
                         )
                         SELECT
                           admitted_run.tenant_id,
                           admitted_run.run_id,
                           admitted_run.workflow_type,
                           admitted_run.project_id,
                           %s,
                           COALESCE((
                             SELECT MAX(sequence)
                               FROM workflow_events
                              WHERE tenant_id = admitted_run.tenant_id
                                AND run_id = admitted_run.run_id
                           ), 0) + 1,
                           %s::jsonb
                         FROM admitted_run
                         WHERE NOT EXISTS (SELECT 1 FROM existing_event)
                         RETURNING 1
                       )
                       SELECT
                         (SELECT COUNT(*)::int FROM admitted_run) AS parent_count,
                         ((SELECT COUNT(*)::int FROM existing_event) +
                          (SELECT COUNT(*)::int FROM event_insert)) AS event_count""",
                    (
                        tenant_id,
                        project_id,
                        run_id,
                        event_type,
                        identity,
                        identity,
                        event_type,
                        json.dumps(payload, ensure_ascii=False, separators=(",", ":")),
                    ),
                )
                row = cursor.fetchone()
                parent_count = _count_value(_row_value(row, "parent_count", 0))
                event_count = _count_value(_row_value(row, "event_count", 1))
            if parent_count != 1 or event_count != 1:
                _rollback_quietly(connection)
            else:
                connection.commit()
        except Exception as exc:
            _rollback_quietly(connection)
            raise RuntimeError(
                "WORKFLOW_EVENT_WRITE_FAILED: worldline auto-evolution workflow event write failed"
            ) from exc
        finally:
            connection.close()
        if parent_count != 1:
            raise RuntimeError(
                "WORKFLOW_RUN_NOT_FOUND: worldline auto-evolution admission parent row is missing"
            )
        if event_count != 1:
            raise RuntimeError(
                "WORKFLOW_EVENT_WRITE_FAILED: worldline auto-evolution workflow event state is inconsistent"
            )


class PostgresWorkflowRunStatusWriter:
    def __init__(self, *, connect: Callable[[], Any]) -> None:
        self._connect = connect

    @classmethod
    def from_database_url(cls, database_url: str) -> "PostgresWorkflowRunStatusWriter":
        try:
            import psycopg
            from psycopg.rows import dict_row
        except ImportError as exc:  # pragma: no cover - depends on optional runtime packaging
            raise RuntimeError("psycopg is required for DATABASE_URL worldline status writes") from exc

        return cls(connect=lambda: psycopg.connect(database_url, row_factory=dict_row))

    def mark_completed(
        self,
        *,
        context: AgentContext,
        result: dict[str, Any],
    ) -> None:
        self._update_status(
            context=context,
            status="completed",
            result=_public_status_result(result),
            code=None,
            message=None,
        )

    def mark_failed(
        self,
        *,
        context: AgentContext,
        session_id: str,
        code: str,
        message: str,
    ) -> None:
        self._update_status(
            context=context,
            session_id=session_id,
            status="failed",
            result=None,
            code=code,
            message=message,
        )

    def _update_status(
        self,
        *,
        context: AgentContext,
        session_id: str | None = None,
        status: str,
        result: dict[str, Any] | None,
        code: str | None,
        message: str | None,
    ) -> None:
        if not context.project_id:
            raise RuntimeError("WORKFLOW_RUN_NOT_FOUND: project_id is required to update worldline step status")
        normalized_session_id = _required_text(
            session_id if session_id is not None else (result or {}).get("session_id"),
            "session_id",
        )
        if context.workflow_type == WORLDLINE_AUTO_EVOLUTION_WORKFLOW_TYPE:
            self._update_auto_evolution_status(
                context=context,
                session_id=normalized_session_id,
                status=status,
                result=result,
                code=code,
                message=message,
            )
            return
        step = _positive_int((result or {}).get("step"), default=0)
        encoded_result = json.dumps(result, ensure_ascii=False, separators=(",", ":")) if result is not None else None
        connection = self._connect()
        missing_parent = False
        try:
            set_postgres_tenant_context(connection, context=context)
            with connection.cursor() as cursor:
                cursor.execute(
                    """WITH session_lock AS MATERIALIZED (
                         SELECT session_id
                           FROM worldline_sessions
                          WHERE tenant_id = %s
                            AND project_id = %s
                            AND session_id = %s
                          FOR UPDATE
                       ),
                       workflow_update AS (
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
                            AND workflow_type = 'worldline_step'
                            AND status IN ('queued', 'running')
                            AND EXISTS (SELECT 1 FROM session_lock)
                            AND EXISTS (
                              SELECT 1
                                FROM workflow_events AS queued_event
                               WHERE queued_event.tenant_id = workflow_runs.tenant_id
                                 AND queued_event.project_id = workflow_runs.project_id
                                 AND queued_event.run_id = workflow_runs.run_id
                                 AND queued_event.workflow_type = workflow_runs.workflow_type
                                 AND queued_event.event_type = 'workflow.queued'
                                 AND queued_event.payload_jsonb->>'session_id' = %s
                            )
                         RETURNING 1
                       ),
                       session_update AS (
                         UPDATE worldline_sessions
                            SET status = 'paused', updated_at = now()
                          WHERE tenant_id = %s
                            AND project_id = %s
                            AND session_id = %s
                            AND status = 'running'
                            AND EXISTS (SELECT 1 FROM workflow_update)
                            AND (
                              %s <> 'completed'
                              OR EXISTS (
                                SELECT 1
                                  FROM worldline_events
                                 WHERE tenant_id = %s
                                   AND project_id = %s
                                   AND session_id = %s
                                   AND source_run_id = %s
                                   AND step = %s
                              )
                            )
                         RETURNING 1
                       )
                       SELECT
                         (SELECT COUNT(*)::int FROM workflow_update) AS workflow_updated,
                         (SELECT COUNT(*)::int FROM session_update) AS session_updated""",
                    (
                        context.tenant_id,
                        context.project_id,
                        normalized_session_id,
                        status,
                        status,
                        _workflow_status_message(status, result, message),
                        encoded_result,
                        encoded_result,
                        code,
                        message,
                        context.tenant_id,
                        context.project_id,
                        context.run_id,
                        normalized_session_id,
                        context.tenant_id,
                        context.project_id,
                        normalized_session_id,
                        status,
                        context.tenant_id,
                        context.project_id,
                        normalized_session_id,
                        context.run_id,
                        step,
                    ),
                )
                row = cursor.fetchone()
                missing_parent = (
                    _count_value(_row_value(row, "workflow_updated", 0)) != 1
                    or _count_value(_row_value(row, "session_updated", 1)) != 1
                )
            if missing_parent:
                _rollback_quietly(connection)
            else:
                connection.commit()
        except Exception as exc:
            if missing_parent:
                raise
            _rollback_quietly(connection)
            raise RuntimeError("WORKFLOW_STATUS_WRITE_FAILED: worldline workflow status write failed") from exc
        finally:
            connection.close()
        if missing_parent:
            raise RuntimeError("WORKFLOW_RUN_NOT_FOUND: worldline step admission parent row is missing")

    def _update_auto_evolution_status(
        self,
        *,
        context: AgentContext,
        session_id: str,
        status: str,
        result: dict[str, Any] | None,
        code: str | None,
        message: str | None,
    ) -> None:
        encoded_result = json.dumps(result, ensure_ascii=False, separators=(",", ":")) if result is not None else None
        connection = self._connect()
        try:
            set_postgres_tenant_context(connection, context=context)
            with connection.cursor() as cursor:
                cursor.execute(
                    """SELECT workflow_run.status AS workflow_status,
                              COALESCE((queued_event.payload_jsonb->>'max_steps')::int, 0) AS max_steps,
                              worldline_session.status AS session_status
                         FROM workflow_runs AS workflow_run
                         JOIN workflow_events AS queued_event
                           ON queued_event.tenant_id = workflow_run.tenant_id
                          AND queued_event.project_id = workflow_run.project_id
                          AND queued_event.run_id = workflow_run.run_id
                          AND queued_event.workflow_type = workflow_run.workflow_type
                          AND queued_event.event_type = 'workflow.queued'
                         JOIN worldline_sessions AS worldline_session
                           ON worldline_session.tenant_id = workflow_run.tenant_id
                          AND worldline_session.project_id = workflow_run.project_id
                          AND worldline_session.session_id::text = queued_event.payload_jsonb->>'session_id'
                        WHERE workflow_run.tenant_id = %s
                          AND workflow_run.project_id = %s
                          AND workflow_run.run_id = %s
                          AND workflow_run.workflow_type = 'worldline_auto_evolution'
                          AND worldline_session.session_id = %s
                          AND queued_event.payload_jsonb->>'world_scope' = 'current_world'
                        FOR UPDATE OF workflow_run, worldline_session""",
                    (context.tenant_id, context.project_id, context.run_id, session_id),
                )
                state = cursor.fetchone()
                if state is None:
                    raise RuntimeError(
                        "WORKFLOW_RUN_NOT_FOUND: worldline auto-evolution admission parent row is missing"
                    )
                current_status = _optional_text(_row_value(state, "workflow_status", 0))
                admitted_max_steps = _count_value(_row_value(state, "max_steps", 1))
                if current_status in {"completed", "failed"}:
                    if current_status != status:
                        raise RuntimeError(
                            "WORKFLOW_STATUS_CONFLICT: worldline auto-evolution terminal status cannot change"
                        )
                    connection.commit()
                    return
                if current_status not in {"queued", "running"}:
                    raise RuntimeError(
                        "WORKFLOW_STATUS_CONFLICT: worldline auto-evolution is not active"
                    )
                if status == "completed":
                    self._validate_auto_evolution_completion(
                        cursor,
                        context=context,
                        session_id=session_id,
                        result=result,
                        admitted_max_steps=admitted_max_steps,
                    )
                cursor.execute(
                    """UPDATE workflow_runs
                          SET status = %s,
                              progress = 100,
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
                          AND workflow_type = 'worldline_auto_evolution'
                          AND status IN ('queued', 'running')
                        RETURNING run_id""",
                    (
                        status,
                        _workflow_status_message(status, result, message),
                        encoded_result,
                        encoded_result,
                        code,
                        message,
                        context.tenant_id,
                        context.project_id,
                        context.run_id,
                    ),
                )
                if cursor.fetchone() is None:
                    raise RuntimeError(
                        "WORKFLOW_STATUS_WRITE_FAILED: worldline auto-evolution workflow status write failed"
                    )
                cursor.execute(
                    """UPDATE worldline_sessions
                          SET status = 'paused', updated_at = now()
                        WHERE tenant_id = %s
                          AND project_id = %s
                          AND session_id = %s
                          AND lifecycle = 'active'
                          AND status IN ('queued', 'running', 'paused')
                        RETURNING session_id""",
                    (context.tenant_id, context.project_id, session_id),
                )
                if cursor.fetchone() is None:
                    raise RuntimeError(
                        "WORKFLOW_STATUS_WRITE_FAILED: worldline auto-evolution session status write failed"
                    )
            connection.commit()
        except RuntimeError:
            _rollback_quietly(connection)
            raise
        except Exception as exc:
            _rollback_quietly(connection)
            raise RuntimeError(
                "WORKFLOW_STATUS_WRITE_FAILED: worldline auto-evolution workflow status write failed"
            ) from exc
        finally:
            connection.close()

    @staticmethod
    def _validate_auto_evolution_completion(
        cursor: Any,
        *,
        context: AgentContext,
        session_id: str,
        result: dict[str, Any] | None,
        admitted_max_steps: int,
    ) -> None:
        completed_steps = _positive_int((result or {}).get("completed_steps"), default=0)
        result_max_steps = _positive_int((result or {}).get("max_steps"), default=0)
        if admitted_max_steps < 1 or completed_steps != admitted_max_steps or result_max_steps != admitted_max_steps:
            raise RuntimeError(
                "WORKFLOW_STATUS_WRITE_FAILED: worldline auto-evolution completion is incomplete"
            )
        cursor.execute(
            """SELECT
                 COUNT(DISTINCT (state_changes_jsonb->>'source_step_index')::int)::int AS completed_steps,
                 COALESCE(MIN((state_changes_jsonb->>'source_step_index')::int), 0)::int AS min_step_index,
                 COALESCE(MAX((state_changes_jsonb->>'source_step_index')::int), 0)::int AS max_step_index
               FROM worldline_events
              WHERE tenant_id = %s
                AND project_id = %s
                AND session_id = %s
                AND source_run_id = %s
                AND state_changes_jsonb->>'source_workflow_type' = 'worldline_auto_evolution'
                AND state_changes_jsonb->>'source_step_index' ~ '^[1-9][0-9]*$'""",
            (context.tenant_id, context.project_id, session_id, context.run_id),
        )
        progress = cursor.fetchone()
        persisted_steps = _count_value(_row_value(progress, "completed_steps", 0))
        min_step_index = _count_value(_row_value(progress, "min_step_index", 1))
        max_step_index = _count_value(_row_value(progress, "max_step_index", 2))
        if persisted_steps != admitted_max_steps or min_step_index != 1 or max_step_index != admitted_max_steps:
            raise RuntimeError(
                "WORKFLOW_STATUS_WRITE_FAILED: worldline auto-evolution candidate steps are incomplete"
            )


def _base_payload(context: AgentContext) -> dict[str, str | None]:
    return {
        **context.to_trace_payload(),
        "workflow_type": WORLDLINE_STEP_WORKFLOW_TYPE,
    }


def _set_postgres_tenant_context_for_ids(
    connection: Any,
    *,
    tenant_id: str,
    actor_user_id: str | None = None,
) -> None:
    normalized_tenant_id = _uuid_or_none(tenant_id)
    if normalized_tenant_id is None:
        return
    normalized_actor_id = _uuid_or_none(actor_user_id)
    with connection.cursor() as cursor:
        cursor.execute(
            "SELECT app_set_tenant_context(%s::uuid, %s::uuid, false)",
            (normalized_tenant_id, normalized_actor_id),
        )


def _rollback_quietly(connection: Any) -> None:
    rollback = getattr(connection, "rollback", None)
    if not callable(rollback):
        return
    try:
        rollback()
    except Exception:
        return


def _sanitize_worldline_value(value: Any) -> Any:
    if isinstance(value, dict):
        sanitized: dict[str, Any] = {}
        for key, item in value.items():
            normalized_key = str(key).strip().lower()
            if not normalized_key or normalized_key in SENSITIVE_WORLDLINE_KEYS:
                continue
            sanitized[str(key)] = _sanitize_worldline_value(item)
        return sanitized
    if isinstance(value, list):
        return [_sanitize_worldline_value(item) for item in value]
    return value


def _write_event(
    writer: WorkflowEventWriter | None,
    *,
    context: AgentContext,
    event_type: str,
    payload: dict[str, Any],
) -> bool:
    if writer is None:
        writer = _workflow_event_writer_from_env()
    if writer is None:
        return False
    writer.write_event(
        tenant_id=context.tenant_id,
        project_id=context.project_id,
        run_id=context.run_id,
        event_type=event_type,
        payload=_sanitize_worldline_value(payload),
    )
    return True


def _failed_result(
    *,
    base: dict[str, Any],
    context: AgentContext,
    session_id: str,
    mode: str,
    code: str,
    message: str,
    workflow_event_writer: WorkflowEventWriter | None,
    workflow_status_writer: WorkflowRunStatusWriter | None,
) -> dict[str, Any]:
    workflow_status_persisted = _mark_workflow_failed(
        workflow_status_writer,
        context=context,
        session_id=session_id,
        code=code,
        message=message,
    )
    stage_event_persisted = _write_event(
        workflow_event_writer,
        context=context,
        event_type="worldline.stage.failed",
        payload={
            "stage": "worldline_step",
            "activity": "worldline_step_activity",
            "status": "failed",
            "module_key": WORLDLINE_STEP_MODULE_KEY,
            "session_id": session_id,
            "mode": mode,
            "error_code": code,
            "message": message,
        },
    )
    return {
        **base,
        "status": "failed",
        "stage": "worldline_step",
        "module_key": WORLDLINE_STEP_MODULE_KEY,
        "session_id": session_id,
        "mode": mode,
        "error": {
            "code": code,
            "message": message,
        },
        "stage_event_persisted": stage_event_persisted,
        "workflow_status_persisted": workflow_status_persisted,
    }


def _persistence_failure_result(
    *,
    base: dict[str, Any],
    context: AgentContext,
    session_id: str,
    mode: str,
    code: str,
    message: str,
    stage_event_persisted: bool,
    workflow_status_writer: WorkflowRunStatusWriter | None,
    mark_failed_status: bool = True,
) -> dict[str, Any]:
    workflow_status_persisted = False
    if mark_failed_status:
        try:
            workflow_status_persisted = _mark_workflow_failed(
                workflow_status_writer,
                context=context,
                session_id=session_id,
                code=code,
                message=message,
            )
        except Exception:
            workflow_status_persisted = False
    return {
        **base,
        "status": "failed",
        "stage": "worldline_step",
        "module_key": WORLDLINE_STEP_MODULE_KEY,
        "session_id": session_id,
        "mode": mode,
        "error": {
            "code": code,
            "message": message,
        },
        "stage_event_persisted": stage_event_persisted,
        "workflow_status_persisted": workflow_status_persisted,
    }


def _stable_workflow_persistence_error(
    exc: Exception,
    *,
    default_code: str,
    default_message: str,
) -> tuple[str, str]:
    text = str(exc)
    safe_messages = {
        "WORKFLOW_EVENT_WRITE_FAILED": "worldline workflow event write failed",
        "WORKFLOW_STATUS_WRITE_FAILED": "worldline workflow status write failed",
        "WORKFLOW_RUN_NOT_FOUND": "worldline step admission parent row is missing",
    }
    if ":" in text:
        code, message = text.split(":", 1)
        normalized_code = code.strip()
        if normalized_code in safe_messages:
            return normalized_code, safe_messages[normalized_code]
    return default_code, default_message


def _workflow_event_writer_from_env() -> WorkflowEventWriter | None:
    database_url = os.environ.get("DATABASE_URL", "").strip()
    if not database_url:
        return None
    return PostgresWorkflowEventWriter.from_database_url(database_url)


def _workflow_status_writer_from_env() -> WorkflowRunStatusWriter | None:
    database_url = os.environ.get("DATABASE_URL", "").strip()
    if not database_url:
        return None
    return PostgresWorkflowRunStatusWriter.from_database_url(database_url)


def _worldline_step_runner_from_env() -> WorldlineStepRunner | None:
    database_url = os.environ.get("DATABASE_URL", "").strip()
    if not database_url:
        return None
    from mirofish_agents.llm_quota import (
        PostgresQuotaStore,
        ProviderQuotaGate,
        QuotaAwareJSONChatClient,
        QuotaEnforcedJSONChatClient,
    )

    return LLMFacilityWorldlineStepRunner(
        binding_resolver=PostgresModuleBindingResolver.from_database_url(database_url),
        credential_provider=PostgresCredentialProvider.from_database_url(
            database_url=database_url,
            key_material=os.environ.get("LLM_CREDENTIAL_ENCRYPTION_KEY"),
        ),
        chat_client=QuotaEnforcedJSONChatClient(
            quota_gate=ProviderQuotaGate(PostgresQuotaStore.from_database_url(database_url)),
            stage_prefix="worldline_director",
            provider_client=QuotaAwareJSONChatClient(),
        ),
        candidate_event_writer=PostgresWorldlineCandidateEventWriter.from_database_url(database_url),
        telemetry_writer=None,
        source_loader=PostgresWorldlineSourceLoader.from_database_url(database_url),
    )


def _mark_workflow_failed(
    writer: WorkflowRunStatusWriter | None,
    *,
    context: AgentContext,
    session_id: str,
    code: str,
    message: str,
) -> bool:
    if writer is None:
        return False
    writer.mark_failed(context=context, session_id=session_id, code=code, message=message)
    return True


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


def _public_status_result(result: dict[str, Any]) -> dict[str, Any]:
    public = _sanitize_worldline_value(result)
    allowed: dict[str, Any] = {}
    for key in (
        "session_id",
        "mode",
        "step",
        "candidate_event_count",
        "model_id",
        "completed_steps",
        "max_steps",
        "last_step",
        "world_scope",
    ):
        value = public.get(key)
        if value is not None:
            allowed[key] = value
    return allowed


def _workflow_status_message(status: str, result: dict[str, Any] | None, message: str | None) -> str:
    if status == "completed":
        completed_steps = result.get("completed_steps") if isinstance(result, dict) else None
        if isinstance(completed_steps, int) and completed_steps > 0:
            return f"worldline auto-evolution completed {completed_steps} steps"
        count = result.get("candidate_event_count", 0) if isinstance(result, dict) else 0
        return f"worldline step completed with {count} candidate events"
    if status == "failed":
        return message or "worldline step failed"
    return status


def _row_value(row: Any, key: str, index: int = 0) -> Any:
    if row is None:
        return None
    if isinstance(row, dict):
        return row.get(key)
    return row[index]


def _count_value(value: Any) -> int:
    if isinstance(value, int):
        return value
    if isinstance(value, str) and value.isdigit():
        return int(value)
    return 0


def _positive_int(value: Any, *, default: int) -> int:
    normalized = _count_value(value)
    return normalized if normalized > 0 else default


def _required_positive_int(value: Any, field_name: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value < 1:
        raise LLMFacilityError("VALIDATION_FAILED", f"{field_name} must be a positive integer")
    return value


def _worldline_runtime_workflow_type(value: Any) -> str:
    normalized = _required_text(value, "workflow_type")
    if normalized not in {
        WORLDLINE_STEP_WORKFLOW_TYPE,
        WORLDLINE_AUTO_EVOLUTION_WORKFLOW_TYPE,
    }:
        raise LLMFacilityError(
            "VALIDATION_FAILED",
            "workflow_type is not supported by the worldline runtime",
        )
    return normalized


def _inactive_worldline_workflow_code(workflow_type: str) -> str:
    if workflow_type == WORLDLINE_AUTO_EVOLUTION_WORKFLOW_TYPE:
        return "WORLDLINE_AUTO_EVOLUTION_NOT_ACTIVE"
    return "WORLDLINE_STEP_NOT_ACTIVE"


def _inactive_worldline_workflow_message(workflow_type: str) -> str:
    if workflow_type == WORLDLINE_AUTO_EVOLUTION_WORKFLOW_TYPE:
        return "worldline auto-evolution is not active for this session"
    return "worldline step is not active for this session"


def _required_text(value: Any, field_name: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{field_name} is required")
    return value.strip()


def _optional_text(value: Any) -> str:
    if not isinstance(value, str):
        return ""
    return value.strip()


def _normalize_mode(value: Any) -> str:
    if not isinstance(value, str) or not value.strip():
        return "director"
    return value.strip()


def _runner_failed(code: str, message: str) -> dict[str, Any]:
    return {"status": "failed", "error": {"code": code, "message": message}}


def _latency_ms(started_at: float) -> int:
    return max(0, int((time.monotonic() - started_at) * 1000))


def _llm_usage_from_response(response_json: dict[str, Any]) -> dict[str, int | float | None]:
    usage = response_json.get("__llm_usage")
    if not isinstance(usage, dict):
        return {"prompt_tokens": None, "completion_tokens": None, "cost_estimate": None}
    return {
        "prompt_tokens": _optional_non_negative_int(usage.get("prompt_tokens")),
        "completion_tokens": _optional_non_negative_int(usage.get("completion_tokens")),
        "total_tokens": _optional_non_negative_int(usage.get("total_tokens")),
        "cost_estimate": _optional_non_negative_number(usage.get("cost_estimate")),
    }


def _optional_non_negative_int(value: Any) -> int | None:
    if isinstance(value, bool):
        return None
    if isinstance(value, int) and value >= 0:
        return value
    if isinstance(value, float) and value >= 0 and value.is_integer():
        return int(value)
    return None


def _optional_non_negative_number(value: Any) -> float | None:
    if isinstance(value, bool):
        return None
    if isinstance(value, (int, float)) and value >= 0:
        return float(value)
    return None


def _record_completed_llm_telemetry(
    writer: LLMTelemetryWriter | None,
    *,
    context: AgentContext,
    resolution: ModuleBindingResolution,
    usage: dict[str, int | float | None],
    latency_ms: int,
) -> None:
    if writer is None:
        return
    try:
        prompt_tokens = usage.get("prompt_tokens")
        completion_tokens = usage.get("completion_tokens")
        total_tokens = usage.get("total_tokens")
        cost_estimate = usage.get("cost_estimate")
        normalized_prompt_tokens = prompt_tokens if isinstance(prompt_tokens, int) else None
        normalized_completion_tokens = completion_tokens if isinstance(completion_tokens, int) else None
        normalized_cost_estimate = cost_estimate if isinstance(cost_estimate, (int, float)) else None
        quantity = _token_quantity(usage)
        atomic_recorder = getattr(writer, "record_completed_llm_call", None)
        if callable(atomic_recorder):
            atomic_recorder(
                context=context,
                module_key=resolution.module_key,
                channel_id=resolution.channel_id,
                model_id=resolution.model_id,
                provider=resolution.provider,
                prompt_tokens=normalized_prompt_tokens,
                completion_tokens=normalized_completion_tokens,
                total_tokens=total_tokens if isinstance(total_tokens, int) else None,
                latency_ms=latency_ms,
                cost_estimate=normalized_cost_estimate,
                usage_quantity=quantity,
            )
            return
        writer.record_llm_activity(
            context=context,
            module_key=resolution.module_key,
            channel_id=resolution.channel_id,
            model_id=resolution.model_id,
            status="completed",
            prompt_tokens=normalized_prompt_tokens,
            completion_tokens=normalized_completion_tokens,
            latency_ms=latency_ms,
            cost_estimate=normalized_cost_estimate,
            error=None,
        )
        if quantity <= 0:
            return
        writer.record_usage_event(
            context=context,
            module_key=resolution.module_key,
            usage_type="llm_tokens",
            quantity=quantity,
            unit="tokens",
            metadata={
                "channel_id": resolution.channel_id,
                "model_id": resolution.model_id,
                "provider": resolution.provider,
                "prompt_tokens": prompt_tokens,
                "completion_tokens": completion_tokens,
                "total_tokens": total_tokens,
                "cost_estimate": cost_estimate,
            },
        )
    except LLMFacilityError:
        raise
    except Exception as exc:
        raise LLMFacilityError(
            "LLM_TELEMETRY_WRITE_FAILED",
            "worldline completed telemetry write failed",
        ) from exc


def _record_failed_llm_telemetry(
    writer: LLMTelemetryWriter | None,
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
            error={"code": code, "message": message},
        )
    except LLMFacilityError:
        raise
    except Exception as exc:
        raise LLMFacilityError(
            "LLM_TELEMETRY_WRITE_FAILED",
            "worldline LLM activity write failed",
        ) from exc


def _token_quantity(usage: dict[str, int | float | None]) -> int:
    prompt_tokens = usage.get("prompt_tokens")
    completion_tokens = usage.get("completion_tokens")
    total_tokens = usage.get("total_tokens")
    if isinstance(total_tokens, int) and total_tokens > 0:
        return total_tokens
    return (prompt_tokens if isinstance(prompt_tokens, int) else 0) + (
        completion_tokens if isinstance(completion_tokens, int) else 0
    )


def _validate_worldline_resolution(resolution: ModuleBindingResolution) -> None:
    if resolution.module_key != WORLDLINE_STEP_MODULE_KEY:
        raise LLMFacilityError("LLM_MODULE_UNBOUND", "resolved module key does not match worldline_director")
    if not resolution.supports_json:
        raise LLMFacilityError("LLM_MODULE_CAPABILITY_MISSING", "worldline_director requires a JSON-capable model")
    for field_name in ("channel_id", "model_id", "provider", "base_url", "credential_ref"):
        value = getattr(resolution, field_name)
        if not isinstance(value, str) or not value.strip():
            raise LLMFacilityError("LLM_PROVIDER_ERROR", f"resolved LLM module is missing {field_name}")


def _worldline_step_messages(
    *,
    context: AgentContext,
    session_id: str,
    mode: str,
    options: dict[str, Any],
    source_summaries: list[dict[str, Any]] | None = None,
) -> list[dict[str, str]]:
    public_options = _sanitize_worldline_value(options)
    user_payload: dict[str, Any] = {
        "tenant_id": context.tenant_id,
        "project_id": context.project_id,
        "run_id": context.run_id,
        "session_id": session_id,
        "module_key": WORLDLINE_STEP_MODULE_KEY,
        "mode": mode,
        "options": public_options,
    }
    if source_summaries:
        user_payload["source_summaries"] = _sanitize_worldline_value(source_summaries)
    return [
        {
            "role": "system",
            "content": (
                "You are the MiroFish worldline director. Return one JSON object with candidate_events. "
                "Each candidate event must include title, summary, kind, optional confidence, "
                "optional involved_agent_ids, and optional state_change_summary. "
                "Do not include event bodies, manuscript text, prompt bodies, API keys, credentials, or provider metadata."
            ),
        },
        {
            "role": "user",
            "content": json.dumps(
                user_payload,
                ensure_ascii=False,
                separators=(",", ":"),
            ),
        },
    ]


def _source_refs(options: dict[str, Any]) -> list[dict[str, Any]]:
    refs = options.get("source_refs")
    if not isinstance(refs, list):
        return []
    normalized: list[dict[str, Any]] = []
    for ref in refs:
        sanitized = _sanitize_worldline_value(ref)
        if isinstance(sanitized, dict) and sanitized:
            normalized.append(sanitized)
    return normalized


def _source_summaries(value: Any) -> list[dict[str, Any]]:
    if not isinstance(value, list):
        raise LLMFacilityError("WORLDLINE_SOURCE_LOAD_FAILED", "worldline source loader returned invalid summaries")
    summaries: list[dict[str, Any]] = []
    for item in value:
        sanitized = _sanitize_worldline_value(item)
        if isinstance(sanitized, dict) and sanitized:
            summaries.append(sanitized)
    return summaries


def _worldline_source_ref_ids(source_refs: list[dict[str, Any]]) -> tuple[list[str], list[str]]:
    asset_ids: list[str] = []
    event_ids: list[str] = []
    for ref in source_refs:
        kind = _optional_text(ref.get("source_kind")).lower()
        source_id = _optional_text(ref.get("source_id")) or _optional_text(ref.get("source_ref"))
        if kind == "asset":
            asset_id = _optional_text(ref.get("asset_id")) or source_id
            if asset_id:
                asset_ids.append(asset_id)
        if kind in {"worldline_event", "event"}:
            event_id = _optional_text(ref.get("event_id")) or source_id
            if event_id:
                event_ids.append(event_id)
    return _unique_texts(asset_ids), _unique_texts(event_ids)


def _unique_texts(values: list[str]) -> list[str]:
    result: list[str] = []
    seen: set[str] = set()
    for value in values:
        if value in seen:
            continue
        seen.add(value)
        result.append(value)
    return result


def _public_source_summaries(rows: Any) -> list[dict[str, Any]]:
    if not isinstance(rows, list):
        return []
    return [_public_source_summary(row) for row in rows]


def _public_source_summary(row: Any) -> dict[str, Any]:
    allowed = ("source_kind", "source_ref", "title", "summary", "asset_type", "category", "kind", "status")
    summary: dict[str, Any] = {}
    for key in allowed:
        value = _row_value(row, key, 0)
        if value is None:
            continue
        summary[key] = value
    return _sanitize_worldline_value(summary)


def _candidate_event_list(value: Any) -> list[dict[str, Any]]:
    if not isinstance(value, list) or not value:
        raise LLMFacilityError("SCHEMA_VALIDATION_FAILED", "candidate_events must be a non-empty array")
    events: list[dict[str, Any]] = []
    for item in value:
        if not isinstance(item, dict):
            raise LLMFacilityError("SCHEMA_VALIDATION_FAILED", "candidate_events items must be objects")
        events.append(item)
    return events


def _candidate_event(value: dict[str, Any], *, step: int) -> dict[str, Any]:
    try:
        title = _required_text(value.get("title"), "title")
        summary = _required_text(value.get("summary"), "summary")
    except ValueError as exc:
        raise LLMFacilityError("SCHEMA_VALIDATION_FAILED", str(exc)) from exc
    kind = _optional_text(value.get("kind")) or "director"
    return {
        "step": step,
        "title": title,
        "summary": summary,
        "kind": kind,
        "confidence": _confidence_or_none(value.get("confidence")),
        "involved_agent_ids": _string_list(value.get("involved_agent_ids")),
        "state_change_summary": _optional_text(value.get("state_change_summary")),
    }


def _step_number(options: dict[str, Any]) -> int:
    value = options.get("step")
    if isinstance(value, int) and value > 0:
        return value
    value = options.get("step_number")
    if isinstance(value, int) and value > 0:
        return value
    return 1


def _source_step_index(options: dict[str, Any]) -> int:
    value = options.get("source_step_index")
    if value is None:
        return 1
    return _required_positive_int(value, "source_step_index")


def _step_from_event(event: dict[str, Any]) -> int:
    value = event.get("step")
    if isinstance(value, int) and value > 0:
        return value
    return 1


def _confidence_or_none(value: Any) -> float | None:
    if value is None:
        return None
    if isinstance(value, (int, float)):
        confidence = float(value)
        if 0 <= confidence <= 1:
            return confidence
    raise LLMFacilityError("SCHEMA_VALIDATION_FAILED", "confidence must be between 0 and 1")


def _string_list(value: Any) -> list[str]:
    if value is None:
        return []
    if not isinstance(value, list):
        raise LLMFacilityError("SCHEMA_VALIDATION_FAILED", "involved_agent_ids must be an array")
    result: list[str] = []
    for item in value:
        if isinstance(item, str) and item.strip():
            result.append(item.strip())
    return result


def _state_changes_payload(
    *,
    event: dict[str, Any],
    model_id: str | None,
    mode: str,
    source_step_index: int = 1,
    workflow_type: str = WORLDLINE_STEP_WORKFLOW_TYPE,
) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "summary": event.get("state_change_summary", ""),
        "mode": mode,
        "source_step_index": source_step_index,
        "source_workflow_type": workflow_type,
    }
    if model_id:
        payload["model_id"] = model_id
    return payload


def _read_candidate_replay(
    writer: WorldlineCandidateEventWriter,
    *,
    context: AgentContext,
    session_id: str,
    source_run_id: str,
    source_step_index: int,
    workflow_type: str,
) -> dict[str, Any] | None:
    reader = getattr(writer, "read_candidate_events", None)
    if not callable(reader):
        return None
    replayed = reader(
        context=context,
        session_id=session_id,
        source_run_id=source_run_id,
        source_step_index=source_step_index,
        workflow_type=workflow_type,
    )
    if replayed is None:
        return None
    count = _positive_int(replayed.get("candidate_event_count"), default=0)
    step = _positive_int(replayed.get("step"), default=0)
    if count < 1 or step < 1:
        raise LLMFacilityError(
            "WORLDLINE_STEP_STATE_INVALID",
            "worldline step candidate replay state is inconsistent",
        )
    return {
        "candidate_event_count": count,
        "step": step,
        "model_id": _optional_text(replayed.get("model_id")) or None,
    }


def _uuid_or_none(value: Any) -> str | None:
    if not isinstance(value, str) or not value.strip():
        return None
    try:
        return str(UUID(value.strip()))
    except ValueError:
        return None


def _required_uuid_text(value: Any, field_name: str) -> str:
    normalized = _uuid_or_none(value)
    if normalized is None:
        raise LLMFacilityError("VALIDATION_FAILED", f"{field_name} must be a valid UUID")
    return normalized


@activity.defn
def worldline_step_activity(
    payload: dict[str, Any],
    step_runner: WorldlineStepRunner | None = None,
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
    session_id = _required_text(payload.get("session_id"), "session_id")
    mode = _normalize_mode(payload.get("mode"))
    if context.workflow_type != WORLDLINE_STEP_WORKFLOW_TYPE:
        return _failed_result(
            base=base,
            context=context,
            session_id=session_id,
            mode=mode,
            code="VALIDATION_FAILED",
            message=f"workflow_type must be {WORLDLINE_STEP_WORKFLOW_TYPE}",
            workflow_event_writer=workflow_event_writer,
            workflow_status_writer=workflow_status_writer,
        )
    if context.module_key is not None and context.module_key != WORLDLINE_STEP_MODULE_KEY:
        return _failed_result(
            base=base,
            context=context,
            session_id=session_id,
            mode=mode,
            code="VALIDATION_FAILED",
            message=f"module_key must be {WORLDLINE_STEP_MODULE_KEY}",
            workflow_event_writer=workflow_event_writer,
            workflow_status_writer=workflow_status_writer,
        )
    if not context.has_permission(WORLDLINE_STEP_MODULE_KEY, "run"):
        return _failed_result(
            base=base,
            context=context,
            session_id=session_id,
            mode=mode,
            code="FORBIDDEN",
            message="worldline_director run permission is required",
            workflow_event_writer=workflow_event_writer,
            workflow_status_writer=workflow_status_writer,
        )
    options = payload.get("options") if isinstance(payload.get("options"), dict) else {}
    if step_runner is None:
        try:
            step_runner = _worldline_step_runner_from_env()
        except Exception:
            step_runner = None
    if step_runner is None:
        return _failed_result(
            base=base,
            context=context,
            session_id=session_id,
            mode=mode,
            code="WORLDLINE_STEP_RUNNER_UNCONFIGURED",
            message="worldline step runner requires a configured director runtime",
            workflow_event_writer=workflow_event_writer,
            workflow_status_writer=workflow_status_writer,
        )
    try:
        result = step_runner.run_step(
            context=context,
            session_id=session_id,
            mode=mode,
            options=_sanitize_worldline_value(options),
        )
    except LLMFacilityError as exc:
        return _failed_result(
            base=base,
            context=context,
            session_id=session_id,
            mode=mode,
            code=exc.code,
            message=exc.message,
            workflow_event_writer=workflow_event_writer,
            workflow_status_writer=workflow_status_writer,
        )
    except Exception:
        return _failed_result(
            base=base,
            context=context,
            session_id=session_id,
            mode=mode,
            code="WORLDLINE_STEP_FAILED",
            message="worldline step runner failed",
            workflow_event_writer=workflow_event_writer,
            workflow_status_writer=workflow_status_writer,
        )
    if isinstance(result, dict) and result.get("status") == "failed":
        error = result.get("error") if isinstance(result.get("error"), dict) else {}
        return _failed_result(
            base=base,
            context=context,
            session_id=session_id,
            mode=mode,
            code=str(error.get("code") or "WORLDLINE_STEP_FAILED"),
            message=str(error.get("message") or "worldline step runner failed"),
            workflow_event_writer=workflow_event_writer,
            workflow_status_writer=workflow_status_writer,
        )
    public_result = _public_status_result({"session_id": session_id, "mode": mode, **_sanitize_worldline_value(result)})
    try:
        stage_event_persisted = _write_event(
            workflow_event_writer,
            context=context,
            event_type="worldline.stage.completed",
            payload={
                "stage": "worldline_step",
                "activity": "worldline_step_activity",
                "status": "completed",
                "module_key": WORLDLINE_STEP_MODULE_KEY,
                **public_result,
            },
        )
    except Exception as exc:
        code, message = _stable_workflow_persistence_error(
            exc,
            default_code="WORKFLOW_EVENT_WRITE_FAILED",
            default_message="worldline workflow event write failed",
        )
        return _persistence_failure_result(
            base=base,
            context=context,
            session_id=session_id,
            mode=mode,
            code=code,
            message=message,
            stage_event_persisted=False,
            workflow_status_writer=workflow_status_writer,
        )
    try:
        workflow_status_persisted = _mark_workflow_completed(
            workflow_status_writer,
            context=context,
            result=public_result,
        )
    except Exception as exc:
        code, message = _stable_workflow_persistence_error(
            exc,
            default_code="WORKFLOW_STATUS_WRITE_FAILED",
            default_message="worldline workflow status write failed",
        )
        return _persistence_failure_result(
            base=base,
            context=context,
            session_id=session_id,
            mode=mode,
            code=code,
            message=message,
            stage_event_persisted=stage_event_persisted,
            workflow_status_writer=workflow_status_writer,
            mark_failed_status=False,
        )
    return {
        **base,
        "status": "completed",
        "stage": "worldline_step",
        "module_key": WORLDLINE_STEP_MODULE_KEY,
        **public_result,
        "workflow_status_persisted": workflow_status_persisted,
        "stage_event_persisted": stage_event_persisted,
    }


@workflow.defn
class WorldlineStepWorkflow:
    @workflow.run
    async def run(self, payload: dict[str, Any]) -> dict[str, Any]:
        return await workflow.execute_activity(
            worldline_step_activity,
            payload,
            start_to_close_timeout=timedelta(minutes=20),
            schedule_to_close_timeout=timedelta(hours=2),
        )


def run_worldline_step_workflow_locally(
    payload: dict[str, Any],
    *,
    step_runner: WorldlineStepRunner | None = None,
    workflow_event_writer: WorkflowEventWriter | None = None,
    workflow_status_writer: WorkflowRunStatusWriter | None = None,
) -> dict[str, Any]:
    return worldline_step_activity(
        payload,
        step_runner=step_runner,
        workflow_event_writer=workflow_event_writer,
        workflow_status_writer=workflow_status_writer,
    )


def worker_spec() -> dict[str, list[str] | str]:
    return {
        "task_queue": WORLDLINE_TASK_QUEUE,
        "workflows": [
            WorldlineStepWorkflow.__name__,
            WorldlinePrepareWorkflow.__name__,
            "WorldlineAutoEvolutionWorkflow",
        ],
        "activities": [
            worldline_step_activity.__name__,
            worldline_prepare_activity.__name__,
            "worldline_auto_evolution_step_activity",
            "worldline_auto_evolution_finalize_activity",
        ],
    }
