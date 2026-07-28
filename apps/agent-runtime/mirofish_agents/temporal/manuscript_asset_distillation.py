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
ASSET_PAYLOAD_GUIDANCE = {
    "character": (
        "canonical_name, aliases, narrative_role, appearance, personality, occupation, affiliations, "
        "abilities, limitations, goals, motivations, relationships, possessions, current_state"
    ),
    "organization": (
        "canonical_name, aliases, organization_type, leaders, members, hierarchy, goals, territory, "
        "resources, rules, relationships, current_state"
    ),
    "location": (
        "canonical_name, aliases, location_type, parent_location, appearance, atmosphere, notable_features, "
        "inhabitants, access_rules, related_events, current_state"
    ),
    "item": (
        "canonical_name, aliases, item_type, appearance, owner, creator, origin, abilities, limitations, "
        "usage, related_characters, current_state"
    ),
    "world_rule": (
        "rule_text, scope, conditions, mechanism, limitations, exceptions, consequences, known_examples"
    ),
    "relationship": (
        "source_entity_name, target_entity_name, relationship_type, direction, history, current_state, "
        "emotional_dynamic, conflicts, obligations, turning_points"
    ),
    "event": (
        "event_type, participants, location, time_order, trigger, actions, outcome, consequences, "
        "related_items, related_threads, status"
    ),
    "plot_thread": (
        "thread_type, setup, participants, clues, current_development, unresolved_questions, stakes, "
        "possible_dependencies, status"
    ),
    "terminology": (
        "canonical_name, aliases, category, definition, usage_context, origin, related_concepts, restrictions"
    ),
}
# Token-aware long-chapter windowing (CONN-011 / W13).
# Estimate ~4 characters per token; target windows of ~6-8k tokens.
CHARS_PER_TOKEN = 4
WINDOW_TOKEN_TARGET = 7000
WINDOW_TOKEN_MAX = 8000
WINDOW_CHAR_TARGET = WINDOW_TOKEN_TARGET * CHARS_PER_TOKEN
WINDOW_CHAR_MAX = WINDOW_TOKEN_MAX * CHARS_PER_TOKEN


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
                settings_types = self._load_enabled_asset_types(cur, context=context)
                manifest_types = manifest.get("enabled_asset_types")
                enabled_asset_types = resolve_enabled_asset_types(
                    manifest_types if isinstance(manifest_types, list) else settings_types
                )
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
                    content, version, status, chapter_id, scene_id, _source_draft = block
                    digest = hashlib.sha256(content.encode("utf-8")).hexdigest()
                    if status != "active" or int(version) != block_version or digest != content_sha:
                        self._complete_stale(cur, context, reason="source_version_drift")
                        conn.commit()
                        return {"stale": True, "source_count": len(sources), "candidate_count": 0}
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
                    "enabled_asset_types": enabled_asset_types,
                }

    def _load_enabled_asset_types(self, cur: Any, *, context: AgentContext) -> list[str]:
        cur.execute(
            """
            SELECT COALESCE(array_to_string(enabled_asset_types, ','), '')
            FROM project_asset_distillation_settings
            WHERE tenant_id=%s::uuid AND project_id=%s::uuid
            """,
            (context.tenant_id, context.project_id),
        )
        row = cur.fetchone()
        if row is None or not row[0]:
            return []
        return [part.strip() for part in str(row[0]).split(",") if part.strip()]

    def distill(
        self,
        *,
        context: AgentContext,
        validated: dict[str, Any],
        resolution: ModuleBindingResolution,
        response: dict[str, Any] | None = None,
        candidates: list[dict[str, Any]] | None = None,
    ) -> dict[str, Any]:
        if candidates is None:
            enabled = resolve_enabled_asset_types(validated.get("enabled_asset_types"))
            candidates = validate_model_candidates(
                response or {},
                validated["sources"],
                enabled_asset_types=enabled,
            )
        with self._connect() as conn:
            set_postgres_tenant_context(conn, context=context)
            with conn.cursor() as cur:
                # Load existing assets for identity resolution
                cur.execute(
                    """
                    SELECT a.asset_id::text, a.asset_type, a.title, COALESCE(a.summary,''), a.lifecycle, a.enabled,
                           COALESCE((
                             SELECT max(v.version_number) + 1
                             FROM asset_versions v
                             WHERE v.tenant_id=a.tenant_id AND v.project_id=a.project_id AND v.asset_id=a.asset_id
                           ), 1) AS next_version
                    FROM assets a
                    WHERE a.tenant_id=%s::uuid AND a.project_id=%s::uuid
                      AND a.lifecycle IN ('seed','canon','material') AND a.enabled=TRUE
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
                        "expected_target_version": int(r[6] or 1),
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
                # Supersede older pending identities before promoting this run's staging batch.
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
                      AND newer.review_status='staging'
                      AND r.run_id=%s::uuid
                    """,
                    (context.tenant_id, context.project_id, context.run_id),
                )
                # Deduplicate within this run: keep the newest staging row per identity.
                cur.execute(
                    """
                    UPDATE asset_candidate_proposals older
                    SET review_status='superseded', updated_at=now()
                    FROM asset_candidate_proposals newer
                    JOIN manuscript_asset_distillation_requests r
                      ON r.tenant_id=newer.tenant_id AND r.request_id=newer.request_id
                    WHERE older.tenant_id=%s::uuid AND older.project_id=%s::uuid
                      AND older.review_status='staging'
                      AND newer.tenant_id=older.tenant_id AND newer.project_id=older.project_id
                      AND newer.normalized_identity=older.normalized_identity
                      AND newer.candidate_asset_id<>older.candidate_asset_id
                      AND newer.review_status='staging'
                      AND r.run_id=%s::uuid
                      AND older.created_at < newer.created_at
                    """,
                    (context.tenant_id, context.project_id, context.run_id),
                )
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
                public = {
                    "status": "completed",
                    "source_count": int(result.get("source_count") or 0),
                    "candidate_count": int(result.get("candidate_count") or 0),
                    "model_candidate_count": int(result.get("model_candidate_count") or 0),
                    "filtered_candidate_count": int(result.get("filtered_candidate_count") or 0),
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
        return {
            "operation": "update",
            "target_asset_id": hits[0]["asset_id"],
            "expected_target_version": int(hits[0].get("expected_target_version") or 1),
        }
    if len(hits) > 1:
        return {"operation": "conflict"}
    return {"operation": "create"}


def resolve_enabled_asset_types(raw: Any) -> list[str]:
    """Empty list means full supported set (product: empty != disable all)."""
    if raw is None:
        return sorted(SUPPORTED_TYPES)
    if not isinstance(raw, list):
        return sorted(SUPPORTED_TYPES)
    cleaned: list[str] = []
    seen: set[str] = set()
    for item in raw:
        asset_type = str(item or "").strip()
        if not asset_type or asset_type not in SUPPORTED_TYPES or asset_type in seen:
            continue
        seen.add(asset_type)
        cleaned.append(asset_type)
    if not cleaned:
        return sorted(SUPPORTED_TYPES)
    return cleaned


def estimate_tokens(text: str) -> int:
    if not text:
        return 0
    return max(1, (len(text) + CHARS_PER_TOKEN - 1) // CHARS_PER_TOKEN)


def _split_long_text(text: str, *, max_chars: int = WINDOW_CHAR_MAX) -> list[tuple[int, int, str]]:
    """Split one block body into char spans that fit the window budget."""
    if len(text) <= max_chars:
        return [(0, len(text), text)]
    spans: list[tuple[int, int, str]] = []
    start = 0
    n = len(text)
    while start < n:
        end = min(start + max_chars, n)
        if end < n:
            # Prefer paragraph / sentence boundaries inside the last 25% of the window.
            search_from = start + max(1, int(max_chars * 0.75))
            boundary = -1
            for sep in ("\n\n", "\n", "。", "！", "？", ". ", "! ", "? "):
                idx = text.rfind(sep, search_from, end)
                if idx >= search_from:
                    boundary = max(boundary, idx + len(sep))
            if boundary > start:
                end = boundary
        chunk = text[start:end]
        if not chunk:
            # Hard advance on pathological input to avoid infinite loop.
            end = min(start + max_chars, n)
            chunk = text[start:end]
        spans.append((start, end, chunk))
        start = end
    return spans


def build_source_windows(
    sources: list[dict[str, Any]],
    *,
    target_chars: int = WINDOW_CHAR_TARGET,
    max_chars: int = WINDOW_CHAR_MAX,
) -> list[list[dict[str, Any]]]:
    """
    Token-aware sequential windows over source blocks.

    Each window item is a source slice with:
      - content_text: slice text sent to the model
      - base_offset: char offset into the original block (for evidence remap)
      - full content retained on the original source for validation against full text
    """
    if not sources:
        return []
    # Pre-split oversized single blocks so no unit exceeds max_chars.
    units: list[dict[str, Any]] = []
    for source in sources:
        text = str(source.get("content_text") or "")
        for start, end, chunk in _split_long_text(text, max_chars=max_chars):
            units.append(
                {
                    "block_id": source["block_id"],
                    "block_version": source["block_version"],
                    "content_sha256": source["content_sha256"],
                    "content_text": chunk,
                    "base_offset": start,
                    "chapter_id": source.get("chapter_id"),
                    "scene_id": source.get("scene_id"),
                    # Keep full original text for evidence validation against real offsets.
                    "_full_content_text": text,
                }
            )

    windows: list[list[dict[str, Any]]] = []
    current: list[dict[str, Any]] = []
    current_chars = 0
    for unit in units:
        unit_chars = len(unit["content_text"])
        # Overhead for block header in prompt.
        header_overhead = 80
        projected = current_chars + unit_chars + header_overhead
        if current and projected > target_chars:
            windows.append(current)
            current = []
            current_chars = 0
        # A single unit may still exceed target but is always <= max_chars.
        current.append(unit)
        current_chars += unit_chars + header_overhead
        if current_chars >= max_chars:
            windows.append(current)
            current = []
            current_chars = 0
    if current:
        windows.append(current)
    return windows


def core_identity_key(asset_type: str, title: str) -> str:
    """Stable cross-window merge key (type + title); hints are unioned, not part of the key."""
    return normalize_identity(asset_type, title, [])


def merge_candidates_by_identity(candidates: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Merge multi-window candidates that share a normalized type+title identity."""
    merged: dict[str, dict[str, Any]] = {}
    order: list[str] = []
    for candidate in candidates:
        identity = core_identity_key(candidate["asset_type"], candidate["title"])
        existing = merged.get(identity)
        if existing is None:
            copy = {
                **candidate,
                "identity_hints": list(candidate.get("identity_hints") or []),
                "tags": list(candidate.get("tags") or []),
                "payload": dict(candidate.get("payload") or {}),
                "evidence": list(candidate.get("evidence") or []),
            }
            merged[identity] = copy
            order.append(identity)
            continue
        # Prefer longer non-empty summary; keep highest confidence; union hints/tags/evidence.
        new_summary = str(candidate.get("summary") or "")
        if len(new_summary) > len(str(existing.get("summary") or "")):
            existing["summary"] = new_summary
        conf_a = existing.get("confidence")
        conf_b = candidate.get("confidence")
        if conf_b is not None and (conf_a is None or float(conf_b) > float(conf_a)):
            existing["confidence"] = conf_b
        hints = list(existing.get("identity_hints") or [])
        for hint in candidate.get("identity_hints") or []:
            if hint not in hints:
                hints.append(hint)
        existing["identity_hints"] = hints
        tags = list(existing.get("tags") or [])
        for tag in candidate.get("tags") or []:
            if tag not in tags:
                tags.append(tag)
        existing["tags"] = tags
        payload = dict(existing.get("payload") or {})
        payload.update(dict(candidate.get("payload") or {}))
        existing["payload"] = payload
        evidence = list(existing.get("evidence") or [])
        seen_ev = {
            (
                e.get("block_id"),
                e.get("start_offset"),
                e.get("end_offset"),
                e.get("quote"),
            )
            for e in evidence
        }
        for ev in candidate.get("evidence") or []:
            key = (ev.get("block_id"), ev.get("start_offset"), ev.get("end_offset"), ev.get("quote"))
            if key in seen_ev:
                continue
            seen_ev.add(key)
            evidence.append(ev)
        existing["evidence"] = evidence
    return [merged[key] for key in order]


def _evidence_units_for_block(sources: list[dict[str, Any]], block_id: str) -> list[dict[str, Any]]:
    """Return source units for a block; window slices keep base_offset + full text."""
    units = [s for s in sources if str(s.get("block_id")) == block_id]
    return units


def _validate_evidence_quote(
    *,
    units: list[dict[str, Any]],
    quote: str,
    start: int,
    end: int,
    remap_window_offsets: bool,
) -> dict[str, Any] | None:
    if not units:
        return None
    # Prefer validating against the unit whose local slice matches offsets/quote.
    for unit in units:
        full_text = str(unit.get("_full_content_text") or unit.get("content_text") or "")
        slice_text = str(unit.get("content_text") or "")
        base = int(unit.get("base_offset") or 0) if remap_window_offsets else 0
        # Local / absolute exact span match on the text the model saw.
        check_text = slice_text if remap_window_offsets else full_text
        if start >= 0 and end > start and end <= len(check_text) and check_text[start:end] == quote:
            abs_start = start + base if remap_window_offsets else start
            abs_end = end + base if remap_window_offsets else end
            if full_text[abs_start:abs_end] == quote:
                return {
                    "block_id": str(unit["block_id"]),
                    "block_version": unit["block_version"],
                    "content_sha256": unit["content_sha256"],
                    "start_offset": abs_start,
                    "end_offset": abs_end,
                    "quote": quote,
                }
        # Unique quote within the unit the model saw (window) or full block.
        if quote and check_text.count(quote) == 1:
            idx = check_text.index(quote)
            abs_start = idx + base if remap_window_offsets else idx
            abs_end = abs_start + len(quote)
            if full_text[abs_start:abs_end] == quote:
                return {
                    "block_id": str(unit["block_id"]),
                    "block_version": unit["block_version"],
                    "content_sha256": unit["content_sha256"],
                    "start_offset": abs_start,
                    "end_offset": abs_end,
                    "quote": quote,
                }
    # Final fallback: unique quote on full block text (absolute offsets).
    full_text = str(units[0].get("_full_content_text") or units[0].get("content_text") or "")
    if quote and full_text.count(quote) == 1:
        idx = full_text.index(quote)
        return {
            "block_id": str(units[0]["block_id"]),
            "block_version": units[0]["block_version"],
            "content_sha256": units[0]["content_sha256"],
            "start_offset": idx,
            "end_offset": idx + len(quote),
            "quote": quote,
        }
    return None


def _split_relationship_title(title: str) -> tuple[str, str] | None:
    """Recover (source, target) entity names from a natural-language relationship title.

    Mirrors the Go assetdistillation.splitRelationshipTitle fallback so the
    distiller can backfill payload endpoints the model left only in the title.
    Handles "A / B", "A→B" style separators, Chinese conjunctions (与/和/跟/…),
    and the "X与Y的<关系名词>" form (strips the trailing relation noun).
    """
    text = title.strip()
    if not text:
        return None
    for sep in (" / ", " -> ", "→", "—", " - ", "、"):
        if sep in text:
            left, _, right = text.partition(sep)
            left, right = left.strip(), right.strip()
            if left and right:
                return left, right
    for conj in ("与", "和", "跟", "同", "及", "对"):
        idx = text.find(conj)
        if idx <= 0:
            continue
        source = text[:idx].strip()
        target = text[idx + len(conj):].strip()
        if not source or not target:
            continue
        target = _strip_relation_suffix(target)
        if source and target:
            return source, target
    return None


_RELATION_SUFFIXES = (
    "关系", "交易", "约定", "冲突", "纠葛", "恩怨", "往来", "合作", "结盟", "联盟",
    "对立", "矛盾", "牵连", "牵扯", "联系", "接触", "相遇", "相识", "重逢", "决裂",
    "和解", "对峙", "同盟", "羁绊", "渊源", "旧怨", "新仇", "密谋", "密约", "婚约",
    "仇怨", "仇恨",
)


def _strip_relation_suffix(target: str) -> str:
    for noun in _RELATION_SUFFIXES:
        if target.endswith(noun):
            stripped = target[: -len(noun)].strip().rstrip("的").strip()
            if stripped:
                return stripped
    return target


def _normalize_relationship_payload(candidate: dict[str, Any]) -> None:
    """Ensure a relationship candidate carries structured endpoint names.

    The model sometimes puts both entity names only in the title; backfill
    source_entity_name/target_entity_name from it so the Go graph projection
    (which requires both) never has to guess. relationship_type defaults to
    "related" when absent. Drops nothing — only fills gaps.
    """
    payload = candidate.get("payload")
    if not isinstance(payload, dict):
        payload = {}
        candidate["payload"] = payload

    def _first(*keys: str) -> str:
        for key in keys:
            value = payload.get(key)
            if value is None:
                continue
            text = str(value).strip()
            if text:
                return text
        return ""

    source = _first("source_entity_name", "source_entity", "source")
    target = _first("target_entity_name", "target_entity", "target")
    if not source or not target:
        parts = _split_relationship_title(str(candidate.get("title") or ""))
        if parts:
            source = source or parts[0]
            target = target or parts[1]
    if source:
        payload["source_entity_name"] = source
    if target:
        payload["target_entity_name"] = target
    if not _first("relationship_type", "kind"):
        payload["relationship_type"] = "related"


def validate_model_candidates(
    response: dict[str, Any],
    sources: list[dict[str, Any]],
    *,
    enabled_asset_types: list[str] | None = None,
    remap_window_offsets: bool = False,
) -> list[dict[str, Any]]:
    items = response.get("candidates")
    if not isinstance(items, list):
        raise LLMFacilityError("DISTILLATION_OUTPUT_INVALID", "distiller output candidates must be a list")
    allowed = set(resolve_enabled_asset_types(enabled_asset_types))
    out: list[dict[str, Any]] = []
    for item in items:
        if not isinstance(item, dict):
            continue
        asset_type = str(item.get("asset_type") or "").strip()
        title = str(item.get("title") or "").strip()
        if asset_type not in SUPPORTED_TYPES or asset_type not in allowed or not title:
            continue
        evidence_in = item.get("evidence") or []
        # Some JSON-capable providers collapse a single-item array into an
        # object. Accept that equivalent shape while keeping all evidence
        # validation below unchanged.
        if isinstance(evidence_in, dict):
            evidence_in = [evidence_in]
        elif not isinstance(evidence_in, list):
            continue
        valid_evidence = []
        for ev in evidence_in:
            if not isinstance(ev, dict):
                continue
            block_id = str(ev.get("block_id") or "")
            units = _evidence_units_for_block(sources, block_id)
            if not units:
                continue
            quote = str(ev.get("quote") or "")
            try:
                start = int(ev.get("start_offset"))
                end = int(ev.get("end_offset"))
            except (TypeError, ValueError):
                start, end = -1, -1
            resolved = _validate_evidence_quote(
                units=units,
                quote=quote,
                start=start,
                end=end,
                remap_window_offsets=remap_window_offsets,
            )
            if resolved is not None:
                valid_evidence.append(resolved)
        if not valid_evidence:
            continue
        conf = item.get("confidence")
        try:
            confidence = float(conf) if conf is not None else None
        except (TypeError, ValueError):
            confidence = None
        candidate = {
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
        if asset_type == "relationship":
            _normalize_relationship_payload(candidate)
        out.append(candidate)
    return out


def _messages(
    sources: list[dict[str, Any]],
    *,
    enabled_asset_types: list[str] | None = None,
) -> list[dict[str, str]]:
    allowed = resolve_enabled_asset_types(enabled_asset_types)
    parts = []
    for source in sources:
        header = f"[block_id={source['block_id']} version={source['block_version']}"
        base = source.get("base_offset")
        if base is not None and int(base) > 0:
            header += f" base_offset={int(base)}"
        header += f"]\n{source['content_text']}"
        parts.append(header)
    body = "\n\n".join(parts)
    return [
        {
            "role": "system",
            "content": _distillation_system_prompt(allowed),
        },
        {"role": "user", "content": body},
    ]


def _distillation_system_prompt(allowed: list[str]) -> str:
    payload_contract = "\n".join(
        f"- {asset_type}: {ASSET_PAYLOAD_GUIDANCE[asset_type]}"
        for asset_type in allowed
    )
    return (
        "You are a story-knowledge distiller. Extract detailed, reusable story assets from active manuscript "
        "text, not a broad chapter recap. Return one JSON object with shape {\"candidates\":[...]}.\n\n"
        "Extraction rules:\n"
        "1. Create one candidate per stable character, organization, location, item, world rule, relationship, "
        "event, plot thread, or terminology concept that the manuscript materially establishes or updates. "
        "Split unrelated identities or facts instead of combining them into a vague asset.\n"
        "2. title must identify the exact subject. summary is the asset's primary readable content: write a "
        "detailed, self-contained dossier in the manuscript's language. Name the subject explicitly and retain "
        "concrete facts such as appearance, role, state, goals, motives, abilities, restrictions, ownership, "
        "relationships, actions, causes, outcomes, and unresolved stakes whenever the text supports them. Preserve "
        "specific names, places, objects, and causal links. Avoid generic summaries such as 'an important person', "
        "'a mysterious item', or 'an event that advances the plot'.\n"
        "3. payload is the structured fact record. Populate every applicable field supported by the text; use "
        "arrays for multiple values and objects only when structure is useful. Omit unknown fields. Never invent "
        "facts or add empty placeholder values merely to fill the schema. Keep current state distinct from history, "
        "rumor, hypothesis, intention, and confirmed outcome.\n"
        "4. identity_hints contains only aliases, titles, or stable disambiguators. tags contains concise retrieval "
        "labels. confidence is a number from 0 to 1 reflecting textual support.\n"
        "5. evidence MUST be a JSON array even when there is one item. Each evidence object needs block_id, "
        "start_offset, end_offset, and quote. quote must be an exact substring of the provided block segment. "
        "Offsets are relative to that provided segment, not the full chapter when base_offset is present. Include "
        "enough evidence spans to support the candidate's main detailed claims; do not use commentary as evidence.\n"
        "6. Write title, summary, tags, and textual payload values in the same language as the manuscript. Do not "
        "copy long prose passages into summary or payload. Do not expose block IDs or offsets outside evidence.\n\n"
        f"Only extract these asset_type values: {', '.join(allowed)}. Do not invent other asset types.\n\n"
        "Type-specific payload fields (include only fields supported by evidence):\n"
        f"{payload_contract}\n\n"
        "For relationship candidates, source_entity_name, target_entity_name, and relationship_type are mandatory "
        "and must name both endpoints exactly as they appear in the manuscript. Do not leave endpoints only in the "
        "title. Every candidate must contain asset_type, title, summary, payload, identity_hints, tags, confidence, "
        "and evidence."
    )


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
            enabled = resolve_enabled_asset_types(validated.get("enabled_asset_types"))
            validated = {**validated, "enabled_asset_types": enabled}
            windows = build_source_windows(validated["sources"])
            aggregated: list[dict[str, Any]] = []
            model_candidate_count = 0
            for window in windows:
                response = self._chat_client.complete_json(
                    context=context,
                    resolution=resolution,
                    api_key=api_key,
                    messages=_messages(window, enabled_asset_types=enabled),
                )
                response_candidates = response.get("candidates")
                if isinstance(response_candidates, list):
                    model_candidate_count += len(response_candidates)
                window_candidates = validate_model_candidates(
                    response,
                    window,
                    enabled_asset_types=enabled,
                    remap_window_offsets=True,
                )
                aggregated.extend(window_candidates)
            merged = merge_candidates_by_identity(aggregated)
            # Final pass: re-validate evidence against full source text and filter types.
            merged = validate_model_candidates(
                {"candidates": merged},
                validated["sources"],
                enabled_asset_types=enabled,
                remap_window_offsets=False,
            )
            distilled = self._store.distill(
                context=context,
                validated=validated,
                resolution=resolution,
                candidates=merged,
            )
            distilled = {
                **distilled,
                "window_count": len(windows),
                "enabled_asset_types": enabled,
                "model_candidate_count": model_candidate_count,
                "filtered_candidate_count": max(model_candidate_count - len(aggregated), 0),
            }
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
