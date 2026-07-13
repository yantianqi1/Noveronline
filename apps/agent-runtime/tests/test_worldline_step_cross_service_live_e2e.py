from __future__ import annotations

import asyncio
import base64
import json
import os
import socket
import subprocess
import threading
import time
from concurrent.futures import ThreadPoolExecutor
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

import psycopg
import pytest
from cryptography.hazmat.primitives.ciphers.aead import AESGCM
from psycopg import sql
from psycopg.conninfo import conninfo_to_dict, make_conninfo
from psycopg.rows import dict_row
from temporalio.client import Client
from temporalio.worker import Worker

from mirofish_agents.temporal.worldline import WorldlineStepWorkflow, worldline_step_activity
from live_schema_guard import ensure_live_schema


ROOT = Path(__file__).resolve().parents[3]
MIGRATION_SQL = ROOT / "infra" / "postgres" / "migrations" / "0001_core_saas.sql"
KEY_MATERIAL = "000102030405060708090a0b0c0d0e0f101112131415161718191a1b1c1d1e1f"
APP_ROLE = "mirofish_worldline_cross_app"
APP_PASSWORD = "mirofish_worldline_cross_password"
TENANT_ID = "71111111-1111-4111-8111-111111111111"
USER_ID = "72222222-2222-4222-8222-222222222222"
PROJECT_ID = "73333333-3333-4333-8333-333333333333"
SESSION_ID = "74444444-4444-4444-8444-444444444444"
SESSION_RUN_ID = "75555555-5555-4555-8555-555555555555"
CHANNEL_ID = "76666666-6666-4666-8666-666666666666"


def test_worldline_step_live_go_http_temporal_python_worker_closes_step(
    monkeypatch: pytest.MonkeyPatch,
    request: pytest.FixtureRequest,
) -> None:
    asyncio.run(_run_cross_service_e2e(monkeypatch, request))


async def _run_cross_service_e2e(
    monkeypatch: pytest.MonkeyPatch,
    request: pytest.FixtureRequest,
) -> None:
    admin_url = _live_database_url()
    temporal_address = _live_temporal_address()
    temporal_namespace = os.environ.get("MIROFISH_WORLDLINE_LIVE_TEMPORAL_NAMESPACE", "default").strip() or "default"
    task_queue = f"worldline-live-{os.getpid()}-{int(time.time() * 1000)}"
    request.addfinalizer(lambda: _cleanup_database(admin_url))

    with _BlockingProvider() as provider:
        _prepare_database(admin_url, provider.base_url)
        app_url = _app_database_url(admin_url)
        monkeypatch.setenv("DATABASE_URL", app_url)
        monkeypatch.setenv("LLM_CREDENTIAL_ENCRYPTION_KEY", KEY_MATERIAL)
        client = await Client.connect(temporal_address, namespace=temporal_namespace)
        with _start_go_api(app_url, temporal_address, temporal_namespace, task_queue) as api:
            async with _WorldlineWorker(client, task_queue):
                first = await asyncio.to_thread(_post_step, api, "req-worldline-live-same")
                assert await asyncio.to_thread(provider.started.wait, 15), "worker did not reach the live provider"

                replay_while_active = await asyncio.to_thread(_post_step, api, "req-worldline-live-same")
                overlap = await asyncio.to_thread(_post_step_error, api, "req-worldline-live-overlap")

                assert replay_while_active["run_id"] == first["run_id"]
                assert overlap["status"] == 409
                assert overlap["body"]["error"]["code"] == "WORLDLINE_STEP_ACTIVE"

                provider.release.set()
                persisted = await asyncio.to_thread(_wait_for_completed_state, admin_url, first["run_id"])
                replay_after_completion = await asyncio.to_thread(_post_step, api, "req-worldline-live-same")

    assert replay_after_completion["run_id"] == first["run_id"]
    assert len(provider.requests) == 1
    assert persisted == {
        "workflow_status": "completed",
        "workflow_progress": 100,
        "session_status": "paused",
        "candidate_count": 1,
        "candidate_step": 3,
        "candidate_status": "candidate",
        "candidate_lifecycle": "simulation",
        "queued_count": 1,
        "completed_count": 1,
    }
    encoded = json.dumps(
        {
            "first": first,
            "replay_while_active": replay_while_active,
            "overlap": overlap,
            "replay_after_completion": replay_after_completion,
            "persisted": persisted,
        },
        sort_keys=True,
    )
    for forbidden in (
        "sk-live-worldline-cross",
        "sk-provider-leak",
        "credential_ref",
        "private author prompt",
        "full event body",
    ):
        assert forbidden not in encoded


class _BlockingProvider:
    def __init__(self) -> None:
        self.requests: list[dict[str, Any]] = []
        self.started = threading.Event()
        self.release = threading.Event()
        self._server = ThreadingHTTPServer(("127.0.0.1", 0), self._handler())
        self.base_url = f"http://127.0.0.1:{self._server.server_port}/v1"
        self._thread = threading.Thread(target=self._server.serve_forever, daemon=True)

    def __enter__(self) -> "_BlockingProvider":
        self._thread.start()
        return self

    def __exit__(self, exc_type: object, exc: object, traceback: object) -> None:
        self.release.set()
        self._server.shutdown()
        self._server.server_close()
        self._thread.join(timeout=5)

    def _handler(self) -> type[BaseHTTPRequestHandler]:
        owner = self

        class Handler(BaseHTTPRequestHandler):
            def do_POST(self) -> None:  # noqa: N802
                length = int(self.headers.get("Content-Length", "0"))
                payload = json.loads(self.rfile.read(length).decode("utf-8"))
                owner.requests.append({"path": self.path, "body": payload})
                owner.started.set()
                if not owner.release.wait(timeout=20):
                    self.send_error(504)
                    return
                content = {
                    "candidate_events": [
                        {
                            "title": "The gate council delays the handoff",
                            "summary": "The current world remains unstable for another night.",
                            "kind": "political_turn",
                            "confidence": 0.81,
                            "involved_agent_ids": ["agent-live"],
                            "state_change_summary": "Pressure rises without canon adoption.",
                            "event_body": "full event body",
                            "api_key": "sk-provider-leak",
                        }
                    ]
                }
                response = {
                    "choices": [{"message": {"content": json.dumps(content)}}],
                    "usage": {"prompt_tokens": 9, "completion_tokens": 11, "total_tokens": 20},
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


class _WorldlineWorker:
    def __init__(self, client: Client, task_queue: str) -> None:
        self.client = client
        self.task_queue = task_queue
        self.executor: ThreadPoolExecutor | None = None
        self.worker: Worker | None = None

    async def __aenter__(self) -> "_WorldlineWorker":
        self.executor = ThreadPoolExecutor(max_workers=4)
        self.worker = Worker(
            self.client,
            task_queue=self.task_queue,
            workflows=[WorldlineStepWorkflow],
            activities=[worldline_step_activity],
            activity_executor=self.executor,
        )
        await self.worker.__aenter__()
        return self

    async def __aexit__(self, exc_type: Any, exc: Any, traceback: Any) -> None:
        if self.worker is not None:
            await self.worker.__aexit__(exc_type, exc, traceback)
        if self.executor is not None:
            self.executor.shutdown(wait=True)


class _GoAPI:
    def __init__(self, process: subprocess.Popen[str], base_url: str) -> None:
        self.process = process
        self.base_url = base_url

    def __enter__(self) -> str:
        return self.base_url

    def __exit__(self, exc_type: Any, exc: Any, traceback: Any) -> None:
        if self.process.poll() is None:
            self.process.terminate()
            try:
                self.process.wait(timeout=10)
            except subprocess.TimeoutExpired:
                self.process.kill()
                self.process.wait(timeout=10)


def _start_go_api(database_url: str, temporal_address: str, namespace: str, task_queue: str) -> _GoAPI:
    port = _free_port()
    base_url = f"http://127.0.0.1:{port}"
    env = os.environ.copy()
    env.update(
        {
            "DATABASE_URL": database_url,
            "TEMPORAL_ADDRESS": temporal_address,
            "TEMPORAL_NAMESPACE": namespace,
            "WORLDLINE_TASK_QUEUE": task_queue,
            "MIROFISH_API_ADDR": f"127.0.0.1:{port}",
        }
    )
    process = subprocess.Popen(
        ["go", "run", "./cmd/api"],
        cwd=ROOT / "apps" / "api",
        env=env,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
    )
    deadline = time.monotonic() + 45
    while time.monotonic() < deadline:
        if process.poll() is not None:
            output = process.stdout.read() if process.stdout is not None else ""
            raise AssertionError(f"Go API exited before health check: {output}")
        try:
            with urlopen(f"{base_url}/healthz", timeout=1) as response:
                if response.status == 200:
                    return _GoAPI(process, base_url)
        except (HTTPError, URLError, TimeoutError):
            time.sleep(0.25)
    process.terminate()
    output = process.stdout.read() if process.stdout is not None else ""
    raise AssertionError(f"Go API did not become healthy: {output}")


def _post_step(api: str, request_id: str) -> dict[str, Any]:
    status, body = _api_json(api, request_id)
    if status != 202:
        raise AssertionError(f"worldline step returned {status}: {body}")
    return body


def _post_step_error(api: str, request_id: str) -> dict[str, Any]:
    status, body = _api_json(api, request_id)
    return {"status": status, "body": body}


def _api_json(api: str, request_id: str) -> tuple[int, dict[str, Any]]:
    body = json.dumps(
        {
            "mode": "director",
            "options": {"step": 99, "goal": "Advance the current world", "prompt": "private author prompt"},
        }
    ).encode("utf-8")
    request = Request(
        f"{api}/v1/worldline-sessions/{SESSION_ID}/steps",
        data=body,
        method="POST",
        headers={
            "Content-Type": "application/json",
            "X-Tenant-Id": TENANT_ID,
            "X-User-Id": USER_ID,
            "X-Request-Id": request_id,
        },
    )
    try:
        with urlopen(request, timeout=15) as response:
            return response.status, json.loads(response.read().decode("utf-8"))
    except HTTPError as exc:
        return exc.code, json.loads(exc.read().decode("utf-8"))


def _wait_for_completed_state(admin_url: str, run_id: str) -> dict[str, Any]:
    deadline = time.monotonic() + 30
    last: dict[str, Any] = {}
    while time.monotonic() < deadline:
        last = _read_state(admin_url, run_id)
        if last.get("workflow_status") == "completed":
            return last
        time.sleep(0.2)
    raise AssertionError(f"worldline step did not complete: {last}")


def _read_state(admin_url: str, run_id: str) -> dict[str, Any]:
    with psycopg.connect(admin_url, row_factory=dict_row) as connection:
        with connection.cursor() as cursor:
            cursor.execute(
                """SELECT status AS workflow_status, progress AS workflow_progress
                   FROM workflow_runs WHERE tenant_id = %s AND project_id = %s AND run_id = %s""",
                (TENANT_ID, PROJECT_ID, run_id),
            )
            row = dict(cursor.fetchone() or {})
            cursor.execute(
                "SELECT status AS session_status FROM worldline_sessions WHERE tenant_id = %s AND session_id = %s",
                (TENANT_ID, SESSION_ID),
            )
            row.update(dict(cursor.fetchone() or {}))
            cursor.execute(
                """SELECT COUNT(*)::int AS candidate_count, MIN(step)::int AS candidate_step,
                          MIN(status) AS candidate_status, MIN(lifecycle) AS candidate_lifecycle
                   FROM worldline_events
                   WHERE tenant_id = %s AND project_id = %s AND session_id = %s AND source_run_id = %s""",
                (TENANT_ID, PROJECT_ID, SESSION_ID, run_id),
            )
            row.update(dict(cursor.fetchone() or {}))
            cursor.execute(
                """SELECT
                     COUNT(*) FILTER (WHERE event_type = 'workflow.queued')::int AS queued_count,
                     COUNT(*) FILTER (WHERE event_type = 'worldline.stage.completed')::int AS completed_count
                   FROM workflow_events WHERE tenant_id = %s AND project_id = %s AND run_id = %s""",
                (TENANT_ID, PROJECT_ID, run_id),
            )
            row.update(dict(cursor.fetchone() or {}))
    return row


def _prepare_database(admin_url: str, provider_base_url: str) -> None:
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
            _ensure_app_role(cursor)
            cursor.execute("DELETE FROM tenants WHERE tenant_id = %s", (TENANT_ID,))
            cursor.execute("DELETE FROM users WHERE user_id = %s", (USER_ID,))
            cursor.execute(
                "INSERT INTO users (user_id, email, display_name) VALUES (%s, 'worldline-cross@example.test', 'Worldline Cross')",
                (USER_ID,),
            )
            cursor.execute(
                "INSERT INTO tenants (tenant_id, slug, name, tenant_type) VALUES (%s, 'worldline-cross', 'Worldline Cross', 'personal')",
                (TENANT_ID,),
            )
            cursor.execute("INSERT INTO tenant_memberships (tenant_id, user_id, role) VALUES (%s, %s, 'owner')", (TENANT_ID, USER_ID))
            cursor.execute("INSERT INTO projects (tenant_id, project_id, title, created_by) VALUES (%s, %s, 'Cross Service', %s)", (TENANT_ID, PROJECT_ID, USER_ID))
            cursor.execute("INSERT INTO project_members (tenant_id, project_id, user_id, role) VALUES (%s, %s, %s, 'project_owner')", (TENANT_ID, PROJECT_ID, USER_ID))
            cursor.execute(
                """INSERT INTO workflow_runs (tenant_id, run_id, workflow_type, project_id, status, progress, started_by)
                   VALUES (%s, %s, 'worldline_session', %s, 'completed', 100, %s)""",
                (TENANT_ID, SESSION_RUN_ID, PROJECT_ID, USER_ID),
            )
            cursor.execute(
                """INSERT INTO worldline_sessions (tenant_id, session_id, project_id, run_id, status, lifecycle, goal_summary, created_by)
                   VALUES (%s, %s, %s, %s, 'paused', 'active', 'Cross-service current world', %s)""",
                (TENANT_ID, SESSION_ID, PROJECT_ID, SESSION_RUN_ID, USER_ID),
            )
            cursor.execute(
                """INSERT INTO worldline_events (tenant_id, session_id, project_id, step, title, summary, status, lifecycle)
                   VALUES (%s, %s, %s, 2, 'Existing step', 'Prior current-world event.', 'candidate', 'simulation')""",
                (TENANT_ID, SESSION_ID, PROJECT_ID),
            )
            cursor.execute(
                """INSERT INTO llm_channels (tenant_id, channel_id, name, provider, base_url, encrypted_api_key, max_concurrency, enabled)
                   VALUES (%s, %s, 'Cross Provider', 'openai-compatible', %s, %s, 1, true)""",
                (TENANT_ID, CHANNEL_ID, provider_base_url, _encrypt_api_key("sk-live-worldline-cross")),
            )
            cursor.execute(
                """INSERT INTO llm_models (tenant_id, channel_id, model_id, owned_by, supports_json, supports_tools)
                   VALUES (%s, %s, 'model-worldline-cross', 'cross-provider', true, false)""",
                (TENANT_ID, CHANNEL_ID),
            )
            cursor.execute(
                """INSERT INTO llm_module_bindings (tenant_id, project_id, module_key, channel_id, model_id, settings_jsonb, updated_by)
                   VALUES (%s, %s, 'worldline_director', %s, 'model-worldline-cross', '{}'::jsonb, %s)""",
                (TENANT_ID, PROJECT_ID, CHANNEL_ID, USER_ID),
            )


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


def _cleanup_database(admin_url: str) -> None:
    with psycopg.connect(admin_url, autocommit=True) as connection:
        with connection.cursor() as cursor:
            cursor.execute("DELETE FROM tenants WHERE tenant_id = %s", (TENANT_ID,))
            cursor.execute("DELETE FROM users WHERE user_id = %s", (USER_ID,))


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
    value = os.environ.get("MIROFISH_WORLDLINE_LIVE_DATABASE_URL", "").strip()
    if not value:
        pytest.skip("set MIROFISH_WORLDLINE_LIVE_DATABASE_URL to run the Worldline cross-service E2E")
    return value


def _live_temporal_address() -> str:
    value = os.environ.get("MIROFISH_WORLDLINE_LIVE_TEMPORAL_ADDRESS", "").strip()
    if not value:
        pytest.skip("set MIROFISH_WORLDLINE_LIVE_TEMPORAL_ADDRESS to run the Worldline cross-service E2E")
    return value


def _free_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.bind(("127.0.0.1", 0))
        return int(sock.getsockname()[1])
