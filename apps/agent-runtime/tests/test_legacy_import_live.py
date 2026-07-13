from __future__ import annotations

import asyncio
import hashlib
import json
import os
import sqlite3
import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from typing import Any

import psycopg
import pytest
from psycopg import sql
from psycopg.conninfo import conninfo_to_dict, make_conninfo
from temporalio.client import Client
from temporalio.worker import Worker

from mirofish_agents.legacy_import.planner import deterministic_id
from mirofish_agents.legacy_import.objects import object_lifecycle_from_env
from mirofish_agents.legacy_import.service import LegacyImportService
from mirofish_agents.temporal.legacy_import_workflow import (
    LegacyImportWorkflow,
    legacy_import_apply_activity,
    legacy_import_plan_activity,
    legacy_import_verify_activity,
)
from test_legacy_import import PRIVATE_TEXT, SECRET, SOURCE_PROJECT_ID, build_synthetic_source


ROOT = Path(__file__).resolve().parents[3]
MIGRATION_SQLS = tuple(
    sorted((ROOT / "infra" / "postgres" / "migrations").glob("[0-9][0-9][0-9][0-9]_*.sql"))
)
APP_ROLE = "mirofish_legacy_import_live"
APP_PASSWORD = "mirofish_legacy_import_live_password"
IMPORT_ID = "21000000-0000-4000-8000-000000000001"
FAILED_IMPORT_ID = "21000000-0000-4000-8000-000000000002"
TENANT_A = "21000000-0000-4000-8000-000000000010"
TENANT_B = "21000000-0000-4000-8000-000000000011"
USER_A = "21000000-0000-4000-8000-000000000020"
USER_B = "21000000-0000-4000-8000-000000000021"
PROJECT_A = "21000000-0000-4000-8000-000000000030"
PROJECT_B = "21000000-0000-4000-8000-000000000031"


class _SchemaGuardConnection:
    def __init__(
        self,
        *,
        ledger_exists: bool,
        public_tables: list[str] | None = None,
        checksums: dict[str, str] | None = None,
        sentinels_ready: bool = True,
    ) -> None:
        self.ledger_exists = ledger_exists
        self.public_tables = public_tables or []
        self.checksums = checksums or _expected_migration_checksums()
        self.sentinels_ready = sentinels_ready
        self.executed_raw_migrations: list[str] = []
        self._one: tuple[Any, ...] = (None,)
        self._many: list[tuple[Any, ...]] = []

    def execute(self, statement: str, params: object = None) -> "_SchemaGuardConnection":
        normalized = " ".join(statement.split())
        self._many = []
        if normalized == "SELECT to_regclass('public.mirofish_schema_migrations') IS NOT NULL":
            self._one = (self.ledger_exists,)
        elif normalized == "SELECT version, checksum FROM mirofish_schema_migrations ORDER BY version":
            self._many = sorted(self.checksums.items())
        elif "COALESCE(array_agg(class.relname" in normalized:
            self._one = (self.public_tables,)
        elif statement in {migration.read_text(encoding="utf-8") for migration in MIGRATION_SQLS}:
            self.executed_raw_migrations.append(statement)
        elif "legacy_artifact_imports_version_ownership_check" in normalized:
            self._one = (self.sentinels_ready,)
        return self

    def fetchone(self) -> tuple[Any, ...]:
        return self._one

    def fetchall(self) -> list[tuple[Any, ...]]:
        return self._many


def test_legacy_import_schema_guard_never_replays_upgraded_database() -> None:
    connection = _SchemaGuardConnection(ledger_exists=True)

    _ensure_live_schema(connection)

    assert connection.executed_raw_migrations == []


def test_legacy_import_schema_guard_rejects_ledgerless_nonempty_database() -> None:
    connection = _SchemaGuardConnection(ledger_exists=False, public_tables=["users"])

    with pytest.raises(RuntimeError, match="refusing raw migration replay"):
        _ensure_live_schema(connection)

    assert connection.executed_raw_migrations == []


def test_legacy_import_schema_guard_allows_raw_migrations_only_on_fresh_database() -> None:
    connection = _SchemaGuardConnection(ledger_exists=False)

    _ensure_live_schema(connection)

    assert connection.executed_raw_migrations == [
        migration.read_text(encoding="utf-8") for migration in MIGRATION_SQLS
    ]


def test_legacy_import_schema_guard_rejects_checksum_or_schema_drift() -> None:
    checksums = _expected_migration_checksums()
    latest = MIGRATION_SQLS[-1].stem
    connection = _SchemaGuardConnection(
        ledger_exists=True,
        checksums={**checksums, latest: "0" * 64},
    )
    with pytest.raises(RuntimeError, match=latest):
        _ensure_live_schema(connection)
    assert connection.executed_raw_migrations == []

    connection = _SchemaGuardConnection(ledger_exists=True, sentinels_ready=False)
    with pytest.raises(RuntimeError, match="schema sentinels"):
        _ensure_live_schema(connection)
    assert connection.executed_raw_migrations == []


def test_legacy_import_live_temporal_idempotency_rls_failure_and_guarded_rollback(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    request: pytest.FixtureRequest,
) -> None:
    admin_url = _live_database_url()
    temporal_address = _live_temporal_address()
    source_path = build_synthetic_source(tmp_path / "legacy.db")
    original_source = source_path.read_bytes()
    report_output = tmp_path / "legacy-report.json"
    _prepare_database(admin_url)
    request.addfinalizer(lambda: _cleanup_database(admin_url))
    app_url = _app_database_url(admin_url)
    monkeypatch.setenv("LEGACY_IMPORT_DATABASE_URL", app_url)
    monkeypatch.setenv("LEGACY_IMPORT_SOURCE_ROOT", str(tmp_path))
    _set_live_object_environment(monkeypatch)
    task_queue = f"legacy-import-live-{os.getpid()}-{int(time.time() * 1000)}"
    payload = {
        "source_path": str(source_path),
        "artifact_root": None,
        "import_id": IMPORT_ID,
        "tenant_id": TENANT_A,
        "project_id": PROJECT_A,
        "actor_user_id": USER_A,
        "source_project_id": SOURCE_PROJECT_ID,
        "report_output": str(report_output),
    }

    terminal = asyncio.run(_run_temporal(temporal_address, task_queue, payload))

    assert terminal["status"] == "complete"
    assert set(terminal) == {"status", "family_counts", "report_digest"}
    report = json.loads(report_output.read_text(encoding="utf-8"))
    assert report["operation"] == "verify"
    assert report["status"] == "complete"
    assert report["object_counts"]["unchanged"] == 1
    _assert_private_values_absent({"terminal": terminal, "report": report})
    assert _cross_tenant_count(app_url) == 0
    assert _cross_tenant_object_count(app_url) == 0
    assert _object_statuses(admin_url, IMPORT_ID) == ["verified"]

    service = _service(source_path, app_url, IMPORT_ID)
    replay = _bound_apply(service)
    assert replay["status"] == "complete"
    assert sum(item["imported"] for item in replay["family_counts"].values()) == 0
    assert sum(item["unchanged"] for item in replay["family_counts"].values()) > 0
    assert _apply_audit_count(admin_url, IMPORT_ID) == 1
    approved_plan = service.plan()

    with sqlite3.connect(source_path) as connection:
        connection.execute(
            "INSERT INTO project_artifacts VALUES (?, 'changed', '{}', '2026-01-02', '2026-01-02')",
            (SOURCE_PROJECT_ID,),
        )
    changed_service = service.__class__(
        source_path=str(source_path), artifact_root=None, import_id=IMPORT_ID,
        tenant_id=TENANT_A, project_id=PROJECT_A, actor_user_id=USER_A,
        source_project_id=SOURCE_PROJECT_ID, target_dsn=app_url,
        object_lifecycle=object_lifecycle_from_env(app_url),
    )
    changed = changed_service.apply(
        execute=True,
        expected_source_fingerprint=approved_plan.source.fingerprint,
        expected_plan_hash=approved_plan.plan_hash,
    )
    assert changed["status"] == "failed"
    assert "LEGACY_IMPORT_PLAN_CHANGED" in changed["blockers"]
    assert _object_statuses(admin_url, IMPORT_ID) == ["verified"]
    source_path.write_bytes(original_source)

    planned_object = service._planned_objects()[0]
    replacement_version = service.object_lifecycle.store.put(
        planned_object.object_key,
        planned_object.payload,
        planned_object.media_type,
    )

    asset_id = deterministic_id(IMPORT_ID, TENANT_A, PROJECT_A, "assets", "asset-a")
    _add_later_reference(admin_url, asset_id)
    blocked = _bound_rollback(service)
    assert blocked["status"] == "failed"
    assert "ROLLBACK_GUARD_BLOCKED" in blocked["blockers"]
    assert _target_entity_count(admin_url) == 2
    _remove_later_reference(admin_url)

    entity_id = deterministic_id(IMPORT_ID, TENANT_A, PROJECT_A, "entities", "entity-a")
    original_entity = _modify_imported_entity(admin_url, entity_id)
    modified = _bound_rollback(service)
    assert modified["status"] == "failed"
    assert "IMPORTED_ROW_MODIFIED" in modified["blockers"]
    _restore_imported_entity(admin_url, entity_id, original_entity)

    rolled_back = _bound_rollback(service)
    assert rolled_back["status"] == "complete"
    assert _target_entity_count(admin_url) == 0
    assert _object_statuses(admin_url, IMPORT_ID) == ["deleted"]
    assert service.object_lifecycle.store.get_version(
        planned_object.object_key, replacement_version
    ) == planned_object.payload
    assert service.object_lifecycle.store.get(planned_object.object_key) == planned_object.payload
    service.object_lifecycle.store.delete_version(
        planned_object.object_key, replacement_version
    )

    _prepare_required_conflict(admin_url)
    failed_service = _service(source_path, app_url, FAILED_IMPORT_ID)
    failed = _bound_apply(failed_service)
    assert failed["status"] == "failed"
    assert _failed_import_row_count(admin_url, FAILED_IMPORT_ID) == 0
    _assert_private_values_absent({"failed": failed, "rollback": rolled_back})


async def _run_temporal(address: str, task_queue: str, payload: dict[str, Any]) -> dict[str, Any]:
    client = await Client.connect(address)
    executor = ThreadPoolExecutor(max_workers=4)
    worker = Worker(
        client,
        task_queue=task_queue,
        workflows=[LegacyImportWorkflow],
        activities=[legacy_import_plan_activity, legacy_import_apply_activity, legacy_import_verify_activity],
        activity_executor=executor,
    )
    try:
        async with worker:
            workflow_id = f"legacy-import/{payload['import_id']}/{task_queue}"
            result = await client.execute_workflow(
                LegacyImportWorkflow.run,
                payload,
                id=workflow_id,
                task_queue=task_queue,
            )
            replayed = await client.get_workflow_handle(workflow_id).result()
            assert replayed == result
            return result
    finally:
        executor.shutdown(wait=True)


def _service(source_path: Path, app_url: str, import_id: str) -> LegacyImportService:
    return LegacyImportService(
        source_path=str(source_path),
        artifact_root=None,
        import_id=import_id,
        tenant_id=TENANT_A,
        project_id=PROJECT_A,
        actor_user_id=USER_A,
        source_project_id=SOURCE_PROJECT_ID,
        target_dsn=app_url,
        object_lifecycle=object_lifecycle_from_env(app_url),
    )


def _bound_apply(service: LegacyImportService) -> dict[str, Any]:
    plan = service.plan()
    return service.apply(
        execute=True,
        expected_source_fingerprint=plan.source.fingerprint,
        expected_plan_hash=plan.plan_hash,
    )


def _bound_rollback(service: LegacyImportService) -> dict[str, Any]:
    plan = service.plan()
    return service.rollback(
        execute=True,
        expected_source_fingerprint=plan.source.fingerprint,
        expected_plan_hash=plan.plan_hash,
    )


def _live_database_url() -> str:
    value = os.environ.get("MIROFISH_LEGACY_IMPORT_LIVE_DATABASE_URL", "").strip()
    if not value:
        pytest.skip("set MIROFISH_LEGACY_IMPORT_LIVE_DATABASE_URL for legacy import live PostgreSQL")
    return value


def _live_temporal_address() -> str:
    value = os.environ.get("MIROFISH_LEGACY_IMPORT_LIVE_TEMPORAL_ADDRESS", "").strip()
    if not value:
        pytest.skip("set MIROFISH_LEGACY_IMPORT_LIVE_TEMPORAL_ADDRESS for legacy import live Temporal")
    return value


def _prepare_database(admin_url: str) -> None:
    with psycopg.connect(admin_url, autocommit=True) as connection:
        _ensure_live_schema(connection)
        connection.execute(
            """
            CREATE TABLE IF NOT EXISTS legacy_import_composite_refs (
              tenant_id UUID NOT NULL,
              project_id UUID NOT NULL,
              asset_id UUID NOT NULL,
              note TEXT NOT NULL,
              PRIMARY KEY (tenant_id, project_id, asset_id, note),
              FOREIGN KEY (tenant_id, project_id, asset_id)
                REFERENCES assets(tenant_id, project_id, asset_id) ON DELETE CASCADE
            );
            ALTER TABLE legacy_import_composite_refs ENABLE ROW LEVEL SECURITY;
            ALTER TABLE legacy_import_composite_refs FORCE ROW LEVEL SECURITY;
            DROP POLICY IF EXISTS legacy_import_composite_refs_tenant
              ON legacy_import_composite_refs;
            CREATE POLICY legacy_import_composite_refs_tenant
              ON legacy_import_composite_refs
              USING (tenant_id = NULLIF(current_setting('app.current_tenant_id', true), '')::UUID)
              WITH CHECK (tenant_id = NULLIF(current_setting('app.current_tenant_id', true), '')::UUID);
            GRANT SELECT ON legacy_import_composite_refs TO mirofish_app;
            """
        )
        connection.execute("DELETE FROM tenants WHERE tenant_id IN (%s::uuid, %s::uuid)", (TENANT_A, TENANT_B))
        connection.execute("DELETE FROM users WHERE user_id IN (%s::uuid, %s::uuid)", (USER_A, USER_B))
        role = connection.execute("SELECT 1 FROM pg_roles WHERE rolname = %s", (APP_ROLE,)).fetchone()
        if role is None:
            connection.execute(
                sql.SQL("CREATE ROLE {} LOGIN PASSWORD {} IN ROLE mirofish_app").format(
                    sql.Identifier(APP_ROLE), sql.Literal(APP_PASSWORD)
                )
            )
        else:
            connection.execute(
                sql.SQL("ALTER ROLE {} LOGIN PASSWORD {}").format(sql.Identifier(APP_ROLE), sql.Literal(APP_PASSWORD))
            )
        with connection.cursor() as cursor:
            cursor.executemany(
                "INSERT INTO users (user_id, email, display_name) VALUES (%s::uuid, %s, %s)",
                [(USER_A, "legacy-a@example.test", "Legacy A"), (USER_B, "legacy-b@example.test", "Legacy B")],
            )
            cursor.executemany(
                "INSERT INTO tenants (tenant_id, slug, name, tenant_type) VALUES (%s::uuid, %s, %s, 'personal')",
                [(TENANT_A, "legacy-import-a", "Legacy A"), (TENANT_B, "legacy-import-b", "Legacy B")],
            )
            cursor.executemany(
                "INSERT INTO tenant_memberships (tenant_id, user_id, role) VALUES (%s::uuid, %s::uuid, 'owner')",
                [(TENANT_A, USER_A), (TENANT_B, USER_B)],
            )
            cursor.executemany(
                "INSERT INTO projects (tenant_id, project_id, title, created_by) VALUES (%s::uuid, %s::uuid, %s, %s::uuid)",
                [(TENANT_A, PROJECT_A, "Legacy A", USER_A), (TENANT_B, PROJECT_B, "Legacy B", USER_B)],
            )


def _ensure_live_schema(connection: Any) -> None:
    ledger_exists = bool(
        connection.execute(
            "SELECT to_regclass('public.mirofish_schema_migrations') IS NOT NULL"
        ).fetchone()[0]
    )
    if ledger_exists:
        _validate_live_migration_ledger(connection)
    else:
        _apply_fresh_disposable_migrations(connection)
    _validate_live_schema_sentinels(connection)


def _expected_migration_checksums() -> dict[str, str]:
    return {
        migration.stem: hashlib.sha256(migration.read_bytes()).hexdigest()
        for migration in MIGRATION_SQLS
    }


def _validate_live_migration_ledger(connection: Any) -> None:
    recorded = dict(
        connection.execute(
            "SELECT version, checksum FROM mirofish_schema_migrations ORDER BY version"
        ).fetchall()
    )
    expected = _expected_migration_checksums()
    if set(recorded) != set(expected):
        raise RuntimeError("Legacy import live database migration ledger set is incomplete or unexpected")
    for version, checksum in expected.items():
        if recorded.get(version) != checksum:
            raise RuntimeError(
                f"Legacy import live database migration ledger checksum mismatched for {version}"
            )


def _apply_fresh_disposable_migrations(connection: Any) -> None:
    public_tables = list(
        connection.execute(
            """SELECT COALESCE(array_agg(class.relname ORDER BY class.relname), ARRAY[]::name[])
               FROM pg_class class
               JOIN pg_namespace namespace ON namespace.oid = class.relnamespace
               WHERE namespace.nspname = 'public' AND class.relkind IN ('r', 'p')"""
        ).fetchone()[0]
    )
    if public_tables:
        raise RuntimeError(
            "Legacy import live database has public tables but no migration ledger; "
            "refusing raw migration replay"
        )
    connection.execute(
        """CREATE TABLE mirofish_schema_migrations (
             version TEXT PRIMARY KEY,
             checksum TEXT NOT NULL CHECK (checksum ~ '^[0-9a-f]{64}$'),
             execution_kind TEXT NOT NULL CHECK (execution_kind IN ('applied', 'baselined')),
             applied_at TIMESTAMPTZ NOT NULL DEFAULT now()
           )"""
    )
    for migration in MIGRATION_SQLS:
        connection.execute(migration.read_text(encoding="utf-8"))
        connection.execute(
            "INSERT INTO mirofish_schema_migrations(version,checksum,execution_kind) "
            "VALUES (%s,%s,'applied')",
            (migration.stem, hashlib.sha256(migration.read_bytes()).hexdigest()),
        )
    connection.execute("REVOKE ALL ON mirofish_schema_migrations FROM PUBLIC")
    connection.execute("REVOKE ALL ON mirofish_schema_migrations FROM mirofish_app")


def _validate_live_schema_sentinels(connection: Any) -> None:
    ready = bool(
        connection.execute(
            """SELECT
                 to_regprocedure('app_set_tenant_context(uuid,uuid,boolean)') IS NOT NULL
                 AND to_regclass('public.users') IS NOT NULL
                 AND to_regclass('public.tenants') IS NOT NULL
                 AND to_regclass('public.projects') IS NOT NULL
                 AND to_regclass('public.entities') IS NOT NULL
                 AND to_regclass('public.assets') IS NOT NULL
                 AND to_regclass('public.audit_logs') IS NOT NULL
                 AND to_regclass('public.legacy_artifact_imports') IS NOT NULL
                 AND EXISTS (
                   SELECT 1 FROM pg_attribute
                   WHERE attrelid = 'public.legacy_artifact_imports'::regclass
                     AND attname = 'created_version_id' AND NOT attisdropped
                 )
                 AND EXISTS (
                   SELECT 1 FROM pg_constraint
                   WHERE conrelid = 'public.legacy_artifact_imports'::regclass
                     AND conname = 'legacy_artifact_imports_version_ownership_check'
                 )"""
        ).fetchone()[0]
    )
    if not ready:
        raise RuntimeError("Legacy import live database schema sentinels are incomplete")


def _cleanup_database(admin_url: str) -> None:
    with psycopg.connect(admin_url, autocommit=True) as connection:
        connection.execute("DELETE FROM tenants WHERE tenant_id IN (%s::uuid, %s::uuid)", (TENANT_A, TENANT_B))
        connection.execute("DELETE FROM users WHERE user_id IN (%s::uuid, %s::uuid)", (USER_A, USER_B))
        connection.execute("DROP TABLE IF EXISTS legacy_import_composite_refs")
        connection.execute(sql.SQL("DROP ROLE IF EXISTS {}").format(sql.Identifier(APP_ROLE)))


def _app_database_url(admin_url: str) -> str:
    values = conninfo_to_dict(admin_url)
    values["user"] = APP_ROLE
    values["password"] = APP_PASSWORD
    return make_conninfo(**values)


def _cross_tenant_count(app_url: str) -> int:
    with psycopg.connect(app_url) as connection:
        connection.execute("SELECT app_set_tenant_context(%s::uuid, %s::uuid, false)", (TENANT_B, USER_B))
        return int(connection.execute("SELECT count(*) FROM entities WHERE project_id = %s::uuid", (PROJECT_A,)).fetchone()[0])


def _cross_tenant_object_count(app_url: str) -> int:
    with psycopg.connect(app_url) as connection:
        connection.execute(
            "SELECT app_set_tenant_context(%s::uuid, %s::uuid, false)",
            (TENANT_B, USER_B),
        )
        return int(
            connection.execute(
                "SELECT count(*) FROM legacy_artifact_imports WHERE import_id = %s::uuid",
                (IMPORT_ID,),
            ).fetchone()[0]
        )


def _object_statuses(admin_url: str, import_id: str) -> list[str]:
    with psycopg.connect(admin_url) as connection:
        return [
            str(row[0])
            for row in connection.execute(
                "SELECT status FROM legacy_artifact_imports WHERE import_id = %s::uuid ORDER BY status",
                (import_id,),
            ).fetchall()
        ]


def _set_live_object_environment(monkeypatch: pytest.MonkeyPatch) -> None:
    mapping = {
        "MIROFISH_OBJECT_STORAGE_ENDPOINT": "MIROFISH_LEGACY_IMPORT_LIVE_OBJECT_ENDPOINT",
        "MIROFISH_OBJECT_STORAGE_BUCKET": "MIROFISH_LEGACY_IMPORT_LIVE_OBJECT_BUCKET",
        "MIROFISH_OBJECT_STORAGE_ACCESS_KEY": "MIROFISH_LEGACY_IMPORT_LIVE_OBJECT_ACCESS_KEY",
        "MIROFISH_OBJECT_STORAGE_SECRET_KEY": "MIROFISH_LEGACY_IMPORT_LIVE_OBJECT_SECRET_KEY",
    }
    for target, source in mapping.items():
        value = os.environ.get(source, "").strip()
        if not value:
            pytest.skip(f"set {source} for legacy import live object storage")
        monkeypatch.setenv(target, value)
    monkeypatch.setenv(
        "MIROFISH_OBJECT_STORAGE_USE_SSL",
        os.environ.get("MIROFISH_LEGACY_IMPORT_LIVE_OBJECT_USE_SSL", "false"),
    )
    monkeypatch.setenv(
        "MIROFISH_OBJECT_STORAGE_REGION",
        os.environ.get("MIROFISH_LEGACY_IMPORT_LIVE_OBJECT_REGION", "us-east-1"),
    )


def _apply_audit_count(admin_url: str, import_id: str) -> int:
    with psycopg.connect(admin_url) as connection:
        return int(connection.execute(
            "SELECT count(*) FROM audit_logs WHERE action = 'legacy_import.apply' AND resource_id = %s::uuid",
            (import_id,),
        ).fetchone()[0])


def _add_later_reference(admin_url: str, asset_id: str) -> None:
    with psycopg.connect(admin_url) as connection:
        connection.execute(
            """
            INSERT INTO legacy_import_composite_refs (tenant_id, project_id, asset_id, note)
            VALUES (%s::uuid, %s::uuid, %s::uuid, 'later')
            """,
            (TENANT_A, PROJECT_A, asset_id),
        )


def _remove_later_reference(admin_url: str) -> None:
    with psycopg.connect(admin_url) as connection:
        connection.execute("DELETE FROM legacy_import_composite_refs WHERE note = 'later'")


def _target_entity_count(admin_url: str) -> int:
    with psycopg.connect(admin_url) as connection:
        return int(connection.execute(
            "SELECT count(*) FROM entities WHERE tenant_id = %s::uuid AND project_id = %s::uuid",
            (TENANT_A, PROJECT_A),
        ).fetchone()[0])


def _modify_imported_entity(admin_url: str, entity_id: str) -> dict[str, Any]:
    with psycopg.connect(admin_url, row_factory=psycopg.rows.dict_row) as connection:
        original = connection.execute(
            "SELECT state_summary, updated_at FROM entities WHERE entity_id = %s::uuid", (entity_id,)
        ).fetchone()
        connection.execute(
            "UPDATE entities SET state_summary = 'later author edit', updated_at = clock_timestamp() WHERE entity_id = %s::uuid",
            (entity_id,),
        )
        return original


def _restore_imported_entity(admin_url: str, entity_id: str, original: dict[str, Any]) -> None:
    with psycopg.connect(admin_url) as connection:
        connection.execute(
            "UPDATE entities SET state_summary = %s, updated_at = %s WHERE entity_id = %s::uuid",
            (original["state_summary"], original["updated_at"], entity_id),
        )


def _prepare_required_conflict(admin_url: str) -> None:
    with psycopg.connect(admin_url) as connection:
        run_id = "21000000-0000-4000-8000-000000000050"
        connection.execute(
            "INSERT INTO workflow_runs (tenant_id, run_id, workflow_type, project_id, status) VALUES (%s, %s, 'manual', %s, 'completed')",
            (TENANT_A, run_id, PROJECT_A),
        )
        connection.execute(
            """
            INSERT INTO entities (tenant_id, entity_id, project_id, source_run_id, canonical_name)
            VALUES (%s, %s, %s, %s, 'Alpha')
            """,
            (TENANT_A, "21000000-0000-4000-8000-000000000051", PROJECT_A, run_id),
        )


def _failed_import_row_count(admin_url: str, import_id: str) -> int:
    with psycopg.connect(admin_url) as connection:
        return int(connection.execute(
            "SELECT count(*) FROM workflow_runs WHERE result_jsonb ->> 'import_id' = %s",
            (import_id,),
        ).fetchone()[0])


def _assert_private_values_absent(value: Any) -> None:
    encoded = json.dumps(value, sort_keys=True)
    assert PRIVATE_TEXT not in encoded
    assert SECRET not in encoded
    assert "postgresql://" not in encoded
    assert "password=" not in encoded
