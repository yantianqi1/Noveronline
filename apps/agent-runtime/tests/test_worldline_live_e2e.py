from __future__ import annotations

import base64
import json
import os
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any

import psycopg
import pytest
from cryptography.hazmat.primitives.ciphers.aead import AESGCM
from psycopg.conninfo import conninfo_to_dict, make_conninfo
from psycopg.rows import dict_row
from psycopg import sql

from mirofish_agents.temporal.worldline import (
    WORLDLINE_STEP_MODULE_KEY,
    run_worldline_step_workflow_locally,
)
from mirofish_agents.temporal.worldline_auto_evolution import (
    WORLDLINE_AUTO_EVOLUTION_WORLD_SCOPE,
    run_worldline_auto_evolution_workflow_locally,
)
from live_schema_guard import ensure_live_schema


ROOT = Path(__file__).resolve().parents[3]
MIGRATION_SQL = ROOT / "infra" / "postgres" / "migrations" / "0001_core_saas.sql"
KEY_MATERIAL = "000102030405060708090a0b0c0d0e0f101112131415161718191a1b1c1d1e1f"
APP_ROLE = "mirofish_live_app"
APP_PASSWORD = "mirofish_live_password"
TENANT_ID = "11111111-1111-1111-1111-111111111111"
USER_ID = "22222222-2222-2222-2222-222222222222"
PROJECT_ID = "33333333-3333-3333-3333-333333333333"
SESSION_ID = "44444444-4444-4444-4444-444444444444"
SESSION_RUN_ID = "55555555-5555-5555-5555-555555555555"
STEP_RUN_ID = "550e8400-e29b-41d4-a716-446655440000"
AUTO_RUN_ID = "77777777-7777-7777-7777-777777777777"
CHANNEL_ID = "66666666-6666-6666-6666-666666666666"


def test_worldline_step_live_postgres_provider_chain_persists_same_run_telemetry_and_candidates(
    monkeypatch: pytest.MonkeyPatch,
    request: pytest.FixtureRequest,
) -> None:
    admin_url = _live_database_url()
    request.addfinalizer(lambda: _cleanup_live_database(admin_url))
    with _LiveProvider() as provider:
        _prepare_live_database(admin_url, provider.base_url)
        app_url = _app_database_url(admin_url)
        monkeypatch.setenv("DATABASE_URL", app_url)
        monkeypatch.setenv("LLM_CREDENTIAL_ENCRYPTION_KEY", KEY_MATERIAL)

        result = run_worldline_step_workflow_locally(
            {
                "context": {
                    "tenant_id": TENANT_ID,
                    "project_id": PROJECT_ID,
                    "run_id": STEP_RUN_ID,
                    "workflow_type": "worldline_step",
                    "actor_user_id": USER_ID,
                    "module_key": WORLDLINE_STEP_MODULE_KEY,
                    "trace_id": "trace-live-worldline-step",
                    "permissions": {WORLDLINE_STEP_MODULE_KEY: ["run"]},
                },
                "session_id": SESSION_ID,
                "mode": "director",
                "options": {
                    "step": 7,
                    "goal": "advance current-world pressure without adopting canon",
                    "prompt": "private author prompt must not persist",
                    "credential_ref": "secret-ref",
                },
            }
        )

    assert result["status"] == "completed"
    assert result["run_id"] == STEP_RUN_ID
    assert result["module_key"] == WORLDLINE_STEP_MODULE_KEY
    assert result["candidate_event_count"] == 1
    assert len(provider.requests) == 1
    assert _header(provider.requests[0]["headers"], "Authorization") == "Bearer sk-live-worldline"
    assert _header(provider.requests[0]["headers"], "X-MiroFish-Run-Id") == STEP_RUN_ID

    persisted = _read_worldline_live_rows(admin_url)
    assert len(persisted["llm_activity"]) == 1
    activity_metadata = persisted["llm_activity"][0].pop("error_jsonb")
    assert persisted["llm_activity"] == [
        {
            "run_id": STEP_RUN_ID,
            "module_key": WORLDLINE_STEP_MODULE_KEY,
            "status": "completed",
            "prompt_tokens": 13,
            "completion_tokens": 21,
            "model_id": "model-worldline-live",
        }
    ]
    assert activity_metadata["pricing_status"] == "available"
    assert activity_metadata["provider_call_id"].startswith("llm:")
    assert persisted["usage_events"] == [
        {
            "run_id": STEP_RUN_ID,
            "module_key": WORLDLINE_STEP_MODULE_KEY,
            "usage_type": "llm_tokens",
            "quantity": 34.0,
            "unit": "tokens",
        },
        {
            "run_id": STEP_RUN_ID,
            "module_key": WORLDLINE_STEP_MODULE_KEY,
            "usage_type": "llm_cost_micros",
            "quantity": 55.0,
            "unit": "micros",
        },
    ]
    assert persisted["worldline_events"] == [
        {
            "source_run_id": None,
            "step": 6,
            "title": "Prior step",
            "summary": "Existing current-world state.",
            "kind": "director",
            "status": "candidate",
            "lifecycle": "simulation",
        },
        {
            "source_run_id": STEP_RUN_ID,
            "step": 7,
            "title": "Live gate accord is delayed",
            "summary": "The current-world council postpones the gate handoff.",
            "kind": "political_turn",
            "status": "candidate",
            "lifecycle": "simulation",
        }
    ]
    assert persisted["workflow_runs"] == [
        {
            "run_id": STEP_RUN_ID,
            "workflow_type": "worldline_step",
            "status": "completed",
            "progress": 100,
            "error_code": None,
            "error_message": None,
        }
    ]
    assert persisted["workflow_events"] == [
        {
            "run_id": STEP_RUN_ID,
            "event_type": "workflow.queued",
            "payload_jsonb": {"session_id": SESSION_ID, "request_id": "req-live-component"},
        },
        {
            "run_id": STEP_RUN_ID,
            "event_type": "worldline.stage.completed",
            "payload_jsonb": {
                "stage": "worldline_step",
                "activity": "worldline_step_activity",
                "status": "completed",
                "module_key": WORLDLINE_STEP_MODULE_KEY,
                "session_id": SESSION_ID,
                "mode": "director",
                "step": 7,
                "candidate_event_count": 1,
                "model_id": "model-worldline-live",
            },
        }
    ]
    assert persisted["worldline_sessions"] == [{"status": "paused"}]
    encoded = json.dumps({"result": result, "persisted": persisted}, ensure_ascii=False, default=str)
    for forbidden in (
        "sk-live-worldline",
        "sk-provider-leak",
        "secret-ref",
        "credential_ref",
        "event_body",
        "private author prompt",
        "full event body must not persist",
    ):
        assert forbidden not in encoded


def test_worldline_auto_evolution_live_persists_three_candidate_steps_and_replays_without_provider(
    monkeypatch: pytest.MonkeyPatch,
    request: pytest.FixtureRequest,
) -> None:
    admin_url = _live_database_url()
    request.addfinalizer(lambda: _cleanup_live_database(admin_url))
    with _LiveProvider() as provider:
        _prepare_live_database(admin_url, provider.base_url)
        _prepare_auto_evolution_admission(admin_url, max_steps=3)
        app_url = _app_database_url(admin_url)
        monkeypatch.setenv("DATABASE_URL", app_url)
        monkeypatch.setenv("LLM_CREDENTIAL_ENCRYPTION_KEY", KEY_MATERIAL)
        payload = {
            "context": {
                "tenant_id": TENANT_ID,
                "project_id": PROJECT_ID,
                "run_id": AUTO_RUN_ID,
                "workflow_type": "worldline_auto_evolution",
                "actor_user_id": USER_ID,
                "module_key": WORLDLINE_STEP_MODULE_KEY,
                "trace_id": "trace-live-worldline-auto",
                "permissions": {WORLDLINE_STEP_MODULE_KEY: ["run"]},
            },
            "session_id": SESSION_ID,
            "max_steps": 3,
            "world_scope": WORLDLINE_AUTO_EVOLUTION_WORLD_SCOPE,
            "request_id": "req-live-auto",
            "options": {
                "goal": "advance the current world three candidate steps",
                "prompt": "private author prompt must not persist",
                "credential_ref": "secret-ref",
            },
        }

        first = run_worldline_auto_evolution_workflow_locally(payload)
        replay = run_worldline_auto_evolution_workflow_locally(payload)

    assert first["status"] == replay["status"] == "completed", json.dumps(
        {"first": first, "replay": replay}, ensure_ascii=False, default=str
    )
    assert first["completed_steps"] == replay["completed_steps"] == 3
    assert first["candidate_event_count"] == replay["candidate_event_count"] == 3
    assert len(provider.requests) == 3
    assert {_header(call["headers"], "X-MiroFish-Run-Id") for call in provider.requests} == {AUTO_RUN_ID}

    persisted = _read_auto_evolution_live_rows(admin_url)
    assert len(persisted["llm_activity"]) == 3
    assert len(persisted["usage_events"]) == 6
    assert [row["source_step_index"] for row in persisted["worldline_events"]] == [1, 2, 3]
    assert [row["step"] for row in persisted["worldline_events"]] == [7, 8, 9]
    assert {row["source_run_id"] for row in persisted["worldline_events"]} == {AUTO_RUN_ID}
    assert {row["status"] for row in persisted["worldline_events"]} == {"candidate"}
    assert {row["lifecycle"] for row in persisted["worldline_events"]} == {"simulation"}
    assert persisted["workflow_run"] == [
        {
            "status": "completed",
            "progress": 100,
            "error_code": None,
            "completed_steps": 3,
            "max_steps": 3,
        }
    ]
    assert [row["event_type"] for row in persisted["workflow_events"]] == [
        "workflow.queued",
        "worldline.auto_evolution.step.completed",
        "worldline.auto_evolution.step.completed",
        "worldline.auto_evolution.step.completed",
        "worldline.auto_evolution.completed",
    ]
    assert persisted["worldline_session"] == [{"status": "paused", "lifecycle": "active"}]
    encoded = json.dumps({"first": first, "replay": replay, "persisted": persisted}, ensure_ascii=False)
    for forbidden in (
        "sk-live-worldline",
        "sk-provider-leak",
        "secret-ref",
        "credential_ref",
        "event_body",
        "private author prompt",
        "full event body must not persist",
    ):
        assert forbidden not in encoded


class _LiveProvider:
    def __init__(self) -> None:
        self.requests: list[dict[str, Any]] = []
        self._server = ThreadingHTTPServer(("127.0.0.1", 0), self._handler())
        self.base_url = f"http://127.0.0.1:{self._server.server_port}/v1"
        self._thread = threading.Thread(target=self._server.serve_forever, daemon=True)

    def __enter__(self) -> "_LiveProvider":
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
                body = self.rfile.read(length).decode("utf-8")
                owner.requests.append(
                    {
                        "path": self.path,
                        "headers": dict(self.headers),
                        "body": json.loads(body),
                    }
                )
                content = {
                    "candidate_events": [
                        {
                            "title": "Live gate accord is delayed",
                            "summary": "The current-world council postpones the gate handoff.",
                            "kind": "political_turn",
                            "confidence": 0.77,
                            "involved_agent_ids": ["agent-live-1"],
                            "state_change_summary": "Tension increases without canon adoption.",
                            "event_body": "full event body must not persist",
                            "api_key": "sk-provider-leak",
                            "credential_ref": "secret-ref",
                        }
                    ]
                }
                response = {
                    "choices": [{"message": {"content": json.dumps(content)}}],
                    "usage": {
                        "prompt_tokens": 13,
                        "completion_tokens": 21,
                        "total_tokens": 34,
                        "cost_estimate": 0.0042,
                    },
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


def _live_database_url() -> str:
    database_url = os.environ.get("MIROFISH_WORLDLINE_LIVE_DATABASE_URL", "").strip()
    if not database_url:
        pytest.skip("set MIROFISH_WORLDLINE_LIVE_DATABASE_URL to run the live Worldline Postgres/provider E2E")
    return database_url


def _prepare_live_database(admin_url: str, provider_base_url: str) -> None:
    with psycopg.connect(admin_url, autocommit=True) as connection:
        with connection.cursor() as cursor:
            ensure_live_schema(
                cursor,
                MIGRATION_SQL,
                (
                    "tenants", "projects", "workflow_runs", "worldline_sessions",
                    "worldline_events", "llm_channels", "llm_module_bindings", "usage_events",
                ),
            )
            _ensure_app_login_role(cursor)
            cursor.execute("DELETE FROM tenants WHERE tenant_id = %s", (TENANT_ID,))
            cursor.execute(
                """INSERT INTO users (user_id, email, display_name)
                   VALUES (%s, 'worldline-live@example.test', 'Worldline Live')
                   ON CONFLICT (user_id) DO UPDATE
                     SET email = EXCLUDED.email,
                         display_name = EXCLUDED.display_name""",
                (USER_ID,),
            )
            cursor.execute(
                """INSERT INTO tenants (tenant_id, slug, name, tenant_type)
                   VALUES (%s, 'worldline-live', 'Worldline Live', 'personal')""",
                (TENANT_ID,),
            )
            cursor.execute(
                """INSERT INTO tenant_memberships (tenant_id, user_id, role)
                   VALUES (%s, %s, 'owner')""",
                (TENANT_ID, USER_ID),
            )
            cursor.execute(
                """INSERT INTO projects (tenant_id, project_id, title, created_by)
                   VALUES (%s, %s, 'Live Worldline Project', %s)""",
                (TENANT_ID, PROJECT_ID, USER_ID),
            )
            cursor.execute(
                """INSERT INTO project_members (tenant_id, project_id, user_id, role)
                   VALUES (%s, %s, %s, 'project_owner')""",
                (TENANT_ID, PROJECT_ID, USER_ID),
            )
            cursor.execute(
                """INSERT INTO workflow_runs (tenant_id, run_id, workflow_type, project_id, status, progress, started_by)
                   VALUES (%s, %s, 'worldline_session', %s, 'completed', 100, %s)""",
                (TENANT_ID, SESSION_RUN_ID, PROJECT_ID, USER_ID),
            )
            cursor.execute(
                """INSERT INTO worldline_sessions (
                     tenant_id, session_id, project_id, run_id, status, lifecycle, goal_summary, created_by
                   )
                   VALUES (%s, %s, %s, %s, 'running', 'active', 'Live current-world session', %s)""",
                (TENANT_ID, SESSION_ID, PROJECT_ID, SESSION_RUN_ID, USER_ID),
            )
            cursor.execute(
                """INSERT INTO workflow_runs (tenant_id, run_id, workflow_type, project_id, status, progress, started_by)
                   VALUES (%s, %s, 'worldline_step', %s, 'queued', 0, %s)""",
                (TENANT_ID, STEP_RUN_ID, PROJECT_ID, USER_ID),
            )
            cursor.execute(
                """INSERT INTO workflow_events (
                     tenant_id, run_id, workflow_type, project_id, event_type, sequence, payload_jsonb
                   ) VALUES (%s, %s, 'worldline_step', %s, 'workflow.queued', 1, %s::jsonb)""",
                (
                    TENANT_ID,
                    STEP_RUN_ID,
                    PROJECT_ID,
                    json.dumps({"session_id": SESSION_ID, "request_id": "req-live-component"}),
                ),
            )
            cursor.execute(
                """INSERT INTO worldline_events (
                     tenant_id, session_id, project_id, step, title, summary, status, lifecycle
                   ) VALUES (%s, %s, %s, 6, 'Prior step', 'Existing current-world state.', 'candidate', 'simulation')""",
                (TENANT_ID, SESSION_ID, PROJECT_ID),
            )
            cursor.execute(
                """INSERT INTO llm_channels (
                     tenant_id, channel_id, name, provider, base_url, encrypted_api_key, max_concurrency, enabled
                   )
                   VALUES (%s, %s, 'Live Provider', 'openai-compatible', %s, %s, 1, true)""",
                (TENANT_ID, CHANNEL_ID, provider_base_url, _encrypt_api_key("sk-live-worldline")),
            )
            cursor.execute(
                """INSERT INTO llm_models (
                     tenant_id, channel_id, model_id, owned_by, context_window,
                     supports_json, supports_tools, input_cost, output_cost
                   )
                   VALUES (%s, %s, 'model-worldline-live', 'live-provider', 8192,
                           true, false, 1, 2)""",
                (TENANT_ID, CHANNEL_ID),
            )
            cursor.execute(
                """INSERT INTO llm_module_bindings (
                     tenant_id, project_id, module_key, channel_id, model_id, settings_jsonb, updated_by
                   )
                   VALUES (%s, %s, %s, %s, 'model-worldline-live', '{"temperature":0.1}'::jsonb, %s)""",
                (TENANT_ID, PROJECT_ID, WORLDLINE_STEP_MODULE_KEY, CHANNEL_ID, USER_ID),
            )
            for scope_type, project_id, module_key in (
                ("tenant", None, None),
                ("project", PROJECT_ID, None),
                ("module", PROJECT_ID, WORLDLINE_STEP_MODULE_KEY),
            ):
                cursor.execute(
                    """INSERT INTO llm_quota_policies (
                         tenant_id, scope_type, project_id, module_key, token_limit,
                         cost_limit_micros, concurrency_limit, period_seconds, updated_by
                       ) VALUES (%s, %s, %s, %s, 1000000, 1000000, 2, 3600, %s)""",
                    (TENANT_ID, scope_type, project_id, module_key, USER_ID),
                )


def _prepare_auto_evolution_admission(admin_url: str, *, max_steps: int) -> None:
    with psycopg.connect(admin_url, autocommit=True) as connection:
        with connection.cursor() as cursor:
            cursor.execute(
                """INSERT INTO workflow_runs (
                     tenant_id, run_id, workflow_type, project_id, status, progress, started_by
                   ) VALUES (%s, %s, 'worldline_auto_evolution', %s, 'queued', 0, %s)""",
                (TENANT_ID, AUTO_RUN_ID, PROJECT_ID, USER_ID),
            )
            cursor.execute(
                """INSERT INTO workflow_events (
                     tenant_id, run_id, workflow_type, project_id, event_type, sequence, payload_jsonb
                   ) VALUES (%s, %s, 'worldline_auto_evolution', %s, 'workflow.queued', 1, %s::jsonb)""",
                (
                    TENANT_ID,
                    AUTO_RUN_ID,
                    PROJECT_ID,
                    json.dumps(
                        {
                            "session_id": SESSION_ID,
                            "request_id": "req-live-auto",
                            "max_steps": max_steps,
                            "world_scope": WORLDLINE_AUTO_EVOLUTION_WORLD_SCOPE,
                        }
                    ),
                ),
            )


def _ensure_app_login_role(cursor: Any) -> None:
    cursor.execute("SELECT 1 FROM pg_roles WHERE rolname = %s", (APP_ROLE,))
    if cursor.fetchone() is None:
        cursor.execute(
            sql.SQL("CREATE ROLE {} LOGIN PASSWORD {} IN ROLE mirofish_app").format(
                sql.Identifier(APP_ROLE),
                sql.Literal(APP_PASSWORD),
            ),
        )
    else:
        cursor.execute(
            sql.SQL("ALTER ROLE {} WITH LOGIN PASSWORD {}").format(sql.Identifier(APP_ROLE), sql.Literal(APP_PASSWORD)),
        )
    cursor.execute(sql.SQL("GRANT mirofish_app TO {}").format(sql.Identifier(APP_ROLE)))


def _app_database_url(admin_url: str) -> str:
    parts = conninfo_to_dict(admin_url)
    parts["user"] = APP_ROLE
    parts["password"] = APP_PASSWORD
    return make_conninfo(**parts)


def _encrypt_api_key(api_key: str) -> str:
    key = bytes.fromhex(KEY_MATERIAL)
    iv = bytes.fromhex("00112233445566778899aabb")
    sealed = AESGCM(key).encrypt(iv, api_key.encode("utf-8"), None)
    ciphertext, tag = sealed[:-16], sealed[-16:]
    return "aes-256-gcm:v1:%s:%s:%s" % (
        base64.b64encode(iv).decode("ascii"),
        base64.b64encode(tag).decode("ascii"),
        base64.b64encode(ciphertext).decode("ascii"),
    )


def _read_worldline_live_rows(admin_url: str) -> dict[str, list[dict[str, Any]]]:
    with psycopg.connect(admin_url, row_factory=dict_row) as connection:
        with connection.cursor() as cursor:
            cursor.execute(
                """SELECT
                     run_id::text, module_key, status, prompt_tokens, completion_tokens, model_id, error_jsonb
                   FROM llm_activity
                   WHERE tenant_id = %s AND project_id = %s AND run_id = %s
                   ORDER BY created_at""",
                (TENANT_ID, PROJECT_ID, STEP_RUN_ID),
            )
            llm_activity = [_normalize_row(row) for row in cursor.fetchall()]
            cursor.execute(
                """SELECT run_id::text, module_key, usage_type, quantity::float8, unit
                   FROM usage_events
                   WHERE tenant_id = %s AND project_id = %s AND run_id = %s
                   ORDER BY created_at""",
                (TENANT_ID, PROJECT_ID, STEP_RUN_ID),
            )
            usage_events = [_normalize_row(row) for row in cursor.fetchall()]
            cursor.execute(
                """SELECT
                     source_run_id::text, step, title, summary, kind, status, lifecycle
                   FROM worldline_events
                   WHERE tenant_id = %s AND project_id = %s AND session_id = %s
                   ORDER BY created_at""",
                (TENANT_ID, PROJECT_ID, SESSION_ID),
            )
            worldline_events = [_normalize_row(row) for row in cursor.fetchall()]
            cursor.execute(
                """SELECT run_id::text, workflow_type, status, progress, error_code, error_message
                   FROM workflow_runs
                   WHERE tenant_id = %s AND project_id = %s AND run_id = %s""",
                (TENANT_ID, PROJECT_ID, STEP_RUN_ID),
            )
            workflow_runs = [_normalize_row(row) for row in cursor.fetchall()]
            cursor.execute(
                """SELECT run_id::text, event_type, payload_jsonb
                   FROM workflow_events
                   WHERE tenant_id = %s AND project_id = %s AND run_id = %s
                   ORDER BY sequence""",
                (TENANT_ID, PROJECT_ID, STEP_RUN_ID),
            )
            workflow_events = [_normalize_row(row) for row in cursor.fetchall()]
            cursor.execute(
                """SELECT status
                   FROM worldline_sessions
                   WHERE tenant_id = %s AND project_id = %s AND session_id = %s""",
                (TENANT_ID, PROJECT_ID, SESSION_ID),
            )
            worldline_sessions = [_normalize_row(row) for row in cursor.fetchall()]
    return {
        "llm_activity": llm_activity,
        "usage_events": usage_events,
        "worldline_events": worldline_events,
        "workflow_runs": workflow_runs,
        "workflow_events": workflow_events,
        "worldline_sessions": worldline_sessions,
    }


def _read_auto_evolution_live_rows(admin_url: str) -> dict[str, list[dict[str, Any]]]:
    with psycopg.connect(admin_url, row_factory=dict_row) as connection:
        with connection.cursor() as cursor:
            cursor.execute(
                """SELECT status, prompt_tokens, completion_tokens, model_id
                   FROM llm_activity
                   WHERE tenant_id = %s AND project_id = %s AND run_id = %s
                   ORDER BY created_at""",
                (TENANT_ID, PROJECT_ID, AUTO_RUN_ID),
            )
            llm_activity = [_normalize_row(row) for row in cursor.fetchall()]
            cursor.execute(
                """SELECT usage_type, quantity::float8, unit
                   FROM usage_events
                   WHERE tenant_id = %s AND project_id = %s AND run_id = %s
                   ORDER BY created_at""",
                (TENANT_ID, PROJECT_ID, AUTO_RUN_ID),
            )
            usage_events = [_normalize_row(row) for row in cursor.fetchall()]
            cursor.execute(
                """SELECT source_run_id::text, step,
                          (state_changes_jsonb->>'source_step_index')::int AS source_step_index,
                          status, lifecycle
                   FROM worldline_events
                   WHERE tenant_id = %s AND project_id = %s AND session_id = %s
                     AND source_run_id = %s
                   ORDER BY step""",
                (TENANT_ID, PROJECT_ID, SESSION_ID, AUTO_RUN_ID),
            )
            worldline_events = [_normalize_row(row) for row in cursor.fetchall()]
            cursor.execute(
                """SELECT status, progress, error_code,
                          (result_jsonb->>'completed_steps')::int AS completed_steps,
                          (result_jsonb->>'max_steps')::int AS max_steps
                   FROM workflow_runs
                   WHERE tenant_id = %s AND project_id = %s AND run_id = %s""",
                (TENANT_ID, PROJECT_ID, AUTO_RUN_ID),
            )
            workflow_run = [_normalize_row(row) for row in cursor.fetchall()]
            cursor.execute(
                """SELECT event_type, payload_jsonb
                   FROM workflow_events
                   WHERE tenant_id = %s AND project_id = %s AND run_id = %s
                   ORDER BY sequence""",
                (TENANT_ID, PROJECT_ID, AUTO_RUN_ID),
            )
            workflow_events = [_normalize_row(row) for row in cursor.fetchall()]
            cursor.execute(
                """SELECT status, lifecycle
                   FROM worldline_sessions
                   WHERE tenant_id = %s AND project_id = %s AND session_id = %s""",
                (TENANT_ID, PROJECT_ID, SESSION_ID),
            )
            worldline_session = [_normalize_row(row) for row in cursor.fetchall()]
    return {
        "llm_activity": llm_activity,
        "usage_events": usage_events,
        "worldline_events": worldline_events,
        "workflow_run": workflow_run,
        "workflow_events": workflow_events,
        "worldline_session": worldline_session,
    }


def _cleanup_live_database(admin_url: str) -> None:
    with psycopg.connect(admin_url, autocommit=True) as connection:
        with connection.cursor() as cursor:
            cursor.execute("DELETE FROM tenants WHERE tenant_id = %s", (TENANT_ID,))
            cursor.execute(
                """DELETE FROM users
                   WHERE user_id = %s
                     AND NOT EXISTS (SELECT 1 FROM projects WHERE created_by = %s)""",
                (USER_ID, USER_ID),
            )


def _normalize_row(row: dict[str, Any]) -> dict[str, Any]:
    return {key: value for key, value in row.items()}


def _header(headers: dict[str, str], name: str) -> str:
    normalized = name.lower()
    for key, value in headers.items():
        if key.lower() == normalized:
            return value
    raise KeyError(name)
