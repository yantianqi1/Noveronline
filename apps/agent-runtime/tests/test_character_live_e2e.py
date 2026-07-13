from __future__ import annotations

import asyncio
import base64
import json
import os
import threading
import time
from concurrent.futures import ThreadPoolExecutor
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Any

import psycopg
import pytest
from cryptography.hazmat.primitives.ciphers.aead import AESGCM
from psycopg import sql
from psycopg.conninfo import conninfo_to_dict, make_conninfo
from temporalio.client import Client
from temporalio.worker import Worker

from mirofish_agents.temporal.character import CharacterDialogueWorkflow, character_dialogue_activity


KEY_MATERIAL = "000102030405060708090a0b0c0d0e0f101112131415161718191a1b1c1d1e1f"
APP_ROLE = "mirofish_character_live_app"
APP_PASSWORD = "mirofish_character_live_password"
TENANT_ID = "81111111-1111-4111-8111-111111111111"
USER_ID = "82222222-2222-4222-8222-222222222222"
PROJECT_ID = "83333333-3333-4333-8333-333333333333"
RUN_ID = "84444444-4444-4444-8444-444444444444"
INTERACTION_ID = "85555555-5555-4555-8555-555555555555"
USER_TURN_ID = "86666666-6666-4666-8666-666666666666"
CHANNEL_ID = "87777777-7777-4777-8777-777777777777"
WORLDLINE_SESSION_ID = "88888888-8888-4888-8888-888888888888"
TRACE_ID = f"trace_{RUN_ID}"


def test_character_dialogue_live_provider_app_role_temporal_replay(
    monkeypatch: pytest.MonkeyPatch, request: pytest.FixtureRequest
) -> None:
    asyncio.run(_run_live(monkeypatch, request))


async def _run_live(monkeypatch: pytest.MonkeyPatch, request: pytest.FixtureRequest) -> None:
    admin_url = _admin_database_url()
    temporal_address = os.environ.get("MIROFISH_CHARACTER_LIVE_TEMPORAL_ADDRESS", "127.0.0.1:7233")
    task_queue = f"character-live-{os.getpid()}-{int(time.time() * 1000)}"
    request.addfinalizer(lambda: _cleanup(admin_url))
    with _Provider() as provider:
        _prepare(admin_url, provider.base_url)
        monkeypatch.setenv("DATABASE_URL", _app_database_url(admin_url))
        monkeypatch.setenv("LLM_CREDENTIAL_ENCRYPTION_KEY", KEY_MATERIAL)
        client = await Client.connect(temporal_address)
        with ThreadPoolExecutor(max_workers=4) as executor:
            async with Worker(
                client,
                task_queue=task_queue,
                workflows=[CharacterDialogueWorkflow],
                activities=[character_dialogue_activity],
                activity_executor=executor,
            ):
                payload = _payload()
                first = await client.execute_workflow(
                    CharacterDialogueWorkflow.run,
                    payload,
                    id=f"character-live-first-{time.time_ns()}",
                    task_queue=task_queue,
                )
                replay = await client.execute_workflow(
                    CharacterDialogueWorkflow.run,
                    payload,
                    id=f"character-live-replay-{time.time_ns()}",
                    task_queue=task_queue,
                )

    assert first["status"] == "completed", first
    assert replay["status"] == "completed" and replay["replayed"] is True, replay
    assert len(provider.requests) == 1
    persisted = _read_persisted(admin_url)
    assert persisted["turn_count"] == 2
    assert persisted["agent_turn_count"] == 1
    assert persisted["workflow_status"] == "completed"
    assert persisted["trace_redaction"] == "full"
    assert persisted["memory_lifecycle"] == "candidate"
    assert persisted["relation_lifecycle"] == "candidate"
    assert persisted["world_lifecycle"] == "candidate"
    assert persisted["candidate_asset_count"] == 3
    assert persisted["candidate_asset_lifecycles"] == ["candidate"]
    assert persisted["candidate_memory_count"] == 1
    assert persisted["candidate_world_event_count"] == 1
    assert persisted["manuscript_count"] == 0
    public_json = json.dumps(persisted["public_events"], ensure_ascii=False)
    for forbidden in ("sk-character-live", "private memory", "provider raw", "manuscript prose"):
        assert forbidden not in public_json


class _Provider:
    def __init__(self) -> None:
        self.requests: list[dict[str, Any]] = []
        self._server = ThreadingHTTPServer(("127.0.0.1", 0), self._handler())
        self.base_url = f"http://127.0.0.1:{self._server.server_port}/v1"
        self._thread = threading.Thread(target=self._server.serve_forever, daemon=True)

    def __enter__(self) -> "_Provider":
        self._thread.start()
        return self

    def __exit__(self, *_: Any) -> None:
        self._server.shutdown()
        self._server.server_close()
        self._thread.join(timeout=5)

    def _handler(self) -> type[BaseHTTPRequestHandler]:
        owner = self

        class Handler(BaseHTTPRequestHandler):
            def do_POST(self) -> None:  # noqa: N802
                length = int(self.headers.get("Content-Length", "0"))
                owner.requests.append(json.loads(self.rfile.read(length)))
                content = {
                    "reply_summary": "The gate was opened from inside.",
                    "speaker_type": "agent",
                    "speaker_id": "agent-live",
                    "memory_candidates": [{"summary": "private memory", "lifecycle": "canon"}],
                    "relation_candidates": [{
                        "summary": "The gatekeeper distrusts the visitor.",
                        "source_entity_name": "Gatekeeper",
                        "target_entity_name": "Visitor",
                        "relationship_type": "distrusts",
                        "lifecycle": "canon",
                    }],
                    "world_state_candidates": [{
                        "proposal": "inspect lock",
                        "state_changes": {"inner_lock": "inspection_requested"},
                        "lifecycle": "canon",
                    }],
                    "response": "provider raw",
                    "manuscript": "manuscript prose",
                }
                encoded = json.dumps({
                    "choices": [{"message": {"content": json.dumps(content)}}],
                    "usage": {"prompt_tokens": 7, "completion_tokens": 9, "total_tokens": 16},
                }).encode()
                self.send_response(200)
                self.send_header("Content-Type", "application/json")
                self.send_header("Content-Length", str(len(encoded)))
                self.end_headers()
                self.wfile.write(encoded)

            def log_message(self, *_: Any) -> None:
                return

        return Handler


def _payload() -> dict[str, Any]:
    return {
        "context": {
            "tenant_id": TENANT_ID,
            "project_id": PROJECT_ID,
            "run_id": RUN_ID,
            "workflow_type": "character_dialogue",
            "actor_user_id": USER_ID,
            "module_key": "character_dialogue",
            "trace_id": TRACE_ID,
            "permissions": {"character_dialogue": ["run"]},
        },
        "interaction_id": INTERACTION_ID,
        "session_id": INTERACTION_ID,
        "user_turn_id": USER_TURN_ID,
    }


def _prepare(admin_url: str, provider_url: str) -> None:
    _cleanup(admin_url)
    with psycopg.connect(admin_url, autocommit=True) as connection:
        with connection.cursor() as cursor:
            _ensure_role(cursor)
            cursor.execute("INSERT INTO users (user_id, email, display_name) VALUES (%s, 'character-live@example.invalid', 'Character Live')", (USER_ID,))
            cursor.execute("INSERT INTO tenants (tenant_id, slug, name, tenant_type) VALUES (%s, 'character-live', 'Character Live', 'personal')", (TENANT_ID,))
            cursor.execute("INSERT INTO tenant_memberships (tenant_id, user_id, role) VALUES (%s, %s, 'owner')", (TENANT_ID, USER_ID))
            cursor.execute("INSERT INTO projects (tenant_id, project_id, title, created_by) VALUES (%s, %s, 'Character Live', %s)", (TENANT_ID, PROJECT_ID, USER_ID))
            cursor.execute("INSERT INTO project_members (tenant_id, project_id, user_id, role) VALUES (%s, %s, %s, 'project_owner')", (TENANT_ID, PROJECT_ID, USER_ID))
            cursor.execute("""INSERT INTO workflow_runs (tenant_id, run_id, workflow_type, project_id, status, progress, started_by)
                              VALUES (%s, %s, 'character_dialogue', %s, 'queued', 0, %s)""", (TENANT_ID, RUN_ID, PROJECT_ID, USER_ID))
            cursor.execute("""INSERT INTO workflow_events (tenant_id, run_id, workflow_type, project_id, event_type, sequence, payload_jsonb)
                              VALUES (%s, %s, 'character_dialogue', %s, 'workflow.queued', 1, %s::jsonb)""",
                           (TENANT_ID, RUN_ID, PROJECT_ID, json.dumps({"interaction_id": INTERACTION_ID, "session_id": INTERACTION_ID, "trace_id": TRACE_ID})))
            cursor.execute("""INSERT INTO worldline_sessions
                              (tenant_id, session_id, project_id, run_id, status, lifecycle, goal_summary, created_by)
                              VALUES (%s, %s, %s, %s, 'paused', 'active', 'Current world', %s)""",
                           (TENANT_ID, WORLDLINE_SESSION_ID, PROJECT_ID, RUN_ID, USER_ID))
            cursor.execute("""INSERT INTO character_interaction_sessions
                              (tenant_id, interaction_id, project_id, worldline_session_id, mode, status, title, pov_agent_id, created_by)
                              VALUES (%s, %s, %s, %s, 'dialogue', 'active', 'Gate inquiry', 'agent-live', %s)""",
                           (TENANT_ID, INTERACTION_ID, PROJECT_ID, WORLDLINE_SESSION_ID, USER_ID))
            cursor.execute("""INSERT INTO character_interaction_turns
                              (tenant_id, turn_id, interaction_id, project_id, turn_order, actor_type, actor_id, turn_kind, summary, created_by)
                              VALUES (%s, %s, %s, %s, 1, 'user', %s, 'dialogue', 'Who opened the gate?', %s)""",
                           (TENANT_ID, USER_TURN_ID, INTERACTION_ID, PROJECT_ID, USER_ID, USER_ID))
            cursor.execute("""INSERT INTO llm_channels
                              (tenant_id, channel_id, name, provider, base_url, encrypted_api_key, enabled)
                              VALUES (%s, %s, 'Character Provider', 'openai-compatible', %s, %s, true)""",
                           (TENANT_ID, CHANNEL_ID, provider_url, _encrypt("sk-character-live")))
            cursor.execute("""INSERT INTO llm_models (
                                tenant_id, channel_id, model_id, context_window,
                                supports_json, supports_tools, input_cost, output_cost
                              ) VALUES (%s, %s, 'model-character-live', 8192,
                                        true, false, 1, 2)""", (TENANT_ID, CHANNEL_ID))
            cursor.execute("""INSERT INTO llm_module_bindings
                              (tenant_id, project_id, module_key, channel_id, model_id, updated_by)
                              VALUES (%s, %s, 'character_dialogue', %s, 'model-character-live', %s)""",
                           (TENANT_ID, PROJECT_ID, CHANNEL_ID, USER_ID))
            for scope_type, project_id, module_key in (
                ("tenant", None, None),
                ("project", PROJECT_ID, None),
                ("module", PROJECT_ID, "character_dialogue"),
            ):
                cursor.execute(
                    """INSERT INTO llm_quota_policies (
                         tenant_id, scope_type, project_id, module_key, token_limit,
                         cost_limit_micros, concurrency_limit, period_seconds, updated_by
                       ) VALUES (%s, %s, %s, %s, 1000000, 1000000, 2, 3600, %s)""",
                    (TENANT_ID, scope_type, project_id, module_key, USER_ID),
                )


def _read_persisted(admin_url: str) -> dict[str, Any]:
    with psycopg.connect(admin_url) as connection:
        with connection.cursor() as cursor:
            cursor.execute("SELECT count(*), count(*) FILTER (WHERE actor_type = 'agent') FROM character_interaction_turns WHERE tenant_id = %s", (TENANT_ID,))
            turn_count, agent_turn_count = cursor.fetchone()
            cursor.execute("SELECT status FROM workflow_runs WHERE tenant_id = %s AND run_id = %s", (TENANT_ID, RUN_ID))
            workflow_status = cursor.fetchone()[0]
            cursor.execute(
                """SELECT redaction_level, payload_jsonb
                     FROM agent_trace_events
                    WHERE tenant_id = %s AND trace_id = %s
                      AND event_type = 'character.dialogue.result'""",
                (TENANT_ID, TRACE_ID),
            )
            trace_redaction, private = cursor.fetchone()
            cursor.execute("SELECT payload_jsonb FROM workflow_events WHERE tenant_id = %s AND run_id = %s ORDER BY sequence", (TENANT_ID, RUN_ID))
            public_events = [row[0] for row in cursor.fetchall()]
            cursor.execute("SELECT count(*) FROM manuscript_blocks WHERE tenant_id = %s AND project_id = %s", (TENANT_ID, PROJECT_ID))
            manuscript_count = cursor.fetchone()[0]
            cursor.execute("""SELECT count(*), array_agg(DISTINCT lifecycle ORDER BY lifecycle)
                              FROM assets WHERE tenant_id = %s AND project_id = %s
                                AND source_kind = 'character_dialogue'""", (TENANT_ID, PROJECT_ID))
            candidate_asset_count, candidate_asset_lifecycles = cursor.fetchone()
            cursor.execute("""SELECT count(*) FROM archive_memories
                              WHERE tenant_id = %s AND project_id = %s AND status = 'candidate'
                                AND source_kind = 'character_dialogue'""", (TENANT_ID, PROJECT_ID))
            candidate_memory_count = cursor.fetchone()[0]
            cursor.execute("""SELECT count(*) FROM worldline_events
                              WHERE tenant_id = %s AND project_id = %s AND session_id = %s
                                AND status = 'candidate' AND lifecycle = 'simulation'
                                AND kind = 'character_dialogue'""",
                           (TENANT_ID, PROJECT_ID, WORLDLINE_SESSION_ID))
            candidate_world_event_count = cursor.fetchone()[0]
    return {
        "turn_count": turn_count,
        "agent_turn_count": agent_turn_count,
        "workflow_status": workflow_status,
        "trace_redaction": trace_redaction,
        "memory_lifecycle": private["memory_candidates"][0]["lifecycle"],
        "relation_lifecycle": private["relation_candidates"][0]["lifecycle"],
        "world_lifecycle": private["world_state_candidates"][0]["lifecycle"],
        "public_events": public_events,
        "manuscript_count": manuscript_count,
        "candidate_asset_count": candidate_asset_count,
        "candidate_asset_lifecycles": candidate_asset_lifecycles,
        "candidate_memory_count": candidate_memory_count,
        "candidate_world_event_count": candidate_world_event_count,
    }


def _ensure_role(cursor: Any) -> None:
    cursor.execute("SELECT 1 FROM pg_roles WHERE rolname = %s", (APP_ROLE,))
    if cursor.fetchone() is None:
        cursor.execute(sql.SQL("CREATE ROLE {} LOGIN PASSWORD {} IN ROLE mirofish_app").format(sql.Identifier(APP_ROLE), sql.Literal(APP_PASSWORD)))
    else:
        cursor.execute(sql.SQL("ALTER ROLE {} WITH LOGIN PASSWORD {}").format(sql.Identifier(APP_ROLE), sql.Literal(APP_PASSWORD)))
    cursor.execute(sql.SQL("GRANT mirofish_app TO {}").format(sql.Identifier(APP_ROLE)))


def _cleanup(admin_url: str) -> None:
    with psycopg.connect(admin_url, autocommit=True) as connection:
        with connection.cursor() as cursor:
            cursor.execute("DELETE FROM tenants WHERE tenant_id = %s", (TENANT_ID,))
            cursor.execute("DELETE FROM users WHERE user_id = %s", (USER_ID,))


def _app_database_url(admin_url: str) -> str:
    parts = conninfo_to_dict(admin_url)
    parts.update(user=APP_ROLE, password=APP_PASSWORD)
    return make_conninfo(**parts)


def _encrypt(value: str) -> str:
    iv = bytes.fromhex("00112233445566778899aabb")
    sealed = AESGCM(bytes.fromhex(KEY_MATERIAL)).encrypt(iv, value.encode(), None)
    return "aes-256-gcm:v1:%s:%s:%s" % (
        base64.b64encode(iv).decode(),
        base64.b64encode(sealed[-16:]).decode(),
        base64.b64encode(sealed[:-16]).decode(),
    )


def _admin_database_url() -> str:
    value = os.environ.get("MIROFISH_CHARACTER_LIVE_DATABASE_URL", "").strip()
    if not value:
        pytest.skip("set MIROFISH_CHARACTER_LIVE_DATABASE_URL to run Character live E2E")
    return value
