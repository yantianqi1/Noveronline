from __future__ import annotations

import json
import os
import re
from datetime import timedelta
from typing import Any, Callable, Protocol
from uuid import UUID

from temporalio import activity, workflow
from temporalio.common import RetryPolicy
from temporalio.exceptions import ActivityError, ApplicationError

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


WRITER_DEDUP_WORKFLOW_TYPE = "writer_dedup_extraction"
WRITER_DEDUP_MODULE_KEY = "writer_dedup_extractor"
WRITER_BOOK_PLAN_WORKFLOW_TYPE = "writer_book_plan_generation"
WRITER_BOOK_PLANNER_MODULE_KEY = "writer_book_planner"
WRITER_PLANNING_TASK_QUEUE = "writer-planning"

_PATTERN_KINDS = {"phrase", "sentence_shape", "transition", "description"}
_PATTERN_FIELDS = {"pattern_text", "pattern_kind", "occurrence_count"}
_ACT_FIELDS = {"title", "summary", "chapter_start", "chapter_end"}
_QUOTE = re.compile(r'["\u201c\u300c\u300e][^"\u201d\u300d\u300f]{16,}["\u201d\u300d\u300f]')


class WriterPlanningStore(Protocol):
    def load_dedup_source(
        self, *, context: AgentContext, block_ids: list[str], chapter_id: str | None
    ) -> dict[str, Any]: ...

    def complete_dedup(
        self, *, context: AgentContext, patterns: list[dict[str, Any]], resolution: ModuleBindingResolution
    ) -> dict[str, Any]: ...

    def load_book_plan(
        self, *, context: AgentContext, book_plan_id: str, expected_version: int | None
    ) -> dict[str, Any]: ...

    def complete_book_plan(
        self, *, context: AgentContext, book_plan_id: str, expected_version: int,
        candidate: dict[str, Any], resolution: ModuleBindingResolution
    ) -> dict[str, Any]: ...

    def fail_workflow(
        self, *, context: AgentContext, code: str, message: str, book_plan_id: str | None
    ) -> None: ...


class LLMFacilityWriterPlanningRunner:
    def __init__(
        self,
        *,
        binding_resolver: ModuleBindingResolver,
        credential_provider: CredentialProvider,
        chat_client: JSONChatClient,
        store: WriterPlanningStore,
    ) -> None:
        self._binding_resolver = binding_resolver
        self._credential_provider = credential_provider
        self._chat_client = chat_client
        self._store = store

    def run_dedup(
        self, *, context: AgentContext, block_ids: list[str] | None = None, chapter_id: str | None = None,
        persist_failure: bool = True,
    ) -> dict[str, Any]:
        try:
            source = self._store.load_dedup_source(
                context=context, block_ids=list(block_ids or []), chapter_id=chapter_id
            )
            if source.get("replayed") is True:
                return _public_result(source)
            resolution, api_key = self._resolve(context, WRITER_DEDUP_MODULE_KEY)
            response = self._chat_client.complete_json(
                context=context,
                resolution=resolution,
                api_key=api_key,
                messages=_dedup_messages(source_text=source["source_text"]),
            )
            patterns = validate_dedup_candidates(response, source_text=source["source_text"])
            candidates = [{**pattern, "lifecycle": "candidate", "enabled": False} for pattern in patterns]
            return _public_result(self._store.complete_dedup(
                context=context, patterns=candidates, resolution=resolution
            ))
        except Exception as exc:
            code, message = _stable_error(exc)
            if persist_failure:
                try:
                    self._store.fail_workflow(context=context, code=code, message=message, book_plan_id=None)
                except Exception:
                    code, message = "WRITER_PLANNING_STATUS_WRITE_FAILED", "writer planning status write failed"
            raise LLMFacilityError(code, message) from exc

    def run_book_plan(
        self, *, context: AgentContext, book_plan_id: str, expected_version: int | None = None,
        persist_failure: bool = True,
    ) -> dict[str, Any]:
        try:
            source = self._store.load_book_plan(
                context=context, book_plan_id=book_plan_id, expected_version=expected_version
            )
            if source.get("replayed") is True:
                return _public_result(source)
            resolution, api_key = self._resolve(context, WRITER_BOOK_PLANNER_MODULE_KEY)
            response = self._chat_client.complete_json(
                context=context,
                resolution=resolution,
                api_key=api_key,
                messages=_book_plan_messages(source),
            )
            candidate = validate_book_plan_candidate(
                response, target_chapter_count=source.get("target_chapter_count")
            )
            candidate["status"] = "draft"
            return _public_result(self._store.complete_book_plan(
                context=context,
                book_plan_id=book_plan_id,
                expected_version=int(source["expected_version"]),
                candidate=candidate,
                resolution=resolution,
            ))
        except Exception as exc:
            code, message = _stable_error(exc)
            if persist_failure:
                try:
                    self._store.fail_workflow(
                        context=context, code=code, message=message, book_plan_id=book_plan_id
                    )
                except Exception:
                    code, message = "WRITER_PLANNING_STATUS_WRITE_FAILED", "writer planning status write failed"
            raise LLMFacilityError(code, message) from exc

    def _resolve(self, context: AgentContext, module_key: str) -> tuple[ModuleBindingResolution, str]:
        resolution = self._binding_resolver.resolve_module_binding(context=context, module_key=module_key)
        _validate_resolution(resolution, module_key)
        api_key = self._credential_provider.resolve_api_key(
            context=context, credential_ref=resolution.credential_ref
        )
        if not isinstance(api_key, str) or not api_key.strip():
            raise LLMFacilityError("LLM_CREDENTIAL_UNAVAILABLE", "resolved credential was empty")
        return resolution, api_key.strip()


class PostgresWriterPlanningStore:
    def __init__(self, *, connect: Callable[[], Any]) -> None:
        self._connect = connect

    @classmethod
    def from_database_url(cls, database_url: str) -> "PostgresWriterPlanningStore":
        try:
            import psycopg
        except ImportError as exc:  # pragma: no cover
            raise RuntimeError("psycopg is required for Writer planning runtime") from exc
        return cls(connect=lambda: psycopg.connect(database_url))

    def load_dedup_source(
        self, *, context: AgentContext, block_ids: list[str], chapter_id: str | None
    ) -> dict[str, Any]:
        _require_context(context, WRITER_DEDUP_WORKFLOW_TYPE, WRITER_DEDUP_MODULE_KEY)
        normalized_ids = [_required_uuid(value, "block_id") for value in block_ids]
        if len(set(normalized_ids)) != len(normalized_ids):
            raise LLMFacilityError("VALIDATION_FAILED", "selected manuscript blocks must be unique")
        normalized_chapter = _optional_uuid(chapter_id, "chapter_id")
        if not normalized_ids and normalized_chapter is None:
            raise LLMFacilityError("VALIDATION_FAILED", "an explicit manuscript block or chapter selection is required")
        connection = self._connect()
        try:
            set_postgres_tenant_context(connection, context=context)
            with connection.cursor() as cursor:
                replay = _lock_workflow(cursor, context)
                if replay is not None:
                    connection.commit()
                    return replay
                cursor.execute(
                    """SELECT block.block_id::text, block.content_text FROM manuscript_blocks block
                       JOIN writer_drafts draft ON draft.tenant_id = block.tenant_id
                         AND draft.project_id = block.project_id
                         AND draft.draft_id = block.source_draft_id AND draft.status = 'adopted'
                       WHERE block.tenant_id = %s AND block.project_id = %s AND block.status = 'active'
                         AND (%s::uuid IS NULL OR block.chapter_id = %s::uuid)
                         AND (cardinality(%s::uuid[]) = 0 OR block.block_id = ANY(%s::uuid[]))
                       ORDER BY block.block_order, block.block_id""",
                    (
                        context.tenant_id, context.project_id,
                        normalized_chapter, normalized_chapter,
                        normalized_ids, normalized_ids,
                    ),
                )
                rows = cursor.fetchall()
                if not rows or (normalized_ids and len(rows) != len(normalized_ids)):
                    raise LLMFacilityError("WRITER_DEDUP_SOURCE_NOT_FOUND", "selected adopted manuscript source was not found")
                _mark_running(cursor, context, "writer.dedup.started", {"source_count": len(rows)})
            connection.commit()
            return {
                "status": "running", "replayed": False,
                "source_text": "\n\n".join(str(row[1]) for row in rows),
                "source_count": len(rows),
            }
        except LLMFacilityError:
            _rollback(connection)
            raise
        except Exception as exc:
            _rollback(connection)
            raise LLMFacilityError("WRITER_DEDUP_SOURCE_LOAD_FAILED", "writer dedup source load failed") from exc
        finally:
            connection.close()

    def complete_dedup(
        self, *, context: AgentContext, patterns: list[dict[str, Any]], resolution: ModuleBindingResolution
    ) -> dict[str, Any]:
        connection = self._connect()
        try:
            set_postgres_tenant_context(connection, context=context)
            with connection.cursor() as cursor:
                replay = _lock_workflow(cursor, context)
                if replay is not None:
                    connection.commit()
                    return replay
                inserted = 0
                for pattern in patterns:
                    cursor.execute(
                        """INSERT INTO writer_dedup_patterns (
                             tenant_id, project_id, pattern_text, normalized_pattern, pattern_kind,
                             lifecycle, enabled, occurrence_count, source_workflow_run_id
                           ) VALUES (%s, %s, %s, %s, %s, 'candidate', FALSE, %s, %s)
                           ON CONFLICT (tenant_id, project_id, normalized_pattern) DO NOTHING
                           RETURNING pattern_id""",
                        (
                            context.tenant_id, context.project_id, pattern["pattern_text"],
                            _normalize_text(pattern["pattern_text"]), pattern["pattern_kind"],
                            pattern["occurrence_count"], context.run_id,
                        ),
                    )
                    if cursor.fetchone() is not None:
                        inserted += 1
                result = {"status": "completed", "candidate_count": inserted, "module_key": resolution.module_key, "model_id": resolution.model_id}
                _complete_workflow(cursor, context, "writer.dedup.completed", result)
            connection.commit()
            return {"status": "completed", "replayed": False, "candidate_count": inserted}
        except Exception as exc:
            _rollback(connection)
            if isinstance(exc, LLMFacilityError):
                raise
            raise LLMFacilityError("WRITER_DEDUP_PERSIST_FAILED", "writer dedup candidate persistence failed") from exc
        finally:
            connection.close()

    def load_book_plan(
        self, *, context: AgentContext, book_plan_id: str, expected_version: int | None
    ) -> dict[str, Any]:
        _require_context(context, WRITER_BOOK_PLAN_WORKFLOW_TYPE, WRITER_BOOK_PLANNER_MODULE_KEY)
        book_plan_id = _required_uuid(book_plan_id, "book_plan_id")
        if isinstance(expected_version, bool) or not isinstance(expected_version, int) or expected_version <= 0:
            raise LLMFacilityError("VALIDATION_FAILED", "expected_version must be positive")
        connection = self._connect()
        try:
            set_postgres_tenant_context(connection, context=context)
            with connection.cursor() as cursor:
                replay = _lock_workflow(cursor, context)
                if replay is not None:
                    connection.commit()
                    return replay
                cursor.execute(
                    """SELECT title, COALESCE(premise, ''), target_chapter_count,
                              optimistic_version, status, last_run_id::text
                       FROM book_plans WHERE tenant_id = %s AND project_id = %s
                         AND book_plan_id = %s FOR UPDATE""",
                    (context.tenant_id, context.project_id, book_plan_id),
                )
                row = cursor.fetchone()
                if row is None:
                    raise LLMFacilityError("BOOK_PLAN_NOT_FOUND", "book plan was not found")
                if row[4] != "draft" or int(row[3]) != expected_version or str(row[5]) != context.run_id:
                    raise LLMFacilityError("BOOK_PLAN_CONFLICT", "book plan generation state changed")
                _mark_running(cursor, context, "writer.book_plan.started", {"book_plan_id": book_plan_id})
                cursor.execute(
                    """UPDATE book_plans SET last_run_status = 'running', updated_at = now()
                       WHERE tenant_id = %s AND project_id = %s AND book_plan_id = %s""",
                    (context.tenant_id, context.project_id, book_plan_id),
                )
                _append_book_event(cursor, context, book_plan_id, "planning.started", "running", 0)
            connection.commit()
            return {
                "status": "running", "replayed": False, "title": str(row[0]),
                "premise": str(row[1]), "target_chapter_count": row[2],
                "expected_version": int(row[3]),
            }
        except LLMFacilityError:
            _rollback(connection)
            raise
        except Exception as exc:
            _rollback(connection)
            raise LLMFacilityError("BOOK_PLAN_SOURCE_LOAD_FAILED", "book plan source load failed") from exc
        finally:
            connection.close()

    def complete_book_plan(
        self, *, context: AgentContext, book_plan_id: str, expected_version: int,
        candidate: dict[str, Any], resolution: ModuleBindingResolution
    ) -> dict[str, Any]:
        connection = self._connect()
        try:
            set_postgres_tenant_context(connection, context=context)
            with connection.cursor() as cursor:
                replay = _lock_workflow(cursor, context)
                if replay is not None:
                    connection.commit()
                    return replay
                planning = {"candidate": True, "acts": candidate["acts"], "model_id": resolution.model_id}
                cursor.execute(
                    """UPDATE book_plans SET premise = %s, planning_jsonb = %s::jsonb,
                              optimistic_version = optimistic_version + 1,
                              last_run_status = 'completed', updated_by = %s, updated_at = now()
                       WHERE tenant_id = %s AND project_id = %s AND book_plan_id = %s
                         AND status = 'draft' AND optimistic_version = %s AND last_run_id = %s
                       RETURNING optimistic_version""",
                    (
                        candidate["premise"], json.dumps(planning, separators=(",", ":")),
                        context.actor_user_id, context.tenant_id, context.project_id,
                        book_plan_id, expected_version, context.run_id,
                    ),
                )
                updated = cursor.fetchone()
                if updated is None:
                    raise LLMFacilityError("BOOK_PLAN_CONFLICT", "book plan generation state changed")
                result = {
                    "status": "completed", "book_plan_id": book_plan_id, "candidate": True,
                    "item_count": len(candidate["acts"]), "version": int(updated[0]),
                    "module_key": resolution.module_key, "model_id": resolution.model_id,
                }
                _append_book_event(cursor, context, book_plan_id, "planning.completed", "completed", len(candidate["acts"]))
                _complete_workflow(cursor, context, "writer.book_plan.completed", result)
            connection.commit()
            return {key: result[key] for key in ("status", "book_plan_id", "candidate", "item_count", "version")}
        except Exception as exc:
            _rollback(connection)
            if isinstance(exc, LLMFacilityError):
                raise
            raise LLMFacilityError("BOOK_PLAN_PERSIST_FAILED", "book plan candidate persistence failed") from exc
        finally:
            connection.close()

    def fail_workflow(
        self, *, context: AgentContext, code: str, message: str, book_plan_id: str | None
    ) -> None:
        connection = self._connect()
        try:
            set_postgres_tenant_context(connection, context=context)
            with connection.cursor() as cursor:
                cursor.execute(
                    """UPDATE workflow_runs SET status = 'failed', progress = 0, message = %s,
                              error_code = %s, error_message = %s, updated_at = now()
                       WHERE tenant_id = %s AND project_id = %s AND run_id = %s
                         AND workflow_type = %s AND status IN ('queued', 'running')""",
                    (message, code, message, context.tenant_id, context.project_id, context.run_id, context.workflow_type),
                )
                if book_plan_id:
                    cursor.execute(
                        """UPDATE book_plans SET last_run_status = 'failed', updated_at = now()
                           WHERE tenant_id = %s AND project_id = %s AND book_plan_id = %s
                             AND last_run_id = %s""",
                        (context.tenant_id, context.project_id, book_plan_id, context.run_id),
                    )
                    _append_book_event(cursor, context, book_plan_id, "planning.failed", "failed", 0)
                _append_workflow_event(cursor, context, "workflow.failed", {"status": "failed", "error_code": code, "module_key": context.module_key})
            connection.commit()
        except Exception as exc:
            _rollback(connection)
            raise LLMFacilityError("WRITER_PLANNING_STATUS_WRITE_FAILED", "writer planning status write failed") from exc
        finally:
            connection.close()


def validate_dedup_candidates(response: dict[str, Any], *, source_text: str) -> list[dict[str, Any]]:
    if not isinstance(response, dict) or set(response) - {"patterns", "__llm_usage"}:
        raise _schema_error()
    values = response.get("patterns")
    if not isinstance(values, list) or not 1 <= len(values) <= 50:
        raise _schema_error()
    patterns: list[dict[str, Any]] = []
    seen: set[str] = set()
    source_normalized = _normalize_text(source_text)
    for value in values:
        if not isinstance(value, dict) or set(value) != _PATTERN_FIELDS:
            raise _schema_error()
        text = _public_text(value.get("pattern_text"), 160)
        kind = value.get("pattern_kind")
        count = value.get("occurrence_count")
        normalized = _normalize_text(text)
        if kind not in _PATTERN_KINDS or isinstance(count, bool) or not isinstance(count, int) or count < 2:
            raise _schema_error()
        if normalized in seen or _QUOTE.search(text) or (len(normalized) >= 16 and normalized in source_normalized):
            raise _schema_error()
        seen.add(normalized)
        patterns.append({"pattern_text": text, "pattern_kind": kind, "occurrence_count": count})
    return patterns


def validate_book_plan_candidate(response: dict[str, Any], *, target_chapter_count: Any) -> dict[str, Any]:
    if not isinstance(response, dict) or set(response) - {"premise", "acts", "__llm_usage"}:
        raise _schema_error()
    premise = _public_text(response.get("premise"), 2000)
    acts = response.get("acts")
    if not isinstance(acts, list) or not 1 <= len(acts) <= 20:
        raise _schema_error()
    maximum = target_chapter_count if isinstance(target_chapter_count, int) and target_chapter_count > 0 else None
    normalized_acts: list[dict[str, Any]] = []
    previous_end = 0
    for value in acts:
        if not isinstance(value, dict) or set(value) != _ACT_FIELDS:
            raise _schema_error()
        start, end = value.get("chapter_start"), value.get("chapter_end")
        if any(isinstance(item, bool) or not isinstance(item, int) for item in (start, end)):
            raise _schema_error()
        if start <= previous_end or end < start or (maximum is not None and end > maximum):
            raise _schema_error()
        previous_end = end
        normalized_acts.append({
            "title": _public_text(value.get("title"), 200),
            "summary": _public_text(value.get("summary"), 2000),
            "chapter_start": start,
            "chapter_end": end,
        })
    return {"premise": premise, "acts": normalized_acts}


def _dedup_messages(*, source_text: str) -> list[dict[str, str]]:
    return [
        {"role": "system", "content": "Extract abstract repetition-risk patterns from explicitly selected adopted manuscript. Return JSON {patterns:[{pattern_text,pattern_kind,occurrence_count}]}. Never quote or reproduce manuscript prose."},
        {"role": "user", "content": source_text},
    ]


def _book_plan_messages(source: dict[str, Any]) -> list[dict[str, str]]:
    return [
        {"role": "system", "content": "Generate a candidate book plan as JSON {premise,acts:[{title,summary,chapter_start,chapter_end}]}. The result remains draft until explicit user activation."},
        {"role": "user", "content": json.dumps({key: source.get(key) for key in ("title", "premise", "target_chapter_count")}, ensure_ascii=False)},
    ]


def _validate_resolution(resolution: ModuleBindingResolution, expected: str) -> None:
    if resolution.module_key != expected:
        raise LLMFacilityError("LLM_MODULE_UNBOUND", f"resolved module key does not match {expected}")
    if not resolution.supports_json:
        raise LLMFacilityError("LLM_CAPABILITY_UNSUPPORTED", f"{expected} requires a JSON-capable model")
    for field in ("channel_id", "model_id", "provider", "base_url", "credential_ref"):
        if not isinstance(getattr(resolution, field), str) or not getattr(resolution, field).strip():
            raise LLMFacilityError("LLM_PROVIDER_ERROR", f"resolved LLM module is missing {field}")


def _lock_workflow(cursor: Any, context: AgentContext) -> dict[str, Any] | None:
    cursor.execute(
        """SELECT status, result_jsonb FROM workflow_runs
           WHERE tenant_id = %s AND project_id = %s AND run_id = %s
             AND workflow_type = %s FOR UPDATE""",
        (context.tenant_id, context.project_id, context.run_id, context.workflow_type),
    )
    row = cursor.fetchone()
    if row is None:
        raise LLMFacilityError("WRITER_PLANNING_NOT_FOUND", "writer planning workflow was not found")
    if row[0] == "completed":
        value = row[1] if isinstance(row[1], dict) else json.loads(row[1] or "{}")
        return {"status": "completed", "replayed": True, **{key: value[key] for key in ("candidate_count", "book_plan_id", "candidate", "item_count", "version") if key in value}}
    if row[0] not in {"queued", "running"}:
        raise LLMFacilityError("WRITER_PLANNING_NOT_ACTIVE", "writer planning workflow is not active")
    return None


def _mark_running(cursor: Any, context: AgentContext, event_type: str, payload: dict[str, Any]) -> None:
    cursor.execute(
        """UPDATE workflow_runs SET status = 'running', progress = 10,
                  message = 'writer planning running', updated_at = now()
           WHERE tenant_id = %s AND project_id = %s AND run_id = %s
             AND workflow_type = %s AND status IN ('queued', 'running')""",
        (context.tenant_id, context.project_id, context.run_id, context.workflow_type),
    )
    _append_workflow_event(cursor, context, event_type, {"status": "running", "module_key": context.module_key, **payload})


def _complete_workflow(cursor: Any, context: AgentContext, event_type: str, result: dict[str, Any]) -> None:
    cursor.execute(
        """UPDATE workflow_runs SET status = 'completed', progress = 100,
                  message = 'writer planning completed', result_jsonb = %s::jsonb,
                  error_code = NULL, error_message = NULL, updated_at = now()
           WHERE tenant_id = %s AND project_id = %s AND run_id = %s
             AND workflow_type = %s AND status IN ('queued', 'running')""",
        (json.dumps(result, separators=(",", ":")), context.tenant_id, context.project_id, context.run_id, context.workflow_type),
    )
    _append_workflow_event(cursor, context, event_type, result)


def _append_workflow_event(cursor: Any, context: AgentContext, event_type: str, payload: dict[str, Any]) -> None:
    cursor.execute(
        """INSERT INTO workflow_events (
             tenant_id, run_id, workflow_type, project_id, event_type, sequence, payload_jsonb
           ) VALUES (%s, %s, %s, %s, %s,
             (SELECT COALESCE(max(sequence), 0) + 1 FROM workflow_events WHERE tenant_id = %s AND run_id = %s),
             %s::jsonb)""",
        (context.tenant_id, context.run_id, context.workflow_type, context.project_id, event_type, context.tenant_id, context.run_id, json.dumps(payload, separators=(",", ":"))),
    )


def _append_book_event(cursor: Any, context: AgentContext, book_plan_id: str, event_type: str, status: str, count: int) -> None:
    cursor.execute(
        """INSERT INTO book_run_events (
             tenant_id, project_id, book_plan_id, run_id, sequence, event_type, status, item_count
           ) VALUES (%s, %s, %s, %s,
             (SELECT COALESCE(max(sequence), 0) + 1 FROM book_run_events WHERE tenant_id = %s AND project_id = %s AND book_plan_id = %s),
             %s, %s, %s)""",
        (context.tenant_id, context.project_id, book_plan_id, context.run_id, context.tenant_id, context.project_id, book_plan_id, event_type, status, count),
    )


def _runner_from_env() -> LLMFacilityWriterPlanningRunner | None:
    database_url = os.environ.get("DATABASE_URL", "").strip()
    if not database_url:
        return None
    from mirofish_agents.llm_quota import PostgresQuotaStore, ProviderQuotaGate, QuotaAwareJSONChatClient, QuotaEnforcedJSONChatClient
    return LLMFacilityWriterPlanningRunner(
        binding_resolver=PostgresModuleBindingResolver.from_database_url(database_url),
        credential_provider=PostgresCredentialProvider.from_database_url(
            database_url=database_url, key_material=os.environ.get("LLM_CREDENTIAL_ENCRYPTION_KEY")
        ),
        chat_client=QuotaEnforcedJSONChatClient(
            quota_gate=ProviderQuotaGate(PostgresQuotaStore.from_database_url(database_url)),
            stage_prefix="writer_planning",
            provider_client=QuotaAwareJSONChatClient(),
        ),
        store=PostgresWriterPlanningStore.from_database_url(database_url),
    )


@activity.defn
def writer_dedup_activity(payload: dict[str, Any], runner: LLMFacilityWriterPlanningRunner | None = None) -> dict[str, Any]:
    return _planning_activity(payload, mode="dedup", runner=runner)


@activity.defn
def writer_book_plan_activity(payload: dict[str, Any], runner: LLMFacilityWriterPlanningRunner | None = None) -> dict[str, Any]:
    return _planning_activity(payload, mode="book_plan", runner=runner)


def _planning_activity(payload: dict[str, Any], *, mode: str, runner: LLMFacilityWriterPlanningRunner | None) -> dict[str, Any]:
    try:
        context = AgentContext.model_validate(payload.get("context", payload))
        expected_workflow = WRITER_DEDUP_WORKFLOW_TYPE if mode == "dedup" else WRITER_BOOK_PLAN_WORKFLOW_TYPE
        expected_module = WRITER_DEDUP_MODULE_KEY if mode == "dedup" else WRITER_BOOK_PLANNER_MODULE_KEY
        _require_context(context, expected_workflow, expected_module)
        if not context.has_permission(expected_module, "run"):
            raise LLMFacilityError("FORBIDDEN", f"{expected_module} run permission is required")
        if runner is None:
            runner = _runner_from_env()
        if runner is None:
            raise LLMFacilityError("WRITER_PLANNING_BACKEND_UNCONFIGURED", "writer planning backend is not configured")
        activity.heartbeat("source")
        if mode == "dedup":
            result = runner.run_dedup(
                context=context,
                block_ids=payload.get("block_ids") if isinstance(payload.get("block_ids"), list) else [],
                chapter_id=payload.get("chapter_id"),
                persist_failure=False,
            )
        else:
            result = runner.run_book_plan(
                context=context,
                book_plan_id=_required_uuid(payload.get("book_plan_id"), "book_plan_id"),
                expected_version=payload.get("expected_version"),
                persist_failure=False,
            )
        activity.heartbeat("completed")
        return {**context.to_trace_payload(), **result}
    except Exception as exc:
        code, message = _stable_error(exc)
        raise ApplicationError(message, type=code, non_retryable=_non_retryable(code)) from exc


@activity.defn
def writer_planning_failure_activity(payload: dict[str, Any]) -> None:
    context = AgentContext.model_validate(payload.get("context", payload))
    database_url = os.environ.get("DATABASE_URL", "").strip()
    if not database_url:
        raise ApplicationError(
            "writer planning backend is not configured",
            type="WRITER_PLANNING_BACKEND_UNCONFIGURED",
            non_retryable=True,
        )
    PostgresWriterPlanningStore.from_database_url(database_url).fail_workflow(
        context=context,
        code=_public_text(payload.get("error_code"), 120),
        message="writer planning request failed",
        book_plan_id=_optional_uuid(payload.get("book_plan_id"), "book_plan_id"),
    )


@workflow.defn
class WriterDedupExtractionWorkflow:
    @workflow.run
    async def run(self, payload: dict[str, Any]) -> dict[str, Any]:
        return await _execute_planning_activity(writer_dedup_activity, payload)


@workflow.defn
class WriterBookPlanWorkflow:
    @workflow.run
    async def run(self, payload: dict[str, Any]) -> dict[str, Any]:
        return await _execute_planning_activity(writer_book_plan_activity, payload)


async def _execute_planning_activity(activity_fn: Any, payload: dict[str, Any]) -> dict[str, Any]:
    try:
        return await workflow.execute_activity(
            activity_fn,
            payload,
            start_to_close_timeout=timedelta(minutes=15),
            schedule_to_close_timeout=timedelta(hours=1),
            heartbeat_timeout=timedelta(seconds=30),
            retry_policy=RetryPolicy(
                initial_interval=timedelta(seconds=1),
                maximum_interval=timedelta(seconds=10),
                maximum_attempts=3,
            ),
        )
    except ActivityError as exc:
        cause = exc.cause
        code = cause.type if isinstance(cause, ApplicationError) and cause.type else "WRITER_PLANNING_FAILED"
        await workflow.execute_activity(
            writer_planning_failure_activity,
            {**payload, "error_code": code},
            start_to_close_timeout=timedelta(seconds=30),
            retry_policy=RetryPolicy(maximum_attempts=3),
        )
        raise ApplicationError("writer planning request failed", type=code, non_retryable=True) from exc


def worker_spec() -> dict[str, list[str] | str]:
    return {
        "task_queue": WRITER_PLANNING_TASK_QUEUE,
        "workflows": [WriterDedupExtractionWorkflow.__name__, WriterBookPlanWorkflow.__name__],
        "activities": [
            writer_dedup_activity.__name__,
            writer_book_plan_activity.__name__,
            writer_planning_failure_activity.__name__,
        ],
    }


def _public_result(result: dict[str, Any]) -> dict[str, Any]:
    return {key: result[key] for key in ("status", "replayed", "candidate_count", "book_plan_id", "candidate", "item_count", "version") if key in result}


def _stable_error(exc: Exception) -> tuple[str, str]:
    if isinstance(exc, LLMFacilityError):
        public = {
            "LLM_MODULE_UNBOUND", "LLM_BINDING_QUERY_FAILED", "LLM_CREDENTIAL_KEY_UNCONFIGURED",
            "LLM_CREDENTIAL_UNAVAILABLE", "LLM_CREDENTIAL_QUERY_FAILED", "LLM_CREDENTIAL_DECRYPT_FAILED",
            "LLM_CAPABILITY_UNSUPPORTED", "LLM_RESPONSE_SCHEMA_INVALID", "SCHEMA_VALIDATION_FAILED",
            "LLM_QUOTA_POLICY_UNAVAILABLE", "LLM_QUOTA_PRICING_UNAVAILABLE", "LLM_QUOTA_TOKENS_EXCEEDED",
            "LLM_QUOTA_COST_EXCEEDED", "LLM_QUOTA_CONCURRENCY_EXCEEDED", "LLM_QUOTA_BACKEND_FAILED",
            "LLM_QUOTA_RESERVE_FAILED", "LLM_QUOTA_FINALIZE_FAILED", "LLM_QUOTA_RELEASE_FAILED",
            "LLM_PROVIDER_USAGE_MISSING", "LLM_PROVIDER_CALL_CONFLICT", "WRITER_DEDUP_SOURCE_NOT_FOUND",
            "WRITER_DEDUP_SOURCE_LOAD_FAILED", "WRITER_DEDUP_PERSIST_FAILED", "BOOK_PLAN_NOT_FOUND",
            "BOOK_PLAN_CONFLICT", "BOOK_PLAN_SOURCE_LOAD_FAILED", "BOOK_PLAN_PERSIST_FAILED",
            "WRITER_PLANNING_NOT_FOUND", "WRITER_PLANNING_NOT_ACTIVE", "VALIDATION_FAILED", "FORBIDDEN",
        }
        if exc.code in public:
            return exc.code, {
                "LLM_RESPONSE_SCHEMA_INVALID": "writer planning response schema is invalid",
                "SCHEMA_VALIDATION_FAILED": "writer planning response schema is invalid",
                "LLM_PROVIDER_USAGE_MISSING": "writer planning provider usage is missing",
            }.get(exc.code, "writer planning request failed")
    return "WRITER_PLANNING_FAILED", "writer planning runtime failed"


def _non_retryable(code: str) -> bool:
    return code in {
        "VALIDATION_FAILED",
        "FORBIDDEN",
        "WRITER_DEDUP_SOURCE_NOT_FOUND",
        "BOOK_PLAN_NOT_FOUND",
        "BOOK_PLAN_CONFLICT",
        "WRITER_PLANNING_NOT_FOUND",
        "WRITER_PLANNING_NOT_ACTIVE",
        "LLM_MODULE_UNBOUND",
        "LLM_CREDENTIAL_KEY_UNCONFIGURED",
        "LLM_CAPABILITY_UNSUPPORTED",
        "LLM_RESPONSE_SCHEMA_INVALID",
        "SCHEMA_VALIDATION_FAILED",
    }


def _require_context(context: AgentContext, workflow_type: str, module_key: str) -> None:
    if context.workflow_type != workflow_type or context.module_key != module_key:
        raise LLMFacilityError("VALIDATION_FAILED", "writer planning workflow context is invalid")
    if not context.project_id or not context.actor_user_id:
        raise LLMFacilityError("VALIDATION_FAILED", "project_id and actor_user_id are required")
    _required_uuid(context.run_id, "run_id")


def _required_uuid(value: Any, field: str) -> str:
    try:
        return str(UUID(str(value).strip()))
    except (ValueError, AttributeError) as exc:
        raise LLMFacilityError("VALIDATION_FAILED", f"{field} must be a valid UUID") from exc


def _optional_uuid(value: Any, field: str) -> str | None:
    if value is None or (isinstance(value, str) and not value.strip()):
        return None
    return _required_uuid(value, field)


def _public_text(value: Any, maximum: int) -> str:
    if not isinstance(value, str) or not value.strip() or len(value.strip()) > maximum:
        raise _schema_error()
    text = value.strip()
    if any(marker in text.lower() for marker in ("api_key", "credential_ref", "content_text", "provider response")):
        raise _schema_error()
    return text


def _normalize_text(value: str) -> str:
    return " ".join(value.lower().split())


def _schema_error() -> LLMFacilityError:
    return LLMFacilityError("LLM_RESPONSE_SCHEMA_INVALID", "writer planning response schema is invalid")


def _rollback(connection: Any) -> None:
    try:
        connection.rollback()
    except Exception:
        pass
