from __future__ import annotations

import hashlib
import hmac
import json
import os
import re
import uuid
from datetime import datetime, timedelta, timezone
from io import BytesIO
from typing import Any, Callable, Protocol
from urllib.parse import quote
from urllib.request import Request, urlopen

from temporalio import activity, workflow

from mirofish_agents.common.context import AgentContext
from mirofish_agents.seed.pdf_ocr import (
    PdfOcrBackend,
    PdfOcrBackendUnconfiguredError,
    PdfOcrError,
    PdfOcrProviderError,
    configured_pdf_ocr_backend,
)
from mirofish_agents.seed.sequential_reader import LLMFacilityError


with workflow.unsafe.imports_passed_through():
    from pypdf import PdfReader
    from pypdf.errors import PyPdfError


SEED_TASK_QUEUE = "seed-heavy"
SENSITIVE_WORKFLOW_EVENT_KEYS = {
    "api_key",
    "artifact_object_key",
    "body",
    "content",
    "credential_ref",
    "draft",
    "encrypted_api_key",
    "manuscript",
    "object_key",
    "prompt",
    "provider_raw_body",
    "provider_response",
    "raw_body",
    "raw_content",
    "response",
    "segment_object_key",
    "source_object_key",
}


SENSITIVE_ARCHIVE_CANDIDATE_KEYS = {
    *SENSITIVE_WORKFLOW_EVENT_KEYS,
    "body_text",
    "content_text",
    "encrypted_credential",
    "material_text",
    "raw_text",
    "source_material",
    "source_text",
    "text",
}
SENSITIVE_SEED_ANALYSIS_KEYS = {
    *SENSITIVE_WORKFLOW_EVENT_KEYS,
    "body_text",
    "content_text",
    "encrypted_credential",
    "evidence",
    "evidence_quotes",
    "evidence_text",
    "excerpt",
    "material_text",
    "quote",
    "quotes",
    "raw_text",
    "source_material",
    "source_text",
    "text",
}
NORMALIZED_SENSITIVE_SEED_ANALYSIS_KEYS = {
    re.sub(r"[^a-z0-9]", "", key)
    for key in SENSITIVE_SEED_ANALYSIS_KEYS
}
SEQUENTIAL_READING_PAYLOAD_LIST_FIELDS = (
    "characters",
    "organizations",
    "relationships",
    "plot_threads",
    "world_rules",
    "events",
    "consistency_notes",
)
OPTIONAL_SEQUENTIAL_READING_PAYLOAD_LIST_FIELDS = ("narrative_arcs", "volume_summaries")
GLOBAL_AGGREGATION_MODULE_KEY = "anchor_point_summary"
PUBLIC_GLOBAL_AGGREGATION_ERROR_CODES = {
    "GLOBAL_AGGREGATOR_CONFIGURATION_FAILED",
    "GLOBAL_AGGREGATOR_UNCONFIGURED",
    "LLM_CONCURRENCY_LIMITED",
    "LLM_CREDENTIAL_DECRYPT_FAILED",
    "LLM_CREDENTIAL_KEY_INVALID",
    "LLM_CREDENTIAL_KEY_UNCONFIGURED",
    "LLM_CREDENTIAL_UNAVAILABLE",
    "LLM_MODULE_UNBOUND",
    "LLM_PROVIDER_ERROR",
    "SCHEMA_VALIDATION_FAILED",
    "SEED_AGGREGATE_SOURCE_QUERY_FAILED",
    "SEED_ANALYSIS_WRITE_FAILED",
}
STORY_ONTOLOGY_MODULE_KEY = "story_ontology"
ENTITY_RESOLUTION_MODULE_KEY = "entity_resolution"
CHARACTER_AGENT_PROFILE_MODULE_KEY = "character_agent_profile"
NARRATIVE_ARCHIVES_MODULE_KEY = "narrative_archives"
UNHEADED_SEGMENT_TARGET_CHARS = 2400


class WorkflowEventWriter(Protocol):
    def record_workflow_event(
        self,
        *,
        context: AgentContext,
        event_type: str,
        payload: dict[str, object],
    ) -> None:
        """Persist a public workflow event for the current tenant/project/run."""


class TextSegmentWriter(Protocol):
    def record_text_segments(
        self,
        *,
        context: AgentContext,
        source_file_id: str,
        segments: list[dict[str, Any]],
    ) -> None:
        """Persist text segment metadata for the current tenant/project/run."""


class TextArtifactWriter(Protocol):
    def record_text_artifact(
        self,
        *,
        context: AgentContext,
        source_file_id: str,
        artifact_type: str,
        object_key: str,
        char_count: int,
        line_count: int,
        sha256: str | None = None,
        metadata_jsonb: dict[str, Any] | None = None,
    ) -> None:
        """Persist an extracted/normalized text object reference for the current run."""


class SourceFileStatusWriter(Protocol):
    def mark_source_file_status(
        self,
        *,
        context: AgentContext,
        source_file_id: str,
        parse_status: str,
    ) -> None:
        """Persist a source file parse lifecycle status for the current tenant/project."""


class WorkflowRunStatusWriter(Protocol):
    def mark_running(
        self,
        *,
        context: AgentContext,
    ) -> None:
        """Mark the admitted Seed workflow run running after the worker accepts it."""

    def mark_completed(
        self,
        *,
        context: AgentContext,
        result: dict[str, Any],
    ) -> None:
        """Mark the admitted Seed workflow run completed with public result metadata."""

    def mark_failed(
        self,
        *,
        context: AgentContext,
        code: str,
        message: str,
    ) -> None:
        """Mark the admitted Seed workflow run failed with a stable public error."""


class SeedSegmentRetryStatusWriter(Protocol):
    def mark_seed_segment_retries(
        self,
        *,
        context: AgentContext,
        segment_ids: list[str],
        retry_attempt_id: str | None = None,
        worker_attempt: int = 1,
        status: str,
        code: str | None = None,
        message: str | None = None,
    ) -> None:
        """Persist per-segment retry request lifecycle status for the current run."""


class SeedSegmentRetryStore(SeedSegmentRetryStatusWriter, Protocol):
    def claim_seed_segment_retries(
        self,
        *,
        context: AgentContext,
        segment_ids: list[str],
        retry_attempt_id: str | None = None,
        worker_attempt: int = 1,
    ) -> list[dict[str, Any]]:
        """Claim requested retry rows and return same-run text segment refs."""


class _UnavailableWorkflowRunStatusWriter:
    def mark_running(
        self,
        *,
        context: AgentContext,
    ) -> None:
        raise RuntimeError("workflow status writer is unavailable")

    def mark_completed(
        self,
        *,
        context: AgentContext,
        result: dict[str, Any],
    ) -> None:
        raise RuntimeError("workflow status writer is unavailable")

    def mark_failed(
        self,
        *,
        context: AgentContext,
        code: str,
        message: str,
    ) -> None:
        raise RuntimeError("workflow status writer is unavailable")


class ObjectStore(Protocol):
    def read_bytes(self, object_key: str) -> bytes:
        """Read an object from the configured private source bucket."""

    def write_bytes(self, object_key: str, data: bytes, content_type: str) -> None:
        """Write an object to the configured private artifact bucket."""


class S3CompatibleObjectStore:
    def __init__(
        self,
        *,
        endpoint: str,
        bucket: str,
        access_key: str,
        secret_key: str,
        use_ssl: bool,
        region: str = "us-east-1",
        http_request: Callable[[Request], bytes] | None = None,
    ) -> None:
        normalized_endpoint = endpoint.strip().rstrip("/")
        normalized_bucket = bucket.strip()
        normalized_access_key = access_key.strip()
        normalized_secret_key = secret_key.strip()
        normalized_region = region.strip() or "us-east-1"
        if not normalized_endpoint or not normalized_bucket or not normalized_access_key or not normalized_secret_key:
            raise ValueError("object storage endpoint, bucket, access key, and signing credential are required")
        if normalized_endpoint.startswith(("http://", "https://")):
            self.endpoint_url = normalized_endpoint
        else:
            scheme = "https" if use_ssl else "http"
            self.endpoint_url = f"{scheme}://{normalized_endpoint}"
        self.bucket = normalized_bucket
        self._access_key = normalized_access_key
        self._secret_key = normalized_secret_key
        self._region = normalized_region
        self._http_request = http_request or _urlopen_bytes

    def read_bytes(self, object_key: str) -> bytes:
        request = self._signed_request("GET", object_key, b"", None)
        return self._http_request(request)

    def write_bytes(self, object_key: str, data: bytes, content_type: str) -> None:
        request = self._signed_request("PUT", object_key, data, content_type)
        self._http_request(request)

    def _signed_request(
        self,
        method: str,
        object_key: str,
        body: bytes,
        content_type: str | None,
    ) -> Request:
        normalized_key = _required_text_value(object_key, "object_key")
        encoded_path = f"/{quote(self.bucket, safe='')}/{quote(normalized_key, safe='/')}"
        url = f"{self.endpoint_url}{encoded_path}"
        now = datetime.now(timezone.utc)
        amz_date = now.strftime("%Y%m%dT%H%M%SZ")
        date_stamp = now.strftime("%Y%m%d")
        payload_hash = hashlib.sha256(body).hexdigest()
        host = self.endpoint_url.split("://", 1)[1]
        headers = {
            "host": host,
            "x-amz-content-sha256": payload_hash,
            "x-amz-date": amz_date,
        }
        if content_type is not None:
            headers["content-type"] = content_type
        canonical_headers = "".join(f"{key}:{headers[key]}\n" for key in sorted(headers))
        signed_headers = ";".join(sorted(headers))
        canonical_request = "\n".join(
            [
                method,
                encoded_path,
                "",
                canonical_headers,
                signed_headers,
                payload_hash,
            ]
        )
        credential_scope = f"{date_stamp}/{self._region}/s3/aws4_request"
        string_to_sign = "\n".join(
            [
                "AWS4-HMAC-SHA256",
                amz_date,
                credential_scope,
                hashlib.sha256(canonical_request.encode("utf-8")).hexdigest(),
            ]
        )
        signature = hmac.new(
            _aws_v4_signing_key(self._secret_key, date_stamp, self._region),
            string_to_sign.encode("utf-8"),
            hashlib.sha256,
        ).hexdigest()
        request_headers = {
            "Authorization": (
                "AWS4-HMAC-SHA256 "
                f"Credential={self._access_key}/{credential_scope}, "
                f"SignedHeaders={signed_headers}, Signature={signature}"
            ),
            "Host": host,
            "X-Amz-Content-Sha256": payload_hash,
            "X-Amz-Date": amz_date,
        }
        if content_type is not None:
            request_headers["Content-Type"] = content_type
        return Request(url, data=body if method != "GET" else None, headers=request_headers, method=method)


class ReadingNotesWriter(Protocol):
    def record_reading_notes(
        self,
        *,
        context: AgentContext,
        pass_id: str,
        pass_type: str,
        status: str,
        module_key: str | None,
        model_id: str | None,
        notes: list[dict[str, Any]],
        metadata_jsonb: dict[str, Any] | None = None,
    ) -> None:
        """Persist reading pass metadata and per-segment notes."""


class RuntimeFactsWriter(Protocol):
    def record_runtime_facts(
        self,
        *,
        context: AgentContext,
        reading_notes: list[dict[str, Any]] | None = None,
    ) -> dict[str, int]:
        """Persist structured canon facts from schema-validated reading notes."""


class SeedAnalysisWriter(Protocol):
    def record_seed_analysis(
        self,
        *,
        context: AgentContext,
        module_key: str,
        model_id: str | None,
        segment_count: int,
        summary_count: int,
        seed_analysis: dict[str, Any],
    ) -> str:
        """Persist a private seed analysis snapshot and return its public id."""


class OntologySnapshotWriter(Protocol):
    def record_ontology_snapshot(
        self,
        *,
        context: AgentContext,
        module_key: str,
        model_id: str | None,
        seed_ontology: dict[str, Any],
        entity_type_count: int,
        relationship_type_count: int,
        world_rule_type_count: int,
    ) -> str:
        """Persist a private ontology snapshot and return its public id."""


class EntityResolutionSnapshotWriter(Protocol):
    def record_entity_resolution_snapshot(
        self,
        *,
        context: AgentContext,
        module_key: str,
        model_id: str | None,
        entity_resolution: dict[str, Any],
        merged_entity_count: int,
        alias_count: int,
        conflict_count: int,
    ) -> str:
        """Persist a private entity resolution snapshot and return its public id."""


class AgentProfileSnapshotWriter(Protocol):
    def record_agent_profile_snapshot(
        self,
        *,
        context: AgentContext,
        module_key: str,
        model_id: str | None,
        agent_profiles: dict[str, Any],
        profile_count: int,
        memory_seed_count: int,
        relationship_view_count: int,
    ) -> str:
        """Persist a private character-agent profile snapshot and return its public id."""


class AgentProfileContextLoader(Protocol):
    def load_context(
        self,
        *,
        context: AgentContext,
    ) -> dict[str, Any]:
        """Load sanitized Seed canon context for character agent profile generation."""


class GlobalAggregationRunner(Protocol):
    def aggregate(
        self,
        *,
        context: AgentContext,
        module_key: str,
    ) -> dict[str, Any]:
        """Run the LLM-bound global aggregation stage through LLM Facility."""


class OntologyRunner(Protocol):
    def generate(
        self,
        *,
        context: AgentContext,
        module_key: str,
    ) -> dict[str, Any]:
        """Run and persist story ontology generation through LLM Facility."""


class EntityResolutionRunner(Protocol):
    def resolve(
        self,
        *,
        context: AgentContext,
        module_key: str,
    ) -> dict[str, Any]:
        """Run and persist entity resolution through LLM Facility."""


class AgentProfileRunner(Protocol):
    def generate(
        self,
        *,
        context: AgentContext,
        module_key: str,
    ) -> dict[str, Any]:
        """Run and persist character agent profile generation through LLM Facility."""


class ArchiveCandidateRunner(Protocol):
    def generate(
        self,
        *,
        context: AgentContext,
        module_key: str,
    ) -> dict[str, Any]:
        """Run and persist archive candidate generation through LLM Facility."""


class ArchiveCandidateWriter(Protocol):
    def write_archive_candidates(
        self,
        *,
        context: AgentContext,
        archive_candidate_batch_id: str,
        model_id: str | None,
        archive_entities: list[dict[str, Any]],
    ) -> dict[str, Any]:
        """Persist archive entity and memory candidates for explicit review."""


class AssetIndexer(Protocol):
    def index(
        self,
        *,
        context: AgentContext,
    ) -> dict[str, Any]:
        """Index seed-produced assets/search documents for the current run."""


class ProjectReadinessUpdater(Protocol):
    def update(
        self,
        *,
        context: AgentContext,
    ) -> dict[str, Any]:
        """Update project readiness metadata after seed assets are indexed."""


class SequentialReadingReader(Protocol):
    def read_segments(
        self,
        *,
        context: AgentContext,
        module_key: str,
        segments: list[dict[str, Any]],
        progress_callback: Callable[..., None] | None = None,
    ) -> dict[str, Any]:
        """Run the LLM-bound sequential reading stage through LLM Facility."""


class PostgresWorkflowEventWriter:
    def __init__(self, *, connect: Callable[[], Any]) -> None:
        self._connect = connect

    @classmethod
    def from_database_url(cls, database_url: str) -> "PostgresWorkflowEventWriter":
        try:
            import psycopg
        except ImportError as exc:  # pragma: no cover - depends on optional runtime packaging
            raise RuntimeError("psycopg is required for DATABASE_URL workflow event persistence") from exc

        return cls(connect=lambda: psycopg.connect(database_url))

    def record_workflow_event(
        self,
        *,
        context: AgentContext,
        event_type: str,
        payload: dict[str, object],
    ) -> None:
        sanitized_payload = _sanitize_workflow_event_payload(payload)
        connection = self._connect()
        try:
            with connection.cursor() as cursor:
                _set_postgres_tenant_context(cursor, context)
                cursor.execute(
                    """INSERT INTO workflow_events (
                         tenant_id, run_id, workflow_type, project_id, event_type, sequence, payload_jsonb
                       )
                       SELECT
                         %s, %s, %s, %s, %s,
                         COALESCE(MAX(sequence), 0) + 1,
                         %s::jsonb
                       FROM workflow_events
                       WHERE tenant_id = %s
                         AND run_id = %s""",
                    (
                        context.tenant_id,
                        context.run_id,
                        context.workflow_type,
                        context.project_id,
                        event_type,
                        json.dumps(sanitized_payload, ensure_ascii=False, separators=(",", ":")),
                        context.tenant_id,
                        context.run_id,
                    ),
                )
            connection.commit()
            # Keep workflow_runs.progress monotonic with stage events for Overview polling.
            if event_type in {"seed.stage.completed", "seed.stage.pending"}:
                stage = str(sanitized_payload.get("stage") or "")
                phase = "completed" if event_type.endswith("completed") else "pending"
                if stage:
                    _bump_seed_stage_progress(context=context, stage=stage, phase=phase)
            elif event_type == "seed.sequential_reading.progress":
                _bump_sequential_reading_batch_progress(context=context, payload=sanitized_payload)
        except Exception:
            _rollback_postgres_connection(connection)
            raise
        finally:
            connection.close()


class PostgresTextArtifactWriter:
    def __init__(self, *, connect: Callable[[], Any]) -> None:
        self._connect = connect

    @classmethod
    def from_database_url(cls, database_url: str) -> "PostgresTextArtifactWriter":
        try:
            import psycopg
        except ImportError as exc:  # pragma: no cover - depends on optional runtime packaging
            raise RuntimeError("psycopg is required for DATABASE_URL text artifact persistence") from exc

        return cls(connect=lambda: psycopg.connect(database_url))

    def record_text_artifact(
        self,
        *,
        context: AgentContext,
        source_file_id: str,
        artifact_type: str,
        object_key: str,
        char_count: int,
        line_count: int,
        sha256: str | None = None,
        metadata_jsonb: dict[str, Any] | None = None,
    ) -> None:
        if context.project_id is None:
            raise ValueError("project_id is required to persist text artifacts")
        normalized_source_file_id = _required_text_value(source_file_id, "source_file_id")
        normalized_artifact_type = _required_artifact_type(artifact_type)
        normalized_object_key = _required_text_value(object_key, "object_key")
        normalized_sha256 = sha256.strip() if isinstance(sha256, str) and sha256.strip() else None
        # Accepting metadata_jsonb lets parse activities pass raw result objects without risking DB storage.
        _ = _json_object(metadata_jsonb or {})

        connection = self._connect()
        try:
            with connection.cursor() as cursor:
                _set_postgres_tenant_context(cursor, context)
                cursor.execute(
                    """INSERT INTO project_text_artifacts (
                         tenant_id, project_id, run_id, source_file_id, artifact_type,
                         object_key, char_count, line_count, sha256
                       )
                       VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
                       ON CONFLICT (tenant_id, project_id, run_id, artifact_type, object_key)
                       DO UPDATE SET
                         source_file_id = EXCLUDED.source_file_id,
                         char_count = EXCLUDED.char_count,
                         line_count = EXCLUDED.line_count,
                         sha256 = EXCLUDED.sha256,
                         updated_at = now()""",
                    (
                        context.tenant_id,
                        context.project_id,
                        context.run_id,
                        normalized_source_file_id,
                        normalized_artifact_type,
                        normalized_object_key,
                        _non_negative_int(char_count, "char_count"),
                        _non_negative_int(line_count, "line_count"),
                        normalized_sha256,
                    ),
                )
            connection.commit()
        except Exception:
            _rollback_postgres_connection(connection)
            raise
        finally:
            connection.close()


class PostgresSourceFileStatusWriter:
    def __init__(self, *, connect: Callable[[], Any]) -> None:
        self._connect = connect

    @classmethod
    def from_database_url(cls, database_url: str) -> "PostgresSourceFileStatusWriter":
        try:
            import psycopg
        except ImportError as exc:  # pragma: no cover - depends on optional runtime packaging
            raise RuntimeError("psycopg is required for DATABASE_URL source file status persistence") from exc

        return cls(connect=lambda: psycopg.connect(database_url))

    def mark_source_file_status(
        self,
        *,
        context: AgentContext,
        source_file_id: str,
        parse_status: str,
    ) -> None:
        if context.project_id is None:
            raise LLMFacilityError("VALIDATION_FAILED", "project_id is required to update source file status")
        normalized_source_file_id = _required_text_value(source_file_id, "source_file_id")
        normalized_status = _required_source_parse_status(parse_status)
        connection = self._connect()
        try:
            with connection.cursor() as cursor:
                _set_postgres_tenant_context(cursor, context)
                cursor.execute(
                    """UPDATE source_files
                       SET parse_status = %s,
                           updated_at = now()
                       WHERE tenant_id = %s
                         AND project_id = %s
                         AND file_id = %s
                         AND parse_status = %s""",
                    (
                        normalized_status,
                        context.tenant_id,
                        context.project_id,
                        normalized_source_file_id,
                        "parsing",
                    ),
                )
                if getattr(cursor, "rowcount", 1) == 0:
                    raise LLMFacilityError(
                        "SOURCE_FILE_PARSE_STATUS_UPDATE_FAILED",
                        "source file parse status update failed",
                    )
            connection.commit()
        except LLMFacilityError:
            _rollback_postgres_connection(connection)
            raise
        except Exception as exc:
            _rollback_postgres_connection(connection)
            raise LLMFacilityError(
                "SOURCE_FILE_PARSE_STATUS_UPDATE_FAILED",
                "source file parse status update failed",
            ) from exc
        finally:
            connection.close()


class PostgresSeedWorkflowRunStatusWriter:
    def __init__(self, *, connect: Callable[[], Any]) -> None:
        self._connect = connect

    @classmethod
    def from_database_url(cls, database_url: str) -> "PostgresSeedWorkflowRunStatusWriter":
        try:
            import psycopg
            from psycopg.rows import dict_row
        except ImportError as exc:  # pragma: no cover - depends on optional runtime packaging
            raise RuntimeError("psycopg is required for DATABASE_URL seed workflow status writes") from exc

        return cls(connect=lambda: psycopg.connect(database_url, row_factory=dict_row))

    def mark_running(
        self,
        *,
        context: AgentContext,
    ) -> None:
        self._update_status(
            context=context,
            status="running",
            result=None,
            code=None,
            message=None,
            progress=5,
        )

    def mark_stage_progress(
        self,
        *,
        context: AgentContext,
        stage: str,
        status: str = "running",
        message: str | None = None,
    ) -> None:
        self._update_status(
            context=context,
            status=status if status in {"queued", "running", "completed", "failed", "cancelled"} else "running",
            result=None,
            code=None,
            message=message or f"seed stage {stage}",
            progress=_seed_stage_progress(stage, terminal=status in {"completed", "failed"}),
        )

    def mark_completed(
        self,
        *,
        context: AgentContext,
        result: dict[str, Any],
    ) -> None:
        self._update_status(
            context=context,
            status="completed",
            result=_public_seed_workflow_status_result(result),
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
        progress: int | None = None,
    ) -> None:
        if context.project_id is None:
            raise LLMFacilityError("WORKFLOW_RUN_NOT_FOUND", "seed workflow admission parent row is missing")
        encoded_result = json.dumps(result, ensure_ascii=False, separators=(",", ":")) if result is not None else None
        connection = self._connect()
        missing_parent = False
        resolved_progress = progress
        if resolved_progress is None:
            if status in {"completed", "failed"}:
                resolved_progress = 100
            elif status == "running":
                resolved_progress = 5
        try:
            with connection.cursor() as cursor:
                _set_postgres_tenant_context(cursor, context)
                cursor.execute(
                    """WITH workflow_update AS (
                         UPDATE workflow_runs
                            SET status = %s,
                                progress = CASE
                                  WHEN %s IN ('completed', 'failed') THEN 100
                                  WHEN %s::int IS NULL THEN progress
                                  ELSE GREATEST(progress, LEAST(%s::int, 99))
                                END,
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
                            AND workflow_type = 'seed_pipeline'
                         RETURNING 1
                       )
                       SELECT COUNT(*)::int AS workflow_updated FROM workflow_update""",
                    (
                        status,
                        status,
                        resolved_progress,
                        resolved_progress,
                        _seed_workflow_status_message(status, result, message),
                        encoded_result,
                        encoded_result,
                        code,
                        message,
                        context.tenant_id,
                        context.project_id,
                        context.run_id,
                    ),
                )
                row = cursor.fetchone()
                missing_parent = _workflow_status_updated_count(row) < 1
            if missing_parent:
                _rollback_postgres_connection(connection)
            else:
                connection.commit()
        except LLMFacilityError:
            _rollback_postgres_connection(connection)
            raise
        except Exception as exc:
            if missing_parent:
                raise LLMFacilityError(
                    "WORKFLOW_RUN_NOT_FOUND",
                    "seed workflow admission parent row is missing",
                ) from exc
            _rollback_postgres_connection(connection)
            raise LLMFacilityError(
                "WORKFLOW_STATUS_WRITE_FAILED",
                "seed workflow status write failed",
            ) from exc
        finally:
            connection.close()
        if missing_parent:
            raise LLMFacilityError("WORKFLOW_RUN_NOT_FOUND", "seed workflow admission parent row is missing")


class PostgresSeedSegmentRetryStore:
    def __init__(self, *, connect: Callable[[], Any]) -> None:
        self._connect = connect

    @classmethod
    def from_database_url(cls, database_url: str) -> "PostgresSeedSegmentRetryStore":
        try:
            import psycopg
            from psycopg.rows import dict_row
        except ImportError as exc:  # pragma: no cover - depends on optional runtime packaging
            raise RuntimeError("psycopg is required for DATABASE_URL seed segment retry persistence") from exc

        return cls(connect=lambda: psycopg.connect(database_url, row_factory=dict_row))

    def claim_seed_segment_retries(
        self,
        *,
        context: AgentContext,
        segment_ids: list[str],
        retry_attempt_id: str | None = None,
        worker_attempt: int = 1,
    ) -> list[dict[str, Any]]:
        normalized_segment_ids = _required_segment_retry_context(context, segment_ids)
        normalized_retry_attempt_id = _required_segment_retry_attempt_id(retry_attempt_id)
        normalized_worker_attempt = _required_segment_retry_worker_attempt(worker_attempt)
        connection = self._connect()
        try:
            with connection.cursor() as cursor:
                _set_postgres_tenant_context(cursor, context)
                cursor.execute(
                    """WITH retry_context AS (
                         SELECT
                           %s::uuid[] AS segment_ids,
                           %s::uuid AS tenant_id,
                           %s::uuid AS project_id,
                           %s::uuid AS run_id,
                           %s::uuid AS retry_attempt_id,
                           %s::integer AS worker_attempt
                       ),
                       requested_segments AS (
                         SELECT DISTINCT unnest(retry_context.segment_ids) AS segment_id
                         FROM retry_context
                       ),
                       eligible_retries AS (
                         SELECT retry_requests.segment_id
                         FROM seed_segment_retry_requests AS retry_requests
                         JOIN requested_segments
                           ON requested_segments.segment_id = retry_requests.segment_id
                         JOIN text_segments
                           ON text_segments.tenant_id = retry_requests.tenant_id
                          AND text_segments.project_id = retry_requests.project_id
                          AND text_segments.run_id = retry_requests.run_id
                          AND text_segments.segment_id = retry_requests.segment_id
                         WHERE retry_requests.tenant_id = (SELECT tenant_id FROM retry_context)
                           AND retry_requests.project_id = (SELECT project_id FROM retry_context)
                           AND retry_requests.run_id = (SELECT run_id FROM retry_context)
                           AND retry_requests.retry_attempt_id = (SELECT retry_attempt_id FROM retry_context)
                           AND (
                             retry_requests.status = 'requested'
                             OR (
                               retry_requests.status = 'running'
                               AND retry_requests.worker_attempt < (SELECT worker_attempt FROM retry_context)
                             )
                           )
                         FOR UPDATE OF retry_requests SKIP LOCKED
                       ),
                       claim_guard AS (
                         SELECT
                           cardinality((SELECT segment_ids FROM retry_context)) AS requested_count,
                           (SELECT COUNT(*) FROM eligible_retries) AS eligible_count
                       ),
                       claimed_retries AS (
                         UPDATE seed_segment_retry_requests AS retry_requests
                            SET status = 'running',
                                attempts = attempts + 1,
                                worker_attempt = (SELECT worker_attempt FROM retry_context),
                                last_error_code = NULL,
                                last_error_message = NULL,
                                updated_at = now()
                           FROM eligible_retries, claim_guard
                          WHERE retry_requests.tenant_id = (SELECT tenant_id FROM retry_context)
                            AND retry_requests.project_id = (SELECT project_id FROM retry_context)
                            AND retry_requests.run_id = (SELECT run_id FROM retry_context)
                            AND retry_requests.segment_id = eligible_retries.segment_id
                            AND claim_guard.requested_count = claim_guard.eligible_count
                         RETURNING retry_requests.segment_id
                       )
                       SELECT
                         text_segments.segment_id::text AS segment_id,
                         text_segments.segment_order,
                         text_segments.chapter_guess,
                         text_segments.title_guess,
                         text_segments.object_key
                       FROM claimed_retries
                       JOIN text_segments
                         ON text_segments.tenant_id = (SELECT tenant_id FROM retry_context)
                        AND text_segments.project_id = (SELECT project_id FROM retry_context)
                        AND text_segments.run_id = (SELECT run_id FROM retry_context)
                        AND text_segments.segment_id = claimed_retries.segment_id
                       ORDER BY text_segments.segment_order ASC""",
                    (
                        normalized_segment_ids,
                        context.tenant_id,
                        context.project_id,
                        context.run_id,
                        normalized_retry_attempt_id,
                        normalized_worker_attempt,
                    ),
                )
                rows = cursor.fetchall()
            connection.commit()
            return [_segment_retry_reference_from_row(row) for row in rows]
        except LLMFacilityError:
            _rollback_postgres_connection(connection)
            raise
        except Exception as exc:
            _rollback_postgres_connection(connection)
            raise LLMFacilityError(
                "SEED_SEGMENT_RETRY_CLAIM_FAILED",
                "seed segment retry claim failed",
            ) from exc
        finally:
            connection.close()

    def mark_seed_segment_retries(
        self,
        *,
        context: AgentContext,
        segment_ids: list[str],
        retry_attempt_id: str | None = None,
        worker_attempt: int = 1,
        status: str,
        code: str | None = None,
        message: str | None = None,
    ) -> None:
        normalized_segment_ids = _required_segment_retry_context(context, segment_ids)
        normalized_retry_attempt_id = _required_segment_retry_attempt_id(retry_attempt_id)
        normalized_worker_attempt = _required_segment_retry_worker_attempt(worker_attempt)
        normalized_status = _required_segment_retry_status(status)
        public_code, public_message = _segment_retry_status_error(normalized_status, code, message)
        connection = self._connect()
        try:
            with connection.cursor() as cursor:
                _set_postgres_tenant_context(cursor, context)
                cursor.execute(
                    """UPDATE seed_segment_retry_requests
                          SET status = %s,
                              last_error_code = %s,
                              last_error_message = %s,
                              updated_at = now()
                        WHERE tenant_id = %s
                          AND project_id = %s
                          AND run_id = %s
                          AND segment_id = ANY(%s::uuid[])
                          AND retry_attempt_id = %s::uuid
                          AND worker_attempt = %s
                          AND status = 'running'""",
                    (
                        normalized_status,
                        public_code,
                        public_message,
                        context.tenant_id,
                        context.project_id,
                        context.run_id,
                        normalized_segment_ids,
                        normalized_retry_attempt_id,
                        normalized_worker_attempt,
                    ),
                )
                if getattr(cursor, "rowcount", len(normalized_segment_ids)) != len(normalized_segment_ids):
                    raise LLMFacilityError(
                        "SEED_SEGMENT_RETRY_STATUS_WRITE_FAILED",
                        "seed segment retry status write failed",
                    )
            connection.commit()
        except LLMFacilityError:
            _rollback_postgres_connection(connection)
            raise
        except Exception as exc:
            _rollback_postgres_connection(connection)
            raise LLMFacilityError(
                "SEED_SEGMENT_RETRY_STATUS_WRITE_FAILED",
                "seed segment retry status write failed",
            ) from exc
        finally:
            connection.close()

    def complete_seed_segment_retries(
        self,
        *,
        context: AgentContext,
        segment_ids: list[str],
        retry_attempt_id: str | None,
        worker_attempt: int,
        requested_count: int,
        segment_count: int,
        note_count: int,
        model_id: str | None,
    ) -> None:
        payload: dict[str, object] = {
            "stage": "segment_retry",
            "status": "completed",
            "requested_count": requested_count,
            "segment_count": segment_count,
            "note_count": note_count,
        }
        if model_id is not None:
            payload["model_id"] = model_id
        self._finish_seed_segment_retries(
            context=context,
            segment_ids=segment_ids,
            retry_attempt_id=retry_attempt_id,
            worker_attempt=worker_attempt,
            status="completed",
            code=None,
            message=None,
            event_type="seed.segments.retry_completed",
            event_payload=payload,
        )

    def complete_seed_segment_retry_notes(
        self,
        *,
        context: AgentContext,
        segment_ids: list[str],
        retry_attempt_id: str | None,
        worker_attempt: int,
        pass_id: str,
        module_key: str | None,
        model_id: str | None,
        notes: list[dict[str, Any]],
    ) -> None:
        payload: dict[str, object] = {
            "stage": "segment_retry",
            "status": "completed",
            "requested_count": len(segment_ids),
            "segment_count": len(segment_ids),
            "note_count": len(notes),
        }
        if model_id is not None:
            payload["model_id"] = model_id
        normalized_retry_attempt_id = _required_segment_retry_attempt_id(retry_attempt_id)
        self._finish_seed_segment_retries(
            context=context,
            segment_ids=segment_ids,
            retry_attempt_id=normalized_retry_attempt_id,
            worker_attempt=worker_attempt,
            status="completed",
            code=None,
            message=None,
            event_type="seed.segments.retry_completed",
            event_payload=payload,
            reading_notes_write={
                "pass_id": _required_text_value(pass_id, "pass_id"),
                "module_key": module_key,
                "model_id": model_id,
                "notes": notes,
                "metadata_jsonb": {
                    "retry": True,
                    "last_retry_segment_count": len(segment_ids),
                    "last_retry_attempt_id": normalized_retry_attempt_id,
                },
            },
        )

    def fail_seed_segment_retries(
        self,
        *,
        context: AgentContext,
        segment_ids: list[str],
        retry_attempt_id: str | None,
        worker_attempt: int,
        requested_count: int,
        segment_count: int | None,
        code: str,
        message: str,
    ) -> None:
        payload: dict[str, object] = {
            "stage": "segment_retry",
            "status": "failed",
            "requested_count": requested_count,
            "error_code": code,
            "error_message": message,
        }
        if segment_count is not None:
            payload["segment_count"] = segment_count
        self._finish_seed_segment_retries(
            context=context,
            segment_ids=segment_ids,
            retry_attempt_id=retry_attempt_id,
            worker_attempt=worker_attempt,
            status="failed",
            code=code,
            message=message,
            event_type="seed.segments.retry_failed",
            event_payload=payload,
        )

    def _finish_seed_segment_retries(
        self,
        *,
        context: AgentContext,
        segment_ids: list[str],
        retry_attempt_id: str | None,
        worker_attempt: int,
        status: str,
        code: str | None,
        message: str | None,
        event_type: str,
        event_payload: dict[str, object],
        reading_notes_write: dict[str, Any] | None = None,
    ) -> None:
        normalized_segment_ids = _required_segment_retry_context(context, segment_ids)
        normalized_retry_attempt_id = _required_segment_retry_attempt_id(retry_attempt_id)
        normalized_worker_attempt = _required_segment_retry_worker_attempt(worker_attempt)
        normalized_status = _required_segment_retry_status(status)
        public_code, public_message = _segment_retry_status_error(normalized_status, code, message)
        encoded_payload = json.dumps(
            _sanitize_workflow_event_payload(event_payload),
            ensure_ascii=False,
            separators=(",", ":"),
        )
        connection = self._connect()
        try:
            with connection.cursor() as cursor:
                _set_postgres_tenant_context(cursor, context)
                self._lock_seed_segment_retry_finish_scope(
                    cursor,
                    context=context,
                    segment_ids=normalized_segment_ids,
                    retry_attempt_id=normalized_retry_attempt_id,
                    worker_attempt=normalized_worker_attempt,
                )
                if reading_notes_write is not None:
                    _record_reading_notes_on_cursor(
                        cursor,
                        context=context,
                        pass_id=reading_notes_write["pass_id"],
                        pass_type="sequential_reading",
                        status="completed",
                        module_key=reading_notes_write["module_key"],
                        model_id=reading_notes_write["model_id"],
                        notes=reading_notes_write["notes"],
                        metadata_jsonb=reading_notes_write["metadata_jsonb"],
                    )
                self._update_finished_seed_segment_retries(
                    cursor,
                    context=context,
                    segment_ids=normalized_segment_ids,
                    retry_attempt_id=normalized_retry_attempt_id,
                    worker_attempt=normalized_worker_attempt,
                    status=normalized_status,
                    code=public_code,
                    message=public_message,
                )
                self._insert_seed_segment_retry_event(
                    cursor,
                    context=context,
                    event_type=event_type,
                    encoded_payload=encoded_payload,
                )
            connection.commit()
        except LLMFacilityError:
            _rollback_postgres_connection(connection)
            raise
        except Exception as exc:
            _rollback_postgres_connection(connection)
            raise LLMFacilityError(
                "SEED_SEGMENT_RETRY_COMPLETION_WRITE_FAILED",
                "seed segment retry completion write failed",
            ) from exc
        finally:
            connection.close()

    @staticmethod
    def _lock_seed_segment_retry_finish_scope(
        cursor: Any,
        *,
        context: AgentContext,
        segment_ids: list[str],
        retry_attempt_id: str,
        worker_attempt: int,
    ) -> None:
        cursor.execute(
            """WITH requested_segments AS (
                 SELECT unnest(%s::uuid[]) AS segment_id
               )
               SELECT retry_requests.segment_id::text AS segment_id
               FROM requested_segments
               JOIN seed_segment_retry_requests AS retry_requests
                 ON retry_requests.segment_id = requested_segments.segment_id
               JOIN workflow_runs
                 ON workflow_runs.tenant_id = retry_requests.tenant_id
                AND workflow_runs.project_id = retry_requests.project_id
                AND workflow_runs.run_id = retry_requests.run_id
                AND workflow_runs.workflow_type = 'seed_pipeline'
               WHERE retry_requests.tenant_id = %s
                 AND retry_requests.project_id = %s
                 AND retry_requests.run_id = %s
                 AND retry_requests.retry_attempt_id = %s::uuid
                 AND retry_requests.worker_attempt = %s
                 AND retry_requests.status = 'running'
               ORDER BY retry_requests.segment_id
               FOR UPDATE OF retry_requests, workflow_runs""",
            (
                segment_ids,
                context.tenant_id,
                context.project_id,
                context.run_id,
                retry_attempt_id,
                worker_attempt,
            ),
        )
        if not _seed_segment_retry_rows_match(cursor.fetchall(), segment_ids):
            _raise_seed_segment_retry_completion_write_failed()

    @staticmethod
    def _update_finished_seed_segment_retries(
        cursor: Any,
        *,
        context: AgentContext,
        segment_ids: list[str],
        retry_attempt_id: str,
        worker_attempt: int,
        status: str,
        code: str | None,
        message: str | None,
    ) -> None:
        cursor.execute(
            """UPDATE seed_segment_retry_requests
                  SET status = %s,
                      last_error_code = %s,
                      last_error_message = %s,
                      updated_at = now()
                WHERE tenant_id = %s
                  AND project_id = %s
                  AND run_id = %s
                  AND segment_id = ANY(%s::uuid[])
                  AND retry_attempt_id = %s::uuid
                  AND worker_attempt = %s
                  AND status = 'running'
              RETURNING segment_id::text AS segment_id""",
            (
                status,
                code,
                message,
                context.tenant_id,
                context.project_id,
                context.run_id,
                segment_ids,
                retry_attempt_id,
                worker_attempt,
            ),
        )
        if not _seed_segment_retry_rows_match(cursor.fetchall(), segment_ids):
            _raise_seed_segment_retry_completion_write_failed()

    @staticmethod
    def _insert_seed_segment_retry_event(
        cursor: Any,
        *,
        context: AgentContext,
        event_type: str,
        encoded_payload: str,
    ) -> None:
        cursor.execute(
            """INSERT INTO workflow_events (
                 tenant_id, run_id, workflow_type, project_id, event_type, sequence, payload_jsonb
               )
               SELECT
                 %s, %s, 'seed_pipeline', %s, %s,
                 COALESCE(MAX(sequence), 0) + 1,
                 %s::jsonb
               FROM workflow_events
               WHERE tenant_id = %s
                 AND run_id = %s""",
            (
                context.tenant_id,
                context.run_id,
                context.project_id,
                event_type,
                encoded_payload,
                context.tenant_id,
                context.run_id,
            ),
        )
        if getattr(cursor, "rowcount", 1) != 1:
            _raise_seed_segment_retry_completion_write_failed()


def _raise_seed_segment_retry_completion_write_failed() -> None:
    raise LLMFacilityError(
        "SEED_SEGMENT_RETRY_COMPLETION_WRITE_FAILED",
        "seed segment retry completion write failed",
    )


def _seed_segment_retry_rows_match(rows: list[Any], segment_ids: list[str]) -> bool:
    try:
        returned_segment_ids = [str(row["segment_id"]) for row in rows]
    except (KeyError, TypeError):
        return False
    return len(returned_segment_ids) == len(segment_ids) and set(returned_segment_ids) == set(segment_ids)


class PostgresTextSegmentWriter:
    def __init__(self, *, connect: Callable[[], Any]) -> None:
        self._connect = connect

    @classmethod
    def from_database_url(cls, database_url: str) -> "PostgresTextSegmentWriter":
        try:
            import psycopg
        except ImportError as exc:  # pragma: no cover - depends on optional runtime packaging
            raise RuntimeError("psycopg is required for DATABASE_URL text segment persistence") from exc

        return cls(connect=lambda: psycopg.connect(database_url))

    def record_text_segments(
        self,
        *,
        context: AgentContext,
        source_file_id: str,
        segments: list[dict[str, Any]],
    ) -> None:
        if context.project_id is None:
            raise ValueError("project_id is required to persist text segments")
        normalized_source_file_id = source_file_id.strip()
        if not normalized_source_file_id:
            raise ValueError("source_file_id is required to persist text segments")
        connection = self._connect()
        try:
            with connection.cursor() as cursor:
                _set_postgres_tenant_context(cursor, context)
                for segment in segments:
                    cursor.execute(
                        """INSERT INTO text_segments (
                             tenant_id, segment_id, project_id, run_id, source_file_id, segment_order,
                             chapter_guess, title_guess, start_offset, end_offset,
                             content_excerpt, object_key, summary, metadata_jsonb
                           )
                           VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s::jsonb)
                           ON CONFLICT (tenant_id, project_id, run_id, segment_order)
                           DO UPDATE SET
                             segment_id = EXCLUDED.segment_id,
                             source_file_id = EXCLUDED.source_file_id,
                             chapter_guess = EXCLUDED.chapter_guess,
                             title_guess = EXCLUDED.title_guess,
                             start_offset = EXCLUDED.start_offset,
                             end_offset = EXCLUDED.end_offset,
                             content_excerpt = EXCLUDED.content_excerpt,
                             object_key = EXCLUDED.object_key,
                             summary = EXCLUDED.summary,
                             metadata_jsonb = EXCLUDED.metadata_jsonb,
                             updated_at = now()""",
                        (
                            context.tenant_id,
                            _required_segment_id(segment),
                            context.project_id,
                            context.run_id,
                            normalized_source_file_id,
                            _required_segment_order(segment),
                            _optional_text(segment, "chapter_guess"),
                            _optional_text(segment, "title_guess"),
                            _optional_int(segment, "start_offset"),
                            _optional_int(segment, "end_offset"),
                            _optional_text(segment, "content_excerpt"),
                            _optional_text(segment, "object_key"),
                            _optional_text(segment, "summary"),
                            _metadata_json(segment),
                        ),
                    )
            connection.commit()
        except Exception:
            _rollback_postgres_connection(connection)
            raise
        finally:
            connection.close()


def _set_postgres_tenant_context(cursor: Any, context: AgentContext) -> None:
    cursor.execute(
        "SELECT app_set_tenant_context(%s::uuid, %s::uuid, false)",
        (context.tenant_id, context.actor_user_id),
    )


def _rollback_postgres_connection(connection: Any) -> None:
    rollback = getattr(connection, "rollback", None)
    if not callable(rollback):
        return
    try:
        rollback()
    except Exception:
        return


class PostgresReadingNotesWriter:
    def __init__(self, *, connect: Callable[[], Any]) -> None:
        self._connect = connect

    @classmethod
    def from_database_url(cls, database_url: str) -> "PostgresReadingNotesWriter":
        try:
            import psycopg
        except ImportError as exc:  # pragma: no cover - depends on optional runtime packaging
            raise RuntimeError("psycopg is required for DATABASE_URL reading notes persistence") from exc

        return cls(connect=lambda: psycopg.connect(database_url))

    def record_reading_notes(
        self,
        *,
        context: AgentContext,
        pass_id: str,
        pass_type: str,
        status: str,
        module_key: str | None,
        model_id: str | None,
        notes: list[dict[str, Any]],
        metadata_jsonb: dict[str, Any] | None = None,
    ) -> None:
        if context.project_id is None:
            raise ValueError("project_id is required to persist reading notes")
        normalized_pass_id = _required_text_value(pass_id, "pass_id")
        connection = self._connect()
        try:
            with connection.cursor() as cursor:
                _set_postgres_tenant_context(cursor, context)
                _record_reading_notes_on_cursor(
                    cursor,
                    context=context,
                    pass_id=normalized_pass_id,
                    pass_type=pass_type,
                    status=status,
                    module_key=module_key,
                    model_id=model_id,
                    notes=notes,
                    metadata_jsonb=metadata_jsonb,
                )
            connection.commit()
        except Exception:
            _rollback_postgres_connection(connection)
            raise
        finally:
            connection.close()


def _record_reading_notes_on_cursor(
    cursor: Any,
    *,
    context: AgentContext,
    pass_id: str,
    pass_type: str,
    status: str,
    module_key: str | None,
    model_id: str | None,
    notes: list[dict[str, Any]],
    metadata_jsonb: dict[str, Any] | None,
) -> None:
    cursor.execute(
        """INSERT INTO reading_passes (
             tenant_id, project_id, run_id, pass_id, pass_type, status,
             module_key, model_id, metadata_jsonb
           )
           VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s::jsonb)
           ON CONFLICT (pass_id)
           DO UPDATE SET
             pass_type = EXCLUDED.pass_type,
             status = EXCLUDED.status,
             module_key = EXCLUDED.module_key,
             model_id = EXCLUDED.model_id,
             metadata_jsonb = reading_passes.metadata_jsonb || EXCLUDED.metadata_jsonb,
             updated_at = now()
           WHERE reading_passes.tenant_id = EXCLUDED.tenant_id
             AND reading_passes.project_id = EXCLUDED.project_id
             AND reading_passes.run_id = EXCLUDED.run_id
           RETURNING reading_passes.pass_id""",
        (
            context.tenant_id,
            context.project_id,
            context.run_id,
            pass_id,
            _required_text_value(pass_type, "pass_type"),
            _required_text_value(status, "status"),
            module_key,
            model_id,
            _json_object(metadata_jsonb or {}),
        ),
    )
    if cursor.fetchone() is None:
        raise RuntimeError("reading pass scope write failed")
    for note in notes:
        cursor.execute(
            """INSERT INTO reading_segment_notes (
                 tenant_id, project_id, run_id, segment_id, pass_id, payload_jsonb, summary
               )
               VALUES (%s, %s, %s, %s, %s, %s::jsonb, %s)
               ON CONFLICT (tenant_id, run_id, segment_id, pass_id)
               DO UPDATE SET
                 payload_jsonb = EXCLUDED.payload_jsonb,
                 summary = EXCLUDED.summary,
                 updated_at = now()""",
            (
                context.tenant_id,
                context.project_id,
                context.run_id,
                _required_note_segment_id(note),
                pass_id,
                _note_payload_json(note),
                _optional_text(note, "summary"),
            ),
        )
    cursor.execute(
        """UPDATE reading_passes AS reading_pass
              SET metadata_jsonb = reading_pass.metadata_jsonb || jsonb_build_object(
                    'segment_count',
                    (
                      SELECT COUNT(*)
                      FROM reading_segment_notes AS reading_note
                      WHERE reading_note.tenant_id = reading_pass.tenant_id
                        AND reading_note.project_id = reading_pass.project_id
                        AND reading_note.run_id = reading_pass.run_id
                        AND reading_note.pass_id = reading_pass.pass_id
                    )
                  ),
                  updated_at = now()
            WHERE reading_pass.tenant_id = %s
              AND reading_pass.project_id = %s
              AND reading_pass.run_id = %s
              AND reading_pass.pass_id = %s
           RETURNING reading_pass.pass_id""",
        (context.tenant_id, context.project_id, context.run_id, pass_id),
    )
    if cursor.fetchone() is None:
        raise RuntimeError("reading pass segment count update failed")


class PostgresSeedAnalysisWriter:
    def __init__(self, *, connect: Callable[[], Any]) -> None:
        self._connect = connect

    @classmethod
    def from_database_url(cls, database_url: str) -> "PostgresSeedAnalysisWriter":
        try:
            import psycopg
        except ImportError as exc:  # pragma: no cover - depends on optional runtime packaging
            raise RuntimeError("psycopg is required for DATABASE_URL seed analysis persistence") from exc

        return cls(connect=lambda: psycopg.connect(database_url))

    def record_seed_analysis(
        self,
        *,
        context: AgentContext,
        module_key: str,
        model_id: str | None,
        segment_count: int,
        summary_count: int,
        seed_analysis: dict[str, Any],
    ) -> str:
        if context.project_id is None:
            raise ValueError("project_id is required to persist seed analysis snapshots")
        normalized_module_key = _required_text_value(module_key, "module_key")
        if model_id is not None and not isinstance(model_id, str):
            raise ValueError("model_id must be a string")
        normalized_segment_count = _non_negative_int(segment_count, "segment_count")
        normalized_summary_count = _non_negative_int(summary_count, "summary_count")
        analysis_json = _seed_analysis_json(seed_analysis)
        connection = self._connect()
        try:
            with connection.cursor() as cursor:
                _set_postgres_tenant_context(cursor, context)
                cursor.execute(
                    """INSERT INTO seed_analysis_snapshots (
                         tenant_id, project_id, run_id, module_key, model_id,
                         analysis_jsonb, summary_count, segment_count, metadata_jsonb
                       )
                       VALUES (%s, %s, %s, %s, %s, %s::jsonb, %s, %s, '{}'::jsonb)
                       ON CONFLICT (tenant_id, project_id, run_id, module_key)
                       DO UPDATE SET
                         model_id = EXCLUDED.model_id,
                         analysis_jsonb = EXCLUDED.analysis_jsonb,
                         summary_count = EXCLUDED.summary_count,
                         segment_count = EXCLUDED.segment_count,
                         updated_at = now()
                       RETURNING seed_analysis_snapshot_id::text AS seed_analysis_snapshot_id""",
                    (
                        context.tenant_id,
                        context.project_id,
                        context.run_id,
                        normalized_module_key,
                        model_id.strip() if isinstance(model_id, str) and model_id.strip() else None,
                        analysis_json,
                        normalized_summary_count,
                        normalized_segment_count,
                    ),
                )
                row = cursor.fetchone()
            connection.commit()
            return _row_value(row, "seed_analysis_snapshot_id")
        except Exception:
            _rollback_postgres_connection(connection)
            raise
        finally:
            connection.close()


class PostgresOntologySnapshotWriter:
    def __init__(self, *, connect: Callable[[], Any]) -> None:
        self._connect = connect

    @classmethod
    def from_database_url(cls, database_url: str) -> "PostgresOntologySnapshotWriter":
        try:
            import psycopg
        except ImportError as exc:  # pragma: no cover - depends on optional runtime packaging
            raise RuntimeError("psycopg is required for DATABASE_URL ontology snapshot persistence") from exc

        return cls(connect=lambda: psycopg.connect(database_url))

    def record_ontology_snapshot(
        self,
        *,
        context: AgentContext,
        module_key: str,
        model_id: str | None,
        seed_ontology: dict[str, Any],
        entity_type_count: int,
        relationship_type_count: int,
        world_rule_type_count: int,
    ) -> str:
        if context.project_id is None:
            raise ValueError("project_id is required to persist ontology snapshots")
        normalized_module_key = _required_text_value(module_key, "module_key")
        if model_id is not None and not isinstance(model_id, str):
            raise ValueError("model_id must be a string")
        normalized_entity_type_count = _non_negative_int(entity_type_count, "entity_type_count")
        normalized_relationship_type_count = _non_negative_int(
            relationship_type_count,
            "relationship_type_count",
        )
        normalized_world_rule_type_count = _non_negative_int(world_rule_type_count, "world_rule_type_count")
        ontology_json = _json_object(seed_ontology)
        connection = self._connect()
        try:
            with connection.cursor() as cursor:
                _set_postgres_tenant_context(cursor, context)
                cursor.execute(
                    """INSERT INTO seed_ontology_snapshots (
                         tenant_id, project_id, run_id, module_key, model_id,
                         ontology_jsonb, entity_type_count, relationship_type_count,
                         world_rule_type_count, metadata_jsonb
                       )
                       VALUES (%s, %s, %s, %s, %s, %s::jsonb, %s, %s, %s, '{}'::jsonb)
                       ON CONFLICT (tenant_id, project_id, run_id, module_key)
                       DO UPDATE SET
                         model_id = EXCLUDED.model_id,
                         ontology_jsonb = EXCLUDED.ontology_jsonb,
                         entity_type_count = EXCLUDED.entity_type_count,
                         relationship_type_count = EXCLUDED.relationship_type_count,
                         world_rule_type_count = EXCLUDED.world_rule_type_count,
                         updated_at = now()
                       RETURNING seed_ontology_snapshot_id::text AS seed_ontology_snapshot_id""",
                    (
                        context.tenant_id,
                        context.project_id,
                        context.run_id,
                        normalized_module_key,
                        model_id.strip() if isinstance(model_id, str) and model_id.strip() else None,
                        ontology_json,
                        normalized_entity_type_count,
                        normalized_relationship_type_count,
                        normalized_world_rule_type_count,
                    ),
                )
                row = cursor.fetchone()
            connection.commit()
            return _row_value(row, "seed_ontology_snapshot_id")
        except Exception as exc:
            _rollback_postgres_connection(connection)
            raise LLMFacilityError("ONTOLOGY_SNAPSHOT_WRITE_FAILED", "ontology snapshot write failed") from exc
        finally:
            connection.close()


class PostgresEntityResolutionSnapshotWriter:
    def __init__(self, *, connect: Callable[[], Any]) -> None:
        self._connect = connect

    @classmethod
    def from_database_url(cls, database_url: str) -> "PostgresEntityResolutionSnapshotWriter":
        try:
            import psycopg
        except ImportError as exc:  # pragma: no cover - depends on optional runtime packaging
            raise RuntimeError("psycopg is required for DATABASE_URL entity resolution snapshot persistence") from exc

        return cls(connect=lambda: psycopg.connect(database_url))

    def record_entity_resolution_snapshot(
        self,
        *,
        context: AgentContext,
        module_key: str,
        model_id: str | None,
        entity_resolution: dict[str, Any],
        merged_entity_count: int,
        alias_count: int,
        conflict_count: int,
    ) -> str:
        if context.project_id is None:
            raise ValueError("project_id is required to persist entity resolution snapshots")
        normalized_module_key = _required_text_value(module_key, "module_key")
        if model_id is not None and not isinstance(model_id, str):
            raise ValueError("model_id must be a string")
        normalized_merged_entity_count = _non_negative_int(merged_entity_count, "merged_entity_count")
        normalized_alias_count = _non_negative_int(alias_count, "alias_count")
        normalized_conflict_count = _non_negative_int(conflict_count, "conflict_count")
        resolution_json = _json_object(entity_resolution)
        connection = self._connect()
        try:
            with connection.cursor() as cursor:
                _set_postgres_tenant_context(cursor, context)
                cursor.execute(
                    """INSERT INTO seed_entity_resolution_snapshots (
                         tenant_id, project_id, run_id, module_key, model_id,
                         resolution_jsonb, merged_entity_count, alias_count,
                         conflict_count, metadata_jsonb
                       )
                       VALUES (%s, %s, %s, %s, %s, %s::jsonb, %s, %s, %s, '{}'::jsonb)
                       ON CONFLICT (tenant_id, project_id, run_id, module_key)
                       DO UPDATE SET
                         model_id = EXCLUDED.model_id,
                         resolution_jsonb = EXCLUDED.resolution_jsonb,
                         merged_entity_count = EXCLUDED.merged_entity_count,
                         alias_count = EXCLUDED.alias_count,
                         conflict_count = EXCLUDED.conflict_count,
                         updated_at = now()
                       RETURNING seed_entity_resolution_snapshot_id::text AS seed_entity_resolution_snapshot_id""",
                    (
                        context.tenant_id,
                        context.project_id,
                        context.run_id,
                        normalized_module_key,
                        model_id.strip() if isinstance(model_id, str) and model_id.strip() else None,
                        resolution_json,
                        normalized_merged_entity_count,
                        normalized_alias_count,
                        normalized_conflict_count,
                    ),
                )
                row = cursor.fetchone()
            connection.commit()
            return _row_value(row, "seed_entity_resolution_snapshot_id")
        except Exception as exc:
            _rollback_postgres_connection(connection)
            raise LLMFacilityError(
                "ENTITY_RESOLUTION_SNAPSHOT_WRITE_FAILED",
                "entity resolution snapshot write failed",
            ) from exc
        finally:
            connection.close()


class PostgresAgentProfileSnapshotWriter:
    def __init__(self, *, connect: Callable[[], Any]) -> None:
        self._connect = connect

    @classmethod
    def from_database_url(cls, database_url: str) -> "PostgresAgentProfileSnapshotWriter":
        try:
            import psycopg
        except ImportError as exc:  # pragma: no cover - depends on optional runtime packaging
            raise RuntimeError("psycopg is required for DATABASE_URL agent profile snapshot persistence") from exc

        return cls(connect=lambda: psycopg.connect(database_url))

    def record_agent_profile_snapshot(
        self,
        *,
        context: AgentContext,
        module_key: str,
        model_id: str | None,
        agent_profiles: dict[str, Any],
        profile_count: int,
        memory_seed_count: int,
        relationship_view_count: int,
    ) -> str:
        if context.project_id is None:
            raise ValueError("project_id is required to persist agent profile snapshots")
        normalized_module_key = _required_text_value(module_key, "module_key")
        if model_id is not None and not isinstance(model_id, str):
            raise ValueError("model_id must be a string")
        normalized_profile_count = _non_negative_int(profile_count, "profile_count")
        normalized_memory_seed_count = _non_negative_int(memory_seed_count, "memory_seed_count")
        normalized_relationship_view_count = _non_negative_int(
            relationship_view_count,
            "relationship_view_count",
        )
        profiles_json = _json_agent_profile_object(agent_profiles)
        connection = self._connect()
        try:
            with connection.cursor() as cursor:
                _set_postgres_tenant_context(cursor, context)
                cursor.execute(
                    """INSERT INTO seed_agent_profile_snapshots (
                         tenant_id, project_id, run_id, module_key, model_id,
                         profiles_jsonb, profile_count, memory_seed_count,
                         relationship_view_count, metadata_jsonb
                       )
                       VALUES (%s, %s, %s, %s, %s, %s::jsonb, %s, %s, %s, '{}'::jsonb)
                       ON CONFLICT (tenant_id, project_id, run_id, module_key)
                       DO UPDATE SET
                         model_id = EXCLUDED.model_id,
                         profiles_jsonb = EXCLUDED.profiles_jsonb,
                         profile_count = EXCLUDED.profile_count,
                         memory_seed_count = EXCLUDED.memory_seed_count,
                         relationship_view_count = EXCLUDED.relationship_view_count,
                         updated_at = now()
                       RETURNING seed_agent_profile_snapshot_id::text AS seed_agent_profile_snapshot_id""",
                    (
                        context.tenant_id,
                        context.project_id,
                        context.run_id,
                        normalized_module_key,
                        model_id.strip() if isinstance(model_id, str) and model_id.strip() else None,
                        profiles_json,
                        normalized_profile_count,
                        normalized_memory_seed_count,
                        normalized_relationship_view_count,
                    ),
                )
                row = cursor.fetchone()
            connection.commit()
            return _row_value(row, "seed_agent_profile_snapshot_id")
        except Exception as exc:
            _rollback_postgres_connection(connection)
            raise LLMFacilityError(
                "AGENT_PROFILE_SNAPSHOT_WRITE_FAILED",
                "agent profile snapshot write failed",
            ) from exc
        finally:
            connection.close()


class PostgresAgentProfileContextLoader:
    def __init__(self, *, connect: Callable[[], Any]) -> None:
        self._connect = connect

    @classmethod
    def from_database_url(cls, database_url: str) -> "PostgresAgentProfileContextLoader":
        try:
            import psycopg
            from psycopg.rows import dict_row
        except ImportError as exc:  # pragma: no cover - depends on optional runtime packaging
            raise RuntimeError("psycopg is required for DATABASE_URL agent profile context loading") from exc

        return cls(connect=lambda: psycopg.connect(database_url, row_factory=dict_row))

    def load_context(self, *, context: AgentContext) -> dict[str, Any]:
        if context.project_id is None:
            raise LLMFacilityError(
                "AGENT_PROFILE_CONTEXT_LOAD_FAILED",
                "agent profile source context load failed",
            )
        connection = self._connect()
        try:
            with connection.cursor() as cursor:
                _set_postgres_tenant_context(cursor, context)
                resolution = self._load_resolution(cursor, context)
                entities = self._load_entities(cursor, context)
                relationships = self._load_relationships(cursor, context)
                segment_summaries = self._load_segment_summaries(cursor, context)
            context_payload: dict[str, Any] = {}
            if resolution:
                context_payload["entity_resolution"] = resolution
            canon: dict[str, Any] = {}
            if entities:
                canon["entities"] = entities
            if relationships:
                canon["relationships"] = relationships
            if segment_summaries:
                canon["segment_summaries"] = segment_summaries
            if canon:
                context_payload["canon"] = canon
            sanitized = _sanitize_agent_profile_context_value(context_payload)
            return sanitized if isinstance(sanitized, dict) else {}
        except LLMFacilityError:
            raise
        except Exception as exc:
            raise LLMFacilityError(
                "AGENT_PROFILE_CONTEXT_LOAD_FAILED",
                "agent profile source context load failed",
            ) from exc
        finally:
            connection.close()

    def _load_resolution(self, cursor: Any, context: AgentContext) -> dict[str, Any]:
        cursor.execute(
            """SELECT
                   seed_entity_resolution_snapshot_id::text AS seed_entity_resolution_snapshot_id,
                   model_id,
                   merged_entity_count,
                   alias_count,
                   conflict_count,
                   resolution_jsonb
               FROM seed_entity_resolution_snapshots
               WHERE tenant_id = %s
                 AND project_id = %s
                 AND run_id = %s
                 AND module_key = 'entity_resolution'
               ORDER BY updated_at DESC
               LIMIT 1""",
            (context.tenant_id, context.project_id, context.run_id),
        )
        row = cursor.fetchone()
        if row is None:
            return {}
        resolution_json = _jsonb_row_value(row, "resolution_jsonb")
        resolution_payload = (
            _project_agent_profile_resolution_context(resolution_json)
            if isinstance(resolution_json, dict)
            else {}
        )
        result = {
            "snapshot_id": _optional_row_text(row, "seed_entity_resolution_snapshot_id"),
            "model_id": _optional_row_text(row, "model_id"),
            "merged_entity_count": _optional_row_int(row, "merged_entity_count"),
            "alias_count": _optional_row_int(row, "alias_count"),
            "conflict_count": _optional_row_int(row, "conflict_count"),
        }
        if resolution_payload:
            result["resolution"] = resolution_payload
        return {key: value for key, value in result.items() if value is not None}

    def _load_entities(self, cursor: Any, context: AgentContext) -> list[dict[str, Any]]:
        cursor.execute(
            """SELECT
                   entity_id::text AS entity_id,
                   entity_type,
                   canonical_name,
                   importance,
                   state_summary
               FROM entities
               WHERE tenant_id = %s
                 AND project_id = %s
                 AND source_run_id::text = %s
               ORDER BY canonical_name ASC
               LIMIT 200""",
            (context.tenant_id, context.project_id, context.run_id),
        )
        return [_compact_sanitized_context_row(row) for row in cursor.fetchall()]

    def _load_relationships(self, cursor: Any, context: AgentContext) -> list[dict[str, Any]]:
        cursor.execute(
            """SELECT
                   relationship_id::text AS relationship_id,
                   source_entity_name,
                   target_entity_name,
                   relationship_type,
                   summary
               FROM relationships
               WHERE tenant_id = %s
                 AND project_id = %s
                 AND source_run_id::text = %s
               ORDER BY source_entity_name ASC, target_entity_name ASC, relationship_type ASC
               LIMIT 200""",
            (context.tenant_id, context.project_id, context.run_id),
        )
        return [_compact_sanitized_context_row(row) for row in cursor.fetchall()]

    def _load_segment_summaries(self, cursor: Any, context: AgentContext) -> list[dict[str, Any]]:
        cursor.execute(
            """SELECT
                   segment_id::text AS segment_id,
                   row_number() OVER (ORDER BY created_at ASC, segment_id ASC) - 1 AS segment_order,
                   summary
               FROM segment_summaries
               WHERE tenant_id = %s
                 AND project_id = %s
                 AND run_id = %s
               ORDER BY created_at ASC, segment_id ASC
               LIMIT 200""",
            (context.tenant_id, context.project_id, context.run_id),
        )
        return [_compact_sanitized_context_row(row) for row in cursor.fetchall()]


class LLMFacilityOntologyRunner:
    def __init__(
        self,
        *,
        binding_resolver: Any,
        credential_provider: Any,
        chat_client: Any,
        ontology_snapshot_writer: OntologySnapshotWriter,
    ) -> None:
        self._binding_resolver = binding_resolver
        self._credential_provider = credential_provider
        self._chat_client = chat_client
        self._ontology_snapshot_writer = ontology_snapshot_writer

    def generate(
        self,
        *,
        context: AgentContext,
        module_key: str,
    ) -> dict[str, Any]:
        if module_key != STORY_ONTOLOGY_MODULE_KEY:
            return _ontology_runner_failed(
                "VALIDATION_FAILED",
                f"LLMFacilityOntologyRunner only supports {STORY_ONTOLOGY_MODULE_KEY}",
            )
        try:
            resolution = self._binding_resolver.resolve_module_binding(
                context=context,
                module_key=module_key,
            )
            _validate_ontology_resolution(resolution)
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
                messages=_ontology_messages(context=context),
            )
            seed_ontology = _seed_ontology_payload(response_json)
            entity_type_count = _ontology_type_count(seed_ontology, "entity_types")
            relationship_type_count = _ontology_type_count(seed_ontology, "relationship_types")
            world_rule_type_count = _ontology_type_count(seed_ontology, "world_rule_types")
            ontology_snapshot_id = self._ontology_snapshot_writer.record_ontology_snapshot(
                context=context,
                module_key=STORY_ONTOLOGY_MODULE_KEY,
                model_id=resolution.model_id,
                seed_ontology=seed_ontology,
                entity_type_count=entity_type_count,
                relationship_type_count=relationship_type_count,
                world_rule_type_count=world_rule_type_count,
            )
        except LLMFacilityError as exc:
            return _ontology_runner_failed(exc.code, exc.message)
        except Exception:
            return _ontology_runner_failed("LLM_PROVIDER_ERROR", "story ontology generation failed")

        return {
            "status": "completed",
            "module_key": STORY_ONTOLOGY_MODULE_KEY,
            "model_id": resolution.model_id,
            "ontology_snapshot_id": ontology_snapshot_id,
            "entity_type_count": entity_type_count,
            "relationship_type_count": relationship_type_count,
            "world_rule_type_count": world_rule_type_count,
        }


class LLMFacilityEntityResolutionRunner:
    def __init__(
        self,
        *,
        binding_resolver: Any,
        credential_provider: Any,
        chat_client: Any,
        entity_resolution_snapshot_writer: EntityResolutionSnapshotWriter,
    ) -> None:
        self._binding_resolver = binding_resolver
        self._credential_provider = credential_provider
        self._chat_client = chat_client
        self._entity_resolution_snapshot_writer = entity_resolution_snapshot_writer

    def resolve(
        self,
        *,
        context: AgentContext,
        module_key: str,
    ) -> dict[str, Any]:
        if module_key != ENTITY_RESOLUTION_MODULE_KEY:
            return _entity_resolution_runner_failed(
                "VALIDATION_FAILED",
                f"LLMFacilityEntityResolutionRunner only supports {ENTITY_RESOLUTION_MODULE_KEY}",
            )
        try:
            resolution = self._binding_resolver.resolve_module_binding(
                context=context,
                module_key=module_key,
            )
            _validate_entity_resolution_resolution(resolution)
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
                messages=_entity_resolution_messages(context=context),
            )
            entity_resolution = _entity_resolution_payload(response_json)
            merged_entity_count = _resolution_item_count(entity_resolution, "merged_entities")
            alias_count = _resolution_item_count(entity_resolution, "aliases")
            conflict_count = _resolution_item_count(entity_resolution, "conflicts")
            resolution_snapshot_id = self._entity_resolution_snapshot_writer.record_entity_resolution_snapshot(
                context=context,
                module_key=ENTITY_RESOLUTION_MODULE_KEY,
                model_id=resolution.model_id,
                entity_resolution=entity_resolution,
                merged_entity_count=merged_entity_count,
                alias_count=alias_count,
                conflict_count=conflict_count,
            )
        except LLMFacilityError as exc:
            return _entity_resolution_runner_failed(exc.code, exc.message)
        except Exception:
            return _entity_resolution_runner_failed("LLM_PROVIDER_ERROR", "entity resolution failed")

        return {
            "status": "completed",
            "module_key": ENTITY_RESOLUTION_MODULE_KEY,
            "model_id": resolution.model_id,
            "resolution_snapshot_id": resolution_snapshot_id,
            "merged_entity_count": merged_entity_count,
            "alias_count": alias_count,
            "conflict_count": conflict_count,
        }


class LLMFacilityAgentProfileRunner:
    def __init__(
        self,
        *,
        binding_resolver: Any,
        credential_provider: Any,
        chat_client: Any,
        agent_profile_snapshot_writer: AgentProfileSnapshotWriter,
        agent_profile_context_loader: AgentProfileContextLoader | None,
    ) -> None:
        self._binding_resolver = binding_resolver
        self._credential_provider = credential_provider
        self._chat_client = chat_client
        self._agent_profile_snapshot_writer = agent_profile_snapshot_writer
        self._agent_profile_context_loader = agent_profile_context_loader

    def generate(
        self,
        *,
        context: AgentContext,
        module_key: str,
    ) -> dict[str, Any]:
        if module_key != CHARACTER_AGENT_PROFILE_MODULE_KEY:
            return _agent_profile_runner_failed(
                "VALIDATION_FAILED",
                f"LLMFacilityAgentProfileRunner only supports {CHARACTER_AGENT_PROFILE_MODULE_KEY}",
            )
        try:
            if self._agent_profile_context_loader is None:
                raise LLMFacilityError(
                    "AGENT_PROFILE_CONTEXT_UNAVAILABLE",
                    "agent profile source context is unavailable",
                )
            try:
                loaded_context = self._agent_profile_context_loader.load_context(context=context)
            except LLMFacilityError:
                raise
            except Exception as exc:
                raise LLMFacilityError(
                    "AGENT_PROFILE_CONTEXT_LOAD_FAILED",
                    "agent profile source context load failed",
                ) from exc
            source_context = _sanitize_agent_profile_context_value(loaded_context)
            if not isinstance(source_context, dict) or not _agent_profile_context_has_content(source_context):
                raise LLMFacilityError(
                    "AGENT_PROFILE_CONTEXT_UNAVAILABLE",
                    "agent profile source context is unavailable",
                )
            resolution = self._binding_resolver.resolve_module_binding(
                context=context,
                module_key=module_key,
            )
            _validate_agent_profile_resolution(resolution)
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
                messages=_agent_profile_messages(context=context, source_context=source_context),
            )
            agent_profiles = _agent_profiles_payload(response_json)
            profile_count = _agent_profile_item_count(agent_profiles, "profiles")
            memory_seed_count = _agent_profile_item_count(agent_profiles, "memory_seeds")
            relationship_view_count = _agent_profile_item_count(agent_profiles, "relationship_views")
            profile_snapshot_id = self._agent_profile_snapshot_writer.record_agent_profile_snapshot(
                context=context,
                module_key=CHARACTER_AGENT_PROFILE_MODULE_KEY,
                model_id=resolution.model_id,
                agent_profiles=agent_profiles,
                profile_count=profile_count,
                memory_seed_count=memory_seed_count,
                relationship_view_count=relationship_view_count,
            )
        except LLMFacilityError as exc:
            return _agent_profile_runner_failed(exc.code, exc.message)
        except Exception:
            return _agent_profile_runner_failed("LLM_PROVIDER_ERROR", "agent profile generation failed")

        return {
            "status": "completed",
            "module_key": CHARACTER_AGENT_PROFILE_MODULE_KEY,
            "model_id": resolution.model_id,
            "profile_snapshot_id": profile_snapshot_id,
            "profile_count": profile_count,
            "memory_seed_count": memory_seed_count,
            "relationship_view_count": relationship_view_count,
        }


class LLMFacilityArchiveCandidateRunner:
    def __init__(
        self,
        *,
        binding_resolver: Any,
        credential_provider: Any,
        chat_client: Any,
        archive_candidate_writer: ArchiveCandidateWriter,
    ) -> None:
        self._binding_resolver = binding_resolver
        self._credential_provider = credential_provider
        self._chat_client = chat_client
        self._archive_candidate_writer = archive_candidate_writer

    def generate(
        self,
        *,
        context: AgentContext,
        module_key: str,
    ) -> dict[str, Any]:
        if module_key != NARRATIVE_ARCHIVES_MODULE_KEY:
            return _archive_runner_failed(
                "VALIDATION_FAILED",
                f"LLMFacilityArchiveCandidateRunner only supports {NARRATIVE_ARCHIVES_MODULE_KEY}",
            )
        try:
            resolution = self._binding_resolver.resolve_module_binding(
                context=context,
                module_key=module_key,
            )
            _validate_archive_candidate_resolution(resolution)
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
                messages=_archive_candidate_messages(context=context),
            )
            archive_entities = _archive_entity_candidates(response_json)
            archive_candidate_batch_id = f"narrative-archives:{context.run_id}"
            persisted = self._archive_candidate_writer.write_archive_candidates(
                context=context,
                archive_candidate_batch_id=archive_candidate_batch_id,
                model_id=resolution.model_id,
                archive_entities=archive_entities,
            )
        except LLMFacilityError as exc:
            return _archive_runner_failed(exc.code, exc.message)
        except Exception as exc:
            return _archive_runner_failed("LLM_PROVIDER_ERROR", str(exc))

        return {
            "status": "completed",
            "module_key": NARRATIVE_ARCHIVES_MODULE_KEY,
            "model_id": resolution.model_id,
            "archive_candidate_batch_id": archive_candidate_batch_id,
            "candidate_count": persisted.get("candidate_count", _archive_candidate_count(archive_entities)),
            "archive_entity_candidate_count": persisted.get(
                "archive_entity_candidate_count",
                len(archive_entities),
            ),
            "memory_candidate_count": persisted.get(
                "memory_candidate_count",
                _archive_memory_candidate_count(archive_entities),
            ),
        }


class PostgresArchiveCandidateWriter:
    def __init__(self, *, connect: Callable[[], Any], source_kind: str = "narrative_archives") -> None:
        self._connect = connect
        self._source_kind = _required_text_value(source_kind, "source_kind")

    @classmethod
    def from_database_url(
        cls,
        database_url: str,
        *,
        source_kind: str = "narrative_archives",
    ) -> "PostgresArchiveCandidateWriter":
        try:
            import psycopg
        except ImportError as exc:  # pragma: no cover - depends on optional runtime packaging
            raise RuntimeError("psycopg is required for DATABASE_URL archive candidate writes") from exc

        return cls(connect=lambda: psycopg.connect(database_url), source_kind=source_kind)

    def write_archive_candidates(
        self,
        *,
        context: AgentContext,
        archive_candidate_batch_id: str,
        model_id: str | None,
        archive_entities: list[dict[str, Any]],
    ) -> dict[str, Any]:
        if context.project_id is None:
            raise LLMFacilityError("VALIDATION_FAILED", "project_id is required to write archive candidates")
        normalized_batch_id = _required_text_value(archive_candidate_batch_id, "archive_candidate_batch_id")
        normalized_entities = _archive_entity_list(archive_entities)
        connection = self._connect()
        try:
            with connection.cursor() as cursor:
                _set_postgres_tenant_context(cursor, context)
                for entity_index, entity in enumerate(normalized_entities):
                    asset_id = self._upsert_archive_asset(
                        cursor=cursor,
                        context=context,
                        archive_candidate_batch_id=normalized_batch_id,
                        model_id=model_id,
                        entity_index=entity_index,
                        entity=entity,
                    )
                    for memory_index, memory in enumerate(entity.get("memories", [])):
                        self._upsert_archive_memory(
                            cursor=cursor,
                            context=context,
                            asset_id=asset_id,
                            archive_candidate_batch_id=normalized_batch_id,
                            entity_index=entity_index,
                            memory_index=memory_index,
                            memory=memory,
                        )
            connection.commit()
        except LLMFacilityError:
            _rollback_postgres_connection(connection)
            raise
        except Exception as exc:
            _rollback_postgres_connection(connection)
            raise LLMFacilityError(
                "ARCHIVE_CANDIDATE_WRITE_FAILED",
                "archive candidate write failed",
            ) from exc
        finally:
            connection.close()

        return {
            "status": "completed",
            "archive_candidate_batch_id": normalized_batch_id,
            "candidate_count": _archive_candidate_count(normalized_entities),
            "archive_entity_candidate_count": len(normalized_entities),
            "memory_candidate_count": _archive_memory_candidate_count(normalized_entities),
        }

    def _upsert_archive_asset(
        self,
        *,
        cursor: Any,
        context: AgentContext,
        archive_candidate_batch_id: str,
        model_id: str | None,
        entity_index: int,
        entity: dict[str, Any],
    ) -> str:
        payload = _archive_payload(entity.get("payload"))
        if model_id:
            payload["model_id"] = model_id
        source_ref = f"{archive_candidate_batch_id}:archive:{entity_index + 1}"
        cursor.execute(
            """INSERT INTO assets (
                 tenant_id, project_id, scope, asset_type, category, lifecycle,
                 title, summary, content_text, payload_jsonb, tags_jsonb,
                 source_kind, source_ref, enabled, pinned, created_by
               )
               VALUES (
                 %s, %s, 'project', 'archive_entity', %s, 'candidate',
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
                entity.get("category"),
                entity["title"],
                entity["summary"],
                entity["summary"],
                json.dumps(payload, ensure_ascii=False, separators=(",", ":")),
                json.dumps(entity.get("tags", []), ensure_ascii=False, separators=(",", ":")),
                self._source_kind,
                source_ref,
                _uuid_or_none(context.actor_user_id),
            ),
        )
        return _row_value(cursor.fetchone(), "asset_id")

    def _upsert_archive_memory(
        self,
        *,
        cursor: Any,
        context: AgentContext,
        asset_id: str,
        archive_candidate_batch_id: str,
        entity_index: int,
        memory_index: int,
        memory: dict[str, Any],
    ) -> None:
        source_ref = f"{archive_candidate_batch_id}:archive:{entity_index + 1}:memory:{memory_index + 1}"
        payload = _archive_payload(memory.get("payload"))
        cursor.execute(
            """INSERT INTO archive_memories (
                 tenant_id, asset_id, project_id, memory_type, status, summary,
                 body_text, payload_jsonb, source_kind, source_ref, enabled, created_by
               )
               VALUES (
                 %s, %s, %s, %s, 'candidate', %s,
                 %s, %s::jsonb, %s, %s, true, %s
               )
               ON CONFLICT (tenant_id, asset_id, source_kind, source_ref, memory_type)
               DO UPDATE SET
                 status = 'candidate',
                 summary = EXCLUDED.summary,
                 body_text = EXCLUDED.body_text,
                 payload_jsonb = EXCLUDED.payload_jsonb,
                 enabled = true,
                 updated_at = now()
               RETURNING memory_id""",
            (
                context.tenant_id,
                asset_id,
                context.project_id,
                memory["memory_type"],
                memory["summary"],
                memory.get("body_text"),
                json.dumps(payload, ensure_ascii=False, separators=(",", ":")),
                self._source_kind,
                source_ref,
                _uuid_or_none(context.actor_user_id),
            ),
        )
        memory_id = _row_value(cursor.fetchone(), "memory_id")
        cursor.execute(
            """INSERT INTO archive_memory_events (
                 tenant_id, memory_id, asset_id, project_id, event_type, status,
                 payload_jsonb, actor_user_id
               )
               VALUES (%s, %s, %s, %s, 'memory.candidate.generated', 'candidate', %s::jsonb, %s)""",
            (
                context.tenant_id,
                memory_id,
                asset_id,
                context.project_id,
                json.dumps(
                    {
                        "source_kind": self._source_kind,
                        "source_ref": source_ref,
                        "archive_candidate_batch_id": archive_candidate_batch_id,
                        "memory_type": memory["memory_type"],
                    },
                    ensure_ascii=False,
                    separators=(",", ":"),
                ),
                _uuid_or_none(context.actor_user_id),
            ),
        )


class PostgresSeedAssetIndexer:
    def __init__(self, *, connect: Callable[[], Any]) -> None:
        self._connect = connect

    @classmethod
    def from_database_url(cls, database_url: str) -> "PostgresSeedAssetIndexer":
        try:
            import psycopg
        except ImportError as exc:  # pragma: no cover - depends on optional runtime packaging
            raise RuntimeError("psycopg is required for DATABASE_URL seed asset indexing") from exc

        return cls(connect=lambda: psycopg.connect(database_url))

    def index(self, *, context: AgentContext) -> dict[str, Any]:
        if context.project_id is None:
            raise ValueError("project_id is required to index seed assets")
        connection = self._connect()
        try:
            with connection.cursor() as cursor:
                _set_postgres_tenant_context(cursor, context)
                entity_asset_count = self._upsert_entity_assets(cursor, context)
                relationship_asset_count = self._upsert_relationship_assets(cursor, context)
                world_rule_asset_count = self._upsert_world_rule_assets(cursor, context)
                plot_thread_asset_count = self._upsert_plot_thread_assets(cursor, context)
                search_document_count = self._upsert_search_documents(cursor, context)
            connection.commit()
            return {
                "status": "completed",
                "asset_index_batch_id": f"seed-assets:{context.run_id}",
                "indexed_asset_count": (
                    entity_asset_count
                    + relationship_asset_count
                    + world_rule_asset_count
                    + plot_thread_asset_count
                ),
                "search_document_count": search_document_count,
                "embedding_count": 0,
            }
        except Exception:
            _rollback_postgres_connection(connection)
            raise
        finally:
            connection.close()

    def _upsert_entity_assets(self, cursor: Any, context: AgentContext) -> int:
        cursor.execute(
            """WITH upserted AS (
                 INSERT INTO assets (
                   tenant_id, project_id, scope, asset_type, category, lifecycle,
                   title, summary, content_text, payload_jsonb, tags_jsonb,
                   source_kind, source_ref, enabled, pinned
                 )
                 SELECT
                   tenant_id,
                   project_id,
                   'project',
                   entity_type,
                   'entity',
                   'seed',
                   canonical_name,
                   state_summary,
                   state_summary,
                   jsonb_build_object(
                     'entity_id', entity_id::text,
                     'source_run_id', source_run_id::text,
                     'importance', importance,
                     'first_seen_segment_id', first_seen_segment_id::text
                   ),
                   '[]'::jsonb,
                   'seed_pipeline',
                   entity_id::text,
                   true,
                   false
                 FROM entities
                 WHERE tenant_id = %s
                   AND project_id = %s
                   AND source_run_id::text = %s
                 ON CONFLICT (tenant_id, project_id, source_kind, source_ref, asset_type, title)
                 DO UPDATE SET
                   summary = CASE
                     WHEN assets.lifecycle = 'seed' AND assets.pinned = false THEN EXCLUDED.summary
                     ELSE assets.summary
                   END,
                   content_text = CASE
                     WHEN assets.lifecycle = 'seed' AND assets.pinned = false THEN EXCLUDED.content_text
                     ELSE assets.content_text
                   END,
                   payload_jsonb = CASE
                     WHEN assets.lifecycle = 'seed' AND assets.pinned = false THEN EXCLUDED.payload_jsonb
                     ELSE assets.payload_jsonb
                   END,
                   enabled = CASE
                     WHEN assets.lifecycle = 'seed' AND assets.pinned = false THEN true
                     ELSE assets.enabled
                   END,
                   updated_at = now()
                 RETURNING asset_id
               )
               SELECT count(*)::int AS entity_asset_count FROM upserted""",
            (context.tenant_id, context.project_id, context.run_id),
        )
        return _row_int(cursor.fetchone(), "entity_asset_count")

    def _upsert_relationship_assets(self, cursor: Any, context: AgentContext) -> int:
        cursor.execute(
            """WITH upserted AS (
                 INSERT INTO assets (
                   tenant_id, project_id, scope, asset_type, category, lifecycle,
                   title, summary, content_text, payload_jsonb, tags_jsonb,
                   source_kind, source_ref, enabled, pinned
                 )
                 SELECT
                   tenant_id,
                   project_id,
                   'project',
                   'relationship',
                   'relationship',
                   'seed',
                   source_entity_name || ' -> ' || target_entity_name || ' / ' || relationship_type,
                   summary,
                   summary,
                   jsonb_build_object(
                     'relationship_id', relationship_id::text,
                     'source_run_id', source_run_id::text,
                     'source_entity_name', source_entity_name,
                     'target_entity_name', target_entity_name,
                     'relationship_type', relationship_type
                   ),
                   '[]'::jsonb,
                   'seed_pipeline',
                   relationship_id::text,
                   true,
                   false
                 FROM relationships
                 WHERE tenant_id = %s
                   AND project_id = %s
                   AND source_run_id::text = %s
                 ON CONFLICT (tenant_id, project_id, source_kind, source_ref, asset_type, title)
                 DO UPDATE SET
                   summary = CASE
                     WHEN assets.lifecycle = 'seed' AND assets.pinned = false THEN EXCLUDED.summary
                     ELSE assets.summary
                   END,
                   content_text = CASE
                     WHEN assets.lifecycle = 'seed' AND assets.pinned = false THEN EXCLUDED.content_text
                     ELSE assets.content_text
                   END,
                   payload_jsonb = CASE
                     WHEN assets.lifecycle = 'seed' AND assets.pinned = false THEN EXCLUDED.payload_jsonb
                     ELSE assets.payload_jsonb
                   END,
                   enabled = CASE
                     WHEN assets.lifecycle = 'seed' AND assets.pinned = false THEN true
                     ELSE assets.enabled
                   END,
                   updated_at = now()
                 RETURNING asset_id
               )
               SELECT count(*)::int AS relationship_asset_count FROM upserted""",
            (context.tenant_id, context.project_id, context.run_id),
        )
        return _row_int(cursor.fetchone(), "relationship_asset_count")

    def _upsert_world_rule_assets(self, cursor: Any, context: AgentContext) -> int:
        cursor.execute(
            """WITH upserted AS (
                 INSERT INTO assets (
                   tenant_id, project_id, scope, asset_type, category, lifecycle,
                   title, summary, content_text, payload_jsonb, tags_jsonb,
                   source_kind, source_ref, enabled, pinned
                 )
                 SELECT
                   tenant_id,
                   project_id,
                   'project',
                   'world_rule',
                   COALESCE(category, 'world'),
                   'seed',
                   rule_text,
                   rule_text,
                   rule_text,
                   jsonb_build_object(
                     'rule_evidence_id', rule_evidence_id::text,
                     'source_run_id', run_id::text,
                     'category', category,
                     'confidence', confidence
                   ),
                   '[]'::jsonb,
                   'seed_pipeline',
                   rule_evidence_id::text,
                   true,
                   false
                 FROM world_rule_evidence
                 WHERE tenant_id = %s
                   AND project_id = %s
                   AND run_id::text = %s
                 ON CONFLICT (tenant_id, project_id, source_kind, source_ref, asset_type, title)
                 DO UPDATE SET
                   summary = CASE
                     WHEN assets.lifecycle = 'seed' AND assets.pinned = false THEN EXCLUDED.summary
                     ELSE assets.summary
                   END,
                   content_text = CASE
                     WHEN assets.lifecycle = 'seed' AND assets.pinned = false THEN EXCLUDED.content_text
                     ELSE assets.content_text
                   END,
                   payload_jsonb = CASE
                     WHEN assets.lifecycle = 'seed' AND assets.pinned = false THEN EXCLUDED.payload_jsonb
                     ELSE assets.payload_jsonb
                   END,
                   enabled = CASE
                     WHEN assets.lifecycle = 'seed' AND assets.pinned = false THEN true
                     ELSE assets.enabled
                   END,
                   updated_at = now()
                 RETURNING asset_id
               )
               SELECT count(*)::int AS world_rule_asset_count FROM upserted""",
            (context.tenant_id, context.project_id, context.run_id),
        )
        return _row_int(cursor.fetchone(), "world_rule_asset_count")

    def _upsert_plot_thread_assets(self, cursor: Any, context: AgentContext) -> int:
        cursor.execute(
            """WITH upserted AS (
                 INSERT INTO assets (
                   tenant_id, project_id, scope, asset_type, category, lifecycle,
                   title, summary, content_text, payload_jsonb, tags_jsonb,
                   source_kind, source_ref, enabled, pinned
                 )
                 SELECT
                   tenant_id,
                   project_id,
                   'project',
                   'plot_thread',
                   'plot',
                   'seed',
                   title,
                   summary,
                   summary,
                   jsonb_build_object(
                     'thread_id', thread_id::text,
                     'source_run_id', source_run_id::text,
                     'status', status,
                     'first_seen_segment_id', first_seen_segment_id::text
                   ),
                   '[]'::jsonb,
                   'seed_pipeline',
                   thread_id::text,
                   true,
                   false
                 FROM plot_threads
                 WHERE tenant_id = %s
                   AND project_id = %s
                   AND source_run_id::text = %s
                 ON CONFLICT (tenant_id, project_id, source_kind, source_ref, asset_type, title)
                 DO UPDATE SET
                   summary = CASE
                     WHEN assets.lifecycle = 'seed' AND assets.pinned = false THEN EXCLUDED.summary
                     ELSE assets.summary
                   END,
                   content_text = CASE
                     WHEN assets.lifecycle = 'seed' AND assets.pinned = false THEN EXCLUDED.content_text
                     ELSE assets.content_text
                   END,
                   payload_jsonb = CASE
                     WHEN assets.lifecycle = 'seed' AND assets.pinned = false THEN EXCLUDED.payload_jsonb
                     ELSE assets.payload_jsonb
                   END,
                   enabled = CASE
                     WHEN assets.lifecycle = 'seed' AND assets.pinned = false THEN true
                     ELSE assets.enabled
                   END,
                   updated_at = now()
                 RETURNING asset_id
               )
               SELECT count(*)::int AS plot_thread_asset_count FROM upserted""",
            (context.tenant_id, context.project_id, context.run_id),
        )
        return _row_int(cursor.fetchone(), "plot_thread_asset_count")

    def _upsert_search_documents(self, cursor: Any, context: AgentContext) -> int:
        cursor.execute(
            """WITH upserted AS (
                 INSERT INTO global_search_index (
                   tenant_id, project_id, source, source_ref, entity_type,
                   title, body, tags_jsonb, payload_jsonb
                 )
                 SELECT
                   tenant_id,
                   project_id,
                   'asset',
                   asset_id::text,
                   asset_type,
                   title,
                   COALESCE(summary, content_text, title),
                   tags_jsonb,
                   jsonb_build_object(
                     'asset_id', asset_id::text,
                     'asset_type', asset_type,
                     'lifecycle', lifecycle,
                     'source_kind', source_kind,
                     'source_ref', source_ref
                   )
                 FROM assets
                 WHERE tenant_id = %s
                   AND project_id = %s
                   AND source_kind = 'seed_pipeline'
                   AND payload_jsonb->>'source_run_id' = %s
                   AND enabled = true
                 ON CONFLICT (tenant_id, project_id, source, source_ref)
                 DO UPDATE SET
                   entity_type = EXCLUDED.entity_type,
                   title = EXCLUDED.title,
                   body = EXCLUDED.body,
                   tags_jsonb = EXCLUDED.tags_jsonb,
                   payload_jsonb = EXCLUDED.payload_jsonb,
                   updated_at = now()
                 RETURNING search_document_id
               )
               SELECT count(*)::int AS search_document_count FROM upserted""",
            (context.tenant_id, context.project_id, context.run_id),
        )
        return _row_int(cursor.fetchone(), "search_document_count")


class PostgresProjectReadinessUpdater:
    def __init__(self, *, connect: Callable[[], Any]) -> None:
        self._connect = connect

    @classmethod
    def from_database_url(cls, database_url: str) -> "PostgresProjectReadinessUpdater":
        try:
            import psycopg
        except ImportError as exc:  # pragma: no cover - depends on optional runtime packaging
            raise RuntimeError("psycopg is required for DATABASE_URL project readiness persistence") from exc

        return cls(connect=lambda: psycopg.connect(database_url))

    def update(self, *, context: AgentContext) -> dict[str, Any]:
        if context.project_id is None:
            raise ValueError("project_id is required to persist project readiness snapshots")
        connection = self._connect()
        try:
            with connection.cursor() as cursor:
                _set_postgres_tenant_context(cursor, context)
                cursor.execute(
                    """WITH readiness_counts AS (
                         SELECT
                           (
                             SELECT count(*)::int
                             FROM assets
                             WHERE tenant_id = %s
                               AND project_id = %s
                               AND source_kind = 'seed_pipeline'
                               AND payload_jsonb->>'source_run_id' = %s
                               AND enabled = true
                           ) AS ready_asset_count,
                           (
                             SELECT count(*)::int
                             FROM entities
                             WHERE tenant_id = %s
                               AND project_id = %s
                               AND (
                                 source_run_id::text = %s
                                 OR metadata_jsonb @> jsonb_build_object(
                                   'observed_source_run_ids', jsonb_build_array(%s::text)
                                 )
                               )
                           ) AS ready_entity_count,
                           (
                             SELECT count(*)::int
                             FROM relationships
                             WHERE tenant_id = %s
                               AND project_id = %s
                               AND (
                                 source_run_id::text = %s
                                 OR metadata_jsonb @> jsonb_build_object(
                                   'observed_source_run_ids', jsonb_build_array(%s::text)
                                 )
                               )
                           ) AS ready_relationship_count,
                           (
                             SELECT count(*)::int
                             FROM world_rule_evidence
                             WHERE tenant_id = %s
                               AND project_id = %s
                               AND run_id::text = %s
                           ) AS ready_world_rule_count
                       )
                       INSERT INTO project_readiness_snapshots (
                         tenant_id, project_id, run_id,
                         ready_asset_count, ready_entity_count,
                         ready_relationship_count, ready_world_rule_count,
                         metadata_jsonb
                       )
                       SELECT
                         %s, %s, %s,
                         ready_asset_count, ready_entity_count,
                         ready_relationship_count, ready_world_rule_count,
                         '{}'::jsonb
                       FROM readiness_counts
                       ON CONFLICT (tenant_id, project_id, run_id)
                       DO UPDATE SET
                         ready_asset_count = EXCLUDED.ready_asset_count,
                         ready_entity_count = EXCLUDED.ready_entity_count,
                         ready_relationship_count = EXCLUDED.ready_relationship_count,
                         ready_world_rule_count = EXCLUDED.ready_world_rule_count,
                         metadata_jsonb = EXCLUDED.metadata_jsonb,
                         updated_at = now()
                       RETURNING
                         project_readiness_snapshot_id::text AS project_readiness_snapshot_id,
                         ready_asset_count,
                         ready_entity_count,
                         ready_relationship_count,
                         ready_world_rule_count""",
                    (
                        context.tenant_id,
                        context.project_id,
                        context.run_id,
                        context.tenant_id,
                        context.project_id,
                        context.run_id,
                        context.run_id,
                        context.tenant_id,
                        context.project_id,
                        context.run_id,
                        context.run_id,
                        context.tenant_id,
                        context.project_id,
                        context.run_id,
                        context.tenant_id,
                        context.project_id,
                        context.run_id,
                    ),
                )
                row = cursor.fetchone()
            connection.commit()
            return {
                "status": "completed",
                "project_readiness_snapshot_id": _row_value_at(row, "project_readiness_snapshot_id", 0),
                "ready_asset_count": _row_int_at(row, "ready_asset_count", 1),
                "ready_entity_count": _row_int_at(row, "ready_entity_count", 2),
                "ready_relationship_count": _row_int_at(row, "ready_relationship_count", 3),
                "ready_world_rule_count": _row_int_at(row, "ready_world_rule_count", 4),
            }
        except LLMFacilityError:
            _rollback_postgres_connection(connection)
            raise
        except Exception as exc:
            _rollback_postgres_connection(connection)
            raise LLMFacilityError(
                "PROJECT_READINESS_UPDATE_FAILED",
                "project readiness update failed",
            ) from exc
        finally:
            connection.close()


class PostgresRuntimeFactsWriter:
    def __init__(self, *, connect: Callable[[], Any]) -> None:
        self._connect = connect

    @classmethod
    def from_database_url(cls, database_url: str) -> "PostgresRuntimeFactsWriter":
        try:
            import psycopg
        except ImportError as exc:  # pragma: no cover - depends on optional runtime packaging
            raise RuntimeError("psycopg is required for DATABASE_URL runtime facts persistence") from exc

        return cls(connect=lambda: psycopg.connect(database_url))

    def record_runtime_facts(
        self,
        *,
        context: AgentContext,
        reading_notes: list[dict[str, Any]] | None = None,
    ) -> dict[str, int]:
        if context.project_id is None:
            raise ValueError("project_id is required to persist runtime facts")
        connection = self._connect()
        try:
            with connection.cursor() as cursor:
                _set_postgres_tenant_context(cursor, context)
                notes = _validated_runtime_fact_notes(
                    reading_notes if reading_notes is not None else self._load_reading_notes(cursor, context)
                )
                counts = self._persist_notes(cursor, context, notes)
            connection.commit()
            return counts
        except Exception:
            _rollback_postgres_connection(connection)
            raise
        finally:
            connection.close()

    def _load_reading_notes(self, cursor: Any, context: AgentContext) -> list[dict[str, Any]]:
        cursor.execute(
            """SELECT segment_id, payload_jsonb, summary
               FROM reading_segment_notes
               WHERE tenant_id = %s
                 AND project_id = %s
                 AND run_id = %s
               ORDER BY created_at ASC""",
            (context.tenant_id, context.project_id, context.run_id),
        )
        rows = cursor.fetchall()
        return [_reading_note_from_row(row) for row in rows]

    def _persist_notes(
        self,
        cursor: Any,
        context: AgentContext,
        notes: list[dict[str, Any]],
    ) -> dict[str, int]:
        entity_count = 0
        entity_label_count = 0
        relationship_count = 0
        plot_thread_count = 0
        thread_lifecycle_count = 0
        narrative_arc_count = 0
        volume_summary_count = 0
        world_rule_count = 0
        character_event_count = 0
        world_event_count = 0
        relationship_event_count = 0
        consistency_note_count = 0
        segment_summary_count = 0
        for note in notes:
            segment_id = _required_note_segment_id(note)
            segment_summary = _optional_text(note, "summary")
            if segment_summary is not None and segment_summary.strip():
                self._upsert_segment_summary(cursor, context, segment_id, segment_summary.strip())
                segment_summary_count += 1
            payload = _runtime_note_payload(note)
            for entity in _runtime_entities_from_payload(payload):
                entity_id = self._upsert_entity(cursor, context, segment_id, entity)
                for alias in entity["aliases"]:
                    self._upsert_entity_alias(cursor, context, entity_id, alias)
                for label in entity["labels"]:
                    self._upsert_entity_label(cursor, context, entity_id, segment_id, label)
                    entity_label_count += 1
                if entity["evidence"]:
                    self._upsert_entity_evidence(cursor, context, entity_id, segment_id, entity["evidence"])
                entity_count += 1
            for relationship in _runtime_relationships_from_payload(payload):
                self._upsert_relationship(cursor, context, segment_id, relationship)
                relationship_count += 1
            for thread in _runtime_plot_threads_from_payload(payload):
                thread_id = self._upsert_plot_thread(cursor, context, segment_id, thread)
                self._upsert_thread_lifecycle(cursor, context, thread_id, segment_id, thread)
                plot_thread_count += 1
                thread_lifecycle_count += 1
            for arc in _runtime_narrative_arcs_from_payload(payload):
                self._upsert_narrative_arc(cursor, context, segment_id, arc)
                narrative_arc_count += 1
            for volume_summary in _runtime_volume_summaries_from_payload(payload):
                self._upsert_volume_summary(cursor, context, segment_id, volume_summary)
                volume_summary_count += 1
            for rule in _runtime_world_rules_from_payload(payload):
                self._upsert_world_rule(cursor, context, segment_id, rule)
                world_rule_count += 1
            for event in _runtime_character_events_from_payload(payload):
                self._upsert_character_event(cursor, context, segment_id, event)
                character_event_count += 1
            for event in _runtime_world_events_from_payload(payload):
                self._upsert_world_event(cursor, context, segment_id, event)
                world_event_count += 1
            for event in _runtime_relationship_events_from_payload(payload):
                self._upsert_relationship_event(cursor, context, segment_id, event)
                relationship_event_count += 1
            for note_value in _runtime_consistency_notes_from_payload(payload):
                self._upsert_consistency_note(cursor, context, segment_id, note_value)
                consistency_note_count += 1
        return {
            "entity_count": entity_count,
            "entity_label_count": entity_label_count,
            "relationship_count": relationship_count,
            "plot_thread_count": plot_thread_count,
            "thread_lifecycle_count": thread_lifecycle_count,
            "narrative_arc_count": narrative_arc_count,
            "volume_summary_count": volume_summary_count,
            "world_rule_count": world_rule_count,
            "character_event_count": character_event_count,
            "world_event_count": world_event_count,
            "relationship_event_count": relationship_event_count,
            "consistency_note_count": consistency_note_count,
            "segment_summary_count": segment_summary_count,
        }

    def _upsert_segment_summary(
        self,
        cursor: Any,
        context: AgentContext,
        segment_id: str,
        summary: str,
    ) -> None:
        cursor.execute(
            """INSERT INTO segment_summaries (
                 tenant_id, project_id, run_id, segment_id, summary,
                 source_kind, metadata_jsonb
               )
               VALUES (%s, %s, %s, %s, %s, 'sequential_reading', '{}'::jsonb)
               ON CONFLICT (tenant_id, project_id, run_id, segment_id, source_kind)
               DO UPDATE SET
                 summary = EXCLUDED.summary,
                 updated_at = now()""",
            (context.tenant_id, context.project_id, context.run_id, segment_id, summary),
        )

    def _upsert_entity(
        self,
        cursor: Any,
        context: AgentContext,
        segment_id: str,
        entity: dict[str, Any],
    ) -> str:
        cursor.execute(
            """INSERT INTO entities (
                 tenant_id, project_id, source_run_id, canonical_name, entity_type,
                 importance, state_summary, first_seen_segment_id, metadata_jsonb
               )
               VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s::jsonb)
               ON CONFLICT (tenant_id, project_id, canonical_name)
               DO UPDATE SET
                 entity_type = EXCLUDED.entity_type,
                 importance = COALESCE(EXCLUDED.importance, entities.importance),
                 state_summary = COALESCE(EXCLUDED.state_summary, entities.state_summary),
                 first_seen_segment_id = COALESCE(entities.first_seen_segment_id, EXCLUDED.first_seen_segment_id),
                 metadata_jsonb = jsonb_set(
                   entities.metadata_jsonb || (EXCLUDED.metadata_jsonb - 'observed_source_run_ids'),
                   '{observed_source_run_ids}',
                   CASE
                     WHEN COALESCE(entities.metadata_jsonb->'observed_source_run_ids', '[]'::jsonb)
                          @> (EXCLUDED.metadata_jsonb->'observed_source_run_ids')
                     THEN COALESCE(entities.metadata_jsonb->'observed_source_run_ids', '[]'::jsonb)
                     ELSE COALESCE(entities.metadata_jsonb->'observed_source_run_ids', '[]'::jsonb)
                          || (EXCLUDED.metadata_jsonb->'observed_source_run_ids')
                   END
                 ),
                 updated_at = now()
               RETURNING entity_id""",
            (
                context.tenant_id,
                context.project_id,
                context.run_id,
                entity["name"],
                entity["entity_type"],
                entity["importance"],
                entity["state_summary"],
                segment_id,
                _json_object(
                    {
                        "source": "sequential_reading",
                        "observed_source_run_ids": [context.run_id],
                    }
                ),
            ),
        )
        row = cursor.fetchone()
        return _row_value(row, "entity_id")

    def _upsert_entity_alias(self, cursor: Any, context: AgentContext, entity_id: str, alias: str) -> None:
        cursor.execute(
            """INSERT INTO entity_aliases (tenant_id, project_id, entity_id, alias)
               VALUES (%s, %s, %s, %s)
               ON CONFLICT (tenant_id, entity_id, alias)
               DO UPDATE SET updated_at = now()""",
            (context.tenant_id, context.project_id, entity_id, alias),
        )

    def _upsert_entity_label(
        self,
        cursor: Any,
        context: AgentContext,
        entity_id: str,
        segment_id: str,
        label: dict[str, Any],
    ) -> None:
        cursor.execute(
            """INSERT INTO entity_labels (
                 tenant_id, project_id, entity_id, run_id, segment_id,
                 label, label_type, source_kind, metadata_jsonb
               )
               VALUES (%s, %s, %s, %s, %s, %s, %s, 'sequential_reading', '{}'::jsonb)
               ON CONFLICT (tenant_id, entity_id, run_id, segment_id, label, source_kind)
               DO UPDATE SET
                 label_type = COALESCE(EXCLUDED.label_type, entity_labels.label_type),
                 updated_at = now()""",
            (
                context.tenant_id,
                context.project_id,
                entity_id,
                context.run_id,
                segment_id,
                label["label"],
                label["label_type"],
            ),
        )

    def _upsert_entity_evidence(
        self,
        cursor: Any,
        context: AgentContext,
        entity_id: str,
        segment_id: str,
        evidence: str,
    ) -> None:
        cursor.execute(
            """INSERT INTO entity_evidence (
                 tenant_id, project_id, entity_id, run_id, segment_id,
                 evidence_text, source_kind, metadata_jsonb
               )
               VALUES (%s, %s, %s, %s, %s, %s, 'sequential_reading', '{}'::jsonb)
               ON CONFLICT (tenant_id, entity_id, run_id, segment_id, source_kind, evidence_text)
               DO UPDATE SET updated_at = now()""",
            (context.tenant_id, context.project_id, entity_id, context.run_id, segment_id, evidence),
        )

    def _upsert_relationship(
        self,
        cursor: Any,
        context: AgentContext,
        segment_id: str,
        relationship: dict[str, Any],
    ) -> None:
        cursor.execute(
            """INSERT INTO relationships (
                 tenant_id, project_id, source_entity_name, target_entity_name,
                 relationship_type, summary, source_run_id, first_seen_segment_id,
                 evidence_text, metadata_jsonb
               )
               VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s::jsonb)
               ON CONFLICT (tenant_id, project_id, source_entity_name, target_entity_name, relationship_type)
               DO UPDATE SET
                 summary = COALESCE(EXCLUDED.summary, relationships.summary),
                 first_seen_segment_id = COALESCE(relationships.first_seen_segment_id, EXCLUDED.first_seen_segment_id),
                 evidence_text = COALESCE(EXCLUDED.evidence_text, relationships.evidence_text),
                 metadata_jsonb = jsonb_set(
                   relationships.metadata_jsonb || (EXCLUDED.metadata_jsonb - 'observed_source_run_ids'),
                   '{observed_source_run_ids}',
                   CASE
                     WHEN COALESCE(relationships.metadata_jsonb->'observed_source_run_ids', '[]'::jsonb)
                          @> (EXCLUDED.metadata_jsonb->'observed_source_run_ids')
                     THEN COALESCE(relationships.metadata_jsonb->'observed_source_run_ids', '[]'::jsonb)
                     ELSE COALESCE(relationships.metadata_jsonb->'observed_source_run_ids', '[]'::jsonb)
                          || (EXCLUDED.metadata_jsonb->'observed_source_run_ids')
                   END
                 ),
                 updated_at = now()""",
            (
                context.tenant_id,
                context.project_id,
                relationship["source_entity_name"],
                relationship["target_entity_name"],
                relationship["relationship_type"],
                relationship["summary"],
                context.run_id,
                segment_id,
                relationship["evidence"],
                _json_object({"observed_source_run_ids": [context.run_id]}),
            ),
        )

    def _upsert_plot_thread(
        self,
        cursor: Any,
        context: AgentContext,
        segment_id: str,
        thread: dict[str, Any],
    ) -> str:
        cursor.execute(
            """INSERT INTO plot_threads (
                 tenant_id, project_id, source_run_id, title, status,
                 summary, first_seen_segment_id, evidence_text, metadata_jsonb
               )
               VALUES (%s, %s, %s, %s, %s, %s, %s, %s, '{}'::jsonb)
               ON CONFLICT (tenant_id, project_id, title)
               DO UPDATE SET
                 status = COALESCE(EXCLUDED.status, plot_threads.status),
                 summary = COALESCE(EXCLUDED.summary, plot_threads.summary),
                 first_seen_segment_id = COALESCE(plot_threads.first_seen_segment_id, EXCLUDED.first_seen_segment_id),
                 evidence_text = COALESCE(EXCLUDED.evidence_text, plot_threads.evidence_text),
                 updated_at = now()
               RETURNING thread_id""",
            (
                context.tenant_id,
                context.project_id,
                context.run_id,
                thread["title"],
                thread["status"],
                thread["summary"],
                segment_id,
                thread["evidence"],
            ),
        )
        row = cursor.fetchone()
        return _row_value(row, "thread_id")

    def _upsert_thread_lifecycle(
        self,
        cursor: Any,
        context: AgentContext,
        thread_id: str,
        segment_id: str,
        thread: dict[str, Any],
    ) -> None:
        cursor.execute(
            """INSERT INTO thread_lifecycle (
                 tenant_id, project_id, thread_id, run_id, segment_id,
                 status, summary, evidence_text, metadata_jsonb
               )
               VALUES (%s, %s, %s, %s, %s, %s, %s, %s, '{}'::jsonb)
               ON CONFLICT (tenant_id, project_id, thread_id, run_id, segment_id, status)
               DO UPDATE SET
                 summary = COALESCE(EXCLUDED.summary, thread_lifecycle.summary),
                 evidence_text = COALESCE(EXCLUDED.evidence_text, thread_lifecycle.evidence_text),
                 updated_at = now()""",
            (
                context.tenant_id,
                context.project_id,
                thread_id,
                context.run_id,
                segment_id,
                thread["status"],
                thread["summary"],
                thread["evidence"],
            ),
        )

    def _upsert_narrative_arc(
        self,
        cursor: Any,
        context: AgentContext,
        segment_id: str,
        arc: dict[str, Any],
    ) -> None:
        cursor.execute(
            """INSERT INTO narrative_arcs (
                 tenant_id, project_id, run_id, segment_id, title,
                 arc_type, summary, evidence_text, metadata_jsonb
               )
               VALUES (%s, %s, %s, %s, %s, %s, %s, %s, '{}'::jsonb)
               ON CONFLICT (tenant_id, project_id, run_id, segment_id, title)
               DO UPDATE SET
                 arc_type = COALESCE(EXCLUDED.arc_type, narrative_arcs.arc_type),
                 summary = COALESCE(EXCLUDED.summary, narrative_arcs.summary),
                 evidence_text = COALESCE(EXCLUDED.evidence_text, narrative_arcs.evidence_text),
                 updated_at = now()""",
            (
                context.tenant_id,
                context.project_id,
                context.run_id,
                segment_id,
                arc["title"],
                arc["arc_type"],
                arc["summary"],
                arc["evidence"],
            ),
        )

    def _upsert_volume_summary(
        self,
        cursor: Any,
        context: AgentContext,
        segment_id: str,
        volume_summary: dict[str, Any],
    ) -> None:
        cursor.execute(
            """INSERT INTO volume_summaries (
                 tenant_id, project_id, run_id, segment_id, volume_key,
                 title, summary, evidence_text, source_kind, metadata_jsonb
               )
               VALUES (%s, %s, %s, %s, %s, %s, %s, %s, 'sequential_reading', '{}'::jsonb)
               ON CONFLICT (tenant_id, project_id, run_id, segment_id, volume_key, source_kind)
               DO UPDATE SET
                 title = COALESCE(EXCLUDED.title, volume_summaries.title),
                 summary = EXCLUDED.summary,
                 evidence_text = COALESCE(EXCLUDED.evidence_text, volume_summaries.evidence_text),
                 updated_at = now()""",
            (
                context.tenant_id,
                context.project_id,
                context.run_id,
                segment_id,
                volume_summary["volume_key"],
                volume_summary["title"],
                volume_summary["summary"],
                volume_summary["evidence"],
            ),
        )

    def _upsert_world_rule(
        self,
        cursor: Any,
        context: AgentContext,
        segment_id: str,
        rule: dict[str, Any],
    ) -> None:
        cursor.execute(
            """INSERT INTO world_rule_evidence (
                 tenant_id, project_id, run_id, segment_id, rule_text,
                 evidence_text, category, confidence, metadata_jsonb
               )
               VALUES (%s, %s, %s, %s, %s, %s, %s, %s, '{}'::jsonb)
               ON CONFLICT (tenant_id, project_id, run_id, segment_id, rule_text)
               DO UPDATE SET
                 evidence_text = COALESCE(EXCLUDED.evidence_text, world_rule_evidence.evidence_text),
                 category = COALESCE(EXCLUDED.category, world_rule_evidence.category),
                 confidence = COALESCE(EXCLUDED.confidence, world_rule_evidence.confidence),
                 updated_at = now()""",
            (
                context.tenant_id,
                context.project_id,
                context.run_id,
                segment_id,
                rule["rule_text"],
                rule["evidence"],
                rule["category"],
                rule["confidence"],
            ),
        )

    def _upsert_character_event(
        self,
        cursor: Any,
        context: AgentContext,
        segment_id: str,
        event: dict[str, Any],
    ) -> None:
        cursor.execute(
            """INSERT INTO character_events (
                 tenant_id, project_id, run_id, segment_id, entity_name,
                 event_summary, event_kind, evidence_text, metadata_jsonb
               )
               VALUES (%s, %s, %s, %s, %s, %s, %s, %s, '{}'::jsonb)
               ON CONFLICT (tenant_id, project_id, run_id, segment_id, entity_name, event_summary)
               DO UPDATE SET
                 event_kind = COALESCE(EXCLUDED.event_kind, character_events.event_kind),
                 evidence_text = COALESCE(EXCLUDED.evidence_text, character_events.evidence_text),
                 updated_at = now()""",
            (
                context.tenant_id,
                context.project_id,
                context.run_id,
                segment_id,
                event["entity_name"],
                event["event_summary"],
                event["event_kind"],
                event["evidence"],
            ),
        )

    def _upsert_world_event(
        self,
        cursor: Any,
        context: AgentContext,
        segment_id: str,
        event: dict[str, Any],
    ) -> None:
        cursor.execute(
            """INSERT INTO world_events (
                 tenant_id, project_id, run_id, segment_id, event_summary,
                 event_kind, evidence_text, metadata_jsonb
               )
               VALUES (%s, %s, %s, %s, %s, %s, %s, '{}'::jsonb)
               ON CONFLICT (tenant_id, project_id, run_id, segment_id, event_summary)
               DO UPDATE SET
                 event_kind = COALESCE(EXCLUDED.event_kind, world_events.event_kind),
                 evidence_text = COALESCE(EXCLUDED.evidence_text, world_events.evidence_text),
                 updated_at = now()""",
            (
                context.tenant_id,
                context.project_id,
                context.run_id,
                segment_id,
                event["event_summary"],
                event["event_kind"],
                event["evidence"],
            ),
        )

    def _upsert_relationship_event(
        self,
        cursor: Any,
        context: AgentContext,
        segment_id: str,
        event: dict[str, Any],
    ) -> None:
        cursor.execute(
            """INSERT INTO relationship_events (
                 tenant_id, project_id, run_id, segment_id, source_entity_name,
                 target_entity_name, relationship_type, event_summary,
                 evidence_text, metadata_jsonb
               )
               VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, '{}'::jsonb)
               ON CONFLICT (
                 tenant_id, project_id, run_id, segment_id,
                 source_entity_name, target_entity_name, relationship_type, event_summary
               )
               DO UPDATE SET
                 evidence_text = COALESCE(EXCLUDED.evidence_text, relationship_events.evidence_text),
                 updated_at = now()""",
            (
                context.tenant_id,
                context.project_id,
                context.run_id,
                segment_id,
                event["source_entity_name"],
                event["target_entity_name"],
                event["relationship_type"],
                event["event_summary"],
                event["evidence"],
            ),
        )

    def _upsert_consistency_note(
        self,
        cursor: Any,
        context: AgentContext,
        segment_id: str,
        note: dict[str, Any],
    ) -> None:
        cursor.execute(
            """INSERT INTO consistency_notes (
                 tenant_id, project_id, run_id, segment_id, note_type,
                 severity, summary, evidence_text, metadata_jsonb
               )
               VALUES (%s, %s, %s, %s, %s, %s, %s, %s, '{}'::jsonb)
               ON CONFLICT (tenant_id, project_id, run_id, segment_id, note_type, summary)
               DO UPDATE SET
                 severity = COALESCE(EXCLUDED.severity, consistency_notes.severity),
                 evidence_text = COALESCE(EXCLUDED.evidence_text, consistency_notes.evidence_text),
                 updated_at = now()""",
            (
                context.tenant_id,
                context.project_id,
                context.run_id,
                segment_id,
                note["note_type"],
                note["severity"],
                note["summary"],
                note["evidence"],
            ),
        )


def _base_payload(context: AgentContext, upload_id: str | None) -> dict[str, Any]:
    return {
        "tenant_id": context.tenant_id,
        "project_id": context.project_id,
        "run_id": context.run_id,
        "workflow_type": context.workflow_type,
        "upload_id": upload_id,
    }


def _sanitize_workflow_event_payload(value: Any) -> Any:
    if isinstance(value, dict):
        return {
            key: _sanitize_workflow_event_payload(child)
            for key, child in value.items()
            if key.lower() not in SENSITIVE_WORKFLOW_EVENT_KEYS
        }
    if isinstance(value, list):
        return [_sanitize_workflow_event_payload(child) for child in value]
    return value


def _required_segment_order(segment: dict[str, Any]) -> int:
    value = segment.get("segment_order")
    if not isinstance(value, int) or value < 0:
        raise ValueError("segment_order must be a non-negative integer")
    return value


def _required_segment_id(segment: dict[str, Any]) -> str:
    value = segment.get("segment_id")
    if not isinstance(value, str) or not value.strip():
        raise ValueError("segment_id is required for text segments")
    return value.strip()


def _optional_int(segment: dict[str, Any], key: str) -> int | None:
    value = segment.get(key)
    if value is None:
        return None
    return _non_negative_int(value, key)


def _non_negative_int(value: int, field_name: str) -> int:
    if not isinstance(value, int) or value < 0:
        raise ValueError(f"{field_name} must be a non-negative integer")
    return value


def _optional_text(segment: dict[str, Any], key: str) -> str | None:
    value = segment.get(key)
    if value is None:
        return None
    if not isinstance(value, str):
        raise ValueError(f"{key} must be a string")
    return value


def _metadata_json(segment: dict[str, Any]) -> str:
    metadata = segment.get("metadata_jsonb", {})
    return _json_object(metadata)


def _json_object(value: dict[str, Any]) -> str:
    if not isinstance(value, dict):
        raise ValueError("json value must be an object")
    sanitized_metadata = _sanitize_workflow_event_payload(value)
    return json.dumps(sanitized_metadata, ensure_ascii=False, separators=(",", ":"))


def _seed_analysis_json(value: dict[str, Any]) -> str:
    if not isinstance(value, dict):
        raise ValueError("seed_analysis must be an object")
    sanitized_analysis = _sanitize_seed_analysis_value(value)
    if not isinstance(sanitized_analysis, dict):
        raise ValueError("seed_analysis must be an object")
    return json.dumps(sanitized_analysis, ensure_ascii=False, separators=(",", ":"))


def _sanitize_seed_analysis_value(value: Any) -> Any:
    if isinstance(value, dict):
        return {
            str(key): _sanitize_seed_analysis_value(child)
            for key, child in value.items()
            if not _is_sensitive_seed_analysis_key(str(key))
        }
    if isinstance(value, list):
        return [_sanitize_seed_analysis_value(child) for child in value]
    return value


def _is_sensitive_seed_analysis_key(key: str) -> bool:
    normalized = re.sub(r"[^a-z0-9]", "", key.lower())
    return normalized in NORMALIZED_SENSITIVE_SEED_ANALYSIS_KEYS


AGENT_PROFILE_PRIVATE_SNAPSHOT_BLOCKED_KEYS = {
    "api_key",
    "artifact_object_key",
    "content",
    "content_text",
    "credential_ref",
    "draft",
    "encrypted_api_key",
    "encrypted_credential",
    "evidence_text",
    "manuscript",
    "material_text",
    "metadata_jsonb",
    "object_key",
    "prompt",
    "provider_raw_body",
    "provider_response",
    "raw_body",
    "raw_content",
    "raw_text",
    "response",
    "segment_object_key",
    "source_material",
    "source_object_key",
    "source_text",
    "text",
}


def _json_agent_profile_object(value: dict[str, Any]) -> str:
    if not isinstance(value, dict):
        raise ValueError("agent profile snapshot must be an object")
    sanitized = _sanitize_agent_profile_value(value)
    if not isinstance(sanitized, dict):
        raise ValueError("agent profile snapshot must be an object")
    return json.dumps(sanitized, ensure_ascii=False, separators=(",", ":"))


def _ontology_runner_failed(code: str, message: str) -> dict[str, Any]:
    return {
        "status": "failed",
        "module_key": STORY_ONTOLOGY_MODULE_KEY,
        "error": {"code": code, "message": message},
    }


def _entity_resolution_runner_failed(code: str, message: str) -> dict[str, Any]:
    return {
        "status": "failed",
        "module_key": ENTITY_RESOLUTION_MODULE_KEY,
        "error": {"code": code, "message": message},
    }


def _agent_profile_runner_failed(code: str, message: str) -> dict[str, Any]:
    return {
        "status": "failed",
        "module_key": CHARACTER_AGENT_PROFILE_MODULE_KEY,
        "error": {"code": code, "message": message},
    }


def _validate_ontology_resolution(resolution: Any) -> None:
    if getattr(resolution, "module_key", None) != STORY_ONTOLOGY_MODULE_KEY:
        raise LLMFacilityError(
            "LLM_MODULE_UNBOUND",
            f"resolved module key does not match {STORY_ONTOLOGY_MODULE_KEY}",
        )
    if not getattr(resolution, "supports_json", False):
        raise LLMFacilityError(
            "LLM_MODULE_CAPABILITY_MISSING",
            f"{STORY_ONTOLOGY_MODULE_KEY} requires a JSON-capable model",
        )
    for field_name in ("channel_id", "model_id", "provider", "base_url", "credential_ref"):
        value = getattr(resolution, field_name, None)
        if not isinstance(value, str) or not value.strip():
            raise LLMFacilityError("LLM_PROVIDER_ERROR", f"resolved LLM module is missing {field_name}")


def _validate_entity_resolution_resolution(resolution: Any) -> None:
    if getattr(resolution, "module_key", None) != ENTITY_RESOLUTION_MODULE_KEY:
        raise LLMFacilityError(
            "LLM_MODULE_UNBOUND",
            f"resolved module key does not match {ENTITY_RESOLUTION_MODULE_KEY}",
        )
    if not getattr(resolution, "supports_json", False):
        raise LLMFacilityError(
            "LLM_MODULE_CAPABILITY_MISSING",
            f"{ENTITY_RESOLUTION_MODULE_KEY} requires a JSON-capable model",
        )
    for field_name in ("channel_id", "model_id", "provider", "base_url", "credential_ref"):
        value = getattr(resolution, field_name, None)
        if not isinstance(value, str) or not value.strip():
            raise LLMFacilityError("LLM_PROVIDER_ERROR", f"resolved LLM module is missing {field_name}")


def _validate_agent_profile_resolution(resolution: Any) -> None:
    if getattr(resolution, "module_key", None) != CHARACTER_AGENT_PROFILE_MODULE_KEY:
        raise LLMFacilityError(
            "LLM_MODULE_UNBOUND",
            f"resolved module key does not match {CHARACTER_AGENT_PROFILE_MODULE_KEY}",
        )
    if not getattr(resolution, "supports_json", False):
        raise LLMFacilityError(
            "LLM_MODULE_CAPABILITY_MISSING",
            f"{CHARACTER_AGENT_PROFILE_MODULE_KEY} requires a JSON-capable model",
        )
    for field_name in ("channel_id", "model_id", "provider", "base_url", "credential_ref"):
        value = getattr(resolution, field_name, None)
        if not isinstance(value, str) or not value.strip():
            raise LLMFacilityError("LLM_PROVIDER_ERROR", f"resolved LLM module is missing {field_name}")


def _ontology_messages(*, context: AgentContext) -> list[dict[str, str]]:
    return [
        {
            "role": "system",
            "content": (
                "You are the MiroFish story_ontology module. Return one JSON object with a "
                "seed_ontology object containing entity_types, relationship_types, and "
                "world_rule_types arrays. Keep entries concise. Do not include prompt bodies, raw "
                "source material copies, API keys, credentials, or provider metadata."
            ),
        },
        {
            "role": "user",
            "content": json.dumps(
                {
                    "tenant_id": context.tenant_id,
                    "project_id": context.project_id,
                    "run_id": context.run_id,
                    "module_key": STORY_ONTOLOGY_MODULE_KEY,
                    "task": "Generate a story ontology taxonomy for downstream entity resolution.",
                },
                ensure_ascii=False,
                separators=(",", ":"),
            ),
        },
    ]


def _entity_resolution_messages(*, context: AgentContext) -> list[dict[str, str]]:
    return [
        {
            "role": "system",
            "content": (
                "You are the MiroFish entity_resolution module. Return one JSON object with an "
                "entity_resolution object containing merged_entities, aliases, and conflicts arrays. "
                "Do not include prompt bodies, raw source material copies, API keys, credentials, or "
                "provider metadata."
            ),
        },
        {
            "role": "user",
            "content": json.dumps(
                {
                    "tenant_id": context.tenant_id,
                    "project_id": context.project_id,
                    "run_id": context.run_id,
                    "module_key": ENTITY_RESOLUTION_MODULE_KEY,
                    "task": "Merge aliases and resolve entity identity conflicts from Seed canon facts.",
                },
                ensure_ascii=False,
                separators=(",", ":"),
            ),
        },
    ]


def _agent_profile_messages(
    *,
    context: AgentContext,
    source_context: dict[str, Any] | None = None,
) -> list[dict[str, str]]:
    user_payload: dict[str, Any] = {
        "tenant_id": context.tenant_id,
        "project_id": context.project_id,
        "run_id": context.run_id,
        "module_key": CHARACTER_AGENT_PROFILE_MODULE_KEY,
        "task": "Generate character agent profiles from resolved Seed canon metadata.",
    }
    if source_context is not None:
        user_payload["source_context"] = source_context
    return [
        {
            "role": "system",
            "content": (
                "You are the MiroFish character_agent_profile module. Return one JSON object with an "
                "agent_profiles object containing profiles, memory_seeds, and relationship_views arrays. "
                "Do not include prompt bodies, raw source material copies, API keys, credentials, or "
                "provider metadata."
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


def _seed_ontology_payload(response_json: dict[str, Any]) -> dict[str, Any]:
    seed_ontology = response_json.get("seed_ontology")
    if seed_ontology is None:
        seed_ontology = response_json.get("ontology")
    if not isinstance(seed_ontology, dict):
        raise LLMFacilityError("SCHEMA_VALIDATION_FAILED", "seed_ontology must be an object")
    sanitized = _sanitize_ontology_value(seed_ontology)
    if not isinstance(sanitized, dict):
        raise LLMFacilityError("SCHEMA_VALIDATION_FAILED", "seed_ontology must be an object")
    for field_name in ("entity_types", "relationship_types", "world_rule_types"):
        _ontology_type_count(sanitized, field_name)
    return sanitized


def _entity_resolution_payload(response_json: dict[str, Any]) -> dict[str, Any]:
    entity_resolution = response_json.get("entity_resolution")
    if entity_resolution is None:
        entity_resolution = response_json.get("resolution")
    if not isinstance(entity_resolution, dict):
        raise LLMFacilityError("SCHEMA_VALIDATION_FAILED", "entity_resolution must be an object")
    sanitized = _sanitize_ontology_value(entity_resolution)
    if not isinstance(sanitized, dict):
        raise LLMFacilityError("SCHEMA_VALIDATION_FAILED", "entity_resolution must be an object")
    for field_name in ("merged_entities", "aliases", "conflicts"):
        _resolution_item_count(sanitized, field_name)
    return sanitized


def _agent_profiles_payload(response_json: dict[str, Any]) -> dict[str, Any]:
    agent_profiles = response_json.get("agent_profiles")
    if agent_profiles is None:
        agent_profiles = response_json.get("profiles")
    if not isinstance(agent_profiles, dict):
        raise LLMFacilityError("SCHEMA_VALIDATION_FAILED", "agent_profiles must be an object")
    sanitized = _sanitize_agent_profile_value(agent_profiles)
    if not isinstance(sanitized, dict):
        raise LLMFacilityError("SCHEMA_VALIDATION_FAILED", "agent_profiles must be an object")
    for field_name in ("profiles", "memory_seeds", "relationship_views"):
        _agent_profile_item_count(sanitized, field_name)
    return sanitized


def _sanitize_ontology_value(value: Any) -> Any:
    if isinstance(value, dict):
        return {
            str(key): _sanitize_ontology_value(child)
            for key, child in value.items()
            if str(key).lower() not in SENSITIVE_ARCHIVE_CANDIDATE_KEYS
        }
    if isinstance(value, list):
        return [_sanitize_ontology_value(child) for child in value]
    return value


def _sanitize_agent_profile_value(value: Any) -> Any:
    if isinstance(value, dict):
        return {
            str(key): _sanitize_agent_profile_value(child)
            for key, child in value.items()
            if str(key).lower() not in AGENT_PROFILE_PRIVATE_SNAPSHOT_BLOCKED_KEYS
        }
    if isinstance(value, list):
        return [_sanitize_agent_profile_value(child) for child in value]
    return value


AGENT_PROFILE_CONTEXT_ITEM_ALLOWED_KEYS = {
    "alias",
    "aliases",
    "alias_count",
    "canonical_name",
    "conflict_count",
    "conflict_type",
    "description",
    "entity_id",
    "entity_type",
    "importance",
    "merged_entity_count",
    "model_id",
    "name",
    "reason",
    "relationship_id",
    "relationship_type",
    "segment_id",
    "segment_order",
    "snapshot_id",
    "source_entity_name",
    "state_summary",
    "summary",
    "target_entity_name",
    "title",
}

AGENT_PROFILE_CONTEXT_SEMANTIC_KEYS = {
    "alias",
    "aliases",
    "canonical_name",
    "conflict_type",
    "description",
    "name",
    "reason",
    "relationship_type",
    "source_entity_name",
    "state_summary",
    "summary",
    "target_entity_name",
    "title",
}


def _sanitize_agent_profile_context_value(value: Any) -> dict[str, Any]:
    if not isinstance(value, dict):
        return {}
    result: dict[str, Any] = {}
    entity_resolution = value.get("entity_resolution")
    if isinstance(entity_resolution, dict):
        projected_resolution = _project_agent_profile_resolution_context(entity_resolution)
        if projected_resolution:
            result["entity_resolution"] = projected_resolution
    canon = value.get("canon")
    if isinstance(canon, dict):
        projected_canon = _project_agent_profile_canon_context(canon)
        if projected_canon:
            result["canon"] = projected_canon
    return result


def _agent_profile_context_has_content(value: Any) -> bool:
    if not isinstance(value, dict):
        return False
    entity_resolution = value.get("entity_resolution")
    if isinstance(entity_resolution, dict):
        for field_name in ("merged_entities", "aliases", "conflicts"):
            if _agent_profile_context_list_has_content(entity_resolution.get(field_name)):
                return True
        resolution = entity_resolution.get("resolution")
        if isinstance(resolution, dict):
            for field_name in ("merged_entities", "aliases", "conflicts"):
                if _agent_profile_context_list_has_content(resolution.get(field_name)):
                    return True
    canon = value.get("canon")
    if isinstance(canon, dict):
        for field_name in ("entities", "relationships", "segment_summaries"):
            if _agent_profile_context_list_has_content(canon.get(field_name)):
                return True
    return False


def _agent_profile_context_list_has_content(value: Any) -> bool:
    return isinstance(value, list) and any(_agent_profile_context_item_has_content(item) for item in value)


def _agent_profile_context_item_has_content(value: Any) -> bool:
    if isinstance(value, dict):
        for key, child in value.items():
            if str(key) in AGENT_PROFILE_CONTEXT_SEMANTIC_KEYS and _agent_profile_context_scalar_has_content(child):
                return True
        return False
    return _agent_profile_context_scalar_has_content(value)


def _agent_profile_context_scalar_has_content(value: Any) -> bool:
    if isinstance(value, str):
        return bool(value.strip())
    if isinstance(value, list):
        return any(_agent_profile_context_scalar_has_content(item) for item in value)
    if isinstance(value, dict):
        return _agent_profile_context_item_has_content(value)
    return False


def _compact_sanitized_context_row(row: Any) -> dict[str, Any]:
    row_dict = _row_dict(row)
    sanitized = _project_agent_profile_context_item(row_dict)
    if not isinstance(sanitized, dict):
        return {}
    return {key: value for key, value in sanitized.items() if value is not None}


def _project_agent_profile_resolution_context(value: dict[str, Any]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key in ("snapshot_id", "model_id", "merged_entity_count", "alias_count", "conflict_count"):
        projected = _project_agent_profile_context_scalar(value.get(key))
        if projected is not None:
            result[key] = projected
    for field_name in ("merged_entities", "aliases", "conflicts"):
        projected_list = _project_agent_profile_context_list(value.get(field_name))
        if projected_list:
            result[field_name] = projected_list
    nested_resolution = value.get("resolution")
    if isinstance(nested_resolution, dict):
        projected_nested: dict[str, Any] = {}
        for field_name in ("merged_entities", "aliases", "conflicts"):
            projected_list = _project_agent_profile_context_list(nested_resolution.get(field_name))
            if projected_list:
                projected_nested[field_name] = projected_list
        if projected_nested:
            result["resolution"] = projected_nested
    return result


def _project_agent_profile_canon_context(value: dict[str, Any]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for field_name in ("entities", "relationships", "segment_summaries"):
        projected_list = _project_agent_profile_context_list(value.get(field_name))
        if projected_list:
            result[field_name] = projected_list
    return result


def _project_agent_profile_context_list(value: Any) -> list[Any]:
    if not isinstance(value, list):
        return []
    projected_items: list[Any] = []
    for item in value:
        if isinstance(item, dict):
            projected_item = _project_agent_profile_context_item(item)
            if projected_item:
                projected_items.append(projected_item)
        else:
            projected_scalar = _project_agent_profile_context_scalar(item)
            if projected_scalar is not None:
                projected_items.append(projected_scalar)
    return projected_items


def _project_agent_profile_context_item(value: dict[str, Any]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, child in value.items():
        normalized_key = str(key)
        if normalized_key not in AGENT_PROFILE_CONTEXT_ITEM_ALLOWED_KEYS:
            continue
        projected_child = _project_agent_profile_context_scalar(child)
        if projected_child is not None:
            result[normalized_key] = projected_child
    return result


def _project_agent_profile_context_scalar(value: Any) -> Any:
    if value is None:
        return None
    if isinstance(value, str):
        stripped = value.strip()
        return stripped or None
    if isinstance(value, bool):
        return value
    if isinstance(value, (int, float)):
        return value
    if isinstance(value, list):
        projected = [_project_agent_profile_context_scalar(item) for item in value]
        return [item for item in projected if item is not None]
    return None


def _row_dict(row: Any) -> dict[str, Any]:
    if isinstance(row, dict):
        return {str(key): value for key, value in row.items()}
    if hasattr(row, "keys"):
        return {str(key): row[key] for key in row.keys()}
    raise ValueError("database row must be mapping-like")


def _row_get(row: Any, key: str) -> Any:
    if isinstance(row, dict):
        return row.get(key)
    if hasattr(row, "keys"):
        return row[key] if key in row.keys() else None
    raise ValueError("database row must be mapping-like")


def _optional_row_text(row: Any, key: str) -> str | None:
    value = _row_get(row, key)
    if value is None:
        return None
    text = str(value).strip()
    return text or None


def _optional_row_int(row: Any, key: str) -> int | None:
    value = _row_get(row, key)
    if value is None:
        return None
    if isinstance(value, bool):
        raise ValueError(f"{key} must be an integer")
    if isinstance(value, int):
        return value
    if isinstance(value, str) and value.strip().isdigit():
        return int(value.strip())
    raise ValueError(f"{key} must be an integer")


def _jsonb_row_value(row: Any, key: str) -> Any:
    value = _row_get(row, key)
    if isinstance(value, str):
        return json.loads(value)
    return value


def _ontology_type_count(seed_ontology: dict[str, Any], field_name: str) -> int:
    value = seed_ontology.get(field_name)
    if not isinstance(value, list):
        raise LLMFacilityError("SCHEMA_VALIDATION_FAILED", f"{field_name} must be an array")
    for index, item in enumerate(value):
        if not isinstance(item, dict):
            raise LLMFacilityError("SCHEMA_VALIDATION_FAILED", f"{field_name}[{index}] must be an object")
    return len(value)


def _resolution_item_count(entity_resolution: dict[str, Any], field_name: str) -> int:
    value = entity_resolution.get(field_name)
    if not isinstance(value, list):
        raise LLMFacilityError("SCHEMA_VALIDATION_FAILED", f"{field_name} must be an array")
    for index, item in enumerate(value):
        if not isinstance(item, dict):
            raise LLMFacilityError("SCHEMA_VALIDATION_FAILED", f"{field_name}[{index}] must be an object")
    return len(value)


def _agent_profile_item_count(agent_profiles: dict[str, Any], field_name: str) -> int:
    value = agent_profiles.get(field_name)
    if not isinstance(value, list):
        raise LLMFacilityError("SCHEMA_VALIDATION_FAILED", f"{field_name} must be an array")
    for index, item in enumerate(value):
        if not isinstance(item, dict):
            raise LLMFacilityError("SCHEMA_VALIDATION_FAILED", f"{field_name}[{index}] must be an object")
    return len(value)


def _archive_runner_failed(code: str, message: str) -> dict[str, Any]:
    return {
        "status": "failed",
        "module_key": NARRATIVE_ARCHIVES_MODULE_KEY,
        "error": {"code": code, "message": message},
    }


def _validate_archive_candidate_resolution(resolution: Any) -> None:
    if getattr(resolution, "module_key", None) != NARRATIVE_ARCHIVES_MODULE_KEY:
        raise LLMFacilityError(
            "LLM_MODULE_UNBOUND",
            f"resolved module key does not match {NARRATIVE_ARCHIVES_MODULE_KEY}",
        )
    if not getattr(resolution, "supports_json", False):
        raise LLMFacilityError(
            "LLM_MODULE_CAPABILITY_MISSING",
            f"{NARRATIVE_ARCHIVES_MODULE_KEY} requires a JSON-capable model",
        )
    for field_name in ("channel_id", "model_id", "base_url", "credential_ref"):
        value = getattr(resolution, field_name, None)
        if not isinstance(value, str) or not value.strip():
            raise LLMFacilityError("LLM_PROVIDER_ERROR", f"resolved LLM module is missing {field_name}")


def _archive_candidate_messages(*, context: AgentContext) -> list[dict[str, str]]:
    return [
        {
            "role": "system",
            "content": (
                "You are the MiroFish narrative_archives module. Return one JSON object with an "
                "archive_entities array. Each archive entity must include title, summary, optional "
                "category, tags, payload, and optional memories. Each memory must include memory_type "
                "and summary, with optional private body_text and payload. Do not include prompt bodies, "
                "raw source material copies, API keys, credentials, or provider metadata in payload fields."
            ),
        },
        {
            "role": "user",
            "content": json.dumps(
                {
                    "tenant_id": context.tenant_id,
                    "project_id": context.project_id,
                    "run_id": context.run_id,
                    "module_key": NARRATIVE_ARCHIVES_MODULE_KEY,
                    "task": "Generate archive entity and archive memory candidates for explicit user review.",
                },
                ensure_ascii=False,
                separators=(",", ":"),
            ),
        },
    ]


def _archive_entity_candidates(response_json: dict[str, Any]) -> list[dict[str, Any]]:
    candidates = response_json.get("archive_entities")
    if candidates is None:
        candidates = response_json.get("archive_candidates")
    return _archive_entity_list(candidates)


def _archive_entity_list(value: Any) -> list[dict[str, Any]]:
    if not isinstance(value, list):
        raise LLMFacilityError("SCHEMA_VALIDATION_FAILED", "archive_entities must be an array")
    entities: list[dict[str, Any]] = []
    for index, item in enumerate(value):
        if not isinstance(item, dict):
            raise LLMFacilityError("SCHEMA_VALIDATION_FAILED", f"archive_entities[{index}] must be an object")
        payload_source: dict[str, Any] = {}
        raw_payload = item.get("payload")
        if raw_payload is not None:
            payload_source = _archive_payload(raw_payload)
        for key, child in item.items():
            if key not in {"title", "summary", "category", "tags", "payload", "memories"}:
                payload_source[key] = child
        entities.append(
            {
                "title": _archive_required_text(item.get("title"), f"archive_entities[{index}].title"),
                "summary": _archive_required_text(item.get("summary"), f"archive_entities[{index}].summary"),
                "category": _archive_optional_text(item.get("category")) or "archive",
                "tags": _archive_tags(item.get("tags")),
                "payload": _archive_payload(payload_source),
                "memories": _archive_memory_list(item.get("memories")),
            }
        )
    return entities


def _archive_memory_list(value: Any) -> list[dict[str, Any]]:
    if value is None:
        return []
    if not isinstance(value, list):
        raise LLMFacilityError("SCHEMA_VALIDATION_FAILED", "archive memory candidates must be an array")
    memories: list[dict[str, Any]] = []
    for index, item in enumerate(value):
        if not isinstance(item, dict):
            raise LLMFacilityError("SCHEMA_VALIDATION_FAILED", f"memories[{index}] must be an object")
        payload_source: dict[str, Any] = {}
        raw_payload = item.get("payload")
        if raw_payload is not None:
            payload_source = _archive_payload(raw_payload)
        for key, child in item.items():
            if key not in {"memory_type", "summary", "body_text", "payload"}:
                payload_source[key] = child
        body_text = _archive_optional_text(item.get("body_text"))
        memory: dict[str, Any] = {
            "memory_type": _archive_required_text(item.get("memory_type"), f"memories[{index}].memory_type"),
            "summary": _archive_required_text(item.get("summary"), f"memories[{index}].summary"),
            "payload": _archive_payload(payload_source),
        }
        if body_text is not None:
            memory["body_text"] = body_text
        memories.append(memory)
    return memories


def _archive_payload(value: Any) -> dict[str, Any]:
    if value is None:
        return {}
    sanitized = _sanitize_archive_value(value)
    if not isinstance(sanitized, dict):
        raise LLMFacilityError("SCHEMA_VALIDATION_FAILED", "archive candidate payload must be an object")
    return sanitized


def _sanitize_archive_value(value: Any) -> Any:
    if isinstance(value, dict):
        return {
            str(key): _sanitize_archive_value(child)
            for key, child in value.items()
            if str(key).lower() not in SENSITIVE_ARCHIVE_CANDIDATE_KEYS
        }
    if isinstance(value, list):
        return [_sanitize_archive_value(child) for child in value]
    return value


def _archive_tags(value: Any) -> list[str]:
    if value is None:
        return []
    if not isinstance(value, list):
        raise LLMFacilityError("SCHEMA_VALIDATION_FAILED", "archive candidate tags must be an array")
    tags: list[str] = []
    for tag in value:
        if isinstance(tag, str) and tag.strip() and tag.strip().lower() not in SENSITIVE_ARCHIVE_CANDIDATE_KEYS:
            tags.append(tag.strip())
    return tags


def _archive_required_text(value: Any, field_name: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise LLMFacilityError("SCHEMA_VALIDATION_FAILED", f"{field_name} is required")
    return value.strip()


def _archive_optional_text(value: Any) -> str | None:
    if value is None:
        return None
    if not isinstance(value, str) or not value.strip():
        raise LLMFacilityError("SCHEMA_VALIDATION_FAILED", "optional archive text must be a non-empty string")
    return value.strip()


def _archive_memory_candidate_count(archive_entities: list[dict[str, Any]]) -> int:
    return sum(len(entity.get("memories", [])) for entity in archive_entities)


def _archive_candidate_count(archive_entities: list[dict[str, Any]]) -> int:
    return len(archive_entities) + _archive_memory_candidate_count(archive_entities)


def _uuid_or_none(value: str | None) -> str | None:
    if not isinstance(value, str) or not value.strip():
        return None
    try:
        uuid.UUID(value.strip())
    except ValueError:
        return None
    return value.strip()


def _required_text_value(value: str, field_name: str) -> str:
    if not isinstance(value, str):
        raise ValueError(f"{field_name} must be a string")
    value = value.strip()
    if not value:
        raise ValueError(f"{field_name} is required")
    return value


def _error_result(
    *,
    base: dict[str, Any],
    code: str,
    message: str,
    extra: dict[str, Any] | None = None,
) -> dict[str, Any]:
    return {
        **base,
        **(extra or {}),
        "status": "failed",
        "error": {
            "code": code,
            "message": message,
        },
    }


def _public_seed_workflow_status_result(result: dict[str, Any]) -> dict[str, Any]:
    sanitized = _sanitize_workflow_event_payload(result)
    if not isinstance(sanitized, dict):
        return {}
    allowed: dict[str, Any] = {}
    for key in (
        "stage",
        "project_readiness_snapshot_id",
        "ready_asset_count",
        "ready_entity_count",
        "ready_relationship_count",
        "ready_world_rule_count",
    ):
        value = sanitized.get(key)
        if value is not None:
            allowed[key] = value
    return allowed


def _seed_workflow_status_message(
    status: str,
    result: dict[str, Any] | None,
    message: str | None,
) -> str:
    if status == "running":
        return "seed pipeline running"
    if status == "completed":
        if result is None:
            return "seed pipeline completed"
        return "seed pipeline completed"
    if message:
        return message
    return "seed pipeline failed"


def _workflow_status_updated_count(row: Any) -> int:
    if row is None:
        return 0
    value = row.get("workflow_updated") if isinstance(row, dict) else row[0]
    if isinstance(value, int):
        return value
    if isinstance(value, str) and value.strip().isdigit():
        return int(value.strip())
    return 0


def _mark_seed_workflow_failed(
    writer: WorkflowRunStatusWriter | None,
    *,
    context: AgentContext,
    code: str,
    message: str,
) -> bool:
    if writer is None:
        return False
    writer.mark_failed(context=context, code=code, message=message)
    return True


def _mark_seed_workflow_running(
    writer: WorkflowRunStatusWriter | None,
    *,
    context: AgentContext,
) -> bool:
    if writer is None:
        return False
    writer.mark_running(context=context)
    return True


def _seed_stage_progress(stage: str, *, terminal: bool = False) -> int:
    """Monotonic public progress for Overview while Seed activities advance."""
    order = {
        "parse_file": 12,
        "segment_text": 24,
        "sequential_reading": 42,
        "persist_runtime_facts": 52,
        "global_aggregation": 62,
        "story_ontology": 72,
        "entity_resolution": 80,
        "agent_profiles": 86,
        "archive_candidates": 92,
        "index_assets": 96,
        "finalize": 100,
    }
    if terminal or stage == "finalize":
        return 100
    return int(order.get(str(stage or "").strip(), 8))


def _bump_seed_stage_progress(
    *,
    context: AgentContext,
    stage: str,
    phase: str = "completed",
) -> None:
    """Best-effort progress write; never fails the Seed activity on status drift."""
    try:
        writer = _workflow_status_writer_from_env()
    except Exception:
        return
    if writer is None or not hasattr(writer, "mark_stage_progress"):
        return
    try:
        # Intermediate stage completions keep workflow status=running with rising progress.
        workflow_status = "running"
        message = f"seed stage {stage} {phase}"
        if phase == "pending":
            # Slightly below completed value so UI shows movement when stage starts.
            progress = max(5, _seed_stage_progress(stage) - 4)
            writer._update_status(  # noqa: SLF001 - internal status path used by worker only
                context=context,
                status=workflow_status,
                result=None,
                code=None,
                message=message,
                progress=progress,
            )
            return
        writer.mark_stage_progress(context=context, stage=stage, status=workflow_status, message=message)
    except Exception:
        return


def _bump_sequential_reading_batch_progress(
    *,
    context: AgentContext,
    payload: dict[str, Any],
) -> None:
    """Interpolate progress within sequential_reading (24→42) from batch counters."""
    try:
        writer = _workflow_status_writer_from_env()
    except Exception:
        return
    if writer is None or not hasattr(writer, "_update_status"):
        return
    try:
        completed = payload.get("completed_segments")
        total = payload.get("total_segments")
        if not isinstance(completed, int) or not isinstance(total, int) or total <= 0:
            return
        completed = max(0, min(completed, total))
        # sequential_reading pending ≈ 38, completed = 42; start from segment_text done (24).
        start = _seed_stage_progress("segment_text")  # 24
        end = _seed_stage_progress("sequential_reading")  # 42
        progress = start + int(round((end - start) * (completed / total)))
        progress = max(start, min(end - 1 if completed < total else end, progress))
        message = payload.get("message") if isinstance(payload.get("message"), str) else "sequential reading batch"
        writer._update_status(  # noqa: SLF001
            context=context,
            status="running",
            result=None,
            code=None,
            message=str(message)[:200],
            progress=progress,
        )
    except Exception:
        return


def _mark_seed_workflow_completed(
    writer: WorkflowRunStatusWriter | None,
    *,
    context: AgentContext,
    result: dict[str, Any],
) -> bool:
    if writer is None:
        return False
    writer.mark_completed(context=context, result=_public_seed_workflow_status_result(result))
    return True


def _mark_seed_segment_retries(
    writer: SeedSegmentRetryStatusWriter | None,
    *,
    context: AgentContext,
    segment_ids: list[str],
    retry_attempt_id: str | None = None,
    worker_attempt: int = 1,
    status: str,
    code: str | None = None,
    message: str | None = None,
) -> bool:
    if writer is None:
        return False
    writer.mark_seed_segment_retries(
        context=context,
        segment_ids=segment_ids,
        retry_attempt_id=retry_attempt_id,
        worker_attempt=worker_attempt,
        status=status,
        code=code,
        message=message,
    )
    return True


def _normalized_segment_retry_ids(value: Any) -> list[str]:
    if not isinstance(value, list):
        return []
    seen: set[str] = set()
    segment_ids: list[str] = []
    for item in value:
        if not isinstance(item, str):
            continue
        normalized = item.strip()
        if not normalized or normalized in seen:
            continue
        seen.add(normalized)
        segment_ids.append(normalized)
    return segment_ids


def _required_segment_retry_context(
    context: AgentContext,
    segment_ids: list[str],
) -> list[str]:
    if context.project_id is None:
        raise LLMFacilityError("VALIDATION_FAILED", "project_id is required for seed segment retry")
    normalized_segment_ids = _normalized_segment_retry_ids(segment_ids)
    if not normalized_segment_ids or len(normalized_segment_ids) != len(segment_ids):
        raise LLMFacilityError("VALIDATION_FAILED", "segment_ids are invalid")
    try:
        for segment_id in normalized_segment_ids:
            uuid.UUID(segment_id)
    except (ValueError, AttributeError) as exc:
        raise LLMFacilityError("VALIDATION_FAILED", "segment_ids are invalid") from exc
    return normalized_segment_ids


def _required_segment_retry_status(value: str) -> str:
    normalized = _required_text_value(value, "status")
    if normalized not in {"running", "completed", "failed", "cancelled"}:
        raise LLMFacilityError("VALIDATION_FAILED", "seed segment retry status is invalid")
    return normalized


def _required_segment_retry_attempt_id(value: str | None) -> str:
    if not isinstance(value, str):
        raise LLMFacilityError("VALIDATION_FAILED", "retry_attempt_id is invalid")
    try:
        normalized = _required_text_value(value, "retry_attempt_id")
        uuid.UUID(normalized)
    except (ValueError, AttributeError) as exc:
        raise LLMFacilityError("VALIDATION_FAILED", "retry_attempt_id is invalid") from exc
    return normalized


def _required_segment_retry_worker_attempt(value: int) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value < 1:
        raise LLMFacilityError("VALIDATION_FAILED", "seed segment retry worker attempt is invalid")
    return value


def _segment_retry_worker_attempt() -> int:
    try:
        attempt = activity.info().attempt
    except Exception:
        return 1
    return attempt if isinstance(attempt, int) and not isinstance(attempt, bool) and attempt > 0 else 1


def _segment_retry_status_error(
    status: str,
    code: str | None,
    message: str | None,
) -> tuple[str | None, str | None]:
    _ = message
    if status not in {"failed", "cancelled"}:
        return None, None
    allowed_codes = {
        "LLM_MODULE_UNBOUND",
        "LLM_CREDENTIAL_KEY_UNCONFIGURED",
        "LLM_CREDENTIAL_KEY_INVALID",
        "LLM_CREDENTIAL_UNAVAILABLE",
        "LLM_CREDENTIAL_DECRYPT_FAILED",
        "LLM_CONCURRENCY_LIMITED",
        "OBJECT_STORAGE_BACKEND_MISCONFIGURED",
        "LLM_PROVIDER_ERROR",
        "SCHEMA_VALIDATION_FAILED",
        "READING_NOTES_WRITE_FAILED",
        "READING_NOTES_WRITER_UNCONFIGURED",
        "LLM_READER_UNCONFIGURED",
        "SEED_SEGMENT_RETRY_REQUEST_NOT_FOUND",
        "SEED_SEGMENT_RETRY_STORE_UNCONFIGURED",
        "SEED_SEGMENT_RETRY_CLAIM_FAILED",
        "SEED_SEGMENT_RETRY_CANON_OWNERSHIP_CONFLICT",
        "SEED_SEGMENT_RETRY_STATUS_WRITE_FAILED",
        "SEED_SEGMENT_RETRY_COMPLETION_WRITE_FAILED",
        "SEED_SEGMENT_RETRY_PROJECTION_WRITE_FAILED",
        "WORKFLOW_EVENT_WRITE_FAILED",
    }
    normalized_code = code.strip() if isinstance(code, str) else ""
    if normalized_code not in allowed_codes:
        normalized_code = "SEED_SEGMENT_RETRY_FAILED"
    return normalized_code, _public_segment_retry_error_message(normalized_code)


def _segment_retry_reference_from_row(row: Any) -> dict[str, Any]:
    return {
        key: value
        for key in ("segment_id", "segment_order", "chapter_guess", "title_guess", "object_key")
        if (value := _row_get(row, key)) is not None
    }


def _validate_segment_retry_claims(
    *,
    segment_refs: list[dict[str, Any]],
    segment_ids: list[str],
) -> None:
    requested_ids = set(segment_ids)
    claimed_ids: list[str] = []
    for segment_ref in segment_refs:
        segment_id = segment_ref.get("segment_id")
        object_key = segment_ref.get("object_key")
        if not isinstance(segment_id, str) or not segment_id.strip():
            raise ValueError("claimed segment_id is required")
        if not isinstance(object_key, str) or not object_key.strip():
            raise ValueError("claimed segment object_key is required")
        claimed_ids.append(segment_id.strip())
    if len(claimed_ids) != len(set(claimed_ids)):
        raise LookupError("duplicate claimed segment retry rows")
    if set(claimed_ids) != requested_ids:
        raise LookupError("claimed segment retry rows do not match requested segments")


def _public_segment_retry_error_message(code: str) -> str:
    if code == "LLM_MODULE_UNBOUND":
        return "LLM module is not bound"
    if code == "SCHEMA_VALIDATION_FAILED":
        return "segment retry output schema validation failed"
    if code == "READING_NOTES_WRITE_FAILED":
        return "reading notes write failed"
    if code == "READING_NOTES_WRITER_UNCONFIGURED":
        return "reading notes writer is unconfigured"
    if code == "LLM_READER_UNCONFIGURED":
        return "LLM reader is unconfigured"
    if code == "SEED_SEGMENT_RETRY_REQUEST_NOT_FOUND":
        return "seed segment retry request not found"
    if code == "SEED_SEGMENT_RETRY_STORE_UNCONFIGURED":
        return "seed segment retry store is not configured"
    if code == "SEED_SEGMENT_RETRY_CLAIM_FAILED":
        return "seed segment retry claim failed"
    if code == "SEED_SEGMENT_RETRY_CANON_OWNERSHIP_CONFLICT":
        return "seed segment retry canon ownership conflict"
    if code == "SEED_SEGMENT_RETRY_STATUS_WRITE_FAILED":
        return "seed segment retry status write failed"
    if code == "SEED_SEGMENT_RETRY_COMPLETION_WRITE_FAILED":
        return "seed segment retry completion write failed"
    if code == "SEED_SEGMENT_RETRY_PROJECTION_WRITE_FAILED":
        return "seed segment retry projection write failed"
    if code == "SEED_SEGMENT_RETRY_FAILED":
        return "seed segment retry failed"
    return _public_llm_error_message(code)


def _segment_retry_failed_result(
    *,
    context: AgentContext,
    requested_count: int,
    segment_count: int | None,
    code: str,
    message: str,
    retry_store: SeedSegmentRetryStore | None,
    segment_ids: list[str],
    workflow_event_writer: WorkflowEventWriter | None,
    retry_attempt_id: str | None = None,
    worker_attempt: int = 1,
) -> dict[str, Any]:
    public_code, public_message = _segment_retry_status_error("failed", code, message)
    if public_code is None or public_message is None:
        public_code = "SEED_SEGMENT_RETRY_FAILED"
        public_message = _public_segment_retry_error_message(public_code)
    atomic_failure_writer = getattr(retry_store, "fail_seed_segment_retries", None)
    if retry_attempt_id is not None and callable(atomic_failure_writer):
        try:
            atomic_failure_writer(
                context=context,
                segment_ids=segment_ids,
                retry_attempt_id=retry_attempt_id,
                worker_attempt=worker_attempt,
                requested_count=requested_count,
                segment_count=segment_count,
                code=public_code,
                message=public_message,
            )
        except Exception:
            return {
                "stage": "segment_retry",
                "status": "failed",
                "requested_count": requested_count,
                **({"segment_count": segment_count} if segment_count is not None else {}),
                "error": {
                    "code": "SEED_SEGMENT_RETRY_COMPLETION_WRITE_FAILED",
                    "message": "seed segment retry completion write failed",
                },
                "retry_status_persisted": False,
                "stage_event_persisted": False,
            }
        return {
            "stage": "segment_retry",
            "status": "failed",
            "requested_count": requested_count,
            **({"segment_count": segment_count} if segment_count is not None else {}),
            "error": {"code": public_code, "message": public_message},
            "retry_status_persisted": True,
            "stage_event_persisted": True,
        }
    try:
        retry_status_persisted = _mark_seed_segment_retries(
            retry_store,
            context=context,
            segment_ids=segment_ids,
            retry_attempt_id=retry_attempt_id,
            worker_attempt=worker_attempt,
            status="failed",
            code=public_code,
            message=public_message,
        )
    except Exception:
        return {
            "stage": "segment_retry",
            "status": "failed",
            "requested_count": requested_count,
            **({"segment_count": segment_count} if segment_count is not None else {}),
            "error": {
                "code": "SEED_SEGMENT_RETRY_STATUS_WRITE_FAILED",
                "message": "seed segment retry status write failed",
            },
            "retry_status_persisted": False,
        }
    try:
        stage_event_persisted = _record_failed_segment_retry_event(
            context=context,
            requested_count=requested_count,
            segment_count=segment_count,
            error_code=public_code,
            error_message=public_message,
            workflow_event_writer=workflow_event_writer,
        )
    except Exception:
        return {
            "stage": "segment_retry",
            "status": "failed",
            "requested_count": requested_count,
            **({"segment_count": segment_count} if segment_count is not None else {}),
            "error": {
                "code": "WORKFLOW_EVENT_WRITE_FAILED",
                "message": "workflow event write failed",
            },
            "retry_status_persisted": retry_status_persisted,
        }
    return {
        "stage": "segment_retry",
        "status": "failed",
        "requested_count": requested_count,
        **({"segment_count": segment_count} if segment_count is not None else {}),
        "error": {
            "code": public_code,
            "message": public_message,
        },
        "retry_status_persisted": retry_status_persisted,
        "stage_event_persisted": stage_event_persisted,
    }


def _required_artifact_type(value: str) -> str:
    normalized_value = _required_text_value(value, "artifact_type")
    allowed_types = {"extracted_text", "normalized_text", "segment_text"}
    if normalized_value not in allowed_types:
        raise ValueError("artifact_type must be extracted_text, normalized_text, or segment_text")
    return normalized_value


def _required_source_parse_status(value: str) -> str:
    normalized_value = _required_text_value(value, "parse_status")
    if normalized_value not in {"parsed", "failed"}:
        raise ValueError("parse_status must be parsed or failed")
    return normalized_value


def _required_note_segment_id(note: dict[str, Any]) -> str:
    value = note.get("segment_id")
    if not isinstance(value, str) or not value.strip():
        raise ValueError("segment_id is required for reading segment notes")
    return value.strip()


def _note_payload_json(note: dict[str, Any]) -> str:
    payload = note.get("payload_jsonb", {})
    if not isinstance(payload, dict):
        raise ValueError("payload_jsonb must be an object")
    return _json_object(payload)


def _workflow_event_writer_from_env() -> WorkflowEventWriter | None:
    database_url = os.environ.get("DATABASE_URL", "").strip()
    if not database_url:
        return None
    return PostgresWorkflowEventWriter.from_database_url(database_url)


def _resolved_workflow_event_writer(
    workflow_event_writer: WorkflowEventWriter | None,
) -> WorkflowEventWriter | None:
    if workflow_event_writer is not None:
        return workflow_event_writer
    return _workflow_event_writer_from_env()


def _workflow_event_writer_resolution_failed_result(
    *,
    base: dict[str, Any],
    stage: str,
    source_file_id: str | None = None,
    module_key: str | None = None,
) -> dict[str, Any]:
    extra: dict[str, Any] = {"stage": stage}
    if source_file_id is not None:
        extra["source_file_id"] = source_file_id
    if module_key is not None:
        extra["module_key"] = module_key
    return _error_result(
        base=base,
        code="WORKFLOW_EVENT_WRITE_FAILED",
        message="workflow event write failed",
        extra=extra,
    )


def _object_store_from_env() -> ObjectStore | None:
    endpoint = os.environ.get("MIROFISH_OBJECT_STORAGE_ENDPOINT", "").strip()
    bucket = os.environ.get("MIROFISH_OBJECT_STORAGE_BUCKET", "").strip()
    access_key = os.environ.get("MIROFISH_OBJECT_STORAGE_ACCESS_KEY", "").strip()
    secret_key = os.environ.get("MIROFISH_OBJECT_STORAGE_SECRET_KEY", "").strip()
    if not any((endpoint, bucket, access_key, secret_key)):
        return None
    return S3CompatibleObjectStore(
        endpoint=endpoint,
        bucket=bucket,
        access_key=access_key,
        secret_key=secret_key,
        use_ssl=_parse_bool(os.environ.get("MIROFISH_OBJECT_STORAGE_USE_SSL", "")),
        region=os.environ.get("MIROFISH_OBJECT_STORAGE_REGION", "us-east-1"),
    )


def _text_artifact_writer_from_env() -> TextArtifactWriter | None:
    database_url = os.environ.get("DATABASE_URL", "").strip()
    if not database_url:
        return None
    return PostgresTextArtifactWriter.from_database_url(database_url)


def _source_file_status_writer_from_env() -> SourceFileStatusWriter | None:
    database_url = os.environ.get("DATABASE_URL", "").strip()
    if not database_url:
        return None
    return PostgresSourceFileStatusWriter.from_database_url(database_url)


def _workflow_status_writer_from_env() -> WorkflowRunStatusWriter | None:
    database_url = os.environ.get("DATABASE_URL", "").strip()
    if not database_url:
        return None
    return PostgresSeedWorkflowRunStatusWriter.from_database_url(database_url)


def _seed_segment_retry_store_from_env() -> SeedSegmentRetryStore | None:
    database_url = os.environ.get("DATABASE_URL", "").strip()
    if not database_url:
        return None
    from mirofish_agents.temporal.seed_retry_projection import (
        PostgresSeedSegmentRetryProjectionStore,
    )

    return PostgresSeedSegmentRetryProjectionStore.from_database_url(database_url)


def _text_segment_writer_from_env() -> TextSegmentWriter | None:
    database_url = os.environ.get("DATABASE_URL", "").strip()
    if not database_url:
        return None
    return PostgresTextSegmentWriter.from_database_url(database_url)


def _reading_notes_writer_from_env() -> ReadingNotesWriter | None:
    database_url = os.environ.get("DATABASE_URL", "").strip()
    if not database_url:
        return None
    return PostgresReadingNotesWriter.from_database_url(database_url)


def _runtime_facts_writer_from_env() -> RuntimeFactsWriter | None:
    database_url = os.environ.get("DATABASE_URL", "").strip()
    if not database_url:
        return None
    return PostgresRuntimeFactsWriter.from_database_url(database_url)


def _seed_analysis_writer_from_env() -> SeedAnalysisWriter | None:
    database_url = os.environ.get("DATABASE_URL", "").strip()
    if not database_url:
        return None
    return PostgresSeedAnalysisWriter.from_database_url(database_url)


def _global_aggregator_from_env(
    *,
    http_request: Callable[[Request], bytes] | None = None,
    connect: Callable[[], Any] | None = None,
) -> GlobalAggregationRunner | None:
    database_url = os.environ.get("DATABASE_URL", "").strip()
    if not database_url and connect is None:
        return None

    from mirofish_agents.seed.global_aggregator import (
        LLMFacilityGlobalAggregator,
        PostgresSeedAggregateSource,
    )
    from mirofish_agents.seed.sequential_reader import (
        AesGcmCredentialDecryptor,
        PostgresCredentialProvider,
        PostgresModuleBindingResolver,
    )

    key_material = os.environ.get("LLM_CREDENTIAL_ENCRYPTION_KEY", "").strip()
    decryptor = AesGcmCredentialDecryptor(key_material=key_material) if key_material else None
    if connect is not None:
        binding_resolver = PostgresModuleBindingResolver(connect=connect)
        credential_provider = PostgresCredentialProvider(connect=connect, decryptor=decryptor)
        aggregate_source = PostgresSeedAggregateSource(connect=connect)
    else:
        binding_resolver = PostgresModuleBindingResolver.from_database_url(database_url)
        credential_provider = PostgresCredentialProvider.from_database_url(
            database_url=database_url,
            key_material=key_material or None,
        )
        aggregate_source = PostgresSeedAggregateSource.from_database_url(database_url)
    return LLMFacilityGlobalAggregator(
        binding_resolver=binding_resolver,
        credential_provider=credential_provider,
        chat_client=_seed_chat_client(
            database_url=database_url,
            connect=connect,
            http_request=http_request,
        ),
        aggregate_source=aggregate_source,
    )


def _ontology_runner_from_env(
    *,
    http_request: Callable[[Request], bytes] | None = None,
    connect: Callable[[], Any] | None = None,
) -> OntologyRunner | None:
    database_url = os.environ.get("DATABASE_URL", "").strip()
    if not database_url and connect is None:
        return None
    from mirofish_agents.seed.sequential_reader import (
        AesGcmCredentialDecryptor,
        PostgresCredentialProvider,
        PostgresModuleBindingResolver,
    )

    key_material = os.environ.get("LLM_CREDENTIAL_ENCRYPTION_KEY", "").strip()
    decryptor = AesGcmCredentialDecryptor(key_material=key_material) if key_material else None
    if connect is not None:
        binding_resolver = PostgresModuleBindingResolver(connect=connect)
        credential_provider = PostgresCredentialProvider(connect=connect, decryptor=decryptor)
        ontology_snapshot_writer = PostgresOntologySnapshotWriter(connect=connect)
    else:
        binding_resolver = PostgresModuleBindingResolver.from_database_url(database_url)
        credential_provider = PostgresCredentialProvider.from_database_url(
            database_url=database_url,
            key_material=key_material or None,
        )
        ontology_snapshot_writer = PostgresOntologySnapshotWriter.from_database_url(database_url)
    return LLMFacilityOntologyRunner(
        binding_resolver=binding_resolver,
        credential_provider=credential_provider,
        chat_client=_seed_chat_client(
            database_url=database_url,
            connect=connect,
            http_request=http_request,
        ),
        ontology_snapshot_writer=ontology_snapshot_writer,
    )


def _entity_resolution_runner_from_env(
    *,
    http_request: Callable[[Request], bytes] | None = None,
    connect: Callable[[], Any] | None = None,
) -> EntityResolutionRunner | None:
    database_url = os.environ.get("DATABASE_URL", "").strip()
    if not database_url and connect is None:
        return None
    from mirofish_agents.seed.sequential_reader import (
        AesGcmCredentialDecryptor,
        PostgresCredentialProvider,
        PostgresModuleBindingResolver,
    )

    key_material = os.environ.get("LLM_CREDENTIAL_ENCRYPTION_KEY", "").strip()
    decryptor = AesGcmCredentialDecryptor(key_material=key_material) if key_material else None
    if connect is not None:
        binding_resolver = PostgresModuleBindingResolver(connect=connect)
        credential_provider = PostgresCredentialProvider(connect=connect, decryptor=decryptor)
        entity_resolution_snapshot_writer = PostgresEntityResolutionSnapshotWriter(connect=connect)
    else:
        binding_resolver = PostgresModuleBindingResolver.from_database_url(database_url)
        credential_provider = PostgresCredentialProvider.from_database_url(
            database_url=database_url,
            key_material=key_material or None,
        )
        entity_resolution_snapshot_writer = PostgresEntityResolutionSnapshotWriter.from_database_url(database_url)
    return LLMFacilityEntityResolutionRunner(
        binding_resolver=binding_resolver,
        credential_provider=credential_provider,
        chat_client=_seed_chat_client(
            database_url=database_url,
            connect=connect,
            http_request=http_request,
        ),
        entity_resolution_snapshot_writer=entity_resolution_snapshot_writer,
    )


def _agent_profile_runner_from_env(
    *,
    http_request: Callable[[Request], bytes] | None = None,
    connect: Callable[[], Any] | None = None,
) -> AgentProfileRunner | None:
    database_url = os.environ.get("DATABASE_URL", "").strip()
    if not database_url and connect is None:
        return None
    from mirofish_agents.seed.sequential_reader import (
        AesGcmCredentialDecryptor,
        PostgresCredentialProvider,
        PostgresModuleBindingResolver,
    )

    key_material = os.environ.get("LLM_CREDENTIAL_ENCRYPTION_KEY", "").strip()
    decryptor = AesGcmCredentialDecryptor(key_material=key_material) if key_material else None
    if connect is not None:
        binding_resolver = PostgresModuleBindingResolver(connect=connect)
        credential_provider = PostgresCredentialProvider(connect=connect, decryptor=decryptor)
        agent_profile_snapshot_writer = PostgresAgentProfileSnapshotWriter(connect=connect)
        agent_profile_context_loader = PostgresAgentProfileContextLoader(connect=connect)
    else:
        binding_resolver = PostgresModuleBindingResolver.from_database_url(database_url)
        credential_provider = PostgresCredentialProvider.from_database_url(
            database_url=database_url,
            key_material=key_material or None,
        )
        agent_profile_snapshot_writer = PostgresAgentProfileSnapshotWriter.from_database_url(database_url)
        agent_profile_context_loader = PostgresAgentProfileContextLoader.from_database_url(database_url)
    return LLMFacilityAgentProfileRunner(
        binding_resolver=binding_resolver,
        credential_provider=credential_provider,
        chat_client=_seed_chat_client(
            database_url=database_url,
            connect=connect,
            http_request=http_request,
        ),
        agent_profile_snapshot_writer=agent_profile_snapshot_writer,
        agent_profile_context_loader=agent_profile_context_loader,
    )


def _archive_candidate_runner_from_env() -> ArchiveCandidateRunner | None:
    database_url = os.environ.get("DATABASE_URL", "").strip()
    if not database_url:
        return None
    from mirofish_agents.seed.sequential_reader import (
        PostgresCredentialProvider,
        PostgresModuleBindingResolver,
    )

    return LLMFacilityArchiveCandidateRunner(
        binding_resolver=PostgresModuleBindingResolver.from_database_url(database_url),
        credential_provider=PostgresCredentialProvider.from_database_url(
            database_url=database_url,
            key_material=os.environ.get("LLM_CREDENTIAL_ENCRYPTION_KEY"),
        ),
        chat_client=_seed_chat_client(database_url=database_url),
        archive_candidate_writer=PostgresArchiveCandidateWriter.from_database_url(database_url),
    )


def _asset_indexer_from_env() -> AssetIndexer | None:
    database_url = os.environ.get("DATABASE_URL", "").strip()
    if database_url:
        return PostgresSeedAssetIndexer.from_database_url(database_url)
    return None


def _project_readiness_updater_from_env() -> ProjectReadinessUpdater | None:
    database_url = os.environ.get("DATABASE_URL", "").strip()
    if database_url:
        return PostgresProjectReadinessUpdater.from_database_url(database_url)
    return None


def _sequential_reader_from_env(
    *,
    segment_text_store: ObjectStore | None = None,
    http_request: Callable[[Request], bytes] | None = None,
    connect: Callable[[], Any] | None = None,
) -> SequentialReadingReader | None:
    database_url = os.environ.get("DATABASE_URL", "").strip()
    if not database_url and connect is None:
        return None
    try:
        text_store = segment_text_store if segment_text_store is not None else _object_store_from_env()
    except Exception:
        raise LLMFacilityError(
            "OBJECT_STORAGE_BACKEND_MISCONFIGURED",
            "object storage backend is misconfigured",
        )
    if text_store is None:
        return None

    from mirofish_agents.seed.sequential_reader import (
        AesGcmCredentialDecryptor,
        LLMFacilitySequentialReader,
        PostgresCredentialProvider,
        PostgresModuleBindingResolver,
    )

    key_material = os.environ.get("LLM_CREDENTIAL_ENCRYPTION_KEY", "").strip()
    decryptor = AesGcmCredentialDecryptor(key_material=key_material) if key_material else None
    if connect is not None:
        binding_resolver = PostgresModuleBindingResolver(connect=connect)
        credential_provider = PostgresCredentialProvider(connect=connect, decryptor=decryptor)
    else:
        binding_resolver = PostgresModuleBindingResolver.from_database_url(database_url)
        credential_provider = PostgresCredentialProvider.from_database_url(
            database_url=database_url,
            key_material=key_material or None,
        )
    return LLMFacilitySequentialReader(
        binding_resolver=binding_resolver,
        credential_provider=credential_provider,
        chat_client=_seed_chat_client(
            database_url=database_url,
            connect=connect,
            http_request=http_request,
        ),
        segment_text_store=text_store,
    )


def _seed_chat_client(
    *,
    database_url: str,
    connect: Callable[[], Any] | None = None,
    http_request: Callable[[Request], bytes] | None = None,
) -> Any:
    from mirofish_agents.seed.sequential_reader import OpenAICompatibleJSONClient

    # Explicit connections are test seams whose scripted cursors predate quota tables.
    if connect is not None:
        return OpenAICompatibleJSONClient(http_request=http_request)
    from mirofish_agents.llm_quota import PostgresQuotaStore, ProviderQuotaGate, QuotaAwareJSONChatClient
    from mirofish_agents.seed.quota_chat_client import SeedQuotaAwareJSONChatClient

    return SeedQuotaAwareJSONChatClient(
        quota_gate=ProviderQuotaGate(PostgresQuotaStore.from_database_url(database_url)),
        provider_client=QuotaAwareJSONChatClient(http_request=http_request),
    )


def _parse_bool(value: str) -> bool:
    return value.strip().lower() in {"1", "true", "yes"}


def _aws_v4_signing_key(secret_key: str, date_stamp: str, region: str) -> bytes:
    date_key = hmac.new(("AWS4" + secret_key).encode("utf-8"), date_stamp.encode("utf-8"), hashlib.sha256).digest()
    region_key = hmac.new(date_key, region.encode("utf-8"), hashlib.sha256).digest()
    service_key = hmac.new(region_key, b"s3", hashlib.sha256).digest()
    return hmac.new(service_key, b"aws4_request", hashlib.sha256).digest()


def _urlopen_bytes(request: Request) -> bytes:
    with urlopen(request, timeout=30) as response:
        return response.read()


def _record_pending_stage_event(
    *,
    context: AgentContext,
    upload_id: str,
    workflow_event_writer: WorkflowEventWriter | None,
) -> bool:
    if workflow_event_writer is None:
        return False
    workflow_event_writer.record_workflow_event(
        context=context,
        event_type="seed.stage.pending",
        payload={
            "stage": "parse_file",
            "status": "pending",
            "activity": "seed_pipeline_activity",
            "upload_id": upload_id,
        },
    )
    return True


def _record_failed_segment_retry_event(
    *,
    context: AgentContext,
    requested_count: int,
    segment_count: int | None = None,
    error_code: str,
    error_message: str,
    workflow_event_writer: WorkflowEventWriter | None,
) -> bool:
    if workflow_event_writer is None:
        return False
    payload: dict[str, object] = {
        "stage": "segment_retry",
        "status": "failed",
        "requested_count": requested_count,
        "error_code": error_code,
        "error_message": error_message,
    }
    if segment_count is not None:
        payload["segment_count"] = segment_count
    workflow_event_writer.record_workflow_event(
        context=context,
        event_type="seed.segments.retry_failed",
        payload=payload,
    )
    return True


def _record_completed_segment_retry_event(
    *,
    context: AgentContext,
    requested_count: int,
    segment_count: int,
    note_count: int,
    model_id: str | None,
    workflow_event_writer: WorkflowEventWriter | None,
) -> bool:
    if workflow_event_writer is None:
        return False
    payload: dict[str, object] = {
        "stage": "segment_retry",
        "status": "completed",
        "requested_count": requested_count,
        "segment_count": segment_count,
        "note_count": note_count,
    }
    if model_id is not None:
        payload["model_id"] = model_id
    workflow_event_writer.record_workflow_event(
        context=context,
        event_type="seed.segments.retry_completed",
        payload=payload,
    )
    return True


def _is_supported_plain_text_mime(mime_type: str) -> bool:
    normalized_mime = mime_type.lower().split(";")[0].strip()
    return normalized_mime in {
        "text/plain",
        "text/markdown",
        "text/x-markdown",
        "application/x-markdown",
    }


def _is_supported_source_mime(mime_type: str) -> bool:
    normalized_mime = mime_type.lower().split(";")[0].strip()
    return _is_supported_plain_text_mime(normalized_mime) or normalized_mime == "application/pdf"


def _extract_source_text(source_bytes: bytes, mime_type: str) -> str:
    normalized_mime = mime_type.lower().split(";")[0].strip()
    if normalized_mime == "application/pdf":
        return _extract_pdf_text(source_bytes)
    return source_bytes.decode("utf-8")


def _source_object_integrity_matches(payload: dict[str, Any], source_bytes: bytes) -> bool:
    expected_size_bytes = payload.get("source_size_bytes")
    if expected_size_bytes is not None:
        if not isinstance(expected_size_bytes, int) or expected_size_bytes < 0:
            return False
        if len(source_bytes) != expected_size_bytes:
            return False
    expected_sha256 = payload.get("source_sha256")
    if expected_sha256 is not None:
        if not isinstance(expected_sha256, str):
            return False
        normalized_sha256 = expected_sha256.strip().lower()
        if re.fullmatch(r"[0-9a-f]{64}", normalized_sha256) is None:
            return False
        if hashlib.sha256(source_bytes).hexdigest() != normalized_sha256:
            return False
    return True


def _extract_pdf_text(source_bytes: bytes) -> str:
    if not source_bytes.startswith(b"%PDF-"):
        raise ValueError("PDF header is invalid")
    reader = PdfReader(BytesIO(source_bytes), strict=False)
    page_texts = [(page.extract_text() or "").strip() for page in reader.pages]
    extracted_text = "\n\n".join(text for text in page_texts if text)
    if not extracted_text.strip():
        raise PdfOcrBackendUnconfiguredError()
    return extracted_text


def _extract_pdf_ocr_text(
    source_bytes: bytes,
    pdf_ocr_backend: PdfOcrBackend | None,
) -> str:
    backend = pdf_ocr_backend if pdf_ocr_backend is not None else configured_pdf_ocr_backend()
    if backend is None:
        raise PdfOcrBackendUnconfiguredError()
    try:
        extracted_text = backend.extract_text(source_bytes).strip()
    except PdfOcrError:
        raise
    except Exception as exc:
        raise PdfOcrProviderError() from exc
    if not extracted_text:
        raise PdfOcrProviderError()
    return extracted_text


def _extracted_text_object_key(context: AgentContext, source_file_id: str) -> str:
    if context.project_id is None:
        raise ValueError("project_id is required to build extracted text object key")
    return f"projects/{context.project_id}/seed-runs/{context.run_id}/extracted/{source_file_id}.txt"


def _record_completed_parse_event(
    *,
    context: AgentContext,
    source_file_id: str,
    char_count: int,
    line_count: int,
    sha256: str,
    workflow_event_writer: WorkflowEventWriter | None,
) -> bool:
    if workflow_event_writer is None:
        return False
    workflow_event_writer.record_workflow_event(
        context=context,
        event_type="seed.stage.completed",
        payload={
            "stage": "parse_file",
            "status": "completed",
            "activity": "parse_file_activity",
            "source_file_id": source_file_id,
            "artifact_type": "extracted_text",
            "char_count": char_count,
            "line_count": line_count,
        },
    )
    return True


def _mark_source_file_parse_status(
    *,
    context: AgentContext,
    source_file_id: str,
    parse_status: str,
    source_status_writer: SourceFileStatusWriter | None,
) -> bool:
    if source_status_writer is None:
        return False
    source_status_writer.mark_source_file_status(
        context=context,
        source_file_id=source_file_id,
        parse_status=parse_status,
    )
    return True


def _record_failed_parse_event(
    *,
    context: AgentContext,
    source_file_id: str,
    error_code: str,
    error_message: str,
    workflow_event_writer: WorkflowEventWriter | None,
) -> bool:
    if workflow_event_writer is None:
        return False
    workflow_event_writer.record_workflow_event(
        context=context,
        event_type="seed.stage.failed",
        payload={
            "stage": "parse_file",
            "status": "failed",
            "activity": "parse_file_activity",
            "source_file_id": source_file_id,
            "error_code": error_code,
            "error_message": error_message,
        },
    )
    return True


def _record_pending_segment_event(
    *,
    context: AgentContext,
    source_file_id: str,
    artifact_type: str,
    workflow_event_writer: WorkflowEventWriter | None,
) -> bool:
    if workflow_event_writer is None:
        return False
    workflow_event_writer.record_workflow_event(
        context=context,
        event_type="seed.stage.pending",
        payload={
            "stage": "segment_text",
            "status": "pending",
            "activity": "segment_text_activity",
            "source_file_id": source_file_id,
            "artifact_type": artifact_type,
        },
    )
    return True


def _record_completed_segment_event(
    *,
    context: AgentContext,
    source_file_id: str,
    segment_count: int,
    workflow_event_writer: WorkflowEventWriter | None,
) -> bool:
    if workflow_event_writer is None:
        return False
    workflow_event_writer.record_workflow_event(
        context=context,
        event_type="seed.stage.completed",
        payload={
            "stage": "segment_text",
            "status": "completed",
            "activity": "segment_text_activity",
            "source_file_id": source_file_id,
            "segment_count": segment_count,
        },
    )
    return True


def _record_failed_segment_event(
    *,
    context: AgentContext,
    source_file_id: str,
    error_code: str,
    error_message: str,
    workflow_event_writer: WorkflowEventWriter | None,
) -> bool:
    if workflow_event_writer is None:
        return False
    workflow_event_writer.record_workflow_event(
        context=context,
        event_type="seed.stage.failed",
        payload={
            "stage": "segment_text",
            "status": "failed",
            "activity": "segment_text_activity",
            "source_file_id": source_file_id,
            "error_code": error_code,
            "error_message": error_message,
        },
    )
    return True


def _record_pending_sequential_reading_event(
    *,
    context: AgentContext,
    segment_count: int,
    workflow_event_writer: WorkflowEventWriter | None,
) -> bool:
    if workflow_event_writer is None:
        return False
    workflow_event_writer.record_workflow_event(
        context=context,
        event_type="seed.stage.pending",
        payload={
            "stage": "sequential_reading",
            "status": "pending",
            "activity": "sequential_reading_activity",
            "module_key": "sequential_reading",
            "segment_count": segment_count,
            "message": f"开始顺序精读（共 {segment_count} 段）",
        },
    )
    return True


def _record_sequential_reading_batch_progress(
    *,
    context: AgentContext,
    payload: dict[str, object],
    workflow_event_writer: WorkflowEventWriter | None,
) -> bool:
    if workflow_event_writer is None:
        return False
    event_payload: dict[str, object] = {
        "stage": "sequential_reading",
        "activity": "sequential_reading_activity",
        "module_key": "sequential_reading",
        **payload,
    }
    workflow_event_writer.record_workflow_event(
        context=context,
        event_type="seed.sequential_reading.progress",
        payload=event_payload,
    )
    return True


def _record_failed_sequential_reading_event(
    *,
    context: AgentContext,
    segment_count: int,
    error_code: str,
    error_message: str,
    workflow_event_writer: WorkflowEventWriter | None,
) -> bool:
    if workflow_event_writer is None:
        return False
    workflow_event_writer.record_workflow_event(
        context=context,
        event_type="seed.stage.failed",
        payload={
            "stage": "sequential_reading",
            "status": "failed",
            "activity": "sequential_reading_activity",
            "module_key": "sequential_reading",
            "segment_count": segment_count,
            "error_code": error_code,
            "error_message": error_message,
        },
    )
    return True


def _record_completed_sequential_reading_event(
    *,
    context: AgentContext,
    segment_count: int,
    note_count: int,
    model_id: str | None,
    workflow_event_writer: WorkflowEventWriter | None,
) -> bool:
    if workflow_event_writer is None:
        return False
    payload: dict[str, object] = {
        "stage": "sequential_reading",
        "status": "completed",
        "activity": "sequential_reading_activity",
        "module_key": "sequential_reading",
        "segment_count": segment_count,
        "note_count": note_count,
        "message": f"顺序精读完成（{segment_count} 段，{note_count} 条笔记）",
    }
    if model_id is not None:
        payload["model_id"] = model_id
    workflow_event_writer.record_workflow_event(
        context=context,
        event_type="seed.stage.completed",
        payload=payload,
    )
    return True


def _record_failed_runtime_facts_event(
    *,
    context: AgentContext,
    error_code: str,
    error_message: str,
    workflow_event_writer: WorkflowEventWriter | None,
) -> bool:
    if workflow_event_writer is None:
        return False
    workflow_event_writer.record_workflow_event(
        context=context,
        event_type="seed.stage.failed",
        payload={
            "stage": "persist_runtime_facts",
            "status": "failed",
            "activity": "persist_runtime_facts_activity",
            "error_code": error_code,
            "error_message": error_message,
        },
    )
    return True


def _record_completed_runtime_facts_event(
    *,
    context: AgentContext,
    entity_count: int,
    entity_label_count: int,
    relationship_count: int,
    plot_thread_count: int,
    thread_lifecycle_count: int,
    narrative_arc_count: int,
    volume_summary_count: int,
    world_rule_count: int,
    character_event_count: int,
    world_event_count: int,
    relationship_event_count: int,
    consistency_note_count: int,
    segment_summary_count: int,
    workflow_event_writer: WorkflowEventWriter | None,
) -> bool:
    if workflow_event_writer is None:
        return False
    workflow_event_writer.record_workflow_event(
        context=context,
        event_type="seed.stage.completed",
        payload={
            "stage": "persist_runtime_facts",
            "status": "completed",
            "activity": "persist_runtime_facts_activity",
            "entity_count": entity_count,
            "entity_label_count": entity_label_count,
            "relationship_count": relationship_count,
            "plot_thread_count": plot_thread_count,
            "thread_lifecycle_count": thread_lifecycle_count,
            "narrative_arc_count": narrative_arc_count,
            "volume_summary_count": volume_summary_count,
            "world_rule_count": world_rule_count,
            "character_event_count": character_event_count,
            "world_event_count": world_event_count,
            "relationship_event_count": relationship_event_count,
            "consistency_note_count": consistency_note_count,
            "segment_summary_count": segment_summary_count,
        },
    )
    return True


def _record_failed_global_aggregation_event(
    *,
    context: AgentContext,
    error_code: str,
    error_message: str,
    workflow_event_writer: WorkflowEventWriter | None,
) -> bool:
    if workflow_event_writer is None:
        return False
    workflow_event_writer.record_workflow_event(
        context=context,
        event_type="seed.stage.failed",
        payload={
            "stage": "global_aggregation",
            "status": "failed",
            "activity": "global_aggregation_activity",
            "module_key": GLOBAL_AGGREGATION_MODULE_KEY,
            "error_code": error_code,
            "error_message": error_message,
        },
    )
    return True


def _record_completed_global_aggregation_event(
    *,
    context: AgentContext,
    model_id: str | None,
    segment_count: int,
    summary_count: int,
    seed_analysis_snapshot_id: str | None,
    workflow_event_writer: WorkflowEventWriter | None,
) -> bool:
    if workflow_event_writer is None:
        return False
    payload: dict[str, object] = {
        "stage": "global_aggregation",
        "status": "completed",
        "activity": "global_aggregation_activity",
        "module_key": GLOBAL_AGGREGATION_MODULE_KEY,
        "segment_count": segment_count,
        "summary_count": summary_count,
    }
    if model_id is not None:
        payload["model_id"] = model_id
    if seed_analysis_snapshot_id is not None:
        payload["seed_analysis_snapshot_id"] = seed_analysis_snapshot_id
    workflow_event_writer.record_workflow_event(
        context=context,
        event_type="seed.stage.completed",
        payload=payload,
    )
    return True


def _record_failed_ontology_event(
    *,
    context: AgentContext,
    error_code: str,
    error_message: str,
    workflow_event_writer: WorkflowEventWriter | None,
) -> bool:
    if workflow_event_writer is None:
        return False
    workflow_event_writer.record_workflow_event(
        context=context,
        event_type="seed.stage.failed",
        payload={
            "stage": "story_ontology",
            "status": "failed",
            "activity": "ontology_activity",
            "module_key": STORY_ONTOLOGY_MODULE_KEY,
            "error_code": error_code,
            "error_message": error_message,
        },
    )
    return True


def _record_completed_ontology_event(
    *,
    context: AgentContext,
    model_id: str | None,
    ontology_snapshot_id: str,
    entity_type_count: int,
    relationship_type_count: int,
    world_rule_type_count: int,
    workflow_event_writer: WorkflowEventWriter | None,
) -> bool:
    if workflow_event_writer is None:
        return False
    payload: dict[str, object] = {
        "stage": "story_ontology",
        "status": "completed",
        "activity": "ontology_activity",
        "module_key": STORY_ONTOLOGY_MODULE_KEY,
        "ontology_snapshot_id": ontology_snapshot_id,
        "entity_type_count": entity_type_count,
        "relationship_type_count": relationship_type_count,
        "world_rule_type_count": world_rule_type_count,
    }
    if model_id is not None:
        payload["model_id"] = model_id
    workflow_event_writer.record_workflow_event(
        context=context,
        event_type="seed.stage.completed",
        payload=payload,
    )
    return True


def _record_failed_entity_resolution_event(
    *,
    context: AgentContext,
    error_code: str,
    error_message: str,
    workflow_event_writer: WorkflowEventWriter | None,
) -> bool:
    if workflow_event_writer is None:
        return False
    workflow_event_writer.record_workflow_event(
        context=context,
        event_type="seed.stage.failed",
        payload={
            "stage": "entity_resolution",
            "status": "failed",
            "activity": "entity_resolution_activity",
            "module_key": ENTITY_RESOLUTION_MODULE_KEY,
            "error_code": error_code,
            "error_message": error_message,
        },
    )
    return True


def _record_completed_entity_resolution_event(
    *,
    context: AgentContext,
    model_id: str | None,
    resolution_snapshot_id: str,
    merged_entity_count: int,
    alias_count: int,
    conflict_count: int,
    workflow_event_writer: WorkflowEventWriter | None,
) -> bool:
    if workflow_event_writer is None:
        return False
    payload: dict[str, object] = {
        "stage": "entity_resolution",
        "status": "completed",
        "activity": "entity_resolution_activity",
        "module_key": ENTITY_RESOLUTION_MODULE_KEY,
        "resolution_snapshot_id": resolution_snapshot_id,
        "merged_entity_count": merged_entity_count,
        "alias_count": alias_count,
        "conflict_count": conflict_count,
    }
    if model_id is not None:
        payload["model_id"] = model_id
    workflow_event_writer.record_workflow_event(
        context=context,
        event_type="seed.stage.completed",
        payload=payload,
    )
    return True


def _record_failed_agent_profile_event(
    *,
    context: AgentContext,
    error_code: str,
    error_message: str,
    workflow_event_writer: WorkflowEventWriter | None,
) -> bool:
    if workflow_event_writer is None:
        return False
    workflow_event_writer.record_workflow_event(
        context=context,
        event_type="seed.stage.failed",
        payload={
            "stage": "agent_profiles",
            "status": "failed",
            "activity": "agent_profile_activity",
            "module_key": CHARACTER_AGENT_PROFILE_MODULE_KEY,
            "error_code": error_code,
            "error_message": error_message,
        },
    )
    return True


def _record_completed_agent_profile_event(
    *,
    context: AgentContext,
    model_id: str | None,
    profile_snapshot_id: str,
    profile_count: int,
    memory_seed_count: int,
    relationship_view_count: int,
    workflow_event_writer: WorkflowEventWriter | None,
) -> bool:
    if workflow_event_writer is None:
        return False
    payload: dict[str, object] = {
        "stage": "agent_profiles",
        "status": "completed",
        "activity": "agent_profile_activity",
        "module_key": CHARACTER_AGENT_PROFILE_MODULE_KEY,
        "profile_snapshot_id": profile_snapshot_id,
        "profile_count": profile_count,
        "memory_seed_count": memory_seed_count,
        "relationship_view_count": relationship_view_count,
    }
    if model_id is not None:
        payload["model_id"] = model_id
    workflow_event_writer.record_workflow_event(
        context=context,
        event_type="seed.stage.completed",
        payload=payload,
    )
    return True


def _record_failed_archive_candidate_event(
    *,
    context: AgentContext,
    error_code: str,
    error_message: str,
    workflow_event_writer: WorkflowEventWriter | None,
) -> bool:
    if workflow_event_writer is None:
        return False
    workflow_event_writer.record_workflow_event(
        context=context,
        event_type="seed.stage.failed",
        payload={
            "stage": "archive_candidates",
            "status": "failed",
            "activity": "archive_candidate_activity",
            "module_key": NARRATIVE_ARCHIVES_MODULE_KEY,
            "error_code": error_code,
            "error_message": error_message,
        },
    )
    return True


def _record_completed_archive_candidate_event(
    *,
    context: AgentContext,
    model_id: str | None,
    archive_candidate_batch_id: str,
    candidate_count: int,
    archive_entity_candidate_count: int,
    memory_candidate_count: int,
    workflow_event_writer: WorkflowEventWriter | None,
) -> bool:
    if workflow_event_writer is None:
        return False
    payload: dict[str, object] = {
        "stage": "archive_candidates",
        "status": "completed",
        "activity": "archive_candidate_activity",
        "module_key": NARRATIVE_ARCHIVES_MODULE_KEY,
        "archive_candidate_batch_id": archive_candidate_batch_id,
        "candidate_count": candidate_count,
        "archive_entity_candidate_count": archive_entity_candidate_count,
        "memory_candidate_count": memory_candidate_count,
    }
    if model_id is not None:
        payload["model_id"] = model_id
    workflow_event_writer.record_workflow_event(
        context=context,
        event_type="seed.stage.completed",
        payload=payload,
    )
    return True


def _record_failed_index_assets_event(
    *,
    context: AgentContext,
    error_code: str,
    error_message: str,
    workflow_event_writer: WorkflowEventWriter | None,
) -> bool:
    if workflow_event_writer is None:
        return False
    workflow_event_writer.record_workflow_event(
        context=context,
        event_type="seed.stage.failed",
        payload={
            "stage": "index_assets",
            "status": "failed",
            "activity": "index_assets_activity",
            "error_code": error_code,
            "error_message": error_message,
        },
    )
    return True


def _record_completed_index_assets_event(
    *,
    context: AgentContext,
    asset_index_batch_id: str,
    indexed_asset_count: int,
    search_document_count: int,
    embedding_count: int,
    workflow_event_writer: WorkflowEventWriter | None,
) -> bool:
    if workflow_event_writer is None:
        return False
    workflow_event_writer.record_workflow_event(
        context=context,
        event_type="seed.stage.completed",
        payload={
            "stage": "index_assets",
            "status": "completed",
            "activity": "index_assets_activity",
            "asset_index_batch_id": asset_index_batch_id,
            "indexed_asset_count": indexed_asset_count,
            "search_document_count": search_document_count,
            "embedding_count": embedding_count,
        },
    )
    return True


def _record_failed_finalize_event(
    *,
    context: AgentContext,
    error_code: str,
    error_message: str,
    workflow_event_writer: WorkflowEventWriter | None,
) -> bool:
    if workflow_event_writer is None:
        return False
    workflow_event_writer.record_workflow_event(
        context=context,
        event_type="seed.stage.failed",
        payload={
            "stage": "finalize",
            "status": "failed",
            "activity": "finalize_seed_activity",
            "error_code": error_code,
            "error_message": error_message,
        },
    )
    return True


def _record_completed_finalize_event(
    *,
    context: AgentContext,
    project_readiness_snapshot_id: str,
    ready_asset_count: int,
    ready_entity_count: int,
    ready_relationship_count: int,
    ready_world_rule_count: int,
    workflow_event_writer: WorkflowEventWriter | None,
) -> bool:
    if workflow_event_writer is None:
        return False
    workflow_event_writer.record_workflow_event(
        context=context,
        event_type="seed.stage.completed",
        payload={
            "stage": "finalize",
            "status": "completed",
            "activity": "finalize_seed_activity",
            "project_readiness_snapshot_id": project_readiness_snapshot_id,
            "ready_asset_count": ready_asset_count,
            "ready_entity_count": ready_entity_count,
            "ready_relationship_count": ready_relationship_count,
            "ready_world_rule_count": ready_world_rule_count,
        },
    )
    return True


def _parse_file_failed_result(
    *,
    base: dict[str, Any],
    context: AgentContext,
    source_file_id: str,
    code: str,
    message: str,
    public_message: str,
    workflow_event_writer: WorkflowEventWriter | None,
    source_status_writer: SourceFileStatusWriter | None = None,
    workflow_status_writer: WorkflowRunStatusWriter | None = None,
) -> dict[str, Any]:
    try:
        _mark_source_file_parse_status(
            context=context,
            source_file_id=source_file_id,
            parse_status="failed",
            source_status_writer=source_status_writer,
        )
    except LLMFacilityError as exc:
        event_persisted = _record_failed_parse_event(
            context=context,
            source_file_id=source_file_id,
            error_code=exc.code,
            error_message=exc.message,
            workflow_event_writer=workflow_event_writer,
        )
        return _terminal_seed_stage_failed_result(
            base=base,
            context=context,
            code=exc.code,
            message=exc.message,
            public_message=exc.message,
            workflow_status_writer=workflow_status_writer,
            extra={
                "source_file_id": source_file_id,
                "stage": "parse_file",
                "stage_event_persisted": event_persisted,
            },
        )
    except Exception as exc:
        sanitized = LLMFacilityError(
            "SOURCE_FILE_PARSE_STATUS_UPDATE_FAILED",
            "source file parse status update failed",
        )
        event_persisted = _record_failed_parse_event(
            context=context,
            source_file_id=source_file_id,
            error_code=sanitized.code,
            error_message=sanitized.message,
            workflow_event_writer=workflow_event_writer,
        )
        return _terminal_seed_stage_failed_result(
            base=base,
            context=context,
            code=sanitized.code,
            message=sanitized.message,
            public_message=sanitized.message,
            workflow_status_writer=workflow_status_writer,
            extra={
                "source_file_id": source_file_id,
                "stage": "parse_file",
                "stage_event_persisted": event_persisted,
            },
        )
    event_persisted = _record_failed_parse_event(
        context=context,
        source_file_id=source_file_id,
        error_code=code,
        error_message=public_message,
        workflow_event_writer=workflow_event_writer,
    )
    return _terminal_seed_stage_failed_result(
        base=base,
        context=context,
        code=code,
        message=message,
        public_message=public_message,
        workflow_status_writer=workflow_status_writer,
        extra={
            "source_file_id": source_file_id,
            "stage": "parse_file",
            "stage_event_persisted": event_persisted,
        },
    )


def _segment_text_failed_result(
    *,
    base: dict[str, Any],
    context: AgentContext,
    source_file_id: str,
    code: str,
    message: str,
    public_message: str,
    workflow_event_writer: WorkflowEventWriter | None,
    workflow_status_writer: WorkflowRunStatusWriter | None = None,
) -> dict[str, Any]:
    _record_failed_segment_event(
        context=context,
        source_file_id=source_file_id,
        error_code=code,
        error_message=public_message,
        workflow_event_writer=workflow_event_writer,
    )
    return _terminal_seed_stage_failed_result(
        base=base,
        context=context,
        code=code,
        message=message,
        public_message=public_message,
        workflow_status_writer=workflow_status_writer,
        extra={"source_file_id": source_file_id, "stage": "segment_text"},
    )


def _terminal_seed_stage_failed_result(
    *,
    base: dict[str, Any],
    context: AgentContext,
    code: str,
    message: str,
    public_message: str,
    workflow_status_writer: WorkflowRunStatusWriter | None,
    extra: dict[str, Any],
) -> dict[str, Any]:
    try:
        workflow_status_persisted = _mark_seed_workflow_failed(
            workflow_status_writer,
            context=context,
            code=code,
            message=public_message,
        )
    except Exception:
        return _error_result(
            base=base,
            code="WORKFLOW_STATUS_WRITE_FAILED",
            message="seed workflow status write failed",
            extra=extra,
        )
    return _error_result(
        base=base,
        code=code,
        message=message,
        extra={**extra, "workflow_status_persisted": workflow_status_persisted},
    )


def _sequential_reading_failed_result(
    *,
    base: dict[str, Any],
    context: AgentContext,
    segment_count: int,
    code: str,
    message: str,
    public_message: str,
    workflow_event_writer: WorkflowEventWriter | None,
    workflow_status_writer: WorkflowRunStatusWriter | None = None,
) -> dict[str, Any]:
    _record_failed_sequential_reading_event(
        context=context,
        segment_count=segment_count,
        error_code=code,
        error_message=public_message,
        workflow_event_writer=workflow_event_writer,
    )
    try:
        workflow_status_persisted = _mark_seed_workflow_failed(
            workflow_status_writer,
            context=context,
            code=code,
            message=public_message,
        )
    except Exception:
        return _error_result(
            base=base,
            code="WORKFLOW_STATUS_WRITE_FAILED",
            message="seed workflow status write failed",
            extra={"stage": "sequential_reading", "module_key": "sequential_reading"},
        )
    return _error_result(
        base=base,
        code=code,
        message=message,
        extra={
            "stage": "sequential_reading",
            "module_key": "sequential_reading",
            "workflow_status_persisted": workflow_status_persisted,
        },
    )


def _sequential_schema_failed_result(
    *,
    base: dict[str, Any],
    context: AgentContext,
    segment_count: int,
    message: str,
    workflow_event_writer: WorkflowEventWriter | None,
    workflow_status_writer: WorkflowRunStatusWriter | None = None,
) -> dict[str, Any]:
    return _sequential_reading_failed_result(
        base=base,
        context=context,
        segment_count=segment_count,
        code="SCHEMA_VALIDATION_FAILED",
        message=message,
        public_message="sequential reading output schema validation failed",
        workflow_event_writer=workflow_event_writer,
        workflow_status_writer=workflow_status_writer,
    )


def _persist_runtime_facts_failed_result(
    *,
    base: dict[str, Any],
    context: AgentContext,
    code: str,
    message: str,
    public_message: str,
    workflow_event_writer: WorkflowEventWriter | None,
) -> dict[str, Any]:
    _record_failed_runtime_facts_event(
        context=context,
        error_code=code,
        error_message=public_message,
        workflow_event_writer=workflow_event_writer,
    )
    return _error_result(
        base=base,
        code=code,
        message=message,
        extra={"stage": "persist_runtime_facts"},
    )


def _global_aggregation_failed_result(
    *,
    base: dict[str, Any],
    context: AgentContext,
    code: str,
    message: str,
    public_message: str,
    workflow_event_writer: WorkflowEventWriter | None,
) -> dict[str, Any]:
    safe_code = _public_global_aggregation_error_code(code)
    safe_message = _public_global_aggregation_error_message(safe_code)
    _record_failed_global_aggregation_event(
        context=context,
        error_code=safe_code,
        error_message=safe_message,
        workflow_event_writer=workflow_event_writer,
    )
    return _error_result(
        base=base,
        code=safe_code,
        message=safe_message,
        extra={"stage": "global_aggregation", "module_key": GLOBAL_AGGREGATION_MODULE_KEY},
    )


def _ontology_failed_result(
    *,
    base: dict[str, Any],
    context: AgentContext,
    code: str,
    message: str,
    public_message: str,
    workflow_event_writer: WorkflowEventWriter | None,
    workflow_status_writer: WorkflowRunStatusWriter | None = None,
) -> dict[str, Any]:
    _record_failed_ontology_event(
        context=context,
        error_code=code,
        error_message=public_message,
        workflow_event_writer=workflow_event_writer,
    )
    try:
        workflow_status_persisted = _mark_seed_workflow_failed(
            workflow_status_writer,
            context=context,
            code=code,
            message=public_message,
        )
    except Exception:
        return _error_result(
            base=base,
            code="WORKFLOW_STATUS_WRITE_FAILED",
            message="seed workflow status write failed",
            extra={"stage": "story_ontology", "module_key": STORY_ONTOLOGY_MODULE_KEY},
        )
    return _error_result(
        base=base,
        code=code,
        message=message,
        extra={
            "stage": "story_ontology",
            "module_key": STORY_ONTOLOGY_MODULE_KEY,
            "workflow_status_persisted": workflow_status_persisted,
        },
    )


def _entity_resolution_failed_result(
    *,
    base: dict[str, Any],
    context: AgentContext,
    code: str,
    message: str,
    public_message: str,
    workflow_event_writer: WorkflowEventWriter | None,
) -> dict[str, Any]:
    _record_failed_entity_resolution_event(
        context=context,
        error_code=code,
        error_message=public_message,
        workflow_event_writer=workflow_event_writer,
    )
    return _error_result(
        base=base,
        code=code,
        message=message,
        extra={"stage": "entity_resolution", "module_key": ENTITY_RESOLUTION_MODULE_KEY},
    )


def _agent_profile_failed_result(
    *,
    base: dict[str, Any],
    context: AgentContext,
    code: str,
    message: str,
    public_message: str,
    workflow_event_writer: WorkflowEventWriter | None,
) -> dict[str, Any]:
    _record_failed_agent_profile_event(
        context=context,
        error_code=code,
        error_message=public_message,
        workflow_event_writer=workflow_event_writer,
    )
    return _error_result(
        base=base,
        code=code,
        message=message,
        extra={"stage": "agent_profiles", "module_key": CHARACTER_AGENT_PROFILE_MODULE_KEY},
    )


def _archive_candidate_failed_result(
    *,
    base: dict[str, Any],
    context: AgentContext,
    code: str,
    message: str,
    public_message: str,
    workflow_event_writer: WorkflowEventWriter | None,
) -> dict[str, Any]:
    _record_failed_archive_candidate_event(
        context=context,
        error_code=code,
        error_message=public_message,
        workflow_event_writer=workflow_event_writer,
    )
    return _error_result(
        base=base,
        code=code,
        message=message,
        extra={"stage": "archive_candidates", "module_key": NARRATIVE_ARCHIVES_MODULE_KEY},
    )


def _index_assets_failed_result(
    *,
    base: dict[str, Any],
    context: AgentContext,
    code: str,
    message: str,
    public_message: str,
    workflow_event_writer: WorkflowEventWriter | None,
) -> dict[str, Any]:
    _record_failed_index_assets_event(
        context=context,
        error_code=code,
        error_message=public_message,
        workflow_event_writer=workflow_event_writer,
    )
    return _error_result(
        base=base,
        code=code,
        message=message,
        extra={"stage": "index_assets"},
    )


def _finalize_seed_failed_result(
    *,
    base: dict[str, Any],
    context: AgentContext,
    code: str,
    message: str,
    public_message: str,
    workflow_event_writer: WorkflowEventWriter | None,
    workflow_status_writer: WorkflowRunStatusWriter | None = None,
) -> dict[str, Any]:
    _record_failed_finalize_event(
        context=context,
        error_code=code,
        error_message=public_message,
        workflow_event_writer=workflow_event_writer,
    )
    try:
        workflow_status_persisted = _mark_seed_workflow_failed(
            workflow_status_writer,
            context=context,
            code=code,
            message=public_message,
        )
    except Exception:
        return _error_result(
            base=base,
            code="WORKFLOW_STATUS_WRITE_FAILED",
            message="seed workflow status write failed",
            extra={"stage": "finalize"},
        )
    return _error_result(
        base=base,
        code=code,
        message=message,
        extra={"stage": "finalize", "workflow_status_persisted": workflow_status_persisted},
    )


@activity.defn
def parse_file_activity(
    payload: dict[str, Any],
    source_object_store: ObjectStore | None = None,
    artifact_object_store: ObjectStore | None = None,
    text_artifact_writer: TextArtifactWriter | None = None,
    source_status_writer: SourceFileStatusWriter | None = None,
    workflow_event_writer: WorkflowEventWriter | None = None,
    workflow_status_writer: WorkflowRunStatusWriter | None = None,
    pdf_ocr_backend: PdfOcrBackend | None = None,
) -> dict[str, Any]:
    context = AgentContext.model_validate(payload.get("context", payload))
    base = _base_payload(context, payload.get("upload_id") if isinstance(payload.get("upload_id"), str) else None)
    if not context.has_permission("seed_pipeline", "run"):
        return _error_result(
            base=base,
            code="FORBIDDEN",
            message="seed_pipeline run permission is required",
        )
    source_file_id = payload.get("source_file_id")
    source_object_key = payload.get("source_object_key")
    mime_type = payload.get("mime_type", payload.get("source_mime_type", ""))
    if not isinstance(source_file_id, str) or not source_file_id.strip():
        return _error_result(base=base, code="VALIDATION_FAILED", message="source_file_id is required")
    if not isinstance(source_object_key, str) or not source_object_key.strip():
        return _error_result(base=base, code="VALIDATION_FAILED", message="source_object_key is required")
    normalized_source_file_id = source_file_id.strip()
    try:
        workflow_event_writer = _resolved_workflow_event_writer(workflow_event_writer)
    except Exception:
        return _error_result(
            base=base,
            code="WORKFLOW_EVENT_WRITE_FAILED",
            message="workflow event write failed",
            extra={"source_file_id": normalized_source_file_id, "stage": "parse_file"},
        )
    try:
        workflow_status_writer = (
            workflow_status_writer if workflow_status_writer is not None else _workflow_status_writer_from_env()
        )
    except Exception:
        workflow_status_writer = _UnavailableWorkflowRunStatusWriter()
    try:
        status_writer = (
            source_status_writer if source_status_writer is not None else _source_file_status_writer_from_env()
        )
    except Exception:
        event_persisted = _record_failed_parse_event(
            context=context,
            source_file_id=normalized_source_file_id,
            error_code="SOURCE_FILE_PARSE_STATUS_UPDATE_FAILED",
            error_message="source file parse status update failed",
            workflow_event_writer=workflow_event_writer,
        )
        return _terminal_seed_stage_failed_result(
            base=base,
            context=context,
            code="SOURCE_FILE_PARSE_STATUS_UPDATE_FAILED",
            message="source file parse status update failed",
            public_message="source file parse status update failed",
            workflow_status_writer=workflow_status_writer,
            extra={
                "source_file_id": normalized_source_file_id,
                "stage": "parse_file",
                "stage_event_persisted": event_persisted,
            },
        )
    if not isinstance(mime_type, str) or not _is_supported_source_mime(mime_type):
        return _parse_file_failed_result(
            base=base,
            context=context,
            source_file_id=normalized_source_file_id,
            code="FILE_PARSE_UNSUPPORTED_MIME",
            message="parse_file currently supports TXT, Markdown, and PDF source objects",
            public_message="unsupported source MIME type",
            workflow_event_writer=workflow_event_writer,
            source_status_writer=status_writer,
            workflow_status_writer=workflow_status_writer,
        )
    try:
        source_store = source_object_store if source_object_store is not None else _object_store_from_env()
        artifact_store = artifact_object_store if artifact_object_store is not None else _object_store_from_env()
    except Exception:
        return _parse_file_failed_result(
            base=base,
            context=context,
            source_file_id=source_file_id.strip(),
            code="OBJECT_STORAGE_BACKEND_MISCONFIGURED",
            message="object storage backend is misconfigured",
            public_message="object storage backend is misconfigured",
            workflow_event_writer=workflow_event_writer,
            source_status_writer=status_writer,
            workflow_status_writer=workflow_status_writer,
        )
    try:
        artifact_writer = text_artifact_writer if text_artifact_writer is not None else _text_artifact_writer_from_env()
    except Exception:
        return _parse_file_failed_result(
            base=base,
            context=context,
            source_file_id=normalized_source_file_id,
            code="TEXT_ARTIFACT_WRITE_FAILED",
            message="text artifact write failed",
            public_message="text artifact write failed",
            workflow_event_writer=workflow_event_writer,
            source_status_writer=status_writer,
            workflow_status_writer=workflow_status_writer,
        )
    if source_store is None or artifact_store is None:
        return _parse_file_failed_result(
            base=base,
            context=context,
            source_file_id=source_file_id.strip(),
            code="OBJECT_STORAGE_BACKEND_UNCONFIGURED",
            message="object storage backend is required to parse source files",
            public_message="object storage backend is unconfigured",
            workflow_event_writer=workflow_event_writer,
            source_status_writer=status_writer,
            workflow_status_writer=workflow_status_writer,
        )
    if artifact_writer is None:
        return _parse_file_failed_result(
            base=base,
            context=context,
            source_file_id=source_file_id.strip(),
            code="TEXT_ARTIFACT_WRITER_UNCONFIGURED",
            message="text artifact writer is required to persist parse_file output references",
            public_message="text artifact writer is unconfigured",
            workflow_event_writer=workflow_event_writer,
            source_status_writer=status_writer,
            workflow_status_writer=workflow_status_writer,
        )
    normalized_source_object_key = source_object_key.strip()
    try:
        source_bytes = source_store.read_bytes(normalized_source_object_key)
    except Exception:
        return _parse_file_failed_result(
            base=base,
            context=context,
            source_file_id=normalized_source_file_id,
            code="SOURCE_FILE_OBJECT_READ_FAILED",
            message="source object read failed",
            public_message="source object read failed",
            workflow_event_writer=workflow_event_writer,
            source_status_writer=status_writer,
            workflow_status_writer=workflow_status_writer,
        )
    if not _source_object_integrity_matches(payload, source_bytes):
        return _parse_file_failed_result(
            base=base,
            context=context,
            source_file_id=normalized_source_file_id,
            code="SOURCE_FILE_OBJECT_INTEGRITY_MISMATCH",
            message="source object integrity check failed",
            public_message="source object integrity check failed",
            workflow_event_writer=workflow_event_writer,
            source_status_writer=status_writer,
            workflow_status_writer=workflow_status_writer,
        )
    try:
        extracted_text = _extract_source_text(source_bytes, mime_type)
    except PdfOcrBackendUnconfiguredError:
        try:
            extracted_text = _extract_pdf_ocr_text(source_bytes, pdf_ocr_backend)
        except PdfOcrError as exc:
            return _parse_file_failed_result(
                base=base,
                context=context,
                source_file_id=normalized_source_file_id,
                code=exc.code,
                message=exc.public_message,
                public_message=exc.public_message,
                workflow_event_writer=workflow_event_writer,
                source_status_writer=status_writer,
                workflow_status_writer=workflow_status_writer,
            )
    except (UnicodeDecodeError, ValueError, PyPdfError):
        return _parse_file_failed_result(
            base=base,
            context=context,
            source_file_id=normalized_source_file_id,
            code="FILE_PARSE_DECODE_FAILED",
            message="source object text extraction failed",
            public_message="source object text extraction failed",
            workflow_event_writer=workflow_event_writer,
            source_status_writer=status_writer,
            workflow_status_writer=workflow_status_writer,
        )
    artifact_object_key = _extracted_text_object_key(context, normalized_source_file_id)
    artifact_bytes = extracted_text.encode("utf-8")
    artifact_sha256 = hashlib.sha256(artifact_bytes).hexdigest()
    char_count = len(extracted_text)
    line_count = len(extracted_text.splitlines())
    try:
        artifact_store.write_bytes(artifact_object_key, artifact_bytes, "text/plain; charset=utf-8")
        artifact_writer.record_text_artifact(
            context=context,
            source_file_id=normalized_source_file_id,
            artifact_type="extracted_text",
            object_key=artifact_object_key,
            char_count=char_count,
            line_count=line_count,
            sha256=artifact_sha256,
            metadata_jsonb={
                "mime_type": mime_type,
                "source_object_key": normalized_source_object_key,
            },
        )
    except Exception:
        return _parse_file_failed_result(
            base=base,
            context=context,
            source_file_id=normalized_source_file_id,
            code="TEXT_ARTIFACT_WRITE_FAILED",
            message="text artifact write failed",
            public_message="text artifact write failed",
            workflow_event_writer=workflow_event_writer,
            source_status_writer=status_writer,
            workflow_status_writer=workflow_status_writer,
        )
    try:
        _mark_source_file_parse_status(
            context=context,
            source_file_id=normalized_source_file_id,
            parse_status="parsed",
            source_status_writer=status_writer,
        )
    except LLMFacilityError as exc:
        event_persisted = _record_failed_parse_event(
            context=context,
            source_file_id=normalized_source_file_id,
            error_code=exc.code,
            error_message=exc.message,
            workflow_event_writer=workflow_event_writer,
        )
        return _terminal_seed_stage_failed_result(
            base=base,
            context=context,
            code=exc.code,
            message=exc.message,
            public_message=exc.message,
            workflow_status_writer=workflow_status_writer,
            extra={
                "source_file_id": normalized_source_file_id,
                "stage": "parse_file",
                "stage_event_persisted": event_persisted,
            },
        )
    except Exception:
        event_persisted = _record_failed_parse_event(
            context=context,
            source_file_id=normalized_source_file_id,
            error_code="SOURCE_FILE_PARSE_STATUS_UPDATE_FAILED",
            error_message="source file parse status update failed",
            workflow_event_writer=workflow_event_writer,
        )
        return _terminal_seed_stage_failed_result(
            base=base,
            context=context,
            code="SOURCE_FILE_PARSE_STATUS_UPDATE_FAILED",
            message="source file parse status update failed",
            public_message="source file parse status update failed",
            workflow_status_writer=workflow_status_writer,
            extra={
                "source_file_id": normalized_source_file_id,
                "stage": "parse_file",
                "stage_event_persisted": event_persisted,
            },
        )
    event_persisted = _record_completed_parse_event(
        context=context,
        source_file_id=normalized_source_file_id,
        char_count=char_count,
        line_count=line_count,
        sha256=artifact_sha256,
        workflow_event_writer=workflow_event_writer,
    )
    return {
        **base,
        "source_file_id": normalized_source_file_id,
        "status": "completed",
        "stage": "parse_file",
        "next_stage": "segment_text",
        "artifact_type": "extracted_text",
        "artifact_object_key": artifact_object_key,
        "char_count": char_count,
        "line_count": line_count,
        "sha256": artifact_sha256,
        "stage_event_persisted": event_persisted,
    }


@activity.defn
def segment_text_activity(
    payload: dict[str, Any],
    artifact_object_store: ObjectStore | None = None,
    text_segment_writer: TextSegmentWriter | None = None,
    workflow_event_writer: WorkflowEventWriter | None = None,
    workflow_status_writer: WorkflowRunStatusWriter | None = None,
) -> dict[str, Any]:
    context = AgentContext.model_validate(payload.get("context", payload))
    base = _base_payload(context, payload.get("upload_id") if isinstance(payload.get("upload_id"), str) else None)
    if not context.has_permission("seed_pipeline", "run"):
        return _error_result(
            base=base,
            code="FORBIDDEN",
            message="seed_pipeline run permission is required",
        )
    source_file_id = payload.get("source_file_id")
    artifact_object_key = payload.get("artifact_object_key")
    artifact_type = payload.get("artifact_type", "extracted_text")
    if not isinstance(source_file_id, str) or not source_file_id.strip():
        return _error_result(base=base, code="VALIDATION_FAILED", message="source_file_id is required")
    if not isinstance(artifact_object_key, str) or not artifact_object_key.strip():
        return _error_result(base=base, code="VALIDATION_FAILED", message="artifact_object_key is required")
    try:
        workflow_event_writer = _resolved_workflow_event_writer(workflow_event_writer)
    except Exception:
        return _error_result(
            base=base,
            code="WORKFLOW_EVENT_WRITE_FAILED",
            message="workflow event write failed",
            extra={"source_file_id": source_file_id.strip(), "stage": "segment_text"},
        )
    try:
        workflow_status_writer = (
            workflow_status_writer if workflow_status_writer is not None else _workflow_status_writer_from_env()
        )
    except Exception:
        workflow_status_writer = _UnavailableWorkflowRunStatusWriter()
    if artifact_type != "extracted_text":
        return _segment_text_failed_result(
            base=base,
            context=context,
            source_file_id=source_file_id.strip(),
            code="SEGMENT_TEXT_UNSUPPORTED_ARTIFACT",
            message="segment_text currently requires an extracted_text artifact",
            public_message="unsupported text artifact type",
            workflow_event_writer=workflow_event_writer,
            workflow_status_writer=workflow_status_writer,
        )
    try:
        object_store = artifact_object_store if artifact_object_store is not None else _object_store_from_env()
    except Exception:
        return _segment_text_failed_result(
            base=base,
            context=context,
            source_file_id=source_file_id.strip(),
            code="OBJECT_STORAGE_BACKEND_MISCONFIGURED",
            message="object storage backend is misconfigured",
            public_message="object storage backend is misconfigured",
            workflow_event_writer=workflow_event_writer,
            workflow_status_writer=workflow_status_writer,
        )
    normalized_source_file_id = source_file_id.strip()
    normalized_artifact_object_key = artifact_object_key.strip()
    try:
        segment_writer = text_segment_writer if text_segment_writer is not None else _text_segment_writer_from_env()
    except Exception:
        return _segment_text_failed_result(
            base=base,
            context=context,
            source_file_id=normalized_source_file_id,
            code="TEXT_SEGMENT_WRITE_FAILED",
            message="text segment write failed",
            public_message="text segment write failed",
            workflow_event_writer=workflow_event_writer,
            workflow_status_writer=workflow_status_writer,
        )
    if object_store is None:
        return _segment_text_failed_result(
            base=base,
            context=context,
            source_file_id=normalized_source_file_id,
            code="OBJECT_STORAGE_BACKEND_UNCONFIGURED",
            message="object storage backend is required to segment extracted text",
            public_message="object storage backend is unconfigured",
            workflow_event_writer=workflow_event_writer,
            workflow_status_writer=workflow_status_writer,
        )
    if segment_writer is None:
        return _segment_text_failed_result(
            base=base,
            context=context,
            source_file_id=normalized_source_file_id,
            code="TEXT_SEGMENT_WRITER_UNCONFIGURED",
            message="text segment writer is required to persist segment references",
            public_message="text segment writer is unconfigured",
            workflow_event_writer=workflow_event_writer,
            workflow_status_writer=workflow_status_writer,
        )
    try:
        event_persisted = _record_pending_segment_event(
            context=context,
            source_file_id=normalized_source_file_id,
            artifact_type=artifact_type,
            workflow_event_writer=workflow_event_writer,
        )
    except Exception:
        return _error_result(
            base=base,
            code="WORKFLOW_EVENT_WRITE_FAILED",
            message="workflow event write failed",
            extra={"source_file_id": normalized_source_file_id},
        )
    try:
        artifact_bytes = object_store.read_bytes(normalized_artifact_object_key)
    except Exception:
        return _segment_text_failed_result(
            base=base,
            context=context,
            source_file_id=normalized_source_file_id,
            code="TEXT_ARTIFACT_READ_FAILED",
            message="text artifact read failed",
            public_message="text artifact read failed",
            workflow_event_writer=workflow_event_writer,
            workflow_status_writer=workflow_status_writer,
        )
    try:
        extracted_text = artifact_bytes.decode("utf-8")
    except UnicodeDecodeError:
        return _segment_text_failed_result(
            base=base,
            context=context,
            source_file_id=normalized_source_file_id,
            code="TEXT_ARTIFACT_DECODE_FAILED",
            message="text artifact UTF-8 decode failed",
            public_message="text artifact UTF-8 decode failed",
            workflow_event_writer=workflow_event_writer,
            workflow_status_writer=workflow_status_writer,
        )
    try:
        segments = _segment_extracted_text(
            context=context,
            source_file_id=normalized_source_file_id,
            text=extracted_text,
            object_store=object_store,
        )
    except ValueError:
        return _segment_text_failed_result(
            base=base,
            context=context,
            source_file_id=normalized_source_file_id,
            code="SEGMENT_TEXT_EMPTY_SOURCE",
            message="extracted text artifact is empty",
            public_message="extracted text artifact is empty",
            workflow_event_writer=workflow_event_writer,
            workflow_status_writer=workflow_status_writer,
        )
    except Exception:
        return _segment_text_failed_result(
            base=base,
            context=context,
            source_file_id=normalized_source_file_id,
            code="TEXT_SEGMENT_WRITE_FAILED",
            message="text segment write failed",
            public_message="text segment write failed",
            workflow_event_writer=workflow_event_writer,
            workflow_status_writer=workflow_status_writer,
        )
    try:
        segment_writer.record_text_segments(
            context=context,
            source_file_id=normalized_source_file_id,
            segments=segments,
        )
        completed_event_persisted = _record_completed_segment_event(
            context=context,
            source_file_id=normalized_source_file_id,
            segment_count=len(segments),
            workflow_event_writer=workflow_event_writer,
        )
    except Exception:
        return _segment_text_failed_result(
            base=base,
            context=context,
            source_file_id=normalized_source_file_id,
            code="TEXT_SEGMENT_WRITE_FAILED",
            message="text segment write failed",
            public_message="text segment write failed",
            workflow_event_writer=workflow_event_writer,
            workflow_status_writer=workflow_status_writer,
        )
    return {
        **base,
        "source_file_id": normalized_source_file_id,
        "status": "completed",
        "stage": "segment_text",
        "next_stage": "sequential_reading",
        "segment_count": len(segments),
        "segments": [_sequential_segment_reference(segment) for segment in segments],
        "sha256": hashlib.sha256(artifact_bytes).hexdigest(),
        "stage_event_persisted": event_persisted and completed_event_persisted,
    }


@activity.defn
def sequential_reading_activity(
    payload: dict[str, Any],
    llm_reader: SequentialReadingReader | None = None,
    reading_notes_writer: ReadingNotesWriter | None = None,
    workflow_event_writer: WorkflowEventWriter | None = None,
    workflow_status_writer: WorkflowRunStatusWriter | None = None,
) -> dict[str, Any]:
    context = AgentContext.model_validate(payload.get("context", payload))
    base = _base_payload(context, payload.get("upload_id") if isinstance(payload.get("upload_id"), str) else None)
    if not context.has_permission("seed_pipeline", "run"):
        return _error_result(
            base=base,
            code="FORBIDDEN",
            message="seed_pipeline run permission is required",
            extra={"stage": "sequential_reading", "module_key": "sequential_reading"},
        )
    segments = payload.get("segments")
    if not isinstance(segments, list) or not segments:
        return _error_result(
            base=base,
            code="VALIDATION_FAILED",
            message="segments are required for sequential_reading",
            extra={"stage": "sequential_reading", "module_key": "sequential_reading"},
        )
    sanitized_segments = [_sanitize_segment_reference(segment) for segment in segments]
    segment_count = len(sanitized_segments)
    try:
        workflow_event_writer = _resolved_workflow_event_writer(workflow_event_writer)
    except Exception:
        return _error_result(
            base=base,
            code="WORKFLOW_EVENT_WRITE_FAILED",
            message="workflow event write failed",
            extra={"stage": "sequential_reading", "module_key": "sequential_reading"},
        )
    if workflow_status_writer is None:
        try:
            workflow_status_writer = _workflow_status_writer_from_env()
        except Exception:
            return _error_result(
                base=base,
                code="WORKFLOW_STATUS_WRITE_FAILED",
                message="seed workflow status write failed",
                extra={"stage": "sequential_reading", "module_key": "sequential_reading"},
            )
    notes_writer = reading_notes_writer if reading_notes_writer is not None else _reading_notes_writer_from_env()
    if notes_writer is None:
        return _sequential_reading_failed_result(
            base=base,
            context=context,
            segment_count=segment_count,
            code="READING_NOTES_WRITER_UNCONFIGURED",
            message="reading notes writer is required to persist sequential reading output",
            public_message="reading notes writer is unconfigured",
            workflow_event_writer=workflow_event_writer,
            workflow_status_writer=workflow_status_writer,
        )
    if llm_reader is not None:
        reader = llm_reader
    else:
        from mirofish_agents.seed.sequential_reader import LLMFacilityError

        try:
            reader = _sequential_reader_from_env()
        except LLMFacilityError as exc:
            return _sequential_reading_failed_result(
                base=base,
                context=context,
                segment_count=segment_count,
                code=exc.code,
                message=exc.message,
                public_message=_public_llm_error_message(exc.code),
                workflow_event_writer=workflow_event_writer,
                workflow_status_writer=workflow_status_writer,
            )
    if reader is None:
        return _sequential_reading_failed_result(
            base=base,
            context=context,
            segment_count=segment_count,
            code="LLM_READER_UNCONFIGURED",
            message="LLM reader is required for sequential_reading and must use LLM Facility module binding",
            public_message="LLM reader is unconfigured",
            workflow_event_writer=workflow_event_writer,
            workflow_status_writer=workflow_status_writer,
        )
    _record_pending_sequential_reading_event(
        context=context,
        segment_count=segment_count,
        workflow_event_writer=workflow_event_writer,
    )

    def _on_sequential_progress(progress_payload: dict[str, Any]) -> None:
        if not isinstance(progress_payload, dict):
            return
        public_payload = {
            key: value
            for key, value in progress_payload.items()
            if key
            in {
                "stage",
                "status",
                "phase",
                "message",
                "batch_index",
                "batch_count",
                "completed_segments",
                "total_segments",
                "segment_order_start",
                "segment_order_end",
                "chapter_guess",
                "title_guess",
                "note_count",
                "error_code",
                "error_message",
            }
        }
        _record_sequential_reading_batch_progress(
            context=context,
            payload=public_payload,
            workflow_event_writer=workflow_event_writer,
        )

    try:
        reading_result = reader.read_segments(
            context=context,
            module_key="sequential_reading",
            segments=sanitized_segments,
            progress_callback=_on_sequential_progress,
        )
    except TypeError:
        # Older test doubles may not accept progress_callback.
        try:
            reading_result = reader.read_segments(
                context=context,
                module_key="sequential_reading",
                segments=sanitized_segments,
            )
        except Exception as exc:
            return _sequential_reading_failed_result(
                base=base,
                context=context,
                segment_count=segment_count,
                code="LLM_PROVIDER_ERROR",
                message=str(exc),
                public_message="sequential reading provider failed",
                workflow_event_writer=workflow_event_writer,
                workflow_status_writer=workflow_status_writer,
            )
    except Exception as exc:
        return _sequential_reading_failed_result(
            base=base,
            context=context,
            segment_count=segment_count,
            code="LLM_PROVIDER_ERROR",
            message=str(exc),
            public_message="sequential reading provider failed",
            workflow_event_writer=workflow_event_writer,
            workflow_status_writer=workflow_status_writer,
        )
    if reading_result.get("status") != "completed":
        error = reading_result.get("error") if isinstance(reading_result.get("error"), dict) else {}
        code = error.get("code") if isinstance(error.get("code"), str) else "LLM_PROVIDER_ERROR"
        message = error.get("message") if isinstance(error.get("message"), str) else "sequential reading failed"
        return _sequential_reading_failed_result(
            base=base,
            context=context,
            segment_count=segment_count,
            code=code,
            message=message,
            public_message=_public_llm_error_message(code),
            workflow_event_writer=workflow_event_writer,
            workflow_status_writer=workflow_status_writer,
        )
    try:
        validated_result = _validated_sequential_reading_result(
            reading_result,
            segment_refs=sanitized_segments,
        )
    except ValueError as exc:
        return _sequential_schema_failed_result(
            base=base,
            context=context,
            segment_count=segment_count,
            message=str(exc),
            workflow_event_writer=workflow_event_writer,
            workflow_status_writer=workflow_status_writer,
        )
    notes = validated_result["notes"]
    try:
        notes_writer.record_reading_notes(
            context=context,
            pass_id=validated_result["pass_id"],
            pass_type="sequential_reading",
            status="completed",
            module_key=validated_result["module_key"],
            model_id=validated_result["model_id"],
            notes=notes,
            metadata_jsonb={"segment_count": segment_count},
        )
        event_persisted = _record_completed_sequential_reading_event(
            context=context,
            segment_count=segment_count,
            note_count=len(notes),
            model_id=validated_result["model_id"],
            workflow_event_writer=workflow_event_writer,
        )
    except Exception as exc:
        return _sequential_reading_failed_result(
            base=base,
            context=context,
            segment_count=segment_count,
            code="READING_NOTES_WRITE_FAILED",
            message=str(exc),
            public_message="reading notes write failed",
            workflow_event_writer=workflow_event_writer,
            workflow_status_writer=workflow_status_writer,
        )
    return {
        **base,
        "status": "completed",
        "stage": "sequential_reading",
        "next_stage": "persist_runtime_facts",
        "module_key": "sequential_reading",
        "segment_count": segment_count,
        "note_count": len(notes),
        "stage_event_persisted": event_persisted,
    }


@activity.defn
def persist_runtime_facts_activity(
    payload: dict[str, Any],
    runtime_facts_writer: RuntimeFactsWriter | None = None,
    workflow_event_writer: WorkflowEventWriter | None = None,
) -> dict[str, Any]:
    context = AgentContext.model_validate(payload.get("context", payload))
    base = _base_payload(context, payload.get("upload_id") if isinstance(payload.get("upload_id"), str) else None)
    if not context.has_permission("seed_pipeline", "run"):
        return _error_result(
            base=base,
            code="FORBIDDEN",
            message="seed_pipeline run permission is required",
            extra={"stage": "persist_runtime_facts"},
        )
    try:
        workflow_event_writer = _resolved_workflow_event_writer(workflow_event_writer)
    except Exception:
        return _workflow_event_writer_resolution_failed_result(
            base=base,
            stage="persist_runtime_facts",
        )
    try:
        reading_notes = _optional_runtime_fact_notes(payload.get("reading_notes"))
    except ValueError as exc:
        return _persist_runtime_facts_failed_result(
            base=base,
            context=context,
            code="SCHEMA_VALIDATION_FAILED",
            message=str(exc),
            public_message="runtime fact input schema validation failed",
            workflow_event_writer=workflow_event_writer,
        )
    writer = runtime_facts_writer if runtime_facts_writer is not None else _runtime_facts_writer_from_env()
    if writer is None:
        return _persist_runtime_facts_failed_result(
            base=base,
            context=context,
            code="RUNTIME_FACTS_WRITER_UNCONFIGURED",
            message="runtime facts writer is required to persist structured canon",
            public_message="runtime facts writer is unconfigured",
            workflow_event_writer=workflow_event_writer,
        )
    try:
        counts = writer.record_runtime_facts(context=context, reading_notes=reading_notes)
        entity_count = _non_negative_int(counts.get("entity_count", 0), "entity_count")
        entity_label_count = _non_negative_int(counts.get("entity_label_count", 0), "entity_label_count")
        relationship_count = _non_negative_int(counts.get("relationship_count", 0), "relationship_count")
        plot_thread_count = _non_negative_int(counts.get("plot_thread_count", 0), "plot_thread_count")
        thread_lifecycle_count = _non_negative_int(
            counts.get("thread_lifecycle_count", 0), "thread_lifecycle_count"
        )
        narrative_arc_count = _non_negative_int(counts.get("narrative_arc_count", 0), "narrative_arc_count")
        volume_summary_count = _non_negative_int(counts.get("volume_summary_count", 0), "volume_summary_count")
        world_rule_count = _non_negative_int(counts.get("world_rule_count", 0), "world_rule_count")
        character_event_count = _non_negative_int(counts.get("character_event_count", 0), "character_event_count")
        world_event_count = _non_negative_int(counts.get("world_event_count", 0), "world_event_count")
        relationship_event_count = _non_negative_int(
            counts.get("relationship_event_count", 0), "relationship_event_count"
        )
        consistency_note_count = _non_negative_int(
            counts.get("consistency_note_count", 0), "consistency_note_count"
        )
        segment_summary_count = _non_negative_int(counts.get("segment_summary_count", 0), "segment_summary_count")
        event_persisted = _record_completed_runtime_facts_event(
            context=context,
            entity_count=entity_count,
            entity_label_count=entity_label_count,
            relationship_count=relationship_count,
            plot_thread_count=plot_thread_count,
            thread_lifecycle_count=thread_lifecycle_count,
            narrative_arc_count=narrative_arc_count,
            volume_summary_count=volume_summary_count,
            world_rule_count=world_rule_count,
            character_event_count=character_event_count,
            world_event_count=world_event_count,
            relationship_event_count=relationship_event_count,
            consistency_note_count=consistency_note_count,
            segment_summary_count=segment_summary_count,
            workflow_event_writer=workflow_event_writer,
        )
    except Exception as exc:
        return _persist_runtime_facts_failed_result(
            base=base,
            context=context,
            code="RUNTIME_FACTS_WRITE_FAILED",
            message=str(exc),
            public_message="runtime facts write failed",
            workflow_event_writer=workflow_event_writer,
        )
    return {
        **base,
        "status": "completed",
        "stage": "persist_runtime_facts",
        "next_stage": "global_aggregation",
        "entity_count": entity_count,
        "entity_label_count": entity_label_count,
        "relationship_count": relationship_count,
        "plot_thread_count": plot_thread_count,
        "thread_lifecycle_count": thread_lifecycle_count,
        "narrative_arc_count": narrative_arc_count,
        "volume_summary_count": volume_summary_count,
        "world_rule_count": world_rule_count,
        "character_event_count": character_event_count,
        "world_event_count": world_event_count,
        "relationship_event_count": relationship_event_count,
        "consistency_note_count": consistency_note_count,
        "segment_summary_count": segment_summary_count,
        "stage_event_persisted": event_persisted,
    }


@activity.defn
def global_aggregation_activity(
    payload: dict[str, Any],
    global_aggregator: GlobalAggregationRunner | None = None,
    seed_analysis_writer: SeedAnalysisWriter | None = None,
    workflow_event_writer: WorkflowEventWriter | None = None,
) -> dict[str, Any]:
    context = AgentContext.model_validate(payload.get("context", payload))
    base = _base_payload(context, payload.get("upload_id") if isinstance(payload.get("upload_id"), str) else None)
    if not context.has_permission("seed_pipeline", "run"):
        return _error_result(
            base=base,
            code="FORBIDDEN",
            message="seed_pipeline run permission is required",
            extra={"stage": "global_aggregation", "module_key": GLOBAL_AGGREGATION_MODULE_KEY},
        )
    try:
        workflow_event_writer = _resolved_workflow_event_writer(workflow_event_writer)
    except Exception:
        return _workflow_event_writer_resolution_failed_result(
            base=base,
            stage="global_aggregation",
            module_key=GLOBAL_AGGREGATION_MODULE_KEY,
        )
    try:
        aggregator = global_aggregator if global_aggregator is not None else _global_aggregator_from_env()
    except Exception as exc:
        code = exc.code if isinstance(getattr(exc, "code", None), str) else "GLOBAL_AGGREGATOR_CONFIGURATION_FAILED"
        message = exc.message if isinstance(getattr(exc, "message", None), str) else str(exc)
        return _global_aggregation_failed_result(
            base=base,
            context=context,
            code=code,
            message=message,
            public_message=_public_global_aggregation_error_message(code),
            workflow_event_writer=workflow_event_writer,
        )
    if aggregator is None:
        return _global_aggregation_failed_result(
            base=base,
            context=context,
            code="GLOBAL_AGGREGATOR_UNCONFIGURED",
            message=(
                "global aggregation requires an LLM Facility backed aggregator for "
                f"{GLOBAL_AGGREGATION_MODULE_KEY}"
            ),
            public_message="global aggregator is unconfigured",
            workflow_event_writer=workflow_event_writer,
        )
    try:
        aggregation_result = aggregator.aggregate(
            context=context,
            module_key=GLOBAL_AGGREGATION_MODULE_KEY,
        )
    except Exception as exc:
        return _global_aggregation_failed_result(
            base=base,
            context=context,
            code="LLM_PROVIDER_ERROR",
            message=str(exc),
            public_message="global aggregation provider failed",
            workflow_event_writer=workflow_event_writer,
        )
    if aggregation_result.get("status") != "completed":
        error = aggregation_result.get("error") if isinstance(aggregation_result.get("error"), dict) else {}
        code = error.get("code") if isinstance(error.get("code"), str) else "LLM_PROVIDER_ERROR"
        message = error.get("message") if isinstance(error.get("message"), str) else "global aggregation failed"
        return _global_aggregation_failed_result(
            base=base,
            context=context,
            code=code,
            message=message,
            public_message=_public_global_aggregation_error_message(code),
            workflow_event_writer=workflow_event_writer,
        )
    try:
        module_key = _optional_result_text(aggregation_result, "module_key") or GLOBAL_AGGREGATION_MODULE_KEY
        if module_key != GLOBAL_AGGREGATION_MODULE_KEY:
            raise ValueError(f"module_key must be {GLOBAL_AGGREGATION_MODULE_KEY}")
        model_id = _optional_result_text(aggregation_result, "model_id")
        segment_count = _non_negative_int(aggregation_result.get("segment_count", 0), "segment_count")
        summary_count = _non_negative_int(aggregation_result.get("summary_count", 0), "summary_count")
    except Exception as exc:
        return _global_aggregation_failed_result(
            base=base,
            context=context,
            code="SCHEMA_VALIDATION_FAILED",
            message=str(exc),
            public_message="global aggregation output schema validation failed",
            workflow_event_writer=workflow_event_writer,
        )
    seed_analysis_snapshot_id: str | None = None
    try:
        analysis_writer = seed_analysis_writer if seed_analysis_writer is not None else _seed_analysis_writer_from_env()
        if analysis_writer is not None:
            seed_analysis = aggregation_result.get("seed_analysis")
            if not isinstance(seed_analysis, dict):
                raise ValueError("seed_analysis must be an object when seed analysis persistence is configured")
            seed_analysis_snapshot_id = analysis_writer.record_seed_analysis(
                context=context,
                module_key=module_key,
                model_id=model_id,
                segment_count=segment_count,
                summary_count=summary_count,
                seed_analysis=seed_analysis,
            )
            seed_analysis_snapshot_id = _required_text_value(
                seed_analysis_snapshot_id,
                "seed_analysis_snapshot_id",
            )
    except Exception as exc:
        return _global_aggregation_failed_result(
            base=base,
            context=context,
            code="SEED_ANALYSIS_WRITE_FAILED",
            message=str(exc),
            public_message="seed analysis snapshot persistence failed",
            workflow_event_writer=workflow_event_writer,
        )
    event_persisted = _record_completed_global_aggregation_event(
        context=context,
        model_id=model_id,
        segment_count=segment_count,
        summary_count=summary_count,
        seed_analysis_snapshot_id=seed_analysis_snapshot_id,
        workflow_event_writer=workflow_event_writer,
    )
    result: dict[str, Any] = {
        **base,
        "status": "completed",
        "stage": "global_aggregation",
        "next_stage": "story_ontology",
        "module_key": GLOBAL_AGGREGATION_MODULE_KEY,
        "segment_count": segment_count,
        "summary_count": summary_count,
        "stage_event_persisted": event_persisted,
    }
    if model_id is not None:
        result["model_id"] = model_id
    if seed_analysis_snapshot_id is not None:
        result["seed_analysis_snapshot_id"] = seed_analysis_snapshot_id
    return result


@activity.defn
def ontology_activity(
    payload: dict[str, Any],
    ontology_runner: OntologyRunner | None = None,
    workflow_event_writer: WorkflowEventWriter | None = None,
    workflow_status_writer: WorkflowRunStatusWriter | None = None,
) -> dict[str, Any]:
    context = AgentContext.model_validate(payload.get("context", payload))
    base = _base_payload(context, payload.get("upload_id") if isinstance(payload.get("upload_id"), str) else None)
    if not context.has_permission("seed_pipeline", "run"):
        return _error_result(
            base=base,
            code="FORBIDDEN",
            message="seed_pipeline run permission is required",
            extra={"stage": "story_ontology", "module_key": STORY_ONTOLOGY_MODULE_KEY},
        )
    try:
        workflow_event_writer = _resolved_workflow_event_writer(workflow_event_writer)
    except Exception:
        return _workflow_event_writer_resolution_failed_result(
            base=base,
            stage="story_ontology",
            module_key=STORY_ONTOLOGY_MODULE_KEY,
        )
    if workflow_status_writer is None:
        try:
            workflow_status_writer = _workflow_status_writer_from_env()
        except Exception:
            workflow_status_writer = _UnavailableWorkflowRunStatusWriter()
    runner = ontology_runner if ontology_runner is not None else _ontology_runner_from_env()
    if runner is None:
        return _ontology_failed_result(
            base=base,
            context=context,
            code="ONTOLOGY_RUNNER_UNCONFIGURED",
            message=(
                "story ontology requires an LLM Facility backed runner for "
                f"{STORY_ONTOLOGY_MODULE_KEY}"
            ),
            public_message="ontology runner is unconfigured",
            workflow_event_writer=workflow_event_writer,
            workflow_status_writer=workflow_status_writer,
        )
    try:
        ontology_result = runner.generate(context=context, module_key=STORY_ONTOLOGY_MODULE_KEY)
    except Exception as exc:
        return _ontology_failed_result(
            base=base,
            context=context,
            code="LLM_PROVIDER_ERROR",
            message=str(exc),
            public_message="story ontology generation failed",
            workflow_event_writer=workflow_event_writer,
            workflow_status_writer=workflow_status_writer,
        )
    if ontology_result.get("status") != "completed":
        error = ontology_result.get("error") if isinstance(ontology_result.get("error"), dict) else {}
        code = error.get("code") if isinstance(error.get("code"), str) else "LLM_PROVIDER_ERROR"
        message = error.get("message") if isinstance(error.get("message"), str) else "story ontology failed"
        return _ontology_failed_result(
            base=base,
            context=context,
            code=code,
            message=message,
            public_message=_public_ontology_error_message(code),
            workflow_event_writer=workflow_event_writer,
            workflow_status_writer=workflow_status_writer,
        )
    try:
        module_key = _optional_result_text(ontology_result, "module_key") or STORY_ONTOLOGY_MODULE_KEY
        if module_key != STORY_ONTOLOGY_MODULE_KEY:
            raise ValueError(f"module_key must be {STORY_ONTOLOGY_MODULE_KEY}")
        model_id = _optional_result_text(ontology_result, "model_id")
        ontology_snapshot_id = _required_text_value(
            ontology_result.get("ontology_snapshot_id"),
            "ontology_snapshot_id",
        )
        entity_type_count = _non_negative_int(ontology_result.get("entity_type_count", 0), "entity_type_count")
        relationship_type_count = _non_negative_int(
            ontology_result.get("relationship_type_count", 0),
            "relationship_type_count",
        )
        world_rule_type_count = _non_negative_int(
            ontology_result.get("world_rule_type_count", 0),
            "world_rule_type_count",
        )
    except Exception as exc:
        return _ontology_failed_result(
            base=base,
            context=context,
            code="SCHEMA_VALIDATION_FAILED",
            message=str(exc),
            public_message="ontology output schema validation failed",
            workflow_event_writer=workflow_event_writer,
            workflow_status_writer=workflow_status_writer,
        )
    event_persisted = _record_completed_ontology_event(
        context=context,
        model_id=model_id,
        ontology_snapshot_id=ontology_snapshot_id,
        entity_type_count=entity_type_count,
        relationship_type_count=relationship_type_count,
        world_rule_type_count=world_rule_type_count,
        workflow_event_writer=workflow_event_writer,
    )
    result: dict[str, Any] = {
        **base,
        "status": "completed",
        "stage": "story_ontology",
        "next_stage": "entity_resolution",
        "module_key": STORY_ONTOLOGY_MODULE_KEY,
        "ontology_snapshot_id": ontology_snapshot_id,
        "entity_type_count": entity_type_count,
        "relationship_type_count": relationship_type_count,
        "world_rule_type_count": world_rule_type_count,
        "stage_event_persisted": event_persisted,
    }
    if model_id is not None:
        result["model_id"] = model_id
    return result


@activity.defn
def entity_resolution_activity(
    payload: dict[str, Any],
    entity_resolution_runner: EntityResolutionRunner | None = None,
    workflow_event_writer: WorkflowEventWriter | None = None,
) -> dict[str, Any]:
    context = AgentContext.model_validate(payload.get("context", payload))
    base = _base_payload(context, payload.get("upload_id") if isinstance(payload.get("upload_id"), str) else None)
    if not context.has_permission("seed_pipeline", "run"):
        return _error_result(
            base=base,
            code="FORBIDDEN",
            message="seed_pipeline run permission is required",
            extra={"stage": "entity_resolution", "module_key": ENTITY_RESOLUTION_MODULE_KEY},
        )
    try:
        workflow_event_writer = _resolved_workflow_event_writer(workflow_event_writer)
    except Exception:
        return _workflow_event_writer_resolution_failed_result(
            base=base,
            stage="entity_resolution",
            module_key=ENTITY_RESOLUTION_MODULE_KEY,
        )
    runner = (
        entity_resolution_runner
        if entity_resolution_runner is not None
        else _entity_resolution_runner_from_env()
    )
    if runner is None:
        return _entity_resolution_failed_result(
            base=base,
            context=context,
            code="ENTITY_RESOLUTION_RUNNER_UNCONFIGURED",
            message=(
                "entity resolution requires an LLM Facility backed runner for "
                f"{ENTITY_RESOLUTION_MODULE_KEY}"
            ),
            public_message="entity resolution runner is unconfigured",
            workflow_event_writer=workflow_event_writer,
        )
    try:
        resolution_result = runner.resolve(context=context, module_key=ENTITY_RESOLUTION_MODULE_KEY)
    except Exception as exc:
        return _entity_resolution_failed_result(
            base=base,
            context=context,
            code="LLM_PROVIDER_ERROR",
            message=str(exc),
            public_message="entity resolution failed",
            workflow_event_writer=workflow_event_writer,
        )
    if resolution_result.get("status") != "completed":
        error = resolution_result.get("error") if isinstance(resolution_result.get("error"), dict) else {}
        code = error.get("code") if isinstance(error.get("code"), str) else "LLM_PROVIDER_ERROR"
        message = error.get("message") if isinstance(error.get("message"), str) else "entity resolution failed"
        return _entity_resolution_failed_result(
            base=base,
            context=context,
            code=code,
            message=message,
            public_message=_public_entity_resolution_error_message(code),
            workflow_event_writer=workflow_event_writer,
        )
    try:
        module_key = _optional_result_text(resolution_result, "module_key") or ENTITY_RESOLUTION_MODULE_KEY
        if module_key != ENTITY_RESOLUTION_MODULE_KEY:
            raise ValueError(f"module_key must be {ENTITY_RESOLUTION_MODULE_KEY}")
        model_id = _optional_result_text(resolution_result, "model_id")
        resolution_snapshot_id = _required_text_value(
            resolution_result.get("resolution_snapshot_id"),
            "resolution_snapshot_id",
        )
        merged_entity_count = _non_negative_int(
            resolution_result.get("merged_entity_count", 0),
            "merged_entity_count",
        )
        alias_count = _non_negative_int(resolution_result.get("alias_count", 0), "alias_count")
        conflict_count = _non_negative_int(resolution_result.get("conflict_count", 0), "conflict_count")
    except Exception as exc:
        return _entity_resolution_failed_result(
            base=base,
            context=context,
            code="SCHEMA_VALIDATION_FAILED",
            message=str(exc),
            public_message="entity resolution output schema validation failed",
            workflow_event_writer=workflow_event_writer,
        )
    event_persisted = _record_completed_entity_resolution_event(
        context=context,
        model_id=model_id,
        resolution_snapshot_id=resolution_snapshot_id,
        merged_entity_count=merged_entity_count,
        alias_count=alias_count,
        conflict_count=conflict_count,
        workflow_event_writer=workflow_event_writer,
    )
    result: dict[str, Any] = {
        **base,
        "status": "completed",
        "stage": "entity_resolution",
        "next_stage": "agent_profiles",
        "module_key": ENTITY_RESOLUTION_MODULE_KEY,
        "resolution_snapshot_id": resolution_snapshot_id,
        "merged_entity_count": merged_entity_count,
        "alias_count": alias_count,
        "conflict_count": conflict_count,
        "stage_event_persisted": event_persisted,
    }
    if model_id is not None:
        result["model_id"] = model_id
    return result


@activity.defn
def agent_profile_activity(
    payload: dict[str, Any],
    agent_profile_runner: AgentProfileRunner | None = None,
    workflow_event_writer: WorkflowEventWriter | None = None,
) -> dict[str, Any]:
    context = AgentContext.model_validate(payload.get("context", payload))
    base = _base_payload(context, payload.get("upload_id") if isinstance(payload.get("upload_id"), str) else None)
    if not context.has_permission("seed_pipeline", "run"):
        return _error_result(
            base=base,
            code="FORBIDDEN",
            message="seed_pipeline run permission is required",
            extra={"stage": "agent_profiles", "module_key": CHARACTER_AGENT_PROFILE_MODULE_KEY},
        )
    try:
        workflow_event_writer = _resolved_workflow_event_writer(workflow_event_writer)
    except Exception:
        return _workflow_event_writer_resolution_failed_result(
            base=base,
            stage="agent_profiles",
            module_key=CHARACTER_AGENT_PROFILE_MODULE_KEY,
        )
    runner = agent_profile_runner if agent_profile_runner is not None else _agent_profile_runner_from_env()
    if runner is None:
        return _agent_profile_failed_result(
            base=base,
            context=context,
            code="AGENT_PROFILE_RUNNER_UNCONFIGURED",
            message=(
                "character agent profiles require an LLM Facility backed runner for "
                f"{CHARACTER_AGENT_PROFILE_MODULE_KEY}"
            ),
            public_message="agent profile runner is unconfigured",
            workflow_event_writer=workflow_event_writer,
        )
    try:
        profile_result = runner.generate(context=context, module_key=CHARACTER_AGENT_PROFILE_MODULE_KEY)
    except Exception as exc:
        return _agent_profile_failed_result(
            base=base,
            context=context,
            code="LLM_PROVIDER_ERROR",
            message=str(exc),
            public_message="agent profile generation failed",
            workflow_event_writer=workflow_event_writer,
        )
    if profile_result.get("status") != "completed":
        error = profile_result.get("error") if isinstance(profile_result.get("error"), dict) else {}
        code = error.get("code") if isinstance(error.get("code"), str) else "LLM_PROVIDER_ERROR"
        message = error.get("message") if isinstance(error.get("message"), str) else "agent profile generation failed"
        return _agent_profile_failed_result(
            base=base,
            context=context,
            code=code,
            message=message,
            public_message=_public_agent_profile_error_message(code),
            workflow_event_writer=workflow_event_writer,
        )
    try:
        module_key = _optional_result_text(profile_result, "module_key") or CHARACTER_AGENT_PROFILE_MODULE_KEY
        if module_key != CHARACTER_AGENT_PROFILE_MODULE_KEY:
            raise ValueError(f"module_key must be {CHARACTER_AGENT_PROFILE_MODULE_KEY}")
        model_id = _optional_result_text(profile_result, "model_id")
        profile_snapshot_id = _required_text_value(
            profile_result.get("profile_snapshot_id"),
            "profile_snapshot_id",
        )
        profile_count = _non_negative_int(profile_result.get("profile_count", 0), "profile_count")
        memory_seed_count = _non_negative_int(profile_result.get("memory_seed_count", 0), "memory_seed_count")
        relationship_view_count = _non_negative_int(
            profile_result.get("relationship_view_count", 0),
            "relationship_view_count",
        )
    except Exception as exc:
        return _agent_profile_failed_result(
            base=base,
            context=context,
            code="SCHEMA_VALIDATION_FAILED",
            message=str(exc),
            public_message="agent profile output schema validation failed",
            workflow_event_writer=workflow_event_writer,
        )
    event_persisted = _record_completed_agent_profile_event(
        context=context,
        model_id=model_id,
        profile_snapshot_id=profile_snapshot_id,
        profile_count=profile_count,
        memory_seed_count=memory_seed_count,
        relationship_view_count=relationship_view_count,
        workflow_event_writer=workflow_event_writer,
    )
    result: dict[str, Any] = {
        **base,
        "status": "completed",
        "stage": "agent_profiles",
        "next_stage": "archive_candidates",
        "module_key": CHARACTER_AGENT_PROFILE_MODULE_KEY,
        "profile_snapshot_id": profile_snapshot_id,
        "profile_count": profile_count,
        "memory_seed_count": memory_seed_count,
        "relationship_view_count": relationship_view_count,
        "stage_event_persisted": event_persisted,
    }
    if model_id is not None:
        result["model_id"] = model_id
    return result


@activity.defn
def archive_candidate_activity(
    payload: dict[str, Any],
    archive_candidate_runner: ArchiveCandidateRunner | None = None,
    workflow_event_writer: WorkflowEventWriter | None = None,
) -> dict[str, Any]:
    context = AgentContext.model_validate(payload.get("context", payload))
    base = _base_payload(context, payload.get("upload_id") if isinstance(payload.get("upload_id"), str) else None)
    if not context.has_permission("seed_pipeline", "run"):
        return _error_result(
            base=base,
            code="FORBIDDEN",
            message="seed_pipeline run permission is required",
            extra={"stage": "archive_candidates", "module_key": NARRATIVE_ARCHIVES_MODULE_KEY},
        )
    try:
        workflow_event_writer = _resolved_workflow_event_writer(workflow_event_writer)
    except Exception:
        return _workflow_event_writer_resolution_failed_result(
            base=base,
            stage="archive_candidates",
            module_key=NARRATIVE_ARCHIVES_MODULE_KEY,
        )
    runner = (
        archive_candidate_runner
        if archive_candidate_runner is not None
        else _archive_candidate_runner_from_env()
    )
    if runner is None:
        return _archive_candidate_failed_result(
            base=base,
            context=context,
            code="ARCHIVE_CANDIDATE_RUNNER_UNCONFIGURED",
            message=(
                "archive candidates require an LLM Facility backed runner for "
                f"{NARRATIVE_ARCHIVES_MODULE_KEY}"
            ),
            public_message="archive candidate runner is unconfigured",
            workflow_event_writer=workflow_event_writer,
        )
    try:
        archive_result = runner.generate(context=context, module_key=NARRATIVE_ARCHIVES_MODULE_KEY)
    except Exception as exc:
        return _archive_candidate_failed_result(
            base=base,
            context=context,
            code="LLM_PROVIDER_ERROR",
            message=str(exc),
            public_message="archive candidate generation failed",
            workflow_event_writer=workflow_event_writer,
        )
    if archive_result.get("status") != "completed":
        error = archive_result.get("error") if isinstance(archive_result.get("error"), dict) else {}
        code = error.get("code") if isinstance(error.get("code"), str) else "LLM_PROVIDER_ERROR"
        message = error.get("message") if isinstance(error.get("message"), str) else "archive candidate generation failed"
        return _archive_candidate_failed_result(
            base=base,
            context=context,
            code=code,
            message=message,
            public_message=_public_archive_candidate_error_message(code),
            workflow_event_writer=workflow_event_writer,
        )
    try:
        module_key = _optional_result_text(archive_result, "module_key") or NARRATIVE_ARCHIVES_MODULE_KEY
        if module_key != NARRATIVE_ARCHIVES_MODULE_KEY:
            raise ValueError(f"module_key must be {NARRATIVE_ARCHIVES_MODULE_KEY}")
        model_id = _optional_result_text(archive_result, "model_id")
        archive_candidate_batch_id = _required_text_value(
            archive_result.get("archive_candidate_batch_id"),
            "archive_candidate_batch_id",
        )
        candidate_count = _non_negative_int(archive_result.get("candidate_count", 0), "candidate_count")
        archive_entity_candidate_count = _non_negative_int(
            archive_result.get("archive_entity_candidate_count", 0),
            "archive_entity_candidate_count",
        )
        memory_candidate_count = _non_negative_int(
            archive_result.get("memory_candidate_count", 0),
            "memory_candidate_count",
        )
    except Exception as exc:
        return _archive_candidate_failed_result(
            base=base,
            context=context,
            code="SCHEMA_VALIDATION_FAILED",
            message=str(exc),
            public_message="archive candidate output schema validation failed",
            workflow_event_writer=workflow_event_writer,
        )
    event_persisted = _record_completed_archive_candidate_event(
        context=context,
        model_id=model_id,
        archive_candidate_batch_id=archive_candidate_batch_id,
        candidate_count=candidate_count,
        archive_entity_candidate_count=archive_entity_candidate_count,
        memory_candidate_count=memory_candidate_count,
        workflow_event_writer=workflow_event_writer,
    )
    result: dict[str, Any] = {
        **base,
        "status": "completed",
        "stage": "archive_candidates",
        "next_stage": "index_assets",
        "module_key": NARRATIVE_ARCHIVES_MODULE_KEY,
        "archive_candidate_batch_id": archive_candidate_batch_id,
        "candidate_count": candidate_count,
        "archive_entity_candidate_count": archive_entity_candidate_count,
        "memory_candidate_count": memory_candidate_count,
        "stage_event_persisted": event_persisted,
    }
    if model_id is not None:
        result["model_id"] = model_id
    return result


@activity.defn
def index_assets_activity(
    payload: dict[str, Any],
    asset_indexer: AssetIndexer | None = None,
    workflow_event_writer: WorkflowEventWriter | None = None,
) -> dict[str, Any]:
    context = AgentContext.model_validate(payload.get("context", payload))
    base = _base_payload(context, payload.get("upload_id") if isinstance(payload.get("upload_id"), str) else None)
    if not context.has_permission("seed_pipeline", "run"):
        return _error_result(
            base=base,
            code="FORBIDDEN",
            message="seed_pipeline run permission is required",
            extra={"stage": "index_assets"},
        )
    try:
        workflow_event_writer = _resolved_workflow_event_writer(workflow_event_writer)
    except Exception:
        return _workflow_event_writer_resolution_failed_result(
            base=base,
            stage="index_assets",
        )
    indexer = asset_indexer if asset_indexer is not None else _asset_indexer_from_env()
    if indexer is None:
        return _index_assets_failed_result(
            base=base,
            context=context,
            code="ASSET_INDEXER_UNCONFIGURED",
            message="asset indexing requires a configured asset indexer",
            public_message="asset indexer is unconfigured",
            workflow_event_writer=workflow_event_writer,
        )
    try:
        index_result = indexer.index(context=context)
    except Exception as exc:
        return _index_assets_failed_result(
            base=base,
            context=context,
            code="ASSET_INDEX_FAILED",
            message=str(exc),
            public_message="asset indexing failed",
            workflow_event_writer=workflow_event_writer,
        )
    if index_result.get("status") != "completed":
        error = index_result.get("error") if isinstance(index_result.get("error"), dict) else {}
        code = error.get("code") if isinstance(error.get("code"), str) else "ASSET_INDEX_FAILED"
        message = error.get("message") if isinstance(error.get("message"), str) else "asset indexing failed"
        return _index_assets_failed_result(
            base=base,
            context=context,
            code=code,
            message=message,
            public_message=_public_index_assets_error_message(code),
            workflow_event_writer=workflow_event_writer,
        )
    try:
        asset_index_batch_id = _required_text_value(
            index_result.get("asset_index_batch_id"),
            "asset_index_batch_id",
        )
        indexed_asset_count = _non_negative_int(index_result.get("indexed_asset_count", 0), "indexed_asset_count")
        search_document_count = _non_negative_int(
            index_result.get("search_document_count", 0),
            "search_document_count",
        )
        embedding_count = _non_negative_int(index_result.get("embedding_count", 0), "embedding_count")
    except Exception as exc:
        return _index_assets_failed_result(
            base=base,
            context=context,
            code="SCHEMA_VALIDATION_FAILED",
            message=str(exc),
            public_message="asset index output schema validation failed",
            workflow_event_writer=workflow_event_writer,
        )
    event_persisted = _record_completed_index_assets_event(
        context=context,
        asset_index_batch_id=asset_index_batch_id,
        indexed_asset_count=indexed_asset_count,
        search_document_count=search_document_count,
        embedding_count=embedding_count,
        workflow_event_writer=workflow_event_writer,
    )
    return {
        **base,
        "status": "completed",
        "stage": "index_assets",
        "next_stage": "finalize",
        "asset_index_batch_id": asset_index_batch_id,
        "indexed_asset_count": indexed_asset_count,
        "search_document_count": search_document_count,
        "embedding_count": embedding_count,
        "stage_event_persisted": event_persisted,
    }


@activity.defn
def finalize_seed_activity(
    payload: dict[str, Any],
    project_readiness_updater: ProjectReadinessUpdater | None = None,
    workflow_event_writer: WorkflowEventWriter | None = None,
    workflow_status_writer: WorkflowRunStatusWriter | None = None,
) -> dict[str, Any]:
    context = AgentContext.model_validate(payload.get("context", payload))
    base = _base_payload(context, payload.get("upload_id") if isinstance(payload.get("upload_id"), str) else None)
    if not context.has_permission("seed_pipeline", "run"):
        return _error_result(
            base=base,
            code="FORBIDDEN",
            message="seed_pipeline run permission is required",
            extra={"stage": "finalize"},
        )
    try:
        workflow_event_writer = _resolved_workflow_event_writer(workflow_event_writer)
    except Exception:
        return _workflow_event_writer_resolution_failed_result(
            base=base,
            stage="finalize",
        )
    if workflow_status_writer is None:
        try:
            workflow_status_writer = _workflow_status_writer_from_env()
        except Exception:
            return _error_result(
                base=base,
                code="WORKFLOW_STATUS_WRITE_FAILED",
                message="seed workflow status write failed",
                extra={"stage": "finalize"},
            )
    updater = (
        project_readiness_updater
        if project_readiness_updater is not None
        else _project_readiness_updater_from_env()
    )
    if updater is None:
        return _finalize_seed_failed_result(
            base=base,
            context=context,
            code="PROJECT_READINESS_UPDATER_UNCONFIGURED",
            message="project readiness update requires a configured updater",
            public_message="project readiness updater is unconfigured",
            workflow_event_writer=workflow_event_writer,
            workflow_status_writer=workflow_status_writer,
        )
    try:
        readiness_result = updater.update(context=context)
    except Exception as exc:
        return _finalize_seed_failed_result(
            base=base,
            context=context,
            code="PROJECT_READINESS_UPDATE_FAILED",
            message=str(exc),
            public_message="project readiness update failed",
            workflow_event_writer=workflow_event_writer,
            workflow_status_writer=workflow_status_writer,
        )
    if readiness_result.get("status") != "completed":
        error = readiness_result.get("error") if isinstance(readiness_result.get("error"), dict) else {}
        code = error.get("code") if isinstance(error.get("code"), str) else "PROJECT_READINESS_UPDATE_FAILED"
        message = (
            error.get("message")
            if isinstance(error.get("message"), str)
            else "project readiness update failed"
        )
        return _finalize_seed_failed_result(
            base=base,
            context=context,
            code=code,
            message=message,
            public_message=_public_finalize_error_message(code),
            workflow_event_writer=workflow_event_writer,
            workflow_status_writer=workflow_status_writer,
        )
    try:
        project_readiness_snapshot_id = _required_text_value(
            readiness_result.get("project_readiness_snapshot_id"),
            "project_readiness_snapshot_id",
        )
        ready_asset_count = _non_negative_int(readiness_result.get("ready_asset_count", 0), "ready_asset_count")
        ready_entity_count = _non_negative_int(readiness_result.get("ready_entity_count", 0), "ready_entity_count")
        ready_relationship_count = _non_negative_int(
            readiness_result.get("ready_relationship_count", 0),
            "ready_relationship_count",
        )
        ready_world_rule_count = _non_negative_int(
            readiness_result.get("ready_world_rule_count", 0),
            "ready_world_rule_count",
        )
    except Exception as exc:
        return _finalize_seed_failed_result(
            base=base,
            context=context,
            code="SCHEMA_VALIDATION_FAILED",
            message=str(exc),
            public_message="project readiness output schema validation failed",
            workflow_event_writer=workflow_event_writer,
            workflow_status_writer=workflow_status_writer,
        )
    event_persisted = _record_completed_finalize_event(
        context=context,
        project_readiness_snapshot_id=project_readiness_snapshot_id,
        ready_asset_count=ready_asset_count,
        ready_entity_count=ready_entity_count,
        ready_relationship_count=ready_relationship_count,
        ready_world_rule_count=ready_world_rule_count,
        workflow_event_writer=workflow_event_writer,
    )
    result = {
        **base,
        "status": "completed",
        "stage": "finalize",
        "project_readiness_snapshot_id": project_readiness_snapshot_id,
        "ready_asset_count": ready_asset_count,
        "ready_entity_count": ready_entity_count,
        "ready_relationship_count": ready_relationship_count,
        "ready_world_rule_count": ready_world_rule_count,
        "stage_event_persisted": event_persisted,
    }
    try:
        workflow_status_persisted = _mark_seed_workflow_completed(
            workflow_status_writer,
            context=context,
            result=result,
        )
    except Exception:
        return _error_result(
            base=base,
            code="WORKFLOW_STATUS_WRITE_FAILED",
            message="seed workflow status write failed",
            extra={"stage": "finalize"},
        )
    if workflow_status_persisted:
        result["workflow_status_persisted"] = workflow_status_persisted
    return result


@activity.defn
def seed_pipeline_activity(
    payload: dict[str, Any],
    workflow_event_writer: WorkflowEventWriter | None = None,
    workflow_status_writer: WorkflowRunStatusWriter | None = None,
) -> dict[str, Any]:
    context = AgentContext.model_validate(payload.get("context", payload))
    upload_id = payload.get("upload_id")
    base = _base_payload(context, upload_id if isinstance(upload_id, str) else None)
    if not context.has_permission("seed_pipeline", "run"):
        return {
            **base,
            "status": "failed",
            "error": {
                "code": "FORBIDDEN",
                "message": "seed_pipeline run permission is required",
            },
        }
    if not isinstance(upload_id, str) or not upload_id.strip():
        return {
            **base,
            "status": "failed",
            "error": {
                "code": "VALIDATION_FAILED",
                "message": "upload_id is required",
            },
        }
    normalized_upload_id = upload_id.strip()
    try:
        writer = _resolved_workflow_event_writer(workflow_event_writer)
        stage_event_persisted = _record_pending_stage_event(
            context=context,
            upload_id=normalized_upload_id,
            workflow_event_writer=writer,
        )
    except Exception:
        return {
            **base,
            "upload_id": normalized_upload_id,
            "status": "failed",
            "error": {
                "code": "WORKFLOW_EVENT_WRITE_FAILED",
                "message": "workflow event write failed",
            },
        }
    if workflow_status_writer is None:
        try:
            workflow_status_writer = _workflow_status_writer_from_env()
        except Exception:
            return {
                **base,
                "upload_id": normalized_upload_id,
                "status": "failed",
                "error": {
                    "code": "WORKFLOW_STATUS_WRITE_FAILED",
                    "message": "seed workflow status write failed",
                },
            }
    try:
        workflow_status_persisted = _mark_seed_workflow_running(
            workflow_status_writer,
            context=context,
        )
    except Exception:
        return {
            **base,
            "upload_id": normalized_upload_id,
            "status": "failed",
            "error": {
                "code": "WORKFLOW_STATUS_WRITE_FAILED",
                "message": "seed workflow status write failed",
            },
        }
    return {
        **base,
        "upload_id": normalized_upload_id,
        "status": "queued",
        "next_stage": "parse_file",
        "stage_event_persisted": stage_event_persisted,
        "workflow_status_persisted": workflow_status_persisted,
        "message": "Seed pipeline skeleton accepted the run; parse_file activity is pending.",
    }


@activity.defn
def seed_segment_retry_activity(
    payload: dict[str, Any],
    retry_store: SeedSegmentRetryStore | None = None,
    llm_reader: SequentialReadingReader | None = None,
    reading_notes_writer: ReadingNotesWriter | None = None,
    retry_status_writer: SeedSegmentRetryStatusWriter | None = None,
    workflow_event_writer: WorkflowEventWriter | None = None,
) -> dict[str, Any]:
    context = AgentContext.model_validate(payload.get("context", payload))
    segment_ids = _normalized_segment_retry_ids(payload.get("segment_ids"))
    retry_attempt_id_value = payload.get("retry_attempt_id")
    retry_attempt_id = (
        retry_attempt_id_value.strip()
        if isinstance(retry_attempt_id_value, str) and retry_attempt_id_value.strip()
        else None
    )
    worker_attempt = _segment_retry_worker_attempt()
    error_code = "SEED_SEGMENT_RETRY_RUNNER_UNCONFIGURED"
    error_message = "seed segment retry runner is not configured"
    if context.workflow_type != "seed_pipeline":
        return {
            "stage": "segment_retry",
            "status": "failed",
            "requested_count": len(segment_ids),
            "error": {
                "code": "VALIDATION_FAILED",
                "message": "seed segment retry requires seed_pipeline workflow context",
            },
        }
    if not context.has_permission("seed_pipeline", "run"):
        return {
            "stage": "segment_retry",
            "status": "failed",
            "requested_count": len(segment_ids),
            "error": {
                "code": "FORBIDDEN",
                "message": "seed_pipeline run permission is required",
            },
        }
    if not segment_ids:
        return {
            "stage": "segment_retry",
            "status": "failed",
            "requested_count": 0,
            "error": {
                "code": "VALIDATION_FAILED",
                "message": "segment_ids are required",
            },
        }

    try:
        writer = _resolved_workflow_event_writer(workflow_event_writer)
    except Exception:
        return {
            "stage": "segment_retry",
            "status": "failed",
            "requested_count": len(segment_ids),
            "error": {
                "code": "WORKFLOW_EVENT_WRITE_FAILED",
                "message": "workflow event write failed",
            },
        }

    if retry_store is None:
        try:
            retry_store = _seed_segment_retry_store_from_env()
        except Exception:
            return _segment_retry_failed_result(
                context=context,
                requested_count=len(segment_ids),
                segment_count=None,
                code="SEED_SEGMENT_RETRY_STORE_UNCONFIGURED",
                message="seed segment retry store is not configured",
                retry_store=None,
                segment_ids=segment_ids,
                workflow_event_writer=writer,
            )

    if retry_store is not None:
        try:
            claimed_segments = retry_store.claim_seed_segment_retries(
                context=context,
                segment_ids=segment_ids,
                retry_attempt_id=retry_attempt_id,
                worker_attempt=worker_attempt,
            )
        except LLMFacilityError as exc:
            return _segment_retry_failed_result(
                context=context,
                requested_count=len(segment_ids),
                segment_count=None,
                code=exc.code,
                message=exc.message,
                retry_store=None,
                segment_ids=segment_ids,
                workflow_event_writer=writer,
            )
        except Exception:
            return _segment_retry_failed_result(
                context=context,
                requested_count=len(segment_ids),
                segment_count=None,
                code="SEED_SEGMENT_RETRY_CLAIM_FAILED",
                message="seed segment retry claim failed",
                retry_store=None,
                segment_ids=segment_ids,
                workflow_event_writer=writer,
            )
        if not claimed_segments:
            return _segment_retry_failed_result(
                context=context,
                requested_count=len(segment_ids),
                segment_count=0,
                code="SEED_SEGMENT_RETRY_REQUEST_NOT_FOUND",
                message="seed segment retry request not found",
                retry_store=None,
                segment_ids=segment_ids,
                workflow_event_writer=writer,
            )
        try:
            segment_refs = [_sanitize_segment_reference(segment) for segment in claimed_segments]
            _validate_segment_retry_claims(segment_refs=segment_refs, segment_ids=segment_ids)
        except LookupError:
            return _segment_retry_failed_result(
                context=context,
                requested_count=len(segment_ids),
                segment_count=len(claimed_segments),
                code="SEED_SEGMENT_RETRY_REQUEST_NOT_FOUND",
                message="seed segment retry request not found",
                retry_store=None,
                segment_ids=segment_ids,
                workflow_event_writer=writer,
            )
        except Exception:
            return _segment_retry_failed_result(
                context=context,
                requested_count=len(segment_ids),
                segment_count=len(claimed_segments),
                code="SCHEMA_VALIDATION_FAILED",
                message="segment retry segment refs are invalid",
                retry_store=retry_store,
                segment_ids=segment_ids,
                workflow_event_writer=writer,
                retry_attempt_id=retry_attempt_id,
                worker_attempt=worker_attempt,
            )
        atomic_notes_completion_writer = getattr(
            retry_store,
            "complete_seed_segment_retry_notes",
            None,
        )
        notes_writer: ReadingNotesWriter | None = None
        if retry_attempt_id is None or not callable(atomic_notes_completion_writer):
            try:
                notes_writer = (
                    reading_notes_writer
                    if reading_notes_writer is not None
                    else _reading_notes_writer_from_env()
                )
            except Exception:
                return _segment_retry_failed_result(
                    context=context,
                    requested_count=len(segment_ids),
                    segment_count=len(segment_refs),
                    code="READING_NOTES_WRITER_UNCONFIGURED",
                    message="reading notes writer is unconfigured",
                    retry_store=retry_store,
                    segment_ids=segment_ids,
                    workflow_event_writer=writer,
                    retry_attempt_id=retry_attempt_id,
                    worker_attempt=worker_attempt,
                )
            if notes_writer is None:
                return _segment_retry_failed_result(
                    context=context,
                    requested_count=len(segment_ids),
                    segment_count=len(segment_refs),
                    code="READING_NOTES_WRITER_UNCONFIGURED",
                    message="reading notes writer is unconfigured",
                    retry_store=retry_store,
                    segment_ids=segment_ids,
                    workflow_event_writer=writer,
                    retry_attempt_id=retry_attempt_id,
                    worker_attempt=worker_attempt,
                )
        if llm_reader is not None:
            reader = llm_reader
        else:
            try:
                reader = _sequential_reader_from_env()
            except LLMFacilityError as exc:
                return _segment_retry_failed_result(
                    context=context,
                    requested_count=len(segment_ids),
                    segment_count=len(segment_refs),
                    code=exc.code,
                    message=exc.message,
                    retry_store=retry_store,
                    segment_ids=segment_ids,
                    workflow_event_writer=writer,
                    retry_attempt_id=retry_attempt_id,
                    worker_attempt=worker_attempt,
                )
            except Exception:
                return _segment_retry_failed_result(
                    context=context,
                    requested_count=len(segment_ids),
                    segment_count=len(segment_refs),
                    code="LLM_READER_UNCONFIGURED",
                    message="LLM reader is unconfigured",
                    retry_store=retry_store,
                    segment_ids=segment_ids,
                    workflow_event_writer=writer,
                    retry_attempt_id=retry_attempt_id,
                    worker_attempt=worker_attempt,
                )
        if reader is None:
            return _segment_retry_failed_result(
                context=context,
                requested_count=len(segment_ids),
                segment_count=len(segment_refs),
                code="LLM_READER_UNCONFIGURED",
                message="LLM reader is unconfigured",
                retry_store=retry_store,
                segment_ids=segment_ids,
                workflow_event_writer=writer,
                retry_attempt_id=retry_attempt_id,
                worker_attempt=worker_attempt,
            )
        try:
            reading_result = reader.read_segments(
                context=context,
                module_key="sequential_reading",
                segments=segment_refs,
            )
        except LLMFacilityError as exc:
            return _segment_retry_failed_result(
                context=context,
                requested_count=len(segment_ids),
                segment_count=len(segment_refs),
                code=exc.code,
                message=exc.message,
                retry_store=retry_store,
                segment_ids=segment_ids,
                workflow_event_writer=writer,
                retry_attempt_id=retry_attempt_id,
                worker_attempt=worker_attempt,
            )
        except Exception:
            return _segment_retry_failed_result(
                context=context,
                requested_count=len(segment_ids),
                segment_count=len(segment_refs),
                code="LLM_PROVIDER_ERROR",
                message="sequential reading provider failed",
                retry_store=retry_store,
                segment_ids=segment_ids,
                workflow_event_writer=writer,
                retry_attempt_id=retry_attempt_id,
                worker_attempt=worker_attempt,
            )
        if not isinstance(reading_result, dict):
            return _segment_retry_failed_result(
                context=context,
                requested_count=len(segment_ids),
                segment_count=len(segment_refs),
                code="SCHEMA_VALIDATION_FAILED",
                message="segment retry output schema validation failed",
                retry_store=retry_store,
                segment_ids=segment_ids,
                workflow_event_writer=writer,
                retry_attempt_id=retry_attempt_id,
                worker_attempt=worker_attempt,
            )
        if reading_result.get("status") != "completed":
            error = reading_result.get("error") if isinstance(reading_result.get("error"), dict) else {}
            code = error.get("code") if isinstance(error.get("code"), str) else "LLM_PROVIDER_ERROR"
            message = error.get("message") if isinstance(error.get("message"), str) else "sequential reading failed"
            return _segment_retry_failed_result(
                context=context,
                requested_count=len(segment_ids),
                segment_count=len(segment_refs),
                code=code,
                message=message,
                retry_store=retry_store,
                segment_ids=segment_ids,
                workflow_event_writer=writer,
                retry_attempt_id=retry_attempt_id,
                worker_attempt=worker_attempt,
            )
        try:
            validated_result = _validated_sequential_reading_result(
                reading_result,
                segment_refs=segment_refs,
                require_all_segments=True,
            )
        except ValueError:
            return _segment_retry_failed_result(
                context=context,
                requested_count=len(segment_ids),
                segment_count=len(segment_refs),
                code="SCHEMA_VALIDATION_FAILED",
                message="segment retry output schema validation failed",
                retry_store=retry_store,
                segment_ids=segment_ids,
                workflow_event_writer=writer,
                retry_attempt_id=retry_attempt_id,
                worker_attempt=worker_attempt,
            )
        notes = validated_result["notes"]
        if retry_attempt_id is not None and callable(atomic_notes_completion_writer):
            try:
                atomic_notes_completion_writer(
                    context=context,
                    segment_ids=segment_ids,
                    retry_attempt_id=retry_attempt_id,
                    worker_attempt=worker_attempt,
                    pass_id=validated_result["pass_id"],
                    module_key=validated_result["module_key"],
                    model_id=validated_result["model_id"],
                    notes=notes,
                )
            except LLMFacilityError as exc:
                return _segment_retry_failed_result(
                    context=context,
                    requested_count=len(segment_ids),
                    segment_count=len(segment_refs),
                    code=exc.code,
                    message=exc.message,
                    retry_store=retry_store,
                    segment_ids=segment_ids,
                    workflow_event_writer=writer,
                    retry_attempt_id=retry_attempt_id,
                    worker_attempt=worker_attempt,
                )
            except Exception:
                return _segment_retry_failed_result(
                    context=context,
                    requested_count=len(segment_ids),
                    segment_count=len(segment_refs),
                    code="SEED_SEGMENT_RETRY_COMPLETION_WRITE_FAILED",
                    message="seed segment retry completion write failed",
                    retry_store=retry_store,
                    segment_ids=segment_ids,
                    workflow_event_writer=writer,
                    retry_attempt_id=retry_attempt_id,
                    worker_attempt=worker_attempt,
                )
            return {
                "stage": "segment_retry",
                "status": "completed",
                "requested_count": len(segment_ids),
                "segment_count": len(segment_refs),
                "note_count": len(notes),
                "retry_status_persisted": True,
                "stage_event_persisted": True,
            }
        retry_metadata: dict[str, Any] = {
            "retry": True,
            "last_retry_segment_count": len(segment_refs),
        }
        if retry_attempt_id is not None:
            retry_metadata["last_retry_attempt_id"] = retry_attempt_id
        try:
            if notes_writer is None:
                raise RuntimeError("reading notes writer is unconfigured")
            notes_writer.record_reading_notes(
                context=context,
                pass_id=validated_result["pass_id"],
                pass_type="sequential_reading",
                status="completed",
                module_key=validated_result["module_key"],
                model_id=validated_result["model_id"],
                notes=notes,
                metadata_jsonb=retry_metadata,
            )
        except Exception:
            return _segment_retry_failed_result(
                context=context,
                requested_count=len(segment_ids),
                segment_count=len(segment_refs),
                code="READING_NOTES_WRITE_FAILED",
                message="reading notes write failed",
                retry_store=retry_store,
                segment_ids=segment_ids,
                workflow_event_writer=writer,
                retry_attempt_id=retry_attempt_id,
                worker_attempt=worker_attempt,
            )
        atomic_completion_writer = getattr(retry_store, "complete_seed_segment_retries", None)
        if retry_attempt_id is not None and callable(atomic_completion_writer):
            try:
                atomic_completion_writer(
                    context=context,
                    segment_ids=segment_ids,
                    retry_attempt_id=retry_attempt_id,
                    worker_attempt=worker_attempt,
                    requested_count=len(segment_ids),
                    segment_count=len(segment_refs),
                    note_count=len(notes),
                    model_id=validated_result["model_id"],
                )
            except Exception:
                return _segment_retry_failed_result(
                    context=context,
                    requested_count=len(segment_ids),
                    segment_count=len(segment_refs),
                    code="SEED_SEGMENT_RETRY_COMPLETION_WRITE_FAILED",
                    message="seed segment retry completion write failed",
                    retry_store=retry_store,
                    segment_ids=segment_ids,
                    workflow_event_writer=writer,
                    retry_attempt_id=retry_attempt_id,
                    worker_attempt=worker_attempt,
                )
            retry_status_persisted = True
            stage_event_persisted = True
        else:
            try:
                retry_status_persisted = _mark_seed_segment_retries(
                    retry_store,
                    context=context,
                    segment_ids=segment_ids,
                    retry_attempt_id=retry_attempt_id,
                    worker_attempt=worker_attempt,
                    status="completed",
                )
            except Exception:
                return {
                    "stage": "segment_retry",
                    "status": "failed",
                    "requested_count": len(segment_ids),
                    "segment_count": len(segment_refs),
                    "error": {
                        "code": "SEED_SEGMENT_RETRY_STATUS_WRITE_FAILED",
                        "message": "seed segment retry status write failed",
                    },
                    "retry_status_persisted": False,
                    "stage_event_persisted": False,
                }
            try:
                stage_event_persisted = _record_completed_segment_retry_event(
                    context=context,
                    requested_count=len(segment_ids),
                    segment_count=len(segment_refs),
                    note_count=len(notes),
                    model_id=validated_result["model_id"],
                    workflow_event_writer=writer,
                )
            except Exception:
                return {
                    "stage": "segment_retry",
                    "status": "failed",
                    "requested_count": len(segment_ids),
                    "segment_count": len(segment_refs),
                    "error": {
                        "code": "WORKFLOW_EVENT_WRITE_FAILED",
                        "message": "workflow event write failed",
                    },
                    "retry_status_persisted": retry_status_persisted,
                    "stage_event_persisted": False,
                }
        return {
            "stage": "segment_retry",
            "status": "completed",
            "requested_count": len(segment_ids),
            "segment_count": len(segment_refs),
            "note_count": len(notes),
            "retry_status_persisted": retry_status_persisted,
            "stage_event_persisted": stage_event_persisted,
        }

    retry_status_persisted = False
    try:
        retry_status_persisted = _mark_seed_segment_retries(
            retry_status_writer,
            context=context,
            segment_ids=segment_ids,
            status="failed",
            code=error_code,
            message=error_message,
        )
    except Exception:
        return {
            "stage": "segment_retry",
            "status": "failed",
            "requested_count": len(segment_ids),
            "error": {
                "code": "SEED_SEGMENT_RETRY_STATUS_WRITE_FAILED",
                "message": "seed segment retry status write failed",
            },
            "retry_status_persisted": False,
        }

    try:
        stage_event_persisted = _record_failed_segment_retry_event(
            context=context,
            requested_count=len(segment_ids),
            error_code=error_code,
            error_message=error_message,
            workflow_event_writer=writer,
        )
    except Exception:
        return {
            "stage": "segment_retry",
            "status": "failed",
            "requested_count": len(segment_ids),
            "error": {
                "code": "WORKFLOW_EVENT_WRITE_FAILED",
                "message": "workflow event write failed",
            },
            "retry_status_persisted": retry_status_persisted,
        }

    return {
        "stage": "segment_retry",
        "status": "failed",
        "requested_count": len(segment_ids),
        "error": {
            "code": error_code,
            "message": error_message,
        },
        "retry_status_persisted": retry_status_persisted,
        "stage_event_persisted": stage_event_persisted,
    }


@workflow.defn
class SeedSegmentRetryWorkflow:
    @workflow.run
    async def run(self, payload: dict[str, Any]) -> dict[str, Any]:
        return await workflow.execute_activity(
            seed_segment_retry_activity,
            payload,
            start_to_close_timeout=timedelta(minutes=10),
        )


@workflow.defn
class SeedPipelineWorkflow:
    @workflow.run
    async def run(self, payload: dict[str, Any]) -> dict[str, Any]:
        result = await workflow.execute_activity(
            seed_pipeline_activity,
            payload,
            start_to_close_timeout=timedelta(seconds=30),
        )
        if result.get("status") != "queued" or not _payload_has_parse_source(payload):
            return result
        parse_result = await workflow.execute_activity(
            parse_file_activity,
            payload,
            start_to_close_timeout=timedelta(minutes=10),
        )
        if parse_result.get("status") != "completed":
            return parse_result
        segment_result = await workflow.execute_activity(
            segment_text_activity,
            _segment_payload_from_parse(payload, parse_result),
            start_to_close_timeout=timedelta(minutes=10),
        )
        if segment_result.get("status") != "completed":
            return segment_result
        sequential_result = await workflow.execute_activity(
            sequential_reading_activity,
            _sequential_payload_from_segment(payload, segment_result),
            start_to_close_timeout=timedelta(minutes=30),
        )
        if sequential_result.get("status") != "completed":
            return sequential_result
        runtime_facts_result = await workflow.execute_activity(
            persist_runtime_facts_activity,
            _runtime_facts_payload_from_sequential(payload),
            start_to_close_timeout=timedelta(minutes=10),
        )
        if runtime_facts_result.get("status") != "completed":
            return runtime_facts_result
        global_aggregation_result = await workflow.execute_activity(
            global_aggregation_activity,
            _global_aggregation_payload_from_runtime_facts(payload, runtime_facts_result),
            start_to_close_timeout=timedelta(minutes=20),
        )
        if global_aggregation_result.get("status") != "completed":
            return global_aggregation_result
        ontology_result = await workflow.execute_activity(
            ontology_activity,
            _ontology_payload_from_global_aggregation(payload, global_aggregation_result),
            start_to_close_timeout=timedelta(minutes=20),
        )
        if ontology_result.get("status") != "completed":
            return ontology_result
        entity_resolution_result = await workflow.execute_activity(
            entity_resolution_activity,
            _entity_resolution_payload_from_ontology(payload, ontology_result),
            start_to_close_timeout=timedelta(minutes=20),
        )
        if entity_resolution_result.get("status") != "completed":
            return entity_resolution_result
        agent_profile_result = await workflow.execute_activity(
            agent_profile_activity,
            _agent_profile_payload_from_entity_resolution(payload, entity_resolution_result),
            start_to_close_timeout=timedelta(minutes=20),
        )
        if agent_profile_result.get("status") != "completed":
            return agent_profile_result
        archive_candidate_result = await workflow.execute_activity(
            archive_candidate_activity,
            _archive_candidate_payload_from_agent_profile(payload, agent_profile_result),
            start_to_close_timeout=timedelta(minutes=20),
        )
        if archive_candidate_result.get("status") != "completed":
            return archive_candidate_result
        index_assets_result = await workflow.execute_activity(
            index_assets_activity,
            _index_assets_payload_from_archive_candidate(payload, archive_candidate_result),
            start_to_close_timeout=timedelta(minutes=20),
        )
        if index_assets_result.get("status") != "completed":
            return index_assets_result
        return await workflow.execute_activity(
            finalize_seed_activity,
            _finalize_payload_from_index_assets(payload, index_assets_result),
            start_to_close_timeout=timedelta(minutes=10),
        )


def run_seed_workflow_locally(
    payload: dict[str, Any],
    *,
    source_object_store: ObjectStore | None = None,
    artifact_object_store: ObjectStore | None = None,
    text_artifact_writer: TextArtifactWriter | None = None,
    source_status_writer: SourceFileStatusWriter | None = None,
    text_segment_writer: TextSegmentWriter | None = None,
    llm_reader: SequentialReadingReader | None = None,
    reading_notes_writer: ReadingNotesWriter | None = None,
    runtime_facts_writer: RuntimeFactsWriter | None = None,
    global_aggregator: GlobalAggregationRunner | None = None,
    ontology_runner: OntologyRunner | None = None,
    entity_resolution_runner: EntityResolutionRunner | None = None,
    agent_profile_runner: AgentProfileRunner | None = None,
    archive_candidate_runner: ArchiveCandidateRunner | None = None,
    asset_indexer: AssetIndexer | None = None,
    project_readiness_updater: ProjectReadinessUpdater | None = None,
    workflow_event_writer: WorkflowEventWriter | None = None,
    workflow_status_writer: WorkflowRunStatusWriter | None = None,
    continue_to_ontology: bool = False,
    continue_to_entity_resolution: bool = False,
    continue_to_agent_profiles: bool = False,
    continue_to_archive_candidates: bool = False,
    continue_to_index_assets: bool = False,
    continue_to_finalize: bool = False,
) -> dict[str, Any]:
    resolved_workflow_event_writer = (
        workflow_event_writer if workflow_event_writer is not None else _workflow_event_writer_from_env()
    )
    try:
        resolved_workflow_status_writer = (
            workflow_status_writer if workflow_status_writer is not None else _workflow_status_writer_from_env()
        )
    except Exception:
        resolved_workflow_status_writer = None
    result = seed_pipeline_activity(
        payload,
        workflow_event_writer=resolved_workflow_event_writer,
        workflow_status_writer=resolved_workflow_status_writer,
    )
    if result["status"] == "queued" and _payload_has_parse_source(payload):
        parse_result = parse_file_activity(
            payload,
            source_object_store=source_object_store,
            artifact_object_store=artifact_object_store,
            text_artifact_writer=text_artifact_writer,
            source_status_writer=source_status_writer,
            workflow_event_writer=resolved_workflow_event_writer,
            workflow_status_writer=resolved_workflow_status_writer,
        )
        if parse_result.get("status") != "completed":
            return parse_result
        segment_result = segment_text_activity(
            _segment_payload_from_parse(payload, parse_result),
            artifact_object_store=artifact_object_store,
            text_segment_writer=text_segment_writer,
            workflow_event_writer=resolved_workflow_event_writer,
            workflow_status_writer=resolved_workflow_status_writer,
        )
        if segment_result.get("status") != "completed":
            return segment_result
        if llm_reader is None and reading_notes_writer is None:
            return segment_result
        sequential_result = sequential_reading_activity(
            _sequential_payload_from_segment(payload, segment_result),
            llm_reader=llm_reader,
            reading_notes_writer=reading_notes_writer,
            workflow_event_writer=resolved_workflow_event_writer,
            workflow_status_writer=resolved_workflow_status_writer,
        )
        if sequential_result.get("status") != "completed":
            return sequential_result
        if runtime_facts_writer is None and global_aggregator is None:
            return sequential_result
        runtime_facts_result = persist_runtime_facts_activity(
            _runtime_facts_payload_from_sequential(payload),
            runtime_facts_writer=runtime_facts_writer,
            workflow_event_writer=resolved_workflow_event_writer,
        )
        if runtime_facts_result.get("status") != "completed":
            return runtime_facts_result
        if global_aggregator is None:
            return runtime_facts_result
        global_aggregation_result = global_aggregation_activity(
            _global_aggregation_payload_from_runtime_facts(payload, runtime_facts_result),
            global_aggregator=global_aggregator,
            workflow_event_writer=resolved_workflow_event_writer,
        )
        if not continue_to_ontology or global_aggregation_result.get("status") != "completed":
            return global_aggregation_result
        ontology_result = ontology_activity(
            _ontology_payload_from_global_aggregation(payload, global_aggregation_result),
            ontology_runner=ontology_runner,
            workflow_event_writer=resolved_workflow_event_writer,
        )
        if not continue_to_entity_resolution or ontology_result.get("status") != "completed":
            return ontology_result
        entity_resolution_result = entity_resolution_activity(
            _entity_resolution_payload_from_ontology(payload, ontology_result),
            entity_resolution_runner=entity_resolution_runner,
            workflow_event_writer=resolved_workflow_event_writer,
        )
        if not continue_to_agent_profiles or entity_resolution_result.get("status") != "completed":
            return entity_resolution_result
        agent_profile_result = agent_profile_activity(
            _agent_profile_payload_from_entity_resolution(payload, entity_resolution_result),
            agent_profile_runner=agent_profile_runner,
            workflow_event_writer=resolved_workflow_event_writer,
        )
        if not continue_to_archive_candidates or agent_profile_result.get("status") != "completed":
            return agent_profile_result
        archive_candidate_result = archive_candidate_activity(
            _archive_candidate_payload_from_agent_profile(payload, agent_profile_result),
            archive_candidate_runner=archive_candidate_runner,
            workflow_event_writer=resolved_workflow_event_writer,
        )
        if not continue_to_index_assets or archive_candidate_result.get("status") != "completed":
            return archive_candidate_result
        index_assets_result = index_assets_activity(
            _index_assets_payload_from_archive_candidate(payload, archive_candidate_result),
            asset_indexer=asset_indexer,
            workflow_event_writer=resolved_workflow_event_writer,
        )
        if not continue_to_finalize or index_assets_result.get("status") != "completed":
            return index_assets_result
        return finalize_seed_activity(
            _finalize_payload_from_index_assets(payload, index_assets_result),
            project_readiness_updater=project_readiness_updater,
            workflow_event_writer=resolved_workflow_event_writer,
            workflow_status_writer=resolved_workflow_status_writer,
        )
    if result["status"] == "queued":
        result = {
            **result,
            "trace_events": [
                {
                    "event_type": "workflow_stage_pending",
                    "payload": {"stage": "parse_file", "activity": "seed_pipeline_activity"},
                }
            ],
        }
    return result


def _payload_has_parse_source(payload: dict[str, Any]) -> bool:
    return all(isinstance(payload.get(key), str) and payload[key].strip() for key in ("source_file_id", "source_object_key"))


def _sanitize_segment_reference(segment: Any) -> dict[str, Any]:
    if not isinstance(segment, dict):
        raise ValueError("segment references must be objects")
    sanitized = {
        key: value
        for key, value in segment.items()
        if key in {"segment_id", "segment_order", "chapter_guess", "title_guess", "object_key"}
    }
    if "segment_order" not in sanitized:
        raise ValueError("segment_order is required for sequential reading")
    return sanitized


def _public_llm_error_message(code: str) -> str:
    if code == "LLM_MODULE_UNBOUND":
        return "sequential_reading module is unbound"
    if code == "LLM_CREDENTIAL_KEY_UNCONFIGURED":
        return "LLM credential key is unconfigured"
    if code == "LLM_CREDENTIAL_KEY_INVALID":
        return "LLM credential key is invalid"
    if code == "LLM_CREDENTIAL_UNAVAILABLE":
        return "LLM credential is unavailable"
    if code == "LLM_CREDENTIAL_DECRYPT_FAILED":
        return "LLM credential decrypt failed"
    if code == "LLM_CONCURRENCY_LIMITED":
        return "LLM concurrency limit reached"
    if code == "OBJECT_STORAGE_BACKEND_MISCONFIGURED":
        return "object storage backend is misconfigured"
    if code == "SCHEMA_VALIDATION_FAILED":
        return "sequential reading model returned unparsable JSON for a batch"
    return "sequential reading failed"


def _public_global_aggregation_error_message(code: str) -> str:
    if code == "GLOBAL_AGGREGATOR_CONFIGURATION_FAILED":
        return "global aggregator configuration failed"
    if code == "GLOBAL_AGGREGATOR_UNCONFIGURED":
        return "global aggregator is unconfigured"
    if code == "LLM_MODULE_UNBOUND":
        return f"{GLOBAL_AGGREGATION_MODULE_KEY} module is unbound"
    if code == "LLM_CREDENTIAL_KEY_UNCONFIGURED":
        return "LLM credential key is unconfigured"
    if code == "LLM_CREDENTIAL_KEY_INVALID":
        return "LLM credential key is invalid"
    if code == "LLM_CREDENTIAL_UNAVAILABLE":
        return "LLM credential is unavailable"
    if code == "LLM_CREDENTIAL_DECRYPT_FAILED":
        return "LLM credential decrypt failed"
    if code == "LLM_CONCURRENCY_LIMITED":
        return "LLM concurrency limit reached"
    if code == "SCHEMA_VALIDATION_FAILED":
        return "global aggregation output schema validation failed"
    if code == "SEED_AGGREGATE_SOURCE_QUERY_FAILED":
        return "seed aggregate source query failed"
    if code == "SEED_ANALYSIS_WRITE_FAILED":
        return "seed analysis write failed"
    return "global aggregation failed"


def _public_global_aggregation_error_code(code: str) -> str:
    if code in PUBLIC_GLOBAL_AGGREGATION_ERROR_CODES:
        return code
    return "LLM_PROVIDER_ERROR"


def _public_ontology_error_message(code: str) -> str:
    if code == "ONTOLOGY_RUNNER_UNCONFIGURED":
        return "ontology runner is unconfigured"
    if code == "ONTOLOGY_PERSISTENCE_UNCONFIGURED":
        return "ontology persistence is unconfigured"
    if code == "LLM_MODULE_UNBOUND":
        return f"{STORY_ONTOLOGY_MODULE_KEY} module is unbound"
    if code == "LLM_CREDENTIAL_KEY_UNCONFIGURED":
        return "LLM credential key is unconfigured"
    if code == "LLM_CREDENTIAL_KEY_INVALID":
        return "LLM credential key is invalid"
    if code == "LLM_CREDENTIAL_UNAVAILABLE":
        return "LLM credential is unavailable"
    if code == "LLM_CREDENTIAL_DECRYPT_FAILED":
        return "LLM credential decrypt failed"
    if code == "LLM_CONCURRENCY_LIMITED":
        return "LLM concurrency limit reached"
    if code == "ONTOLOGY_SNAPSHOT_WRITE_FAILED":
        return "ontology snapshot write failed"
    if code == "SCHEMA_VALIDATION_FAILED":
        return "ontology output schema validation failed"
    return "story ontology generation failed"


def _public_entity_resolution_error_message(code: str) -> str:
    if code == "ENTITY_RESOLUTION_RUNNER_UNCONFIGURED":
        return "entity resolution runner is unconfigured"
    if code == "LLM_MODULE_UNBOUND":
        return f"{ENTITY_RESOLUTION_MODULE_KEY} module is unbound"
    if code == "LLM_CREDENTIAL_KEY_UNCONFIGURED":
        return "LLM credential key is unconfigured"
    if code == "LLM_CREDENTIAL_KEY_INVALID":
        return "LLM credential key is invalid"
    if code == "LLM_CREDENTIAL_UNAVAILABLE":
        return "LLM credential is unavailable"
    if code == "LLM_CREDENTIAL_DECRYPT_FAILED":
        return "LLM credential decrypt failed"
    if code == "LLM_CONCURRENCY_LIMITED":
        return "LLM concurrency limit reached"
    if code == "ENTITY_RESOLUTION_SNAPSHOT_WRITE_FAILED":
        return "entity resolution snapshot write failed"
    if code == "SCHEMA_VALIDATION_FAILED":
        return "entity resolution output schema validation failed"
    return "entity resolution failed"


def _public_agent_profile_error_message(code: str) -> str:
    if code == "AGENT_PROFILE_RUNNER_UNCONFIGURED":
        return "agent profile runner is unconfigured"
    if code == "LLM_MODULE_UNBOUND":
        return f"{CHARACTER_AGENT_PROFILE_MODULE_KEY} module is unbound"
    if code == "LLM_CREDENTIAL_KEY_UNCONFIGURED":
        return "LLM credential key is unconfigured"
    if code == "LLM_CREDENTIAL_KEY_INVALID":
        return "LLM credential key is invalid"
    if code == "LLM_CREDENTIAL_UNAVAILABLE":
        return "LLM credential is unavailable"
    if code == "LLM_CREDENTIAL_DECRYPT_FAILED":
        return "LLM credential decrypt failed"
    if code == "LLM_CONCURRENCY_LIMITED":
        return "LLM concurrency limit reached"
    if code == "SCHEMA_VALIDATION_FAILED":
        return "agent profile output schema validation failed"
    return "agent profile generation failed"


def _public_archive_candidate_error_message(code: str) -> str:
    if code == "ARCHIVE_CANDIDATE_RUNNER_UNCONFIGURED":
        return "archive candidate runner is unconfigured"
    if code == "LLM_MODULE_UNBOUND":
        return f"{NARRATIVE_ARCHIVES_MODULE_KEY} module is unbound"
    if code == "LLM_CREDENTIAL_KEY_UNCONFIGURED":
        return "LLM credential key is unconfigured"
    if code == "LLM_CREDENTIAL_KEY_INVALID":
        return "LLM credential key is invalid"
    if code == "LLM_CREDENTIAL_UNAVAILABLE":
        return "LLM credential is unavailable"
    if code == "LLM_CREDENTIAL_DECRYPT_FAILED":
        return "LLM credential decrypt failed"
    if code == "LLM_CONCURRENCY_LIMITED":
        return "LLM concurrency limit reached"
    if code == "SCHEMA_VALIDATION_FAILED":
        return "archive candidate output schema validation failed"
    return "archive candidate generation failed"


def _public_index_assets_error_message(code: str) -> str:
    if code == "ASSET_INDEXER_UNCONFIGURED":
        return "asset indexer is unconfigured"
    if code == "SCHEMA_VALIDATION_FAILED":
        return "asset index output schema validation failed"
    return "asset indexing failed"


def _public_finalize_error_message(code: str) -> str:
    if code == "PROJECT_READINESS_UPDATER_UNCONFIGURED":
        return "project readiness updater is unconfigured"
    if code == "SCHEMA_VALIDATION_FAILED":
        return "project readiness output schema validation failed"
    return "project readiness update failed"


def _validated_sequential_reading_result(
    reading_result: dict[str, Any],
    *,
    segment_refs: list[dict[str, Any]],
    require_all_segments: bool = False,
) -> dict[str, Any]:
    if reading_result.get("status") != "completed":
        raise ValueError("status must be completed")
    pass_id = _required_text_value(reading_result.get("pass_id"), "pass_id")
    module_key = _optional_result_text(reading_result, "module_key") or "sequential_reading"
    if module_key != "sequential_reading":
        raise ValueError("module_key must be sequential_reading")
    model_id = _optional_result_text(reading_result, "model_id")
    raw_notes = reading_result.get("notes")
    if not isinstance(raw_notes, list):
        raise ValueError("notes must be a list")
    known_segment_ids = {
        segment["segment_id"].strip()
        for segment in segment_refs
        if isinstance(segment.get("segment_id"), str) and segment["segment_id"].strip()
    }
    notes = [_validated_reading_note(note, known_segment_ids=known_segment_ids) for note in raw_notes]
    if require_all_segments:
        if not known_segment_ids or len(known_segment_ids) != len(segment_refs):
            raise ValueError("segment retry requires complete segment refs")
        note_segment_ids = [note["segment_id"] for note in notes]
        if len(note_segment_ids) != len(set(note_segment_ids)):
            raise ValueError("segment retry notes must not duplicate segment refs")
        if set(note_segment_ids) != known_segment_ids:
            raise ValueError("segment retry notes must cover every claimed segment")
    return {
        "pass_id": pass_id,
        "module_key": module_key,
        "model_id": model_id,
        "notes": notes,
    }


def _validated_reading_note(note: Any, *, known_segment_ids: set[str]) -> dict[str, Any]:
    if not isinstance(note, dict):
        raise ValueError("reading notes must be objects")
    segment_id = _required_text_value(note.get("segment_id"), "segment_id")
    if known_segment_ids and segment_id not in known_segment_ids:
        raise ValueError("note segment_id must reference an input segment")
    payload = note.get("payload_jsonb")
    if not isinstance(payload, dict):
        raise ValueError("payload_jsonb must be an object")
    sanitized_payload = _sanitize_workflow_event_payload(payload)
    if not isinstance(sanitized_payload, dict):
        raise ValueError("payload_jsonb must be an object")
    for field_name in SEQUENTIAL_READING_PAYLOAD_LIST_FIELDS:
        if not isinstance(sanitized_payload.get(field_name), list):
            raise ValueError(f"payload_jsonb.{field_name} must be a list")
    for field_name in OPTIONAL_SEQUENTIAL_READING_PAYLOAD_LIST_FIELDS:
        if field_name in sanitized_payload and not isinstance(sanitized_payload.get(field_name), list):
            raise ValueError(f"payload_jsonb.{field_name} must be a list")
    return {
        "segment_id": segment_id,
        "summary": _optional_text(note, "summary"),
        "payload_jsonb": sanitized_payload,
    }


def _optional_runtime_fact_notes(value: Any) -> list[dict[str, Any]] | None:
    if value is None:
        return None
    return _validated_runtime_fact_notes(value)


def _validated_runtime_fact_notes(value: Any) -> list[dict[str, Any]]:
    if not isinstance(value, list):
        raise ValueError("reading_notes must be a list")
    return [_validated_reading_note(note, known_segment_ids=set()) for note in value]


def _reading_note_from_row(row: Any) -> dict[str, Any]:
    if isinstance(row, dict):
        segment_id = row.get("segment_id")
        payload = row.get("payload_jsonb")
        summary = row.get("summary")
    else:
        segment_id = row[0]
        payload = row[1]
        summary = row[2] if len(row) > 2 else None
    if isinstance(payload, str):
        payload = json.loads(payload)
    return {
        "segment_id": str(segment_id),
        "summary": summary,
        "payload_jsonb": payload,
    }


def _runtime_note_payload(note: dict[str, Any]) -> dict[str, Any]:
    payload = note.get("payload_jsonb")
    if not isinstance(payload, dict):
        raise ValueError("payload_jsonb must be an object")
    return payload


def _runtime_entities_from_payload(payload: dict[str, Any]) -> list[dict[str, Any]]:
    entities: list[dict[str, Any]] = []
    for character in payload.get("characters", []):
        entities.append(_runtime_entity(character, entity_type="character"))
    for organization in payload.get("organizations", []):
        entities.append(_runtime_entity(organization, entity_type="organization"))
    return entities


def _runtime_entity(value: Any, *, entity_type: str) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise ValueError(f"{entity_type} facts must be objects")
    name = _required_text_value(value.get("name"), "entity.name")
    return {
        "name": name,
        "entity_type": entity_type,
        "aliases": _optional_string_list(value.get("aliases")),
        "labels": _runtime_entity_labels(value.get("labels")),
        "importance": _optional_fact_text(value, "importance"),
        "state_summary": _optional_fact_text(value, "state_update") or _optional_fact_text(value, "state_summary"),
        "evidence": _optional_fact_text(value, "evidence"),
    }


def _runtime_entity_labels(value: Any) -> list[dict[str, str]]:
    if value is None:
        return []
    if not isinstance(value, list):
        raise ValueError("entity.labels must be a list")
    labels: list[dict[str, str]] = []
    for label in value:
        if isinstance(label, str):
            normalized_label = _required_text_value(label, "entity.label")
            labels.append({"label": normalized_label, "label_type": "tag"})
            continue
        if not isinstance(label, dict):
            raise ValueError("entity.labels entries must be objects or strings")
        normalized_label = _required_text_value(label.get("label") or label.get("name"), "entity.label")
        labels.append(
            {
                "label": normalized_label,
                "label_type": _optional_fact_text(label, "label_type") or _optional_fact_text(label, "type") or "tag",
            }
        )
    return labels


def _runtime_relationships_from_payload(payload: dict[str, Any]) -> list[dict[str, Any]]:
    return [_runtime_relationship(relationship) for relationship in payload.get("relationships", [])]


def _runtime_relationship(value: Any) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise ValueError("relationships entries must be objects")
    source = (
        _optional_fact_text(value, "source")
        or _optional_fact_text(value, "source_entity")
        or _optional_fact_text(value, "source_entity_name")
        or _optional_fact_text(value, "from")
    )
    target = (
        _optional_fact_text(value, "target")
        or _optional_fact_text(value, "target_entity")
        or _optional_fact_text(value, "target_entity_name")
        or _optional_fact_text(value, "to")
    )
    relationship_type = (
        _optional_fact_text(value, "type")
        or _optional_fact_text(value, "relationship_type")
        or _optional_fact_text(value, "relation")
    )
    if source is None:
        raise ValueError("relationship.source is required")
    if target is None:
        raise ValueError("relationship.target is required")
    if relationship_type is None:
        raise ValueError("relationship.type is required")
    return {
        "source_entity_name": source,
        "target_entity_name": target,
        "relationship_type": relationship_type,
        "summary": _optional_fact_text(value, "summary") or _optional_fact_text(value, "description"),
        "evidence": _optional_fact_text(value, "evidence"),
    }


def _runtime_plot_threads_from_payload(payload: dict[str, Any]) -> list[dict[str, Any]]:
    return [_runtime_plot_thread(thread) for thread in payload.get("plot_threads", [])]


def _runtime_plot_thread(value: Any) -> dict[str, Any]:
    if isinstance(value, str):
        return {"title": _required_text_value(value, "plot_thread"), "status": "open", "summary": None, "evidence": None}
    if not isinstance(value, dict):
        raise ValueError("plot_threads entries must be objects or strings")
    title = _optional_fact_text(value, "title") or _optional_fact_text(value, "name")
    if title is None:
        raise ValueError("plot_thread.title is required")
    return {
        "title": title,
        "status": _optional_fact_text(value, "status") or "open",
        "summary": _optional_fact_text(value, "summary") or _optional_fact_text(value, "description"),
        "evidence": _optional_fact_text(value, "evidence"),
    }


def _runtime_narrative_arcs_from_payload(payload: dict[str, Any]) -> list[dict[str, Any]]:
    return [_runtime_narrative_arc(arc) for arc in payload.get("narrative_arcs", [])]


def _runtime_narrative_arc(value: Any) -> dict[str, Any]:
    if isinstance(value, str):
        return {
            "title": _required_text_value(value, "narrative_arc"),
            "arc_type": None,
            "summary": None,
            "evidence": None,
        }
    if not isinstance(value, dict):
        raise ValueError("narrative_arcs entries must be objects or strings")
    title = _optional_fact_text(value, "title") or _optional_fact_text(value, "name")
    if title is None:
        raise ValueError("narrative_arc.title is required")
    return {
        "title": title,
        "arc_type": _optional_fact_text(value, "arc_type") or _optional_fact_text(value, "type"),
        "summary": _optional_fact_text(value, "summary") or _optional_fact_text(value, "description"),
        "evidence": _optional_fact_text(value, "evidence"),
    }


def _runtime_volume_summaries_from_payload(payload: dict[str, Any]) -> list[dict[str, Any]]:
    return [_runtime_volume_summary(summary) for summary in payload.get("volume_summaries", [])]


def _runtime_volume_summary(value: Any) -> dict[str, Any]:
    if isinstance(value, str):
        return {
            "volume_key": "default",
            "title": None,
            "summary": _required_text_value(value, "volume_summary"),
            "evidence": None,
        }
    if not isinstance(value, dict):
        raise ValueError("volume_summaries entries must be objects or strings")
    title = _optional_fact_text(value, "title") or _optional_fact_text(value, "name")
    volume_key = (
        _optional_fact_text(value, "volume_key")
        or _optional_fact_text(value, "volume_id")
        or _optional_fact_text(value, "volume")
        or title
    )
    if volume_key is None:
        raise ValueError("volume_summary.volume_key is required")
    summary = _optional_fact_text(value, "summary") or _optional_fact_text(value, "description")
    if summary is None:
        raise ValueError("volume_summary.summary is required")
    return {
        "volume_key": volume_key,
        "title": title,
        "summary": summary,
        "evidence": _optional_fact_text(value, "evidence"),
    }


def _runtime_world_rules_from_payload(payload: dict[str, Any]) -> list[dict[str, Any]]:
    return [_runtime_world_rule(rule) for rule in payload.get("world_rules", [])]


def _runtime_world_rule(value: Any) -> dict[str, Any]:
    if isinstance(value, str):
        return {"rule_text": _required_text_value(value, "world_rule"), "evidence": None, "category": None, "confidence": None}
    if not isinstance(value, dict):
        raise ValueError("world_rules entries must be objects or strings")
    rule_text = (
        _optional_fact_text(value, "rule")
        or _optional_fact_text(value, "rule_text")
        or _optional_fact_text(value, "text")
        or _optional_fact_text(value, "description")
    )
    if rule_text is None:
        raise ValueError("world_rule.rule is required")
    return {
        "rule_text": rule_text,
        "evidence": _optional_fact_text(value, "evidence"),
        "category": _optional_fact_text(value, "category"),
        "confidence": _optional_number(value.get("confidence")),
    }


def _runtime_character_events_from_payload(payload: dict[str, Any]) -> list[dict[str, Any]]:
    return [
        _runtime_character_event(event)
        for event in payload.get("events", [])
        if _runtime_event_category(event) == "character"
    ]


def _runtime_world_events_from_payload(payload: dict[str, Any]) -> list[dict[str, Any]]:
    return [_runtime_world_event(event) for event in payload.get("events", []) if _runtime_event_category(event) == "world"]


def _runtime_relationship_events_from_payload(payload: dict[str, Any]) -> list[dict[str, Any]]:
    return [
        _runtime_relationship_event(event)
        for event in payload.get("events", [])
        if _runtime_event_category(event) == "relationship"
    ]


def _runtime_event_category(value: Any) -> str:
    if not isinstance(value, dict):
        raise ValueError("events entries must be objects")
    event_type = _optional_fact_text(value, "event_type") or _optional_fact_text(value, "type")
    scope = _optional_fact_text(value, "scope")
    if event_type == "relationship" or _has_any_fact_text(value, ("source", "source_entity", "source_entity_name", "from")):
        return "relationship"
    if scope == "world" or event_type == "world":
        return "world"
    return "character"


def _runtime_character_event(value: Any) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise ValueError("events entries must be objects")
    entity_name = (
        _optional_fact_text(value, "entity_name")
        or _optional_fact_text(value, "character")
        or _optional_fact_text(value, "character_name")
        or _optional_fact_text(value, "actor")
    )
    if entity_name is None:
        raise ValueError("character_event.entity_name is required")
    return {
        "entity_name": entity_name,
        "event_summary": _runtime_event_summary(value),
        "event_kind": _optional_fact_text(value, "event_kind") or _optional_fact_text(value, "kind"),
        "evidence": _optional_fact_text(value, "evidence"),
    }


def _runtime_world_event(value: Any) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise ValueError("events entries must be objects")
    return {
        "event_summary": _runtime_event_summary(value),
        "event_kind": _optional_fact_text(value, "event_kind") or _optional_fact_text(value, "kind"),
        "evidence": _optional_fact_text(value, "evidence"),
    }


def _runtime_relationship_event(value: Any) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise ValueError("events entries must be objects")
    source = (
        _optional_fact_text(value, "source")
        or _optional_fact_text(value, "source_entity")
        or _optional_fact_text(value, "source_entity_name")
        or _optional_fact_text(value, "from")
    )
    target = (
        _optional_fact_text(value, "target")
        or _optional_fact_text(value, "target_entity")
        or _optional_fact_text(value, "target_entity_name")
        or _optional_fact_text(value, "to")
    )
    relationship_type = (
        _optional_fact_text(value, "relationship_type")
        or _optional_fact_text(value, "relation")
        or _optional_fact_text(value, "relationship")
    )
    if source is None:
        raise ValueError("relationship_event.source is required")
    if target is None:
        raise ValueError("relationship_event.target is required")
    if relationship_type is None:
        raise ValueError("relationship_event.relationship_type is required")
    return {
        "source_entity_name": source,
        "target_entity_name": target,
        "relationship_type": relationship_type,
        "event_summary": _runtime_event_summary(value),
        "evidence": _optional_fact_text(value, "evidence"),
    }


def _runtime_event_summary(value: dict[str, Any]) -> str:
    summary = (
        _optional_fact_text(value, "summary")
        or _optional_fact_text(value, "description")
        or _optional_fact_text(value, "event")
    )
    if summary is None:
        raise ValueError("event.summary is required")
    return summary


def _runtime_consistency_notes_from_payload(payload: dict[str, Any]) -> list[dict[str, Any]]:
    return [_runtime_consistency_note(note) for note in payload.get("consistency_notes", [])]


def _runtime_consistency_note(value: Any) -> dict[str, Any]:
    if isinstance(value, str):
        return {
            "note_type": "general",
            "severity": "info",
            "summary": _required_text_value(value, "consistency_note"),
            "evidence": None,
        }
    if not isinstance(value, dict):
        raise ValueError("consistency_notes entries must be objects or strings")
    summary = (
        _optional_fact_text(value, "summary")
        or _optional_fact_text(value, "note")
        or _optional_fact_text(value, "description")
    )
    if summary is None:
        raise ValueError("consistency_note.summary is required")
    return {
        "note_type": _optional_fact_text(value, "note_type") or _optional_fact_text(value, "type") or "general",
        "severity": _optional_fact_text(value, "severity") or "info",
        "summary": summary,
        "evidence": _optional_fact_text(value, "evidence"),
    }


def _has_any_fact_text(value: dict[str, Any], keys: tuple[str, ...]) -> bool:
    return any(_optional_fact_text(value, key) is not None for key in keys)


def _optional_fact_text(value: dict[str, Any], key: str) -> str | None:
    raw_value = value.get(key)
    if raw_value is None:
        return None
    if not isinstance(raw_value, str):
        raise ValueError(f"{key} must be a string")
    normalized_value = raw_value.strip()
    return normalized_value or None


def _optional_string_list(value: Any) -> list[str]:
    if value is None:
        return []
    if not isinstance(value, list):
        raise ValueError("aliases must be a list")
    aliases: list[str] = []
    for alias in value:
        aliases.append(_required_text_value(alias, "alias"))
    return aliases


def _optional_number(value: Any) -> int | float | None:
    if value is None:
        return None
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ValueError("confidence must be a number")
    return value


def _row_value(row: Any, key: str) -> str:
    if row is None:
        raise ValueError(f"{key} was not returned")
    value = row.get(key) if isinstance(row, dict) else row[0]
    return _required_text_value(str(value), key)


def _row_int(row: Any, key: str) -> int:
    if row is None:
        raise ValueError(f"{key} was not returned")
    value = row.get(key) if isinstance(row, dict) else row[0]
    return _non_negative_int(value, key)


def _row_value_at(row: Any, key: str, index: int) -> str:
    if row is None:
        raise ValueError(f"{key} was not returned")
    value = row.get(key) if isinstance(row, dict) else row[index]
    return _required_text_value(str(value), key)


def _row_int_at(row: Any, key: str, index: int) -> int:
    if row is None:
        raise ValueError(f"{key} was not returned")
    value = row.get(key) if isinstance(row, dict) else row[index]
    return _non_negative_int(value, key)


def _optional_result_text(result: dict[str, Any], key: str) -> str | None:
    value = result.get(key)
    if value is None:
        return None
    if not isinstance(value, str):
        raise ValueError(f"{key} must be a string")
    value = value.strip()
    return value or None


def _segment_payload_from_parse(payload: dict[str, Any], parse_result: dict[str, Any]) -> dict[str, Any]:
    return {
        **payload,
        "artifact_type": "extracted_text",
        "artifact_object_key": parse_result.get("artifact_object_key"),
    }


def _sequential_payload_from_segment(payload: dict[str, Any], segment_result: dict[str, Any]) -> dict[str, Any]:
    return {
        **payload,
        "source_file_id": segment_result.get("source_file_id", payload.get("source_file_id")),
        "segments": segment_result.get("segments"),
    }


def _runtime_facts_payload_from_sequential(payload: dict[str, Any]) -> dict[str, Any]:
    return {**payload}


def _global_aggregation_payload_from_runtime_facts(
    payload: dict[str, Any],
    runtime_facts_result: dict[str, Any],
) -> dict[str, Any]:
    return {
        **payload,
        "runtime_fact_counts": {
            key: runtime_facts_result[key]
            for key in (
                "entity_count",
                "entity_label_count",
                "relationship_count",
                "plot_thread_count",
                "thread_lifecycle_count",
                "narrative_arc_count",
                "volume_summary_count",
                "world_rule_count",
                "character_event_count",
                "world_event_count",
                "relationship_event_count",
                "consistency_note_count",
                "segment_summary_count",
            )
            if key in runtime_facts_result
        },
    }


def _ontology_payload_from_global_aggregation(
    payload: dict[str, Any],
    global_aggregation_result: dict[str, Any],
) -> dict[str, Any]:
    ontology_payload: dict[str, Any] = {
        **payload,
        "global_aggregation": {
            key: global_aggregation_result[key]
            for key in (
                "module_key",
                "model_id",
                "segment_count",
                "summary_count",
                "seed_analysis_snapshot_id",
            )
            if key in global_aggregation_result
        },
    }
    return ontology_payload


def _entity_resolution_payload_from_ontology(
    payload: dict[str, Any],
    ontology_result: dict[str, Any],
) -> dict[str, Any]:
    return {
        **payload,
        "story_ontology": {
            key: ontology_result[key]
            for key in (
                "module_key",
                "model_id",
                "ontology_snapshot_id",
                "entity_type_count",
                "relationship_type_count",
                "world_rule_type_count",
            )
            if key in ontology_result
        },
    }


def _agent_profile_payload_from_entity_resolution(
    payload: dict[str, Any],
    entity_resolution_result: dict[str, Any],
) -> dict[str, Any]:
    return {
        **payload,
        "entity_resolution": {
            key: entity_resolution_result[key]
            for key in (
                "module_key",
                "model_id",
                "resolution_snapshot_id",
                "merged_entity_count",
                "alias_count",
                "conflict_count",
            )
            if key in entity_resolution_result
        },
    }


def _archive_candidate_payload_from_agent_profile(
    payload: dict[str, Any],
    agent_profile_result: dict[str, Any],
) -> dict[str, Any]:
    return {
        **payload,
        "agent_profiles": {
            key: agent_profile_result[key]
            for key in (
                "module_key",
                "model_id",
                "profile_snapshot_id",
                "profile_count",
                "memory_seed_count",
                "relationship_view_count",
            )
            if key in agent_profile_result
        },
    }


def _index_assets_payload_from_archive_candidate(
    payload: dict[str, Any],
    archive_candidate_result: dict[str, Any],
) -> dict[str, Any]:
    return {
        **payload,
        "archive_candidates": {
            key: archive_candidate_result[key]
            for key in (
                "module_key",
                "model_id",
                "archive_candidate_batch_id",
                "candidate_count",
                "archive_entity_candidate_count",
                "memory_candidate_count",
            )
            if key in archive_candidate_result
        },
    }


def _finalize_payload_from_index_assets(
    payload: dict[str, Any],
    index_assets_result: dict[str, Any],
) -> dict[str, Any]:
    return {
        **payload,
        "asset_index": {
            key: index_assets_result[key]
            for key in (
                "asset_index_batch_id",
                "indexed_asset_count",
                "search_document_count",
                "embedding_count",
            )
            if key in index_assets_result
        },
    }


def _sequential_segment_reference(segment: dict[str, Any]) -> dict[str, Any]:
    return {
        key: segment[key]
        for key in ("segment_id", "segment_order", "chapter_guess", "title_guess", "object_key")
        if key in segment
    }


def _segment_extracted_text(
    *,
    context: AgentContext,
    source_file_id: str,
    text: str,
    object_store: ObjectStore,
) -> list[dict[str, Any]]:
    raw_segments = _split_text_by_headings(text)
    segments: list[dict[str, Any]] = []
    for index, raw_segment in enumerate(raw_segments):
        object_key = _segment_text_object_key(context, index)
        segment_text = raw_segment["text"]
        object_store.write_bytes(object_key, segment_text.encode("utf-8"), "text/plain; charset=utf-8")
        segments.append(
            {
                "segment_id": _segment_id(context=context, source_file_id=source_file_id, segment_order=index),
                "segment_order": index,
                "chapter_guess": raw_segment.get("chapter_guess"),
                "title_guess": raw_segment.get("title_guess"),
                "start_offset": raw_segment["start_offset"],
                "end_offset": raw_segment["end_offset"],
                "content_excerpt": _segment_excerpt(segment_text),
                "object_key": object_key,
                "summary": None,
                "metadata_jsonb": {
                    "segmentation_strategy": raw_segment.get(
                        "segmentation_strategy", "chapter_heading_or_single_document"
                    ),
                    "source_file_id": source_file_id,
                },
            }
        )
    return segments


def _segment_id(*, context: AgentContext, source_file_id: str, segment_order: int) -> str:
    stable_key = ":".join(
        [
            "mirofish",
            "seed-segment",
            context.tenant_id,
            context.project_id or "",
            context.run_id,
            source_file_id,
            str(segment_order),
        ]
    )
    return str(uuid.uuid5(uuid.NAMESPACE_URL, stable_key))


def _segment_text_object_key(context: AgentContext, segment_order: int) -> str:
    if context.project_id is None:
        raise ValueError("project_id is required to build segment text object key")
    return f"projects/{context.project_id}/seed-runs/{context.run_id}/segments/{segment_order:04d}.txt"


def _split_text_by_headings(text: str) -> list[dict[str, Any]]:
    if not text.strip():
        raise ValueError("extracted text is empty")
    headings: list[dict[str, Any]] = []
    offset = 0
    for line in text.splitlines(keepends=True):
        heading = _chapter_heading(line)
        if heading is not None:
            headings.append({"start": offset, **heading})
        offset += len(line)
    if not headings:
        return _split_unheaded_text(text)

    segments: list[dict[str, Any]] = []
    if headings[0]["start"] > 0:
        preface = _segment_from_span(text, 0, headings[0]["start"], None, None)
        if preface is not None:
            segments.append(preface)
    for index, heading in enumerate(headings):
        end = headings[index + 1]["start"] if index + 1 < len(headings) else len(text)
        segment = _segment_from_span(
            text,
            heading["start"],
            end,
            heading["chapter_guess"],
            heading["title_guess"],
        )
        if segment is not None:
            segments.append(segment)
    return segments


def _split_unheaded_text(text: str) -> list[dict[str, Any]]:
    segments: list[dict[str, Any]] = []
    current_start: int | None = None
    current_end: int | None = None
    for paragraph_start, paragraph_end in _paragraph_spans(text):
        if current_start is None or current_end is None:
            current_start = paragraph_start
            current_end = paragraph_end
            continue
        _, _, candidate_text = _trimmed_span(text, current_start, paragraph_end)
        if len(candidate_text) > UNHEADED_SEGMENT_TARGET_CHARS:
            segments.extend(_unheaded_segments_from_span(text, current_start, current_end))
            current_start = paragraph_start
            current_end = paragraph_end
            continue
        current_end = paragraph_end
    if current_start is not None and current_end is not None:
        segments.extend(_unheaded_segments_from_span(text, current_start, current_end))
    return segments


def _paragraph_spans(text: str) -> list[tuple[int, int]]:
    spans: list[tuple[int, int]] = []
    paragraph_start: int | None = None
    paragraph_end: int | None = None
    offset = 0
    for line in text.splitlines(keepends=True):
        if line.strip():
            if paragraph_start is None:
                paragraph_start = offset
            paragraph_end = offset + len(line)
        elif paragraph_start is not None and paragraph_end is not None:
            spans.append((paragraph_start, paragraph_end))
            paragraph_start = None
            paragraph_end = None
        offset += len(line)
    if paragraph_start is not None and paragraph_end is not None:
        spans.append((paragraph_start, paragraph_end))
    return spans


def _unheaded_segments_from_span(text: str, start: int, end: int) -> list[dict[str, Any]]:
    start_offset, end_offset, segment_text = _trimmed_span(text, start, end)
    if not segment_text:
        return []
    if len(segment_text) <= UNHEADED_SEGMENT_TARGET_CHARS:
        segment = _segment_from_span(text, start_offset, end_offset, None, None)
        if segment is None:
            return []
        segment["segmentation_strategy"] = "paragraph_window"
        return [segment]

    segments: list[dict[str, Any]] = []
    cursor = start_offset
    while cursor < end_offset:
        split_at = _find_unheaded_split(text, cursor, end_offset)
        segment = _segment_from_span(text, cursor, split_at, None, None)
        if segment is not None:
            segment["segmentation_strategy"] = "paragraph_window"
            segments.append(segment)
        cursor = split_at
    return segments


def _find_unheaded_split(text: str, start: int, end: int) -> int:
    limit = min(end, start + UNHEADED_SEGMENT_TARGET_CHARS)
    if limit >= end:
        return end
    minimum = start + (UNHEADED_SEGMENT_TARGET_CHARS // 2)
    for separator in ("\n\n", "\n", "。", "！", "？", ". ", "! ", "? ", " "):
        position = text.rfind(separator, start + 1, limit)
        if position >= minimum:
            return position + len(separator)
    return limit


def _segment_from_span(
    text: str,
    start: int,
    end: int,
    chapter_guess: str | None,
    title_guess: str | None,
) -> dict[str, Any] | None:
    start_offset, end_offset, segment_text = _trimmed_span(text, start, end)
    if not segment_text:
        return None
    return {
        "text": segment_text,
        "start_offset": start_offset,
        "end_offset": end_offset,
        "chapter_guess": chapter_guess,
        "title_guess": title_guess,
    }


def _trimmed_span(text: str, start: int, end: int) -> tuple[int, int, str]:
    segment_text = text[start:end]
    leading_trimmed = len(segment_text) - len(segment_text.lstrip())
    trailing_trimmed = len(segment_text.rstrip())
    trimmed_text = segment_text.strip()
    return start + leading_trimmed, start + trailing_trimmed, trimmed_text


def _chapter_heading(line: str) -> dict[str, str] | None:
    stripped = line.strip()
    if stripped.startswith("#"):
        stripped = stripped.lstrip("#").strip()
    match = re.match(r"^(第.+?[章节卷部回])\s*(.*)$", stripped)
    if match is not None:
        title = match.group(2).strip() or None
        return {"chapter_guess": match.group(1).strip(), "title_guess": title}
    match = re.match(
        r"^((?:chapter|chap\.?)\s+[A-Za-z0-9IVXLCDMivxlcdm]+)\s*(?::|：|-|—)?\s*(.*)$",
        stripped,
        re.IGNORECASE,
    )
    if match is None:
        return None
    title = match.group(2).strip() or None
    return {"chapter_guess": match.group(1).strip(), "title_guess": title}


def _segment_excerpt(segment_text: str) -> str:
    for line in segment_text.splitlines():
        stripped = line.strip()
        if stripped:
            return stripped
    return segment_text.strip()


def worker_spec() -> dict[str, list[str] | str]:
    return {
        "task_queue": SEED_TASK_QUEUE,
        "workflows": [SeedPipelineWorkflow.__name__, SeedSegmentRetryWorkflow.__name__],
        "activities": [
            seed_pipeline_activity.__name__,
            parse_file_activity.__name__,
            segment_text_activity.__name__,
            sequential_reading_activity.__name__,
            persist_runtime_facts_activity.__name__,
            global_aggregation_activity.__name__,
            ontology_activity.__name__,
            entity_resolution_activity.__name__,
            agent_profile_activity.__name__,
            archive_candidate_activity.__name__,
            index_assets_activity.__name__,
            finalize_seed_activity.__name__,
            seed_segment_retry_activity.__name__,
        ],
    }
