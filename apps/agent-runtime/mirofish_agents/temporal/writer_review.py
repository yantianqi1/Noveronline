from __future__ import annotations

import json
import os
import re
import time
from datetime import timedelta
from typing import Any, Callable, Protocol
from uuid import UUID

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


WRITER_REVIEW_WORKFLOW_TYPE = "writer_review"
WRITER_REVIEW_MODULE_KEY = "writer_reviewer"
WRITER_REVIEW_TASK_QUEUE = "writer-reviewer"
WRITER_REVIEW_ACTIVITY_RETRY_POLICY = RetryPolicy(
    initial_interval=timedelta(seconds=5),
    backoff_coefficient=2.0,
    maximum_interval=timedelta(minutes=1),
    maximum_attempts=3,
)

_SEVERITIES = {"low", "medium", "high", "critical"}
_CATEGORIES = {
    "rhetoric_density",
    "scene_repetition",
    "pov_drift",
    "timeline_conflict",
    "phrase_repetition",
}
_ISSUE_FIELDS = {"severity", "category", "summary", "suggestion"}
_SENSITIVE_MARKERS = {
    "api_key",
    "credential_ref",
    "encrypted_api_key",
    "content_text",
    "draft text",
    "manuscript text",
    "prompt",
    "provider response",
}
_LONG_QUOTE = re.compile(r'["\u201c\u300c\u300e][^"\u201d\u300d\u300f]{20,}["\u201d\u300d\u300f]')


class WriterReviewStore(Protocol):
    def load_candidate(self, *, context: AgentContext, review_id: str, draft_id: str) -> dict[str, Any]: ...

    def complete_review(
        self,
        *,
        context: AgentContext,
        review_id: str,
        draft_id: str,
        resolution: ModuleBindingResolution,
        issues: list[dict[str, str]],
        usage: dict[str, int | float | None],
        latency_ms: int,
    ) -> dict[str, Any]: ...

    def fail_review(
        self,
        *,
        context: AgentContext,
        review_id: str,
        draft_id: str,
        code: str,
        message: str,
        resolution: ModuleBindingResolution | None,
        latency_ms: int,
    ) -> None: ...


class WriterReviewRunner(Protocol):
    def run_review(self, *, context: AgentContext, review_id: str, draft_id: str) -> dict[str, Any]: ...


class LLMFacilityWriterReviewRunner:
    def __init__(
        self,
        *,
        binding_resolver: ModuleBindingResolver,
        credential_provider: CredentialProvider,
        chat_client: JSONChatClient,
        store: WriterReviewStore,
    ) -> None:
        self._binding_resolver = binding_resolver
        self._credential_provider = credential_provider
        self._chat_client = chat_client
        self._store = store

    def run_review(self, *, context: AgentContext, review_id: str, draft_id: str) -> dict[str, Any]:
        started_at = time.monotonic()
        resolution: ModuleBindingResolution | None = None
        try:
            source = self._store.load_candidate(context=context, review_id=review_id, draft_id=draft_id)
            if source.get("replayed") is True:
                return _public_result(source)
            resolution = self._binding_resolver.resolve_module_binding(
                context=context, module_key=WRITER_REVIEW_MODULE_KEY
            )
            _validate_resolution(resolution)
            api_key = self._credential_provider.resolve_api_key(
                context=context, credential_ref=resolution.credential_ref
            )
            if not isinstance(api_key, str) or not api_key.strip():
                raise LLMFacilityError("LLM_CREDENTIAL_UNAVAILABLE", "resolved credential was empty")
            response = self._chat_client.complete_json(
                context=context,
                resolution=resolution,
                api_key=api_key.strip(),
                messages=_review_messages(draft_text=source["draft_text"]),
            )
            issues = validate_review_issues(response)
            result = self._store.complete_review(
                context=context,
                review_id=review_id,
                draft_id=draft_id,
                resolution=resolution,
                issues=issues,
                usage=_llm_usage(response),
                latency_ms=_latency_ms(started_at),
            )
            return _public_result(result)
        except Exception as exc:
            code, message = _stable_error(exc)
            try:
                self._store.fail_review(
                    context=context,
                    review_id=review_id,
                    draft_id=draft_id,
                    code=code,
                    message=message,
                    resolution=resolution,
                    latency_ms=_latency_ms(started_at),
                )
            except Exception:
                code, message = "WRITER_REVIEW_STATUS_WRITE_FAILED", "writer review status write failed"
            raise LLMFacilityError(code, message) from exc


class PostgresWriterReviewStore:
    def __init__(self, *, connect: Callable[[], Any]) -> None:
        self._connect = connect

    @classmethod
    def from_database_url(cls, database_url: str) -> "PostgresWriterReviewStore":
        try:
            import psycopg
        except ImportError as exc:  # pragma: no cover
            raise RuntimeError("psycopg is required for Writer reviewer runtime") from exc
        return cls(connect=lambda: psycopg.connect(database_url))

    def load_candidate(self, *, context: AgentContext, review_id: str, draft_id: str) -> dict[str, Any]:
        _require_context(context)
        review_id = _required_uuid(review_id, "review_id")
        draft_id = _required_uuid(draft_id, "draft_id")
        connection = self._connect()
        try:
            set_postgres_tenant_context(connection, context=context)
            with connection.cursor() as cursor:
                cursor.execute(
                    """SELECT review.status, draft.status, draft.content_text,
                              (SELECT count(*) FROM draft_review_issues issue
                               WHERE issue.tenant_id = review.tenant_id
                                 AND issue.project_id = review.project_id
                                 AND issue.review_id = review.review_id
                                 AND issue.draft_id = review.draft_id)
                       FROM draft_reviews review
                       JOIN workflow_runs workflow
                         ON workflow.tenant_id = review.tenant_id AND workflow.run_id = review.run_id
                        AND workflow.workflow_type = 'writer_review'
                       JOIN writer_drafts draft
                         ON draft.tenant_id = review.tenant_id
                        AND draft.project_id = review.project_id
                        AND draft.draft_id = review.draft_id
                       WHERE review.tenant_id = %s AND review.project_id = %s
                         AND review.review_id = %s AND review.draft_id = %s
                         AND review.run_id = %s
                       FOR UPDATE OF review, workflow""",
                    (context.tenant_id, context.project_id, review_id, draft_id, context.run_id),
                )
                row = cursor.fetchone()
                if row is None:
                    raise LLMFacilityError("WRITER_REVIEW_NOT_FOUND", "writer review admission was not found")
                if row[0] == "completed":
                    connection.commit()
                    return {
                        "status": "completed",
                        "replayed": True,
                        "review_id": review_id,
                        "draft_id": draft_id,
                        "issue_count": int(row[3]),
                    }
                if row[0] not in {"queued", "running"}:
                    raise LLMFacilityError("WRITER_REVIEW_NOT_ACTIVE", "writer review is not active")
                if row[1] != "candidate":
                    raise LLMFacilityError("DRAFT_NOT_CANDIDATE", "writer review requires a candidate draft")
                cursor.execute(
                    """UPDATE draft_reviews SET status = 'running', updated_at = now()
                       WHERE tenant_id = %s AND project_id = %s AND review_id = %s
                         AND status IN ('queued', 'running')""",
                    (context.tenant_id, context.project_id, review_id),
                )
                cursor.execute(
                    """UPDATE workflow_runs SET status = 'running', progress = 10,
                              message = 'writer review running', updated_at = now()
                       WHERE tenant_id = %s AND project_id = %s AND run_id = %s
                         AND workflow_type = 'writer_review' AND status IN ('queued', 'running')""",
                    (context.tenant_id, context.project_id, context.run_id),
                )
            connection.commit()
        except LLMFacilityError:
            _rollback(connection)
            raise
        except Exception as exc:
            _rollback(connection)
            raise LLMFacilityError("WRITER_REVIEW_SOURCE_LOAD_FAILED", "writer review source load failed") from exc
        finally:
            connection.close()
        return {"status": "running", "replayed": False, "draft_text": row[2]}

    def complete_review(
        self,
        *,
        context: AgentContext,
        review_id: str,
        draft_id: str,
        resolution: ModuleBindingResolution,
        issues: list[dict[str, str]],
        usage: dict[str, int | float | None],
        latency_ms: int,
    ) -> dict[str, Any]:
        connection = self._connect()
        try:
            set_postgres_tenant_context(connection, context=context)
            with connection.cursor() as cursor:
                cursor.execute(
                    """SELECT status FROM draft_reviews
                       WHERE tenant_id = %s AND project_id = %s AND review_id = %s
                         AND draft_id = %s AND run_id = %s FOR UPDATE""",
                    (context.tenant_id, context.project_id, review_id, draft_id, context.run_id),
                )
                row = cursor.fetchone()
                if row is None:
                    raise LLMFacilityError("WRITER_REVIEW_NOT_FOUND", "writer review admission was not found")
                if row[0] == "completed":
                    cursor.execute(
                        """SELECT count(*) FROM draft_review_issues
                           WHERE tenant_id = %s AND project_id = %s AND review_id = %s AND draft_id = %s""",
                        (context.tenant_id, context.project_id, review_id, draft_id),
                    )
                    count = int(cursor.fetchone()[0])
                    connection.commit()
                    return {"status": "completed", "replayed": True, "review_id": review_id, "draft_id": draft_id, "issue_count": count}
                if row[0] not in {"queued", "running"}:
                    raise LLMFacilityError("WRITER_REVIEW_NOT_ACTIVE", "writer review is not active")
                cursor.execute(
                    """SELECT count(*) FROM draft_review_issues
                       WHERE tenant_id = %s AND project_id = %s AND review_id = %s AND draft_id = %s""",
                    (context.tenant_id, context.project_id, review_id, draft_id),
                )
                if int(cursor.fetchone()[0]) != 0:
                    raise LLMFacilityError("WRITER_REVIEW_PARTIAL_ISSUES", "writer review has partial issues")
                for issue in issues:
                    cursor.execute(
                        """INSERT INTO draft_review_issues (
                             tenant_id, review_id, draft_id, project_id,
                             severity, category, summary, suggestion, status
                           ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, 'open')""",
                        (
                            context.tenant_id, review_id, draft_id, context.project_id,
                            issue["severity"], issue["category"], issue["summary"], issue["suggestion"],
                        ),
                    )
                cursor.execute(
                    """UPDATE draft_reviews SET status = 'completed', error_code = NULL,
                              error_message = NULL, updated_at = now()
                       WHERE tenant_id = %s AND project_id = %s AND review_id = %s""",
                    (context.tenant_id, context.project_id, review_id),
                )
                cursor.execute(
                    """UPDATE workflow_runs SET status = 'completed', progress = 100,
                              message = 'writer review completed',
                              result_jsonb = %s::jsonb, error_code = NULL, error_message = NULL,
                              updated_at = now()
                       WHERE tenant_id = %s AND project_id = %s AND run_id = %s
                         AND workflow_type = 'writer_review'""",
                    (
                        json.dumps({"review_id": review_id, "draft_id": draft_id, "issue_count": len(issues)}, separators=(",", ":")),
                        context.tenant_id, context.project_id, context.run_id,
                    ),
                )
                event = _completion_event(review_id, draft_id, issues, resolution.model_id)
                cursor.execute(
                    """INSERT INTO workflow_events (
                         tenant_id, run_id, workflow_type, project_id,
                         event_type, sequence, payload_jsonb
                       ) VALUES (%s, %s, 'writer_review', %s, 'writer.review.completed',
                                 (SELECT COALESCE(max(sequence), 0) + 1 FROM workflow_events
                                  WHERE tenant_id = %s AND run_id = %s), %s::jsonb)""",
                    (
                        context.tenant_id, context.run_id, context.project_id,
                        context.tenant_id, context.run_id,
                        json.dumps(event, separators=(",", ":")),
                    ),
                )
            connection.commit()
        except LLMFacilityError:
            _rollback(connection)
            raise
        except Exception as exc:
            _rollback(connection)
            raise LLMFacilityError("WRITER_REVIEW_PERSIST_FAILED", "writer review persistence failed") from exc
        finally:
            connection.close()
        return {"status": "completed", "replayed": False, "review_id": review_id, "draft_id": draft_id, "issue_count": len(issues), "model_id": resolution.model_id}

    def fail_review(
        self,
        *,
        context: AgentContext,
        review_id: str,
        draft_id: str,
        code: str,
        message: str,
        resolution: ModuleBindingResolution | None,
        latency_ms: int,
    ) -> None:
        connection = self._connect()
        try:
            set_postgres_tenant_context(connection, context=context)
            with connection.cursor() as cursor:
                cursor.execute(
                    """SELECT status FROM draft_reviews
                       WHERE tenant_id = %s AND project_id = %s AND review_id = %s
                         AND draft_id = %s AND run_id = %s FOR UPDATE""",
                    (context.tenant_id, context.project_id, review_id, draft_id, context.run_id),
                )
                row = cursor.fetchone()
                if row is None:
                    raise LLMFacilityError("WRITER_REVIEW_NOT_FOUND", "writer review admission was not found")
                if row[0] == "completed":
                    connection.commit()
                    return
                cursor.execute(
                    """DELETE FROM draft_review_issues
                       WHERE tenant_id = %s AND project_id = %s AND review_id = %s AND draft_id = %s""",
                    (context.tenant_id, context.project_id, review_id, draft_id),
                )
                cursor.execute(
                    """UPDATE draft_reviews SET status = 'failed', error_code = %s,
                              error_message = %s, updated_at = now()
                       WHERE tenant_id = %s AND project_id = %s AND review_id = %s""",
                    (code, message, context.tenant_id, context.project_id, review_id),
                )
                cursor.execute(
                    """UPDATE workflow_runs SET status = 'failed', progress = 0,
                              message = %s, error_code = %s, error_message = %s, updated_at = now()
                       WHERE tenant_id = %s AND project_id = %s AND run_id = %s
                         AND workflow_type = 'writer_review'""",
                    (message, code, message, context.tenant_id, context.project_id, context.run_id),
                )
                cursor.execute(
                    """INSERT INTO workflow_events (
                         tenant_id, run_id, workflow_type, project_id,
                         event_type, sequence, payload_jsonb
                       ) VALUES (%s, %s, 'writer_review', %s, 'writer.review.failed',
                                 (SELECT COALESCE(max(sequence), 0) + 1 FROM workflow_events
                                  WHERE tenant_id = %s AND run_id = %s), %s::jsonb)""",
                    (
                        context.tenant_id, context.run_id, context.project_id,
                        context.tenant_id, context.run_id,
                        json.dumps({"status": "failed", "review_id": review_id, "draft_id": draft_id, "issue_count": 0, "module_key": WRITER_REVIEW_MODULE_KEY, "error_code": code}, separators=(",", ":")),
                    ),
                )
            connection.commit()
        except LLMFacilityError:
            _rollback(connection)
            raise
        except Exception as exc:
            _rollback(connection)
            raise LLMFacilityError("WRITER_REVIEW_STATUS_WRITE_FAILED", "writer review status write failed") from exc
        finally:
            connection.close()


def validate_review_issues(response: dict[str, Any]) -> list[dict[str, str]]:
    allowed_root = {"issues", "__llm_usage"}
    if not isinstance(response, dict) or set(response) - allowed_root or "issues" not in response:
        raise LLMFacilityError("LLM_RESPONSE_SCHEMA_INVALID", "writer review response schema is invalid")
    raw_issues = response.get("issues")
    if not isinstance(raw_issues, list) or not raw_issues:
        raise LLMFacilityError("LLM_RESPONSE_SCHEMA_INVALID", "writer review issues must be a non-empty array")
    issues: list[dict[str, str]] = []
    seen: set[tuple[str, str]] = set()
    for raw in raw_issues:
        if not isinstance(raw, dict) or set(raw) != _ISSUE_FIELDS:
            raise LLMFacilityError("LLM_RESPONSE_SCHEMA_INVALID", "writer review issue fields are invalid")
        issue = {key: _required_public_text(raw.get(key), key) for key in _ISSUE_FIELDS}
        if issue["severity"] not in _SEVERITIES or issue["category"] not in _CATEGORIES:
            raise LLMFacilityError("LLM_RESPONSE_SCHEMA_INVALID", "writer review issue classification is invalid")
        duplicate_key = (issue["category"], " ".join(issue["summary"].lower().split()))
        if duplicate_key in seen:
            raise LLMFacilityError("LLM_RESPONSE_SCHEMA_INVALID", "writer review issues must be unique")
        seen.add(duplicate_key)
        issues.append(issue)
    return issues


def _required_public_text(value: Any, field: str) -> str:
    if not isinstance(value, str) or not value.strip() or len(value.strip()) > 1000:
        raise LLMFacilityError("LLM_RESPONSE_SCHEMA_INVALID", f"writer review {field} is invalid")
    text = value.strip()
    lowered = text.lower()
    if any(marker in lowered for marker in _SENSITIVE_MARKERS) or _LONG_QUOTE.search(text):
        raise LLMFacilityError("LLM_RESPONSE_SCHEMA_INVALID", "writer review issue contains sensitive quoted content")
    return text


def _review_messages(*, draft_text: str) -> list[dict[str, str]]:
    return [
        {
            "role": "system",
            "content": (
                "You are the independent MiroFish writer_reviewer module. Return exactly one JSON object "
                "with a non-empty issues array. Each issue must contain exactly severity, category, summary, "
                "and suggestion. severity is low|medium|high|critical. category is rhetoric_density, "
                "scene_repetition, pov_drift, timeline_conflict, or phrase_repetition. Summarize findings "
                "without quoting the draft. Do not rewrite, adopt, score, or return draft text."
            ),
        },
        {"role": "user", "content": draft_text},
    ]


def _validate_resolution(resolution: ModuleBindingResolution) -> None:
    if resolution.module_key != WRITER_REVIEW_MODULE_KEY:
        raise LLMFacilityError("LLM_MODULE_UNBOUND", "resolved module key does not match writer_reviewer")
    if not resolution.supports_json:
        raise LLMFacilityError("LLM_CAPABILITY_UNSUPPORTED", "writer_reviewer requires a JSON-capable model")
    for field in ("channel_id", "model_id", "provider", "base_url", "credential_ref"):
        if not isinstance(getattr(resolution, field), str) or not getattr(resolution, field).strip():
            raise LLMFacilityError("LLM_PROVIDER_ERROR", f"resolved LLM module is missing {field}")


def _completion_event(review_id: str, draft_id: str, issues: list[dict[str, str]], model_id: str) -> dict[str, Any]:
    severity_counts = {severity: sum(1 for issue in issues if issue["severity"] == severity) for severity in sorted(_SEVERITIES)}
    category_counts = {category: sum(1 for issue in issues if issue["category"] == category) for category in sorted(_CATEGORIES)}
    return {
        "status": "completed", "review_id": review_id, "draft_id": draft_id,
        "issue_count": len(issues), "severity_counts": severity_counts,
        "category_counts": category_counts, "module_key": WRITER_REVIEW_MODULE_KEY,
        "model_id": model_id,
    }


def _public_result(result: dict[str, Any]) -> dict[str, Any]:
    return {
        key: result[key]
        for key in ("status", "replayed", "review_id", "draft_id", "issue_count", "model_id")
        if key in result
    }


def _llm_usage(response: dict[str, Any]) -> dict[str, int | float | None]:
    usage = response.get("__llm_usage")
    if not isinstance(usage, dict):
        return {}
    result: dict[str, int | float | None] = {}
    for key in ("prompt_tokens", "completion_tokens", "total_tokens"):
        value = usage.get(key)
        result[key] = value if isinstance(value, int) and not isinstance(value, bool) and value >= 0 else None
    cost = usage.get("cost_estimate")
    result["cost_estimate"] = float(cost) if isinstance(cost, (int, float)) and not isinstance(cost, bool) and cost >= 0 else None
    return result


def _stable_error(exc: Exception) -> tuple[str, str]:
    if isinstance(exc, LLMFacilityError):
        messages = {
            "LLM_MODULE_UNBOUND": "writer_reviewer module is not bound",
            "LLM_BINDING_QUERY_FAILED": "LLM module binding query failed",
            "LLM_CREDENTIAL_KEY_UNCONFIGURED": "LLM credential encryption key is not configured",
            "LLM_CREDENTIAL_UNAVAILABLE": "LLM credential is unavailable",
            "LLM_CREDENTIAL_QUERY_FAILED": "LLM credential query failed",
            "LLM_CREDENTIAL_DECRYPT_FAILED": "LLM credential decrypt failed",
            "LLM_PROVIDER_ERROR": "writer reviewer provider call failed",
            "LLM_CAPABILITY_UNSUPPORTED": "writer_reviewer requires a JSON-capable model",
            "LLM_RESPONSE_SCHEMA_INVALID": "writer review response schema is invalid",
            "SCHEMA_VALIDATION_FAILED": "writer review response schema is invalid",
            "WRITER_REVIEW_NOT_FOUND": "writer review admission was not found",
            "WRITER_REVIEW_NOT_ACTIVE": "writer review is not active",
            "DRAFT_NOT_CANDIDATE": "writer review requires a candidate draft",
            "WRITER_REVIEW_SOURCE_LOAD_FAILED": "writer review source load failed",
            "WRITER_REVIEW_PERSIST_FAILED": "writer review persistence failed",
            "WRITER_REVIEW_PARTIAL_ISSUES": "writer review has partial issues",
            "WRITER_REVIEW_PROVIDER_REPLAY_BLOCKED": "writer review provider call was already started",
            "LLM_TELEMETRY_WRITE_FAILED": "writer review telemetry write failed",
            "LLM_QUOTA_POLICY_UNAVAILABLE": "writer reviewer LLM quota policy is unavailable",
            "LLM_QUOTA_PRICING_UNAVAILABLE": "writer reviewer LLM pricing is required by the active quota policy",
            "LLM_QUOTA_TOKENS_EXCEEDED": "writer reviewer LLM token quota exceeded",
            "LLM_QUOTA_COST_EXCEEDED": "writer reviewer LLM cost quota exceeded",
            "LLM_QUOTA_CONCURRENCY_EXCEEDED": "writer reviewer LLM concurrency quota exceeded",
            "LLM_QUOTA_BACKEND_FAILED": "writer reviewer LLM quota backend failed",
            "LLM_QUOTA_RESERVE_FAILED": "writer reviewer LLM quota reservation failed",
            "LLM_QUOTA_FINALIZE_FAILED": "writer reviewer LLM quota finalization failed",
            "LLM_QUOTA_RELEASE_FAILED": "writer reviewer LLM quota release failed",
            "LLM_QUOTA_CONFIG_INVALID": "writer reviewer LLM quota configuration is invalid",
            "LLM_QUOTA_RESERVATION_UNAVAILABLE": "writer reviewer LLM quota reservation is unavailable",
            "LLM_QUOTA_RESERVATION_CLOSED": "writer reviewer LLM quota reservation is closed",
            "LLM_QUOTA_RESERVATION_NOT_FOUND": "writer reviewer LLM quota reservation was not found",
            "LLM_USAGE_EXCEEDS_RESERVATION": "writer reviewer LLM usage exceeded its reservation",
            "LLM_USAGE_DATA_INVALID": "writer reviewer LLM usage data is invalid",
            "LLM_PROVIDER_USAGE_MISSING": "writer reviewer provider usage is missing",
            "LLM_MODEL_PRICING_UNAVAILABLE": "writer reviewer model pricing is unavailable",
            "LLM_MODEL_PRICING_INVALID": "writer reviewer model pricing is invalid",
            "LLM_CHANNEL_UNAVAILABLE": "writer reviewer LLM channel is unavailable",
            "LLM_PROVIDER_CALL_CONFLICT": "writer reviewer provider call identity conflicts with its reservation",
            "VALIDATION_FAILED": "writer review request is invalid",
        }
        if exc.code in messages:
            return exc.code, messages[exc.code]
    return "WRITER_REVIEW_FAILED", "writer review runtime failed"


def _require_context(context: AgentContext) -> None:
    if not context.project_id or not context.actor_user_id:
        raise LLMFacilityError("VALIDATION_FAILED", "project_id and actor_user_id are required")
    _required_uuid(context.run_id, "run_id")


def _required_uuid(value: Any, field: str) -> str:
    try:
        return str(UUID(str(value).strip()))
    except (ValueError, AttributeError) as exc:
        raise LLMFacilityError("VALIDATION_FAILED", f"{field} must be a valid UUID") from exc


def _latency_ms(started_at: float) -> int:
    return max(0, int((time.monotonic() - started_at) * 1000))


def _rollback(connection: Any) -> None:
    try:
        connection.rollback()
    except Exception:
        pass


def _runner_from_env() -> WriterReviewRunner | None:
    database_url = os.environ.get("DATABASE_URL", "").strip()
    if not database_url:
        return None
    from mirofish_agents.llm_quota import (
        PostgresQuotaStore,
        ProviderQuotaGate,
        QuotaAwareJSONChatClient,
        QuotaEnforcedJSONChatClient,
    )

    store = PostgresWriterReviewStore.from_database_url(database_url)
    return LLMFacilityWriterReviewRunner(
        binding_resolver=PostgresModuleBindingResolver.from_database_url(database_url),
        credential_provider=PostgresCredentialProvider.from_database_url(
            database_url=database_url,
            key_material=os.environ.get("LLM_CREDENTIAL_ENCRYPTION_KEY"),
        ),
        chat_client=QuotaEnforcedJSONChatClient(
            quota_gate=ProviderQuotaGate(PostgresQuotaStore.from_database_url(database_url)),
            stage_prefix=WRITER_REVIEW_MODULE_KEY,
            provider_client=QuotaAwareJSONChatClient(),
        ),
        store=store,
    )


@activity.defn
def writer_review_activity(payload: dict[str, Any], runner: WriterReviewRunner | None = None) -> dict[str, Any]:
    try:
        context = AgentContext.model_validate(payload.get("context", payload))
        review_id = _required_uuid(payload.get("review_id"), "review_id")
        draft_id = _required_uuid(payload.get("draft_id"), "draft_id")
        if context.workflow_type != WRITER_REVIEW_WORKFLOW_TYPE or context.module_key != WRITER_REVIEW_MODULE_KEY:
            raise LLMFacilityError("VALIDATION_FAILED", "invalid writer review workflow context")
        if not context.has_permission(WRITER_REVIEW_MODULE_KEY, "run"):
            raise LLMFacilityError("FORBIDDEN", "writer_reviewer run permission is required")
        if runner is None:
            runner = _runner_from_env()
        if runner is None:
            raise LLMFacilityError("WRITER_REVIEW_BACKEND_UNCONFIGURED", "writer review backend is not configured")
        return {**context.to_trace_payload(), **runner.run_review(context=context, review_id=review_id, draft_id=draft_id)}
    except Exception as exc:
        code, message = _stable_error(exc)
        return {"status": "failed", "stage": "writer_review", "module_key": WRITER_REVIEW_MODULE_KEY, "error": {"code": code, "message": message}}


@workflow.defn
class WriterReviewWorkflow:
    @workflow.run
    async def run(self, payload: dict[str, Any]) -> dict[str, Any]:
        return await workflow.execute_activity(
            writer_review_activity,
            payload,
            start_to_close_timeout=timedelta(minutes=15),
            schedule_to_close_timeout=timedelta(hours=1),
            retry_policy=WRITER_REVIEW_ACTIVITY_RETRY_POLICY,
        )


def run_writer_review_workflow_locally(payload: dict[str, Any], *, runner: WriterReviewRunner | None = None) -> dict[str, Any]:
    return writer_review_activity(payload, runner=runner)


def worker_spec() -> dict[str, list[str] | str]:
    return {
        "task_queue": WRITER_REVIEW_TASK_QUEUE,
        "workflows": [WriterReviewWorkflow.__name__],
        "activities": [writer_review_activity.__name__],
    }
