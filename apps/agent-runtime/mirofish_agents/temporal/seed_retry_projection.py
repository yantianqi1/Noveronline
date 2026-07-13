from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any, Callable

from mirofish_agents.common.context import AgentContext
from mirofish_agents.seed.sequential_reader import LLMFacilityError, _reading_pass_id
from mirofish_agents.temporal.seed import (
    PostgresRuntimeFactsWriter,
    PostgresSeedAssetIndexer,
    PostgresSeedSegmentRetryStore,
    _rollback_postgres_connection,
    _record_reading_notes_on_cursor,
    _reading_note_from_row,
    _required_note_segment_id,
    _required_segment_retry_attempt_id,
    _required_segment_retry_context,
    _required_segment_retry_worker_attempt,
    _required_text_value,
    _runtime_entities_from_payload,
    _runtime_note_payload,
    _runtime_plot_threads_from_payload,
    _runtime_relationships_from_payload,
    _set_postgres_tenant_context,
    _validated_runtime_fact_notes,
)


@dataclass(frozen=True)
class _DesiredAggregateKeys:
    entity_names: frozenset[str]
    relationship_keys: frozenset[tuple[str, str, str]]
    plot_thread_titles: frozenset[str]


@dataclass(frozen=True)
class _AggregateMutationScope:
    desired_entity_ids: tuple[str, ...]
    stale_entity_ids: tuple[str, ...]
    desired_relationship_ids: tuple[str, ...]
    stale_relationships: tuple[dict[str, str], ...]
    desired_plot_thread_ids: tuple[str, ...]
    stale_plot_thread_ids: tuple[str, ...]


class PostgresSeedSegmentRetryProjectionStore(PostgresSeedSegmentRetryStore):
    """Atomically replace all retry-derived Seed projections for one run."""

    def __init__(self, *, connect: Callable[[], Any]) -> None:
        super().__init__(connect=connect)
        self._runtime_facts_writer = PostgresRuntimeFactsWriter(connect=connect)
        self._asset_indexer = PostgresSeedAssetIndexer(connect=connect)

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
        normalized_segment_ids = _required_segment_retry_context(context, segment_ids)
        normalized_retry_attempt_id = _required_segment_retry_attempt_id(retry_attempt_id)
        normalized_worker_attempt = _required_segment_retry_worker_attempt(worker_attempt)
        normalized_pass_id = self._required_deterministic_pass_id(context, pass_id)
        normalized_module_key = _required_text_value(module_key, "module_key")
        normalized_notes = self._required_selected_notes(notes, normalized_segment_ids)
        normalized_model_id = model_id.strip() if isinstance(model_id, str) and model_id.strip() else None
        event_payload: dict[str, object] = {
            "stage": "segment_retry",
            "status": "completed",
            "requested_count": len(normalized_segment_ids),
            "segment_count": len(normalized_segment_ids),
            "note_count": len(normalized_notes),
        }
        if normalized_model_id is not None:
            event_payload["model_id"] = normalized_model_id
        encoded_event_payload = json.dumps(
            event_payload,
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
                projected_segment_count = self._upsert_retry_reading_notes(
                    cursor,
                    context=context,
                    segment_ids=normalized_segment_ids,
                    retry_attempt_id=normalized_retry_attempt_id,
                    worker_attempt=normalized_worker_attempt,
                    notes=normalized_notes,
                    pass_id=normalized_pass_id,
                    module_key=normalized_module_key,
                    model_id=normalized_model_id,
                )
                full_pass_notes = self._load_full_pass_reading_notes(
                    cursor,
                    context=context,
                    pass_id=normalized_pass_id,
                )
                if projected_segment_count != len(full_pass_notes):
                    _raise_projection_write_failed()
                self._replace_run_segment_scoped_facts(
                    cursor,
                    context=context,
                    reading_notes=full_pass_notes,
                )
                self._reconcile_seed_assets(cursor, context=context)
                self._upsert_readiness_snapshot(cursor, context=context)
                self._update_finished_seed_segment_retries(
                    cursor,
                    context=context,
                    segment_ids=normalized_segment_ids,
                    retry_attempt_id=normalized_retry_attempt_id,
                    worker_attempt=normalized_worker_attempt,
                    status="completed",
                    code=None,
                    message=None,
                )
                self._insert_seed_segment_retry_event(
                    cursor,
                    context=context,
                    event_type="seed.segments.retry_completed",
                    encoded_payload=encoded_event_payload,
                )
            connection.commit()
        except LLMFacilityError:
            _rollback_postgres_connection(connection)
            raise
        except Exception as exc:
            _rollback_postgres_connection(connection)
            raise LLMFacilityError(
                "SEED_SEGMENT_RETRY_PROJECTION_WRITE_FAILED",
                "seed segment retry projection write failed",
            ) from exc
        finally:
            connection.close()

    def _upsert_retry_reading_notes(
        self,
        cursor: Any,
        *,
        context: AgentContext,
        segment_ids: list[str],
        retry_attempt_id: str | None,
        worker_attempt: int,
        notes: list[dict[str, Any]],
        pass_id: str,
        module_key: str,
        model_id: str | None,
    ) -> int:
        """Replace selected notes after the caller has locked the retry attempt."""

        normalized_segment_ids = _required_segment_retry_context(context, segment_ids)
        normalized_retry_attempt_id = _required_segment_retry_attempt_id(retry_attempt_id)
        normalized_worker_attempt = _required_segment_retry_worker_attempt(worker_attempt)
        normalized_pass_id = self._required_deterministic_pass_id(context, pass_id)
        normalized_module_key = _required_text_value(module_key, "module_key")
        if normalized_module_key != "sequential_reading":
            raise LLMFacilityError(
                "VALIDATION_FAILED",
                "seed segment retry projection module is invalid",
            )
        normalized_notes = self._required_selected_notes(notes, normalized_segment_ids)
        normalized_model_id = model_id.strip() if isinstance(model_id, str) and model_id.strip() else None

        _record_reading_notes_on_cursor(
            cursor,
            context=context,
            pass_id=normalized_pass_id,
            pass_type="sequential_reading",
            status="completed",
            module_key=normalized_module_key,
            model_id=normalized_model_id,
            notes=normalized_notes,
            metadata_jsonb={
                "retry": True,
                "last_retry_attempt_id": normalized_retry_attempt_id,
                "last_retry_worker_attempt": normalized_worker_attempt,
                "last_retry_segment_count": len(normalized_segment_ids),
            },
        )
        cursor.execute(
            """SELECT (metadata_jsonb->>'segment_count')::int AS segment_count
               FROM reading_passes
               WHERE tenant_id = %s
                 AND project_id = %s
                 AND run_id = %s
                 AND pass_id = %s""",
            (
                context.tenant_id,
                context.project_id,
                context.run_id,
                normalized_pass_id,
            ),
        )
        row = cursor.fetchone()
        if row is None:
            _raise_projection_write_failed()
        return _row_int(row, "segment_count", 0)

    def _load_full_pass_reading_notes(
        self,
        cursor: Any,
        *,
        context: AgentContext,
        pass_id: str,
    ) -> list[dict[str, Any]]:
        normalized_pass_id = self._required_deterministic_pass_id(context, pass_id)
        cursor.execute(
            """SELECT
                 reading_note.segment_id::text AS segment_id,
                 reading_note.payload_jsonb,
                 reading_note.summary
               FROM reading_segment_notes AS reading_note
               JOIN text_segments AS text_segment
                 ON text_segment.tenant_id = reading_note.tenant_id
                AND text_segment.project_id = reading_note.project_id
                AND text_segment.run_id = reading_note.run_id
                AND text_segment.segment_id = reading_note.segment_id
               WHERE reading_note.tenant_id = %s
                 AND reading_note.project_id = %s
                 AND reading_note.run_id = %s
                 AND reading_note.pass_id = %s
               ORDER BY text_segment.segment_order ASC, reading_note.segment_id ASC""",
            (
                context.tenant_id,
                context.project_id,
                context.run_id,
                normalized_pass_id,
            ),
        )
        return _validated_runtime_fact_notes(
            [_reading_note_from_row(row) for row in cursor.fetchall()]
        )

    def _replace_run_segment_scoped_facts(
        self,
        cursor: Any,
        *,
        context: AgentContext,
        reading_notes: list[dict[str, Any]],
    ) -> dict[str, int]:
        """Rebuild run-scoped facts; caller must first guard aggregate ownership."""

        normalized_notes = _validated_runtime_fact_notes(reading_notes)
        desired_keys = self._desired_aggregate_keys(normalized_notes)
        mutation_scope = self._lock_and_validate_aggregate_ownership(
            cursor,
            context=context,
            desired_keys=desired_keys,
        )
        self._reset_and_prune_aggregates(
            cursor,
            context=context,
            mutation_scope=mutation_scope,
        )
        self._delete_run_segment_scoped_facts(cursor, context=context)
        return self._runtime_facts_writer._persist_notes(cursor, context, normalized_notes)

    @staticmethod
    def _desired_aggregate_keys(
        reading_notes: list[dict[str, Any]],
    ) -> _DesiredAggregateKeys:
        entity_names: set[str] = set()
        relationship_keys: set[tuple[str, str, str]] = set()
        plot_thread_titles: set[str] = set()
        for note in _validated_runtime_fact_notes(reading_notes):
            payload = _runtime_note_payload(note)
            entity_names.update(entity["name"] for entity in _runtime_entities_from_payload(payload))
            relationship_keys.update(
                (
                    relationship["source_entity_name"],
                    relationship["target_entity_name"],
                    relationship["relationship_type"],
                )
                for relationship in _runtime_relationships_from_payload(payload)
            )
            plot_thread_titles.update(
                thread["title"] for thread in _runtime_plot_threads_from_payload(payload)
            )
        return _DesiredAggregateKeys(
            entity_names=frozenset(entity_names),
            relationship_keys=frozenset(relationship_keys),
            plot_thread_titles=frozenset(plot_thread_titles),
        )

    def _lock_and_validate_aggregate_ownership(
        self,
        cursor: Any,
        *,
        context: AgentContext,
        desired_keys: _DesiredAggregateKeys,
    ) -> _AggregateMutationScope:
        entity_rows = self._lock_relevant_entities(cursor, context=context, desired_keys=desired_keys)
        relationship_rows = self._lock_relevant_relationships(
            cursor,
            context=context,
            desired_keys=desired_keys,
        )
        plot_thread_rows = self._lock_relevant_plot_threads(
            cursor,
            context=context,
            desired_keys=desired_keys,
        )
        mutation_scope = self._classify_aggregate_rows(
            context=context,
            desired_keys=desired_keys,
            entity_rows=entity_rows,
            relationship_rows=relationship_rows,
            plot_thread_rows=plot_thread_rows,
        )
        self._raise_if_stale_aggregates_are_referenced(
            cursor,
            context=context,
            mutation_scope=mutation_scope,
        )
        return mutation_scope

    @staticmethod
    def _lock_relevant_entities(
        cursor: Any,
        *,
        context: AgentContext,
        desired_keys: _DesiredAggregateKeys,
    ) -> list[Any]:
        cursor.execute(
            """SELECT entity_id::text AS entity_id,
                      canonical_name,
                      source_run_id::text AS source_run_id
               FROM entities
               WHERE tenant_id = %s
                 AND project_id = %s
                 AND (
                   source_run_id = %s
                   OR canonical_name = ANY(%s::text[])
                 )
               ORDER BY entity_id
               FOR UPDATE""",
            (
                context.tenant_id,
                context.project_id,
                context.run_id,
                sorted(desired_keys.entity_names),
            ),
        )
        return list(cursor.fetchall())

    @staticmethod
    def _lock_relevant_relationships(
        cursor: Any,
        *,
        context: AgentContext,
        desired_keys: _DesiredAggregateKeys,
    ) -> list[Any]:
        desired_json = _relationship_keys_json(desired_keys.relationship_keys)
        cursor.execute(
            """WITH desired_relationships AS (
                 SELECT source_entity_name, target_entity_name, relationship_type
                 FROM jsonb_to_recordset(%s::jsonb) AS desired(
                   source_entity_name text,
                   target_entity_name text,
                   relationship_type text
                 )
               )
               SELECT relationship.relationship_id::text AS relationship_id,
                      relationship.source_entity_name,
                      relationship.target_entity_name,
                      relationship.relationship_type,
                      relationship.source_run_id::text AS source_run_id
               FROM relationships AS relationship
               WHERE relationship.tenant_id = %s
                 AND relationship.project_id = %s
                 AND (
                   relationship.source_run_id = %s
                   OR EXISTS (
                     SELECT 1
                     FROM desired_relationships AS desired
                     WHERE desired.source_entity_name = relationship.source_entity_name
                       AND desired.target_entity_name = relationship.target_entity_name
                       AND desired.relationship_type = relationship.relationship_type
                   )
                 )
               ORDER BY relationship.relationship_id
               FOR UPDATE OF relationship""",
            (desired_json, context.tenant_id, context.project_id, context.run_id),
        )
        return list(cursor.fetchall())

    @staticmethod
    def _lock_relevant_plot_threads(
        cursor: Any,
        *,
        context: AgentContext,
        desired_keys: _DesiredAggregateKeys,
    ) -> list[Any]:
        cursor.execute(
            """SELECT thread_id::text AS thread_id,
                      title,
                      source_run_id::text AS source_run_id
               FROM plot_threads
               WHERE tenant_id = %s
                 AND project_id = %s
                 AND (
                   source_run_id = %s
                   OR title = ANY(%s::text[])
                 )
               ORDER BY thread_id
               FOR UPDATE""",
            (
                context.tenant_id,
                context.project_id,
                context.run_id,
                sorted(desired_keys.plot_thread_titles),
            ),
        )
        return list(cursor.fetchall())

    @staticmethod
    def _classify_aggregate_rows(
        *,
        context: AgentContext,
        desired_keys: _DesiredAggregateKeys,
        entity_rows: list[Any],
        relationship_rows: list[Any],
        plot_thread_rows: list[Any],
    ) -> _AggregateMutationScope:
        desired_entity_ids: list[str] = []
        stale_entity_ids: list[str] = []
        for row in entity_rows:
            entity_id = _row_text(row, "entity_id", 0)
            key = _row_text(row, "canonical_name", 1)
            source_run_id = _row_text(row, "source_run_id", 2)
            if key in desired_keys.entity_names:
                _require_current_run_ownership(source_run_id, context.run_id)
                desired_entity_ids.append(entity_id)
            elif source_run_id == context.run_id:
                stale_entity_ids.append(entity_id)

        desired_relationship_ids: list[str] = []
        stale_relationships: list[dict[str, str]] = []
        for row in relationship_rows:
            relationship_id = _row_text(row, "relationship_id", 0)
            key = (
                _row_text(row, "source_entity_name", 1),
                _row_text(row, "target_entity_name", 2),
                _row_text(row, "relationship_type", 3),
            )
            source_run_id = _row_text(row, "source_run_id", 4)
            if key in desired_keys.relationship_keys:
                _require_current_run_ownership(source_run_id, context.run_id)
                desired_relationship_ids.append(relationship_id)
            elif source_run_id == context.run_id:
                stale_relationships.append(
                    {
                        "relationship_id": relationship_id,
                        "source_entity_name": key[0],
                        "target_entity_name": key[1],
                        "relationship_type": key[2],
                    }
                )

        desired_plot_thread_ids: list[str] = []
        stale_plot_thread_ids: list[str] = []
        for row in plot_thread_rows:
            thread_id = _row_text(row, "thread_id", 0)
            key = _row_text(row, "title", 1)
            source_run_id = _row_text(row, "source_run_id", 2)
            if key in desired_keys.plot_thread_titles:
                _require_current_run_ownership(source_run_id, context.run_id)
                desired_plot_thread_ids.append(thread_id)
            elif source_run_id == context.run_id:
                stale_plot_thread_ids.append(thread_id)

        return _AggregateMutationScope(
            desired_entity_ids=tuple(desired_entity_ids),
            stale_entity_ids=tuple(stale_entity_ids),
            desired_relationship_ids=tuple(desired_relationship_ids),
            stale_relationships=tuple(stale_relationships),
            desired_plot_thread_ids=tuple(desired_plot_thread_ids),
            stale_plot_thread_ids=tuple(stale_plot_thread_ids),
        )

    def _raise_if_stale_aggregates_are_referenced(
        self,
        cursor: Any,
        *,
        context: AgentContext,
        mutation_scope: _AggregateMutationScope,
    ) -> None:
        if mutation_scope.stale_entity_ids:
            self._query_stale_entity_conflict(
                cursor,
                context=context,
                entity_ids=list(mutation_scope.stale_entity_ids),
            )
        if mutation_scope.stale_relationships:
            self._query_stale_relationship_conflict(
                cursor,
                context=context,
                relationships=list(mutation_scope.stale_relationships),
            )
        if mutation_scope.stale_plot_thread_ids:
            self._query_stale_plot_thread_conflict(
                cursor,
                context=context,
                thread_ids=list(mutation_scope.stale_plot_thread_ids),
            )

    @staticmethod
    def _query_stale_entity_conflict(
        cursor: Any,
        *,
        context: AgentContext,
        entity_ids: list[str],
    ) -> None:
        cursor.execute(
            """WITH stale AS (
                 SELECT unnest(%s::uuid[]) AS entity_id
               )
               SELECT
                 EXISTS (
                   SELECT 1
                   FROM entity_labels AS label
                   JOIN stale ON stale.entity_id = label.entity_id
                   WHERE label.tenant_id = %s
                     AND label.project_id = %s
                     AND label.run_id <> %s
                 )
                 OR EXISTS (
                   SELECT 1
                   FROM entity_evidence AS evidence
                   JOIN stale ON stale.entity_id = evidence.entity_id
                   WHERE evidence.tenant_id = %s
                     AND evidence.project_id = %s
                     AND evidence.run_id <> %s
                 )
                 OR EXISTS (
                   SELECT 1
                   FROM story_graph_nodes AS node
                   JOIN stale ON stale.entity_id = node.canonical_entity_id
                   WHERE node.tenant_id = %s
                     AND node.project_id = %s
                 )
                 OR EXISTS (
                   SELECT 1
                   FROM manuscript_blocks AS block
                   JOIN stale ON stale.entity_id = block.pov_entity_id
                   WHERE block.tenant_id = %s
                     AND block.project_id = %s
                 ) AS ownership_conflict""",
            (
                entity_ids,
                context.tenant_id,
                context.project_id,
                context.run_id,
                context.tenant_id,
                context.project_id,
                context.run_id,
                context.tenant_id,
                context.project_id,
                context.tenant_id,
                context.project_id,
            ),
        )
        _raise_on_ownership_conflict(cursor.fetchone())

    @staticmethod
    def _query_stale_relationship_conflict(
        cursor: Any,
        *,
        context: AgentContext,
        relationships: list[dict[str, str]],
    ) -> None:
        cursor.execute(
            """WITH stale AS (
                 SELECT relationship_id::uuid,
                        source_entity_name,
                        target_entity_name,
                        relationship_type
                 FROM jsonb_to_recordset(%s::jsonb) AS stale_relationship(
                   relationship_id text,
                   source_entity_name text,
                   target_entity_name text,
                   relationship_type text
                 )
               )
               SELECT
                 EXISTS (
                   SELECT 1
                   FROM relationship_events AS event
                   JOIN stale
                     ON stale.source_entity_name = event.source_entity_name
                    AND stale.target_entity_name = event.target_entity_name
                    AND stale.relationship_type = event.relationship_type
                   WHERE event.tenant_id = %s
                     AND event.project_id = %s
                     AND event.run_id <> %s
                 )
                 OR EXISTS (
                   SELECT 1
                   FROM story_graph_evidence AS evidence
                   JOIN stale ON stale.relationship_id::text = evidence.source_id
                   WHERE evidence.tenant_id = %s
                     AND evidence.project_id = %s
                     AND evidence.source_type = 'relationship'
                 ) AS ownership_conflict""",
            (
                json.dumps(relationships, ensure_ascii=False, separators=(",", ":")),
                context.tenant_id,
                context.project_id,
                context.run_id,
                context.tenant_id,
                context.project_id,
            ),
        )
        _raise_on_ownership_conflict(cursor.fetchone())

    @staticmethod
    def _query_stale_plot_thread_conflict(
        cursor: Any,
        *,
        context: AgentContext,
        thread_ids: list[str],
    ) -> None:
        cursor.execute(
            """WITH stale AS (
                 SELECT unnest(%s::uuid[]) AS thread_id
               )
               SELECT
                 EXISTS (
                   SELECT 1
                   FROM thread_lifecycle AS lifecycle
                   JOIN stale ON stale.thread_id = lifecycle.thread_id
                   WHERE lifecycle.tenant_id = %s
                     AND lifecycle.project_id = %s
                     AND lifecycle.run_id <> %s
                 )
                 OR EXISTS (
                   SELECT 1
                   FROM story_graph_evidence AS evidence
                   JOIN stale ON stale.thread_id::text = evidence.source_id
                   WHERE evidence.tenant_id = %s
                     AND evidence.project_id = %s
                     AND evidence.source_type = 'plot_thread'
                 ) AS ownership_conflict""",
            (
                thread_ids,
                context.tenant_id,
                context.project_id,
                context.run_id,
                context.tenant_id,
                context.project_id,
            ),
        )
        _raise_on_ownership_conflict(cursor.fetchone())

    @staticmethod
    def _reset_and_prune_aggregates(
        cursor: Any,
        *,
        context: AgentContext,
        mutation_scope: _AggregateMutationScope,
    ) -> None:
        if mutation_scope.desired_entity_ids:
            cursor.execute(
                """DELETE FROM entity_aliases
                   WHERE tenant_id = %s
                     AND project_id = %s
                     AND entity_id = ANY(%s::uuid[])""",
                (
                    context.tenant_id,
                    context.project_id,
                    list(mutation_scope.desired_entity_ids),
                ),
            )
            cursor.execute(
                """UPDATE entities
                   SET importance = NULL,
                       state_summary = NULL,
                       first_seen_segment_id = NULL,
                       metadata_jsonb = '{}'::jsonb,
                       updated_at = now()
                   WHERE tenant_id = %s
                     AND project_id = %s
                     AND source_run_id = %s
                     AND entity_id = ANY(%s::uuid[])""",
                (
                    context.tenant_id,
                    context.project_id,
                    context.run_id,
                    list(mutation_scope.desired_entity_ids),
                ),
            )
            _require_expected_rowcount(cursor, len(mutation_scope.desired_entity_ids))
        if mutation_scope.stale_entity_ids:
            cursor.execute(
                """DELETE FROM entities
                   WHERE tenant_id = %s
                     AND project_id = %s
                     AND source_run_id = %s
                     AND entity_id = ANY(%s::uuid[])""",
                (
                    context.tenant_id,
                    context.project_id,
                    context.run_id,
                    list(mutation_scope.stale_entity_ids),
                ),
            )
            _require_expected_rowcount(cursor, len(mutation_scope.stale_entity_ids))

        if mutation_scope.desired_relationship_ids:
            cursor.execute(
                """UPDATE relationships
                   SET summary = NULL,
                       first_seen_segment_id = NULL,
                       evidence_text = NULL,
                       metadata_jsonb = '{}'::jsonb,
                       updated_at = now()
                   WHERE tenant_id = %s
                     AND project_id = %s
                     AND source_run_id = %s
                     AND relationship_id = ANY(%s::uuid[])""",
                (
                    context.tenant_id,
                    context.project_id,
                    context.run_id,
                    list(mutation_scope.desired_relationship_ids),
                ),
            )
            _require_expected_rowcount(cursor, len(mutation_scope.desired_relationship_ids))
        stale_relationship_ids = [
            relationship["relationship_id"]
            for relationship in mutation_scope.stale_relationships
        ]
        if stale_relationship_ids:
            cursor.execute(
                """DELETE FROM relationships
                   WHERE tenant_id = %s
                     AND project_id = %s
                     AND source_run_id = %s
                     AND relationship_id = ANY(%s::uuid[])""",
                (
                    context.tenant_id,
                    context.project_id,
                    context.run_id,
                    stale_relationship_ids,
                ),
            )
            _require_expected_rowcount(cursor, len(stale_relationship_ids))

        if mutation_scope.desired_plot_thread_ids:
            cursor.execute(
                """UPDATE plot_threads
                   SET status = 'open',
                       summary = NULL,
                       first_seen_segment_id = NULL,
                       evidence_text = NULL,
                       metadata_jsonb = '{}'::jsonb,
                       updated_at = now()
                   WHERE tenant_id = %s
                     AND project_id = %s
                     AND source_run_id = %s
                     AND thread_id = ANY(%s::uuid[])""",
                (
                    context.tenant_id,
                    context.project_id,
                    context.run_id,
                    list(mutation_scope.desired_plot_thread_ids),
                ),
            )
            _require_expected_rowcount(cursor, len(mutation_scope.desired_plot_thread_ids))
        if mutation_scope.stale_plot_thread_ids:
            cursor.execute(
                """DELETE FROM plot_threads
                   WHERE tenant_id = %s
                     AND project_id = %s
                     AND source_run_id = %s
                     AND thread_id = ANY(%s::uuid[])""",
                (
                    context.tenant_id,
                    context.project_id,
                    context.run_id,
                    list(mutation_scope.stale_plot_thread_ids),
                ),
            )
            _require_expected_rowcount(cursor, len(mutation_scope.stale_plot_thread_ids))

    @staticmethod
    def _delete_run_segment_scoped_facts(cursor: Any, *, context: AgentContext) -> None:
        statements = (
            "DELETE FROM entity_labels WHERE tenant_id = %s AND project_id = %s "
            "AND run_id = %s AND source_kind = 'sequential_reading'",
            "DELETE FROM entity_evidence WHERE tenant_id = %s AND project_id = %s "
            "AND run_id = %s AND source_kind = 'sequential_reading'",
            "DELETE FROM relationship_events WHERE tenant_id = %s AND project_id = %s AND run_id = %s",
            "DELETE FROM character_events WHERE tenant_id = %s AND project_id = %s AND run_id = %s",
            "DELETE FROM world_events WHERE tenant_id = %s AND project_id = %s AND run_id = %s",
            "DELETE FROM thread_lifecycle WHERE tenant_id = %s AND project_id = %s AND run_id = %s",
            "DELETE FROM narrative_arcs WHERE tenant_id = %s AND project_id = %s AND run_id = %s",
            "DELETE FROM volume_summaries WHERE tenant_id = %s AND project_id = %s "
            "AND run_id = %s AND source_kind = 'sequential_reading'",
            "DELETE FROM world_rule_evidence WHERE tenant_id = %s AND project_id = %s AND run_id = %s",
            "DELETE FROM consistency_notes WHERE tenant_id = %s AND project_id = %s AND run_id = %s",
            "DELETE FROM segment_summaries WHERE tenant_id = %s AND project_id = %s "
            "AND run_id = %s AND source_kind = 'sequential_reading'",
        )
        scope = (context.tenant_id, context.project_id, context.run_id)
        for statement in statements:
            cursor.execute(statement, scope)

    def _reconcile_seed_assets(
        self,
        cursor: Any,
        *,
        context: AgentContext,
    ) -> dict[str, int]:
        entity_asset_count = self._asset_indexer._upsert_entity_assets(cursor, context)
        relationship_asset_count = self._asset_indexer._upsert_relationship_assets(cursor, context)
        world_rule_asset_count = self._asset_indexer._upsert_world_rule_assets(cursor, context)
        plot_thread_asset_count = self._asset_indexer._upsert_plot_thread_assets(cursor, context)
        disabled_asset_count = self._disable_stale_seed_assets(cursor, context=context)
        deleted_search_document_count = self._delete_disabled_search_documents(
            cursor,
            context=context,
        )
        search_document_count = self._asset_indexer._upsert_search_documents(cursor, context)
        return {
            "indexed_asset_count": (
                entity_asset_count
                + relationship_asset_count
                + world_rule_asset_count
                + plot_thread_asset_count
            ),
            "disabled_asset_count": disabled_asset_count,
            "deleted_search_document_count": deleted_search_document_count,
            "search_document_count": search_document_count,
        }

    @staticmethod
    def _disable_stale_seed_assets(cursor: Any, *, context: AgentContext) -> int:
        cursor.execute(
            """WITH request_context AS (
                 SELECT
                   %s::uuid AS tenant_id,
                   %s::uuid AS project_id,
                   %s::text AS run_id
               ),
               desired_assets (source_ref, asset_type, title) AS (
                 SELECT entity.entity_id::text, entity.entity_type, entity.canonical_name
                 FROM entities AS entity
                 CROSS JOIN request_context
                 WHERE entity.tenant_id = request_context.tenant_id
                   AND entity.project_id = request_context.project_id
                   AND entity.source_run_id::text = request_context.run_id
                 UNION ALL
                 SELECT
                   relationship.relationship_id::text,
                   'relationship',
                   relationship.source_entity_name || ' -> '
                     || relationship.target_entity_name || ' / '
                     || relationship.relationship_type
                 FROM relationships AS relationship
                 CROSS JOIN request_context
                 WHERE relationship.tenant_id = request_context.tenant_id
                   AND relationship.project_id = request_context.project_id
                   AND relationship.source_run_id::text = request_context.run_id
                 UNION ALL
                 SELECT rule.rule_evidence_id::text, 'world_rule', rule.rule_text
                 FROM world_rule_evidence AS rule
                 CROSS JOIN request_context
                 WHERE rule.tenant_id = request_context.tenant_id
                   AND rule.project_id = request_context.project_id
                   AND rule.run_id::text = request_context.run_id
                 UNION ALL
                 SELECT thread.thread_id::text, 'plot_thread', thread.title
                 FROM plot_threads AS thread
                 CROSS JOIN request_context
                 WHERE thread.tenant_id = request_context.tenant_id
                   AND thread.project_id = request_context.project_id
                   AND thread.source_run_id::text = request_context.run_id
               ),
               disabled AS (
                 UPDATE assets AS asset
                    SET enabled = false,
                        updated_at = now()
                   FROM request_context
                  WHERE asset.tenant_id = request_context.tenant_id
                    AND asset.project_id = request_context.project_id
                    AND asset.source_kind = 'seed_pipeline'
                    AND asset.payload_jsonb->>'source_run_id' = request_context.run_id
                    AND asset.lifecycle = 'seed'
                    AND asset.pinned = false
                    AND asset.enabled = true
                    AND NOT EXISTS (
                      SELECT 1
                      FROM desired_assets AS desired
                      WHERE desired.source_ref = asset.source_ref
                        AND desired.asset_type = asset.asset_type
                        AND desired.title = asset.title
                    )
                 RETURNING asset.asset_id
               )
               SELECT count(*)::int AS disabled_asset_count
               FROM disabled""",
            (context.tenant_id, context.project_id, context.run_id),
        )
        row = cursor.fetchone()
        if row is None:
            _raise_projection_write_failed()
        return _row_int(row, "disabled_asset_count", 0)

    @staticmethod
    def _delete_disabled_search_documents(cursor: Any, *, context: AgentContext) -> int:
        cursor.execute(
            """WITH deleted AS (
                 DELETE FROM global_search_index AS search_document
                 USING assets AS asset
                 WHERE asset.tenant_id = %s
                   AND asset.project_id = %s
                   AND asset.source_kind = 'seed_pipeline'
                   AND asset.payload_jsonb->>'source_run_id' = %s
                   AND asset.enabled = false
                   AND search_document.tenant_id = asset.tenant_id
                   AND search_document.project_id = asset.project_id
                   AND search_document.source = 'asset'
                   AND search_document.source_ref = asset.asset_id::text
                 RETURNING search_document.search_document_id
               )
               SELECT count(*)::int AS deleted_search_document_count
               FROM deleted""",
            (context.tenant_id, context.project_id, context.run_id),
        )
        row = cursor.fetchone()
        if row is None:
            _raise_projection_write_failed()
        return _row_int(row, "deleted_search_document_count", 0)

    @staticmethod
    def _upsert_readiness_snapshot(
        cursor: Any,
        *,
        context: AgentContext,
    ) -> dict[str, Any]:
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
                       AND source_run_id::text = %s
                   ) AS ready_entity_count,
                   (
                     SELECT count(*)::int
                     FROM relationships
                     WHERE tenant_id = %s
                       AND project_id = %s
                       AND source_run_id::text = %s
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
                context.tenant_id,
                context.project_id,
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
        if row is None:
            _raise_projection_write_failed()
        return {
            "project_readiness_snapshot_id": _row_text(
                row,
                "project_readiness_snapshot_id",
                0,
            ),
            "ready_asset_count": _row_int(row, "ready_asset_count", 1),
            "ready_entity_count": _row_int(row, "ready_entity_count", 2),
            "ready_relationship_count": _row_int(row, "ready_relationship_count", 3),
            "ready_world_rule_count": _row_int(row, "ready_world_rule_count", 4),
        }

    @staticmethod
    def _required_deterministic_pass_id(context: AgentContext, pass_id: str) -> str:
        normalized_pass_id = _required_text_value(pass_id, "pass_id")
        if normalized_pass_id != _reading_pass_id(context):
            raise LLMFacilityError(
                "VALIDATION_FAILED",
                "seed segment retry reading pass is invalid",
            )
        return normalized_pass_id

    @staticmethod
    def _required_selected_notes(
        notes: list[dict[str, Any]],
        segment_ids: list[str],
    ) -> list[dict[str, Any]]:
        try:
            normalized_notes = _validated_runtime_fact_notes(notes)
            note_segment_ids = [_required_note_segment_id(note) for note in normalized_notes]
        except (TypeError, ValueError) as exc:
            raise LLMFacilityError(
                "VALIDATION_FAILED",
                "seed segment retry reading notes are invalid",
            ) from exc
        if len(note_segment_ids) != len(segment_ids) or set(note_segment_ids) != set(segment_ids):
            raise LLMFacilityError(
                "VALIDATION_FAILED",
                "seed segment retry reading notes are invalid",
            )
        return normalized_notes


def _raise_projection_write_failed() -> None:
    raise LLMFacilityError(
        "SEED_SEGMENT_RETRY_PROJECTION_WRITE_FAILED",
        "seed segment retry projection write failed",
    )


def _row_int(row: Any, key: str, index: int) -> int:
    value = row.get(key) if isinstance(row, dict) else row[index]
    return int(value or 0)


def _row_text(row: Any, key: str, index: int) -> str:
    value = row.get(key) if isinstance(row, dict) else row[index]
    if value is None:
        _raise_projection_write_failed()
    return str(value)


def _relationship_keys_json(keys: frozenset[tuple[str, str, str]]) -> str:
    values = [
        {
            "source_entity_name": source,
            "target_entity_name": target,
            "relationship_type": relationship_type,
        }
        for source, target, relationship_type in sorted(keys)
    ]
    return json.dumps(values, ensure_ascii=False, separators=(",", ":"))


def _require_current_run_ownership(source_run_id: str, current_run_id: str) -> None:
    if source_run_id != current_run_id:
        _raise_canon_ownership_conflict()


def _raise_on_ownership_conflict(row: Any) -> None:
    if row is None:
        _raise_projection_write_failed()
    value = row.get("ownership_conflict") if isinstance(row, dict) else row[0]
    if bool(value):
        _raise_canon_ownership_conflict()


def _raise_canon_ownership_conflict() -> None:
    raise LLMFacilityError(
        "SEED_SEGMENT_RETRY_CANON_OWNERSHIP_CONFLICT",
        "seed segment retry canon ownership conflict",
    )


def _require_expected_rowcount(cursor: Any, expected: int) -> None:
    rowcount = getattr(cursor, "rowcount", expected)
    if rowcount != expected:
        _raise_projection_write_failed()
