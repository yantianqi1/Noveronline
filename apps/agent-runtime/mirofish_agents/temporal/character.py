from __future__ import annotations

import json
import os
import time
from datetime import timedelta
from typing import Any, Callable, Protocol
from uuid import UUID

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


CHARACTER_TASK_QUEUE = "character-interactive"
CHARACTER_DIALOGUE_WORKFLOW_TYPE = "character_dialogue"
CHARACTER_DIALOGUE_MODULE_KEY = "character_dialogue"
CHARACTER_DIALOGUE_ASSET_SOURCE_KIND = "character_dialogue"


class CharacterDialogueStore(Protocol):
    def load_context(
        self, *, context: AgentContext, interaction_id: str, user_turn_id: str
    ) -> dict[str, Any]: ...

    def persist_result(
        self,
        *,
        context: AgentContext,
        interaction_id: str,
        user_turn_id: str,
        model_id: str,
        result: dict[str, Any],
    ) -> dict[str, Any]: ...

    def mark_failed(
        self, *, context: AgentContext, interaction_id: str, code: str, message: str
    ) -> None: ...


class CharacterDialogueRunner(Protocol):
    def run_dialogue(
        self, *, context: AgentContext, interaction_id: str, user_turn_id: str
    ) -> dict[str, Any]: ...


class LLMFacilityCharacterDialogueRunner:
    def __init__(
        self,
        *,
        binding_resolver: ModuleBindingResolver,
        credential_provider: CredentialProvider,
        chat_client: JSONChatClient,
        store: CharacterDialogueStore,
    ) -> None:
        self._binding_resolver = binding_resolver
        self._credential_provider = credential_provider
        self._chat_client = chat_client
        self._store = store

    def run_dialogue(
        self, *, context: AgentContext, interaction_id: str, user_turn_id: str
    ) -> dict[str, Any]:
        source = self._store.load_context(
            context=context,
            interaction_id=interaction_id,
            user_turn_id=user_turn_id,
        )
        if source.get("replayed"):
            return _public_result(source)
        resolution = self._binding_resolver.resolve_module_binding(
            context=context,
            module_key=CHARACTER_DIALOGUE_MODULE_KEY,
        )
        _validate_resolution(resolution)
        api_key = self._credential_provider.resolve_api_key(
            context=context,
            credential_ref=resolution.credential_ref,
        )
        if not isinstance(api_key, str) or not api_key.strip():
            raise LLMFacilityError(
                "LLM_CREDENTIAL_UNAVAILABLE", "resolved credential was empty"
            )
        response = self._chat_client.complete_json(
            context=context,
            resolution=resolution,
            api_key=api_key.strip(),
            messages=_dialogue_messages(source),
        )
        private_result = _validate_provider_result(response)
        persisted = self._store.persist_result(
            context=context,
            interaction_id=interaction_id,
            user_turn_id=user_turn_id,
            model_id=resolution.model_id,
            result=private_result,
        )
        return _public_result({**persisted, "model_id": resolution.model_id})


class PostgresCharacterDialogueStore:
    def __init__(self, *, connect: Callable[[], Any]) -> None:
        self._connect = connect

    @classmethod
    def from_database_url(cls, database_url: str) -> "PostgresCharacterDialogueStore":
        try:
            import psycopg
        except ImportError as exc:  # pragma: no cover
            raise RuntimeError("psycopg is required for Character dialogue runtime") from exc
        return cls(connect=lambda: psycopg.connect(database_url))

    def load_context(
        self, *, context: AgentContext, interaction_id: str, user_turn_id: str
    ) -> dict[str, Any]:
        _require_runtime_context(context)
        interaction_id = _required_uuid(interaction_id, "interaction_id")
        user_turn_id = _required_uuid(user_turn_id, "user_turn_id")
        connection = self._connect()
        try:
            set_postgres_tenant_context(connection, context=context)
            with connection.cursor() as cursor:
                cursor.execute(
                    """SELECT interaction.mode, interaction.pov_agent_id,
                              COALESCE(interaction.worldline_session_id::text, ''),
                              interaction.anchor_type, interaction.anchor_id,
                              interaction.title, interaction.summary,
                              COALESCE(worldline.lifecycle, 'active')
                       FROM character_interaction_sessions AS interaction
                       LEFT JOIN worldline_sessions AS worldline
                         ON worldline.tenant_id = interaction.tenant_id
                        AND worldline.project_id = interaction.project_id
                        AND worldline.session_id = interaction.worldline_session_id
                       WHERE interaction.tenant_id = %s
                         AND interaction.project_id = %s
                         AND interaction.interaction_id = %s
                         AND interaction.status IN ('active', 'saved')""",
                    (context.tenant_id, context.project_id, interaction_id),
                )
                interaction = cursor.fetchone()
                if interaction is None:
                    raise LLMFacilityError(
                        "CHARACTER_INTERACTION_NOT_FOUND",
                        "character interaction was not found or is not active",
                    )
                if interaction[2] and interaction[7] != "active":
                    raise LLMFacilityError(
                        "CURRENT_WORLD_REQUIRED",
                        "character dialogue requires the active current_world session",
                    )
                cursor.execute(
                    """SELECT turn_order, actor_type, actor_id, turn_kind, summary
                       FROM character_interaction_turns
                       WHERE tenant_id = %s AND project_id = %s AND interaction_id = %s
                       ORDER BY turn_order DESC LIMIT 20""",
                    (context.tenant_id, context.project_id, interaction_id),
                )
                history = list(reversed(cursor.fetchall()))
                cursor.execute(
                    """SELECT turn_order, actor_type, actor_id, turn_kind, summary
                       FROM character_interaction_turns
                       WHERE tenant_id = %s AND project_id = %s
                         AND interaction_id = %s AND turn_id = %s""",
                    (context.tenant_id, context.project_id, interaction_id, user_turn_id),
                )
                user_turn = cursor.fetchone()
                if user_turn is None or user_turn[1] != "user":
                    raise LLMFacilityError(
                        "CHARACTER_USER_TURN_NOT_FOUND",
                        "character dialogue user turn was not found",
                    )
                cursor.execute(
                    """SELECT turn_id::text, turn_order
                       FROM character_interaction_turns
                       WHERE tenant_id = %s AND project_id = %s
                         AND interaction_id = %s AND trace_id = %s
                         AND actor_type IN ('agent', 'director') LIMIT 1""",
                    (
                        context.tenant_id,
                        context.project_id,
                        interaction_id,
                        context.trace_id,
                    ),
                )
                replay = cursor.fetchone()
            connection.commit()
        except LLMFacilityError:
            _rollback(connection)
            raise
        except Exception as exc:
            _rollback(connection)
            raise LLMFacilityError(
                "CHARACTER_CONTEXT_LOAD_FAILED", "character dialogue context load failed"
            ) from exc
        finally:
            connection.close()
        if replay is not None:
            return {
                "status": "completed",
                "replayed": True,
                "interaction_id": interaction_id,
                "turn_id": replay[0],
                "turn_order": replay[1],
            }
        return {
            "interaction_id": interaction_id,
            "mode": interaction[0],
            "pov_agent_id": interaction[1],
            "worldline_session_id": interaction[2],
            "world_scope": "current_world",
            "anchor_type": interaction[3],
            "anchor_id": interaction[4],
            "title": interaction[5],
            "interaction_summary": interaction[6],
            "history": [_turn_summary(row) for row in history],
            "user_turn": _turn_summary(user_turn),
        }

    def persist_result(
        self,
        *,
        context: AgentContext,
        interaction_id: str,
        user_turn_id: str,
        model_id: str,
        result: dict[str, Any],
    ) -> dict[str, Any]:
        interaction_id = _required_uuid(interaction_id, "interaction_id")
        user_turn_id = _required_uuid(user_turn_id, "user_turn_id")
        connection = self._connect()
        try:
            set_postgres_tenant_context(connection, context=context)
            with connection.cursor() as cursor:
                cursor.execute(
                    "SELECT pg_advisory_xact_lock(hashtextextended(%s || ':' || %s, 0))",
                    (context.tenant_id, interaction_id),
                )
                cursor.execute(
                    """SELECT status, COALESCE(worldline_session_id::text, '')
                       FROM character_interaction_sessions
                       WHERE tenant_id = %s AND project_id = %s AND interaction_id = %s
                       FOR UPDATE""",
                    (context.tenant_id, context.project_id, interaction_id),
                )
                parent = cursor.fetchone()
                if parent is None or parent[0] not in ("active", "saved"):
                    raise LLMFacilityError(
                        "CHARACTER_INTERACTION_NOT_FOUND",
                        "character interaction was not found or is not active",
                    )
                cursor.execute(
                    """SELECT turn_id::text, turn_order
                       FROM character_interaction_turns
                       WHERE tenant_id = %s AND project_id = %s
                         AND interaction_id = %s AND trace_id = %s
                         AND actor_type IN ('agent', 'director') LIMIT 1""",
                    (
                        context.tenant_id,
                        context.project_id,
                        interaction_id,
                        context.trace_id,
                    ),
                )
                replay = cursor.fetchone()
                if replay is not None:
                    connection.commit()
                    return {
                        "status": "completed",
                        "replayed": True,
                        "interaction_id": interaction_id,
                        "turn_id": replay[0],
                        "turn_order": replay[1],
                    }
                cursor.execute(
                    """SELECT COALESCE(MAX(turn_order), 0) + 1
                       FROM character_interaction_turns
                       WHERE tenant_id = %s AND project_id = %s AND interaction_id = %s""",
                    (context.tenant_id, context.project_id, interaction_id),
                )
                turn_order = int(cursor.fetchone()[0])
                public_metadata = {
                    "lifecycle": "candidate",
                    "world_scope": "current_world",
                    "source_user_turn_id": user_turn_id,
                    "memory_candidate_count": len(result["memory_candidates"]),
                    "relation_candidate_count": len(result["relation_candidates"]),
                    "world_state_candidate_count": len(result["world_state_candidates"]),
                }
                cursor.execute(
                    """INSERT INTO character_interaction_turns (
                         tenant_id, interaction_id, project_id, turn_order, actor_type,
                         actor_id, turn_kind, summary, action_jsonb,
                         world_state_delta_jsonb, trace_id, created_by
                       ) VALUES (
                         %s, %s, %s, %s, %s, %s, 'dialogue', %s, %s::jsonb,
                         %s::jsonb, %s, %s
                       ) RETURNING turn_id::text""",
                    (
                        context.tenant_id,
                        interaction_id,
                        context.project_id,
                        turn_order,
                        "director" if result["speaker_type"] == "director" else "agent",
                        result["speaker_id"],
                        result["reply_summary"],
                        json.dumps(public_metadata, separators=(",", ":")),
                        json.dumps(
                            {
                                "lifecycle": "candidate",
                                "proposal_count": len(result["world_state_candidates"]),
                            },
                            separators=(",", ":"),
                        ),
                        context.trace_id,
                        _uuid_or_none(context.actor_user_id),
                    ),
                )
                turn_id = cursor.fetchone()[0]
                candidate_assets = self._write_candidate_assets(
                    cursor,
                    context=context,
                    interaction_id=interaction_id,
                    user_turn_id=user_turn_id,
                    turn_id=turn_id,
                    model_id=model_id,
                    result=result,
                    worldline_session_id=parent[1],
                )
                self._write_trace(
                    cursor,
                    context=context,
                    interaction_id=interaction_id,
                    user_turn_id=user_turn_id,
                    turn_id=turn_id,
                    model_id=model_id,
                    result=result,
                    candidate_assets=candidate_assets,
                )
                self._write_public_terminal_events(
                    cursor,
                    context=context,
                    interaction_id=interaction_id,
                    user_turn_id=user_turn_id,
                    turn_id=turn_id,
                    turn_order=turn_order,
                    result=result,
                    candidate_assets=candidate_assets,
                )
                cursor.execute(
                    """UPDATE character_interaction_sessions
                       SET updated_at = now() WHERE tenant_id = %s AND project_id = %s
                         AND interaction_id = %s""",
                    (context.tenant_id, context.project_id, interaction_id),
                )
            connection.commit()
        except LLMFacilityError:
            _rollback(connection)
            raise
        except Exception as exc:
            _rollback(connection)
            raise LLMFacilityError(
                "CHARACTER_TURN_WRITE_FAILED", "character dialogue turn write failed"
            ) from exc
        finally:
            connection.close()
        return {
            "status": "completed",
            "replayed": False,
            "interaction_id": interaction_id,
            "turn_id": turn_id,
            "turn_order": turn_order,
            "candidate_asset_count": len(candidate_assets),
            "candidate_asset_ids": [item["asset_id"] for item in candidate_assets],
            **_candidate_counts(result),
        }

    def _write_candidate_assets(
        self,
        cursor: Any,
        *,
        context: AgentContext,
        interaction_id: str,
        user_turn_id: str,
        turn_id: str,
        model_id: str,
        result: dict[str, Any],
        worldline_session_id: str,
    ) -> list[dict[str, str]]:
        records: list[dict[str, str]] = []
        if result.get("world_state_candidates"):
            if not worldline_session_id:
                raise LLMFacilityError(
                    "CURRENT_WORLD_REQUIRED",
                    "character world-state proposals require an active current_world session",
                )
            cursor.execute(
                """SELECT lifecycle FROM worldline_sessions
                   WHERE tenant_id = %s AND project_id = %s AND session_id = %s
                   FOR UPDATE""",
                (context.tenant_id, context.project_id, worldline_session_id),
            )
            current_world = cursor.fetchone()
            if current_world is None or current_world[0] != "active":
                raise LLMFacilityError(
                    "CURRENT_WORLD_REQUIRED",
                    "character world-state proposals require an active current_world session",
                )
        for candidate in _candidate_asset_specs(result):
            payload = {
                **candidate["payload"],
                "interaction_id": interaction_id,
                "source_user_turn_id": user_turn_id,
                "source_turn_id": turn_id,
                "source_run_id": context.run_id,
                "model_id": model_id,
                "proposal_type": candidate["proposal_type"],
                "lifecycle": "candidate",
                "world_scope": "current_world",
            }
            source_ref = (
                f"{context.run_id}:{candidate['proposal_type']}:{candidate['candidate_index']}"
            )
            cursor.execute(
                """INSERT INTO assets (
                     tenant_id, project_id, scope, asset_type, category, lifecycle,
                     title, summary, content_text, payload_jsonb, tags_jsonb,
                     source_kind, source_ref, enabled, pinned, created_by
                   ) VALUES (
                     %s, %s, 'project', %s, %s, 'candidate',
                     %s, %s, %s, %s::jsonb, %s::jsonb,
                     %s, %s, true, false, %s
                   )
                   ON CONFLICT (tenant_id, project_id, source_kind, source_ref, asset_type, title)
                   DO UPDATE SET
                     category = EXCLUDED.category,
                     summary = EXCLUDED.summary,
                     content_text = EXCLUDED.content_text,
                     payload_jsonb = EXCLUDED.payload_jsonb,
                     tags_jsonb = EXCLUDED.tags_jsonb,
                     enabled = true,
                     updated_at = now()
                   RETURNING asset_id::text""",
                (
                    context.tenant_id,
                    context.project_id,
                    candidate["asset_type"],
                    candidate["category"],
                    candidate["title"],
                    candidate["summary"],
                    candidate["summary"],
                    json.dumps(payload, ensure_ascii=False, separators=(",", ":")),
                    json.dumps(candidate["tags"], ensure_ascii=False, separators=(",", ":")),
                    CHARACTER_DIALOGUE_ASSET_SOURCE_KIND,
                    source_ref,
                    _uuid_or_none(context.actor_user_id),
                ),
            )
            asset_id = cursor.fetchone()[0]
            target_id = self._write_candidate_target(
                cursor,
                context=context,
                asset_id=asset_id,
                source_ref=source_ref,
                worldline_session_id=worldline_session_id,
                candidate=candidate,
            )
            cursor.execute(
                """UPDATE assets
                   SET payload_jsonb = payload_jsonb || jsonb_build_object('target_id', %s::text),
                       updated_at = now()
                   WHERE tenant_id = %s AND project_id = %s AND asset_id = %s""",
                (target_id, context.tenant_id, context.project_id, asset_id),
            )
            records.append(
                {
                    "asset_id": asset_id,
                    "asset_type": candidate["asset_type"],
                    "proposal_type": candidate["proposal_type"],
                    "target_id": target_id,
                }
            )
        return records

    def _write_candidate_target(
        self,
        cursor: Any,
        *,
        context: AgentContext,
        asset_id: str,
        source_ref: str,
        worldline_session_id: str,
        candidate: dict[str, Any],
    ) -> str:
        proposal_type = candidate["proposal_type"]
        if proposal_type == "memory":
            cursor.execute(
                """INSERT INTO archive_memories (
                     tenant_id, asset_id, project_id, memory_type, status, summary,
                     body_text, payload_jsonb, source_kind, source_ref, enabled, created_by
                   ) VALUES (
                     %s, %s, %s, %s, 'candidate', %s, %s, %s::jsonb,
                     %s, %s, true, %s
                   )
                   ON CONFLICT (tenant_id, asset_id, source_kind, source_ref, memory_type)
                   DO UPDATE SET
                     summary = EXCLUDED.summary,
                     body_text = EXCLUDED.body_text,
                     payload_jsonb = EXCLUDED.payload_jsonb,
                     enabled = true,
                     updated_at = now()
                   RETURNING memory_id::text""",
                (
                    context.tenant_id,
                    asset_id,
                    context.project_id,
                    candidate["payload"]["memory_type"],
                    candidate["summary"],
                    candidate["summary"],
                    json.dumps(candidate["payload"], ensure_ascii=False, separators=(",", ":")),
                    CHARACTER_DIALOGUE_ASSET_SOURCE_KIND,
                    source_ref,
                    _uuid_or_none(context.actor_user_id),
                ),
            )
            return cursor.fetchone()[0]
        if proposal_type == "world_state":
            cursor.execute(
                """SELECT COALESCE(MAX(step), 0) + 1
                   FROM worldline_events
                   WHERE tenant_id = %s AND project_id = %s AND session_id = %s""",
                (context.tenant_id, context.project_id, worldline_session_id),
            )
            step = int(cursor.fetchone()[0])
            cursor.execute(
                """INSERT INTO worldline_events (
                     tenant_id, session_id, project_id, step, title, summary, kind,
                     status, lifecycle, involved_agent_ids_jsonb, state_changes_jsonb,
                     source_run_id, created_by
                   ) VALUES (
                     %s, %s, %s, %s, %s, %s, 'character_dialogue',
                     'candidate', 'simulation', %s::jsonb, %s::jsonb, %s, %s
                   ) RETURNING event_id::text""",
                (
                    context.tenant_id,
                    worldline_session_id,
                    context.project_id,
                    step,
                    candidate["title"],
                    candidate["summary"],
                    json.dumps(candidate["payload"].get("involved_agent_ids", []), separators=(",", ":")),
                    json.dumps(candidate["payload"]["state_changes"], ensure_ascii=False, separators=(",", ":")),
                    context.run_id,
                    _uuid_or_none(context.actor_user_id),
                ),
            )
            return cursor.fetchone()[0]
        if proposal_type == "relation":
            return ""
        raise LLMFacilityError(
            "LLM_RESPONSE_SCHEMA_INVALID", "unsupported character proposal type"
        )

    def _write_trace(
        self,
        cursor: Any,
        *,
        context: AgentContext,
        interaction_id: str,
        user_turn_id: str,
        turn_id: str,
        model_id: str,
        result: dict[str, Any],
        candidate_assets: list[dict[str, str]],
    ) -> None:
        cursor.execute(
            """INSERT INTO agent_traces (
                 tenant_id, trace_id, run_id, project_id, module_key, agent_name,
                 status, started_at, completed_at
               ) VALUES (%s, %s, %s, %s, %s, 'character_dialogue',
                         'completed', now(), now())
               ON CONFLICT (tenant_id, trace_id) DO UPDATE SET
                 status = 'completed', completed_at = now(), updated_at = now()""",
            (
                context.tenant_id,
                context.trace_id,
                context.run_id,
                context.project_id,
                CHARACTER_DIALOGUE_MODULE_KEY,
            ),
        )
        private_payload = {
            "interaction_id": interaction_id,
            "source_user_turn_id": user_turn_id,
            "turn_id": turn_id,
            "model_id": model_id,
            "lifecycle": "candidate",
            "reply_summary": result["reply_summary"],
            "memory_candidates": result["memory_candidates"],
            "relation_candidates": result["relation_candidates"],
            "world_state_candidates": result["world_state_candidates"],
            "candidate_assets": candidate_assets,
        }
        cursor.execute(
            """INSERT INTO agent_trace_events (
                 tenant_id, trace_id, event_order, event_type, payload_jsonb,
                 redaction_level
               ) VALUES (
                 %s, %s,
                 (SELECT COALESCE(MAX(event_order), 0) + 1
                    FROM agent_trace_events
                   WHERE tenant_id = %s AND trace_id = %s),
                 'character.dialogue.result', %s::jsonb, 'full'
               )
               ON CONFLICT (tenant_id, trace_id, event_order) DO NOTHING""",
            (
                context.tenant_id,
                context.trace_id,
                context.tenant_id,
                context.trace_id,
                json.dumps(private_payload, ensure_ascii=False, separators=(",", ":")),
            ),
        )

    def _write_public_terminal_events(
        self,
        cursor: Any,
        *,
        context: AgentContext,
        interaction_id: str,
        user_turn_id: str,
        turn_id: str,
        turn_order: int,
        result: dict[str, Any],
        candidate_assets: list[dict[str, str]],
    ) -> None:
        cursor.execute(
            "SELECT COALESCE(MAX(sequence), 0) FROM workflow_events WHERE tenant_id = %s AND run_id = %s",
            (context.tenant_id, context.run_id),
        )
        sequence = int(cursor.fetchone()[0])
        public_base = {
            "interaction_id": interaction_id,
            "session_id": interaction_id,
            "source_user_turn_id": user_turn_id,
            "trace_id": context.trace_id,
            "module_key": CHARACTER_DIALOGUE_MODULE_KEY,
            "world_scope": "current_world",
        }
        events = (
            ("character.dialogue.started", {**public_base, "status": "running"}),
            (
                "character.turn.completed",
                {
                    **public_base,
                    "status": "completed",
                    "turn_id": turn_id,
                    "turn_order": turn_order,
                    "lifecycle": "candidate",
                    "candidate_assets": candidate_assets,
                    **_candidate_counts(result),
                },
            ),
        )
        for offset, (event_type, payload) in enumerate(events, start=1):
            cursor.execute(
                """INSERT INTO workflow_events (
                     tenant_id, run_id, workflow_type, project_id, event_type,
                     sequence, payload_jsonb
                   ) VALUES (%s, %s, %s, %s, %s, %s, %s::jsonb)""",
                (
                    context.tenant_id,
                    context.run_id,
                    CHARACTER_DIALOGUE_WORKFLOW_TYPE,
                    context.project_id,
                    event_type,
                    sequence + offset,
                    json.dumps(payload, separators=(",", ":")),
                ),
            )
        cursor.execute(
            """UPDATE workflow_runs SET status = 'completed', progress = 100,
                 message = 'character dialogue completed',
                 result_jsonb = %s::jsonb, error_code = NULL, error_message = NULL,
                 updated_at = now()
               WHERE tenant_id = %s AND project_id = %s AND run_id = %s
                 AND workflow_type = %s AND status IN ('queued', 'running')""",
            (
                json.dumps(
                    {
                        "interaction_id": interaction_id,
                        "turn_id": turn_id,
                        "turn_order": turn_order,
                        "lifecycle": "candidate",
                        "candidate_assets": candidate_assets,
                        **_candidate_counts(result),
                    },
                    separators=(",", ":"),
                ),
                context.tenant_id,
                context.project_id,
                context.run_id,
                CHARACTER_DIALOGUE_WORKFLOW_TYPE,
            ),
        )
        if cursor.rowcount != 1:
            raise LLMFacilityError(
                "WORKFLOW_RUN_NOT_FOUND", "character dialogue admission parent is missing"
            )

    def mark_failed(
        self, *, context: AgentContext, interaction_id: str, code: str, message: str
    ) -> None:
        connection = self._connect()
        try:
            set_postgres_tenant_context(connection, context=context)
            with connection.cursor() as cursor:
                cursor.execute(
                    "SELECT COALESCE(MAX(sequence), 0) FROM workflow_events WHERE tenant_id = %s AND run_id = %s",
                    (context.tenant_id, context.run_id),
                )
                sequence = int(cursor.fetchone()[0]) + 1
                cursor.execute(
                    """INSERT INTO workflow_events (
                         tenant_id, run_id, workflow_type, project_id, event_type,
                         sequence, payload_jsonb
                       ) SELECT %s, %s, %s, %s, 'character.dialogue.failed', %s, %s::jsonb
                       WHERE EXISTS (
                         SELECT 1 FROM workflow_runs WHERE tenant_id = %s AND run_id = %s
                       )""",
                    (
                        context.tenant_id,
                        context.run_id,
                        CHARACTER_DIALOGUE_WORKFLOW_TYPE,
                        context.project_id,
                        sequence,
                        json.dumps(
                            {
                                "interaction_id": interaction_id,
                                "session_id": interaction_id,
                                "status": "failed",
                                "module_key": CHARACTER_DIALOGUE_MODULE_KEY,
                                "error_code": code,
                                "message": message,
                            },
                            separators=(",", ":"),
                        ),
                        context.tenant_id,
                        context.run_id,
                    ),
                )
                cursor.execute(
                    """UPDATE workflow_runs SET status = 'failed', error_code = %s,
                         error_message = %s, message = 'character dialogue failed', updated_at = now()
                       WHERE tenant_id = %s AND project_id = %s AND run_id = %s
                         AND workflow_type = %s AND status IN ('queued', 'running')""",
                    (
                        code,
                        message,
                        context.tenant_id,
                        context.project_id,
                        context.run_id,
                        CHARACTER_DIALOGUE_WORKFLOW_TYPE,
                    ),
                )
            connection.commit()
        except Exception as exc:
            _rollback(connection)
            raise LLMFacilityError(
                "WORKFLOW_STATUS_WRITE_FAILED",
                "character dialogue workflow status write failed",
            ) from exc
        finally:
            connection.close()


def _dialogue_messages(source: dict[str, Any]) -> list[dict[str, str]]:
    public_source = {
        key: source.get(key)
        for key in (
            "mode",
            "pov_agent_id",
            "worldline_session_id",
            "world_scope",
            "anchor_type",
            "anchor_id",
            "title",
            "interaction_summary",
            "history",
            "user_turn",
        )
    }
    return [
        {
            "role": "system",
            "content": (
                "Respond as the selected fictional character or director. Return JSON with "
                "reply_summary, speaker_type (agent|director), speaker_id, memory_candidates, "
                "relation_candidates, and world_state_candidates. Every candidate is a proposal; "
                "never claim canon or manuscript adoption. Memory candidates require summary. "
                "Relation candidates require summary or change plus source_entity_name, "
                "target_entity_name, and relationship_type. World-state candidates require "
                "summary or proposal and may include state_changes and involved_agent_ids."
            ),
        },
        {
            "role": "user",
            "content": json.dumps(public_source, ensure_ascii=False, separators=(",", ":")),
        },
    ]


def _validate_provider_result(value: Any) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise LLMFacilityError(
            "LLM_RESPONSE_SCHEMA_INVALID", "character dialogue response must be an object"
        )
    reply = value.get("reply_summary")
    if not isinstance(reply, str) or not reply.strip():
        raise LLMFacilityError(
            "LLM_RESPONSE_SCHEMA_INVALID", "character dialogue reply_summary is required"
        )
    speaker_type = str(value.get("speaker_type") or "agent").strip()
    if speaker_type not in {"agent", "director"}:
        raise LLMFacilityError(
            "LLM_RESPONSE_SCHEMA_INVALID", "character dialogue speaker_type is invalid"
        )
    result = {
        "reply_summary": reply.strip(),
        "speaker_type": speaker_type,
        "speaker_id": str(value.get("speaker_id") or "").strip(),
        "memory_candidates": _candidate_list(value.get("memory_candidates"), "memory"),
        "relation_candidates": _candidate_list(value.get("relation_candidates"), "relation"),
        "world_state_candidates": _candidate_list(value.get("world_state_candidates"), "world_state"),
    }
    _candidate_asset_specs(result)
    return result


def _candidate_list(value: Any, proposal_type: str) -> list[dict[str, Any]]:
    if value is None:
        return []
    if not isinstance(value, list) or any(not isinstance(item, dict) for item in value):
        raise LLMFacilityError(
            "LLM_RESPONSE_SCHEMA_INVALID", "character dialogue candidates must be object arrays"
        )
    normalized: list[dict[str, Any]] = []
    for item in value:
        clean = _sanitize_candidate_value(item)
        if not isinstance(clean, dict):
            clean = {}
        _candidate_summary(clean, proposal_type)
        normalized.append({**clean, "lifecycle": "candidate"})
    return normalized


def _candidate_asset_specs(result: dict[str, Any]) -> list[dict[str, Any]]:
    groups = (
        ("memory_candidates", "memory", "character_memory_proposal", "character"),
        ("relation_candidates", "relation", "character_relation_proposal", "relationship"),
        ("world_state_candidates", "world_state", "character_world_state_proposal", "world_state"),
    )
    specs: list[dict[str, Any]] = []
    for field, proposal_type, asset_type, category in groups:
        for index, candidate in enumerate(result.get(field, []), start=1):
            summary = _candidate_summary(candidate, proposal_type)
            specs.append(
                {
                    "proposal_type": proposal_type,
                    "candidate_index": str(index),
                    "asset_type": asset_type,
                    "category": category,
                    "title": _candidate_title(candidate, proposal_type, index),
                    "summary": summary,
                    "payload": _candidate_payload(candidate, proposal_type, summary),
                    "tags": ["character_console", "candidate", proposal_type],
                }
            )
    return specs


def _candidate_summary(candidate: dict[str, Any], proposal_type: str) -> str:
    keys = {
        "memory": ("summary", "memory", "note"),
        "relation": ("summary", "change", "proposal"),
        "world_state": ("summary", "proposal", "change"),
    }.get(proposal_type, ("summary",))
    for key in keys:
        value = candidate.get(key)
        if isinstance(value, str) and value.strip():
            return value.strip()
    raise LLMFacilityError(
        "LLM_RESPONSE_SCHEMA_INVALID",
        f"character dialogue {proposal_type} candidate summary is required",
    )


def _candidate_payload(
    candidate: dict[str, Any], proposal_type: str, summary: str
) -> dict[str, Any]:
    if proposal_type == "memory":
        memory_type = candidate.get("memory_type")
        return {
            "summary": summary,
            "memory_type": memory_type.strip()
            if isinstance(memory_type, str) and memory_type.strip()
            else "interaction",
        }
    if proposal_type == "relation":
        return {
            "summary": summary,
            "source_entity_name": _required_candidate_text(
                candidate, "source_entity_name", proposal_type
            ),
            "target_entity_name": _required_candidate_text(
                candidate, "target_entity_name", proposal_type
            ),
            "relationship_type": _required_candidate_text(
                candidate, "relationship_type", proposal_type
            ),
        }
    state_changes = candidate.get("state_changes")
    if not isinstance(state_changes, dict):
        state_changes = {"proposal": summary}
    involved = candidate.get("involved_agent_ids")
    if not isinstance(involved, list):
        involved = []
    return {
        "summary": summary,
        "state_changes": _sanitize_candidate_value(state_changes),
        "involved_agent_ids": [
            item.strip() for item in involved if isinstance(item, str) and item.strip()
        ],
    }


def _required_candidate_text(
    candidate: dict[str, Any], field: str, proposal_type: str
) -> str:
    value = candidate.get(field)
    if isinstance(value, str) and value.strip():
        return value.strip()
    raise LLMFacilityError(
        "LLM_RESPONSE_SCHEMA_INVALID",
        f"character dialogue {proposal_type} candidate {field} is required",
    )


def _candidate_title(candidate: dict[str, Any], proposal_type: str, index: int) -> str:
    if proposal_type == "relation":
        target = candidate.get("target")
        if isinstance(target, str) and target.strip():
            return f"Relationship proposal: {target.strip()}"
    labels = {
        "memory": "Character memory proposal",
        "relation": "Character relationship proposal",
        "world_state": "World state proposal",
    }
    return f"{labels.get(proposal_type, 'Character proposal')} {index}"


def _sanitize_candidate_value(value: Any) -> Any:
    if isinstance(value, dict):
        return {
            key: _sanitize_candidate_value(item)
            for key, item in value.items()
            if not _candidate_field_is_sensitive(key)
        }
    if isinstance(value, list):
        return [_sanitize_candidate_value(item) for item in value]
    return value


def _candidate_field_is_sensitive(field: str) -> bool:
    normalized = "".join(character for character in str(field).lower() if character.isalnum())
    return normalized in {
        "apikey",
        "encryptedapikey",
        "credentialref",
        "prompt",
        "response",
        "rawresponse",
        "rawcontent",
        "bodytext",
        "contenttext",
        "draft",
        "manuscript",
    }


def _validate_resolution(resolution: ModuleBindingResolution) -> None:
    if not resolution.provider or not resolution.provider.strip():
        raise LLMFacilityError(
            "LLM_PROVIDER_ERROR", "resolved LLM module is missing provider"
        )
    if not resolution.model_id or not resolution.base_url or not resolution.credential_ref:
        raise LLMFacilityError(
            "LLM_MODULE_UNBOUND", "character_dialogue module binding is incomplete"
        )
    if not resolution.supports_json:
        raise LLMFacilityError(
            "LLM_CAPABILITY_UNSUPPORTED",
            "character_dialogue requires a JSON-capable model",
        )


def _candidate_counts(result: dict[str, Any]) -> dict[str, int]:
    return {
        "memory_candidate_count": len(result.get("memory_candidates", [])),
        "relation_candidate_count": len(result.get("relation_candidates", [])),
        "world_state_candidate_count": len(result.get("world_state_candidates", [])),
    }


def _public_result(result: dict[str, Any]) -> dict[str, Any]:
    return {
        key: result[key]
        for key in (
            "status",
            "replayed",
            "interaction_id",
            "turn_id",
            "turn_order",
            "model_id",
            "memory_candidate_count",
            "relation_candidate_count",
            "world_state_candidate_count",
            "candidate_asset_count",
            "candidate_asset_ids",
        )
        if key in result
    }


def _turn_summary(row: Any) -> dict[str, Any]:
    return {
        "turn_order": row[0],
        "actor_type": row[1],
        "actor_id": row[2],
        "turn_kind": row[3],
        "summary": row[4],
    }


def _required_uuid(value: Any, name: str) -> str:
    try:
        return str(UUID(str(value).strip()))
    except (ValueError, AttributeError) as exc:
        raise LLMFacilityError("VALIDATION_FAILED", f"{name} must be a valid UUID") from exc


def _uuid_or_none(value: Any) -> str | None:
    if value is None:
        return None
    try:
        return str(UUID(str(value).strip()))
    except ValueError:
        return None


def _require_runtime_context(context: AgentContext) -> None:
    if not context.project_id or not context.actor_user_id:
        raise LLMFacilityError(
            "VALIDATION_FAILED", "project_id and actor_user_id are required"
        )


def _rollback(connection: Any) -> None:
    try:
        connection.rollback()
    except Exception:
        pass


def _runner_from_env() -> CharacterDialogueRunner | None:
    database_url = os.environ.get("DATABASE_URL", "").strip()
    if not database_url:
        return None
    from mirofish_agents.llm_quota import (
        PostgresQuotaStore,
        ProviderQuotaGate,
        QuotaAwareJSONChatClient,
        QuotaEnforcedJSONChatClient,
    )

    store = PostgresCharacterDialogueStore.from_database_url(database_url)
    return LLMFacilityCharacterDialogueRunner(
        binding_resolver=PostgresModuleBindingResolver.from_database_url(database_url),
        credential_provider=PostgresCredentialProvider.from_database_url(
            database_url=database_url,
            key_material=os.environ.get("LLM_CREDENTIAL_ENCRYPTION_KEY"),
        ),
        chat_client=QuotaEnforcedJSONChatClient(
            quota_gate=ProviderQuotaGate(PostgresQuotaStore.from_database_url(database_url)),
            stage_prefix="character_dialogue",
            provider_client=QuotaAwareJSONChatClient(),
        ),
        store=store,
    )


def _stable_error(exc: Exception) -> tuple[str, str]:
    if isinstance(exc, LLMFacilityError):
        stable_messages = {
            "LLM_MODULE_UNBOUND": "character_dialogue module is not bound",
            "LLM_BINDING_QUERY_FAILED": "LLM module binding query failed",
            "LLM_CREDENTIAL_UNAVAILABLE": "LLM credential is unavailable",
            "LLM_CREDENTIAL_QUERY_FAILED": "LLM credential query failed",
            "LLM_PROVIDER_ERROR": "character dialogue provider call failed",
            "LLM_CAPABILITY_UNSUPPORTED": "character_dialogue requires a JSON-capable model",
            "LLM_RESPONSE_SCHEMA_INVALID": "character dialogue response schema is invalid",
            "CHARACTER_INTERACTION_NOT_FOUND": "character interaction was not found or is not active",
            "CHARACTER_USER_TURN_NOT_FOUND": "character dialogue user turn was not found",
            "CURRENT_WORLD_REQUIRED": "character dialogue requires the active current_world session",
            "CHARACTER_CONTEXT_LOAD_FAILED": "character dialogue context load failed",
            "CHARACTER_TURN_WRITE_FAILED": "character dialogue turn write failed",
            "WORKFLOW_RUN_NOT_FOUND": "character dialogue admission parent is missing",
            "VALIDATION_FAILED": "character dialogue request is invalid",
        }
        if exc.code in stable_messages:
            return exc.code, stable_messages[exc.code]
    return "CHARACTER_DIALOGUE_FAILED", "character dialogue runtime failed"


@activity.defn
def character_dialogue_activity(
    payload: dict[str, Any], runner: CharacterDialogueRunner | None = None
) -> dict[str, Any]:
    context = AgentContext.model_validate(payload.get("context", payload))
    interaction_id = _required_uuid(payload.get("interaction_id"), "interaction_id")
    user_turn_id = _required_uuid(payload.get("user_turn_id"), "user_turn_id")
    if context.workflow_type != CHARACTER_DIALOGUE_WORKFLOW_TYPE:
        return _failed(context, interaction_id, "VALIDATION_FAILED", "invalid workflow_type", runner)
    if context.module_key != CHARACTER_DIALOGUE_MODULE_KEY:
        return _failed(context, interaction_id, "VALIDATION_FAILED", "invalid module_key", runner)
    if not context.has_permission(CHARACTER_DIALOGUE_MODULE_KEY, "run"):
        return _failed(context, interaction_id, "FORBIDDEN", "character_dialogue run permission is required", runner)
    if runner is None:
        runner = _runner_from_env()
    if runner is None:
        return _failed(
            context,
            interaction_id,
            "CHARACTER_DIALOGUE_BACKEND_UNCONFIGURED",
            "character dialogue backend is not configured",
            runner,
        )
    try:
        result = runner.run_dialogue(
            context=context,
            interaction_id=interaction_id,
            user_turn_id=user_turn_id,
        )
    except Exception as exc:
        code, message = _stable_error(exc)
        return _failed(context, interaction_id, code, message, runner)
    return {
        **context.to_trace_payload(),
        "status": "completed",
        "stage": "character_dialogue",
        "session_id": interaction_id,
        **_public_result(result),
    }


def _failed(
    context: AgentContext,
    interaction_id: str,
    code: str,
    message: str,
    runner: CharacterDialogueRunner | None,
) -> dict[str, Any]:
    store = getattr(runner, "_store", None)
    if store is not None and hasattr(store, "mark_failed"):
        try:
            store.mark_failed(
                context=context,
                interaction_id=interaction_id,
                code=code,
                message=message,
            )
        except Exception:
            code, message = (
                "WORKFLOW_STATUS_WRITE_FAILED",
                "character dialogue workflow status write failed",
            )
    return {
        **context.to_trace_payload(),
        "status": "failed",
        "stage": "character_dialogue",
        "session_id": interaction_id,
        "error": {"code": code, "message": message},
    }


@workflow.defn
class CharacterDialogueWorkflow:
    @workflow.run
    async def run(self, payload: dict[str, Any]) -> dict[str, Any]:
        return await workflow.execute_activity(
            character_dialogue_activity,
            payload,
            start_to_close_timeout=timedelta(minutes=10),
            schedule_to_close_timeout=timedelta(hours=1),
        )


def run_character_dialogue_workflow_locally(
    payload: dict[str, Any], *, runner: CharacterDialogueRunner | None = None
) -> dict[str, Any]:
    return character_dialogue_activity(payload, runner=runner)


def worker_spec() -> dict[str, list[str] | str]:
    return {
        "task_queue": CHARACTER_TASK_QUEUE,
        "workflows": [CharacterDialogueWorkflow.__name__],
        "activities": [character_dialogue_activity.__name__],
    }
