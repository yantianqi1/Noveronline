from __future__ import annotations

import base64
import json
import os
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Any

import psycopg
import pytest
from cryptography.hazmat.primitives.ciphers.aead import AESGCM
from psycopg.rows import dict_row

from mirofish_agents.common.context import AgentContext
from mirofish_agents.seed.sequential_reader import LLMFacilityError
from mirofish_agents.temporal.assets import ASSET_REINDEX_MODULE_KEY, PostgresAssetReindexer, asset_reindex_activity


TENANT_A = "91000000-0000-4000-8000-000000000001"
TENANT_B = "91000000-0000-4000-8000-000000000002"
PROJECT_A = "92000000-0000-4000-8000-000000000001"
PROJECT_B = "92000000-0000-4000-8000-000000000002"
USER_A = "93000000-0000-4000-8000-000000000001"
CHANNEL_A = "94000000-0000-4000-8000-000000000001"
ASSET_MOON = "95000000-0000-4000-8000-000000000001"
ASSET_FIRE = "95000000-0000-4000-8000-000000000002"
ASSET_DISABLED = "95000000-0000-4000-8000-000000000003"
ASSET_FOREIGN = "95000000-0000-4000-8000-000000000004"
RUN_ID = "96000000-0000-4000-8000-000000000001"
RETRY_RUN_ID = "96000000-0000-4000-8000-000000000002"
NO_POLICY_RUN_ID = "96000000-0000-4000-8000-000000000003"
KEY = bytes.fromhex("11" * 32)


def _required_live_urls() -> tuple[str, str]:
    admin_url = os.environ.get("MIROFISH_ASSET_SEARCH_LIVE_ADMIN_DATABASE_URL", "").strip()
    app_url = os.environ.get("MIROFISH_ASSET_SEARCH_LIVE_DATABASE_URL", "").strip()
    if not admin_url or not app_url:
        pytest.skip("asset search live PostgreSQL URLs are not configured")
    return admin_url, app_url


def _credential_envelope(value: str) -> str:
    iv = bytes.fromhex("22" * 12)
    encrypted = AESGCM(KEY).encrypt(iv, value.encode("utf-8"), None)
    ciphertext, tag = encrypted[:-16], encrypted[-16:]
    return ":".join(
        [
            "aes-256-gcm",
            "v1",
            base64.b64encode(iv).decode("ascii"),
            base64.b64encode(tag).decode("ascii"),
            base64.b64encode(ciphertext).decode("ascii"),
        ]
    )


class EmbeddingProviderState:
    def __init__(self, *, admin_url: str) -> None:
        self.admin_url = admin_url
        self.calls = 0
        self.mutate_source_on_next_call = False

    def embeddings(self, inputs: list[str]) -> list[list[float]]:
        self.calls += 1
        if self.mutate_source_on_next_call:
            self.mutate_source_on_next_call = False
            with psycopg.connect(self.admin_url) as connection:
                connection.execute(
                    """UPDATE assets
                       SET title = 'Moon rule changed during reindex',
                           updated_at = updated_at + interval '1 second'
                       WHERE tenant_id = %s AND asset_id = %s""",
                    (TENANT_A, ASSET_MOON),
                )
        vectors: list[list[float]] = []
        for text in inputs:
            lowered = text.lower()
            if "moon" in lowered:
                vectors.append([1.0, 0.0, 0.0])
            elif "fire" in lowered:
                vectors.append([0.0, 1.0, 0.0])
            else:
                vectors.append([0.0, 0.0, 1.0])
        return vectors


def _provider_server(state: EmbeddingProviderState) -> tuple[ThreadingHTTPServer, threading.Thread]:
    class Handler(BaseHTTPRequestHandler):
        def do_POST(self) -> None:  # noqa: N802 - BaseHTTPRequestHandler API
            if self.path != "/v1/embeddings" or self.headers.get("Authorization") != "Bearer live-provider-key":
                self.send_response(401)
                self.end_headers()
                return
            body = json.loads(self.rfile.read(int(self.headers.get("Content-Length", "0"))).decode("utf-8"))
            inputs = body.get("input")
            if body.get("model") != "live-embedding-model" or not isinstance(inputs, list):
                self.send_response(400)
                self.end_headers()
                return
            vectors = state.embeddings(inputs)
            response = json.dumps(
                {
                    "data": [{"index": index, "embedding": vector} for index, vector in enumerate(vectors)],
                    "usage": {"prompt_tokens": 20, "total_tokens": 20},
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


def _seed_live_data(admin_url: str, provider_base_url: str) -> None:
    with psycopg.connect(admin_url) as connection:
        connection.execute("DELETE FROM tenants WHERE tenant_id IN (%s, %s)", (TENANT_A, TENANT_B))
        connection.execute("DELETE FROM users WHERE user_id = %s", (USER_A,))
        connection.execute(
            "INSERT INTO users (user_id, email, display_name) VALUES (%s, %s, %s)",
            (USER_A, "asset-search-live@example.invalid", "Asset Search Live"),
        )
        with connection.cursor() as cursor:
            cursor.executemany(
                "INSERT INTO tenants (tenant_id, slug, name, tenant_type) VALUES (%s, %s, %s, 'organization')",
                [
                    (TENANT_A, "asset-search-live-a", "Asset Search Live A"),
                    (TENANT_B, "asset-search-live-b", "Asset Search Live B"),
                ],
            )
            cursor.executemany(
                "INSERT INTO projects (tenant_id, project_id, title, created_by) VALUES (%s, %s, %s, %s)",
                [
                    (TENANT_A, PROJECT_A, "Asset Search Project A", USER_A),
                    (TENANT_B, PROJECT_B, "Asset Search Project B", USER_A),
                ],
            )
            cursor.executemany(
                """INSERT INTO assets (
                 tenant_id, asset_id, project_id, scope, asset_type, category, lifecycle,
                 title, summary, content_text, source_kind, source_ref, enabled, pinned, created_by
               ) VALUES (%s, %s, %s, 'project', 'world_rule', 'world', %s, %s, %s, %s, 'manual', %s, %s, %s, %s)""",
                [
                    (TENANT_A, ASSET_MOON, PROJECT_A, "canon", "Moon rule", "Moon summary", "Moon private full body", "moon", True, True, USER_A),
                    (TENANT_A, ASSET_FIRE, PROJECT_A, "material", "Fire rule", "Fire summary", "Fire private full body", "fire", True, False, USER_A),
                    (TENANT_A, ASSET_DISABLED, PROJECT_A, "canon", "Disabled rule", "Disabled summary", "Disabled private body", "disabled", False, False, USER_A),
                    (TENANT_B, ASSET_FOREIGN, PROJECT_B, "canon", "Foreign rule", "Foreign summary", "Foreign private body", "foreign", True, False, USER_A),
                ],
            )
        connection.execute(
            """INSERT INTO llm_channels (
                 tenant_id, channel_id, name, provider, base_url, encrypted_api_key,
                 max_concurrency, enabled
               ) VALUES (%s, %s, 'Asset Search Embeddings', 'openai-compatible', %s, %s, 2, true)""",
            (TENANT_A, CHANNEL_A, provider_base_url, _credential_envelope("live-provider-key")),
        )
        connection.execute(
            """INSERT INTO llm_models (
                 tenant_id, channel_id, model_id, context_window, supports_json,
                 input_cost, output_cost
               ) VALUES (%s, %s, 'live-embedding-model', 4096, false, 1, 0)""",
            (TENANT_A, CHANNEL_A),
        )
        connection.execute(
            """INSERT INTO llm_module_bindings (
                 tenant_id, project_id, module_key, channel_id, model_id, settings_jsonb, updated_by
               ) VALUES (%s, %s, %s, %s, 'live-embedding-model', '{"embedding_dimensions":3}'::jsonb, %s)""",
            (TENANT_A, PROJECT_A, ASSET_REINDEX_MODULE_KEY, CHANNEL_A, USER_A),
        )
        connection.execute(
            """INSERT INTO llm_quota_policies (
                 tenant_id, scope_type, project_id, module_key, token_limit,
                 cost_limit_micros, concurrency_limit, period_seconds, enabled, updated_by
               ) VALUES (%s, 'module', %s, %s, 50000, 50000, 1, 3600, true, %s)""",
            (TENANT_A, PROJECT_A, ASSET_REINDEX_MODULE_KEY, USER_A),
        )
        with connection.cursor() as cursor:
            cursor.executemany(
                """INSERT INTO workflow_runs (
                     tenant_id, run_id, workflow_type, project_id, status, started_by
                   ) VALUES (%s, %s, 'asset_reindex', %s, 'queued', %s)""",
                [
                    (TENANT_A, RUN_ID, PROJECT_A, USER_A),
                    (TENANT_A, RETRY_RUN_ID, PROJECT_A, USER_A),
                    (TENANT_A, NO_POLICY_RUN_ID, PROJECT_A, USER_A),
                ],
            )


def _context(run_id: str = RUN_ID) -> AgentContext:
    return AgentContext(
        tenant_id=TENANT_A,
        project_id=PROJECT_A,
        run_id=run_id,
        workflow_type="asset_reindex",
        actor_user_id=USER_A,
        module_key=ASSET_REINDEX_MODULE_KEY,
        trace_id="97000000-0000-4000-8000-000000000001",
        permissions={ASSET_REINDEX_MODULE_KEY: ["run"]},
    )


def _index_snapshot(admin_url: str) -> dict[str, Any]:
    with psycopg.connect(admin_url, row_factory=dict_row) as connection:
        keyword_rows = connection.execute(
            """SELECT source_ref, title, body
               FROM global_search_index
               WHERE tenant_id = %s AND project_id = %s AND source = 'asset'
               ORDER BY source_ref""",
            (TENANT_A, PROJECT_A),
        ).fetchall()
        embedding_rows = connection.execute(
            """SELECT asset_id::text, embedding_model, dimensions, embedding::text, content_sha256
               FROM asset_embeddings
               WHERE tenant_id = %s AND project_id = %s
               ORDER BY asset_id""",
            (TENANT_A, PROJECT_A),
        ).fetchall()
    return {"keyword": keyword_rows, "embeddings": embedding_rows}


def test_asset_hybrid_reindex_live_provider_app_role_isolation_idempotency_and_rollback(monkeypatch: pytest.MonkeyPatch) -> None:
    admin_url, app_url = _required_live_urls()
    state = EmbeddingProviderState(admin_url=admin_url)
    server, thread = _provider_server(state)
    try:
        provider_base_url = f"http://127.0.0.1:{server.server_address[1]}/v1"
        _seed_live_data(admin_url, provider_base_url)
        monkeypatch.setenv("LLM_CREDENTIAL_ENCRYPTION_KEY", KEY.hex())
        monkeypatch.setenv("DATABASE_URL", app_url)
        reindexer = PostgresAssetReindexer.from_database_url(app_url)

        first = asset_reindex_activity(
            {
                "context": _context().model_dump(),
                "scope": "project",
                "mode": "hybrid",
                "options": {},
            },
            asset_reindexer=reindexer,
        )
        assert first["status"] == "completed", first.get("error")
        assert first["workflow_status_persisted"] is True
        assert first["stage_event_persisted"] is True
        assert first["asset_count"] == 2
        assert first["search_document_count"] == 2
        assert first["embedding_count"] == 2
        assert first["embedding_model"] == "live-embedding-model"
        first_snapshot = _index_snapshot(admin_url)
        assert {row["source_ref"] for row in first_snapshot["keyword"]} == {ASSET_MOON, ASSET_FIRE}
        assert {row["asset_id"] for row in first_snapshot["embeddings"]} == {ASSET_MOON, ASSET_FIRE}
        with psycopg.connect(admin_url, row_factory=dict_row) as connection:
            workflow_row = connection.execute(
                """SELECT status, progress, result_jsonb, error_code
                   FROM workflow_runs WHERE tenant_id = %s AND run_id = %s""",
                (TENANT_A, RUN_ID),
            ).fetchone()
            event_count = connection.execute(
                "SELECT count(*) AS count FROM workflow_events WHERE tenant_id = %s AND run_id = %s",
                (TENANT_A, RUN_ID),
            ).fetchone()["count"]
        assert workflow_row["status"] == "completed"
        assert workflow_row["progress"] == 100
        assert workflow_row["result_jsonb"]["embedding_count"] == 2
        assert workflow_row["error_code"] is None
        assert event_count == 1

        second = reindexer.reindex(context=_context(), scope="project", mode="hybrid", options={})
        assert second["embedding_count"] == 2
        assert _index_snapshot(admin_url) == first_snapshot
        assert state.calls == 1
        with psycopg.connect(admin_url) as connection:
            usage_rows = connection.execute(
                """SELECT usage_type, quantity::bigint
                   FROM usage_events WHERE tenant_id = %s AND run_id = %s
                   ORDER BY usage_type""",
                (TENANT_A, RUN_ID),
            ).fetchall()
        assert usage_rows == [("llm_cost_micros", 20), ("llm_tokens", 20)]

        with psycopg.connect(app_url) as connection:
            connection.execute("SELECT app_set_tenant_context(%s::uuid, %s::uuid, false)", (TENANT_A, USER_A))
            foreign_count = connection.execute(
                "SELECT count(*) FROM asset_embeddings WHERE project_id = %s",
                (PROJECT_B,),
            ).fetchone()[0]
            disabled_count = connection.execute(
                "SELECT count(*) FROM asset_embeddings WHERE asset_id = %s",
                (ASSET_DISABLED,),
            ).fetchone()[0]
        assert foreign_count == 0
        assert disabled_count == 0

        state.mutate_source_on_next_call = True
        with pytest.raises(LLMFacilityError) as exc_info:
            reindexer.reindex(context=_context(RETRY_RUN_ID), scope="project", mode="hybrid", options={})
        assert exc_info.value.code == "ASSET_REINDEX_SOURCE_CHANGED"
        assert _index_snapshot(admin_url) == first_snapshot
        assert state.calls == 2

        with psycopg.connect(admin_url) as connection:
            connection.execute("UPDATE llm_quota_policies SET enabled = false WHERE tenant_id = %s", (TENANT_A,))
        with pytest.raises(LLMFacilityError) as exc_info:
            reindexer.reindex(context=_context(NO_POLICY_RUN_ID), scope="project", mode="hybrid", options={})
        assert exc_info.value.code == "LLM_QUOTA_POLICY_UNAVAILABLE"
        assert state.calls == 2
    finally:
        server.shutdown()
        thread.join(timeout=5)
        server.server_close()
        with psycopg.connect(admin_url) as connection:
            connection.execute("DELETE FROM tenants WHERE tenant_id IN (%s, %s)", (TENANT_A, TENANT_B))
            connection.execute("DELETE FROM users WHERE user_id = %s", (USER_A,))
