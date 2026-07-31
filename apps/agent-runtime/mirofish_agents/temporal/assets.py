from __future__ import annotations

import hashlib
import json
import math
import os
import uuid
from datetime import timedelta
from typing import Any, Callable, Protocol
from urllib.request import Request, urlopen

from temporalio import activity, workflow
from temporalio.common import RetryPolicy

from mirofish_agents.common.context import AgentContext
from mirofish_agents.common.http import read_response_limited, response_limit_from_env
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
    _estimate_tokens,
)

ASSET_TASK_QUEUE = "asset-light"
ASSET_ACTIVITY_RETRY_POLICY = RetryPolicy(
    initial_interval=timedelta(seconds=5),
    backoff_coefficient=2.0,
    maximum_interval=timedelta(minutes=1),
    maximum_attempts=3,
)
ASSET_INGESTION_MODULE_KEY = "asset_ingestion"
STYLE_EXTRACTION_MODULE_KEY = "style_extractor"
ASSET_REINDEX_MODULE_KEY = "asset_reindex"
SENSITIVE_ASSET_KEYS = {
    "api_key",
    "body",
    "content",
    "credential_ref",
    "draft",
    "encrypted_api_key",
    "excerpt",
    "excerpts",
    "manuscript",
    "material_text",
    "prompt",
    "quote",
    "quotes",
    "raw_content",
    "response",
    "sample",
    "samples",
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


class WorkflowStatusWriter(Protocol):
    def write_status(
        self,
        *,
        context: AgentContext,
        status: str,
        result: dict[str, Any] | None,
        error_code: str | None,
        error_message: str | None,
    ) -> None:
        ...


class AssetIngestionRunner(Protocol):
    def ingest(
        self,
        *,
        context: AgentContext,
        module_key: str,
        material_text: str,
        hint_type: str | None,
        scope: str,
        options: dict[str, Any],
    ) -> dict[str, Any]:
        ...


class AssetCandidateWriter(Protocol):
    def write_candidates(
        self,
        *,
        context: AgentContext,
        candidate_batch_id: str,
        model_id: str | None,
        scope: str,
        candidates: list[dict[str, Any]],
    ) -> dict[str, Any]:
        ...


class StyleExtractionRunner(Protocol):
    def extract_style(
        self,
        *,
        context: AgentContext,
        module_key: str,
        material_text: str | None,
        source_asset_id: str | None,
        scope: str,
        options: dict[str, Any],
    ) -> dict[str, Any]:
        ...


class StyleSourceMaterialLoader(Protocol):
    def load_material(self, *, context: AgentContext, source_asset_id: str) -> str:
        ...


class AssetReindexer(Protocol):
    def reindex(
        self,
        *,
        context: AgentContext,
        scope: str,
        mode: str,
        options: dict[str, Any],
    ) -> dict[str, Any]:
        ...


class EmbeddingClient(Protocol):
    def embed_texts(
        self,
        *,
        context: AgentContext,
        resolution: ModuleBindingResolution,
        api_key: str,
        texts: list[str],
        provider_call_id: str | None = None,
    ) -> list[list[float]]:
        ...


class EmbeddingVectors(list[list[float]]):
    def __init__(self, values: list[list[float]], *, llm_usage: dict[str, int] | None) -> None:
        super().__init__(values)
        self.llm_usage = llm_usage


class OpenAICompatibleEmbeddingClient:
    def __init__(self, *, http_request: Callable[[Request], bytes] | None = None) -> None:
        self._http_request = http_request or _urlopen_bytes

    def embed_texts(
        self,
        *,
        context: AgentContext,
        resolution: ModuleBindingResolution,
        api_key: str,
        texts: list[str],
        provider_call_id: str | None = None,
    ) -> EmbeddingVectors:
        if not texts:
            return EmbeddingVectors([], llm_usage=None)
        body: dict[str, Any] = {"model": resolution.model_id, "input": texts}
        dimensions = resolution.settings.get("embedding_dimensions")
        if isinstance(dimensions, int) and not isinstance(dimensions, bool) and dimensions > 0:
            body["dimensions"] = dimensions
        headers = {
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
            "X-MiroFish-Tenant-Id": context.tenant_id,
            "X-MiroFish-Project-Id": context.project_id or "",
            "X-MiroFish-Run-Id": context.run_id,
            "X-MiroFish-Module-Key": resolution.module_key,
        }
        if isinstance(provider_call_id, str) and provider_call_id.strip():
            headers["Idempotency-Key"] = provider_call_id.strip()
        request = Request(
            _embeddings_url(resolution.base_url),
            data=json.dumps(body, ensure_ascii=False).encode("utf-8"),
            headers=headers,
            method="POST",
        )
        try:
            response_body = self._http_request(request)
        except Exception as exc:
            raise LLMFacilityError("LLM_PROVIDER_ERROR", "embedding provider request failed") from exc
        try:
            response = json.loads(response_body.decode("utf-8"))
            data = response["data"]
        except (KeyError, TypeError, UnicodeDecodeError, json.JSONDecodeError) as exc:
            raise LLMFacilityError("LLM_PROVIDER_ERROR", "embedding response was not valid") from exc
        if not isinstance(data, list) or len(data) != len(texts):
            raise LLMFacilityError("SCHEMA_VALIDATION_FAILED", "embedding response count did not match input count")
        ordered: list[list[float] | None] = [None] * len(texts)
        for fallback_index, item in enumerate(data):
            if not isinstance(item, dict):
                raise LLMFacilityError("SCHEMA_VALIDATION_FAILED", "embedding response item must be an object")
            index = item.get("index", fallback_index)
            if isinstance(index, bool) or not isinstance(index, int) or index < 0 or index >= len(texts):
                raise LLMFacilityError("SCHEMA_VALIDATION_FAILED", "embedding response index was invalid")
            if ordered[index] is not None:
                raise LLMFacilityError("SCHEMA_VALIDATION_FAILED", "embedding response index was duplicated")
            ordered[index] = _embedding_vector(item.get("embedding"))
        embeddings = [embedding for embedding in ordered if embedding is not None]
        if len(embeddings) != len(texts):
            raise LLMFacilityError("SCHEMA_VALIDATION_FAILED", "embedding response was incomplete")
        dimensions_seen = {len(embedding) for embedding in embeddings}
        if len(dimensions_seen) != 1:
            raise LLMFacilityError("SCHEMA_VALIDATION_FAILED", "embedding dimensions were inconsistent")
        return EmbeddingVectors(embeddings, llm_usage=_embedding_usage(response.get("usage")))


class LLMFacilityAssetIngestionRunner:
    def __init__(
        self,
        *,
        binding_resolver: ModuleBindingResolver,
        credential_provider: CredentialProvider,
        chat_client: JSONChatClient,
        candidate_writer: AssetCandidateWriter,
        quota_gate: ProviderQuotaGate | None = None,
    ) -> None:
        self._binding_resolver = binding_resolver
        self._credential_provider = credential_provider
        self._chat_client = chat_client
        self._candidate_writer = candidate_writer
        self._quota_gate = quota_gate

    def ingest(
        self,
        *,
        context: AgentContext,
        module_key: str,
        material_text: str,
        hint_type: str | None,
        scope: str,
        options: dict[str, Any],
    ) -> dict[str, Any]:
        if module_key != ASSET_INGESTION_MODULE_KEY:
            return _runner_failed("VALIDATION_FAILED", "LLMFacilityAssetIngestionRunner only supports asset_ingestion")
        try:
            resolution = self._binding_resolver.resolve_module_binding(
                context=context,
                module_key=module_key,
            )
            _validate_asset_ingestion_resolution(resolution)
            api_key = self._credential_provider.resolve_api_key(
                context=context,
                credential_ref=resolution.credential_ref,
            )
            if not isinstance(api_key, str) or not api_key.strip():
                raise LLMFacilityError("LLM_CREDENTIAL_UNAVAILABLE", "resolved credential was empty")
            messages = _asset_ingestion_messages(
                context=context,
                material_text=material_text,
                hint_type=hint_type,
                scope=scope,
                options=options,
            )
            if self._quota_gate is None:
                response_json = self._chat_client.complete_json(
                    context=context,
                    resolution=resolution,
                    api_key=api_key.strip(),
                    messages=messages,
                )
                candidates = _candidate_list(response_json.get("candidates"))
            else:
                candidates = self._quota_gate.execute_json(
                    context=context,
                    resolution=resolution,
                    stage="candidate_generation",
                    call_index=0,
                    input_texts=[message["content"] for message in messages],
                    provider=lambda provider_call_id: self._chat_client.complete_json(
                        context=context,
                        resolution=resolution,
                        api_key=api_key.strip(),
                        messages=messages,
                        provider_call_id=provider_call_id,
                    ),
                    validate=lambda response: _candidate_list(response.get("candidates")),
                )
            candidate_batch_id = f"asset-ingestion:{context.run_id}"
            persisted = self._candidate_writer.write_candidates(
                context=context,
                candidate_batch_id=candidate_batch_id,
                model_id=resolution.model_id,
                scope=scope,
                candidates=candidates,
            )
        except LLMFacilityError as exc:
            return _runner_failed(exc.code, exc.message)
        except Exception as exc:
            return _runner_failed("LLM_PROVIDER_ERROR", str(exc))

        return {
            "status": "completed",
            "module_key": ASSET_INGESTION_MODULE_KEY,
            "model_id": resolution.model_id,
            "candidate_batch_id": candidate_batch_id,
            "candidate_count": persisted.get("candidate_count", len(candidates)),
            "asset_type_counts": persisted.get("asset_type_counts", _count_candidate_types(candidates)),
        }


class LLMFacilityStyleExtractionRunner:
    def __init__(
        self,
        *,
        binding_resolver: ModuleBindingResolver,
        credential_provider: CredentialProvider,
        chat_client: JSONChatClient,
        candidate_writer: AssetCandidateWriter,
        source_material_loader: StyleSourceMaterialLoader | None = None,
        quota_gate: ProviderQuotaGate | None = None,
    ) -> None:
        self._binding_resolver = binding_resolver
        self._credential_provider = credential_provider
        self._chat_client = chat_client
        self._candidate_writer = candidate_writer
        self._source_material_loader = source_material_loader
        self._quota_gate = quota_gate

    def extract_style(
        self,
        *,
        context: AgentContext,
        module_key: str,
        material_text: str | None,
        source_asset_id: str | None,
        scope: str,
        options: dict[str, Any],
    ) -> dict[str, Any]:
        if module_key != STYLE_EXTRACTION_MODULE_KEY:
            return _style_runner_failed("VALIDATION_FAILED", "LLMFacilityStyleExtractionRunner only supports style_extractor")
        try:
            resolved_material_text = self._resolve_material_text(
                context=context,
                material_text=material_text,
                source_asset_id=source_asset_id,
            )
            resolution = self._binding_resolver.resolve_module_binding(
                context=context,
                module_key=module_key,
            )
            _validate_style_extraction_resolution(resolution)
            api_key = self._credential_provider.resolve_api_key(
                context=context,
                credential_ref=resolution.credential_ref,
            )
            if not isinstance(api_key, str) or not api_key.strip():
                raise LLMFacilityError("LLM_CREDENTIAL_UNAVAILABLE", "resolved credential was empty")
            messages = _style_extraction_messages(
                context=context,
                material_text=resolved_material_text,
                source_asset_id=source_asset_id,
                scope=scope,
                options=options,
            )
            if self._quota_gate is None:
                response_json = self._chat_client.complete_json(
                    context=context,
                    resolution=resolution,
                    api_key=api_key.strip(),
                    messages=messages,
                )
                candidates = [_style_profile_candidate(response_json.get("style_profile"))]
            else:
                candidates = self._quota_gate.execute_json(
                    context=context,
                    resolution=resolution,
                    stage="style_extraction",
                    call_index=0,
                    input_texts=[message["content"] for message in messages],
                    provider=lambda provider_call_id: self._chat_client.complete_json(
                        context=context,
                        resolution=resolution,
                        api_key=api_key.strip(),
                        messages=messages,
                        provider_call_id=provider_call_id,
                    ),
                    validate=lambda response: [_style_profile_candidate(response.get("style_profile"))],
                )
            candidate_batch_id = f"style-extraction:{context.run_id}"
            persisted = self._candidate_writer.write_candidates(
                context=context,
                candidate_batch_id=candidate_batch_id,
                model_id=resolution.model_id,
                scope=scope,
                candidates=candidates,
            )
        except LLMFacilityError as exc:
            return _style_runner_failed(exc.code, exc.message)
        except Exception as exc:
            return _style_runner_failed("LLM_PROVIDER_ERROR", str(exc))

        return {
            "status": "completed",
            "module_key": STYLE_EXTRACTION_MODULE_KEY,
            "model_id": resolution.model_id,
            "candidate_batch_id": candidate_batch_id,
            "candidate_count": persisted.get("candidate_count", len(candidates)),
            "asset_type_counts": persisted.get("asset_type_counts", {"style_profile": len(candidates)}),
        }

    def _resolve_material_text(
        self,
        *,
        context: AgentContext,
        material_text: str | None,
        source_asset_id: str | None,
    ) -> str:
        if isinstance(material_text, str) and material_text.strip():
            return material_text.strip()
        if not isinstance(source_asset_id, str) or not source_asset_id.strip():
            raise LLMFacilityError("STYLE_SOURCE_MATERIAL_UNAVAILABLE", "style source material is unavailable")
        if self._source_material_loader is None:
            raise LLMFacilityError(
                "STYLE_SOURCE_MATERIAL_UNAVAILABLE",
                "source asset material loader is not configured",
            )
        loaded = self._source_material_loader.load_material(
            context=context,
            source_asset_id=source_asset_id.strip(),
        )
        if not isinstance(loaded, str) or not loaded.strip():
            raise LLMFacilityError("STYLE_SOURCE_MATERIAL_UNAVAILABLE", "style source material is unavailable")
        return loaded.strip()


class PostgresAssetCandidateWriter:
    def __init__(self, *, connect: Callable[[], Any], source_kind: str = "asset_ingestion") -> None:
        self._connect = connect
        self._source_kind = _required_text(source_kind, "source_kind")

    @classmethod
    def from_database_url(
        cls,
        database_url: str,
        *,
        source_kind: str = "asset_ingestion",
    ) -> "PostgresAssetCandidateWriter":
        try:
            import psycopg
        except ImportError as exc:  # pragma: no cover - depends on runtime packaging
            raise RuntimeError("psycopg is required for DATABASE_URL asset candidate writes") from exc

        return cls(connect=lambda: psycopg.connect(database_url), source_kind=source_kind)

    def write_candidates(
        self,
        *,
        context: AgentContext,
        candidate_batch_id: str,
        model_id: str | None,
        scope: str,
        candidates: list[dict[str, Any]],
    ) -> dict[str, Any]:
        if not context.project_id:
            raise LLMFacilityError("VALIDATION_FAILED", "project_id is required to write asset candidates")
        normalized_batch_id = _required_text(candidate_batch_id, "candidate_batch_id")
        normalized_scope = _asset_scope(scope)
        normalized_candidates = _candidate_list(candidates)
        normalized_source_kind = _required_text(self._source_kind, "source_kind")
        connection = self._connect()
        try:
            set_postgres_tenant_context(connection, context=context)
            with connection.cursor() as cursor:
                for index, candidate in enumerate(normalized_candidates):
                    asset_type = _required_text(candidate.get("asset_type"), "asset_type")
                    title = _required_text(candidate.get("title"), "title")
                    summary = _optional_text(candidate.get("summary"))
                    category = _optional_text(candidate.get("category"))
                    tags = _candidate_tags(candidate.get("tags"))
                    payload = _candidate_payload(candidate.get("payload"))
                    if model_id:
                        payload["model_id"] = model_id
                    source_ref = f"{normalized_batch_id}:{index + 1}"
                    cursor.execute(
                        """INSERT INTO assets (
                             tenant_id, project_id, scope, asset_type, category, lifecycle,
                             title, summary, content_text, payload_jsonb, tags_jsonb,
                             source_kind, source_ref, enabled, pinned, created_by
                           )
                           VALUES (
                             %s, %s, %s, %s, %s, 'candidate',
                             %s, %s, %s, %s::jsonb, %s::jsonb,
                             %s, %s, true, false, %s
                           )
                           ON CONFLICT (tenant_id, project_id, source_kind, source_ref, asset_type, title)
                           DO UPDATE SET
                             scope = EXCLUDED.scope,
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
                            normalized_scope,
                            asset_type,
                            category,
                            title,
                            summary,
                            summary,
                            json.dumps(payload, ensure_ascii=False, separators=(",", ":")),
                            json.dumps(tags, ensure_ascii=False, separators=(",", ":")),
                            normalized_source_kind,
                            source_ref,
                            _uuid_or_none(context.actor_user_id),
                        ),
                    )
                    cursor.fetchone()
            connection.commit()
        except LLMFacilityError:
            raise
        except Exception as exc:
            raise LLMFacilityError("ASSET_CANDIDATE_WRITE_FAILED", str(exc)) from exc
        finally:
            connection.close()
        return {
            "status": "completed",
            "candidate_batch_id": normalized_batch_id,
            "candidate_count": len(normalized_candidates),
            "asset_type_counts": _count_candidate_types(normalized_candidates),
        }


class PostgresStyleSourceMaterialLoader:
    def __init__(self, *, connect: Callable[[], Any]) -> None:
        self._connect = connect

    @classmethod
    def from_database_url(cls, database_url: str) -> "PostgresStyleSourceMaterialLoader":
        try:
            import psycopg
        except ImportError as exc:  # pragma: no cover - depends on runtime packaging
            raise RuntimeError("psycopg is required for DATABASE_URL style source material reads") from exc

        return cls(connect=lambda: psycopg.connect(database_url))

    def load_material(self, *, context: AgentContext, source_asset_id: str) -> str:
        if not context.project_id:
            raise LLMFacilityError("STYLE_SOURCE_MATERIAL_UNAVAILABLE", "project_id is required to load style source material")
        normalized_asset_id = _required_text(source_asset_id, "source_asset_id")
        connection = self._connect()
        try:
            set_postgres_tenant_context(connection, context=context)
            with connection.cursor() as cursor:
                cursor.execute(
                    """SELECT content_text
                       FROM assets
                       WHERE tenant_id = %s
                         AND project_id = %s
                         AND asset_id = %s
                         AND enabled = true
                       LIMIT 1""",
                    (context.tenant_id, context.project_id, normalized_asset_id),
                )
                row = cursor.fetchone()
        except LLMFacilityError:
            raise
        except Exception as exc:
            raise LLMFacilityError("STYLE_SOURCE_MATERIAL_UNAVAILABLE", "style source material is unavailable") from exc
        finally:
            connection.close()
        content_text = _row_value(row, "content_text", 0)
        if not isinstance(content_text, str) or not content_text.strip():
            raise LLMFacilityError("STYLE_SOURCE_MATERIAL_UNAVAILABLE", "style source material is unavailable")
        return content_text.strip()


class PostgresAssetReindexer:
    def __init__(
        self,
        *,
        connect: Callable[[], Any],
        binding_resolver: ModuleBindingResolver | None = None,
        credential_provider: CredentialProvider | None = None,
        embedding_client: EmbeddingClient | None = None,
        quota_gate: ProviderQuotaGate | None = None,
    ) -> None:
        self._connect = connect
        self._binding_resolver = binding_resolver
        self._credential_provider = credential_provider
        self._embedding_client = embedding_client
        self._quota_gate = quota_gate

    @classmethod
    def from_database_url(cls, database_url: str) -> "PostgresAssetReindexer":
        try:
            import psycopg
        except ImportError as exc:  # pragma: no cover - depends on runtime packaging
            raise RuntimeError("psycopg is required for DATABASE_URL asset reindexing") from exc

        return cls(
            connect=lambda: psycopg.connect(database_url),
            binding_resolver=PostgresModuleBindingResolver.from_database_url(database_url),
            credential_provider=PostgresCredentialProvider.from_database_url(
                database_url=database_url,
                key_material=os.environ.get("LLM_CREDENTIAL_ENCRYPTION_KEY"),
            ),
            embedding_client=OpenAICompatibleEmbeddingClient(),
            quota_gate=ProviderQuotaGate(PostgresQuotaStore.from_database_url(database_url)),
        )

    def reindex(
        self,
        *,
        context: AgentContext,
        scope: str,
        mode: str,
        options: dict[str, Any],
    ) -> dict[str, Any]:
        if not context.project_id:
            raise LLMFacilityError("VALIDATION_FAILED", "project_id is required to reindex project assets")
        normalized_scope = _asset_reindex_scope(scope)
        normalized_mode = _asset_reindex_mode(mode)
        include_disabled = bool(options.get("include_disabled", False))
        if include_disabled:
            raise LLMFacilityError("VALIDATION_FAILED", "disabled assets cannot be included in search indexes")
        embedding_model: str | None = None
        embedding_assets: list[dict[str, str]] = []
        embeddings: list[list[float]] = []
        manuscript_blocks: list[dict[str, str]] = []
        manuscript_embeddings: list[list[float]] = []
        if normalized_mode in {"vector", "hybrid"}:
            resolution, api_key = self._resolve_embedding_provider(context)
            embedding_model = resolution.model_id
            embedding_assets = self._load_embedding_assets(context)
            manuscript_blocks = self._load_embedding_manuscript_blocks(context)
            embedding_texts = [asset["embedding_text"] for asset in embedding_assets]
            manuscript_texts = [block["embedding_text"] for block in manuscript_blocks]
            all_texts = embedding_texts + manuscript_texts
            all_vectors: list[list[float]] = []
            for call_index, batch in enumerate(_reindex_embedding_batches(all_texts, resolution.settings)):
                if self._quota_gate is not None:
                    batch_vectors = self._quota_gate.execute_embedding(
                        context=context,
                        resolution=resolution,
                        stage="reindex_embedding",
                        call_index=call_index,
                        input_texts=batch,
                        provider=lambda provider_call_id, batch=batch: _embedding_provider_payload(
                            self._embedding_client,
                            context=context,
                            resolution=resolution,
                            api_key=api_key,
                            texts=batch,
                            provider_call_id=provider_call_id,
                        ),
                        validate=lambda response, expected_count=len(batch): _quota_embedding_vectors(
                            response, expected_count=expected_count
                        ),
                    )
                else:
                    batch_vectors = self._embedding_client.embed_texts(
                        context=context,
                        resolution=resolution,
                        api_key=api_key,
                        texts=batch,
                    )
                all_vectors.extend(batch_vectors)
            embeddings = all_vectors[: len(embedding_texts)]
            manuscript_embeddings = all_vectors[len(embedding_texts):]
        reindex_batch_id = f"asset-reindex:{context.run_id}"
        connection = self._connect()
        try:
            set_postgres_tenant_context(connection, context=context)
            with connection.cursor() as cursor:
                cursor.execute(
                    """WITH request_context AS (
                         SELECT
                           %s::uuid AS tenant_id,
                           %s::uuid AS project_id,
                           %s::text AS run_id,
                           %s::boolean AS include_disabled
                       ),
                       deleted_existing AS (
                         DELETE FROM global_search_index search
                         USING request_context request
                         WHERE search.tenant_id = request.tenant_id
                           AND search.project_id = request.project_id
                           AND search.source = 'asset'
                       ),
                       eligible_assets AS (
                         SELECT
                           asset.tenant_id,
                           asset.project_id,
                           asset.asset_id,
                           asset.asset_type,
                           asset.title,
                           asset.summary,
                           asset.content_text,
                           asset.tags_jsonb,
                           asset.payload_jsonb
                         FROM assets asset
                         JOIN request_context request
                           ON request.tenant_id = asset.tenant_id
                          AND request.project_id = asset.project_id
                         WHERE asset.scope = 'project'
                           AND (request.include_disabled OR asset.enabled = true)
                       ),
                       inserted_search AS (
                         INSERT INTO global_search_index (
                           tenant_id,
                           source,
                           source_ref,
                           project_id,
                           entity_type,
                           title,
                           body,
                           tags_jsonb,
                           payload_jsonb
                         )
                         SELECT
                           eligible.tenant_id,
                           'asset',
                           eligible.asset_id::text,
                           eligible.project_id,
                           eligible.asset_type,
                           eligible.title,
                           btrim(COALESCE(eligible.summary, '') || E'\n' || COALESCE(eligible.content_text, '')),
                           CASE
                             WHEN jsonb_typeof(eligible.tags_jsonb) = 'array' THEN eligible.tags_jsonb
                             ELSE '[]'::jsonb
                           END,
                           (
                             CASE
                               WHEN jsonb_typeof(eligible.payload_jsonb) = 'object' THEN eligible.payload_jsonb
                               ELSE '{}'::jsonb
                             END
                           ) || jsonb_strip_nulls(jsonb_build_object(
                                  'asset_type', eligible.asset_type,
                                  'asset_id', eligible.asset_id,
                                  'summary', eligible.summary,
                                  'reindex_run_id', (SELECT run_id FROM request_context)
                                ))
                         FROM eligible_assets eligible
                         ON CONFLICT (tenant_id, project_id, source, source_ref)
                         DO UPDATE SET
                           project_id = EXCLUDED.project_id,
                           entity_type = EXCLUDED.entity_type,
                           title = EXCLUDED.title,
                           body = EXCLUDED.body,
                           tags_jsonb = EXCLUDED.tags_jsonb,
                           payload_jsonb = EXCLUDED.payload_jsonb,
                           updated_at = now()
                         RETURNING search_document_id
                       )
                       SELECT
                         (SELECT count(*)::int FROM eligible_assets) AS asset_count,
                         (SELECT count(*)::int FROM inserted_search) AS search_document_count,
                         0::int AS embedding_count""",
                    (
                        context.tenant_id,
                        context.project_id,
                        context.run_id,
                        include_disabled,
                    ),
                )
                row = cursor.fetchone()
                asset_count = _non_negative_int(_row_value(row, "asset_count", 0), "asset_count")
                if normalized_mode in {"vector", "hybrid"}:
                    if asset_count != len(embedding_assets):
                        raise LLMFacilityError("ASSET_REINDEX_SOURCE_CHANGED", "asset source changed during reindex")
                    self._replace_embeddings(
                        cursor=cursor,
                        context=context,
                        embedding_model=embedding_model or "",
                        reindex_batch_id=reindex_batch_id,
                        assets=embedding_assets,
                        embeddings=embeddings,
                    )
                    self._replace_manuscript_embeddings(
                        cursor=cursor,
                        context=context,
                        embedding_model=embedding_model or "",
                        reindex_batch_id=reindex_batch_id,
                        blocks=manuscript_blocks,
                        embeddings=manuscript_embeddings,
                    )
            connection.commit()
        except LLMFacilityError:
            _rollback_quietly(connection)
            raise
        except Exception as exc:
            _rollback_quietly(connection)
            raise LLMFacilityError("ASSET_REINDEX_FAILED", "asset reindex failed") from exc
        finally:
            connection.close()
        result: dict[str, Any] = {
            "status": "completed",
            "module_key": ASSET_REINDEX_MODULE_KEY,
            "reindex_batch_id": reindex_batch_id,
            "asset_count": _non_negative_int(_row_value(row, "asset_count", 0), "asset_count"),
            "search_document_count": _non_negative_int(
                _row_value(row, "search_document_count", 1),
                "search_document_count",
            ),
            "embedding_count": len(embeddings),
            "manuscript_embedding_count": len(manuscript_embeddings),
            "scope": normalized_scope,
            "mode": normalized_mode,
        }
        if embedding_model is not None:
            result["embedding_model"] = embedding_model
        return result

    def _resolve_embedding_provider(
        self,
        context: AgentContext,
    ) -> tuple[ModuleBindingResolution, str]:
        if self._binding_resolver is None or self._credential_provider is None or self._embedding_client is None:
            raise LLMFacilityError(
                "ASSET_EMBEDDING_PROVIDER_UNCONFIGURED",
                "asset embedding provider is not configured",
            )
        resolution = self._binding_resolver.resolve_module_binding(
            context=context,
            module_key=ASSET_REINDEX_MODULE_KEY,
        )
        _validate_asset_reindex_resolution(resolution)
        api_key = self._credential_provider.resolve_api_key(
            context=context,
            credential_ref=resolution.credential_ref,
        )
        if not isinstance(api_key, str) or not api_key.strip():
            raise LLMFacilityError("LLM_CREDENTIAL_UNAVAILABLE", "resolved credential was empty")
        return resolution, api_key.strip()

    def _load_embedding_assets(self, context: AgentContext) -> list[dict[str, str]]:
        connection = self._connect()
        try:
            set_postgres_tenant_context(connection, context=context)
            with connection.cursor() as cursor:
                cursor.execute(
                    """SELECT
                         asset_id::text,
                         title,
                         COALESCE(summary, ''),
                         COALESCE(content_text, ''),
                         updated_at::text
                       FROM assets
                       WHERE tenant_id::text = %s
                         AND project_id::text = %s
                         AND scope = 'project'
                         AND enabled = true
                       ORDER BY asset_id::text ASC""",
                    (context.tenant_id, context.project_id),
                )
                rows = cursor.fetchall()
            connection.commit()
        except LLMFacilityError:
            _rollback_quietly(connection)
            raise
        except Exception as exc:
            _rollback_quietly(connection)
            raise LLMFacilityError("ASSET_REINDEX_FAILED", "asset reindex failed") from exc
        finally:
            connection.close()
        return [
            {
                "asset_id": str(_row_value(row, "asset_id", 0)),
                "embedding_text": _asset_embedding_text(row),
                "source_updated_at": str(_row_value(row, "updated_at", 4)),
            }
            for row in rows
        ]

    @staticmethod
    def _replace_embeddings(
        *,
        cursor: Any,
        context: AgentContext,
        embedding_model: str,
        reindex_batch_id: str,
        assets: list[dict[str, str]],
        embeddings: list[list[float]],
    ) -> None:
        if len(assets) != len(embeddings):
            raise LLMFacilityError("SCHEMA_VALIDATION_FAILED", "embedding count did not match assets")
        cursor.execute(
            """DELETE FROM asset_embeddings
               WHERE tenant_id::text = %s
                 AND project_id::text = %s
                 AND embedding_model = %s""",
            (context.tenant_id, context.project_id, embedding_model),
        )
        for asset, embedding in zip(assets, embeddings, strict=True):
            cursor.execute(
                """INSERT INTO asset_embeddings (
                     tenant_id, asset_id, project_id, embedding_model, dimensions,
                     embedding, content_sha256, reindex_batch_id, source_updated_at
                   )
                   SELECT
                     asset.tenant_id,
                     asset.asset_id,
                     asset.project_id,
                     %s,
                     %s,
                     %s::vector,
                     %s,
                     %s,
                     asset.updated_at
                   FROM assets asset
                   WHERE asset.tenant_id::text = %s
                     AND asset.project_id::text = %s
                     AND asset.asset_id::text = %s
                     AND asset.updated_at::text = %s
                     AND asset.enabled = true
                   RETURNING embedding_id""",
                (
                    embedding_model,
                    len(embedding),
                    _vector_literal(embedding),
                    hashlib.sha256(asset["embedding_text"].encode("utf-8")).hexdigest(),
                    reindex_batch_id,
                    context.tenant_id,
                    context.project_id,
                    asset["asset_id"],
                    asset["source_updated_at"],
                ),
            )
            if cursor.fetchone() is None:
                raise LLMFacilityError("ASSET_REINDEX_SOURCE_CHANGED", "asset source changed during reindex")

    def _load_embedding_manuscript_blocks(self, context: AgentContext) -> list[dict[str, str]]:
        connection = self._connect()
        try:
            set_postgres_tenant_context(connection, context=context)
            with connection.cursor() as cursor:
                cursor.execute(
                    """SELECT
                         block_id::text,
                         COALESCE(content_text, ''),
                         updated_at::text
                       FROM manuscript_blocks
                       WHERE tenant_id::text = %s
                         AND project_id::text = %s
                         AND status = 'active'
                       ORDER BY block_order ASC""",
                    (context.tenant_id, context.project_id),
                )
                rows = cursor.fetchall()
            connection.commit()
        except LLMFacilityError:
            _rollback_quietly(connection)
            raise
        except Exception as exc:
            _rollback_quietly(connection)
            raise LLMFacilityError("ASSET_REINDEX_FAILED", "asset reindex failed") from exc
        finally:
            connection.close()
        return [
            {
                "block_id": str(_row_value(row, "block_id", 0)),
                "embedding_text": str(_row_value(row, "content_text", 1)).strip(),
                "source_updated_at": str(_row_value(row, "updated_at", 2)),
            }
            for row in rows
            if str(_row_value(row, "content_text", 1)).strip()
        ]

    @staticmethod
    def _replace_manuscript_embeddings(
        *,
        cursor: Any,
        context: AgentContext,
        embedding_model: str,
        reindex_batch_id: str,
        blocks: list[dict[str, str]],
        embeddings: list[list[float]],
    ) -> None:
        if len(blocks) != len(embeddings):
            raise LLMFacilityError("SCHEMA_VALIDATION_FAILED", "manuscript embedding count did not match blocks")
        cursor.execute(
            """DELETE FROM manuscript_block_embeddings
               WHERE tenant_id::text = %s
                 AND project_id::text = %s
                 AND embedding_model = %s""",
            (context.tenant_id, context.project_id, embedding_model),
        )
        for block, embedding in zip(blocks, embeddings, strict=True):
            cursor.execute(
                """INSERT INTO manuscript_block_embeddings (
                     tenant_id, block_id, project_id, embedding_model, dimensions,
                     embedding, content_sha256, reindex_batch_id, source_updated_at
                   )
                   SELECT
                     block.tenant_id,
                     block.block_id,
                     block.project_id,
                     %s,
                     %s,
                     %s::vector,
                     %s,
                     %s,
                     block.updated_at
                   FROM manuscript_blocks block
                   WHERE block.tenant_id::text = %s
                     AND block.project_id::text = %s
                     AND block.block_id::text = %s
                     AND block.updated_at::text = %s
                     AND block.status = 'active'
                   RETURNING embedding_id""",
                (
                    embedding_model,
                    len(embedding),
                    _vector_literal(embedding),
                    hashlib.sha256(block["embedding_text"].encode("utf-8")).hexdigest(),
                    reindex_batch_id,
                    context.tenant_id,
                    context.project_id,
                    block["block_id"],
                    block["source_updated_at"],
                ),
            )
            if cursor.fetchone() is None:
                raise LLMFacilityError("ASSET_REINDEX_SOURCE_CHANGED", "manuscript source changed during reindex")


class PostgresAssetReindexStatusWriter:
    def __init__(self, *, connect: Callable[[], Any]) -> None:
        self._connect = connect

    @classmethod
    def from_database_url(cls, database_url: str) -> "PostgresAssetReindexStatusWriter":
        try:
            import psycopg
        except ImportError as exc:  # pragma: no cover - depends on runtime packaging
            raise RuntimeError("psycopg is required for DATABASE_URL asset reindex status writes") from exc
        return cls(connect=lambda: psycopg.connect(database_url))

    def write_status(
        self,
        *,
        context: AgentContext,
        status: str,
        result: dict[str, Any] | None,
        error_code: str | None,
        error_message: str | None,
    ) -> None:
        if status not in {"running", "completed", "failed"}:
            raise LLMFacilityError("VALIDATION_FAILED", "asset reindex workflow status is invalid")
        connection = self._connect()
        try:
            set_postgres_tenant_context(connection, context=context)
            with connection.cursor() as cursor:
                cursor.execute(
                    """UPDATE workflow_runs
                       SET status = %s,
                           progress = CASE WHEN %s = 'completed' THEN 100 ELSE progress END,
                           result_jsonb = %s::jsonb,
                           error_code = %s,
                           error_message = %s,
                           updated_at = now()
                       WHERE tenant_id::text = %s
                         AND project_id::text = %s
                         AND run_id::text = %s
                         AND workflow_type = 'asset_reindex'""",
                    (
                        status,
                        status,
                        json.dumps(_sanitize_asset_value(result), ensure_ascii=False) if result is not None else None,
                        error_code,
                        error_message,
                        context.tenant_id,
                        context.project_id,
                        context.run_id,
                    ),
                )
                if cursor.rowcount != 1:
                    raise LLMFacilityError("WORKFLOW_RUN_NOT_FOUND", "asset reindex workflow run was not found")
            connection.commit()
        except LLMFacilityError:
            _rollback_quietly(connection)
            raise
        except Exception as exc:
            _rollback_quietly(connection)
            raise LLMFacilityError("WORKFLOW_STATUS_WRITE_FAILED", "asset reindex workflow status write failed") from exc
        finally:
            connection.close()


def _base_payload(context: AgentContext) -> dict[str, str | None]:
    return {
        "tenant_id": context.tenant_id,
        "project_id": context.project_id,
        "run_id": context.run_id,
        "workflow_type": context.workflow_type,
        "trace_id": context.trace_id,
    }


def _error_result(
    *,
    base: dict[str, Any],
    code: str,
    message: str,
    extra: dict[str, Any] | None = None,
) -> dict[str, Any]:
    return {
        **base,
        "status": "failed",
        "error": {"code": code, "message": message},
        **(extra or {}),
    }


def _asset_ingestion_runner_from_env() -> AssetIngestionRunner | None:
    database_url = os.environ.get("DATABASE_URL")
    if not database_url:
        return None
    return LLMFacilityAssetIngestionRunner(
        binding_resolver=PostgresModuleBindingResolver.from_database_url(database_url),
        credential_provider=PostgresCredentialProvider.from_database_url(
            database_url=database_url,
            key_material=os.environ.get("LLM_CREDENTIAL_ENCRYPTION_KEY"),
        ),
        chat_client=QuotaAwareJSONChatClient(),
        candidate_writer=PostgresAssetCandidateWriter.from_database_url(database_url),
        quota_gate=ProviderQuotaGate(PostgresQuotaStore.from_database_url(database_url)),
    )


def _workflow_event_writer_from_env() -> WorkflowEventWriter | None:
    try:
        from mirofish_agents.temporal.seed import _workflow_event_writer_from_env as seed_event_writer_from_env
    except Exception:
        return None
    return seed_event_writer_from_env()


def _record_asset_ingestion_event(
    *,
    context: AgentContext,
    event_type: str,
    payload: dict[str, Any],
    workflow_event_writer: WorkflowEventWriter | None,
) -> bool:
    writer = workflow_event_writer if workflow_event_writer is not None else _workflow_event_writer_from_env()
    if writer is None:
        return False
    write_event = getattr(writer, "write_event", None)
    if callable(write_event):
        write_event(
            tenant_id=context.tenant_id,
            project_id=context.project_id,
            run_id=context.run_id,
            event_type=event_type,
            payload=payload,
        )
        return True
    record_workflow_event = getattr(writer, "record_workflow_event", None)
    if not callable(record_workflow_event):
        raise LLMFacilityError("WORKFLOW_EVENT_WRITE_FAILED", "asset workflow event writer is invalid")
    record_workflow_event(context=context, event_type=event_type, payload=payload)
    return True


def _failed_asset_ingestion_result(
    *,
    base: dict[str, Any],
    context: AgentContext,
    code: str,
    message: str,
    public_message: str,
    workflow_event_writer: WorkflowEventWriter | None,
) -> dict[str, Any]:
    event_persisted = _record_asset_ingestion_event(
        context=context,
        event_type="asset.stage.failed",
        payload={
            "stage": "asset_ingestion",
            "activity": "asset_ingestion_activity",
            "status": "failed",
            "module_key": ASSET_INGESTION_MODULE_KEY,
            "error_code": code,
            "message": public_message,
        },
        workflow_event_writer=workflow_event_writer,
    )
    return _error_result(
        base=base,
        code=code,
        message=message,
        extra={
            "stage": "asset_ingestion",
            "module_key": ASSET_INGESTION_MODULE_KEY,
            "stage_event_persisted": event_persisted,
        },
    )


def _completed_asset_ingestion_event(
    *,
    context: AgentContext,
    model_id: str | None,
    candidate_batch_id: str,
    candidate_count: int,
    asset_type_counts: dict[str, int],
    workflow_event_writer: WorkflowEventWriter | None,
) -> bool:
    payload: dict[str, Any] = {
        "stage": "asset_ingestion",
        "activity": "asset_ingestion_activity",
        "status": "completed",
        "module_key": ASSET_INGESTION_MODULE_KEY,
        "candidate_batch_id": candidate_batch_id,
        "candidate_count": candidate_count,
        "asset_type_counts": asset_type_counts,
    }
    if model_id is not None:
        payload["model_id"] = model_id
    return _record_asset_ingestion_event(
        context=context,
        event_type="asset.stage.completed",
        payload=payload,
        workflow_event_writer=workflow_event_writer,
    )


def _completed_style_extraction_event(
    *,
    context: AgentContext,
    model_id: str | None,
    candidate_batch_id: str,
    candidate_count: int,
    asset_type_counts: dict[str, int],
    workflow_event_writer: WorkflowEventWriter | None,
) -> bool:
    payload: dict[str, Any] = {
        "stage": "style_extraction",
        "activity": "style_extraction_activity",
        "status": "completed",
        "module_key": STYLE_EXTRACTION_MODULE_KEY,
        "candidate_batch_id": candidate_batch_id,
        "candidate_count": candidate_count,
        "asset_type_counts": asset_type_counts,
    }
    if model_id is not None:
        payload["model_id"] = model_id
    return _record_asset_ingestion_event(
        context=context,
        event_type="asset.stage.completed",
        payload=payload,
        workflow_event_writer=workflow_event_writer,
    )


def _failed_style_extraction_result(
    *,
    base: dict[str, Any],
    context: AgentContext,
    code: str,
    message: str,
    public_message: str,
    workflow_event_writer: WorkflowEventWriter | None,
) -> dict[str, Any]:
    event_persisted = _record_asset_ingestion_event(
        context=context,
        event_type="asset.stage.failed",
        payload={
            "stage": "style_extraction",
            "activity": "style_extraction_activity",
            "status": "failed",
            "module_key": STYLE_EXTRACTION_MODULE_KEY,
            "error_code": code,
            "message": public_message,
        },
        workflow_event_writer=workflow_event_writer,
    )
    return _error_result(
        base=base,
        code=code,
        message=message,
        extra={
            "stage": "style_extraction",
            "module_key": STYLE_EXTRACTION_MODULE_KEY,
            "stage_event_persisted": event_persisted,
        },
    )


def _style_extraction_runner_from_env() -> StyleExtractionRunner | None:
    database_url = os.environ.get("DATABASE_URL")
    if not database_url:
        return None
    return LLMFacilityStyleExtractionRunner(
        binding_resolver=PostgresModuleBindingResolver.from_database_url(database_url),
        credential_provider=PostgresCredentialProvider.from_database_url(
            database_url=database_url,
            key_material=os.environ.get("LLM_CREDENTIAL_ENCRYPTION_KEY"),
        ),
        chat_client=QuotaAwareJSONChatClient(),
        candidate_writer=PostgresAssetCandidateWriter.from_database_url(
            database_url,
            source_kind="style_extraction",
        ),
        source_material_loader=PostgresStyleSourceMaterialLoader.from_database_url(database_url),
        quota_gate=ProviderQuotaGate(PostgresQuotaStore.from_database_url(database_url)),
    )


def _asset_reindexer_from_env() -> AssetReindexer | None:
    database_url = os.environ.get("DATABASE_URL")
    if not database_url:
        return None
    return PostgresAssetReindexer.from_database_url(database_url)


def _asset_reindex_status_writer_from_env() -> WorkflowStatusWriter | None:
    database_url = os.environ.get("DATABASE_URL")
    if not database_url:
        return None
    return PostgresAssetReindexStatusWriter.from_database_url(database_url)


def _completed_asset_reindex_event(
    *,
    context: AgentContext,
    reindex_batch_id: str,
    asset_count: int,
    search_document_count: int,
    embedding_count: int,
    embedding_model: str | None,
    scope: str,
    mode: str,
    workflow_event_writer: WorkflowEventWriter | None,
) -> bool:
    event_payload: dict[str, Any] = {
        "stage": "asset_reindex",
        "activity": "asset_reindex_activity",
        "status": "completed",
        "module_key": ASSET_REINDEX_MODULE_KEY,
        "reindex_batch_id": reindex_batch_id,
        "asset_count": asset_count,
        "search_document_count": search_document_count,
        "embedding_count": embedding_count,
        "scope": scope,
        "mode": mode,
    }
    if embedding_model is not None:
        event_payload["embedding_model"] = embedding_model
    return _record_asset_ingestion_event(
        context=context,
        event_type="asset.stage.completed",
        payload=event_payload,
        workflow_event_writer=workflow_event_writer,
    )


def _failed_asset_reindex_result(
    *,
    base: dict[str, Any],
    context: AgentContext,
    code: str,
    message: str,
    public_message: str,
    workflow_event_writer: WorkflowEventWriter | None,
    workflow_status_writer: WorkflowStatusWriter | None = None,
) -> dict[str, Any]:
    event_persisted = _record_asset_ingestion_event(
        context=context,
        event_type="asset.stage.failed",
        payload={
            "stage": "asset_reindex",
            "activity": "asset_reindex_activity",
            "status": "failed",
            "module_key": ASSET_REINDEX_MODULE_KEY,
            "error_code": code,
            "message": public_message,
        },
        workflow_event_writer=workflow_event_writer,
    )
    status_persisted = False
    if workflow_status_writer is not None:
        try:
            workflow_status_writer.write_status(
                context=context,
                status="failed",
                result=None,
                error_code=code,
                error_message=public_message,
            )
            status_persisted = True
        except Exception:
            status_persisted = False
    return _error_result(
        base=base,
        code=code,
        message=message,
        extra={
            "stage": "asset_reindex",
            "module_key": ASSET_REINDEX_MODULE_KEY,
            "stage_event_persisted": event_persisted,
            "workflow_status_persisted": status_persisted,
        },
    )


def _public_style_extraction_error_message(code: str) -> str:
    if code == "LLM_MODULE_UNBOUND":
        return "style_extractor module is unbound"
    if code == "SCHEMA_VALIDATION_FAILED":
        return "style extraction output schema validation failed"
    if code == "STYLE_EXTRACTION_RUNNER_UNCONFIGURED":
        return "style extraction runner is unconfigured"
    if code == "STYLE_SOURCE_MATERIAL_UNAVAILABLE":
        return "style source material is unavailable"
    return "style extraction failed"


def _optional_text(value: Any) -> str | None:
    if value is None:
        return None
    if not isinstance(value, str) or not value.strip():
        raise ValueError("optional text value must be a non-empty string")
    return value.strip()


def _row_value(row: Any, key: str, index: int = 0) -> Any:
    if row is None:
        return None
    if isinstance(row, dict):
        return row.get(key)
    return row[index]


def _required_text(value: Any, field_name: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{field_name} is required")
    return value.strip()


def _non_negative_int(value: Any, field_name: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        raise ValueError(f"{field_name} must be a non-negative integer")
    return value


def _asset_type_counts(value: Any) -> dict[str, int]:
    if value is None:
        return {}
    if not isinstance(value, dict):
        raise ValueError("asset_type_counts must be an object")
    counts: dict[str, int] = {}
    for key, count in value.items():
        if not isinstance(key, str) or not key.strip():
            raise ValueError("asset_type_counts keys must be non-empty strings")
        counts[key.strip()] = _non_negative_int(count, f"asset_type_counts.{key}")
    return counts


def _public_asset_ingestion_error_message(code: str) -> str:
    if code == "LLM_MODULE_UNBOUND":
        return "asset_ingestion module is unbound"
    if code == "SCHEMA_VALIDATION_FAILED":
        return "asset ingestion output schema validation failed"
    if code == "ASSET_INGESTION_RUNNER_UNCONFIGURED":
        return "asset ingestion runner is unconfigured"
    return "asset ingestion failed"


def _public_asset_reindex_error_message(code: str) -> str:
    if code == "ASSET_REINDEXER_UNCONFIGURED":
        return "asset reindexer is unconfigured"
    if code == "ASSET_EMBEDDING_PROVIDER_UNCONFIGURED":
        return "asset embedding provider is unconfigured"
    if code == "LLM_MODULE_UNBOUND":
        return "asset_reindex module is unbound"
    if code in {"LLM_CREDENTIAL_UNAVAILABLE", "LLM_CREDENTIAL_KEY_UNCONFIGURED"}:
        return "asset embedding credential is unavailable"
    if code == "ASSET_REINDEX_SOURCE_CHANGED":
        return "asset source changed during reindex"
    if code == "SCHEMA_VALIDATION_FAILED":
        return "asset reindex output schema validation failed"
    if code == "VALIDATION_FAILED":
        return "asset reindex request is invalid"
    return "asset reindex failed"


def _runner_failed(code: str, message: str) -> dict[str, Any]:
    return {
        "status": "failed",
        "module_key": ASSET_INGESTION_MODULE_KEY,
        "error": {"code": code, "message": message},
    }


def _style_runner_failed(code: str, message: str) -> dict[str, Any]:
    return {
        "status": "failed",
        "module_key": STYLE_EXTRACTION_MODULE_KEY,
        "error": {"code": code, "message": message},
    }


def _validate_asset_ingestion_resolution(resolution: ModuleBindingResolution) -> None:
    if resolution.module_key != ASSET_INGESTION_MODULE_KEY:
        raise LLMFacilityError("LLM_MODULE_UNBOUND", "resolved module key does not match asset_ingestion")
    if not resolution.supports_json:
        raise LLMFacilityError("LLM_MODULE_CAPABILITY_MISSING", "asset_ingestion requires a JSON-capable model")
    for field_name in ("channel_id", "model_id", "base_url", "credential_ref"):
        value = getattr(resolution, field_name)
        if not isinstance(value, str) or not value.strip():
            raise LLMFacilityError("LLM_PROVIDER_ERROR", f"resolved LLM module is missing {field_name}")


def _validate_style_extraction_resolution(resolution: ModuleBindingResolution) -> None:
    if resolution.module_key != STYLE_EXTRACTION_MODULE_KEY:
        raise LLMFacilityError("LLM_MODULE_UNBOUND", "resolved module key does not match style_extractor")
    if not resolution.supports_json:
        raise LLMFacilityError("LLM_MODULE_CAPABILITY_MISSING", "style_extractor requires a JSON-capable model")
    for field_name in ("channel_id", "model_id", "base_url", "credential_ref"):
        value = getattr(resolution, field_name)
        if not isinstance(value, str) or not value.strip():
            raise LLMFacilityError("LLM_PROVIDER_ERROR", f"resolved LLM module is missing {field_name}")


def _asset_ingestion_messages(
    *,
    context: AgentContext,
    material_text: str,
    hint_type: str | None,
    scope: str,
    options: dict[str, Any],
) -> list[dict[str, str]]:
    if not isinstance(material_text, str) or not material_text.strip():
        raise LLMFacilityError("VALIDATION_FAILED", "material_text is required")
    public_options = _sanitize_asset_value(options)
    return [
        {
            "role": "system",
            "content": (
                "You are the MiroFish asset ingestion module. Return one JSON object with a candidates array. "
                "Each candidate must include asset_type, title, and summary, with optional category, tags, and payload. "
                "Do not include prompt bodies, raw source material copies, API keys, credentials, or provider metadata."
            ),
        },
        {
            "role": "user",
            "content": json.dumps(
                {
                    "tenant_id": context.tenant_id,
                    "project_id": context.project_id,
                    "run_id": context.run_id,
                    "module_key": ASSET_INGESTION_MODULE_KEY,
                    "hint_type": hint_type,
                    "scope": scope,
                    "options": public_options,
                    "material_text": material_text.strip(),
                },
                ensure_ascii=False,
                separators=(",", ":"),
            ),
        },
    ]


def _style_extraction_messages(
    *,
    context: AgentContext,
    material_text: str,
    source_asset_id: str | None,
    scope: str,
    options: dict[str, Any],
) -> list[dict[str, str]]:
    if not isinstance(material_text, str) or not material_text.strip():
        raise LLMFacilityError("VALIDATION_FAILED", "material_text is required")
    public_options = _sanitize_asset_value(options)
    return [
        {
            "role": "system",
            "content": (
                "You are the MiroFish style_extractor module. Return one JSON object with a style_profile object. "
                "The style_profile must include title and summary, with optional tags and payload. "
                "Do not include quoted source samples, prompt bodies, raw source material copies, API keys, "
                "credentials, or provider metadata."
            ),
        },
        {
            "role": "user",
            "content": json.dumps(
                {
                    "tenant_id": context.tenant_id,
                    "project_id": context.project_id,
                    "run_id": context.run_id,
                    "module_key": STYLE_EXTRACTION_MODULE_KEY,
                    "source_asset_id": source_asset_id,
                    "scope": scope,
                    "options": public_options,
                    "material_text": material_text.strip(),
                },
                ensure_ascii=False,
                separators=(",", ":"),
            ),
        },
    ]


def _style_profile_candidate(value: Any) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise LLMFacilityError("SCHEMA_VALIDATION_FAILED", "style_profile must be an object")
    title = _candidate_required_text(value.get("title"), "style_profile.title")
    summary = _candidate_required_text(value.get("summary"), "style_profile.summary")
    payload_source: dict[str, Any] = {}
    raw_payload = value.get("payload")
    if raw_payload is not None:
        payload_source = _candidate_payload(raw_payload)
    for key, child in value.items():
        if key not in {"title", "summary", "category", "tags", "payload"}:
            payload_source[key] = child
    return {
        "asset_type": "style_profile",
        "category": _candidate_optional_text(value.get("category")) or "writing_style",
        "title": title,
        "summary": summary,
        "payload": _candidate_payload(payload_source),
        "tags": _candidate_tags(value.get("tags")),
    }


def _candidate_list(value: Any) -> list[dict[str, Any]]:
    if not isinstance(value, list):
        raise LLMFacilityError("SCHEMA_VALIDATION_FAILED", "candidates must be an array")
    candidates: list[dict[str, Any]] = []
    for index, item in enumerate(value):
        if not isinstance(item, dict):
            raise LLMFacilityError("SCHEMA_VALIDATION_FAILED", f"candidates[{index}] must be an object")
        asset_type = _candidate_required_text(item.get("asset_type"), f"candidates[{index}].asset_type")
        title = _candidate_required_text(item.get("title"), f"candidates[{index}].title")
        summary = _candidate_optional_text(item.get("summary"))
        if summary is None:
            raise LLMFacilityError("SCHEMA_VALIDATION_FAILED", f"candidates[{index}].summary is required")
        normalized: dict[str, Any] = {
            "asset_type": asset_type,
            "title": title,
            "summary": summary,
            "payload": _candidate_payload(item.get("payload")),
            "tags": _candidate_tags(item.get("tags")),
        }
        category = _candidate_optional_text(item.get("category"))
        if category is not None:
            normalized["category"] = category
        candidates.append(normalized)
    return candidates


def _candidate_payload(value: Any) -> dict[str, Any]:
    if value is None:
        return {}
    sanitized = _sanitize_asset_value(value)
    if not isinstance(sanitized, dict):
        raise LLMFacilityError("SCHEMA_VALIDATION_FAILED", "candidate payload must be an object")
    return sanitized


def _candidate_tags(value: Any) -> list[str]:
    if value is None:
        return []
    if not isinstance(value, list):
        raise LLMFacilityError("SCHEMA_VALIDATION_FAILED", "candidate tags must be an array")
    tags: list[str] = []
    for tag in value:
        if isinstance(tag, str) and tag.strip() and tag.strip().lower() not in SENSITIVE_ASSET_KEYS:
            tags.append(tag.strip())
    return tags


def _sanitize_asset_value(value: Any) -> Any:
    if isinstance(value, dict):
        return {
            str(key): _sanitize_asset_value(child)
            for key, child in value.items()
            if str(key).lower() not in SENSITIVE_ASSET_KEYS
        }
    if isinstance(value, list):
        return [_sanitize_asset_value(item) for item in value]
    return value


def _count_candidate_types(candidates: list[dict[str, Any]]) -> dict[str, int]:
    counts: dict[str, int] = {}
    for candidate in candidates:
        asset_type = candidate.get("asset_type")
        if isinstance(asset_type, str) and asset_type.strip():
            normalized = asset_type.strip()
            counts[normalized] = counts.get(normalized, 0) + 1
    return counts


def _asset_scope(value: str) -> str:
    normalized = value.strip() if isinstance(value, str) else "project"
    if normalized not in {"tenant", "project", "system"}:
        raise LLMFacilityError("VALIDATION_FAILED", "asset candidate scope is invalid")
    return normalized


def _asset_reindex_scope(value: str) -> str:
    normalized = value.strip() if isinstance(value, str) else "project"
    if not normalized:
        normalized = "project"
    if normalized not in {"project"}:
        raise LLMFacilityError("VALIDATION_FAILED", "only project asset reindexing is currently supported")
    return normalized


def _asset_reindex_mode(value: str) -> str:
    normalized = value.strip() if isinstance(value, str) else "keyword"
    if not normalized:
        normalized = "keyword"
    if normalized not in {"keyword", "vector", "hybrid"}:
        raise LLMFacilityError("VALIDATION_FAILED", "asset reindex mode must be keyword, vector, or hybrid")
    return normalized


def _validate_asset_reindex_resolution(resolution: ModuleBindingResolution) -> None:
    if resolution.module_key != ASSET_REINDEX_MODULE_KEY:
        raise LLMFacilityError("LLM_MODULE_UNBOUND", "resolved module key does not match asset_reindex")
    for field_name in ("channel_id", "model_id", "provider", "base_url", "credential_ref"):
        value = getattr(resolution, field_name)
        if not isinstance(value, str) or not value.strip():
            raise LLMFacilityError("LLM_PROVIDER_ERROR", f"resolved LLM module is missing {field_name}")


def _asset_embedding_text(row: Any) -> str:
    parts = [
        _row_value(row, "title", 1),
        _row_value(row, "summary", 2),
        _row_value(row, "content_text", 3),
    ]
    return "\n".join(str(part).strip() for part in parts if isinstance(part, str) and part.strip())


def _embedding_vector(value: Any) -> list[float]:
    if not isinstance(value, list) or not value:
        raise LLMFacilityError("SCHEMA_VALIDATION_FAILED", "embedding must be a non-empty array")
    vector: list[float] = []
    for component in value:
        if isinstance(component, bool) or not isinstance(component, (int, float)):
            raise LLMFacilityError("SCHEMA_VALIDATION_FAILED", "embedding components must be numbers")
        normalized = float(component)
        if not math.isfinite(normalized):
            raise LLMFacilityError("SCHEMA_VALIDATION_FAILED", "embedding components must be finite")
        vector.append(normalized)
    return vector


def _embedding_usage(value: Any) -> dict[str, int] | None:
    if not isinstance(value, dict):
        return None
    prompt_tokens = _embedding_non_negative_int(
        value.get("prompt_tokens") if "prompt_tokens" in value else value.get("input_tokens")
    )
    total_tokens = _embedding_non_negative_int(value.get("total_tokens"))
    if prompt_tokens is None:
        prompt_tokens = total_tokens
    if prompt_tokens is None:
        return None
    if total_tokens is None:
        total_tokens = prompt_tokens
    if total_tokens < prompt_tokens:
        return None
    return {
        "prompt_tokens": prompt_tokens,
        "completion_tokens": total_tokens - prompt_tokens,
        "total_tokens": total_tokens,
    }


def _embedding_non_negative_int(value: Any) -> int | None:
    if isinstance(value, bool):
        return None
    if isinstance(value, int) and value >= 0:
        return value
    if isinstance(value, float) and value >= 0 and value.is_integer():
        return int(value)
    return None


def _embedding_provider_payload(
    client: EmbeddingClient,
    *,
    context: AgentContext,
    resolution: ModuleBindingResolution,
    api_key: str,
    texts: list[str],
    provider_call_id: str,
) -> dict[str, Any]:
    vectors = client.embed_texts(
        context=context,
        resolution=resolution,
        api_key=api_key,
        texts=texts,
        provider_call_id=provider_call_id,
    )
    return {
        "vectors": [list(vector) for vector in vectors],
        "__llm_usage": getattr(vectors, "llm_usage", None),
    }


def _reindex_embedding_batches(texts: list[str], settings: dict[str, Any]) -> list[list[str]]:
    """Keep provider requests bounded while preserving corpus order."""
    max_tokens = _positive_reindex_setting(settings, "embedding_batch_max_tokens", 8192)
    max_items = _positive_reindex_setting(settings, "embedding_batch_size", 64)
    batches: list[list[str]] = []
    current: list[str] = []
    current_tokens = 0
    for text in texts:
        text_tokens = max(1, _estimate_tokens(text))
        if current and (len(current) >= max_items or current_tokens + text_tokens > max_tokens):
            batches.append(current)
            current = []
            current_tokens = 0
        current.append(text)
        current_tokens += text_tokens
    if current:
        batches.append(current)
    return batches


def _positive_reindex_setting(settings: dict[str, Any], key: str, default: int) -> int:
    value = settings.get(key)
    if isinstance(value, int) and not isinstance(value, bool) and value > 0:
        return min(value, 4096 if key == "embedding_batch_size" else 262_144)
    return default


def _quota_embedding_vectors(response: dict[str, Any], *, expected_count: int) -> list[list[float]]:
    raw_vectors = response.get("vectors")
    if not isinstance(raw_vectors, list) or len(raw_vectors) != expected_count:
        raise LLMFacilityError("SCHEMA_VALIDATION_FAILED", "embedding response count did not match input count")
    vectors = [_embedding_vector(value) for value in raw_vectors]
    if len({len(vector) for vector in vectors}) > 1:
        raise LLMFacilityError("SCHEMA_VALIDATION_FAILED", "embedding dimensions were inconsistent")
    return vectors


def _vector_literal(vector: list[float]) -> str:
    return "[" + ",".join(format(component, ".17g") for component in vector) + "]"


def _embeddings_url(base_url: str) -> str:
    normalized = base_url.strip().rstrip("/")
    if normalized.endswith("/embeddings"):
        return normalized
    return f"{normalized}/embeddings"


def _urlopen_bytes(request: Request) -> bytes:
    with urlopen(request) as response:  # noqa: S310 - URL comes from an authorized LLM Facility channel
        return read_response_limited(
            response,
            max_bytes=response_limit_from_env("MIROFISH_LLM_MAX_RESPONSE_BYTES", 16 * 1024 * 1024),
        )


def _rollback_quietly(connection: Any) -> None:
    try:
        connection.rollback()
    except Exception:
        pass


def _candidate_required_text(value: Any, field_name: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise LLMFacilityError("SCHEMA_VALIDATION_FAILED", f"{field_name} is required")
    return value.strip()


def _candidate_optional_text(value: Any) -> str | None:
    if value is None:
        return None
    if not isinstance(value, str) or not value.strip():
        raise LLMFacilityError("SCHEMA_VALIDATION_FAILED", "optional candidate text must be a non-empty string")
    return value.strip()


def _uuid_or_none(value: str | None) -> str | None:
    if not isinstance(value, str) or not value.strip():
        return None
    try:
        return str(uuid.UUID(value))
    except ValueError:
        return None


@activity.defn
def style_extraction_activity(
    payload: dict[str, Any],
    style_extraction_runner: StyleExtractionRunner | None = None,
    workflow_event_writer: WorkflowEventWriter | None = None,
) -> dict[str, Any]:
    context = AgentContext.model_validate(payload.get("context", payload))
    base = _base_payload(context)
    if not context.has_permission("style_extractor", "run"):
        return _error_result(
            base=base,
            code="FORBIDDEN",
            message="style_extractor run permission is required",
            extra={"stage": "style_extraction", "module_key": STYLE_EXTRACTION_MODULE_KEY},
        )
    if context.module_key is not None and context.module_key != STYLE_EXTRACTION_MODULE_KEY:
        return _failed_style_extraction_result(
            base=base,
            context=context,
            code="VALIDATION_FAILED",
            message=f"module_key must be {STYLE_EXTRACTION_MODULE_KEY}",
            public_message="style extraction module key is invalid",
            workflow_event_writer=workflow_event_writer,
        )
    material_text = payload.get("material_text")
    source_asset_id = payload.get("source_asset_id")
    normalized_material = material_text.strip() if isinstance(material_text, str) and material_text.strip() else None
    normalized_source_asset_id = source_asset_id.strip() if isinstance(source_asset_id, str) and source_asset_id.strip() else None
    if normalized_material is None and normalized_source_asset_id is None:
        return _failed_style_extraction_result(
            base=base,
            context=context,
            code="VALIDATION_FAILED",
            message="material_text or source_asset_id is required",
            public_message="style extraction source is missing",
            workflow_event_writer=workflow_event_writer,
        )
    try:
        scope = _optional_text(payload.get("scope")) or "project"
    except Exception as exc:
        return _failed_style_extraction_result(
            base=base,
            context=context,
            code="VALIDATION_FAILED",
            message=str(exc),
            public_message="style extraction request is invalid",
            workflow_event_writer=workflow_event_writer,
        )
    options = payload.get("options") if isinstance(payload.get("options"), dict) else {}
    runner = style_extraction_runner if style_extraction_runner is not None else _style_extraction_runner_from_env()
    if runner is None:
        return _failed_style_extraction_result(
            base=base,
            context=context,
            code="STYLE_EXTRACTION_RUNNER_UNCONFIGURED",
            message=(
                "style extraction requires an LLM Facility backed runner for "
                f"{STYLE_EXTRACTION_MODULE_KEY}"
            ),
            public_message="style extraction runner is unconfigured",
            workflow_event_writer=workflow_event_writer,
        )
    try:
        extraction_result = runner.extract_style(
            context=context,
            module_key=STYLE_EXTRACTION_MODULE_KEY,
            material_text=normalized_material,
            source_asset_id=normalized_source_asset_id,
            scope=scope,
            options=_sanitize_asset_value(options),
        )
    except Exception:
        return _failed_style_extraction_result(
            base=base,
            context=context,
            code="LLM_PROVIDER_ERROR",
            message="style extraction runner failed",
            public_message="style extraction failed",
            workflow_event_writer=workflow_event_writer,
        )
    if extraction_result.get("status") != "completed":
        error = extraction_result.get("error") if isinstance(extraction_result.get("error"), dict) else {}
        code = error.get("code") if isinstance(error.get("code"), str) else "LLM_PROVIDER_ERROR"
        return _failed_style_extraction_result(
            base=base,
            context=context,
            code=code,
            message=_public_style_extraction_error_message(code),
            public_message=_public_style_extraction_error_message(code),
            workflow_event_writer=workflow_event_writer,
        )
    try:
        module_key = _optional_text(extraction_result.get("module_key")) or STYLE_EXTRACTION_MODULE_KEY
        if module_key != STYLE_EXTRACTION_MODULE_KEY:
            raise ValueError(f"module_key must be {STYLE_EXTRACTION_MODULE_KEY}")
        model_id = _optional_text(extraction_result.get("model_id"))
        candidate_batch_id = _required_text(extraction_result.get("candidate_batch_id"), "candidate_batch_id")
        candidate_count = _non_negative_int(extraction_result.get("candidate_count", 0), "candidate_count")
        asset_type_counts = _asset_type_counts(extraction_result.get("asset_type_counts"))
    except Exception as exc:
        return _failed_style_extraction_result(
            base=base,
            context=context,
            code="SCHEMA_VALIDATION_FAILED",
            message=str(exc),
            public_message="style extraction output schema validation failed",
            workflow_event_writer=workflow_event_writer,
        )
    event_persisted = _completed_style_extraction_event(
        context=context,
        model_id=model_id,
        candidate_batch_id=candidate_batch_id,
        candidate_count=candidate_count,
        asset_type_counts=asset_type_counts,
        workflow_event_writer=workflow_event_writer,
    )
    result: dict[str, Any] = {
        **base,
        "status": "completed",
        "stage": "style_extraction",
        "module_key": STYLE_EXTRACTION_MODULE_KEY,
        "candidate_batch_id": candidate_batch_id,
        "candidate_count": candidate_count,
        "asset_type_counts": asset_type_counts,
        "stage_event_persisted": event_persisted,
    }
    if model_id is not None:
        result["model_id"] = model_id
    return result


@activity.defn
def asset_ingestion_activity(
    payload: dict[str, Any],
    asset_ingestion_runner: AssetIngestionRunner | None = None,
    workflow_event_writer: WorkflowEventWriter | None = None,
) -> dict[str, Any]:
    context = AgentContext.model_validate(payload.get("context", payload))
    base = _base_payload(context)
    if not context.has_permission("asset_ingestion", "run"):
        return _error_result(
            base=base,
            code="FORBIDDEN",
            message="asset_ingestion run permission is required",
            extra={"stage": "asset_ingestion", "module_key": ASSET_INGESTION_MODULE_KEY},
        )
    if context.module_key is not None and context.module_key != ASSET_INGESTION_MODULE_KEY:
        return _failed_asset_ingestion_result(
            base=base,
            context=context,
            code="VALIDATION_FAILED",
            message=f"module_key must be {ASSET_INGESTION_MODULE_KEY}",
            public_message="asset ingestion module key is invalid",
            workflow_event_writer=workflow_event_writer,
        )
    material_text = payload.get("material_text")
    if not isinstance(material_text, str) or not material_text.strip():
        return _failed_asset_ingestion_result(
            base=base,
            context=context,
            code="VALIDATION_FAILED",
            message="material_text is required",
            public_message="asset ingestion material is missing",
            workflow_event_writer=workflow_event_writer,
        )
    try:
        hint_type = _optional_text(payload.get("hint_type"))
        scope = _optional_text(payload.get("scope")) or "project"
    except Exception as exc:
        return _failed_asset_ingestion_result(
            base=base,
            context=context,
            code="VALIDATION_FAILED",
            message=str(exc),
            public_message="asset ingestion request is invalid",
            workflow_event_writer=workflow_event_writer,
        )
    options = payload.get("options") if isinstance(payload.get("options"), dict) else {}
    runner = asset_ingestion_runner if asset_ingestion_runner is not None else _asset_ingestion_runner_from_env()
    if runner is None:
        return _failed_asset_ingestion_result(
            base=base,
            context=context,
            code="ASSET_INGESTION_RUNNER_UNCONFIGURED",
            message=(
                "asset ingestion requires an LLM Facility backed runner for "
                f"{ASSET_INGESTION_MODULE_KEY}"
            ),
            public_message="asset ingestion runner is unconfigured",
            workflow_event_writer=workflow_event_writer,
        )
    try:
        ingestion_result = runner.ingest(
            context=context,
            module_key=ASSET_INGESTION_MODULE_KEY,
            material_text=material_text.strip(),
            hint_type=hint_type,
            scope=scope,
            options=options,
        )
    except Exception:
        return _failed_asset_ingestion_result(
            base=base,
            context=context,
            code="LLM_PROVIDER_ERROR",
            message="asset ingestion runner failed",
            public_message="asset ingestion failed",
            workflow_event_writer=workflow_event_writer,
        )
    if ingestion_result.get("status") != "completed":
        error = ingestion_result.get("error") if isinstance(ingestion_result.get("error"), dict) else {}
        code = error.get("code") if isinstance(error.get("code"), str) else "LLM_PROVIDER_ERROR"
        return _failed_asset_ingestion_result(
            base=base,
            context=context,
            code=code,
            message=_public_asset_ingestion_error_message(code),
            public_message=_public_asset_ingestion_error_message(code),
            workflow_event_writer=workflow_event_writer,
        )
    try:
        module_key = _optional_text(ingestion_result.get("module_key")) or ASSET_INGESTION_MODULE_KEY
        if module_key != ASSET_INGESTION_MODULE_KEY:
            raise ValueError(f"module_key must be {ASSET_INGESTION_MODULE_KEY}")
        model_id = _optional_text(ingestion_result.get("model_id"))
        candidate_batch_id = _required_text(ingestion_result.get("candidate_batch_id"), "candidate_batch_id")
        candidate_count = _non_negative_int(ingestion_result.get("candidate_count", 0), "candidate_count")
        asset_type_counts = _asset_type_counts(ingestion_result.get("asset_type_counts"))
    except Exception as exc:
        return _failed_asset_ingestion_result(
            base=base,
            context=context,
            code="SCHEMA_VALIDATION_FAILED",
            message=str(exc),
            public_message="asset ingestion output schema validation failed",
            workflow_event_writer=workflow_event_writer,
        )
    event_persisted = _completed_asset_ingestion_event(
        context=context,
        model_id=model_id,
        candidate_batch_id=candidate_batch_id,
        candidate_count=candidate_count,
        asset_type_counts=asset_type_counts,
        workflow_event_writer=workflow_event_writer,
    )
    result: dict[str, Any] = {
        **base,
        "status": "completed",
        "stage": "asset_ingestion",
        "module_key": ASSET_INGESTION_MODULE_KEY,
        "candidate_batch_id": candidate_batch_id,
        "candidate_count": candidate_count,
        "asset_type_counts": asset_type_counts,
        "stage_event_persisted": event_persisted,
    }
    if model_id is not None:
        result["model_id"] = model_id
    return result


@activity.defn
def asset_reindex_activity(
    payload: dict[str, Any],
    asset_reindexer: AssetReindexer | None = None,
    workflow_event_writer: WorkflowEventWriter | None = None,
    workflow_status_writer: WorkflowStatusWriter | None = None,
) -> dict[str, Any]:
    context = AgentContext.model_validate(payload.get("context", payload))
    base = _base_payload(context)
    status_writer = (
        workflow_status_writer
        if workflow_status_writer is not None
        else _asset_reindex_status_writer_from_env()
    )
    if not context.has_permission(ASSET_REINDEX_MODULE_KEY, "run"):
        return _error_result(
            base=base,
            code="FORBIDDEN",
            message="asset_reindex run permission is required",
            extra={"stage": "asset_reindex", "module_key": ASSET_REINDEX_MODULE_KEY},
        )
    if context.module_key is not None and context.module_key != ASSET_REINDEX_MODULE_KEY:
        return _failed_asset_reindex_result(
            base=base,
            context=context,
            code="VALIDATION_FAILED",
            message=f"module_key must be {ASSET_REINDEX_MODULE_KEY}",
            public_message="asset reindex module key is invalid",
            workflow_event_writer=workflow_event_writer,
            workflow_status_writer=status_writer,
        )
    try:
        scope = _asset_reindex_scope(_optional_text(payload.get("scope")) or "project")
        mode = _asset_reindex_mode(_optional_text(payload.get("mode")) or "keyword")
    except Exception as exc:
        return _failed_asset_reindex_result(
            base=base,
            context=context,
            code="VALIDATION_FAILED",
            message=str(exc),
            public_message="asset reindex request is invalid",
            workflow_event_writer=workflow_event_writer,
            workflow_status_writer=status_writer,
        )
    options = payload.get("options") if isinstance(payload.get("options"), dict) else {}
    reindexer = asset_reindexer if asset_reindexer is not None else _asset_reindexer_from_env()
    if reindexer is None:
        return _failed_asset_reindex_result(
            base=base,
            context=context,
            code="ASSET_REINDEXER_UNCONFIGURED",
            message="asset reindexer requires DATABASE_URL backed storage",
            public_message="asset reindexer is unconfigured",
            workflow_event_writer=workflow_event_writer,
            workflow_status_writer=status_writer,
        )
    try:
        reindex_result = reindexer.reindex(
            context=context,
            scope=scope,
            mode=mode,
            options=_sanitize_asset_value(options),
        )
    except LLMFacilityError as exc:
        return _failed_asset_reindex_result(
            base=base,
            context=context,
            code=exc.code,
            message=exc.message,
            public_message=_public_asset_reindex_error_message(exc.code),
            workflow_event_writer=workflow_event_writer,
            workflow_status_writer=status_writer,
        )
    except Exception:
        return _failed_asset_reindex_result(
            base=base,
            context=context,
            code="ASSET_REINDEX_FAILED",
            message="asset reindexer failed",
            public_message="asset reindex failed",
            workflow_event_writer=workflow_event_writer,
            workflow_status_writer=status_writer,
        )
    if reindex_result.get("status") != "completed":
        error = reindex_result.get("error") if isinstance(reindex_result.get("error"), dict) else {}
        code = error.get("code") if isinstance(error.get("code"), str) else "ASSET_REINDEX_FAILED"
        return _failed_asset_reindex_result(
            base=base,
            context=context,
            code=code,
            message=_public_asset_reindex_error_message(code),
            public_message=_public_asset_reindex_error_message(code),
            workflow_event_writer=workflow_event_writer,
            workflow_status_writer=status_writer,
        )
    try:
        module_key = _optional_text(reindex_result.get("module_key")) or ASSET_REINDEX_MODULE_KEY
        if module_key != ASSET_REINDEX_MODULE_KEY:
            raise ValueError(f"module_key must be {ASSET_REINDEX_MODULE_KEY}")
        reindex_batch_id = _required_text(reindex_result.get("reindex_batch_id"), "reindex_batch_id")
        asset_count = _non_negative_int(reindex_result.get("asset_count", 0), "asset_count")
        search_document_count = _non_negative_int(
            reindex_result.get("search_document_count", 0),
            "search_document_count",
        )
        embedding_count = _non_negative_int(reindex_result.get("embedding_count", 0), "embedding_count")
        embedding_model = _optional_text(reindex_result.get("embedding_model"))
    except Exception as exc:
        return _failed_asset_reindex_result(
            base=base,
            context=context,
            code="SCHEMA_VALIDATION_FAILED",
            message=str(exc),
            public_message="asset reindex output schema validation failed",
            workflow_event_writer=workflow_event_writer,
            workflow_status_writer=status_writer,
        )
    status_result: dict[str, Any] = {
        "stage": "asset_reindex",
        "module_key": ASSET_REINDEX_MODULE_KEY,
        "reindex_batch_id": reindex_batch_id,
        "asset_count": asset_count,
        "search_document_count": search_document_count,
        "embedding_count": embedding_count,
        "scope": scope,
        "mode": mode,
    }
    if embedding_model is not None:
        status_result["embedding_model"] = embedding_model
    status_persisted = False
    if status_writer is not None:
        try:
            status_writer.write_status(
                context=context,
                status="completed",
                result=status_result,
                error_code=None,
                error_message=None,
            )
            status_persisted = True
        except LLMFacilityError as exc:
            return _failed_asset_reindex_result(
                base=base,
                context=context,
                code=exc.code,
                message=exc.message,
                public_message="asset reindex workflow status write failed",
                workflow_event_writer=workflow_event_writer,
            )
        except Exception:
            return _failed_asset_reindex_result(
                base=base,
                context=context,
                code="WORKFLOW_STATUS_WRITE_FAILED",
                message="asset reindex workflow status write failed",
                public_message="asset reindex workflow status write failed",
                workflow_event_writer=workflow_event_writer,
            )
    event_persisted = _completed_asset_reindex_event(
        context=context,
        reindex_batch_id=reindex_batch_id,
        asset_count=asset_count,
        search_document_count=search_document_count,
        embedding_count=embedding_count,
        embedding_model=embedding_model,
        scope=scope,
        mode=mode,
        workflow_event_writer=workflow_event_writer,
    )
    result = {
        **base,
        "status": "completed",
        "stage": "asset_reindex",
        "module_key": ASSET_REINDEX_MODULE_KEY,
        "reindex_batch_id": reindex_batch_id,
        "asset_count": asset_count,
        "search_document_count": search_document_count,
        "embedding_count": embedding_count,
        "scope": scope,
        "mode": mode,
        "stage_event_persisted": event_persisted,
        "workflow_status_persisted": status_persisted,
    }
    if embedding_model is not None:
        result["embedding_model"] = embedding_model
    return result


@workflow.defn
class AssetIngestionWorkflow:
    @workflow.run
    async def run(self, payload: dict[str, Any]) -> dict[str, Any]:
        return await workflow.execute_activity(
            asset_ingestion_activity,
            payload,
            start_to_close_timeout=timedelta(minutes=20),
            retry_policy=ASSET_ACTIVITY_RETRY_POLICY,
        )


@workflow.defn
class StyleExtractionWorkflow:
    @workflow.run
    async def run(self, payload: dict[str, Any]) -> dict[str, Any]:
        return await workflow.execute_activity(
            style_extraction_activity,
            payload,
            start_to_close_timeout=timedelta(minutes=20),
            retry_policy=ASSET_ACTIVITY_RETRY_POLICY,
        )


@workflow.defn
class AssetReindexWorkflow:
    @workflow.run
    async def run(self, payload: dict[str, Any]) -> dict[str, Any]:
        return await workflow.execute_activity(
            asset_reindex_activity,
            payload,
            start_to_close_timeout=timedelta(minutes=20),
            retry_policy=ASSET_ACTIVITY_RETRY_POLICY,
        )


def run_asset_ingestion_workflow_locally(
    payload: dict[str, Any],
    *,
    asset_ingestion_runner: AssetIngestionRunner | None = None,
    workflow_event_writer: WorkflowEventWriter | None = None,
) -> dict[str, Any]:
    return asset_ingestion_activity(
        payload,
        asset_ingestion_runner=asset_ingestion_runner,
        workflow_event_writer=workflow_event_writer,
    )


def run_style_extraction_workflow_locally(
    payload: dict[str, Any],
    *,
    style_extraction_runner: StyleExtractionRunner | None = None,
    workflow_event_writer: WorkflowEventWriter | None = None,
) -> dict[str, Any]:
    return style_extraction_activity(
        payload,
        style_extraction_runner=style_extraction_runner,
        workflow_event_writer=workflow_event_writer,
    )


def run_asset_reindex_workflow_locally(
    payload: dict[str, Any],
    *,
    asset_reindexer: AssetReindexer | None = None,
    workflow_event_writer: WorkflowEventWriter | None = None,
) -> dict[str, Any]:
    return asset_reindex_activity(
        payload,
        asset_reindexer=asset_reindexer,
        workflow_event_writer=workflow_event_writer,
    )


def worker_spec() -> dict[str, list[str] | str]:
    return {
        "task_queue": ASSET_TASK_QUEUE,
        "workflows": [
            AssetIngestionWorkflow.__name__,
            StyleExtractionWorkflow.__name__,
            AssetReindexWorkflow.__name__,
        ],
        "activities": [
            asset_ingestion_activity.__name__,
            style_extraction_activity.__name__,
            asset_reindex_activity.__name__,
        ],
    }
