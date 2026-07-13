from __future__ import annotations

import hashlib
import json
import os
import re
from datetime import timedelta
from typing import Any, Callable
from uuid import UUID, uuid4

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


MODULE_KEY = "writer_asset_distiller"
WORKFLOW_TYPE = "manuscript_asset_distillation"
WORKFLOW_NAME = "ManuscriptAssetDistillationWorkflow"
TASK_QUEUE = "writer-planning"
CONTRACT_VERSION = 1
SUPPORTED_TYPES = {
    "character",
    "organization",
    "location",
    "item",
    "world_rule",
    "relationship",
    "event",
    "plot_thread",
    "terminology",
}


def _ctx(payload: dict[str, Any]) -> AgentContext:
    context = payload.get("context") or {}
    return AgentContext(
        tenant_id=str(context["tenant_id"]),
        project_id=str(context["project_id"]),
        run_id=str(context["run_id"]),
        actor_user_id=str(context.get("actor_user_id") or "") or None,
        module_key=MODULE_KEY,
        workflow_type=WORKFLOW_TYPE,
        trace_id=str(context.get("trace_id") or f"trace_{context['run_id']}"),
        permissions=context.get("permissions") or {MODULE_KEY: ["run"]},
    )


class PostgresManuscriptAssetDistillationStore:
    def __init__(self, *, connect: Callable[[], Any]) -> None:
        self._connect = connect

    @classmethod
    def from_database_url(cls, database_url: str) -> "PostgresManuscriptAssetDistillationStore":
        import psycopg

        return cls(connect=lambda: psycopg.connect(database_url))

    def validate_sources(self, *, context: AgentContext, request_id: str) -> dict[str, Any]:
        with self._connect() as conn:
            set_postgres_tenant_context(conn, context=context)
            with conn.cursor() as cur:
                cur.execute(
                    """
                    SELECT request_id::text, trigger_kind, source_manifest_jsonb::text, input_fingerprint
                    FROM manuscript_asset_distillation_requests
                    WHERE tenant_id=%s::uuid AND project_id=%s::uuid AND run_id=%s::uuid
                    """,
                    (context.tenant_id, context.project_id, context.run_id),
                )
                row = cur.fetchone()
                if row is None:
                    raise LLMFacilityError("DISTILLATION_REQUEST_NOT_FOUND", "distillation request was not found")
                request_id_db, trigger_kind, manifest_raw, fingerprint = row
                manifest = json.loads(manifest_raw)
                sources = list(manifest.get("sources") or [])
                if not sources:
                    raise LLMFacilityError("DISTILLATION_SOURCE_EMPTY", "distillation source manifest is empty")
                validated: list[dict[str, Any]] = []
                for source in sources:
                    block_id = str(source["block_id"])
                    block_version = int(source["block_version"])
                    content_sha = str(source["content_sha256"])
                    cur.execute(
                        """
                        SELECT content_text, version, status, COALESCE(chapter_id::text,''), COALESCE(scene_id::text,''),
                               COALESCE(source_draft_id::text,'')
                        FROM manuscript_blocks
                        WHERE tenant_id=%s::uuid AND project_id=%s::uuid AND block_id=%s::uuid
                        """,
                        (context.tenant_id, context.project_id, block_id),
                    )
                    block = cur.fetchone()
                    if block is None:
                        raise LLMFacilityError("DISTILLATION_SOURCE_NOT_FOUND", "manuscript block was not found")
                    content, version, status, chapter_id, scene_id, source_draft = block
                    digest = hashlib.sha256(content.encode("utf-8")).hexdigest()
                    if status != "active" or int(version) != block_version or digest != content_sha:
                        self._complete_stale(cur, context, reason="source_version_drift")
                        conn.commit()
                        return {"stale": True, "source_count": len(sources), "candidate_count": 0}
                    if not source_draft and trigger_kind != "manual":
                        raise LLMFacilityError("DISTILLATION_SOURCE_NOT_ADOPTED", "automatic distillation requires adopted manuscript")
                    validated.append(
                        {
                            "block_id": block_id,
                            "block_version": block_version,
                            "content_sha256": content_sha,
                            "content_text": content,
                            "chapter_id": chapter_id or None,
                            "scene_id": scene_id or None,
                        }
                    )
                conn.commit()
                return {
                    "stale": False,
                    "request_id": request_id_db,
                    "trigger_kind": trigger_kind,
                    "input_fingerprint": fingerprint,
                    "sources": validated,
                    "source_count": len(validated),
                }

    def distill(self, *, context: AgentContext, validated: dict[str, Any], resolution: ModuleBindingResolution,
                response: dict[str, Any]) -> dict[str, Any]:
        candidates = validate_model_candidates(response, validated["sources"])
        with self._connect() as conn:
            set_postgres_tenant_context(conn, context=context)
            with conn.cursor() as cur:
                # Load existing assets for identity resolution
                cur.execute(
                    """
                    SELECT asset_id::text, asset_type, title, COALESCE(summary,''), lifecycle, enabled
                    FROM assets
                    WHERE tenant_id=%s::uuid AND project_id=%s::uuid
                      AND lifecycle IN ('seed','canon','material') AND enabled=TRUE
                    """,
                    (context.tenant_id, context.project_id),
                )
                existing = [
                    {
                        "asset_id": r[0],
                        "asset_type": r[1],
                        "title": r[2],
                        "summary": r[3],
                        "lifecycle": r[4],
                        "enabled": r[5],
                    }
                    for r in cur.fetchall()
                ]
                counts = {"create": 0, "update": 0, "conflict": 0, "dropped": 0}
                written = 0
                for candidate in candidates:
                    decision = resolve_identity(candidate, existing)
                    if not candidate.get("evidence"):
                        counts["dropped"] += 1
                        continue
                    identity = normalize_identity(candidate["asset_type"], candidate["title"], candidate.get("identity_hints") or [])
                    source_ref = f"{validated['request_id']}:{identity}"
                    cur.execute(
                        """
                        INSERT INTO assets (
                          tenant_id, project_id, scope, asset_type, category, lifecycle, title, summary,
                          payload_jsonb, tags_jsonb, source_kind, source_ref, enabled, pinned, created_by
                        ) VALUES (
                          %s::uuid, %s::uuid, 'project', %s, %s, 'candidate', %s, %s,
                          %s::jsonb, %s::jsonb, 'manuscript_distillation', %s, FALSE, FALSE, NULLIF(%s,'')::uuid
                        )
                        ON CONFLICT (tenant_id, project_id, source_kind, source_ref, asset_type, title)
                        DO UPDATE SET summary=EXCLUDED.summary, payload_jsonb=EXCLUDED.payload_jsonb,
                          lifecycle='candidate', enabled=FALSE, updated_at=now()
                        RETURNING asset_id::text
                        """,
                        (
                            context.tenant_id,
                            context.project_id,
                            candidate["asset_type"],
                            candidate.get("category") or candidate["asset_type"],
                            candidate["title"],
                            candidate.get("summary") or "",
                            json.dumps(candidate.get("payload") or {}),
                            json.dumps(candidate.get("tags") or []),
                            source_ref,
                            context.actor_user_id or "",
                        ),
                    )
                    asset_id = cur.fetchone()[0]
                    operation = decision["operation"]
                    review_status = "staging"
                    target_id = decision.get("target_asset_id")
                    expected_version = decision.get("expected_target_version")
                    if operation == "conflict":
                        review_status = "conflict"
                        counts["conflict"] += 1
                    elif operation == "update":
                        counts["update"] += 1
                    else:
                        counts["create"] += 1
                    cur.execute(
                        """
                        INSERT INTO asset_candidate_proposals (
                          tenant_id, project_id, candidate_asset_id, request_id, operation,
                          target_asset_id, expected_target_version, normalized_identity, confidence, review_status
                        ) VALUES (
                          %s::uuid, %s::uuid, %s::uuid, %s::uuid, %s,
                          NULLIF(%s,'')::uuid, %s, %s, %s, %s
                        )
                        ON CONFLICT (candidate_asset_id) DO UPDATE SET
                          operation=EXCLUDED.operation,
                          target_asset_id=EXCLUDED.target_asset_id,
                          expected_target_version=EXCLUDED.expected_target_version,
                          normalized_identity=EXCLUDED.normalized_identity,
                          confidence=EXCLUDED.confidence,
                          review_status=EXCLUDED.review_status,
                          updated_at=now()
                        """,
                        (
                            context.tenant_id,
                            context.project_id,
                            asset_id,
                            validated["request_id"],
                            "update" if operation == "update" else "create",
                            target_id or "",
                            expected_version,
                            identity,
                            candidate.get("confidence"),
                            review_status,
                        ),
                    )
                    for evidence in candidate["evidence"]:
                        cur.execute(
                            """
                            INSERT INTO asset_candidate_evidence (
                              tenant_id, project_id, candidate_asset_id, block_id, block_version,
                              content_sha256, start_offset, end_offset, evidence_text, confidence
                            ) VALUES (
                              %s::uuid, %s::uuid, %s::uuid, %s::uuid, %s,
                              %s, %s, %s, %s, %s
                            )
                            ON CONFLICT DO NOTHING
                            """,
                            (
                                context.tenant_id,
                                context.project_id,
                                asset_id,
                                evidence["block_id"],
                                evidence["block_version"],
                                evidence["content_sha256"],
                                evidence["start_offset"],
                                evidence["end_offset"],
                                evidence["quote"],
                                candidate.get("confidence"),
                            ),
                        )
                    written += 1
                conn.commit()
                return {"candidate_count": written, "counts": counts, "source_count": validated["source_count"]}

    def finalize(self, *, context: AgentContext, result: dict[str, Any], resolution: ModuleBindingResolution | None) -> dict[str, Any]:
        with self._connect() as conn:
            set_postgres_tenant_context(conn, context=context)
            with conn.cursor() as cur:
                # Promote staging create/update to pending; supersede older pending same identity
                cur.execute(
                    """
                    UPDATE asset_candidate_proposals p
                    SET review_status='pending', updated_at=now()
                    FROM manuscript_asset_distillation_requests r
                    WHERE p.tenant_id=r.tenant_id AND p.request_id=r.request_id
                      AND r.tenant_id=%s::uuid AND r.project_id=%s::uuid AND r.run_id=%s::uuid
                      AND p.review_status='staging'
                    """,
                    (context.tenant_id, context.project_id, context.run_id),
                )
                cur.execute(
                    """
                    UPDATE asset_candidate_proposals older
                    SET review_status='superseded', updated_at=now()
                    FROM asset_candidate_proposals newer
                    JOIN manuscript_asset_distillation_requests r
                      ON r.tenant_id=newer.tenant_id AND r.request_id=newer.request_id
                    WHERE older.tenant_id=%s::uuid AND older.project_id=%s::uuid
                      AND older.review_status='pending'
                      AND newer.tenant_id=older.tenant_id AND newer.project_id=older.project_id
                      AND newer.normalized_identity=older.normalized_identity
                      AND newer.candidate_asset_id<>older.candidate_asset_id
                      AND newer.review_status='pending'
                      AND r.run_id=%s::uuid
                      AND older.created_at < newer.created_at
                    """,
                    (context.tenant_id, context.project_id, context.run_id),
                )
                public = {
                    "status": "completed",
                    "source_count": int(result.get("source_count") or 0),
                    "candidate_count": int(result.get("candidate_count") or 0),
                    "create_count": int((result.get("counts") or {}).get("create") or 0),
                    "update_count": int((result.get("counts") or {}).get("update") or 0),
                    "conflict_count": int((result.get("counts") or {}).get("conflict") or 0),
                    "module_key": MODULE_KEY,
                }
                if resolution is not None:
                    public["model_id"] = resolution.model_id
                cur.execute(
                    """
                    UPDATE workflow_runs
                    SET status='completed', progress=100, message='completed', result_jsonb=%s::jsonb, updated_at=now()
                    WHERE tenant_id=%s::uuid AND project_id=%s::uuid AND run_id=%s::uuid
                    """,
                    (json.dumps(public), context.tenant_id, context.project_id, context.run_id),
                )
                cur.execute(
                    """
                    INSERT INTO workflow_events (
                      tenant_id, run_id, workflow_type, project_id, event_type, sequence, payload_jsonb
                    )
                    SELECT %s::uuid, %s::uuid, %s, %s::uuid, 'workflow.completed',
                           COALESCE(MAX(sequence),0)+1, %s::jsonb
                    FROM workflow_events WHERE tenant_id=%s::uuid AND run_id=%s::uuid
                    """,
                    (
                        context.tenant_id,
                        context.run_id,
                        WORKFLOW_TYPE,
                        context.project_id,
                        json.dumps(public),
                        context.tenant_id,
                        context.run_id,
                    ),
                )
                conn.commit()
                return public

    def fail(self, *, context: AgentContext, code: str, message: str) -> None:
        with self._connect() as conn:
            set_postgres_tenant_context(conn, context=context)
            with conn.cursor() as cur:
                cur.execute(
                    """
                    UPDATE workflow_runs
                    SET status='failed', message=%s, error_code=%s, error_message=%s, updated_at=now()
                    WHERE tenant_id=%s::uuid AND run_id=%s::uuid
                    """,
                    (message, code, message, context.tenant_id, context.run_id),
                )
                payload = json.dumps({"status": "failed", "error_code": code})
                cur.execute(
                    """
                    INSERT INTO workflow_events (
                      tenant_id, run_id, workflow_type, project_id, event_type, sequence, payload_jsonb
                    )
                    SELECT %s::uuid, %s::uuid, %s, %s::uuid, 'workflow.failed',
                           COALESCE(MAX(sequence),0)+1, %s::jsonb
                    FROM workflow_events WHERE tenant_id=%s::uuid AND run_id=%s::uuid
                    """,
                    (
                        context.tenant_id,
                        context.run_id,
                        WORKFLOW_TYPE,
                        context.project_id,
                        payload,
                        context.tenant_id,
                        context.run_id,
                    ),
                )
                conn.commit()

    def _complete_stale(self, cur: Any, context: AgentContext, *, reason: str) -> None:
        public = {
            "status": "completed",
            "stale": True,
            "source_count": 0,
            "candidate_count": 0,
            "error_code": "DISTILLATION_SOURCE_STALE",
            "reason": reason,
            "module_key": MODULE_KEY,
        }
        cur.execute(
            """
            UPDATE workflow_runs
            SET status='completed', progress=100, message='source stale', result_jsonb=%s::jsonb, updated_at=now()
            WHERE tenant_id=%s::uuid AND run_id=%s::uuid
            """,
            (json.dumps(public), context.tenant_id, context.run_id),
        )


def normalize_identity(asset_type: str, title: str, hints: list[str]) -> str:
    parts = [asset_type.strip().lower(), re.sub(r"\s+", " ", title.strip().lower())]
    for hint in hints:
        cleaned = re.sub(r"\s+", " ", str(hint).strip().lower())
        if cleaned and cleaned not in parts:
            parts.append(cleaned)
    return "|".join(parts)


def resolve_identity(candidate: dict[str, Any], existing: list[dict[str, Any]]) -> dict[str, Any]:
    identity = normalize_identity(candidate["asset_type"], candidate["title"], candidate.get("identity_hints") or [])
    hits = []
    for asset in existing:
        asset_identity = normalize_identity(asset["asset_type"], asset["title"], [])
        if asset_identity == identity or asset["title"].strip().lower() == candidate["title"].strip().lower() and asset["asset_type"] == candidate["asset_type"]:
            hits.append(asset)
    if len(hits) == 1:
        return {"operation": "update", "target_asset_id": hits[0]["asset_id"], "expected_target_version": 1}
    if len(hits) > 1:
        return {"operation": "conflict"}
    return {"operation": "create"}


def validate_model_candidates(response: dict[str, Any], sources: list[dict[str, Any]]) -> list[dict[str, Any]]:
    items = response.get("candidates")
    if not isinstance(items, list):
        raise LLMFacilityError("DISTILLATION_OUTPUT_INVALID", "distiller output candidates must be a list")
    by_block = {s["block_id"]: s for s in sources}
    out: list[dict[str, Any]] = []
    for item in items:
        if not isinstance(item, dict):
            continue
        asset_type = str(item.get("asset_type") or "").strip()
        title = str(item.get("title") or "").strip()
        if asset_type not in SUPPORTED_TYPES or not title:
            continue
        evidence_in = item.get("evidence") or []
        if not isinstance(evidence_in, list):
            continue
        valid_evidence = []
        for ev in evidence_in:
            if not isinstance(ev, dict):
                continue
            block_id = str(ev.get("block_id") or "")
            source = by_block.get(block_id)
            if source is None:
                continue
            quote = str(ev.get("quote") or "")
            try:
                start = int(ev.get("start_offset"))
                end = int(ev.get("end_offset"))
            except (TypeError, ValueError):
                start, end = -1, -1
            text = source["content_text"]
            if start >= 0 and end > start and end <= len(text) and text[start:end] == quote:
                valid_evidence.append(
                    {
                        "block_id": block_id,
                        "block_version": source["block_version"],
                        "content_sha256": source["content_sha256"],
                        "start_offset": start,
                        "end_offset": end,
                        "quote": quote,
                    }
                )
                continue
            # exact unique quote lookup fallback
            if quote and text.count(quote) == 1:
                idx = text.index(quote)
                valid_evidence.append(
                    {
                        "block_id": block_id,
                        "block_version": source["block_version"],
                        "content_sha256": source["content_sha256"],
                        "start_offset": idx,
                        "end_offset": idx + len(quote),
                        "quote": quote,
                    }
                )
        if not valid_evidence:
            continue
        conf = item.get("confidence")
        try:
            confidence = float(conf) if conf is not None else None
        except (TypeError, ValueError):
            confidence = None
        out.append(
            {
                "local_id": str(item.get("local_id") or uuid4()),
                "asset_type": asset_type,
                "title": title,
                "summary": str(item.get("summary") or ""),
                "category": str(item.get("category") or asset_type),
                "tags": list(item.get("tags") or []),
                "payload": dict(item.get("payload") or {}),
                "identity_hints": list(item.get("identity_hints") or []),
                "confidence": confidence,
                "evidence": valid_evidence,
            }
        )
    return out


def _messages(sources: list[dict[str, Any]]) -> list[dict[str, str]]:
    parts = []
    for source in sources:
        parts.append(
            f"[block_id={source['block_id']} version={source['block_version']}]\n{source['content_text']}"
        )
    body = "\n\n".join(parts)
    return [
        {
            "role": "system",
            "content": (
                "You extract structured story assets from adopted manuscript text. "
                "Return JSON object {\"candidates\":[...]}. Each candidate needs asset_type, title, summary, "
                "identity_hints, confidence, and evidence with block_id, start_offset, end_offset, quote. "
                "Evidence quote must be an exact substring of the provided block text. "
                f"Supported asset_type values: {', '.join(sorted(SUPPORTED_TYPES))}."
            ),
        },
        {"role": "user", "content": body},
    ]


class LLMFacilityManuscriptAssetDistiller:
    def __init__(
        self,
        *,
        binding_resolver: ModuleBindingResolver,
        credential_provider: CredentialProvider,
        chat_client: JSONChatClient,
        store: PostgresManuscriptAssetDistillationStore,
    ) -> None:
        self._binding_resolver = binding_resolver
        self._credential_provider = credential_provider
        self._chat_client = chat_client
        self._store = store

    def run(self, *, payload: dict[str, Any]) -> dict[str, Any]:
        context = _ctx(payload)
        try:
            validated = self._store.validate_sources(context=context, request_id=str(payload.get("request_id") or ""))
            if validated.get("stale"):
                return self._store.finalize(context=context, result=validated, resolution=None)
            resolution = self._binding_resolver.resolve_module_binding(context=context, module_key=MODULE_KEY)
            if not resolution.supports_json:
                raise LLMFacilityError("LLM_CAPABILITY_UNSUPPORTED", "writer_asset_distiller requires JSON capability")
            api_key = self._credential_provider.resolve_api_key(
                context=context, credential_ref=resolution.credential_ref
            )
            response = self._chat_client.complete_json(
                context=context,
                resolution=resolution,
                api_key=api_key,
                messages=_messages(validated["sources"]),
            )
            distilled = self._store.distill(
                context=context, validated=validated, resolution=resolution, response=response
            )
            return self._store.finalize(context=context, result=distilled, resolution=resolution)
        except Exception as exc:
            code, message = _stable_error(exc)
            try:
                self._store.fail(context=context, code=code, message=message)
            except Exception:
                pass
            raise LLMFacilityError(code, message) from exc


def _stable_error(exc: Exception) -> tuple[str, str]:
    if isinstance(exc, LLMFacilityError):
        return exc.code, "manuscript asset distillation failed"
    if isinstance(exc, ApplicationError):
        return str(exc.type or "DISTILLATION_FAILED"), "manuscript asset distillation failed"
    return "DISTILLATION_FAILED", "manuscript asset distillation failed"


@activity.defn(name="validate_distillation_source_activity")
def validate_distillation_source_activity(payload: dict[str, Any]) -> dict[str, Any]:
    store = _default_store()
    context = _ctx(payload)
    validated = store.validate_sources(context=context, request_id=str(payload.get("request_id") or ""))
    # Never return manuscript body on the activity boundary for public history.
    return {
        "stale": bool(validated.get("stale")),
        "source_count": int(validated.get("source_count") or 0),
        "request_id": validated.get("request_id"),
        "trigger_kind": validated.get("trigger_kind"),
        # private activity-local field consumed only by next activity in same process when needed;
        # Temporal payloads should avoid body: strip sources content for returned value.
        "source_refs": [
            {
                "block_id": s["block_id"],
                "block_version": s["block_version"],
                "content_sha256": s["content_sha256"],
            }
            for s in validated.get("sources") or []
        ],
    }


@activity.defn(name="distill_manuscript_assets_activity")
def distill_manuscript_assets_activity(payload: dict[str, Any]) -> dict[str, Any]:
    return _default_runner().run(payload=payload)


@activity.defn(name="finalize_distillation_activity")
def finalize_distillation_activity(payload: dict[str, Any]) -> dict[str, Any]:
    # Distill activity already finalizes; this is a no-op counts pass-through for workflow shape.
    return {
        "source_count": int(payload.get("source_count") or 0),
        "candidate_count": int(payload.get("candidate_count") or 0),
        "create_count": int(payload.get("create_count") or 0),
        "update_count": int(payload.get("update_count") or 0),
        "conflict_count": int(payload.get("conflict_count") or 0),
    }


@activity.defn(name="manuscript_asset_distillation_failure_activity")
def manuscript_asset_distillation_failure_activity(payload: dict[str, Any]) -> None:
    store = _default_store()
    context = _ctx(payload)
    store.fail(
        context=context,
        code=str(payload.get("error_code") or "DISTILLATION_FAILED"),
        message=str(payload.get("message") or "manuscript asset distillation failed"),
    )


@workflow.defn(name=WORKFLOW_NAME)
class ManuscriptAssetDistillationWorkflow:
    @workflow.run
    async def run(self, payload: dict[str, Any]) -> dict[str, Any]:
        retry = RetryPolicy(maximum_attempts=3)
        try:
            result = await workflow.execute_activity(
                distill_manuscript_assets_activity,
                payload,
                start_to_close_timeout=timedelta(minutes=20),
                retry_policy=retry,
            )
            return result
        except ActivityError as exc:
            await workflow.execute_activity(
                manuscript_asset_distillation_failure_activity,
                {
                    **payload,
                    "error_code": "DISTILLATION_FAILED",
                    "message": "manuscript asset distillation failed",
                },
                start_to_close_timeout=timedelta(minutes=2),
                retry_policy=RetryPolicy(maximum_attempts=1),
            )
            raise ApplicationError("manuscript asset distillation failed", type="DISTILLATION_FAILED") from exc


def _default_store() -> PostgresManuscriptAssetDistillationStore:
    database_url = os.environ.get("DATABASE_URL", "").strip()
    if not database_url:
        raise LLMFacilityError("DATABASE_URL_MISSING", "DATABASE_URL is required")
    return PostgresManuscriptAssetDistillationStore.from_database_url(database_url)


def _default_runner() -> LLMFacilityManuscriptAssetDistiller:
    from mirofish_agents.llm_quota import (
        PostgresQuotaStore,
        ProviderQuotaGate,
        QuotaAwareJSONChatClient,
        QuotaEnforcedJSONChatClient,
    )

    database_url = os.environ.get("DATABASE_URL", "").strip()
    if not database_url:
        raise LLMFacilityError("DATABASE_URL_MISSING", "DATABASE_URL is required")
    store = PostgresManuscriptAssetDistillationStore.from_database_url(database_url)
    return LLMFacilityManuscriptAssetDistiller(
        binding_resolver=PostgresModuleBindingResolver.from_database_url(database_url),
        credential_provider=PostgresCredentialProvider.from_database_url(
            database_url=database_url,
            key_material=os.environ.get("LLM_CREDENTIAL_ENCRYPTION_KEY"),
        ),
        chat_client=QuotaEnforcedJSONChatClient(
            quota_gate=ProviderQuotaGate(PostgresQuotaStore.from_database_url(database_url)),
            stage_prefix="manuscript_asset_distillation",
            provider_client=QuotaAwareJSONChatClient(),
        ),
        store=store,
    )
