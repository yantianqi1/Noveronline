from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any

import psycopg
import pytest
from psycopg import sql
from psycopg.conninfo import conninfo_to_dict, make_conninfo
from psycopg.rows import dict_row

from mirofish_agents.common.context import AgentContext
from mirofish_agents.seed.sequential_reader import LLMFacilityError
from mirofish_agents.temporal.seed import (
    PostgresReadingNotesWriter,
    PostgresRuntimeFactsWriter,
    PostgresSeedSegmentRetryStore,
)
from mirofish_agents.temporal.seed_retry_projection import (
    PostgresSeedSegmentRetryProjectionStore,
)
from live_schema_guard import ensure_live_schema


ROOT = Path(__file__).resolve().parents[3]
MIGRATION_SQL = ROOT / "infra" / "postgres" / "migrations" / "0001_core_saas.sql"
APP_ROLE = "mirofish_seed_retry_live_app"
APP_PASSWORD = "mirofish_seed_retry_live_password"
TENANT_ID = "81111111-1111-4111-8111-111111111111"
USER_ID = "82222222-2222-4222-8222-222222222222"
PROJECT_ID = "83333333-3333-4333-8333-333333333333"
RUN_ID = "84444444-4444-4444-8444-444444444444"
SEGMENT_IDS = [
    "85555555-5555-4555-8555-555555555555",
    "86666666-6666-4666-8666-666666666666",
]
UNRETRIED_SEGMENT_ID = "88888888-8888-4888-8888-888888888888"
RETRY_ATTEMPT_ID = "87777777-7777-4777-8777-777777777777"
PASS_ID = "246441db-2701-537c-b2f8-092cdec08410"
OTHER_RUN_ID = "8aaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa"

STALE_SEED_ASSET_ID = "8b111111-1111-4111-8111-111111111111"
STALE_RULE_ASSET_ID = "8b222222-2222-4222-8222-222222222222"
PINNED_STALE_ASSET_ID = "8b333333-3333-4333-8333-333333333333"
ADOPTED_STALE_ASSET_ID = "8b444444-4444-4444-8444-444444444444"
KEPT_DISABLED_ASSET_ID = "8b555555-5555-4555-8555-555555555555"
DESIRED_PINNED_ASSET_ID = "8b666666-6666-4666-8666-666666666666"
DESIRED_CANON_ASSET_ID = "8b777777-7777-4777-8777-777777777777"
UNRETRIED_ASSET_ID = "8b888888-8888-4888-8888-888888888888"
MANUAL_CONTROL_ASSET_ID = "8b999999-9999-4999-8999-999999999999"
OTHER_RUN_CONTROL_ASSET_ID = "8baaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa"


def test_seed_segment_retry_postgres_state_machine_live() -> None:
    admin_url = os.environ.get("MIROFISH_SEED_RETRY_LIVE_DATABASE_URL", "").strip()
    if not admin_url:
        pytest.skip("set MIROFISH_SEED_RETRY_LIVE_DATABASE_URL to run the live retry state-machine test")

    _prepare_database(admin_url)
    try:
        store = PostgresSeedSegmentRetryStore.from_database_url(_app_database_url(admin_url))
        context = _context()

        first_claim = store.claim_seed_segment_retries(
            context=context,
            segment_ids=SEGMENT_IDS,
            retry_attempt_id=RETRY_ATTEMPT_ID,
            worker_attempt=1,
        )
        assert [row["segment_id"] for row in first_claim] == SEGMENT_IDS

        duplicate_claim = store.claim_seed_segment_retries(
            context=context,
            segment_ids=SEGMENT_IDS,
            retry_attempt_id=RETRY_ATTEMPT_ID,
            worker_attempt=1,
        )
        assert duplicate_claim == []

        recovered_claim = store.claim_seed_segment_retries(
            context=context,
            segment_ids=SEGMENT_IDS,
            retry_attempt_id=RETRY_ATTEMPT_ID,
            worker_attempt=2,
        )
        assert [row["segment_id"] for row in recovered_claim] == SEGMENT_IDS

        with pytest.raises(LLMFacilityError) as stale_error:
            store.complete_seed_segment_retry_notes(
                context=context,
                segment_ids=SEGMENT_IDS,
                retry_attempt_id=RETRY_ATTEMPT_ID,
                worker_attempt=1,
                pass_id=PASS_ID,
                module_key="sequential_reading",
                model_id="model-stale",
                notes=_retry_notes("stale"),
            )
        assert stale_error.value.code == "SEED_SEGMENT_RETRY_COMPLETION_WRITE_FAILED"

        after_stale = _read_persisted_state(admin_url)
        assert [row["status"] for row in after_stale["requests"]] == ["running", "running"]
        assert [row["worker_attempt"] for row in after_stale["requests"]] == [2, 2]
        assert after_stale["events"] == []
        assert after_stale["passes"] == []
        assert after_stale["notes"] == []

        store.complete_seed_segment_retry_notes(
            context=context,
            segment_ids=SEGMENT_IDS,
            retry_attempt_id=RETRY_ATTEMPT_ID,
            worker_attempt=2,
            pass_id=PASS_ID,
            module_key="sequential_reading",
            model_id="model-live",
            notes=_retry_notes("fresh"),
        )

        persisted = _read_persisted_state(admin_url)
        assert persisted["requests"] == [
            {
                "segment_id": SEGMENT_IDS[0],
                "status": "completed",
                "attempts": 2,
                "worker_attempt": 2,
            },
            {
                "segment_id": SEGMENT_IDS[1],
                "status": "completed",
                "attempts": 2,
                "worker_attempt": 2,
            },
        ]
        assert persisted["events"] == [
            {
                "event_type": "seed.segments.retry_completed",
                "payload_jsonb": {
                    "stage": "segment_retry",
                    "status": "completed",
                    "requested_count": 2,
                    "segment_count": 2,
                    "note_count": 2,
                    "model_id": "model-live",
                },
            }
        ]
        assert persisted["passes"] == [
            {
                "metadata_jsonb": {
                    "retry": True,
                    "segment_count": 2,
                    "last_retry_attempt_id": RETRY_ATTEMPT_ID,
                    "last_retry_segment_count": 2,
                }
            }
        ]
        assert persisted["notes"] == [
            {
                "segment_id": SEGMENT_IDS[0],
                "summary": "fresh summary 0",
                "payload_jsonb": {"characters": [], "world_rules": []},
            },
            {
                "segment_id": SEGMENT_IDS[1],
                "summary": "fresh summary 1",
                "payload_jsonb": {"characters": [], "world_rules": []},
            },
        ]
    finally:
        _cleanup_database(admin_url)


def test_seed_segment_retry_postgres_projection_reconciliation_live() -> None:
    admin_url = os.environ.get("MIROFISH_SEED_RETRY_LIVE_DATABASE_URL", "").strip()
    if not admin_url:
        pytest.skip("set MIROFISH_SEED_RETRY_LIVE_DATABASE_URL to run the live retry projection test")
    if (
        PostgresSeedSegmentRetryProjectionStore.complete_seed_segment_retry_notes
        is PostgresSeedSegmentRetryStore.complete_seed_segment_retry_notes
    ):
        pytest.skip(
            "PostgresSeedSegmentRetryProjectionStore must override "
            "complete_seed_segment_retry_notes before the live projection contract can run"
        )

    _prepare_projection_database(admin_url)
    try:
        store = PostgresSeedSegmentRetryProjectionStore.from_database_url(
            _app_database_url(admin_url)
        )
        context = _context()
        assert [
            row["segment_id"]
            for row in store.claim_seed_segment_retries(
                context=context,
                segment_ids=SEGMENT_IDS,
                retry_attempt_id=RETRY_ATTEMPT_ID,
                worker_attempt=1,
            )
        ] == SEGMENT_IDS
        assert [
            row["segment_id"]
            for row in store.claim_seed_segment_retries(
                context=context,
                segment_ids=SEGMENT_IDS,
                retry_attempt_id=RETRY_ATTEMPT_ID,
                worker_attempt=2,
            )
        ] == SEGMENT_IDS

        before_stale = _read_projection_state(admin_url)
        with pytest.raises(LLMFacilityError) as stale_error:
            store.complete_seed_segment_retry_notes(
                context=context,
                segment_ids=SEGMENT_IDS,
                retry_attempt_id=RETRY_ATTEMPT_ID,
                worker_attempt=1,
                pass_id=PASS_ID,
                module_key="sequential_reading",
                model_id="model-stale",
                notes=_fresh_projection_notes("stale"),
            )
        assert stale_error.value.code == "SEED_SEGMENT_RETRY_COMPLETION_WRITE_FAILED"
        assert _read_projection_state(admin_url) == before_stale

        store.complete_seed_segment_retry_notes(
            context=context,
            segment_ids=SEGMENT_IDS,
            retry_attempt_id=RETRY_ATTEMPT_ID,
            worker_attempt=2,
            pass_id=PASS_ID,
            module_key="sequential_reading",
            model_id="model-live",
            notes=_fresh_projection_notes("fresh"),
        )

        persisted = _read_projection_state(admin_url)
        _assert_projection_completion(persisted, before_stale)
    finally:
        _cleanup_database(admin_url)


def test_seed_segment_retry_postgres_projection_rejects_foreign_aggregate_live() -> None:
    admin_url = os.environ.get("MIROFISH_SEED_RETRY_LIVE_DATABASE_URL", "").strip()
    if not admin_url:
        pytest.skip("set MIROFISH_SEED_RETRY_LIVE_DATABASE_URL to run the live retry projection test")

    _prepare_projection_database(admin_url)
    try:
        _insert_foreign_desired_entity(admin_url)
        store = PostgresSeedSegmentRetryProjectionStore.from_database_url(
            _app_database_url(admin_url)
        )
        context = _context()
        assert [
            row["segment_id"]
            for row in store.claim_seed_segment_retries(
                context=context,
                segment_ids=SEGMENT_IDS,
                retry_attempt_id=RETRY_ATTEMPT_ID,
                worker_attempt=1,
            )
        ] == SEGMENT_IDS
        before_conflict = _read_projection_state(admin_url)

        with pytest.raises(LLMFacilityError) as conflict_error:
            store.complete_seed_segment_retry_notes(
                context=context,
                segment_ids=SEGMENT_IDS,
                retry_attempt_id=RETRY_ATTEMPT_ID,
                worker_attempt=1,
                pass_id=PASS_ID,
                module_key="sequential_reading",
                model_id="model-conflict",
                notes=_fresh_projection_notes("conflict"),
            )

        assert conflict_error.value.code == "SEED_SEGMENT_RETRY_CANON_OWNERSHIP_CONFLICT"
        assert conflict_error.value.message == "seed segment retry canon ownership conflict"
        assert _read_projection_state(admin_url) == before_conflict
    finally:
        _cleanup_database(admin_url)


def _context() -> AgentContext:
    return AgentContext(
        tenant_id=TENANT_ID,
        project_id=PROJECT_ID,
        run_id=RUN_ID,
        workflow_type="seed_pipeline",
        actor_user_id=USER_ID,
        trace_id=f"trace_{RUN_ID}",
        permissions={"seed_pipeline": ["run"]},
    )


def _retry_notes(prefix: str) -> list[dict[str, Any]]:
    return [
        {
            "segment_id": segment_id,
            "summary": f"{prefix} summary {index}",
            "payload_jsonb": {"characters": [], "world_rules": []},
        }
        for index, segment_id in enumerate(SEGMENT_IDS)
    ]


def _old_projection_notes() -> list[dict[str, Any]]:
    return [
        {
            "segment_id": SEGMENT_IDS[0],
            "summary": "old retry summary 0",
            "payload_jsonb": _projection_payload(
                characters=[
                    {"name": "Stale Character", "state_update": "must disappear"},
                    {"name": "Kept Character", "state_update": "old kept state"},
                ],
                world_rules=[{"rule": "stale retry rule", "category": "fixture"}],
            ),
        },
        {
            "segment_id": SEGMENT_IDS[1],
            "summary": "old retry summary 1",
            "payload_jsonb": _projection_payload(
                characters=[
                    {"name": "Desired Pinned Character", "state_update": "old pinned state"},
                    {"name": "Desired Canon Character", "state_update": "old canon state"},
                ]
            ),
        },
        {
            "segment_id": UNRETRIED_SEGMENT_ID,
            "summary": "unretried summary",
            "payload_jsonb": _projection_payload(
                characters=[
                    {"name": "Unretried Character", "state_update": "unchanged state"}
                ],
                world_rules=[{"rule": "unretried rule", "category": "fixture"}],
            ),
        },
    ]


def _fresh_projection_notes(prefix: str) -> list[dict[str, Any]]:
    return [
        {
            "segment_id": SEGMENT_IDS[0],
            "summary": f"{prefix} retry summary 0",
            "payload_jsonb": _projection_payload(
                characters=[
                    {"name": "Kept Character", "state_update": f"{prefix} kept state"},
                    {"name": "Fresh Character", "state_update": f"{prefix} fresh state"},
                ],
                relationships=[
                    {
                        "source": "Fresh Character",
                        "target": "Kept Character",
                        "type": "ally",
                        "summary": f"{prefix} alliance",
                    }
                ],
                world_rules=[
                    {"rule": f"{prefix} retry rule", "category": "fixture"}
                ],
            ),
        },
        {
            "segment_id": SEGMENT_IDS[1],
            "summary": f"{prefix} retry summary 1",
            "payload_jsonb": _projection_payload(
                characters=[
                    {
                        "name": "Desired Pinned Character",
                        "state_update": f"{prefix} pinned state",
                    },
                    {
                        "name": "Desired Canon Character",
                        "state_update": f"{prefix} canon state",
                    },
                ]
            ),
        },
    ]


def _projection_payload(
    *,
    characters: list[dict[str, Any]],
    relationships: list[dict[str, Any]] | None = None,
    world_rules: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    return {
        "characters": characters,
        "organizations": [],
        "relationships": relationships or [],
        "plot_threads": [],
        "world_rules": world_rules or [],
        "events": [],
        "consistency_notes": [],
    }


def _prepare_database(admin_url: str) -> None:
    with psycopg.connect(admin_url, autocommit=True) as connection:
        with connection.cursor() as cursor:
            ensure_live_schema(
                cursor,
                MIGRATION_SQL,
                ("tenants", "projects", "workflow_runs", "seed_segments", "seed_passes", "workflow_events"),
            )
            _ensure_app_role(cursor)
            cursor.execute("DELETE FROM tenants WHERE tenant_id = %s", (TENANT_ID,))
            cursor.execute(
                "INSERT INTO users (user_id, email, display_name) VALUES (%s, %s, %s) "
                "ON CONFLICT (user_id) DO UPDATE SET email = EXCLUDED.email, display_name = EXCLUDED.display_name",
                (USER_ID, "seed-retry-live@example.test", "Seed Retry Live"),
            )
            cursor.execute(
                "INSERT INTO tenants (tenant_id, slug, name, tenant_type) VALUES (%s, %s, %s, 'personal')",
                (TENANT_ID, "seed-retry-live", "Seed Retry Live"),
            )
            cursor.execute(
                "INSERT INTO tenant_memberships (tenant_id, user_id, role) VALUES (%s, %s, 'owner')",
                (TENANT_ID, USER_ID),
            )
            cursor.execute(
                "INSERT INTO projects (tenant_id, project_id, title, created_by) VALUES (%s, %s, %s, %s)",
                (TENANT_ID, PROJECT_ID, "Seed Retry Live", USER_ID),
            )
            cursor.execute(
                "INSERT INTO workflow_runs (tenant_id, run_id, workflow_type, project_id, status, started_by) "
                "VALUES (%s, %s, 'seed_pipeline', %s, 'failed', %s)",
                (TENANT_ID, RUN_ID, PROJECT_ID, USER_ID),
            )
            for index, segment_id in enumerate(SEGMENT_IDS):
                cursor.execute(
                    "INSERT INTO text_segments (tenant_id, segment_id, project_id, run_id, segment_order, object_key) "
                    "VALUES (%s, %s, %s, %s, %s, %s)",
                    (TENANT_ID, segment_id, PROJECT_ID, RUN_ID, index, f"private/segment-{index}.txt"),
                )
                cursor.execute(
                    "INSERT INTO seed_segment_retry_requests ("
                    "tenant_id, project_id, run_id, segment_id, status, requested_by, request_id, retry_attempt_id"
                    ") VALUES (%s, %s, %s, %s, 'requested', %s, %s, %s)",
                    (TENANT_ID, PROJECT_ID, RUN_ID, segment_id, USER_ID, "req-live", RETRY_ATTEMPT_ID),
                )


def _prepare_projection_database(admin_url: str) -> None:
    _prepare_database(admin_url)
    with psycopg.connect(admin_url, autocommit=True) as connection:
        connection.execute(
            "INSERT INTO text_segments ("
            "tenant_id, segment_id, project_id, run_id, segment_order, object_key"
            ") VALUES (%s, %s, %s, %s, 2, %s)",
            (
                TENANT_ID,
                UNRETRIED_SEGMENT_ID,
                PROJECT_ID,
                RUN_ID,
                "private/segment-unretried.txt",
            ),
        )

    app_url = _app_database_url(admin_url)
    context = _context()
    old_notes = _old_projection_notes()
    PostgresReadingNotesWriter.from_database_url(app_url).record_reading_notes(
        context=context,
        pass_id=PASS_ID,
        pass_type="sequential_reading",
        status="completed",
        module_key="sequential_reading",
        model_id="model-old",
        notes=old_notes,
        metadata_jsonb={"fixture": "old-projection"},
    )
    PostgresRuntimeFactsWriter.from_database_url(app_url).record_runtime_facts(
        context=context,
        reading_notes=old_notes,
    )

    with psycopg.connect(admin_url, autocommit=True) as connection:
        with connection.cursor() as cursor:
            _insert_projection_assets(cursor)
            cursor.execute(
                """INSERT INTO global_search_index (
                     tenant_id, project_id, source, source_ref, entity_type,
                     title, body, tags_jsonb, payload_jsonb
                   )
                   SELECT
                     tenant_id, project_id, 'asset', asset_id::text, asset_type,
                     title, COALESCE(summary, title), tags_jsonb,
                     jsonb_build_object('asset_id', asset_id::text, 'fixture', true)
                   FROM assets
                   WHERE tenant_id = %s AND project_id = %s""",
                (TENANT_ID, PROJECT_ID),
            )
            cursor.execute(
                """INSERT INTO project_readiness_snapshots (
                     tenant_id, project_id, run_id, ready_asset_count,
                     ready_entity_count, ready_relationship_count,
                     ready_world_rule_count, metadata_jsonb
                   ) VALUES (%s, %s, %s, 97, 98, 99, 100, '{"fixture":"stale"}'::jsonb)""",
                (TENANT_ID, PROJECT_ID, RUN_ID),
            )


def _insert_foreign_desired_entity(admin_url: str) -> None:
    with psycopg.connect(admin_url, autocommit=True) as connection:
        with connection.cursor() as cursor:
            cursor.execute(
                "INSERT INTO workflow_runs (tenant_id, run_id, workflow_type, project_id, status, started_by) "
                "VALUES (%s, %s, 'seed_pipeline', %s, 'completed', %s)",
                (TENANT_ID, OTHER_RUN_ID, PROJECT_ID, USER_ID),
            )
            cursor.execute(
                "INSERT INTO entities (tenant_id, project_id, source_run_id, canonical_name, entity_type) "
                "VALUES (%s, %s, %s, 'Fresh Character', 'character')",
                (TENANT_ID, PROJECT_ID, OTHER_RUN_ID),
            )


def _insert_projection_assets(cursor: Any) -> None:
    stale_entity_ref = _fact_source_ref(
        cursor,
        "SELECT entity_id::text FROM entities WHERE tenant_id = %s AND project_id = %s "
        "AND source_run_id = %s AND canonical_name = 'Stale Character'",
    )
    stale_rule_ref = _fact_source_ref(
        cursor,
        "SELECT rule_evidence_id::text FROM world_rule_evidence "
        "WHERE tenant_id = %s AND project_id = %s AND run_id = %s "
        "AND rule_text = 'stale retry rule'",
    )
    kept_ref = _fact_source_ref(
        cursor,
        "SELECT entity_id::text FROM entities WHERE tenant_id = %s AND project_id = %s "
        "AND source_run_id = %s AND canonical_name = 'Kept Character'",
    )
    desired_pinned_ref = _fact_source_ref(
        cursor,
        "SELECT entity_id::text FROM entities WHERE tenant_id = %s AND project_id = %s "
        "AND source_run_id = %s AND canonical_name = 'Desired Pinned Character'",
    )
    desired_canon_ref = _fact_source_ref(
        cursor,
        "SELECT entity_id::text FROM entities WHERE tenant_id = %s AND project_id = %s "
        "AND source_run_id = %s AND canonical_name = 'Desired Canon Character'",
    )
    unretried_ref = _fact_source_ref(
        cursor,
        "SELECT entity_id::text FROM entities WHERE tenant_id = %s AND project_id = %s "
        "AND source_run_id = %s AND canonical_name = 'Unretried Character'",
    )

    fixtures = [
        (STALE_SEED_ASSET_ID, "character", "Stale Character", stale_entity_ref, "seed", True, False),
        (STALE_RULE_ASSET_ID, "world_rule", "stale retry rule", stale_rule_ref, "seed", True, False),
        (
            PINNED_STALE_ASSET_ID,
            "character",
            "Pinned Stale Character",
            stale_entity_ref,
            "seed",
            True,
            True,
        ),
        (
            ADOPTED_STALE_ASSET_ID,
            "character",
            "Adopted Stale Character",
            stale_entity_ref,
            "canon",
            True,
            False,
        ),
        (KEPT_DISABLED_ASSET_ID, "character", "Kept Character", kept_ref, "seed", False, False),
        (
            DESIRED_PINNED_ASSET_ID,
            "character",
            "Desired Pinned Character",
            desired_pinned_ref,
            "seed",
            False,
            True,
        ),
        (
            DESIRED_CANON_ASSET_ID,
            "character",
            "Desired Canon Character",
            desired_canon_ref,
            "canon",
            False,
            False,
        ),
        (
            UNRETRIED_ASSET_ID,
            "character",
            "Unretried Character",
            unretried_ref,
            "seed",
            True,
            False,
        ),
    ]
    for asset_id, asset_type, title, source_ref, lifecycle, enabled, pinned in fixtures:
        _insert_projection_asset(
            cursor,
            asset_id=asset_id,
            asset_type=asset_type,
            title=title,
            source_kind="seed_pipeline",
            source_ref=source_ref,
            source_run_id=RUN_ID,
            lifecycle=lifecycle,
            enabled=enabled,
            pinned=pinned,
        )

    _insert_projection_asset(
        cursor,
        asset_id=MANUAL_CONTROL_ASSET_ID,
        asset_type="note",
        title="Manual Control",
        source_kind="manual",
        source_ref="manual-control",
        source_run_id=RUN_ID,
        lifecycle="material",
        enabled=True,
        pinned=False,
    )
    _insert_projection_asset(
        cursor,
        asset_id=OTHER_RUN_CONTROL_ASSET_ID,
        asset_type="character",
        title="Other Run Control",
        source_kind="seed_pipeline",
        source_ref="other-run-control",
        source_run_id=OTHER_RUN_ID,
        lifecycle="seed",
        enabled=True,
        pinned=False,
    )


def _fact_source_ref(cursor: Any, query: str) -> str:
    cursor.execute(query, (TENANT_ID, PROJECT_ID, RUN_ID))
    row = cursor.fetchone()
    assert row is not None
    return str(row[0])


def _insert_projection_asset(
    cursor: Any,
    *,
    asset_id: str,
    asset_type: str,
    title: str,
    source_kind: str,
    source_ref: str,
    source_run_id: str,
    lifecycle: str,
    enabled: bool,
    pinned: bool,
) -> None:
    cursor.execute(
        """INSERT INTO assets (
             tenant_id, asset_id, project_id, scope, asset_type, category,
             lifecycle, title, summary, content_text, payload_jsonb, tags_jsonb,
             source_kind, source_ref, enabled, pinned, created_by
           ) VALUES (
             %s, %s, %s, 'project', %s, 'fixture', %s, %s, %s, %s,
             %s::jsonb, '[]'::jsonb, %s, %s, %s, %s, %s
           )""",
        (
            TENANT_ID,
            asset_id,
            PROJECT_ID,
            asset_type,
            lifecycle,
            title,
            f"old asset: {title}",
            f"old asset: {title}",
            json.dumps({"source_run_id": source_run_id, "fixture": True}),
            source_kind,
            source_ref,
            enabled,
            pinned,
            USER_ID,
        ),
    )


def _ensure_app_role(cursor: Any) -> None:
    cursor.execute("SELECT 1 FROM pg_roles WHERE rolname = %s", (APP_ROLE,))
    if cursor.fetchone() is None:
        cursor.execute(
            sql.SQL("CREATE ROLE {} LOGIN PASSWORD {} IN ROLE mirofish_app").format(
                sql.Identifier(APP_ROLE),
                sql.Literal(APP_PASSWORD),
            )
        )
    else:
        cursor.execute(
            sql.SQL("ALTER ROLE {} WITH LOGIN PASSWORD {}").format(
                sql.Identifier(APP_ROLE),
                sql.Literal(APP_PASSWORD),
            )
        )
    cursor.execute(sql.SQL("GRANT mirofish_app TO {}").format(sql.Identifier(APP_ROLE)))


def _app_database_url(admin_url: str) -> str:
    parts = conninfo_to_dict(admin_url)
    parts["user"] = APP_ROLE
    parts["password"] = APP_PASSWORD
    return make_conninfo(**parts)


def _read_persisted_state(admin_url: str) -> dict[str, list[dict[str, Any]]]:
    with psycopg.connect(admin_url, row_factory=dict_row) as connection:
        with connection.cursor() as cursor:
            cursor.execute(
                "SELECT segment_id::text, status, attempts, worker_attempt "
                "FROM seed_segment_retry_requests WHERE tenant_id = %s AND run_id = %s ORDER BY segment_id",
                (TENANT_ID, RUN_ID),
            )
            requests = list(cursor.fetchall())
            cursor.execute(
                "SELECT event_type, payload_jsonb FROM workflow_events "
                "WHERE tenant_id = %s AND run_id = %s ORDER BY sequence",
                (TENANT_ID, RUN_ID),
            )
            events = list(cursor.fetchall())
            cursor.execute(
                "SELECT metadata_jsonb FROM reading_passes "
                "WHERE tenant_id = %s AND project_id = %s AND run_id = %s AND pass_id = %s",
                (TENANT_ID, PROJECT_ID, RUN_ID, PASS_ID),
            )
            passes = list(cursor.fetchall())
            cursor.execute(
                "SELECT segment_id::text, summary, payload_jsonb FROM reading_segment_notes "
                "WHERE tenant_id = %s AND project_id = %s AND run_id = %s AND pass_id = %s ORDER BY segment_id",
                (TENANT_ID, PROJECT_ID, RUN_ID, PASS_ID),
            )
            notes = list(cursor.fetchall())
    return {"requests": requests, "events": events, "passes": passes, "notes": notes}


def _read_projection_state(admin_url: str) -> dict[str, Any]:
    state: dict[str, Any] = _read_persisted_state(admin_url)
    with psycopg.connect(admin_url, row_factory=dict_row) as connection:
        with connection.cursor() as cursor:
            cursor.execute(
                "SELECT status FROM workflow_runs WHERE tenant_id = %s AND run_id = %s",
                (TENANT_ID, RUN_ID),
            )
            state["workflow_status"] = cursor.fetchone()["status"]
            cursor.execute(
                "SELECT canonical_name, state_summary, source_run_id::text "
                "FROM entities WHERE tenant_id = %s AND project_id = %s ORDER BY canonical_name",
                (TENANT_ID, PROJECT_ID),
            )
            state["entities"] = list(cursor.fetchall())
            cursor.execute(
                "SELECT source_entity_name, target_entity_name, relationship_type, summary, "
                "source_run_id::text FROM relationships WHERE tenant_id = %s AND project_id = %s "
                "ORDER BY source_entity_name, target_entity_name, relationship_type",
                (TENANT_ID, PROJECT_ID),
            )
            state["relationships"] = list(cursor.fetchall())
            cursor.execute(
                "SELECT rule_text, category, run_id::text FROM world_rule_evidence "
                "WHERE tenant_id = %s AND project_id = %s ORDER BY rule_text",
                (TENANT_ID, PROJECT_ID),
            )
            state["world_rules"] = list(cursor.fetchall())
            cursor.execute(
                "SELECT asset_id::text, title, lifecycle, enabled, pinned, summary, "
                "payload_jsonb->>'source_run_id' AS source_run_id FROM assets "
                "WHERE tenant_id = %s AND project_id = %s ORDER BY asset_id",
                (TENANT_ID, PROJECT_ID),
            )
            state["assets"] = list(cursor.fetchall())
            cursor.execute(
                "SELECT source_ref, title, body FROM global_search_index "
                "WHERE tenant_id = %s AND project_id = %s ORDER BY source_ref",
                (TENANT_ID, PROJECT_ID),
            )
            state["search_documents"] = list(cursor.fetchall())
            cursor.execute(
                "SELECT ready_asset_count, ready_entity_count, ready_relationship_count, "
                "ready_world_rule_count, metadata_jsonb FROM project_readiness_snapshots "
                "WHERE tenant_id = %s AND project_id = %s AND run_id = %s",
                (TENANT_ID, PROJECT_ID, RUN_ID),
            )
            state["readiness"] = cursor.fetchone()
    return state


def _assert_projection_completion(
    persisted: dict[str, Any],
    before_stale: dict[str, Any],
) -> None:
    assert persisted["workflow_status"] == before_stale["workflow_status"] == "failed"
    assert [row["status"] for row in persisted["requests"]] == ["completed", "completed"]
    assert [row["worker_attempt"] for row in persisted["requests"]] == [2, 2]
    assert persisted["events"] == [
        {
            "event_type": "seed.segments.retry_completed",
            "payload_jsonb": {
                "stage": "segment_retry",
                "status": "completed",
                "requested_count": 2,
                "segment_count": 2,
                "note_count": 2,
                "model_id": "model-live",
            },
        }
    ]
    assert persisted["passes"] == [
        {
            "metadata_jsonb": {
                "retry": True,
                "fixture": "old-projection",
                "segment_count": 3,
                "last_retry_attempt_id": RETRY_ATTEMPT_ID,
                "last_retry_worker_attempt": 2,
                "last_retry_segment_count": 2,
            }
        }
    ]
    assert persisted["notes"] == [
        {
            "segment_id": SEGMENT_IDS[0],
            "summary": "fresh retry summary 0",
            "payload_jsonb": _fresh_projection_notes("fresh")[0]["payload_jsonb"],
        },
        {
            "segment_id": SEGMENT_IDS[1],
            "summary": "fresh retry summary 1",
            "payload_jsonb": _fresh_projection_notes("fresh")[1]["payload_jsonb"],
        },
        {
            "segment_id": UNRETRIED_SEGMENT_ID,
            "summary": "unretried summary",
            "payload_jsonb": _old_projection_notes()[2]["payload_jsonb"],
        },
    ]

    assert persisted["entities"] == [
        {
            "canonical_name": "Desired Canon Character",
            "state_summary": "fresh canon state",
            "source_run_id": RUN_ID,
        },
        {
            "canonical_name": "Desired Pinned Character",
            "state_summary": "fresh pinned state",
            "source_run_id": RUN_ID,
        },
        {
            "canonical_name": "Fresh Character",
            "state_summary": "fresh fresh state",
            "source_run_id": RUN_ID,
        },
        {
            "canonical_name": "Kept Character",
            "state_summary": "fresh kept state",
            "source_run_id": RUN_ID,
        },
        {
            "canonical_name": "Unretried Character",
            "state_summary": "unchanged state",
            "source_run_id": RUN_ID,
        },
    ]
    assert persisted["relationships"] == [
        {
            "source_entity_name": "Fresh Character",
            "target_entity_name": "Kept Character",
            "relationship_type": "ally",
            "summary": "fresh alliance",
            "source_run_id": RUN_ID,
        }
    ]
    assert persisted["world_rules"] == [
        {"rule_text": "fresh retry rule", "category": "fixture", "run_id": RUN_ID},
        {"rule_text": "unretried rule", "category": "fixture", "run_id": RUN_ID},
    ]

    assets_by_id = {row["asset_id"]: row for row in persisted["assets"]}
    assert {
        asset_id: assets_by_id[asset_id]["enabled"]
        for asset_id in (
            STALE_SEED_ASSET_ID,
            STALE_RULE_ASSET_ID,
            PINNED_STALE_ASSET_ID,
            ADOPTED_STALE_ASSET_ID,
            KEPT_DISABLED_ASSET_ID,
            DESIRED_PINNED_ASSET_ID,
            DESIRED_CANON_ASSET_ID,
            UNRETRIED_ASSET_ID,
            MANUAL_CONTROL_ASSET_ID,
            OTHER_RUN_CONTROL_ASSET_ID,
        )
    } == {
        STALE_SEED_ASSET_ID: False,
        STALE_RULE_ASSET_ID: False,
        PINNED_STALE_ASSET_ID: True,
        ADOPTED_STALE_ASSET_ID: True,
        KEPT_DISABLED_ASSET_ID: True,
        DESIRED_PINNED_ASSET_ID: False,
        DESIRED_CANON_ASSET_ID: False,
        UNRETRIED_ASSET_ID: True,
        MANUAL_CONTROL_ASSET_ID: True,
        OTHER_RUN_CONTROL_ASSET_ID: True,
    }
    assert assets_by_id[KEPT_DISABLED_ASSET_ID]["summary"] == "fresh kept state"
    assert assets_by_id[DESIRED_PINNED_ASSET_ID]["summary"] == (
        "old asset: Desired Pinned Character"
    )
    assert assets_by_id[DESIRED_CANON_ASSET_ID]["summary"] == (
        "old asset: Desired Canon Character"
    )
    assets_by_title = {row["title"]: row for row in persisted["assets"]}
    for title in (
        "Fresh Character",
        "Fresh Character -> Kept Character / ally",
        "fresh retry rule",
    ):
        assert assets_by_title[title]["enabled"] is True
        assert assets_by_title[title]["lifecycle"] == "seed"

    assert {row["title"] for row in persisted["search_documents"]} == {
        "Pinned Stale Character",
        "Adopted Stale Character",
        "Kept Character",
        "Unretried Character",
        "Manual Control",
        "Other Run Control",
        "Fresh Character",
        "Fresh Character -> Kept Character / ally",
        "fresh retry rule",
        "unretried rule",
    }
    assert persisted["readiness"] == {
        "ready_asset_count": 8,
        "ready_entity_count": 5,
        "ready_relationship_count": 1,
        "ready_world_rule_count": 2,
        "metadata_jsonb": {},
    }


def _cleanup_database(admin_url: str) -> None:
    with psycopg.connect(admin_url, autocommit=True) as connection:
        connection.execute("DELETE FROM tenants WHERE tenant_id = %s", (TENANT_ID,))
