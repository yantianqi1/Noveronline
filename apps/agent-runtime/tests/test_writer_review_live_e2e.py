from __future__ import annotations

import asyncio
import base64
import hashlib
import json
import os
import subprocess
import threading
import time
from concurrent.futures import ThreadPoolExecutor
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any

import psycopg
import pytest
from cryptography.hazmat.primitives.ciphers.aead import AESGCM
from psycopg import sql
from psycopg.conninfo import conninfo_to_dict, make_conninfo
from psycopg.rows import dict_row
from temporalio.client import Client
from temporalio.worker import Worker

from mirofish_agents.temporal.writer_review import WriterReviewWorkflow, writer_review_activity


ROOT = Path(__file__).resolve().parents[3]
MIGRATION_SQL = ROOT / "infra" / "postgres" / "migrations" / "0001_core_saas.sql"
QUOTA_MIGRATION_SQL = ROOT / "infra" / "postgres" / "migrations" / "0003_llm_quota_billing.sql"
REQUIRED_MIGRATIONS = {
    "0001_core_saas": MIGRATION_SQL,
    "0003_llm_quota_billing": QUOTA_MIGRATION_SQL,
}
KEY_MATERIAL = "000102030405060708090a0b0c0d0e0f101112131415161718191a1b1c1d1e1f"
APP_ROLE = "mirofish_writer_review_live_app"
APP_PASSWORD = "mirofish_writer_review_live_password"
TENANT_ID = "81111111-1111-4111-8111-111111111111"
USER_ID = "82222222-2222-4222-8222-222222222222"
PROJECT_ID = "83333333-3333-4333-8333-333333333333"
WRITER_RUN_ID = "84444444-4444-4444-8444-444444444444"
DRAFT_ID = "85555555-5555-4555-8555-555555555555"
CHANNEL_ID = "86666666-6666-4666-8666-666666666666"
OTHER_TENANT_ID = "87777777-7777-4777-8777-777777777777"
OTHER_USER_ID = "88888888-8888-4888-8888-888888888888"
OTHER_PROJECT_ID = "89999999-9999-4999-8999-999999999999"


class _SchemaGuardCursor:
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
        self.checksums = checksums or {
            version: hashlib.sha256(path.read_bytes()).hexdigest()
            for version, path in REQUIRED_MIGRATIONS.items()
        }
        self.sentinels_ready = sentinels_ready
        self.executed_raw_migrations: list[str] = []
        self._one: tuple[Any, ...] = (None,)
        self._many: list[tuple[Any, ...]] = []

    def execute(self, statement: str, params: object = None) -> None:
        normalized = " ".join(statement.split())
        self._many = []
        if normalized == "SELECT to_regclass('public.mirofish_schema_migrations') IS NOT NULL":
            self._one = (self.ledger_exists,)
        elif normalized.startswith("SELECT version, checksum FROM mirofish_schema_migrations"):
            self._many = list(self.checksums.items())
        elif "COALESCE(array_agg(class.relname" in normalized:
            self._one = (self.public_tables,)
        elif "to_regprocedure('app_set_tenant_context(uuid,uuid,boolean)')" in normalized:
            self._one = (self.sentinels_ready,)
        else:
            self.executed_raw_migrations.append(statement)

    def fetchone(self) -> tuple[Any, ...]:
        return self._one

    def fetchall(self) -> list[tuple[Any, ...]]:
        return self._many


def test_writer_review_schema_guard_never_replays_migrations_on_upgraded_database() -> None:
    cursor = _SchemaGuardCursor(ledger_exists=True)

    _ensure_live_schema(cursor)

    assert cursor.executed_raw_migrations == []


def test_writer_review_schema_guard_rejects_ledgerless_nonempty_database() -> None:
    cursor = _SchemaGuardCursor(ledger_exists=False, public_tables=["users"])

    with pytest.raises(RuntimeError, match="refusing raw migration replay"):
        _ensure_live_schema(cursor)

    assert cursor.executed_raw_migrations == []


def test_writer_review_schema_guard_allows_raw_baseline_only_on_fresh_database() -> None:
    cursor = _SchemaGuardCursor(ledger_exists=False)

    _ensure_live_schema(cursor)

    assert cursor.executed_raw_migrations == [
        migration.read_text(encoding="utf-8") for migration in REQUIRED_MIGRATIONS.values()
    ]


def test_writer_review_schema_guard_rejects_mismatched_ledger() -> None:
    cursor = _SchemaGuardCursor(
        ledger_exists=True,
        checksums={**_SchemaGuardCursor(ledger_exists=True).checksums, "0003_llm_quota_billing": "0" * 64},
    )

    with pytest.raises(RuntimeError, match="0003_llm_quota_billing"):
        _ensure_live_schema(cursor)

    assert cursor.executed_raw_migrations == []


def test_writer_review_live_go_temporal_app_role_provider_and_issue_lifecycle(
    monkeypatch: pytest.MonkeyPatch,
    request: pytest.FixtureRequest,
) -> None:
    asyncio.run(_run_live(monkeypatch, request))


async def _run_live(monkeypatch: pytest.MonkeyPatch, request: pytest.FixtureRequest) -> None:
    admin_url = _live_database_url()
    temporal_address = _live_temporal_address()
    namespace = os.environ.get("MIROFISH_WRITER_REVIEW_LIVE_TEMPORAL_NAMESPACE", "default").strip() or "default"
    task_queue = f"writer-review-live-{os.getpid()}-{int(time.time() * 1000)}"
    request.addfinalizer(lambda: _cleanup_database(admin_url))

    with _LocalProvider() as provider:
        _prepare_database(admin_url, provider.base_url)
        app_url = _app_database_url(admin_url)
        monkeypatch.setenv("DATABASE_URL", app_url)
        monkeypatch.setenv("LLM_CREDENTIAL_ENCRYPTION_KEY", KEY_MATERIAL)
        client = await Client.connect(temporal_address, namespace=namespace)
        async with _ReviewerWorker(client, task_queue):
            await asyncio.to_thread(
                _run_go_live,
                "TestWriterReviewCrossServiceAdmissionLive",
                app_url,
                temporal_address,
                namespace,
                task_queue,
            )
            state = await asyncio.to_thread(_wait_for_completion, admin_url)
            await asyncio.to_thread(
                _run_go_live,
                "TestWriterReviewStartCompensationLive|TestWriterReviewIssueMutationLive",
                app_url,
                temporal_address,
                namespace,
                task_queue,
            )
        final = _read_final_state(admin_url)

    assert len(provider.requests) == 1
    assert state["review_status"] == "completed"
    assert state["workflow_status"] == "completed"
    assert state["issue_count"] == 3
    assert state["draft_status"] == "candidate"
    assert state["manuscript_count"] == 0
    assert state["completed_activity_count"] == 1
    assert state["usage_quantity"] == 50
    assert state["finalized_reservation_count"] == 1
    assert state["queued_event_count"] == 1
    assert state["completed_event_count"] == 1
    assert final["issue_statuses"] == ["accepted", "dismissed", "resolved"]
    assert final["issue_audit_count"] == 3
    assert final["compensated_review_status"] == "failed"
    assert final["compensated_issue_count"] == 0
    assert final["draft_status"] == "candidate"
    assert final["manuscript_count"] == 0
    public = json.dumps({"state": state, "final": final}, sort_keys=True)
    for forbidden in (
        "Private candidate opening",
        "sk-writer-review-live",
        "credential_ref",
        "content_text",
        "provider response",
        "summary",
        "suggestion",
    ):
        assert forbidden not in public


class _LocalProvider:
    def __init__(self) -> None:
        self.requests: list[dict[str, Any]] = []
        self._server = ThreadingHTTPServer(("127.0.0.1", 0), self._handler())
        self.base_url = f"http://127.0.0.1:{self._server.server_port}/v1"
        self._thread = threading.Thread(target=self._server.serve_forever, daemon=True)

    def __enter__(self) -> "_LocalProvider":
        self._thread.start()
        return self

    def __exit__(self, exc_type: object, exc: object, traceback: object) -> None:
        self._server.shutdown()
        self._server.server_close()
        self._thread.join(timeout=5)

    def _handler(self) -> type[BaseHTTPRequestHandler]:
        owner = self

        class Handler(BaseHTTPRequestHandler):
            def do_POST(self) -> None:  # noqa: N802
                length = int(self.headers.get("Content-Length", "0"))
                payload = json.loads(self.rfile.read(length).decode("utf-8"))
                owner.requests.append({"path": self.path, "headers": dict(self.headers), "body": payload})
                content = {
                    "issues": [
                        {
                            "severity": "high",
                            "category": "pov_drift",
                            "summary": "The viewpoint changes without an established transition.",
                            "suggestion": "Anchor perception to the selected viewpoint character.",
                        },
                        {
                            "severity": "medium",
                            "category": "timeline_conflict",
                            "summary": "The event order conflicts with the scene chronology.",
                            "suggestion": "Clarify the sequence before the closing action.",
                        },
                        {
                            "severity": "low",
                            "category": "phrase_repetition",
                            "summary": "Multiple sentences begin with the same construction.",
                            "suggestion": "Vary the sentence openings without changing meaning.",
                        },
                    ]
                }
                response = {
                    "choices": [{"message": {"content": json.dumps(content)}}],
                    "usage": {"prompt_tokens": 30, "completion_tokens": 20, "total_tokens": 50},
                }
                encoded = json.dumps(response).encode("utf-8")
                self.send_response(200)
                self.send_header("Content-Type", "application/json")
                self.send_header("Content-Length", str(len(encoded)))
                self.end_headers()
                self.wfile.write(encoded)

            def log_message(self, format: str, *args: Any) -> None:
                return None

        return Handler


class _ReviewerWorker:
    def __init__(self, client: Client, task_queue: str) -> None:
        self.client = client
        self.task_queue = task_queue
        self.executor: ThreadPoolExecutor | None = None
        self.worker: Worker | None = None

    async def __aenter__(self) -> "_ReviewerWorker":
        self.executor = ThreadPoolExecutor(max_workers=4)
        self.worker = Worker(
            self.client,
            task_queue=self.task_queue,
            workflows=[WriterReviewWorkflow],
            activities=[writer_review_activity],
            activity_executor=self.executor,
        )
        await self.worker.__aenter__()
        return self

    async def __aexit__(self, exc_type: Any, exc: Any, traceback: Any) -> None:
        if self.worker is not None:
            await self.worker.__aexit__(exc_type, exc, traceback)
        if self.executor is not None:
            self.executor.shutdown(wait=True)


def _run_go_live(test_pattern: str, app_url: str, temporal_address: str, namespace: str, task_queue: str) -> None:
    env = os.environ.copy()
    env.update(
        {
            "MIROFISH_WRITER_REVIEW_LIVE_APP_DATABASE_URL": app_url,
            "MIROFISH_WRITER_REVIEW_LIVE_TEMPORAL_ADDRESS": temporal_address,
            "MIROFISH_WRITER_REVIEW_LIVE_TEMPORAL_NAMESPACE": namespace,
            "MIROFISH_WRITER_REVIEW_LIVE_TASK_QUEUE": task_queue,
            "MIROFISH_WRITER_REVIEW_LIVE_TENANT_ID": TENANT_ID,
            "MIROFISH_WRITER_REVIEW_LIVE_PROJECT_ID": PROJECT_ID,
            "MIROFISH_WRITER_REVIEW_LIVE_DRAFT_ID": DRAFT_ID,
            "MIROFISH_WRITER_REVIEW_LIVE_ACTOR_ID": USER_ID,
            "MIROFISH_WRITER_REVIEW_LIVE_OTHER_TENANT_ID": OTHER_TENANT_ID,
            "MIROFISH_WRITER_REVIEW_LIVE_OTHER_PROJECT_ID": OTHER_PROJECT_ID,
            "MIROFISH_WRITER_REVIEW_LIVE_OTHER_ACTOR_ID": OTHER_USER_ID,
        }
    )
    result = subprocess.run(
        [
            "go", "test",
            "internal/workflows/writer.go",
            "internal/workflows/hello.go",
            "internal/workflows/writer_admission.go",
            "internal/workflows/writer_events.go",
            "internal/workflows/workflow_events.go",
            "internal/workflows/writer_draft_review.go",
            "internal/workflows/writer_draft_review_runtime.go",
            "internal/workflows/writer_draft_review_runtime_live_test.go",
            "-run", f"^({test_pattern})$", "-count=1",
        ],
        cwd=ROOT / "apps" / "api",
        env=env,
        text=True,
        capture_output=True,
        timeout=60,
        check=False,
    )
    if result.returncode != 0:
        raise AssertionError(f"Go Writer reviewer live test failed:\n{result.stdout}\n{result.stderr}")


def _prepare_database(admin_url: str, provider_base_url: str) -> None:
    with psycopg.connect(admin_url, autocommit=True) as connection:
        with connection.cursor() as cursor:
            _ensure_live_schema(cursor)
            _ensure_app_role(cursor)
            _delete_fixture(cursor)
            cursor.execute(
                "INSERT INTO users (user_id, email, display_name) VALUES (%s, 'writer-review-live@example.test', 'Writer Review Live')",
                (USER_ID,),
            )
            cursor.execute(
                "INSERT INTO tenants (tenant_id, slug, name, tenant_type) VALUES (%s, 'writer-review-live', 'Writer Review Live', 'personal')",
                (TENANT_ID,),
            )
            cursor.execute("INSERT INTO tenant_memberships (tenant_id, user_id, role) VALUES (%s, %s, 'owner')", (TENANT_ID, USER_ID))
            cursor.execute("INSERT INTO projects (tenant_id, project_id, title, created_by) VALUES (%s, %s, 'Writer Review Live', %s)", (TENANT_ID, PROJECT_ID, USER_ID))
            cursor.execute("INSERT INTO project_members (tenant_id, project_id, user_id, role) VALUES (%s, %s, %s, 'project_owner')", (TENANT_ID, PROJECT_ID, USER_ID))
            cursor.execute(
                """INSERT INTO workflow_runs (
                     tenant_id, run_id, workflow_type, project_id, status, progress, started_by
                   ) VALUES (%s, %s, 'writer_run', %s, 'completed', 100, %s)""",
                (TENANT_ID, WRITER_RUN_ID, PROJECT_ID, USER_ID),
            )
            cursor.execute(
                """INSERT INTO writer_runs (
                     tenant_id, run_id, workflow_run_id, project_id, mode, status,
                     module_key, instruction, created_by
                   ) VALUES (%s, %s, %s, %s, 'draft', 'completed',
                             'writer_composer', 'private writer instruction', %s)""",
                (TENANT_ID, WRITER_RUN_ID, WRITER_RUN_ID, PROJECT_ID, USER_ID),
            )
            cursor.execute(
                """INSERT INTO writer_drafts (
                     tenant_id, draft_id, run_id, project_id, content_text, word_count, status
                   ) VALUES (%s, %s, %s, %s, %s, 8, 'candidate')""",
                (TENANT_ID, DRAFT_ID, WRITER_RUN_ID, PROJECT_ID, "Private candidate opening remains outside public metadata."),
            )
            cursor.execute(
                """INSERT INTO llm_channels (
                     tenant_id, channel_id, name, provider, base_url, encrypted_api_key,
                     max_concurrency, enabled
                   ) VALUES (%s, %s, 'Writer Review Local', 'openai-compatible', %s, %s, 1, true)""",
                (TENANT_ID, CHANNEL_ID, provider_base_url, _encrypt_api_key("sk-writer-review-live")),
            )
            cursor.execute(
                """INSERT INTO llm_models (
                     tenant_id, channel_id, model_id, owned_by, supports_json, supports_tools,
                     input_cost, output_cost
                   ) VALUES (%s, %s, 'model-writer-review-live', 'local', true, false, 1, 2)""",
                (TENANT_ID, CHANNEL_ID),
            )
            cursor.execute(
                """INSERT INTO llm_module_bindings (
                     tenant_id, project_id, module_key, channel_id, model_id, settings_jsonb, updated_by
                   ) VALUES (%s, %s, 'writer_reviewer', %s, 'model-writer-review-live',
                             '{"max_tokens":256}'::jsonb, %s)""",
                (TENANT_ID, PROJECT_ID, CHANNEL_ID, USER_ID),
            )
            cursor.execute(
                """INSERT INTO llm_quota_policies (
                     tenant_id, scope_type, token_limit, cost_limit_micros,
                     concurrency_limit, period_seconds, updated_by
                   ) VALUES (%s, 'tenant', 1000000, 1000000, 2, 3600, %s)""",
                (TENANT_ID, USER_ID),
            )
            cursor.execute(
                """INSERT INTO llm_quota_policies (
                     tenant_id, scope_type, project_id, token_limit, cost_limit_micros,
                     concurrency_limit, period_seconds, updated_by
                   ) VALUES (%s, 'project', %s, 1000000, 1000000, 2, 3600, %s)""",
                (TENANT_ID, PROJECT_ID, USER_ID),
            )
            cursor.execute(
                """INSERT INTO llm_quota_policies (
                     tenant_id, scope_type, project_id, module_key, token_limit,
                     cost_limit_micros, concurrency_limit, period_seconds, updated_by
                   ) VALUES (%s, 'module', %s, 'writer_reviewer',
                             1000000, 1000000, 1, 3600, %s)""",
                (TENANT_ID, PROJECT_ID, USER_ID),
            )
            cursor.execute(
                "INSERT INTO users (user_id, email, display_name) VALUES (%s, 'writer-review-other@example.test', 'Writer Review Other')",
                (OTHER_USER_ID,),
            )
            cursor.execute(
                "INSERT INTO tenants (tenant_id, slug, name, tenant_type) VALUES (%s, 'writer-review-other', 'Writer Review Other', 'personal')",
                (OTHER_TENANT_ID,),
            )
            cursor.execute("INSERT INTO tenant_memberships (tenant_id, user_id, role) VALUES (%s, %s, 'owner')", (OTHER_TENANT_ID, OTHER_USER_ID))
            cursor.execute("INSERT INTO projects (tenant_id, project_id, title, created_by) VALUES (%s, %s, 'Other', %s)", (OTHER_TENANT_ID, OTHER_PROJECT_ID, OTHER_USER_ID))
            cursor.execute("INSERT INTO project_members (tenant_id, project_id, user_id, role) VALUES (%s, %s, %s, 'project_owner')", (OTHER_TENANT_ID, OTHER_PROJECT_ID, OTHER_USER_ID))


def _ensure_live_schema(cursor: Any) -> None:
    cursor.execute("SELECT to_regclass('public.mirofish_schema_migrations') IS NOT NULL")
    ledger_exists = bool(cursor.fetchone()[0])
    if ledger_exists:
        _validate_live_migration_ledger(cursor)
    else:
        _apply_fresh_disposable_baseline(cursor)
    _validate_live_schema_sentinels(cursor)


def _validate_live_migration_ledger(cursor: Any) -> None:
    cursor.execute(
        "SELECT version, checksum FROM mirofish_schema_migrations WHERE version = ANY(%s)",
        (list(REQUIRED_MIGRATIONS),),
    )
    recorded = dict(cursor.fetchall())
    for version, migration in REQUIRED_MIGRATIONS.items():
        checksum = hashlib.sha256(migration.read_bytes()).hexdigest()
        if recorded.get(version) != checksum:
            raise RuntimeError(f"Writer reviewer live database migration ledger is missing or mismatched for {version}")


def _apply_fresh_disposable_baseline(cursor: Any) -> None:
    cursor.execute(
        """SELECT COALESCE(array_agg(class.relname ORDER BY class.relname), ARRAY[]::name[])
           FROM pg_class class
           JOIN pg_namespace namespace ON namespace.oid = class.relnamespace
           WHERE namespace.nspname = 'public' AND class.relkind IN ('r', 'p')"""
    )
    public_tables = list(cursor.fetchone()[0])
    if public_tables:
        raise RuntimeError(
            "Writer reviewer live database has public tables but no migration ledger; refusing raw migration replay"
        )
    for migration in REQUIRED_MIGRATIONS.values():
        cursor.execute(migration.read_text(encoding="utf-8"))


def _validate_live_schema_sentinels(cursor: Any) -> None:
    cursor.execute(
        """SELECT
             to_regprocedure('app_set_tenant_context(uuid,uuid,boolean)') IS NOT NULL
             AND 14 = (
               SELECT count(*) FROM pg_class
               WHERE relname IN (
                 'users', 'tenants', 'tenant_memberships', 'projects', 'project_members',
                 'workflow_runs', 'workflow_events', 'writer_runs', 'writer_drafts',
                 'draft_reviews', 'draft_review_issues', 'llm_channels',
                 'llm_quota_policies', 'llm_quota_reservations'
               ) AND relkind = 'r'
             )
             AND 2 = (
               SELECT count(*) FROM pg_class
               WHERE relname IN ('llm_quota_policies', 'llm_quota_reservations')
                 AND relrowsecurity AND relforcerowsecurity
             )"""
    )
    if not bool(cursor.fetchone()[0]):
        raise RuntimeError("Writer reviewer live database schema sentinels are incomplete")


def _ensure_app_role(cursor: Any) -> None:
    cursor.execute("SELECT 1 FROM pg_roles WHERE rolname = %s", (APP_ROLE,))
    if cursor.fetchone() is None:
        cursor.execute(
            sql.SQL("CREATE ROLE {} LOGIN PASSWORD {} IN ROLE mirofish_app").format(
                sql.Identifier(APP_ROLE), sql.Literal(APP_PASSWORD)
            )
        )
    else:
        cursor.execute(sql.SQL("ALTER ROLE {} WITH LOGIN PASSWORD {}").format(sql.Identifier(APP_ROLE), sql.Literal(APP_PASSWORD)))
    cursor.execute(sql.SQL("GRANT mirofish_app TO {}").format(sql.Identifier(APP_ROLE)))


def _wait_for_completion(admin_url: str) -> dict[str, Any]:
    deadline = time.monotonic() + 30
    last: dict[str, Any] = {}
    while time.monotonic() < deadline:
        last = _read_state(admin_url)
        if last.get("workflow_status") == "completed":
            return last
        time.sleep(0.2)
    raise AssertionError(f"writer review did not complete: {last}")


def _read_state(admin_url: str) -> dict[str, Any]:
    with psycopg.connect(admin_url, row_factory=dict_row) as connection:
        with connection.cursor() as cursor:
            cursor.execute(
                """SELECT review.status AS review_status, workflow.status AS workflow_status,
                          workflow.run_id::text AS run_id, review.error_code AS review_error_code,
                          workflow.error_code AS workflow_error_code
                   FROM draft_reviews review
                   JOIN workflow_runs workflow ON workflow.tenant_id = review.tenant_id AND workflow.run_id = review.run_id
                   JOIN workflow_events queued ON queued.tenant_id = workflow.tenant_id AND queued.run_id = workflow.run_id
                    AND queued.event_type = 'workflow.queued'
                   WHERE review.tenant_id = %s AND review.project_id = %s
                     AND queued.payload_jsonb->>'request_id' = 'writer-review-live-request'""",
                (TENANT_ID, PROJECT_ID),
            )
            state = dict(cursor.fetchone() or {})
            run_id = state.get("run_id")
            cursor.execute("SELECT count(*)::int AS issue_count FROM draft_review_issues WHERE tenant_id = %s AND project_id = %s", (TENANT_ID, PROJECT_ID))
            state.update(dict(cursor.fetchone() or {}))
            cursor.execute("SELECT status AS draft_status FROM writer_drafts WHERE tenant_id = %s AND draft_id = %s", (TENANT_ID, DRAFT_ID))
            state.update(dict(cursor.fetchone() or {}))
            cursor.execute("SELECT count(*)::int AS manuscript_count FROM manuscript_blocks WHERE tenant_id = %s AND project_id = %s", (TENANT_ID, PROJECT_ID))
            state.update(dict(cursor.fetchone() or {}))
            cursor.execute("SELECT count(*)::int AS completed_activity_count FROM llm_activity WHERE tenant_id = %s AND run_id = %s AND module_key = 'writer_reviewer' AND status = 'completed'", (TENANT_ID, run_id))
            state.update(dict(cursor.fetchone() or {}))
            cursor.execute("SELECT COALESCE(sum(quantity), 0)::int AS usage_quantity FROM usage_events WHERE tenant_id = %s AND run_id = %s AND module_key = 'writer_reviewer' AND usage_type = 'llm_tokens'", (TENANT_ID, run_id))
            state.update(dict(cursor.fetchone() or {}))
            cursor.execute("SELECT count(*)::int AS finalized_reservation_count FROM llm_quota_reservations WHERE tenant_id = %s AND run_id = %s AND module_key = 'writer_reviewer' AND status = 'finalized'", (TENANT_ID, run_id))
            state.update(dict(cursor.fetchone() or {}))
            cursor.execute(
                """SELECT count(*) FILTER (WHERE event_type = 'workflow.queued')::int AS queued_event_count,
                          count(*) FILTER (WHERE event_type = 'writer.review.completed')::int AS completed_event_count
                   FROM workflow_events WHERE tenant_id = %s AND run_id = %s""",
                (TENANT_ID, run_id),
            )
            state.update(dict(cursor.fetchone() or {}))
            cursor.execute("SELECT payload_jsonb::text AS payload FROM workflow_events WHERE tenant_id = %s AND run_id = %s AND event_type = 'writer.review.completed'", (TENANT_ID, run_id))
            event = cursor.fetchone()
            if event:
                payload = json.loads(event["payload"])
                assert set(payload) == {"status", "review_id", "draft_id", "issue_count", "severity_counts", "category_counts", "module_key", "model_id"}
    return state


def _read_final_state(admin_url: str) -> dict[str, Any]:
    with psycopg.connect(admin_url, row_factory=dict_row) as connection:
        with connection.cursor() as cursor:
            cursor.execute("SELECT status FROM draft_review_issues WHERE tenant_id = %s AND project_id = %s ORDER BY status", (TENANT_ID, PROJECT_ID))
            statuses = sorted(row["status"] for row in cursor.fetchall())
            cursor.execute("SELECT count(*)::int AS issue_audit_count FROM audit_logs WHERE tenant_id = %s AND project_id = %s AND action = 'writer.review_issue_status_changed'", (TENANT_ID, PROJECT_ID))
            final = dict(cursor.fetchone() or {})
            final["issue_statuses"] = statuses
            cursor.execute(
                """SELECT review.status AS compensated_review_status,
                          (SELECT count(*) FROM draft_review_issues issue WHERE issue.review_id = review.review_id)::int AS compensated_issue_count
                   FROM draft_reviews review
                   JOIN workflow_events queued ON queued.tenant_id = review.tenant_id AND queued.run_id = review.run_id
                    AND queued.event_type = 'workflow.queued'
                   WHERE review.tenant_id = %s AND review.project_id = %s
                     AND queued.payload_jsonb->>'request_id' = 'writer-review-live-compensation'""",
                (TENANT_ID, PROJECT_ID),
            )
            final.update(dict(cursor.fetchone() or {}))
            cursor.execute("SELECT status AS draft_status FROM writer_drafts WHERE tenant_id = %s AND draft_id = %s", (TENANT_ID, DRAFT_ID))
            final.update(dict(cursor.fetchone() or {}))
            cursor.execute("SELECT count(*)::int AS manuscript_count FROM manuscript_blocks WHERE tenant_id = %s AND project_id = %s", (TENANT_ID, PROJECT_ID))
            final.update(dict(cursor.fetchone() or {}))
    return final


def _delete_fixture(cursor: Any) -> None:
    cursor.execute("DELETE FROM tenants WHERE tenant_id IN (%s, %s)", (TENANT_ID, OTHER_TENANT_ID))
    cursor.execute("DELETE FROM users WHERE user_id IN (%s, %s)", (USER_ID, OTHER_USER_ID))


def _cleanup_database(admin_url: str) -> None:
    with psycopg.connect(admin_url, autocommit=True) as connection:
        with connection.cursor() as cursor:
            _delete_fixture(cursor)


def _app_database_url(admin_url: str) -> str:
    parts = conninfo_to_dict(admin_url)
    parts["user"] = APP_ROLE
    parts["password"] = APP_PASSWORD
    return make_conninfo(**parts)


def _encrypt_api_key(api_key: str) -> str:
    key = bytes.fromhex(KEY_MATERIAL)
    iv = bytes.fromhex("00112233445566778899aabb")
    sealed = AESGCM(key).encrypt(iv, api_key.encode("utf-8"), None)
    return "aes-256-gcm:v1:%s:%s:%s" % (
        base64.b64encode(iv).decode("ascii"),
        base64.b64encode(sealed[-16:]).decode("ascii"),
        base64.b64encode(sealed[:-16]).decode("ascii"),
    )


def _live_database_url() -> str:
    value = os.environ.get("MIROFISH_WRITER_REVIEW_LIVE_DATABASE_URL", "").strip()
    if not value:
        pytest.skip("set MIROFISH_WRITER_REVIEW_LIVE_DATABASE_URL to run Writer reviewer live E2E")
    return value


def _live_temporal_address() -> str:
    value = os.environ.get("MIROFISH_WRITER_REVIEW_LIVE_TEMPORAL_ADDRESS", "").strip()
    if not value:
        pytest.skip("set MIROFISH_WRITER_REVIEW_LIVE_TEMPORAL_ADDRESS to run Writer reviewer live E2E")
    return value
