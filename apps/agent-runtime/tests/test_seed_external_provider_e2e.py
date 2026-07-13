from __future__ import annotations

import base64
import os
from typing import Any
from urllib.parse import urlparse

import psycopg
import pytest
from cryptography.hazmat.primitives.ciphers.aead import AESGCM
from psycopg import sql
from psycopg.conninfo import conninfo_to_dict, make_conninfo

from mirofish_agents.common.context import AgentContext
from mirofish_agents.llm_quota import PostgresQuotaStore, ProviderQuotaGate
from mirofish_agents.seed.quota_chat_client import SeedQuotaAwareJSONChatClient
from mirofish_agents.seed.sequential_reader import (
    ModuleBindingResolution,
    OpenAICompatibleJSONClient,
    PostgresCredentialProvider,
    PostgresModuleBindingResolver,
)


FACILITY_TENANT_ID = "97111111-1111-4111-8111-111111111111"
FACILITY_PROJECT_ID = "97222222-2222-4222-8222-222222222222"
FACILITY_USER_ID = "97333333-3333-4333-8333-333333333333"
FACILITY_CHANNEL_ID = "97444444-4444-4444-8444-444444444444"
FACILITY_RUN_ID = "97555555-5555-4555-8555-555555555555"
FACILITY_TRACE_ID = "97666666-6666-4666-8666-666666666666"
FACILITY_ROLE = "mirofish_seed_external_facility_live"
FACILITY_ROLE_PASSWORD = "mirofish_seed_external_facility_live_password"
FACILITY_KEY = bytes.fromhex("37" * 32)


def test_seed_external_provider_json_contract_opt_in() -> None:
    base_url = os.environ.get("MIROFISH_SEED_EXTERNAL_PROVIDER_BASE_URL", "").strip()
    model_id = os.environ.get("MIROFISH_SEED_EXTERNAL_PROVIDER_MODEL_ID", "").strip()
    api_key = os.environ.get("MIROFISH_SEED_EXTERNAL_PROVIDER_API_KEY", "").strip()
    if not any((base_url, model_id, api_key)):
        pytest.skip("set Seed external-provider env to run the opt-in provider gate")
    if not all((base_url, model_id, api_key)):
        pytest.fail("Seed external-provider opt-in configuration is incomplete")

    parsed_url = urlparse(base_url)
    if parsed_url.scheme != "https" or not parsed_url.hostname:
        pytest.fail("Seed external-provider base URL must use HTTPS")
    if parsed_url.username or parsed_url.password:
        pytest.fail("Seed external-provider base URL must not contain credentials")

    context = AgentContext(
        tenant_id="91111111-1111-4111-8111-111111111111",
        project_id="92222222-2222-4222-8222-222222222222",
        run_id="93333333-3333-4333-8333-333333333333",
        workflow_type="seed_pipeline",
        actor_user_id="94444444-4444-4444-8444-444444444444",
        trace_id="95555555-5555-4555-8555-555555555555",
        permissions={"seed_pipeline": ["run"]},
    )
    resolution = ModuleBindingResolution(
        tenant_id=context.tenant_id,
        project_id=context.project_id,
        module_key="story_ontology",
        channel_id="96666666-6666-4666-8666-666666666666",
        model_id=model_id,
        provider="external-openai-compatible",
        base_url=base_url,
        credential_ref="external-provider-opt-in",
        supports_json=True,
        settings={"temperature": 0},
    )

    response = OpenAICompatibleJSONClient().complete_json(
        context=context,
        resolution=resolution,
        api_key=api_key,
        messages=[
            {
                "role": "system",
                "content": "Return only one JSON object matching the requested fields.",
            },
            {
                "role": "user",
                "content": 'Return exactly {"seed_external_provider_probe":"ok"}.',
            },
        ],
    )

    assert response.get("seed_external_provider_probe") == "ok"
    assert api_key not in repr(response)


def test_seed_external_provider_facility_binding_quota_usage_trace_opt_in() -> None:
    base_url, model_id, api_key = _external_provider_config()
    admin_url = os.environ.get("MIROFISH_SEED_EXTERNAL_PROVIDER_ADMIN_DATABASE_URL", "").strip()
    if not any((base_url, model_id, api_key, admin_url)):
        pytest.skip("set Seed external-provider Facility env to run the opt-in semantic chain")
    if not all((base_url, model_id, api_key, admin_url)):
        pytest.fail("Seed external-provider Facility opt-in configuration is incomplete")
    _validate_external_url(base_url)

    _prepare_facility(admin_url, base_url=base_url, model_id=model_id, api_key=api_key)
    app_url = _facility_app_url(admin_url)
    context = AgentContext(
        tenant_id=FACILITY_TENANT_ID,
        project_id=FACILITY_PROJECT_ID,
        run_id=FACILITY_RUN_ID,
        workflow_type="seed_pipeline",
        actor_user_id=FACILITY_USER_ID,
        trace_id=FACILITY_TRACE_ID,
        permissions={"seed_pipeline": ["run"]},
    )
    try:
        resolution = PostgresModuleBindingResolver.from_database_url(app_url).resolve_module_binding(
            context=context,
            module_key="story_ontology",
        )
        resolved_key = PostgresCredentialProvider.from_database_url(
            database_url=app_url,
            key_material=FACILITY_KEY.hex(),
        ).resolve_api_key(context=context, credential_ref=resolution.credential_ref)
        client = SeedQuotaAwareJSONChatClient(
            quota_gate=ProviderQuotaGate(PostgresQuotaStore.from_database_url(app_url, ttl_seconds=120)),
        )
        response = client.complete_json(
            context=context,
            resolution=resolution,
            api_key=resolved_key,
            messages=[
                {"role": "system", "content": "Return only one JSON object matching the requested fields."},
                {"role": "user", "content": 'Return exactly {"seed_external_facility_probe":"ok"}.'},
            ],
        )

        assert response.get("seed_external_facility_probe") == "ok"
        assert api_key not in repr(response)
        _assert_facility_evidence(admin_url)
    finally:
        _cleanup_facility(admin_url)


def _external_provider_config() -> tuple[str, str, str]:
    return (
        os.environ.get("MIROFISH_SEED_EXTERNAL_PROVIDER_BASE_URL", "").strip(),
        os.environ.get("MIROFISH_SEED_EXTERNAL_PROVIDER_MODEL_ID", "").strip(),
        os.environ.get("MIROFISH_SEED_EXTERNAL_PROVIDER_API_KEY", "").strip(),
    )


def _validate_external_url(base_url: str) -> None:
    parsed_url = urlparse(base_url)
    if parsed_url.scheme != "https" or not parsed_url.hostname:
        pytest.fail("Seed external-provider base URL must use HTTPS")
    if parsed_url.username or parsed_url.password:
        pytest.fail("Seed external-provider base URL must not contain credentials")
    if parsed_url.hostname in {"localhost", "127.0.0.1", "::1"}:
        pytest.fail("Seed external-provider Facility base URL must be non-local")


def _credential_envelope(api_key: str) -> str:
    iv = os.urandom(12)
    encrypted = AESGCM(FACILITY_KEY).encrypt(iv, api_key.encode("utf-8"), None)
    ciphertext, auth_tag = encrypted[:-16], encrypted[-16:]
    return ":".join([
        "aes-256-gcm",
        "v1",
        base64.b64encode(iv).decode("ascii"),
        base64.b64encode(auth_tag).decode("ascii"),
        base64.b64encode(ciphertext).decode("ascii"),
    ])


def _prepare_facility(admin_url: str, *, base_url: str, model_id: str, api_key: str) -> None:
    with psycopg.connect(admin_url, autocommit=True) as connection:
        with connection.cursor() as cursor:
            _ensure_facility_role(cursor)
            cursor.execute("DELETE FROM tenants WHERE tenant_id = %s", (FACILITY_TENANT_ID,))
            cursor.execute("DELETE FROM users WHERE user_id = %s", (FACILITY_USER_ID,))
            cursor.execute(
                "INSERT INTO users (user_id, email, display_name) VALUES (%s, 'seed-external-facility@example.test', 'Seed External Facility')",
                (FACILITY_USER_ID,),
            )
            cursor.execute(
                "INSERT INTO tenants (tenant_id, slug, name, tenant_type) VALUES (%s, 'seed-external-facility', 'Seed External Facility', 'organization')",
                (FACILITY_TENANT_ID,),
            )
            cursor.execute(
                "INSERT INTO tenant_memberships (tenant_id, user_id, role) VALUES (%s, %s, 'owner')",
                (FACILITY_TENANT_ID, FACILITY_USER_ID),
            )
            cursor.execute(
                "INSERT INTO projects (tenant_id, project_id, title, created_by) VALUES (%s, %s, 'Seed External Facility', %s)",
                (FACILITY_TENANT_ID, FACILITY_PROJECT_ID, FACILITY_USER_ID),
            )
            cursor.execute(
                """INSERT INTO workflow_runs (tenant_id, run_id, workflow_type, project_id, status, started_by)
                   VALUES (%s, %s, 'seed_pipeline', %s, 'running', %s)""",
                (FACILITY_TENANT_ID, FACILITY_RUN_ID, FACILITY_PROJECT_ID, FACILITY_USER_ID),
            )
            cursor.execute(
                """INSERT INTO llm_channels (
                     tenant_id, channel_id, name, provider, base_url, encrypted_api_key,
                     max_concurrency, enabled
                   ) VALUES (%s, %s, 'Seed External Facility', 'external-openai-compatible', %s, %s, 1, true)""",
                (FACILITY_TENANT_ID, FACILITY_CHANNEL_ID, base_url, _credential_envelope(api_key)),
            )
            cursor.execute(
                """INSERT INTO llm_models (
                     tenant_id, channel_id, model_id, context_window, supports_json,
                     input_cost, output_cost, enabled
                   ) VALUES (%s, %s, %s, 8192, true, 1, 2, true)""",
                (FACILITY_TENANT_ID, FACILITY_CHANNEL_ID, model_id),
            )
            cursor.execute(
                """INSERT INTO llm_module_bindings (
                     tenant_id, project_id, module_key, channel_id, model_id, settings_jsonb, updated_by
                   ) VALUES (%s, %s, 'story_ontology', %s, %s, '{"temperature":0,"max_tokens":256,"max_concurrency":1}'::jsonb, %s)""",
                (FACILITY_TENANT_ID, FACILITY_PROJECT_ID, FACILITY_CHANNEL_ID, model_id, FACILITY_USER_ID),
            )
            cursor.executemany(
                """INSERT INTO llm_quota_policies (
                     tenant_id, scope_type, project_id, module_key, token_limit,
                     cost_limit_micros, concurrency_limit, period_seconds, enabled, updated_by
                   ) VALUES (%s, %s, %s, %s, %s, %s, %s, 3600, true, %s)""",
                [
                    (FACILITY_TENANT_ID, "tenant", None, None, 50000, 100000, 4, FACILITY_USER_ID),
                    (FACILITY_TENANT_ID, "project", FACILITY_PROJECT_ID, None, 25000, 50000, 2, FACILITY_USER_ID),
                    (FACILITY_TENANT_ID, "module", FACILITY_PROJECT_ID, "story_ontology", 10000, 25000, 1, FACILITY_USER_ID),
                ],
            )


def _ensure_facility_role(cursor: Any) -> None:
    cursor.execute("SELECT 1 FROM pg_roles WHERE rolname = %s", (FACILITY_ROLE,))
    if cursor.fetchone() is None:
        cursor.execute(
            sql.SQL("CREATE ROLE {} LOGIN PASSWORD {} IN ROLE mirofish_app").format(
                sql.Identifier(FACILITY_ROLE), sql.Literal(FACILITY_ROLE_PASSWORD)
            )
        )
    else:
        cursor.execute(
            sql.SQL("ALTER ROLE {} WITH LOGIN PASSWORD {}").format(
                sql.Identifier(FACILITY_ROLE), sql.Literal(FACILITY_ROLE_PASSWORD)
            )
        )
    cursor.execute(sql.SQL("GRANT mirofish_app TO {}").format(sql.Identifier(FACILITY_ROLE)))


def _facility_app_url(admin_url: str) -> str:
    parts = conninfo_to_dict(admin_url)
    parts["user"] = FACILITY_ROLE
    parts["password"] = FACILITY_ROLE_PASSWORD
    return make_conninfo(**parts)


def _assert_facility_evidence(admin_url: str) -> None:
    with psycopg.connect(admin_url) as connection:
        reservation = connection.execute(
            """SELECT provider_call_id, status, actual_prompt_tokens, actual_completion_tokens
               FROM llm_quota_reservations WHERE tenant_id = %s AND run_id = %s""",
            (FACILITY_TENANT_ID, FACILITY_RUN_ID),
        ).fetchone()
        assert reservation is not None
        assert reservation[0].startswith("llm:")
        assert reservation[1] == "finalized"
        assert reservation[2] >= 0 and reservation[3] >= 0
        assert connection.execute(
            "SELECT count(*) FROM usage_events WHERE tenant_id = %s AND run_id = %s",
            (FACILITY_TENANT_ID, FACILITY_RUN_ID),
        ).fetchone()[0] == 2
        assert connection.execute(
            """SELECT count(*) FROM llm_activity
               WHERE tenant_id = %s AND run_id = %s AND status = 'completed'
                 AND error_jsonb->>'provider_call_id' = %s""",
            (FACILITY_TENANT_ID, FACILITY_RUN_ID, reservation[0]),
        ).fetchone()[0] == 1
        trace = connection.execute(
            """SELECT redaction_level, payload_jsonb->>'provider_call_id'
               FROM agent_trace_events
               WHERE tenant_id = %s AND trace_id = %s AND event_type = 'llm.provider.response'""",
            (FACILITY_TENANT_ID, FACILITY_TRACE_ID),
        ).fetchone()
        assert trace == ("full", reservation[0])


def _cleanup_facility(admin_url: str) -> None:
    with psycopg.connect(admin_url, autocommit=True) as connection:
        connection.execute("DELETE FROM tenants WHERE tenant_id = %s", (FACILITY_TENANT_ID,))
        connection.execute("DELETE FROM users WHERE user_id = %s", (FACILITY_USER_ID,))
