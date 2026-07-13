from __future__ import annotations

import os
import json
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Any

import psycopg
import pytest
from psycopg import sql
from psycopg.conninfo import conninfo_to_dict, make_conninfo

from mirofish_agents.llm_quota import (
    PostgresQuotaStore,
    ProviderCallRequest,
    ProviderQuotaGate,
    ProviderUsage,
    QuotaAwareJSONChatClient,
)
from mirofish_agents.common.context import AgentContext
from mirofish_agents.seed.sequential_reader import LLMFacilityError, ModuleBindingResolution


TENANT_A = "a1100000-0000-4000-8000-000000000001"
TENANT_B = "a1100000-0000-4000-8000-000000000002"
PROJECT_A = "a1200000-0000-4000-8000-000000000001"
PROJECT_B = "a1200000-0000-4000-8000-000000000002"
USER_ID = "a1300000-0000-4000-8000-000000000001"
CHANNEL_ID = "a1400000-0000-4000-8000-000000000001"
RUN_A = "a1500000-0000-4000-8000-000000000001"
RUN_B = "a1500000-0000-4000-8000-000000000002"
APP_ROLE = "mirofish_python_quota_live"
APP_PASSWORD = "mirofish_python_quota_live_password"


def _admin_url() -> str:
    value = os.environ.get("MIROFISH_PYTHON_QUOTA_LIVE_ADMIN_DATABASE_URL", "").strip()
    if not value:
        pytest.skip("set MIROFISH_PYTHON_QUOTA_LIVE_ADMIN_DATABASE_URL for Python quota live PostgreSQL")
    return value


def _request(*, run_id: str, call_id: str, trace_id: str) -> ProviderCallRequest:
    return ProviderCallRequest(
        tenant_id=TENANT_A,
        project_id=PROJECT_A,
        run_id=run_id,
        actor_user_id=USER_ID,
        trace_id=trace_id,
        workflow_type="asset_ingestion",
        module_key="asset_ingestion",
        channel_id=CHANNEL_ID,
        model_id="quota-live-model",
        provider_call_id=call_id,
        stage="candidate_generation",
        call_index=0,
        input_token_upper_bound=100,
        output_token_upper_bound=100,
        module_max_concurrency=1,
    )


def test_postgres_quota_reservation_concurrency_finalize_release_replay_and_rls() -> None:
    admin_url = _admin_url()
    _prepare(admin_url)
    app_url = _app_url(admin_url)
    store = PostgresQuotaStore.from_database_url(app_url, ttl_seconds=120)
    first_request = _request(run_id=RUN_A, call_id="llm:python-quota-live-first", trace_id="trace-python-quota-live-first")
    second_request = _request(run_id=RUN_B, call_id="llm:python-quota-live-second", trace_id="trace-python-quota-live-second")
    try:
        first = store.admit(first_request)
        with pytest.raises(LLMFacilityError) as exc_info:
            store.admit(second_request)
        assert exc_info.value.code == "LLM_QUOTA_CONCURRENCY_EXCEEDED"

        response = {
            "candidates": [{"title": "Private candidate output"}],
            "__llm_usage": {"prompt_tokens": 10, "completion_tokens": 5},
        }
        store.finalize(first_request, first, ProviderUsage(prompt_tokens=10, completion_tokens=5), response)
        replay = store.admit(first_request)
        assert replay.replay_payload == response

        second = store.admit(second_request)
        store.fail(second_request, second, "LLM_PROVIDER_UNAVAILABLE")

        with psycopg.connect(admin_url) as connection:
            finalized = connection.execute(
                """SELECT status, actual_prompt_tokens, actual_completion_tokens, actual_cost_micros
                   FROM llm_quota_reservations WHERE tenant_id = %s AND provider_call_id = %s""",
                (TENANT_A, first_request.provider_call_id),
            ).fetchone()
            released = connection.execute(
                "SELECT status FROM llm_quota_reservations WHERE tenant_id = %s AND provider_call_id = %s",
                (TENANT_A, second_request.provider_call_id),
            ).fetchone()
            usage_rows = connection.execute(
                """SELECT usage_type, quantity::bigint, metadata_jsonb->>'provider_call_id'
                   FROM usage_events WHERE tenant_id = %s AND run_id = %s ORDER BY usage_type""",
                (TENANT_A, RUN_A),
            ).fetchall()
            activities = connection.execute(
                """SELECT status, error_jsonb->>'provider_call_id'
                   FROM llm_activity WHERE tenant_id = %s AND run_id IN (%s, %s) ORDER BY status""",
                (TENANT_A, RUN_A, RUN_B),
            ).fetchall()
            active_locks = connection.execute(
                "SELECT count(*) FROM resource_locks WHERE tenant_id = %s AND expires_at > now()",
                (TENANT_A,),
            ).fetchone()[0]
        assert finalized == ("finalized", 10, 5, 20)
        assert released == ("released",)
        assert usage_rows == [
            ("llm_cost_micros", 20, first_request.provider_call_id),
            ("llm_tokens", 15, first_request.provider_call_id),
        ]
        assert activities == [
            ("completed", first_request.provider_call_id),
            ("failed", second_request.provider_call_id),
        ]
        assert active_locks == 0
        with psycopg.connect(admin_url) as connection:
            connection.execute(
                "UPDATE llm_quota_policies SET enabled = false WHERE tenant_id = %s",
                (TENANT_A,),
            )
        with pytest.raises(LLMFacilityError) as exc_info:
            store.admit(
                _request(
                    run_id=RUN_B,
                    call_id="llm:python-quota-live-no-policy",
                    trace_id="trace-python-quota-live-no-policy",
                )
            )
        assert exc_info.value.code == "LLM_QUOTA_POLICY_UNAVAILABLE"
        _assert_cross_tenant_hidden(app_url)
    finally:
        _cleanup(admin_url)


def test_quota_gate_live_local_provider_replay_has_one_provider_side_effect() -> None:
    admin_url = _admin_url()
    _prepare(admin_url)
    state = {"calls": 0, "provider_call_ids": []}
    server, thread = _provider_server(state)
    try:
        app_url = _app_url(admin_url)
        store = PostgresQuotaStore.from_database_url(app_url, ttl_seconds=120)
        gate = ProviderQuotaGate(store)
        context = AgentContext(
            tenant_id=TENANT_A,
            project_id=PROJECT_A,
            run_id=RUN_A,
            workflow_type="asset_ingestion",
            actor_user_id=USER_ID,
            module_key="asset_ingestion",
            trace_id="trace-python-quota-live-provider",
            permissions={"asset_ingestion": ["run"]},
        )
        resolution = ModuleBindingResolution(
            tenant_id=TENANT_A,
            project_id=PROJECT_A,
            module_key="asset_ingestion",
            channel_id=CHANNEL_ID,
            model_id="quota-live-model",
            provider="openai-compatible",
            base_url=f"http://127.0.0.1:{server.server_address[1]}/v1",
            credential_ref=CHANNEL_ID,
            supports_json=True,
            settings={"max_tokens": 100, "max_concurrency": 1},
        )
        messages = [{"role": "user", "content": "Generate one public asset candidate."}]
        client = QuotaAwareJSONChatClient()

        def execute() -> list[dict[str, Any]]:
            return gate.execute_json(
                context=context,
                resolution=resolution,
                stage="candidate_generation",
                call_index=0,
                input_texts=[message["content"] for message in messages],
                provider=lambda provider_call_id: client.complete_json(
                    context=context,
                    resolution=resolution,
                    api_key="quota-live-provider-key",
                    messages=messages,
                    provider_call_id=provider_call_id,
                ),
                validate=lambda response: response["candidates"],
            )

        assert execute() == [{"title": "Live candidate"}]
        assert execute() == [{"title": "Live candidate"}]
        assert state["calls"] == 1
        assert len(state["provider_call_ids"]) == 1
        assert str(state["provider_call_ids"][0]).startswith("llm:")
        with psycopg.connect(admin_url) as connection:
            assert connection.execute(
                "SELECT count(*) FROM llm_quota_reservations WHERE tenant_id = %s AND status = 'finalized'",
                (TENANT_A,),
            ).fetchone()[0] == 1
            assert connection.execute(
                "SELECT count(*) FROM usage_events WHERE tenant_id = %s AND run_id = %s",
                (TENANT_A, RUN_A),
            ).fetchone()[0] == 2
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=2)
        _cleanup(admin_url)


def _provider_server(state: dict[str, Any]) -> tuple[ThreadingHTTPServer, threading.Thread]:
    class Handler(BaseHTTPRequestHandler):
        def do_POST(self) -> None:  # noqa: N802 - BaseHTTPRequestHandler contract
            if self.path != "/v1/chat/completions" or self.headers.get("Authorization") != "Bearer quota-live-provider-key":
                self.send_response(401)
                self.end_headers()
                return
            body = json.loads(self.rfile.read(int(self.headers.get("Content-Length", "0"))).decode("utf-8"))
            if body.get("model") != "quota-live-model":
                self.send_response(400)
                self.end_headers()
                return
            state["calls"] += 1
            state["provider_call_ids"].append(self.headers.get("Idempotency-Key"))
            response = json.dumps(
                {
                    "choices": [{"message": {"content": json.dumps({"candidates": [{"title": "Live candidate"}]})}}],
                    "usage": {"prompt_tokens": 10, "completion_tokens": 5, "total_tokens": 15},
                }
            ).encode("utf-8")
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(response)))
            self.end_headers()
            self.wfile.write(response)

        def log_message(self, format: str, *args: Any) -> None:
            return None

    server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    return server, thread


def _prepare(admin_url: str) -> None:
    with psycopg.connect(admin_url, autocommit=True) as connection:
        with connection.cursor() as cursor:
            _ensure_role(cursor)
            cursor.execute("DELETE FROM tenants WHERE tenant_id IN (%s, %s)", (TENANT_A, TENANT_B))
            cursor.execute("DELETE FROM users WHERE user_id = %s", (USER_ID,))
            cursor.execute(
                "INSERT INTO users (user_id, email, display_name) VALUES (%s, 'python-quota-live@example.test', 'Python Quota Live')",
                (USER_ID,),
            )
            cursor.executemany(
                "INSERT INTO tenants (tenant_id, slug, name, tenant_type) VALUES (%s, %s, %s, 'organization')",
                [
                    (TENANT_A, "python-quota-live-a", "Python Quota Live A"),
                    (TENANT_B, "python-quota-live-b", "Python Quota Live B"),
                ],
            )
            cursor.executemany(
                "INSERT INTO projects (tenant_id, project_id, title, created_by) VALUES (%s, %s, %s, %s)",
                [
                    (TENANT_A, PROJECT_A, "Python Quota Project A", USER_ID),
                    (TENANT_B, PROJECT_B, "Python Quota Project B", USER_ID),
                ],
            )
            cursor.executemany(
                """INSERT INTO workflow_runs (tenant_id, run_id, workflow_type, project_id, status, started_by)
                   VALUES (%s, %s, 'asset_ingestion', %s, 'queued', %s)""",
                [(TENANT_A, RUN_A, PROJECT_A, USER_ID), (TENANT_A, RUN_B, PROJECT_A, USER_ID)],
            )
            cursor.execute(
                """INSERT INTO llm_channels (
                     tenant_id, channel_id, name, provider, base_url, encrypted_api_key,
                     max_concurrency, enabled
                   ) VALUES (%s, %s, 'Python Quota Live', 'openai-compatible',
                             'http://127.0.0.1:1/v1', 'not-used', 1, true)""",
                (TENANT_A, CHANNEL_ID),
            )
            cursor.execute(
                """INSERT INTO llm_models (
                     tenant_id, channel_id, model_id, context_window, supports_json,
                     input_cost, output_cost
                   ) VALUES (%s, %s, 'quota-live-model', 4096, true, 1, 2)""",
                (TENANT_A, CHANNEL_ID),
            )
            cursor.executemany(
                """INSERT INTO llm_quota_policies (
                     tenant_id, scope_type, project_id, module_key, token_limit,
                     cost_limit_micros, concurrency_limit, period_seconds, enabled, updated_by
                   ) VALUES (%s, %s, %s, %s, %s, %s, %s, 3600, true, %s)""",
                [
                    (TENANT_A, "tenant", None, None, 50000, 50000, 4, USER_ID),
                    (TENANT_A, "project", PROJECT_A, None, 25000, 25000, 2, USER_ID),
                    (TENANT_A, "module", PROJECT_A, "asset_ingestion", 10000, 10000, 1, USER_ID),
                ],
            )


def _ensure_role(cursor: Any) -> None:
    cursor.execute("SELECT 1 FROM pg_roles WHERE rolname = %s", (APP_ROLE,))
    if cursor.fetchone() is None:
        cursor.execute(
            sql.SQL("CREATE ROLE {} LOGIN PASSWORD {} IN ROLE mirofish_app").format(
                sql.Identifier(APP_ROLE), sql.Literal(APP_PASSWORD)
            )
        )
    else:
        cursor.execute(
            sql.SQL("ALTER ROLE {} WITH LOGIN PASSWORD {}").format(
                sql.Identifier(APP_ROLE), sql.Literal(APP_PASSWORD)
            )
        )
    cursor.execute(sql.SQL("GRANT mirofish_app TO {}").format(sql.Identifier(APP_ROLE)))


def _app_url(admin_url: str) -> str:
    parts = conninfo_to_dict(admin_url)
    parts["user"] = APP_ROLE
    parts["password"] = APP_PASSWORD
    return make_conninfo(**parts)


def _assert_cross_tenant_hidden(app_url: str) -> None:
    with psycopg.connect(app_url) as connection:
        connection.execute("SELECT app_set_tenant_context(%s::uuid, %s::uuid, false)", (TENANT_B, USER_ID))
        assert connection.execute(
            "SELECT count(*) FROM llm_quota_reservations WHERE tenant_id = %s", (TENANT_A,)
        ).fetchone()[0] == 0
        assert connection.execute(
            "SELECT count(*) FROM resource_locks WHERE tenant_id = %s", (TENANT_A,)
        ).fetchone()[0] == 0


def _cleanup(admin_url: str) -> None:
    with psycopg.connect(admin_url, autocommit=True) as connection:
        connection.execute("DELETE FROM tenants WHERE tenant_id IN (%s, %s)", (TENANT_A, TENANT_B))
        connection.execute("DELETE FROM users WHERE user_id = %s", (USER_ID,))
