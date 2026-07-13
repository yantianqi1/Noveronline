from __future__ import annotations

import json
from typing import Any

import pytest

from mirofish_agents.common.context import AgentContext
from mirofish_agents.seed.sequential_reader import LLMFacilityError, _reading_pass_id
from mirofish_agents.temporal.seed_retry_projection import (
    PostgresSeedSegmentRetryProjectionStore,
)


TENANT_ID = "11111111-1111-4111-8111-111111111111"
USER_ID = "22222222-2222-4222-8222-222222222222"
PROJECT_ID = "33333333-3333-4333-8333-333333333333"
RUN_ID = "44444444-4444-4444-8444-444444444444"
OTHER_RUN_ID = "44444444-4444-4444-8444-444444444445"
SEGMENT_IDS = [
    "55555555-5555-4555-8555-555555555555",
    "66666666-6666-4666-8666-666666666666",
]
RETRY_ATTEMPT_ID = "77777777-7777-4777-8777-777777777777"
DESIRED_ENTITY_ID = "81111111-1111-4111-8111-111111111111"
STALE_ENTITY_ID = "82222222-2222-4222-8222-222222222222"
DESIRED_RELATIONSHIP_ID = "83333333-3333-4333-8333-333333333333"
STALE_RELATIONSHIP_ID = "84444444-4444-4444-8444-444444444444"
DESIRED_THREAD_ID = "85555555-5555-4555-8555-555555555555"
STALE_THREAD_ID = "86666666-6666-4666-8666-666666666666"


class RecordingCursor:
    def __init__(
        self,
        *,
        fetchone_rows: list[Any] | None = None,
        fetchall_rows: list[Any] | None = None,
        fetchall_batches: list[list[Any]] | None = None,
    ) -> None:
        self.executed: list[tuple[str, tuple[Any, ...] | None]] = []
        self._fetchone_rows = list(fetchone_rows or [])
        self._fetchall_rows = list(fetchall_rows or [])
        self._fetchall_batches = [list(batch) for batch in (fetchall_batches or [])]

    def execute(self, query: str, params: tuple[Any, ...] | None = None) -> None:
        self.executed.append((query, params))

    def __enter__(self) -> "RecordingCursor":
        return self

    def __exit__(self, exc_type: object, exc: object, traceback: object) -> None:
        return None

    def fetchone(self) -> Any:
        return self._fetchone_rows.pop(0) if self._fetchone_rows else None

    def fetchall(self) -> list[Any]:
        if self._fetchall_batches:
            return self._fetchall_batches.pop(0)
        return list(self._fetchall_rows)


class RecordingConnection:
    def __init__(self, *, fail_on_commit: bool = False) -> None:
        self.cursor_instance = RecordingCursor()
        self.fail_on_commit = fail_on_commit
        self.commits = 0
        self.rollbacks = 0
        self.closed = False

    def cursor(self) -> RecordingCursor:
        return self.cursor_instance

    def commit(self) -> None:
        if self.fail_on_commit:
            raise RuntimeError(
                "private commit prompt api_key=sk-hidden credential_ref=secret raw novel text"
            )
        self.commits += 1

    def rollback(self) -> None:
        self.rollbacks += 1

    def close(self) -> None:
        self.closed = True


class RecordingRuntimeFactsWriter:
    def __init__(self) -> None:
        self.calls: list[dict[str, Any]] = []

    def _persist_notes(
        self,
        cursor: RecordingCursor,
        context: AgentContext,
        notes: list[dict[str, Any]],
    ) -> dict[str, int]:
        self.calls.append(
            {
                "tenant_id": context.tenant_id,
                "project_id": context.project_id,
                "run_id": context.run_id,
                "notes": notes,
                "delete_count_before_rebuild": len(cursor.executed),
            }
        )
        return {"segment_summary_count": len(notes)}


def _context() -> AgentContext:
    return AgentContext(
        tenant_id=TENANT_ID,
        project_id=PROJECT_ID,
        run_id=RUN_ID,
        workflow_type="seed_pipeline",
        actor_user_id=USER_ID,
        trace_id=f"trace-{RUN_ID}",
        permissions={"seed_pipeline": ["run"]},
    )


def _notes() -> list[dict[str, Any]]:
    return [
        {
            "segment_id": segment_id,
            "summary": f"summary-{index}",
            "payload_jsonb": {
                "characters": [],
                "organizations": [],
                "relationships": [],
                "plot_threads": [],
                "world_rules": [],
                "events": [],
                "consistency_notes": [],
            },
        }
        for index, segment_id in enumerate(SEGMENT_IDS)
    ]


def _aggregate_notes() -> list[dict[str, Any]]:
    notes = _notes()
    notes[0]["payload_jsonb"].update(
        {
            "characters": [
                {
                    "name": "Lin",
                    "aliases": ["Archivist"],
                    "importance": "major",
                    "state_update": "awake",
                    "evidence": "segment evidence",
                }
            ],
            "organizations": [{"name": "North Guild"}],
            "relationships": [
                {
                    "source": "Lin",
                    "target": "North Guild",
                    "type": "member_of",
                    "summary": "joined",
                }
            ],
            "plot_threads": [
                {
                    "title": "Lost Key",
                    "status": "open",
                    "summary": "the key remains missing",
                }
            ],
        }
    )
    notes[1]["payload_jsonb"]["characters"] = [{"name": "Lin"}]
    return notes


def _store() -> PostgresSeedSegmentRetryProjectionStore:
    return PostgresSeedSegmentRetryProjectionStore(connect=lambda: None)


def _orchestrated_store(
    connection: RecordingConnection,
    *,
    fail_at: str | None = None,
    failure: Exception | None = None,
) -> tuple[PostgresSeedSegmentRetryProjectionStore, list[str]]:
    store = PostgresSeedSegmentRetryProjectionStore(connect=lambda: connection)
    calls: list[str] = []

    def step(name: str, result: Any = None) -> Any:
        calls.append(name)
        if fail_at == name:
            raise failure or RuntimeError("private projection database failure api_key=sk-hidden")
        return result

    store._lock_seed_segment_retry_finish_scope = (  # type: ignore[method-assign]
        lambda cursor, **kwargs: step("lock")
    )
    store._upsert_retry_reading_notes = (  # type: ignore[method-assign]
        lambda cursor, **kwargs: step("notes", 3)
    )
    store._load_full_pass_reading_notes = (  # type: ignore[method-assign]
        lambda cursor, **kwargs: step("load", _notes() + [{**_notes()[0], "segment_id": STALE_ENTITY_ID}])
    )
    store._replace_run_segment_scoped_facts = (  # type: ignore[method-assign]
        lambda cursor, **kwargs: step("facts", {"entity_count": 3})
    )
    store._reconcile_seed_assets = (  # type: ignore[method-assign]
        lambda cursor, **kwargs: step("assets", {"indexed_asset_count": 3})
    )
    store._upsert_readiness_snapshot = (  # type: ignore[method-assign]
        lambda cursor, **kwargs: step("readiness", {"ready_asset_count": 3})
    )
    store._update_finished_seed_segment_retries = (  # type: ignore[method-assign]
        lambda cursor, **kwargs: step("terminal")
    )
    store._insert_seed_segment_retry_event = (  # type: ignore[method-assign]
        lambda cursor, **kwargs: step("event")
    )
    return store, calls


def _complete_projection(store: PostgresSeedSegmentRetryProjectionStore) -> None:
    store.complete_seed_segment_retry_notes(
        context=_context(),
        segment_ids=SEGMENT_IDS,
        retry_attempt_id=RETRY_ATTEMPT_ID,
        worker_attempt=2,
        pass_id=_reading_pass_id(_context()),
        module_key="sequential_reading",
        model_id="model-a",
        notes=_notes(),
    )


def test_retry_projection_public_transaction_commits_all_projections_before_terminal_state() -> None:
    connection = RecordingConnection()
    store, calls = _orchestrated_store(connection)

    _complete_projection(store)

    assert calls == [
        "lock",
        "notes",
        "load",
        "facts",
        "assets",
        "readiness",
        "terminal",
        "event",
    ]
    assert connection.commits == 1
    assert connection.rollbacks == 0
    assert connection.closed is True


def test_retry_projection_public_transaction_preserves_domain_error_and_rolls_back() -> None:
    connection = RecordingConnection()
    domain_error = LLMFacilityError(
        "SEED_SEGMENT_RETRY_CANON_OWNERSHIP_CONFLICT",
        "seed segment retry canon ownership conflict",
    )
    store, calls = _orchestrated_store(
        connection,
        fail_at="facts",
        failure=domain_error,
    )

    with pytest.raises(LLMFacilityError) as exc_info:
        _complete_projection(store)

    assert exc_info.value is domain_error
    assert calls == ["lock", "notes", "load", "facts"]
    assert connection.commits == 0
    assert connection.rollbacks == 1
    assert connection.closed is True


@pytest.mark.parametrize("fail_at", ["notes", "assets", "readiness", "terminal", "event"])
def test_retry_projection_public_transaction_normalizes_unknown_failure(
    fail_at: str,
) -> None:
    connection = RecordingConnection()
    store, calls = _orchestrated_store(connection, fail_at=fail_at)

    with pytest.raises(LLMFacilityError) as exc_info:
        _complete_projection(store)

    assert exc_info.value.code == "SEED_SEGMENT_RETRY_PROJECTION_WRITE_FAILED"
    assert exc_info.value.message == "seed segment retry projection write failed"
    assert fail_at in calls
    assert connection.commits == 0
    assert connection.rollbacks == 1
    assert connection.closed is True
    public_error = json.dumps(
        {"code": exc_info.value.code, "message": exc_info.value.message},
        ensure_ascii=False,
    )
    for forbidden in ("private projection", "api_key", "sk-hidden"):
        assert forbidden not in public_error


def test_retry_projection_public_transaction_rolls_back_commit_failure() -> None:
    connection = RecordingConnection(fail_on_commit=True)
    store, calls = _orchestrated_store(connection)

    with pytest.raises(LLMFacilityError) as exc_info:
        _complete_projection(store)

    assert exc_info.value.code == "SEED_SEGMENT_RETRY_PROJECTION_WRITE_FAILED"
    assert calls[-2:] == ["terminal", "event"]
    assert connection.commits == 0
    assert connection.rollbacks == 1
    assert connection.closed is True
    assert "sk-hidden" not in exc_info.value.message


def test_retry_projection_note_helper_is_scoped_and_records_run_total() -> None:
    context = _context()
    pass_id = _reading_pass_id(context)
    cursor = RecordingCursor(
        fetchone_rows=[{"pass_id": pass_id}, {"pass_id": pass_id}, {"segment_count": 9}],
    )

    total = _store()._upsert_retry_reading_notes(
        cursor,
        context=context,
        segment_ids=SEGMENT_IDS,
        retry_attempt_id=RETRY_ATTEMPT_ID,
        worker_attempt=3,
        notes=_notes(),
        pass_id=pass_id,
        module_key="sequential_reading",
        model_id="model-a",
    )

    assert total == 9
    assert len(cursor.executed) == 5
    pass_sql, pass_params = cursor.executed[0]
    assert "INSERT INTO reading_passes" in pass_sql
    assert "reading_passes.tenant_id = EXCLUDED.tenant_id" in pass_sql
    assert pass_params is not None
    assert pass_params[:-1] == (
        TENANT_ID,
        PROJECT_ID,
        RUN_ID,
        pass_id,
        "sequential_reading",
        "completed",
        "sequential_reading",
        "model-a",
    )
    assert json.loads(pass_params[-1]) == {
        "retry": True,
        "last_retry_attempt_id": RETRY_ATTEMPT_ID,
        "last_retry_worker_attempt": 3,
        "last_retry_segment_count": 2,
    }
    count_sql, count_params = cursor.executed[-2]
    assert "SELECT COUNT(*)" in count_sql
    assert "reading_note.run_id = reading_pass.run_id" in count_sql
    assert "segment_count" in count_sql
    assert count_params == (TENANT_ID, PROJECT_ID, RUN_ID, pass_id)
    total_sql, total_params = cursor.executed[-1]
    assert "metadata_jsonb->>'segment_count'" in total_sql
    assert total_params == (
        TENANT_ID,
        PROJECT_ID,
        RUN_ID,
        pass_id,
    )


def test_retry_projection_note_helper_rejects_non_deterministic_pass_before_sql() -> None:
    cursor = RecordingCursor()

    with pytest.raises(LLMFacilityError) as exc_info:
        _store()._upsert_retry_reading_notes(
            cursor,
            context=_context(),
            segment_ids=SEGMENT_IDS,
            retry_attempt_id=RETRY_ATTEMPT_ID,
            worker_attempt=1,
            notes=_notes(),
            pass_id="88888888-8888-4888-8888-888888888888",
            module_key="sequential_reading",
            model_id=None,
        )

    assert exc_info.value.code == "VALIDATION_FAILED"
    assert cursor.executed == []


def test_retry_projection_loads_only_full_deterministic_pass_in_segment_order() -> None:
    context = _context()
    pass_id = _reading_pass_id(context)
    notes = _notes()
    cursor = RecordingCursor(fetchall_rows=notes)

    loaded = _store()._load_full_pass_reading_notes(
        cursor,
        context=context,
        pass_id=pass_id,
    )

    assert loaded == notes
    query, params = cursor.executed[0]
    assert "JOIN text_segments AS text_segment" in query
    assert "reading_note.tenant_id = %s" in query
    assert "reading_note.project_id = %s" in query
    assert "reading_note.run_id = %s" in query
    assert "reading_note.pass_id = %s" in query
    assert "ORDER BY text_segment.segment_order ASC" in query
    assert params == (TENANT_ID, PROJECT_ID, RUN_ID, pass_id)


def test_retry_projection_replaces_all_run_segment_scoped_tables_before_rebuild() -> None:
    cursor = RecordingCursor()
    store = _store()
    runtime_writer = RecordingRuntimeFactsWriter()
    store._runtime_facts_writer = runtime_writer  # type: ignore[assignment]

    counts = store._replace_run_segment_scoped_facts(
        cursor,
        context=_context(),
        reading_notes=_notes(),
    )

    expected_tables = [
        "entity_labels",
        "entity_evidence",
        "relationship_events",
        "character_events",
        "world_events",
        "thread_lifecycle",
        "narrative_arcs",
        "volume_summaries",
        "world_rule_evidence",
        "consistency_notes",
        "segment_summaries",
    ]
    assert counts == {"segment_summary_count": 2}
    assert len(cursor.executed) == len(expected_tables) + 3
    assert runtime_writer.calls[0]["delete_count_before_rebuild"] == len(expected_tables) + 3
    for (query, params), table in zip(cursor.executed[3:], expected_tables, strict=True):
        assert query.startswith(f"DELETE FROM {table} ")
        assert "tenant_id = %s" in query
        assert "project_id = %s" in query
        assert "run_id = %s" in query
        assert params == (TENANT_ID, PROJECT_ID, RUN_ID)

    sql = "\n".join(query for query, _ in cursor.executed).lower()
    assert "update workflow_runs" not in sql
    assert "seed_segment_retry_requests" not in sql
    assert "workflow_events" not in sql


def test_retry_projection_derives_deduplicated_desired_aggregate_keys() -> None:
    desired = _store()._desired_aggregate_keys(_aggregate_notes())

    assert desired.entity_names == frozenset({"Lin", "North Guild"})
    assert desired.relationship_keys == frozenset(
        {("Lin", "North Guild", "member_of")}
    )
    assert desired.plot_thread_titles == frozenset({"Lost Key"})


def test_retry_projection_rejects_foreign_desired_identity_before_destructive_sql() -> None:
    cursor = RecordingCursor(
        fetchall_batches=[
            [
                {
                    "entity_id": DESIRED_ENTITY_ID,
                    "canonical_name": "Lin",
                    "source_run_id": OTHER_RUN_ID,
                }
            ],
            [],
            [],
        ]
    )
    store = _store()
    runtime_writer = RecordingRuntimeFactsWriter()
    store._runtime_facts_writer = runtime_writer  # type: ignore[assignment]

    with pytest.raises(LLMFacilityError) as exc_info:
        store._replace_run_segment_scoped_facts(
            cursor,
            context=_context(),
            reading_notes=_aggregate_notes(),
        )

    assert exc_info.value.code == "SEED_SEGMENT_RETRY_CANON_OWNERSHIP_CONFLICT"
    assert exc_info.value.message == "seed segment retry canon ownership conflict"
    assert runtime_writer.calls == []
    assert len(cursor.executed) == 3
    assert all(_is_read_only_ownership_sql(query) for query, _ in cursor.executed)


def test_retry_projection_rejects_referenced_stale_identity_before_destructive_sql() -> None:
    cursor = RecordingCursor(
        fetchone_rows=[{"ownership_conflict": True}],
        fetchall_batches=[
            [
                {
                    "entity_id": STALE_ENTITY_ID,
                    "canonical_name": "Removed",
                    "source_run_id": RUN_ID,
                }
            ],
            [],
            [],
        ],
    )
    store = _store()
    runtime_writer = RecordingRuntimeFactsWriter()
    store._runtime_facts_writer = runtime_writer  # type: ignore[assignment]

    with pytest.raises(LLMFacilityError) as exc_info:
        store._replace_run_segment_scoped_facts(
            cursor,
            context=_context(),
            reading_notes=_notes(),
        )

    assert exc_info.value.code == "SEED_SEGMENT_RETRY_CANON_OWNERSHIP_CONFLICT"
    assert runtime_writer.calls == []
    assert len(cursor.executed) == 4
    assert all(_is_read_only_ownership_sql(query) for query, _ in cursor.executed)
    conflict_sql = cursor.executed[-1][0]
    assert "entity_labels" in conflict_sql
    assert "entity_evidence" in conflict_sql
    assert "story_graph_nodes" in conflict_sql
    assert "manuscript_blocks" in conflict_sql
    assert "FROM assets" not in conflict_sql


def test_retry_projection_preserves_desired_ids_and_deletes_unreferenced_stale_rows() -> None:
    cursor = RecordingCursor(
        fetchone_rows=[
            {"ownership_conflict": False},
            {"ownership_conflict": False},
            {"ownership_conflict": False},
        ],
        fetchall_batches=[
            [
                {
                    "entity_id": DESIRED_ENTITY_ID,
                    "canonical_name": "Lin",
                    "source_run_id": RUN_ID,
                },
                {
                    "entity_id": STALE_ENTITY_ID,
                    "canonical_name": "Removed",
                    "source_run_id": RUN_ID,
                },
            ],
            [
                {
                    "relationship_id": DESIRED_RELATIONSHIP_ID,
                    "source_entity_name": "Lin",
                    "target_entity_name": "North Guild",
                    "relationship_type": "member_of",
                    "source_run_id": RUN_ID,
                },
                {
                    "relationship_id": STALE_RELATIONSHIP_ID,
                    "source_entity_name": "Removed",
                    "target_entity_name": "Lin",
                    "relationship_type": "opposes",
                    "source_run_id": RUN_ID,
                },
            ],
            [
                {
                    "thread_id": DESIRED_THREAD_ID,
                    "title": "Lost Key",
                    "source_run_id": RUN_ID,
                },
                {
                    "thread_id": STALE_THREAD_ID,
                    "title": "Closed Thread",
                    "source_run_id": RUN_ID,
                },
            ],
        ],
    )
    store = _store()
    runtime_writer = RecordingRuntimeFactsWriter()
    store._runtime_facts_writer = runtime_writer  # type: ignore[assignment]

    counts = store._replace_run_segment_scoped_facts(
        cursor,
        context=_context(),
        reading_notes=_aggregate_notes(),
    )

    assert counts == {"segment_summary_count": 2}
    assert len(runtime_writer.calls) == 1
    alias_delete = _find_sql(cursor, "DELETE FROM entity_aliases")
    assert alias_delete[1] == (TENANT_ID, PROJECT_ID, [DESIRED_ENTITY_ID])
    entity_reset = _find_sql(cursor, "UPDATE entities")
    assert "importance = NULL" in entity_reset[0]
    assert "first_seen_segment_id = NULL" in entity_reset[0]
    assert entity_reset[1] == (
        TENANT_ID,
        PROJECT_ID,
        RUN_ID,
        [DESIRED_ENTITY_ID],
    )
    entity_delete = _find_sql(cursor, "DELETE FROM entities")
    assert entity_delete[1][-1] == [STALE_ENTITY_ID]

    relationship_reset = _find_sql(cursor, "UPDATE relationships")
    assert relationship_reset[1][-1] == [DESIRED_RELATIONSHIP_ID]
    relationship_delete = _find_sql(cursor, "DELETE FROM relationships")
    assert relationship_delete[1][-1] == [STALE_RELATIONSHIP_ID]
    thread_reset = _find_sql(cursor, "UPDATE plot_threads")
    assert thread_reset[1][-1] == [DESIRED_THREAD_ID]
    thread_delete = _find_sql(cursor, "DELETE FROM plot_threads")
    assert thread_delete[1][-1] == [STALE_THREAD_ID]

    relationship_guard = _find_sql_containing(cursor, "FROM relationship_events")
    assert "event.run_id <> %s" in relationship_guard[0]
    assert "evidence.source_type = 'relationship'" in relationship_guard[0]
    thread_guard = _find_sql_containing(cursor, "FROM thread_lifecycle")
    assert "lifecycle.run_id <> %s" in thread_guard[0]
    assert "evidence.source_type = 'plot_thread'" in thread_guard[0]
    for guard in (relationship_guard, thread_guard):
        assert "FROM assets" not in guard[0]

    destructive_sql = "\n".join(
        query
        for query, _ in cursor.executed
        if query.lstrip().startswith(("DELETE", "UPDATE"))
    )
    assert DESIRED_ENTITY_ID not in destructive_sql
    assert "DELETE FROM entities" in destructive_sql


def _is_read_only_ownership_sql(query: str) -> bool:
    normalized = query.lstrip().upper()
    statements = [line.strip() for line in normalized.splitlines()]
    return (
        (normalized.startswith("SELECT") or normalized.startswith("WITH"))
        and not any(
            line.startswith(("DELETE FROM", "UPDATE ", "INSERT INTO"))
            for line in statements
        )
    )


def _find_sql(
    cursor: RecordingCursor,
    prefix: str,
) -> tuple[str, tuple[Any, ...]]:
    for query, params in cursor.executed:
        if query.lstrip().startswith(prefix):
            assert params is not None
            return query, params
    raise AssertionError(f"SQL not found: {prefix}")


def _find_sql_containing(
    cursor: RecordingCursor,
    fragment: str,
) -> tuple[str, tuple[Any, ...]]:
    for query, params in cursor.executed:
        if fragment in query:
            assert params is not None
            return query, params
    raise AssertionError(f"SQL not found: {fragment}")


def test_retry_projection_inherits_attempt_worker_running_scope_lock() -> None:
    cursor = RecordingCursor(
        fetchall_rows=[{"segment_id": SEGMENT_IDS[0]}, {"segment_id": SEGMENT_IDS[1]}],
    )

    _store()._lock_seed_segment_retry_finish_scope(
        cursor,
        context=_context(),
        segment_ids=SEGMENT_IDS,
        retry_attempt_id=RETRY_ATTEMPT_ID,
        worker_attempt=4,
    )

    query, params = cursor.executed[0]
    assert "retry_requests.retry_attempt_id = %s::uuid" in query
    assert "retry_requests.worker_attempt = %s" in query
    assert "retry_requests.status = 'running'" in query
    assert "FOR UPDATE OF retry_requests, workflow_runs" in query
    assert params == (
        SEGMENT_IDS,
        TENANT_ID,
        PROJECT_ID,
        RUN_ID,
        RETRY_ATTEMPT_ID,
        4,
    )
