from __future__ import annotations

import base64
import json
import os
import threading
import time
from dataclasses import dataclass
from http.cookies import SimpleCookie
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.parse import quote, urlparse
from urllib.request import Request, urlopen
from uuid import uuid4

import psycopg
import pytest
from cryptography.hazmat.primitives.ciphers.aead import AESGCM


ENV_PREFIX = "MIROFISH_CHARACTER_HTTP_LIVE_"
PROVIDER_API_KEY = "sk-character-http-live"
PROVIDER_MODEL = "model-character-http-live"
WRITER_ORCHESTRATOR_MODEL = "model-writer-orchestrator-http-live"
WRITER_COMPOSER_MODEL = "model-writer-composer-http-live"
WRITER_PRIVATE_PROSE = "Live chapter candidate from Character Console."
FORBIDDEN_PUBLIC_VALUES = (
    PROVIDER_API_KEY,
    "credential_ref",
    "private-provider-response",
    "private-manuscript-body",
    WRITER_PRIVATE_PROSE,
    "messages",
    "prompt",
    "raw_body",
    "raw_content",
)


@dataclass(frozen=True)
class _Config:
    database_url: str
    api_base_url: str
    key_material: str
    provider_host: str


@dataclass(frozen=True)
class _FixtureIDs:
    tenant: str
    user: str
    project: str
    worldline_run: str
    worldline_session: str
    character_channel: str
    writer_orchestrator_channel: str
    writer_composer_channel: str
    chapter: str
    scene: str

    @classmethod
    def create(cls) -> "_FixtureIDs":
        return cls(*(str(uuid4()) for _ in range(10)))


def test_character_dialogue_real_http_temporal_worker_multi_round_recovery(
    request: pytest.FixtureRequest,
) -> None:
    config = _live_config()
    ids = _FixtureIDs.create()
    request.addfinalizer(lambda: _cleanup(config.database_url, ids))

    with _BlockingProvider(config.provider_host) as provider:
        _prepare_database(config, ids, provider.worker_base_url)
        api = _AuthenticatedAPI.create(config.api_base_url, ids)
        interaction = api.post(
            f"/v1/projects/{ids.project}/character-interactions",
            {
                "worldline_session_id": ids.worldline_session,
                "anchor_type": "worldline_session",
                "anchor_id": ids.worldline_session,
                "pov_agent_id": "agent-live",
                "mode": "dialogue",
                "title": "Gate inquiry",
                "summary": "A private conversation at the inner gate.",
                "metadata": {},
            },
            expected=201,
        )
        interaction_id = interaction["interaction_id"]

        first_turn = _append_user_turn(api, interaction_id, ids.user, "Who opened the gate?")
        first_run = _start_dialogue(api, interaction_id, first_turn["turn_id"], "round-1")
        assert provider.started.wait(20), "Character worker did not reach the local provider"

        conflict_status, conflict = api.request(
            "POST",
            f"/v1/character-interactions/{interaction_id}/dialogue",
            {"user_turn_id": first_turn["turn_id"]},
            request_id="round-1-conflict",
        )
        assert conflict_status == 409, conflict
        assert conflict["error"]["code"] == "CHARACTER_TURN_ACTIVE"
        assert (
            conflict["error"]["message"]
            == "character interaction already has an active dialogue turn"
        )
        assert provider.request_count == 1

        provider.release.set()
        first_terminal = _wait_for_run(api, first_run["run_id"])
        first_recovery = _read_recovery(api, interaction_id)
        _assert_first_round(first_terminal, first_recovery, first_turn["turn_id"])

        second_turn = _append_user_turn(
            api, interaction_id, ids.user, "What should we inspect next?"
        )
        second_run = _start_dialogue(api, interaction_id, second_turn["turn_id"], "round-2")
        second_terminal = _wait_for_run(api, second_run["run_id"])
        final_recovery = _read_recovery(api, interaction_id)
        refreshed_recovery = _read_recovery(api, interaction_id)

        chapter_admission = api.post(
            f"/v1/character-interactions/{interaction_id}/chapter-drafts",
            {
                "target_chapter_id": ids.chapter,
                "target_scene_id": ids.scene,
                "pov_mode": "first_person",
                "style_asset_ids": [],
                "author_instruction": "Preserve the restrained gate conversation.",
            },
            expected=202,
            request_id="chapter-handoff",
        )
        chapter_terminal = _wait_for_run(api, chapter_admission["run_id"])
        chapter_detail = api.get(f"/v1/writer-runs/{chapter_admission['run_id']}")
        chapter_refreshed = api.get(f"/v1/writer-runs/{chapter_admission['run_id']}")

    _assert_final_state(
        second_terminal,
        final_recovery,
        refreshed_recovery,
        chapter_admission,
        chapter_terminal,
        chapter_detail,
        chapter_refreshed,
        provider,
    )
    _assert_public_privacy(
        interaction,
        conflict,
        first_run,
        first_terminal,
        first_recovery,
        second_run,
        second_terminal,
        final_recovery,
        refreshed_recovery,
        chapter_admission,
        chapter_terminal,
        chapter_detail,
        chapter_refreshed,
    )
    _assert_database_state(
        config.database_url,
        ids,
        interaction_id,
        chapter_admission["run_id"],
    )


class _AuthenticatedAPI:
    def __init__(self, base_url: str, ids: _FixtureIDs, cookie: str, csrf: str) -> None:
        self.base_url = base_url.rstrip("/")
        self.ids = ids
        self.cookie = cookie
        self.csrf = csrf

    @classmethod
    def create(cls, base_url: str, ids: _FixtureIDs) -> "_AuthenticatedAPI":
        status, _, headers = _request_json(
            base_url,
            "POST",
            "/v1/auth/dev-sessions",
            {"user_id": ids.user},
            {},
        )
        if status != 201:
            raise AssertionError(f"dev session returned HTTP {status}")
        cookie = SimpleCookie()
        for value in headers.get_all("Set-Cookie", []):
            cookie.load(value)
        if "mirofish_session" not in cookie:
            raise AssertionError("dev session did not return the session cookie")
        cookie_header = f"mirofish_session={cookie['mirofish_session'].value}"
        status, body, _ = _request_json(
            base_url,
            "GET",
            "/v1/auth/csrf-token",
            None,
            {"Cookie": cookie_header},
        )
        if status != 200 or not str(body.get("csrf_token", "")).strip():
            raise AssertionError(f"CSRF token request returned HTTP {status}")
        return cls(base_url, ids, cookie_header, body["csrf_token"])

    def request(
        self,
        method: str,
        path: str,
        payload: dict[str, Any] | None = None,
        *,
        request_id: str = "",
    ) -> tuple[int, dict[str, Any]]:
        headers = {
            "Cookie": self.cookie,
            "X-Tenant-Id": self.ids.tenant,
        }
        if method != "GET":
            headers["X-CSRF-Token"] = self.csrf
        if request_id:
            headers["X-Request-Id"] = request_id
        status, body, _ = _request_json(self.base_url, method, path, payload, headers)
        return status, body

    def post(
        self,
        path: str,
        payload: dict[str, Any],
        *,
        expected: int,
        request_id: str = "",
    ) -> dict[str, Any]:
        status, body = self.request("POST", path, payload, request_id=request_id)
        if status != expected:
            raise AssertionError(f"POST {path} returned HTTP {status}: {_public_error(body)}")
        return body

    def get(self, path: str) -> dict[str, Any]:
        status, body = self.request("GET", path)
        if status != 200:
            raise AssertionError(f"GET {path} returned HTTP {status}: {_public_error(body)}")
        return body


class _BlockingProvider:
    def __init__(self, worker_host: str) -> None:
        self.requests: list[dict[str, Any]] = []
        self.started = threading.Event()
        self.release = threading.Event()
        self._lock = threading.Lock()
        self._server = ThreadingHTTPServer(("0.0.0.0", 0), self._handler())
        self.worker_base_url = f"http://{worker_host}:{self._server.server_port}/v1"
        self._thread = threading.Thread(target=self._server.serve_forever, daemon=True)

    @property
    def request_count(self) -> int:
        with self._lock:
            return len(self.requests)

    def __enter__(self) -> "_BlockingProvider":
        self._thread.start()
        return self

    def __exit__(self, *_: Any) -> None:
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
                request_record = {
                    "path": self.path,
                    "authorization": self.headers.get("Authorization"),
                    "model": payload.get("model"),
                    "tenant_id": self.headers.get("X-MiroFish-Tenant-Id"),
                    "project_id": self.headers.get("X-MiroFish-Project-Id"),
                    "run_id": self.headers.get("X-MiroFish-Run-Id"),
                    "module_key": self.headers.get("X-MiroFish-Module-Key"),
                }
                module_key = request_record["module_key"] or {
                    WRITER_ORCHESTRATOR_MODEL: "writer_orchestrator",
                    WRITER_COMPOSER_MODEL: "writer_composer",
                }.get(request_record["model"])
                request_record["module_key"] = module_key
                with owner._lock:
                    owner.requests.append(request_record)
                    module_call_number = sum(
                        item["module_key"] == module_key for item in owner.requests
                    )
                if module_key == "character_dialogue" and module_call_number == 1:
                    owner.started.set()
                    if not owner.release.wait(timeout=30):
                        self.send_error(504)
                        return
                if module_key in {"writer_orchestrator", "writer_composer"}:
                    self._respond_writer(payload)
                else:
                    self._respond_character(module_call_number)

            def _respond_character(self, call_number: int) -> None:
                content = {
                    "reply_summary": f"The gate was opened from inside, round {call_number}.",
                    "speaker_type": "agent",
                    "speaker_id": "agent-live",
                    "memory_candidates": [
                        {"summary": f"Candidate memory {call_number}", "lifecycle": "canon"}
                    ],
                    "relation_candidates": [
                        {
                            "summary": "The gatekeeper distrusts the visitor.",
                            "source_entity_name": "Gatekeeper",
                            "target_entity_name": "Visitor",
                            "relationship_type": "distrusts",
                            "lifecycle": "canon",
                        }
                    ],
                    "world_state_candidates": [
                        {
                            "summary": "Inspect the inner lock.",
                            "state_changes": {"inner_lock": "inspection_requested"},
                            "lifecycle": "canon",
                        }
                    ],
                    "response": "private-provider-response",
                    "manuscript": "private-manuscript-body",
                }
                encoded = json.dumps(
                    {
                        "choices": [{"message": {"content": json.dumps(content)}}],
                        "usage": {"prompt_tokens": 7, "completion_tokens": 9, "total_tokens": 16},
                    }
                ).encode("utf-8")
                self.send_response(200)
                self.send_header("Content-Type", "application/json")
                self.send_header("Content-Length", str(len(encoded)))
                self.end_headers()
                self.wfile.write(encoded)

            def _respond_writer(self, payload: dict[str, Any]) -> None:
                messages = payload.get("messages")
                tools = payload.get("tools")
                last_role = messages[-1].get("role") if isinstance(messages, list) and messages else ""
                if isinstance(tools, list) and tools and last_role != "tool":
                    chunks = [
                        _writer_chunk(
                            {
                                "role": "assistant",
                                "tool_calls": [
                                    {
                                        "index": 0,
                                        "id": "call-project",
                                        "type": "function",
                                        "function": {
                                            "name": "query_project_context",
                                            "arguments": "{}",
                                        },
                                    }
                                ],
                            },
                            None,
                        ),
                        _writer_chunk({}, "tool_calls"),
                    ]
                else:
                    text = (
                        "Live authoritative writing brief."
                        if isinstance(tools, list) and tools
                        else WRITER_PRIVATE_PROSE
                    )
                    chunks = [
                        _writer_chunk({"role": "assistant"}, None),
                        _writer_chunk({"content": text[:20]}, None),
                        _writer_chunk({"content": text[20:]}, None),
                        _writer_chunk(
                            {},
                            "stop",
                            {"prompt_tokens": 5, "completion_tokens": 7, "total_tokens": 12},
                        ),
                    ]
                encoded = "".join(
                    f"data: {json.dumps(chunk)}\n\n" for chunk in chunks
                ) + "data: [DONE]\n\n"
                body = encoded.encode("utf-8")
                self.send_response(200)
                self.send_header("Content-Type", "text/event-stream")
                self.send_header("Content-Length", str(len(body)))
                self.end_headers()
                self.wfile.write(body)

            def log_message(self, *_: Any) -> None:
                return

        return Handler


def _append_user_turn(
    api: _AuthenticatedAPI,
    interaction_id: str,
    user_id: str,
    summary: str,
) -> dict[str, Any]:
    return api.post(
        f"/v1/character-interactions/{interaction_id}/turns",
        {
            "actor_type": "user",
            "actor_id": user_id,
            "turn_kind": "dialogue",
            "summary": summary,
            "action": {},
            "world_state_delta": {},
            "trace_id": "",
        },
        expected=201,
    )


def _start_dialogue(
    api: _AuthenticatedAPI,
    interaction_id: str,
    user_turn_id: str,
    request_id: str,
) -> dict[str, Any]:
    return api.post(
        f"/v1/character-interactions/{interaction_id}/dialogue",
        {"user_turn_id": user_turn_id},
        expected=202,
        request_id=request_id,
    )


def _wait_for_run(api: _AuthenticatedAPI, run_id: str) -> dict[str, Any]:
    deadline = time.monotonic() + 45
    last: dict[str, Any] = {}
    while time.monotonic() < deadline:
        last = api.get(f"/v1/workflow-runs/{run_id}")
        if last.get("status") == "completed":
            return last
        if last.get("status") in {"failed", "cancelled"}:
            raise AssertionError(
                f"Character dialogue run reached {last['status']}: "
                f"{last.get('error_code', '')} {last.get('error_message', '')}"
            )
        time.sleep(0.25)
    raise AssertionError(
        f"Character dialogue run did not complete; last status={last.get('status')}"
    )


def _read_recovery(api: _AuthenticatedAPI, interaction_id: str) -> dict[str, Any]:
    events = api.get(f"/v1/character-interactions/{interaction_id}/events")
    cursor = events["items"][0]["event_id"] if events["items"] else ""
    replay = api.get(
        f"/v1/character-interactions/{interaction_id}/events?after_event_id={quote(cursor)}"
    )
    return {
        "detail": api.get(f"/v1/character-interactions/{interaction_id}"),
        "turns": api.get(f"/v1/character-interactions/{interaction_id}/turns"),
        "events": events,
        "cursor": cursor,
        "cursor_replay": replay,
        "proposals": api.get(f"/v1/character-interactions/{interaction_id}/proposals"),
    }


def _assert_first_round(
    terminal: dict[str, Any], recovery: dict[str, Any], user_turn_id: str
) -> None:
    assert terminal["status"] == "completed" and terminal["progress"] == 100
    turns = recovery["turns"]["items"]
    assert [turn["turn_order"] for turn in turns] == [1, 2]
    assert turns[0]["turn_id"] == user_turn_id and turns[0]["actor_type"] == "user"
    assert turns[1]["actor_type"] == "agent"
    event_types = {event["event_type"] for event in recovery["events"]["items"]}
    assert {"workflow.queued", "character.dialogue.started", "character.turn.completed"}.issubset(
        event_types
    )
    completed = next(
        event
        for event in recovery["events"]["items"]
        if event["event_type"] == "character.turn.completed"
    )
    assert completed["payload"]["status"] == "completed"
    assert completed["payload"]["memory_candidate_count"] == 1
    assert completed["payload"]["relation_candidate_count"] == 1
    assert completed["payload"]["world_state_candidate_count"] == 1
    assert all(
        event["event_id"] != recovery["cursor"]
        for event in recovery["cursor_replay"]["items"]
    )
    proposals = recovery["proposals"]["items"]
    assert len(proposals) == 3
    assert {proposal["lifecycle"] for proposal in proposals} == {"candidate"}


def _assert_final_state(
    terminal: dict[str, Any],
    recovery: dict[str, Any],
    refreshed: dict[str, Any],
    chapter_admission: dict[str, Any],
    chapter_terminal: dict[str, Any],
    chapter_detail: dict[str, Any],
    chapter_refreshed: dict[str, Any],
    provider: _BlockingProvider,
) -> None:
    assert terminal["status"] == "completed" and terminal["progress"] == 100
    turns = recovery["turns"]["items"]
    assert [turn["turn_order"] for turn in turns] == [1, 2, 3, 4]
    assert [turn["actor_type"] for turn in turns] == ["user", "agent", "user", "agent"]
    character_requests = [
        item for item in provider.requests if item["module_key"] == "character_dialogue"
    ]
    writer_requests = [
        item
        for item in provider.requests
        if item["module_key"] in {"writer_orchestrator", "writer_composer"}
    ]
    assert len(character_requests) == 2
    assert len(writer_requests) == 3
    assert all(request["path"] == "/v1/chat/completions" for request in provider.requests)
    assert all(
        request["authorization"] == f"Bearer {PROVIDER_API_KEY}"
        for request in provider.requests
    )
    assert all(request["model"] == PROVIDER_MODEL for request in character_requests)
    assert [request["model"] for request in writer_requests].count(
        WRITER_ORCHESTRATOR_MODEL
    ) == 2
    assert [request["model"] for request in writer_requests].count(
        WRITER_COMPOSER_MODEL
    ) == 1
    assert {request["module_key"] for request in writer_requests} == {
        "writer_orchestrator",
        "writer_composer",
    }
    assert all(request["tenant_id"] and request["project_id"] for request in character_requests)
    assert len({request["run_id"] for request in character_requests}) == 2
    assert len(recovery["proposals"]["items"]) == 6
    assert {item["lifecycle"] for item in recovery["proposals"]["items"]} == {"candidate"}
    assert refreshed == recovery
    assert chapter_admission["workflow_type"] == "writer_run"
    assert chapter_admission["status"] == "queued"
    assert chapter_terminal["workflow_type"] == "writer_run"
    assert chapter_terminal["status"] == "completed"
    assert chapter_terminal["progress"] == 100
    assert chapter_detail["run_id"] == chapter_admission["run_id"]
    assert chapter_detail["status"] == "completed"
    assert chapter_refreshed == chapter_detail


def _assert_public_privacy(*responses: dict[str, Any]) -> None:
    public_json = json.dumps(responses, ensure_ascii=False, sort_keys=True)
    for forbidden in FORBIDDEN_PUBLIC_VALUES:
        assert forbidden not in public_json


def _assert_database_state(
    database_url: str,
    ids: _FixtureIDs,
    interaction_id: str,
    writer_run_id: str,
) -> None:
    with psycopg.connect(database_url) as connection, connection.cursor() as cursor:
        cursor.execute(
            "SELECT count(*) FROM manuscript_blocks WHERE tenant_id = %s AND project_id = %s",
            (ids.tenant, ids.project),
        )
        assert cursor.fetchone()[0] == 0
        cursor.execute(
            """SELECT count(*), array_agg(DISTINCT lifecycle ORDER BY lifecycle)
               FROM assets WHERE tenant_id = %s AND project_id = %s
                 AND source_kind = 'character_dialogue'""",
            (ids.tenant, ids.project),
        )
        assert cursor.fetchone() == (6, ["candidate"])
        cursor.execute(
            """SELECT status, chapter_id::text, scene_id::text, content_text
               FROM writer_drafts
               WHERE tenant_id = %s AND project_id = %s AND run_id = %s""",
            (ids.tenant, ids.project, writer_run_id),
        )
        assert cursor.fetchall() == [
            (
                "candidate",
                ids.chapter,
                ids.scene,
                WRITER_PRIVATE_PROSE,
            )
        ]
        cursor.execute(
            """SELECT options_jsonb->>'source',
                      options_jsonb->>'character_interaction_id',
                      options_jsonb->>'target_chapter_id',
                      options_jsonb->>'target_scene_id'
               FROM writer_runs
               WHERE tenant_id = %s AND project_id = %s AND run_id = %s""",
            (ids.tenant, ids.project, writer_run_id),
        )
        assert cursor.fetchone() == (
            "character_console",
            interaction_id,
            ids.chapter,
            ids.scene,
        )
        cursor.execute(
            """SELECT EXISTS (
                     SELECT 1 FROM character_interaction_sessions
                     WHERE tenant_id = %s AND project_id = %s AND interaction_id = %s
                   ), count(*)
               FROM character_interaction_turns
               WHERE tenant_id = %s AND project_id = %s AND interaction_id = %s""",
            (
                ids.tenant,
                ids.project,
                interaction_id,
                ids.tenant,
                ids.project,
                interaction_id,
            ),
        )
        assert cursor.fetchone() == (True, 4)
        cursor.execute(
            """SELECT module_key, status
               FROM llm_activity
               WHERE tenant_id = %s AND project_id = %s AND run_id = %s
               ORDER BY module_key""",
            (ids.tenant, ids.project, writer_run_id),
        )
        assert cursor.fetchall() == [
            ("writer_composer", "completed"),
            ("writer_orchestrator", "completed"),
        ]
        cursor.execute(
            """SELECT payload_jsonb FROM workflow_events
               WHERE tenant_id = %s AND project_id = %s
                 AND payload_jsonb->>'interaction_id' = %s""",
            (ids.tenant, ids.project, interaction_id),
        )
        public_events = [row[0] for row in cursor.fetchall()]
    _assert_public_privacy({"events": public_events})


def _prepare_database(config: _Config, ids: _FixtureIDs, provider_url: str) -> None:
    encrypted_key = _encrypt(PROVIDER_API_KEY, config.key_material)
    slug = f"character-http-live-{ids.tenant[:8]}"
    email = f"character-http-live-{ids.user[:8]}@example.invalid"
    with psycopg.connect(config.database_url, autocommit=True) as connection:
        with connection.cursor() as cursor:
            cursor.execute(
                """INSERT INTO users (user_id, email, display_name)
                   VALUES (%s, %s, 'Character HTTP Live')""",
                (ids.user, email),
            )
            cursor.execute(
                """INSERT INTO tenants (tenant_id, slug, name, tenant_type)
                   VALUES (%s, %s, 'Character HTTP Live', 'personal')""",
                (ids.tenant, slug),
            )
            cursor.execute(
                """INSERT INTO tenant_memberships (tenant_id, user_id, role)
                   VALUES (%s, %s, 'owner')""",
                (ids.tenant, ids.user),
            )
            cursor.execute(
                """INSERT INTO projects (tenant_id, project_id, title, created_by)
                   VALUES (%s, %s, 'Character HTTP Live', %s)""",
                (ids.tenant, ids.project, ids.user),
            )
            cursor.execute(
                """INSERT INTO project_members (tenant_id, project_id, user_id, role)
                   VALUES (%s, %s, %s, 'project_owner')""",
                (ids.tenant, ids.project, ids.user),
            )
            cursor.execute(
                """INSERT INTO llm_quota_policies
                   (tenant_id, scope_type, token_limit, cost_limit_micros,
                    concurrency_limit, period_seconds, updated_by)
                   VALUES (%s, 'tenant', 1000000, 1000000, 2, 3600, %s)""",
                (ids.tenant, ids.user),
            )
            cursor.execute(
                """INSERT INTO llm_quota_policies
                   (tenant_id, scope_type, project_id, token_limit, cost_limit_micros,
                    concurrency_limit, period_seconds, updated_by)
                   VALUES (%s, 'project', %s, 1000000, 1000000, 2, 3600, %s)""",
                (ids.tenant, ids.project, ids.user),
            )
            cursor.execute(
                """INSERT INTO workflow_runs
                   (tenant_id, run_id, workflow_type, project_id, status, progress, started_by)
                   VALUES (%s, %s, 'worldline_session', %s, 'completed', 100, %s)""",
                (ids.tenant, ids.worldline_run, ids.project, ids.user),
            )
            cursor.execute(
                """INSERT INTO worldline_sessions
                   (tenant_id, session_id, project_id, run_id, status, lifecycle,
                    goal_summary, created_by)
                   VALUES (%s, %s, %s, %s, 'paused', 'active', 'Current world', %s)""",
                (
                    ids.tenant,
                    ids.worldline_session,
                    ids.project,
                    ids.worldline_run,
                    ids.user,
                ),
            )
            for module_key, channel_id, model_id, supports_tools in (
                ("character_dialogue", ids.character_channel, PROVIDER_MODEL, False),
                (
                    "writer_orchestrator",
                    ids.writer_orchestrator_channel,
                    WRITER_ORCHESTRATOR_MODEL,
                    True,
                ),
                (
                    "writer_composer",
                    ids.writer_composer_channel,
                    WRITER_COMPOSER_MODEL,
                    False,
                ),
            ):
                binding_settings = (
                    {
                        "max_tokens": 240,
                        "quota_reserved_tokens": 512,
                        "input_cost": 1,
                        "output_cost": 2,
                        "temperature": 0,
                    }
                    if module_key in {"writer_orchestrator", "writer_composer"}
                    else {}
                )
                cursor.execute(
                    """INSERT INTO llm_channels
                       (tenant_id, channel_id, name, provider, base_url,
                        encrypted_api_key, enabled)
                       VALUES (%s, %s, %s, 'openai-compatible', %s, %s, true)""",
                    (ids.tenant, channel_id, module_key, provider_url, encrypted_key),
                )
                cursor.execute(
                    """INSERT INTO llm_models
                       (tenant_id, channel_id, model_id, context_window,
                        supports_json, supports_tools, input_cost, output_cost)
                       VALUES (%s, %s, %s, 8192, true, %s, 1, 2)""",
                    (ids.tenant, channel_id, model_id, supports_tools),
                )
                cursor.execute(
                    """INSERT INTO llm_module_bindings
                       (tenant_id, project_id, module_key, channel_id, model_id,
                        settings_jsonb, updated_by)
                       VALUES (%s, %s, %s, %s, %s, %s::jsonb, %s)""",
                    (
                        ids.tenant,
                        ids.project,
                        module_key,
                        channel_id,
                        model_id,
                        json.dumps(binding_settings),
                        ids.user,
                    ),
                )
                if module_key in {"writer_orchestrator", "writer_composer"}:
                    cursor.execute(
                        """INSERT INTO llm_quota_policies
                           (tenant_id, scope_type, project_id, module_key, token_limit,
                            cost_limit_micros, concurrency_limit, period_seconds, updated_by)
                           VALUES (%s, 'module', %s, %s, 1000000, 1000000, 1, 3600, %s)""",
                        (ids.tenant, ids.project, module_key, ids.user),
                    )


def _cleanup(database_url: str, ids: _FixtureIDs) -> None:
    with psycopg.connect(database_url, autocommit=True) as connection:
        with connection.cursor() as cursor:
            cursor.execute("DELETE FROM tenants WHERE tenant_id = %s", (ids.tenant,))
            cursor.execute("DELETE FROM users WHERE user_id = %s", (ids.user,))


def _encrypt(value: str, key_material: str) -> str:
    try:
        key = bytes.fromhex(key_material)
    except ValueError as exc:
        raise AssertionError(f"{ENV_PREFIX}KEY_MATERIAL must be a 64-character hex key") from exc
    if len(key) != 32:
        raise AssertionError(f"{ENV_PREFIX}KEY_MATERIAL must be a 64-character hex key")
    iv = os.urandom(12)
    sealed = AESGCM(key).encrypt(iv, value.encode("utf-8"), None)
    return "aes-256-gcm:v1:%s:%s:%s" % (
        base64.b64encode(iv).decode("ascii"),
        base64.b64encode(sealed[-16:]).decode("ascii"),
        base64.b64encode(sealed[:-16]).decode("ascii"),
    )


def _request_json(
    base_url: str,
    method: str,
    path: str,
    payload: dict[str, Any] | None,
    headers: dict[str, str],
) -> tuple[int, dict[str, Any], Any]:
    request_headers = {"Accept": "application/json", **headers}
    body = None
    if payload is not None:
        body = json.dumps(payload).encode("utf-8")
        request_headers["Content-Type"] = "application/json"
    request = Request(
        f"{base_url.rstrip('/')}{path}",
        data=body,
        method=method,
        headers=request_headers,
    )
    try:
        with urlopen(request, timeout=20) as response:
            encoded = response.read().decode("utf-8")
            return response.status, json.loads(encoded or "{}"), response.headers
    except HTTPError as exc:
        encoded = exc.read().decode("utf-8")
        return exc.code, json.loads(encoded or "{}"), exc.headers
    except (URLError, TimeoutError) as exc:
        raise AssertionError(f"local API request failed: {method} {path}") from exc


def _live_config() -> _Config:
    configured = {
        name: value.strip()
        for name, value in os.environ.items()
        if name.startswith(ENV_PREFIX) and value.strip()
    }
    if not configured:
        pytest.skip(f"set {ENV_PREFIX}* variables to run Character HTTP live-local E2E")
    required = {
        f"{ENV_PREFIX}ALLOW_MUTATION",
        f"{ENV_PREFIX}THROWAWAY_PROJECT",
        f"{ENV_PREFIX}DATABASE_URL",
        f"{ENV_PREFIX}API_BASE_URL",
        f"{ENV_PREFIX}KEY_MATERIAL",
    }
    missing = sorted(required - configured.keys())
    if missing:
        raise AssertionError(
            "Character HTTP live-local configuration is incomplete: " + ", ".join(missing)
        )
    for opt_in in ("ALLOW_MUTATION", "THROWAWAY_PROJECT"):
        if configured[f"{ENV_PREFIX}{opt_in}"] != "1":
            raise AssertionError(f"{ENV_PREFIX}{opt_in} must be exactly 1")
    api_base_url = configured[f"{ENV_PREFIX}API_BASE_URL"].rstrip("/")
    parsed = urlparse(api_base_url)
    if parsed.scheme != "http" or parsed.hostname not in {"127.0.0.1", "localhost", "::1"}:
        raise AssertionError(f"{ENV_PREFIX}API_BASE_URL must be a local HTTP URL")
    return _Config(
        database_url=configured[f"{ENV_PREFIX}DATABASE_URL"],
        api_base_url=api_base_url,
        key_material=configured[f"{ENV_PREFIX}KEY_MATERIAL"],
        provider_host=configured.get(f"{ENV_PREFIX}PROVIDER_HOST", "host.docker.internal"),
    )


def _public_error(body: dict[str, Any]) -> str:
    error = body.get("error")
    if isinstance(error, dict):
        return f"{error.get('code', 'UNKNOWN')}"
    return "UNKNOWN"


def _writer_chunk(
    delta: dict[str, Any],
    finish_reason: str | None,
    usage: dict[str, int] | None = None,
) -> dict[str, Any]:
    chunk: dict[str, Any] = {
        "id": "live",
        "object": "chat.completion.chunk",
        "created": 1,
        "model": "live",
        "choices": [{"index": 0, "delta": delta, "finish_reason": finish_reason}],
    }
    if usage is not None:
        chunk["usage"] = usage
    return chunk
