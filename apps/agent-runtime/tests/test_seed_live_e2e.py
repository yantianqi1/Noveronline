from __future__ import annotations

import asyncio
import base64
import hashlib
import json
import os
import socket
import subprocess
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen
from uuid import UUID

import psycopg
import pytest
from cryptography.hazmat.primitives.ciphers.aead import AESGCM
from psycopg import sql
from psycopg.conninfo import conninfo_to_dict, make_conninfo
from psycopg.rows import dict_row
from temporalio.client import Client
from temporalio.worker import Worker

from mirofish_agents.temporal.seed import (
    SeedPipelineWorkflow,
    S3CompatibleObjectStore,
    agent_profile_activity,
    archive_candidate_activity,
    entity_resolution_activity,
    finalize_seed_activity,
    global_aggregation_activity,
    ontology_activity,
    parse_file_activity,
    seed_pipeline_activity,
    segment_text_activity,
    sequential_reading_activity,
    run_seed_workflow_locally,
)


ROOT = Path(__file__).resolve().parents[3]
MIGRATION_SQL = ROOT / "infra" / "postgres" / "migrations" / "0001_core_saas.sql"
APP_ROLE = "mirofish_seed_live_app"
APP_PASSWORD = "mirofish_seed_live_password"
TENANT_ID = "71111111-1111-1111-1111-111111111111"
USER_ID = "72222222-2222-2222-2222-222222222222"
PROJECT_ID = "73333333-3333-3333-3333-333333333333"
RUN_ID = "74444444-4444-4444-4444-444444444444"
SOURCE_FILE_ID = "75555555-5555-5555-5555-555555555555"
UPLOAD_ID = "76666666-6666-6666-6666-666666666666"
SOURCE_OBJECT_KEY = "projects/live-seed/source-files/upload-1/book.txt"
CHANNEL_ID = "77777777-7777-7777-7777-777777777777"
SEGMENT_ID = "78888888-8888-8888-8888-888888888888"
SEGMENT_ID_2 = "79999999-9999-9999-9999-999999999999"
KEY_MATERIAL = "000102030405060708090a0b0c0d0e0f101112131415161718191a1b1c1d1e1f"


def test_seed_live_go_api_upload_complete_temporal_worker_parse_segment_e2e(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    asyncio.run(_run_seed_live_go_api_upload_complete_temporal_worker_parse_segment_e2e(monkeypatch))


async def _run_seed_live_go_api_upload_complete_temporal_worker_parse_segment_e2e(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    admin_url = _live_database_url()
    temporal_address = _live_temporal_address()
    temporal_namespace = os.environ.get("MIROFISH_SEED_LIVE_TEMPORAL_NAMESPACE", "default").strip() or "default"
    storage_env = _live_object_storage_env()
    object_store = _object_store_from_env(storage_env)
    source_text = "第一章 雨夜\n雨声压住脚步。\n\n第二章 破晓\n光落在窗沿。\n"
    source_bytes = source_text.encode("utf-8")
    source_sha256 = hashlib.sha256(source_bytes).hexdigest()
    _prepare_live_database_foundation(admin_url)
    app_url = _app_database_url(admin_url)
    task_queue = f"seed-live-e2e-{os.getpid()}-{int(time.time() * 1000)}"

    monkeypatch.setenv("DATABASE_URL", app_url)
    for key, value in storage_env.items():
        monkeypatch.setenv(key, value)
    client = await Client.connect(temporal_address, namespace=temporal_namespace)
    with _start_live_go_api(app_url, temporal_address, temporal_namespace, task_queue, storage_env) as api:
        async with _seed_worker(client, task_queue):
            run_id, source_file_id, persisted, public_events = await asyncio.to_thread(
                _drive_live_go_api_seed_run,
                api,
                admin_url,
                source_bytes,
                source_sha256,
            )
            assert persisted["source_files"] == [{"file_id": source_file_id, "parse_status": "parsed"}]
            assert persisted["project_text_artifacts"] == [
                {
                    "source_file_id": source_file_id,
                    "artifact_type": "extracted_text",
                    "char_count": len(source_text),
                    "line_count": len(source_text.splitlines()),
                    "sha256": source_sha256,
                }
            ]
            assert persisted["text_segments"] == [
                {"segment_order": 0, "chapter_guess": "第一章", "title_guess": "雨夜"},
                {"segment_order": 1, "chapter_guess": "第二章", "title_guess": "破晓"},
            ]
            _assert_seed_object_readback(
                object_store,
                persisted,
                expected_artifact_bytes=source_bytes,
                expected_segment_texts=["第一章 雨夜\n雨声压住脚步。", "第二章 破晓\n光落在窗沿。"],
            )
            event_types = [event["event_type"] for event in persisted["workflow_events"]]
            assert "workflow.queued" in event_types
            assert event_types.count("seed.stage.completed") >= 2
            assert persisted["workflow_runs"][0]["status"] == "failed"
            assert persisted["workflow_runs"][0]["error_code"] == "LLM_MODULE_UNBOUND"
            public_event_body = json.dumps(public_events, ensure_ascii=False, sort_keys=True)
            for forbidden in (
                "object_key",
                "source_object_key",
                "artifact_object_key",
                "segment_object_key",
                "source_sha256",
                "sha256",
                "hash",
                "checksum",
                source_sha256,
                "雨声压住脚步",
                "光落在窗沿",
                "prompt",
                "credential_ref",
                "api_key",
                "draft",
                "manuscript",
            ):
                assert forbidden not in public_event_body


def _drive_live_go_api_seed_run(
    api: str,
    admin_url: str,
    source_bytes: bytes,
    source_sha256: str,
) -> tuple[str, str, dict[str, list[dict[str, Any]]], dict[str, Any]]:
    headers = {
        "X-Tenant-Id": TENANT_ID,
        "X-User-Id": USER_ID,
        "Content-Type": "application/json",
    }
    upload = _api_json(
        "POST",
        f"{api}/v1/projects/{PROJECT_ID}/uploads",
        headers,
        {
            "filename": "book.txt",
            "mime_type": "text/plain; charset=utf-8",
            "size_bytes": len(source_bytes),
            "sha256": source_sha256,
            "purpose": "seed",
            "tenant_id": "00000000-0000-0000-0000-000000000000",
        },
    )
    upload_id = upload["upload_id"]
    source_file_id = upload["file_id"]
    _api_bytes(
        "PUT",
        f"{api}/v1/uploads/{upload_id}/object",
        {"X-Tenant-Id": TENANT_ID, "X-User-Id": USER_ID},
        source_bytes,
    )
    completed = _api_json(
        "POST",
        f"{api}/v1/uploads/{upload_id}/complete",
        headers,
        {},
    )
    assert completed["parse_status"] == "uploaded"
    run = _api_json(
        "POST",
        f"{api}/v1/projects/{PROJECT_ID}/seed-runs",
        headers,
        {
            "tenant_id": "00000000-0000-0000-0000-000000000000",
            "upload_id": upload_id,
            "options": {
                "language": "zh-CN",
                "prompt": "must not enter the Temporal payload",
                "credential_ref": "hidden",
            },
        },
    )
    assert run["status"] == "queued"
    run_id = run["run_id"]
    persisted = _wait_for_seed_live_parse_segment_rows(admin_url, run_id, source_file_id)
    public_events = _api_json(
        "GET",
        f"{api}/v1/seed-runs/{run_id}/events",
        {"X-Tenant-Id": TENANT_ID},
        None,
    )
    return run_id, source_file_id, persisted, public_events


def test_seed_live_postgres_app_role_parse_segment_persists_public_metadata(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    admin_url = _live_database_url()
    source_text = "第一章 雨夜\n雨声压住脚步。\n\n第二章 破晓\n光落在窗沿。\n"
    source_bytes = source_text.encode("utf-8")
    source_sha256 = hashlib.sha256(source_bytes).hexdigest()
    _prepare_live_database(admin_url, source_bytes)
    app_url = _app_database_url(admin_url)
    monkeypatch.setenv("DATABASE_URL", app_url)
    object_store = _InMemoryObjectStore({SOURCE_OBJECT_KEY: source_bytes})

    result = run_seed_workflow_locally(
        {
            "context": {
                "tenant_id": TENANT_ID,
                "project_id": PROJECT_ID,
                "run_id": RUN_ID,
                "workflow_type": "seed_pipeline",
                "actor_user_id": USER_ID,
                "trace_id": "trace-live-seed-parse-segment",
                "permissions": {"seed_pipeline": ["run"]},
            },
            "upload_id": UPLOAD_ID,
            "source_file_id": SOURCE_FILE_ID,
            "source_object_key": SOURCE_OBJECT_KEY,
            "source_mime_type": "text/plain",
            "options": {"language": "zh-CN"},
        },
        source_object_store=object_store,
        artifact_object_store=object_store,
    )

    assert result["status"] == "completed"
    assert result["stage"] == "segment_text"
    assert result["next_stage"] == "sequential_reading"
    assert result["segment_count"] == 2
    persisted = _read_seed_live_rows(admin_url)
    assert persisted["source_files"] == [{"file_id": SOURCE_FILE_ID, "parse_status": "parsed"}]
    assert persisted["project_text_artifacts"] == [
        {
            "source_file_id": SOURCE_FILE_ID,
            "artifact_type": "extracted_text",
            "char_count": len(source_text),
            "line_count": len(source_text.splitlines()),
            "sha256": source_sha256,
        }
    ]
    assert persisted["text_segments"] == [
        {"segment_order": 0, "chapter_guess": "第一章", "title_guess": "雨夜"},
        {"segment_order": 1, "chapter_guess": "第二章", "title_guess": "破晓"},
    ]
    assert persisted["workflow_events"] == [
        {
            "event_type": "seed.stage.pending",
            "payload_jsonb": {
                "stage": "parse_file",
                "status": "pending",
                "activity": "seed_pipeline_activity",
                "upload_id": UPLOAD_ID,
            },
        },
        {
            "event_type": "seed.stage.completed",
            "payload_jsonb": {
                "stage": "parse_file",
                "status": "completed",
                "activity": "parse_file_activity",
                "source_file_id": SOURCE_FILE_ID,
                "artifact_type": "extracted_text",
                "char_count": len(source_text),
                "line_count": len(source_text.splitlines()),
            },
        },
        {
            "event_type": "seed.stage.pending",
            "payload_jsonb": {
                "stage": "segment_text",
                "status": "pending",
                "activity": "segment_text_activity",
                "source_file_id": SOURCE_FILE_ID,
                "artifact_type": "extracted_text",
            },
        },
        {
            "event_type": "seed.stage.completed",
            "payload_jsonb": {
                "stage": "segment_text",
                "status": "completed",
                "activity": "segment_text_activity",
                "source_file_id": SOURCE_FILE_ID,
                "segment_count": 2,
            },
        },
    ]
    public_event_body = json.dumps(persisted["workflow_events"], ensure_ascii=False, sort_keys=True)
    for forbidden in (
        SOURCE_OBJECT_KEY,
        "source_object_key",
        "artifact_object_key",
        "segment_object_key",
        "object_key",
        "source_sha256",
        "sha256",
        "hash",
        "checksum",
        source_sha256,
        "雨声压住脚步",
        "光落在窗沿",
        "api_key",
        "credential_ref",
        "draft",
        "manuscript",
    ):
        assert forbidden not in public_event_body


def test_seed_live_minio_postgres_app_role_parse_segment_reads_and_writes_real_objects(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    admin_url = _live_database_url()
    object_store = _live_object_store()
    source_text = "第一章 雨夜\n雨声压住脚步。\n\n第二章 破晓\n光落在窗沿。\n"
    source_bytes = source_text.encode("utf-8")
    source_sha256 = hashlib.sha256(source_bytes).hexdigest()
    _prepare_live_database(admin_url, source_bytes)
    object_store.write_bytes(SOURCE_OBJECT_KEY, source_bytes, "text/plain; charset=utf-8")
    app_url = _app_database_url(admin_url)
    monkeypatch.setenv("DATABASE_URL", app_url)

    result = run_seed_workflow_locally(
        {
            "context": {
                "tenant_id": TENANT_ID,
                "project_id": PROJECT_ID,
                "run_id": RUN_ID,
                "workflow_type": "seed_pipeline",
                "actor_user_id": USER_ID,
                "trace_id": "trace-live-seed-minio-parse-segment",
                "permissions": {"seed_pipeline": ["run"]},
            },
            "upload_id": UPLOAD_ID,
            "source_file_id": SOURCE_FILE_ID,
            "source_object_key": SOURCE_OBJECT_KEY,
            "source_mime_type": "text/plain",
            "options": {"language": "zh-CN"},
        },
        source_object_store=object_store,
        artifact_object_store=object_store,
    )

    assert result["status"] == "completed"
    artifact_object_key = f"projects/{PROJECT_ID}/seed-runs/{RUN_ID}/extracted/{SOURCE_FILE_ID}.txt"
    assert object_store.read_bytes(artifact_object_key) == source_bytes
    assert [
        object_store.read_bytes(segment["object_key"]).decode("utf-8")
        for segment in result["segments"]
    ] == ["第一章 雨夜\n雨声压住脚步。", "第二章 破晓\n光落在窗沿。"]
    persisted = _read_seed_live_rows(admin_url)
    assert persisted["source_files"] == [{"file_id": SOURCE_FILE_ID, "parse_status": "parsed"}]
    public_event_body = json.dumps(persisted["workflow_events"], ensure_ascii=False, sort_keys=True)
    for forbidden in (
        SOURCE_OBJECT_KEY,
        artifact_object_key,
        "source_object_key",
        "artifact_object_key",
        "segment_object_key",
        "object_key",
        "source_sha256",
        "sha256",
        "hash",
        "checksum",
        source_sha256,
        "雨声压住脚步",
        "api_key",
        "credential_ref",
        "draft",
        "manuscript",
    ):
        assert forbidden not in public_event_body


def test_seed_agent_profile_live_postgres_provider_chain_persists_snapshot_and_public_event(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    admin_url = _live_database_url()
    with _LiveAgentProfileProvider() as provider:
        _prepare_live_agent_profile_database(admin_url, provider.base_url)
        app_url = _app_database_url(admin_url)
        monkeypatch.setenv("DATABASE_URL", app_url)
        monkeypatch.setenv("LLM_CREDENTIAL_ENCRYPTION_KEY", KEY_MATERIAL)

        result = agent_profile_activity(
            {
                "context": {
                    "tenant_id": TENANT_ID,
                    "project_id": PROJECT_ID,
                    "run_id": RUN_ID,
                    "workflow_type": "seed_pipeline",
                    "actor_user_id": USER_ID,
                    "trace_id": "trace-live-seed-agent-profile",
                    "permissions": {"seed_pipeline": ["run"]},
                }
            }
        )

    assert result["status"] == "completed"
    assert result["stage"] == "agent_profiles"
    assert result["module_key"] == "character_agent_profile"
    assert result["profile_count"] == 1
    assert result["memory_seed_count"] == 1
    assert result["relationship_view_count"] == 1
    assert len(provider.requests) == 1
    assert _header(provider.requests[0]["headers"], "Authorization") == "Bearer sk-live-seed-profile"
    assert _header(provider.requests[0]["headers"], "X-MiroFish-Run-Id") == RUN_ID
    provider_body = json.dumps(provider.requests[0]["body"], ensure_ascii=False, sort_keys=True)
    assert "source_context" in provider_body
    assert "林舟" in provider_body
    for forbidden in (
        "credential_ref",
        "source_object_key",
        "object_key",
        "private_notes",
        "provider_raw_body",
        "api_key",
        "sk-provider-leak",
        "raw manuscript sentence",
        "draft",
        "manuscript",
    ):
        assert forbidden not in provider_body

    persisted = _read_seed_agent_profile_live_rows(admin_url)
    assert len(persisted["seed_agent_profile_snapshots"]) == 1
    snapshot = persisted["seed_agent_profile_snapshots"][0]
    assert snapshot["module_key"] == "character_agent_profile"
    assert snapshot["model_id"] == "model-seed-profile-live"
    assert snapshot["profile_count"] == 1
    assert snapshot["memory_seed_count"] == 1
    assert snapshot["relationship_view_count"] == 1
    assert snapshot["profiles_jsonb"]["profiles"] == [{"name": "林舟", "voice": "quiet resolve"}]
    assert persisted["workflow_events"] == [
        {
            "event_type": "seed.stage.completed",
            "payload_jsonb": {
                "stage": "agent_profiles",
                "status": "completed",
                "activity": "agent_profile_activity",
                "module_key": "character_agent_profile",
                "profile_snapshot_id": result["profile_snapshot_id"],
                "profile_count": 1,
                "memory_seed_count": 1,
                "relationship_view_count": 1,
                "model_id": "model-seed-profile-live",
            },
        }
    ]
    encoded = json.dumps({"result": result, "persisted": persisted}, ensure_ascii=False, default=str)
    for forbidden in (
        "sk-live-seed-profile",
        "sk-provider-leak",
        "secret-ref",
        "credential_ref",
        "provider_raw_body",
        "raw manuscript sentence",
        "private prompt",
        "draft",
        "manuscript",
    ):
        assert forbidden not in encoded


def test_seed_story_ontology_live_postgres_provider_persists_snapshot_and_public_event(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    admin_url = _live_database_url()
    with _LiveOntologyProvider() as provider:
        _prepare_live_ontology_database(admin_url, provider.base_url)
        app_url = _app_database_url(admin_url)
        monkeypatch.setenv("DATABASE_URL", app_url)
        monkeypatch.setenv("LLM_CREDENTIAL_ENCRYPTION_KEY", KEY_MATERIAL)

        result = ontology_activity(
            {
                "context": {
                    "tenant_id": TENANT_ID,
                    "project_id": PROJECT_ID,
                    "run_id": RUN_ID,
                    "workflow_type": "seed_pipeline",
                    "actor_user_id": USER_ID,
                    "trace_id": "trace-live-seed-story-ontology",
                    "permissions": {"seed_pipeline": ["run"]},
                }
            }
        )
        repeat_result = ontology_activity(
            {
                "context": {
                    "tenant_id": TENANT_ID,
                    "project_id": PROJECT_ID,
                    "run_id": RUN_ID,
                    "workflow_type": "seed_pipeline",
                    "actor_user_id": USER_ID,
                    "trace_id": "trace-live-seed-story-ontology-repeat",
                    "permissions": {"seed_pipeline": ["run"]},
                }
            }
        )

    assert result == {
        "tenant_id": TENANT_ID,
        "project_id": PROJECT_ID,
        "run_id": RUN_ID,
        "workflow_type": "seed_pipeline",
        "upload_id": None,
        "status": "completed",
        "stage": "story_ontology",
        "next_stage": "entity_resolution",
        "module_key": "story_ontology",
        "ontology_snapshot_id": result["ontology_snapshot_id"],
        "entity_type_count": 2,
        "relationship_type_count": 1,
        "world_rule_type_count": 1,
        "stage_event_persisted": True,
        "model_id": "model-seed-ontology-live",
    }
    assert repeat_result["status"] == "completed"
    assert repeat_result["ontology_snapshot_id"] == result["ontology_snapshot_id"]
    assert len(provider.requests) == 2
    assert _header(provider.requests[0]["headers"], "Authorization") == "Bearer sk-live-seed-ontology"
    assert _header(provider.requests[0]["headers"], "X-MiroFish-Run-Id") == RUN_ID
    assert _header(provider.requests[0]["headers"], "X-MiroFish-Module-Key") == "story_ontology"
    provider_body = json.dumps(provider.requests[0]["body"], ensure_ascii=False, sort_keys=True)
    assert "model-seed-ontology-live" in provider_body
    assert "story_ontology" in provider_body
    for forbidden in (
        "credential_ref",
        "sk-live-seed-ontology",
        "api_key",
        "provider_response",
        "raw manuscript sentence",
        "draft",
        "manuscript",
    ):
        assert forbidden not in provider_body

    persisted = _read_seed_ontology_live_rows(admin_url)
    assert persisted["seed_ontology_snapshots"] == [
        {
            "module_key": "story_ontology",
            "model_id": "model-seed-ontology-live",
            "entity_type_count": 2,
            "relationship_type_count": 1,
            "world_rule_type_count": 1,
            "ontology_jsonb": {
                "entity_types": [{"name": "character"}, {"name": "organization"}],
                "relationship_types": [{"name": "ally"}],
                "world_rule_types": [{"name": "ritual_law"}],
                "private_notes": "allowed only in private ontology snapshot",
            },
        }
    ]
    assert persisted["workflow_events"] == [
        {
            "event_type": "seed.stage.completed",
            "payload_jsonb": {
                "stage": "story_ontology",
                "status": "completed",
                "activity": "ontology_activity",
                "module_key": "story_ontology",
                "ontology_snapshot_id": result["ontology_snapshot_id"],
                "entity_type_count": 2,
                "relationship_type_count": 1,
                "world_rule_type_count": 1,
                "model_id": "model-seed-ontology-live",
            },
        },
        {
            "event_type": "seed.stage.completed",
            "payload_jsonb": {
                "stage": "story_ontology",
                "status": "completed",
                "activity": "ontology_activity",
                "module_key": "story_ontology",
                "ontology_snapshot_id": result["ontology_snapshot_id"],
                "entity_type_count": 2,
                "relationship_type_count": 1,
                "world_rule_type_count": 1,
                "model_id": "model-seed-ontology-live",
            },
        },
    ]
    public_event_body = json.dumps(persisted["workflow_events"], ensure_ascii=False, sort_keys=True)
    encoded = json.dumps({"result": result, "events": persisted["workflow_events"]}, ensure_ascii=False, sort_keys=True)
    for forbidden in (
        "sk-live-seed-ontology",
        "sk-provider-leak",
        "secret-ref",
        "credential_ref",
        "provider_response",
        "raw_body",
        "raw manuscript sentence",
        "private prompt",
        "draft",
        "manuscript",
        "allowed only in private ontology snapshot",
    ):
        assert forbidden not in public_event_body
        assert forbidden not in encoded


def test_seed_entity_resolution_live_postgres_provider_upserts_snapshot_and_public_event(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    admin_url = _live_database_url()
    with _LiveEntityResolutionProvider() as provider:
        _prepare_live_entity_resolution_database(admin_url, provider.base_url)
        app_url = _app_database_url(admin_url)
        monkeypatch.setenv("DATABASE_URL", app_url)
        monkeypatch.setenv("LLM_CREDENTIAL_ENCRYPTION_KEY", KEY_MATERIAL)

        result = entity_resolution_activity(
            {
                "context": {
                    "tenant_id": TENANT_ID,
                    "project_id": PROJECT_ID,
                    "run_id": RUN_ID,
                    "workflow_type": "seed_pipeline",
                    "actor_user_id": USER_ID,
                    "trace_id": "trace-live-seed-entity-resolution",
                    "permissions": {"seed_pipeline": ["run"]},
                }
            }
        )
        repeat_result = entity_resolution_activity(
            {
                "context": {
                    "tenant_id": TENANT_ID,
                    "project_id": PROJECT_ID,
                    "run_id": RUN_ID,
                    "workflow_type": "seed_pipeline",
                    "actor_user_id": USER_ID,
                    "trace_id": "trace-live-seed-entity-resolution-repeat",
                    "permissions": {"seed_pipeline": ["run"]},
                }
            }
        )

    assert result == {
        "tenant_id": TENANT_ID,
        "project_id": PROJECT_ID,
        "run_id": RUN_ID,
        "workflow_type": "seed_pipeline",
        "upload_id": None,
        "status": "completed",
        "stage": "entity_resolution",
        "next_stage": "agent_profiles",
        "module_key": "entity_resolution",
        "resolution_snapshot_id": result["resolution_snapshot_id"],
        "merged_entity_count": 1,
        "alias_count": 2,
        "conflict_count": 1,
        "stage_event_persisted": True,
        "model_id": "model-seed-entity-resolution-live",
    }
    assert repeat_result["status"] == "completed"
    assert repeat_result["resolution_snapshot_id"] == result["resolution_snapshot_id"]
    assert len(provider.requests) == 2
    for recorded_request in provider.requests:
        assert _header(recorded_request["headers"], "Authorization") == "Bearer sk-live-seed-entity-resolution"
        assert _header(recorded_request["headers"], "X-MiroFish-Tenant-Id") == TENANT_ID
        assert _header(recorded_request["headers"], "X-MiroFish-Project-Id") == PROJECT_ID
        assert _header(recorded_request["headers"], "X-MiroFish-Run-Id") == RUN_ID
        assert _header(recorded_request["headers"], "X-MiroFish-Module-Key") == "entity_resolution"
    provider_body = json.dumps(provider.requests[0]["body"], ensure_ascii=False, sort_keys=True)
    assert "model-seed-entity-resolution-live" in provider_body
    assert "entity_resolution" in provider_body
    for forbidden in (
        "credential_ref",
        "sk-live-seed-entity-resolution",
        "api_key",
        "provider_response",
        "raw_body",
        "raw manuscript sentence",
        "draft",
        "manuscript",
    ):
        assert forbidden not in provider_body

    persisted = _read_seed_entity_resolution_live_rows(admin_url)
    assert persisted["workflow_runs"] == [{"status": "running", "progress": 70}]
    assert persisted["seed_entity_resolution_snapshots"] == [
        {
            "module_key": "entity_resolution",
            "model_id": "model-seed-entity-resolution-live",
            "merged_entity_count": 1,
            "alias_count": 2,
            "conflict_count": 1,
            "resolution_jsonb": {
                "merged_entities": [
                    {
                        "canonical_name": "林舟",
                        "entity_type": "character",
                        "aliases": ["小舟", "雨港守夜人"],
                    }
                ],
                "aliases": [
                    {"alias": "小舟", "canonical_name": "林舟"},
                    {"alias": "雨港守夜人", "canonical_name": "林舟"},
                ],
                "conflicts": [{"name": "林舟", "reason": "章节称谓不一致"}],
                "private_notes": "allowed only in private resolution snapshot",
            },
        }
    ]
    assert persisted["workflow_events"] == [
        {
            "event_type": "seed.stage.completed",
            "payload_jsonb": {
                "stage": "entity_resolution",
                "status": "completed",
                "activity": "entity_resolution_activity",
                "module_key": "entity_resolution",
                "resolution_snapshot_id": result["resolution_snapshot_id"],
                "merged_entity_count": 1,
                "alias_count": 2,
                "conflict_count": 1,
                "model_id": "model-seed-entity-resolution-live",
            },
        },
        {
            "event_type": "seed.stage.completed",
            "payload_jsonb": {
                "stage": "entity_resolution",
                "status": "completed",
                "activity": "entity_resolution_activity",
                "module_key": "entity_resolution",
                "resolution_snapshot_id": result["resolution_snapshot_id"],
                "merged_entity_count": 1,
                "alias_count": 2,
                "conflict_count": 1,
                "model_id": "model-seed-entity-resolution-live",
            },
        },
    ]
    public_event_body = json.dumps(persisted["workflow_events"], ensure_ascii=False, sort_keys=True)
    encoded = json.dumps(
        {"result": result, "repeat_result": repeat_result, "events": persisted["workflow_events"]},
        ensure_ascii=False,
        sort_keys=True,
    )
    for forbidden in (
        "prompt",
        "sk-live-seed-entity-resolution",
        "sk-provider-leak",
        "secret-ref",
        "credential_ref",
        "provider_response",
        "provider_raw_body",
        "raw_body",
        "object_key",
        "source_object_key",
        "artifact_object_key",
        "segment_object_key",
        "raw manuscript sentence",
        "private prompt",
        "draft",
        "manuscript",
        "allowed only in private resolution snapshot",
    ):
        assert forbidden not in public_event_body
        assert forbidden not in encoded


def test_seed_sequential_reading_live_postgres_provider_object_store_persists_notes_and_public_event(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    admin_url = _live_database_url()
    storage_env = _live_object_storage_env()
    object_store = _object_store_from_env(storage_env)
    segment_object_key_1 = f"projects/{PROJECT_ID}/seed-runs/{RUN_ID}/segments/0000.txt"
    segment_object_key_2 = f"projects/{PROJECT_ID}/seed-runs/{RUN_ID}/segments/0001.txt"
    segment_text_1 = "第一章 雨夜\n雨声压住脚步。"
    segment_text_2 = "第二章 破晓\n光落在窗沿。"

    with _LiveSequentialReadingProvider() as provider:
        _prepare_live_sequential_reading_database(
            admin_url,
            provider.base_url,
            segment_object_key_1=segment_object_key_1,
            segment_object_key_2=segment_object_key_2,
        )
        object_store.write_bytes(segment_object_key_1, segment_text_1.encode("utf-8"), "text/plain; charset=utf-8")
        object_store.write_bytes(segment_object_key_2, segment_text_2.encode("utf-8"), "text/plain; charset=utf-8")
        app_url = _app_database_url(admin_url)
        monkeypatch.setenv("DATABASE_URL", app_url)
        monkeypatch.setenv("LLM_CREDENTIAL_ENCRYPTION_KEY", KEY_MATERIAL)
        for key, value in storage_env.items():
            monkeypatch.setenv(key, value)

        result = sequential_reading_activity(
            {
                "context": {
                    "tenant_id": TENANT_ID,
                    "project_id": PROJECT_ID,
                    "run_id": RUN_ID,
                    "workflow_type": "seed_pipeline",
                    "actor_user_id": USER_ID,
                    "trace_id": "trace-live-seed-sequential-reading",
                    "permissions": {"seed_pipeline": ["run"]},
                },
                "segments": [
                    {
                        "segment_id": SEGMENT_ID,
                        "segment_order": 0,
                        "chapter_guess": "第一章",
                        "title_guess": "雨夜",
                        "object_key": segment_object_key_1,
                    },
                    {
                        "segment_id": SEGMENT_ID_2,
                        "segment_order": 1,
                        "chapter_guess": "第二章",
                        "title_guess": "破晓",
                        "object_key": segment_object_key_2,
                    },
                ],
            }
        )

    assert result == {
        "tenant_id": TENANT_ID,
        "project_id": PROJECT_ID,
        "run_id": RUN_ID,
        "workflow_type": "seed_pipeline",
        "upload_id": None,
        "status": "completed",
        "stage": "sequential_reading",
        "next_stage": "persist_runtime_facts",
        "module_key": "sequential_reading",
        "segment_count": 2,
        "note_count": 2,
        "stage_event_persisted": True,
    }
    assert len(provider.requests) == 1
    assert _header(provider.requests[0]["headers"], "Authorization") == "Bearer sk-live-seed-sequential"
    assert _header(provider.requests[0]["headers"], "X-MiroFish-Run-Id") == RUN_ID
    provider_body = json.dumps(provider.requests[0]["body"], ensure_ascii=False, sort_keys=True)
    assert "model-seed-sequential-live" in provider_body
    assert "雨声压住脚步" in provider_body
    assert "光落在窗沿" in provider_body
    for forbidden in ("credential_ref", "sk-live-seed-sequential", "api_key"):
        assert forbidden not in provider_body

    persisted = _read_seed_sequential_reading_live_rows(admin_url)
    assert persisted["text_segments"] == [
        {"segment_id": SEGMENT_ID, "segment_order": 0, "chapter_guess": "第一章", "title_guess": "雨夜"},
        {"segment_id": SEGMENT_ID_2, "segment_order": 1, "chapter_guess": "第二章", "title_guess": "破晓"},
    ]
    assert persisted["reading_passes"] == [
        {
            "pass_id": persisted["reading_passes"][0]["pass_id"],
            "pass_type": "sequential_reading",
            "status": "completed",
            "module_key": "sequential_reading",
            "model_id": "model-seed-sequential-live",
            "metadata_jsonb": {"segment_count": 2},
        }
    ]
    UUID(persisted["reading_passes"][0]["pass_id"])
    assert persisted["reading_segment_notes"] == [
        {
            "segment_id": SEGMENT_ID,
            "pass_id": persisted["reading_passes"][0]["pass_id"],
            "summary": "林舟在雨夜听见脚步。",
            "payload_jsonb": {
                "characters": [{"name": "林舟", "role": "protagonist"}],
                "organizations": [],
                "relationships": [],
                "plot_threads": [{"title": "雨港秘密", "status": "opened"}],
                "world_rules": [],
                "events": [{"summary": "雨声压住脚步"}],
                "consistency_notes": [],
            },
        },
        {
            "segment_id": SEGMENT_ID_2,
            "pass_id": persisted["reading_passes"][0]["pass_id"],
            "summary": "陆晚在破晓抵达窗前。",
            "payload_jsonb": {
                "characters": [{"name": "陆晚", "role": "witness"}],
                "organizations": [],
                "relationships": [],
                "plot_threads": [],
                "world_rules": [{"rule": "破晓会显露昨夜痕迹"}],
                "events": [{"summary": "光落在窗沿"}],
                "consistency_notes": [],
            },
        },
    ]
    assert persisted["workflow_events"] == [
        {
            "event_type": "seed.stage.completed",
            "payload_jsonb": {
                "stage": "sequential_reading",
                "status": "completed",
                "activity": "sequential_reading_activity",
                "module_key": "sequential_reading",
                "segment_count": 2,
                "note_count": 2,
                "model_id": "model-seed-sequential-live",
            },
        }
    ]
    public_event_body = json.dumps(persisted["workflow_events"], ensure_ascii=False, sort_keys=True)
    for forbidden in (
        segment_object_key_1,
        segment_object_key_2,
        "object_key",
        "segment_object_key",
        "source_object_key",
        "artifact_object_key",
        "provider_response",
        "prompt",
        "credential_ref",
        "sk-live-seed-sequential",
        "api_key",
        segment_text_1,
        segment_text_2,
        "draft",
        "manuscript",
    ):
        assert forbidden not in public_event_body


def test_seed_global_aggregation_live_postgres_provider_persists_sanitized_snapshot_and_public_event(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    admin_url = _live_database_url()
    with _LiveGlobalAggregationProvider() as provider:
        _prepare_live_global_aggregation_database(admin_url, provider.base_url)
        app_url = _app_database_url(admin_url)
        monkeypatch.setenv("DATABASE_URL", app_url)
        monkeypatch.setenv("LLM_CREDENTIAL_ENCRYPTION_KEY", KEY_MATERIAL)

        result = global_aggregation_activity(
            {
                "context": {
                    "tenant_id": TENANT_ID,
                    "project_id": PROJECT_ID,
                    "run_id": RUN_ID,
                    "workflow_type": "seed_pipeline",
                    "actor_user_id": USER_ID,
                    "trace_id": "trace-live-seed-global-aggregation",
                    "permissions": {"seed_pipeline": ["run"]},
                }
            }
        )

    assert result == {
        "tenant_id": TENANT_ID,
        "project_id": PROJECT_ID,
        "run_id": RUN_ID,
        "workflow_type": "seed_pipeline",
        "upload_id": None,
        "status": "completed",
        "stage": "global_aggregation",
        "next_stage": "story_ontology",
        "module_key": "anchor_point_summary",
        "segment_count": 2,
        "summary_count": 2,
        "stage_event_persisted": True,
        "model_id": "model-seed-global-aggregation-live",
        "seed_analysis_snapshot_id": result["seed_analysis_snapshot_id"],
    }
    assert len(provider.requests) == 1
    assert provider.requests[0]["path"] == "/v1/chat/completions"
    assert _header(provider.requests[0]["headers"], "Authorization") == "Bearer sk-live-seed-global-aggregation"
    assert _header(provider.requests[0]["headers"], "X-MiroFish-Tenant-Id") == TENANT_ID
    assert _header(provider.requests[0]["headers"], "X-MiroFish-Project-Id") == PROJECT_ID
    assert _header(provider.requests[0]["headers"], "X-MiroFish-Run-Id") == RUN_ID
    assert _header(provider.requests[0]["headers"], "X-MiroFish-Module-Key") == "anchor_point_summary"
    provider_body = json.dumps(provider.requests[0]["body"], ensure_ascii=False, sort_keys=True)
    assert "model-seed-global-aggregation-live" in provider_body
    assert "雨夜公共摘要" in provider_body
    assert "破晓公共摘要" in provider_body
    assert '"fact_counts"' in provider_body
    assert '"entities"' in provider_body
    assert '"relationships"' in provider_body
    for forbidden in _global_aggregation_live_forbidden_public_markers():
        assert forbidden not in provider_body

    persisted = _read_seed_global_aggregation_live_rows(admin_url)
    assert persisted["seed_analysis_snapshots"] == [
        {
            "module_key": "anchor_point_summary",
            "model_id": "model-seed-global-aggregation-live",
            "summary_count": 2,
            "segment_count": 2,
            "analysis_jsonb": {
                "overview": "雨港卷进入追踪压力。",
                "timeline_summary": "雨夜发现脚步，破晓确认痕迹。",
                "anchors": [{"title": "雨夜锚点", "summary": "林舟开始追踪。"}],
            },
        }
    ]
    assert persisted["workflow_events"] == [
        {
            "event_type": "seed.stage.completed",
            "payload_jsonb": {
                "stage": "global_aggregation",
                "status": "completed",
                "activity": "global_aggregation_activity",
                "module_key": "anchor_point_summary",
                "segment_count": 2,
                "summary_count": 2,
                "model_id": "model-seed-global-aggregation-live",
                "seed_analysis_snapshot_id": result["seed_analysis_snapshot_id"],
            },
        }
    ]
    public_body = json.dumps({"result": result, "events": persisted["workflow_events"]}, ensure_ascii=False)
    for forbidden in _global_aggregation_live_forbidden_public_markers():
        assert forbidden not in public_body
    snapshot_body = json.dumps(persisted["seed_analysis_snapshots"], ensure_ascii=False)
    for forbidden in (
        "prompt",
        "raw_content",
        "raw_body",
        "api_key",
        "credential_ref",
        "provider_response",
        "PRIVATE_AGGREGATE_TEXT",
        "PRIVATE_AGGREGATE_EVIDENCE",
        "draft",
        "manuscript",
    ):
        assert forbidden not in snapshot_body


def test_seed_archive_candidate_live_postgres_provider_persists_candidate_assets_memories_and_public_event(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    admin_url = _live_database_url()
    with _LiveArchiveCandidateProvider() as provider:
        _prepare_live_archive_candidate_database(admin_url, provider.base_url)
        app_url = _app_database_url(admin_url)
        monkeypatch.setenv("DATABASE_URL", app_url)
        monkeypatch.setenv("LLM_CREDENTIAL_ENCRYPTION_KEY", KEY_MATERIAL)

        result = archive_candidate_activity(
            {
                "context": {
                    "tenant_id": TENANT_ID,
                    "project_id": PROJECT_ID,
                    "run_id": RUN_ID,
                    "workflow_type": "seed_pipeline",
                    "actor_user_id": USER_ID,
                    "trace_id": "trace-live-seed-archive-candidate",
                    "permissions": {"seed_pipeline": ["run"]},
                }
            }
        )

    assert result == {
        "tenant_id": TENANT_ID,
        "project_id": PROJECT_ID,
        "run_id": RUN_ID,
        "workflow_type": "seed_pipeline",
        "upload_id": None,
        "status": "completed",
        "stage": "archive_candidates",
        "next_stage": "index_assets",
        "module_key": "narrative_archives",
        "model_id": "model-seed-archive-live",
        "archive_candidate_batch_id": f"narrative-archives:{RUN_ID}",
        "candidate_count": 2,
        "archive_entity_candidate_count": 1,
        "memory_candidate_count": 1,
        "stage_event_persisted": True,
    }
    assert len(provider.requests) == 1
    assert provider.requests[0]["path"] == "/v1/chat/completions"
    assert _header(provider.requests[0]["headers"], "Authorization") == "Bearer sk-live-seed-archive"
    assert _header(provider.requests[0]["headers"], "X-MiroFish-Tenant-Id") == TENANT_ID
    assert _header(provider.requests[0]["headers"], "X-MiroFish-Project-Id") == PROJECT_ID
    assert _header(provider.requests[0]["headers"], "X-MiroFish-Run-Id") == RUN_ID
    assert _header(provider.requests[0]["headers"], "X-MiroFish-Module-Key") == "narrative_archives"
    provider_body = json.dumps(provider.requests[0]["body"], ensure_ascii=False, sort_keys=True)
    assert "model-seed-archive-live" in provider_body
    assert "narrative_archives" in provider_body
    for forbidden in (
        "credential_ref",
        "sk-live-seed-archive",
        "api_key",
        "provider_response",
        "raw_body",
        "PRIVATE_ARCHIVE_PROMPT",
        "PRIVATE_ARCHIVE_DRAFT",
        "PRIVATE_ARCHIVE_MANUSCRIPT",
    ):
        assert forbidden not in provider_body

    persisted = _read_seed_archive_candidate_live_rows(admin_url)
    assert persisted["assets"] == [
        {
            "asset_id": persisted["assets"][0]["asset_id"],
            "asset_type": "archive_entity",
            "category": "character",
            "lifecycle": "candidate",
            "title": "阿澜档案",
            "summary": "雨夜谈判中的核心人物。",
            "content_text": "雨夜谈判中的核心人物。",
            "payload_jsonb": {
                "entity_name": "阿澜",
                "entity_type": "character",
                "core_drive": "守住秘密",
                "stable_detail": "只保留可进入档案候选的结构化摘要。",
                "model_id": "model-seed-archive-live",
            },
            "tags_jsonb": ["character", "rain"],
            "source_kind": "narrative_archives",
            "source_ref": f"narrative-archives:{RUN_ID}:archive:1",
        }
    ]
    assert persisted["archive_memories"] == [
        {
            "memory_id": persisted["archive_memories"][0]["memory_id"],
            "asset_id": persisted["assets"][0]["asset_id"],
            "memory_type": "motivation",
            "status": "candidate",
            "summary": "她用沉默拖住谈判节奏。",
            "body_text": "PRIVATE_ARCHIVE_MEMORY_BODY is allowed only in archive_memories.body_text.",
            "payload_jsonb": {"visibility": "writer_context", "confidence": "medium"},
            "source_kind": "narrative_archives",
            "source_ref": f"narrative-archives:{RUN_ID}:archive:1:memory:1",
        }
    ]
    assert persisted["archive_memory_events"] == [
        {
            "event_type": "memory.candidate.generated",
            "status": "candidate",
            "payload_jsonb": {
                "source_kind": "narrative_archives",
                "source_ref": f"narrative-archives:{RUN_ID}:archive:1:memory:1",
                "archive_candidate_batch_id": f"narrative-archives:{RUN_ID}",
                "memory_type": "motivation",
            },
        }
    ]
    assert persisted["workflow_events"] == [
        {
            "event_type": "seed.stage.completed",
            "payload_jsonb": {
                "stage": "archive_candidates",
                "status": "completed",
                "activity": "archive_candidate_activity",
                "module_key": "narrative_archives",
                "model_id": "model-seed-archive-live",
                "archive_candidate_batch_id": f"narrative-archives:{RUN_ID}",
                "candidate_count": 2,
                "archive_entity_candidate_count": 1,
                "memory_candidate_count": 1,
            },
        }
    ]
    public_body = json.dumps(
        {"result": result, "workflow_events": persisted["workflow_events"]},
        ensure_ascii=False,
        sort_keys=True,
    )
    for forbidden in _archive_candidate_live_forbidden_public_markers():
        assert forbidden not in public_body


def test_seed_finalize_live_postgres_readiness_updates_snapshot_and_workflow_status(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    admin_url = _live_database_url()
    _prepare_live_finalize_database(admin_url)
    app_url = _app_database_url(admin_url)
    monkeypatch.setenv("DATABASE_URL", app_url)

    result = finalize_seed_activity(
        {
            "context": {
                "tenant_id": TENANT_ID,
                "project_id": PROJECT_ID,
                "run_id": RUN_ID,
                "workflow_type": "seed_pipeline",
                "actor_user_id": USER_ID,
                "trace_id": "trace-live-seed-finalize",
                "permissions": {"seed_pipeline": ["run"]},
            }
        }
    )

    assert result == {
        "tenant_id": TENANT_ID,
        "project_id": PROJECT_ID,
        "run_id": RUN_ID,
        "workflow_type": "seed_pipeline",
        "upload_id": None,
        "status": "completed",
        "stage": "finalize",
        "project_readiness_snapshot_id": result["project_readiness_snapshot_id"],
        "ready_asset_count": 2,
        "ready_entity_count": 2,
        "ready_relationship_count": 1,
        "ready_world_rule_count": 1,
        "stage_event_persisted": True,
        "workflow_status_persisted": True,
    }

    persisted = _read_seed_finalize_live_rows(admin_url)
    assert persisted["project_readiness_snapshots"] == [
        {
            "project_readiness_snapshot_id": result["project_readiness_snapshot_id"],
            "run_id": RUN_ID,
            "ready_asset_count": 2,
            "ready_entity_count": 2,
            "ready_relationship_count": 1,
            "ready_world_rule_count": 1,
            "metadata_jsonb": {},
        }
    ]
    assert persisted["workflow_runs"] == [
        {
            "status": "completed",
            "progress": 100,
            "message": "seed pipeline completed",
            "error_code": None,
            "error_message": None,
            "result_jsonb": {
                "stage": "finalize",
                "project_readiness_snapshot_id": result["project_readiness_snapshot_id"],
                "ready_asset_count": 2,
                "ready_entity_count": 2,
                "ready_relationship_count": 1,
                "ready_world_rule_count": 1,
            },
        }
    ]
    assert persisted["workflow_events"] == [
        {
            "event_type": "seed.stage.completed",
            "payload_jsonb": {
                "stage": "finalize",
                "status": "completed",
                "activity": "finalize_seed_activity",
                "project_readiness_snapshot_id": result["project_readiness_snapshot_id"],
                "ready_asset_count": 2,
                "ready_entity_count": 2,
                "ready_relationship_count": 1,
                "ready_world_rule_count": 1,
            },
        }
    ]
    public_body = json.dumps(
        {
            "result": result,
            "workflow_runs": persisted["workflow_runs"],
            "workflow_events": persisted["workflow_events"],
        },
        ensure_ascii=False,
        sort_keys=True,
    )
    for forbidden in _finalize_live_forbidden_public_markers():
        assert forbidden not in public_body


class _InMemoryObjectStore:
    def __init__(self, objects: dict[str, bytes]) -> None:
        self.objects = dict(objects)

    def read_bytes(self, object_key: str) -> bytes:
        return self.objects[object_key]

    def write_bytes(self, object_key: str, data: bytes, content_type: str) -> None:
        self.objects[object_key] = data


class _LiveAgentProfileProvider:
    def __init__(self) -> None:
        self.requests: list[dict[str, Any]] = []
        self._server = ThreadingHTTPServer(("127.0.0.1", 0), self._handler())
        self.base_url = f"http://127.0.0.1:{self._server.server_port}/v1"
        self._thread = threading.Thread(target=self._server.serve_forever, daemon=True)

    def __enter__(self) -> "_LiveAgentProfileProvider":
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
                    "agent_profiles": {
                        "profiles": [
                            {
                                "name": "林舟",
                                "voice": "quiet resolve",
                                "provider_raw_body": "must not persist",
                                "api_key": "sk-provider-leak",
                            }
                        ],
                        "memory_seeds": [{"title": "雨港承诺", "summary": "Keeps one promise."}],
                        "relationship_views": [{"name": "林舟 / 陆晚", "summary": "Careful alliance."}],
                    }
                }
                response = {
                    "choices": [{"message": {"content": json.dumps(content, ensure_ascii=False)}}],
                    "usage": {
                        "prompt_tokens": 11,
                        "completion_tokens": 17,
                        "total_tokens": 28,
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


class _LiveSequentialReadingProvider:
    def __init__(self) -> None:
        self.requests: list[dict[str, Any]] = []
        self._server = ThreadingHTTPServer(("127.0.0.1", 0), self._handler())
        self.base_url = f"http://127.0.0.1:{self._server.server_port}/v1"
        self._thread = threading.Thread(target=self._server.serve_forever, daemon=True)

    def __enter__(self) -> "_LiveSequentialReadingProvider":
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
                    "notes": [
                        {
                            "segment_id": SEGMENT_ID,
                            "summary": "林舟在雨夜听见脚步。",
                            "payload_jsonb": {
                                "characters": [{"name": "林舟", "role": "protagonist"}],
                                "organizations": [],
                                "relationships": [],
                                "plot_threads": [{"title": "雨港秘密", "status": "opened"}],
                                "world_rules": [],
                                "events": [{"summary": "雨声压住脚步"}],
                                "consistency_notes": [],
                                "prompt": "must be sanitized",
                                "provider_response": "must be sanitized",
                                "credential_ref": "secret-ref",
                                "api_key": "sk-provider-leak",
                                "draft": "private draft",
                                "manuscript": "private manuscript",
                            },
                        },
                        {
                            "segment_id": SEGMENT_ID_2,
                            "summary": "陆晚在破晓抵达窗前。",
                            "payload_jsonb": {
                                "characters": [{"name": "陆晚", "role": "witness"}],
                                "organizations": [],
                                "relationships": [],
                                "plot_threads": [],
                                "world_rules": [{"rule": "破晓会显露昨夜痕迹"}],
                                "events": [{"summary": "光落在窗沿"}],
                                "consistency_notes": [],
                            },
                        },
                    ]
                }
                response = {
                    "choices": [{"message": {"content": json.dumps(content, ensure_ascii=False)}}],
                    "usage": {
                        "prompt_tokens": 23,
                        "completion_tokens": 31,
                        "total_tokens": 54,
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


class _LiveGlobalAggregationProvider:
    def __init__(self) -> None:
        self.requests: list[dict[str, Any]] = []
        self._server = ThreadingHTTPServer(("127.0.0.1", 0), self._handler())
        self.base_url = f"http://127.0.0.1:{self._server.server_port}/v1"
        self._thread = threading.Thread(target=self._server.serve_forever, daemon=True)

    def __enter__(self) -> "_LiveGlobalAggregationProvider":
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
                    "seed_analysis": {
                        "overview": "雨港卷进入追踪压力。",
                        "timeline_summary": "雨夜发现脚步，破晓确认痕迹。",
                        "anchors": [
                            {
                                "title": "雨夜锚点",
                                "summary": "林舟开始追踪。",
                                "text": "PRIVATE_AGGREGATE_TEXT must not persist",
                                "evidence": "PRIVATE_AGGREGATE_EVIDENCE must not persist",
                                "provider_response": "PRIVATE_AGGREGATE_PROVIDER_RESPONSE must not persist",
                            }
                        ],
                        "prompt": "PRIVATE_AGGREGATE_PROMPT must not persist",
                        "raw_content": "PRIVATE_AGGREGATE_RAW_CONTENT must not persist",
                        "raw_body": "PRIVATE_AGGREGATE_RAW_BODY must not persist",
                        "api_key": "sk-provider-aggregate-leak",
                        "credential_ref": "aggregate-secret-ref",
                        "draft": "PRIVATE_AGGREGATE_DRAFT must not persist",
                        "manuscript": "PRIVATE_AGGREGATE_MANUSCRIPT must not persist",
                    }
                }
                response = {
                    "choices": [{"message": {"content": json.dumps(content, ensure_ascii=False)}}],
                    "usage": {
                        "prompt_tokens": 31,
                        "completion_tokens": 41,
                        "total_tokens": 72,
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


class _LiveOntologyProvider:
    def __init__(self) -> None:
        self.requests: list[dict[str, Any]] = []
        self._server = ThreadingHTTPServer(("127.0.0.1", 0), self._handler())
        self.base_url = f"http://127.0.0.1:{self._server.server_port}/v1"
        self._thread = threading.Thread(target=self._server.serve_forever, daemon=True)

    def __enter__(self) -> "_LiveOntologyProvider":
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
                    "seed_ontology": {
                        "entity_types": [
                            {"name": "character", "text": "must be sanitized"},
                            {"name": "organization", "source_text": "must be sanitized"},
                        ],
                        "relationship_types": [{"name": "ally", "provider_response": "must be sanitized"}],
                        "world_rule_types": [{"name": "ritual_law", "api_key": "sk-provider-leak"}],
                        "private_notes": "allowed only in private ontology snapshot",
                        "prompt": "private prompt",
                        "raw_body": "raw manuscript sentence",
                        "credential_ref": "secret-ref",
                        "draft": "private draft",
                        "manuscript": "private manuscript",
                    }
                }
                response = {
                    "choices": [{"message": {"content": json.dumps(content, ensure_ascii=False)}}],
                    "usage": {
                        "prompt_tokens": 13,
                        "completion_tokens": 19,
                        "total_tokens": 32,
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


class _LiveEntityResolutionProvider:
    def __init__(self) -> None:
        self.requests: list[dict[str, Any]] = []
        self._server = ThreadingHTTPServer(("127.0.0.1", 0), self._handler())
        self.base_url = f"http://127.0.0.1:{self._server.server_port}/v1"
        self._thread = threading.Thread(target=self._server.serve_forever, daemon=True)

    def __enter__(self) -> "_LiveEntityResolutionProvider":
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
                    "entity_resolution": {
                        "merged_entities": [
                            {
                                "canonical_name": "林舟",
                                "entity_type": "character",
                                "aliases": ["小舟", "雨港守夜人"],
                                "object_key": "provider/leaked/object.txt",
                                "text": "must be sanitized",
                                "source_text": "must be sanitized",
                            }
                        ],
                        "aliases": [
                            {
                                "alias": "小舟",
                                "canonical_name": "林舟",
                                "provider_response": "must be sanitized",
                            },
                            {
                                "alias": "雨港守夜人",
                                "canonical_name": "林舟",
                                "api_key": "sk-provider-leak",
                            },
                        ],
                        "conflicts": [{"name": "林舟", "reason": "章节称谓不一致", "raw_body": "raw manuscript sentence"}],
                        "source_object_key": "provider/leaked/source.txt",
                        "artifact_object_key": "provider/leaked/artifact.txt",
                        "segment_object_key": "provider/leaked/segment.txt",
                        "private_notes": "allowed only in private resolution snapshot",
                        "prompt": "private prompt",
                        "credential_ref": "secret-ref",
                        "draft": "private draft",
                        "manuscript": "private manuscript",
                    }
                }
                response = {
                    "choices": [{"message": {"content": json.dumps(content, ensure_ascii=False)}}],
                    "usage": {
                        "prompt_tokens": 17,
                        "completion_tokens": 21,
                        "total_tokens": 38,
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


class _LiveArchiveCandidateProvider:
    def __init__(self) -> None:
        self.requests: list[dict[str, Any]] = []
        self._server = ThreadingHTTPServer(("127.0.0.1", 0), self._handler())
        self.base_url = f"http://127.0.0.1:{self._server.server_port}/v1"
        self._thread = threading.Thread(target=self._server.serve_forever, daemon=True)

    def __enter__(self) -> "_LiveArchiveCandidateProvider":
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
                    "archive_entities": [
                        {
                            "title": "阿澜档案",
                            "summary": "雨夜谈判中的核心人物。",
                            "category": "character",
                            "tags": ["character", "rain", "draft"],
                            "payload": {
                                "entity_name": "阿澜",
                                "entity_type": "character",
                                "core_drive": "守住秘密",
                                "stable_detail": "只保留可进入档案候选的结构化摘要。",
                                "prompt": "PRIVATE_ARCHIVE_PROMPT must not persist",
                                "provider_response": "PRIVATE_PROVIDER_RESPONSE must not persist",
                                "raw_body": "PRIVATE_ARCHIVE_RAW_BODY must not persist",
                                "api_key": "sk-provider-archive-leak",
                                "credential_ref": "secret-ref",
                                "object_key": "projects/leaked/archive/private.txt",
                                "draft": "PRIVATE_ARCHIVE_DRAFT must not persist",
                                "manuscript": "PRIVATE_ARCHIVE_MANUSCRIPT must not persist",
                            },
                            "provider_raw_body": "PRIVATE_PROVIDER_RAW_BODY must not persist",
                            "source_object_key": "projects/leaked/source.txt",
                            "memories": [
                                {
                                    "memory_type": "motivation",
                                    "summary": "她用沉默拖住谈判节奏。",
                                    "body_text": (
                                        "PRIVATE_ARCHIVE_MEMORY_BODY is allowed only in "
                                        "archive_memories.body_text."
                                    ),
                                    "payload": {
                                        "visibility": "writer_context",
                                        "confidence": "medium",
                                        "body_text": "PRIVATE_ARCHIVE_BODY_TEXT_PAYLOAD must not persist",
                                        "raw_body": "PRIVATE_ARCHIVE_MEMORY_RAW_BODY must not persist",
                                        "provider_response": "PRIVATE_MEMORY_PROVIDER_RESPONSE must not persist",
                                        "api_key": "sk-provider-memory-leak",
                                        "credential_ref": "memory-secret-ref",
                                        "object_key": "projects/leaked/archive/memory.txt",
                                        "draft": "PRIVATE_ARCHIVE_MEMORY_DRAFT must not persist",
                                        "manuscript": "PRIVATE_ARCHIVE_MEMORY_MANUSCRIPT must not persist",
                                    },
                                }
                            ],
                        }
                    ],
                    "prompt": "PRIVATE_ARCHIVE_TOP_LEVEL_PROMPT must not persist",
                    "provider_response": "PRIVATE_ARCHIVE_TOP_LEVEL_RESPONSE must not persist",
                    "raw_body": "PRIVATE_ARCHIVE_TOP_LEVEL_RAW_BODY must not persist",
                    "api_key": "sk-provider-top-level-leak",
                    "credential_ref": "top-level-secret-ref",
                    "object_key": "projects/leaked/archive/top-level.txt",
                    "draft": "PRIVATE_ARCHIVE_TOP_LEVEL_DRAFT must not persist",
                    "manuscript": "PRIVATE_ARCHIVE_TOP_LEVEL_MANUSCRIPT must not persist",
                }
                response = {
                    "choices": [{"message": {"content": json.dumps(content, ensure_ascii=False)}}],
                    "usage": {
                        "prompt_tokens": 29,
                        "completion_tokens": 37,
                        "total_tokens": 66,
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
    database_url = os.environ.get("MIROFISH_SEED_LIVE_DATABASE_URL", "").strip()
    if not database_url:
        pytest.skip("set MIROFISH_SEED_LIVE_DATABASE_URL to run opt-in live Seed Postgres E2E tests")
    return database_url


def _live_object_store() -> S3CompatibleObjectStore:
    storage_env = _live_object_storage_env()
    return _object_store_from_env(storage_env)


def _object_store_from_env(storage_env: dict[str, str]) -> S3CompatibleObjectStore:
    return S3CompatibleObjectStore(
        endpoint=storage_env["MIROFISH_OBJECT_STORAGE_ENDPOINT"],
        bucket=storage_env["MIROFISH_OBJECT_STORAGE_BUCKET"],
        access_key=storage_env["MIROFISH_OBJECT_STORAGE_ACCESS_KEY"],
        secret_key=storage_env["MIROFISH_OBJECT_STORAGE_SECRET_KEY"],
        use_ssl=_env_bool("MIROFISH_SEED_LIVE_OBJECT_STORAGE_USE_SSL"),
        region=os.environ.get("MIROFISH_SEED_LIVE_OBJECT_STORAGE_REGION", "us-east-1"),
    )


def _live_object_storage_env() -> dict[str, str]:
    endpoint = os.environ.get("MIROFISH_SEED_LIVE_OBJECT_STORAGE_ENDPOINT", "").strip()
    bucket = os.environ.get("MIROFISH_SEED_LIVE_OBJECT_STORAGE_BUCKET", "").strip()
    access_key = os.environ.get("MIROFISH_SEED_LIVE_OBJECT_STORAGE_ACCESS_KEY", "").strip()
    secret_key = os.environ.get("MIROFISH_SEED_LIVE_OBJECT_STORAGE_SECRET_KEY", "").strip()
    if not endpoint:
        pytest.skip("set MIROFISH_SEED_LIVE_OBJECT_STORAGE_ENDPOINT to run the live Seed MinIO E2E")
    if not bucket or not access_key or not secret_key:
        pytest.skip("set MIROFISH_SEED_LIVE_OBJECT_STORAGE_BUCKET/ACCESS_KEY/SECRET_KEY to run live Seed MinIO E2E")
    return {
        "MIROFISH_OBJECT_STORAGE_ENDPOINT": endpoint,
        "MIROFISH_OBJECT_STORAGE_BUCKET": bucket,
        "MIROFISH_OBJECT_STORAGE_ACCESS_KEY": access_key,
        "MIROFISH_OBJECT_STORAGE_SECRET_KEY": secret_key,
        "MIROFISH_OBJECT_STORAGE_USE_SSL": os.environ.get("MIROFISH_SEED_LIVE_OBJECT_STORAGE_USE_SSL", ""),
    }


def _live_temporal_address() -> str:
    temporal_address = os.environ.get("MIROFISH_SEED_LIVE_TEMPORAL_ADDRESS", "").strip()
    if not temporal_address:
        pytest.skip("set MIROFISH_SEED_LIVE_TEMPORAL_ADDRESS to run the live Seed Temporal handoff E2E")
    return temporal_address


def _env_bool(name: str) -> bool:
    return os.environ.get(name, "").strip().lower() in {"1", "true", "yes", "on"}


def _prepare_live_database(admin_url: str, source_bytes: bytes) -> None:
    _prepare_live_database_foundation(admin_url)
    with psycopg.connect(admin_url, autocommit=True) as connection:
        with connection.cursor() as cursor:
            cursor.execute(
                """INSERT INTO workflow_runs (
                     tenant_id, run_id, workflow_type, project_id, status, progress, started_by
                   )
                   VALUES (%s, %s, 'seed_pipeline', %s, 'queued', 0, %s)""",
                (TENANT_ID, RUN_ID, PROJECT_ID, USER_ID),
            )
            cursor.execute(
                """INSERT INTO source_files (
                     tenant_id, file_id, project_id, upload_id, object_key, filename,
                     mime_type, size_bytes, sha256, purpose, parse_status, created_by
                   )
                   VALUES (%s, %s, %s, %s, %s, 'book.txt', 'text/plain', %s, %s, 'seed', 'parsing', %s)""",
                (
                    TENANT_ID,
                    SOURCE_FILE_ID,
                    PROJECT_ID,
                    UPLOAD_ID,
                    SOURCE_OBJECT_KEY,
                    len(source_bytes),
                    hashlib.sha256(source_bytes).hexdigest(),
                    USER_ID,
                ),
            )


def _prepare_live_agent_profile_database(admin_url: str, provider_base_url: str) -> None:
    _prepare_live_database_foundation(admin_url)
    with psycopg.connect(admin_url, autocommit=True) as connection:
        with connection.cursor() as cursor:
            cursor.execute(
                """INSERT INTO workflow_runs (
                     tenant_id, run_id, workflow_type, project_id, status, progress, started_by
                   )
                   VALUES (%s, %s, 'seed_pipeline', %s, 'running', 80, %s)""",
                (TENANT_ID, RUN_ID, PROJECT_ID, USER_ID),
            )
            cursor.execute(
                """INSERT INTO seed_entity_resolution_snapshots (
                     tenant_id, project_id, run_id, module_key, model_id,
                     resolution_jsonb, merged_entity_count, alias_count, conflict_count
                   )
                   VALUES (
                     %s, %s, %s, 'entity_resolution', 'model-entity-resolution-live',
                     %s::jsonb, 1, 1, 0
                   )""",
                (
                    TENANT_ID,
                    PROJECT_ID,
                    RUN_ID,
                    json.dumps(
                        {
                            "merged_entities": [
                                {
                                    "canonical_name": "林舟",
                                    "entity_type": "character",
                                    "aliases": ["小舟"],
                                    "private_notes": "must not reach provider",
                                    "credential_ref": "secret-ref",
                                }
                            ],
                            "prompt": "private prompt must not reach provider",
                        },
                        ensure_ascii=False,
                    ),
                ),
            )
            cursor.execute(
                """INSERT INTO entities (
                     tenant_id, entity_id, project_id, entity_type, canonical_name,
                     importance, state_summary, source_run_id
                   )
                   VALUES (%s, gen_random_uuid(), %s, 'character', '林舟', 8, '守住雨港秘密。', %s)""",
                (TENANT_ID, PROJECT_ID, RUN_ID),
            )
            cursor.execute(
                """INSERT INTO relationships (
                     tenant_id, relationship_id, project_id, source_entity_name,
                     target_entity_name, relationship_type, summary, source_run_id
                   )
                   VALUES (%s, gen_random_uuid(), %s, '林舟', '陆晚', 'ally', '互相试探。', %s)""",
                (TENANT_ID, PROJECT_ID, RUN_ID),
            )
            cursor.execute(
                """INSERT INTO text_segments (
                     tenant_id, segment_id, project_id, run_id, segment_order,
                     chapter_guess, title_guess, summary
                   )
                   VALUES (%s, %s, %s, %s, 0, '第一章', '雨港', '雨夜相遇。')""",
                (TENANT_ID, SEGMENT_ID, PROJECT_ID, RUN_ID),
            )
            cursor.execute(
                """INSERT INTO segment_summaries (
                     tenant_id, segment_id, project_id, run_id, summary
                   )
                   VALUES (%s, %s, %s, %s, '雨夜相遇。')""",
                (TENANT_ID, SEGMENT_ID, PROJECT_ID, RUN_ID),
            )
            cursor.execute(
                """INSERT INTO llm_channels (
                     tenant_id, channel_id, name, provider, base_url, encrypted_api_key, max_concurrency, enabled
                   )
                   VALUES (%s, %s, 'Seed Profile Live Provider', 'openai-compatible', %s, %s, 1, true)""",
                (TENANT_ID, CHANNEL_ID, provider_base_url, _encrypt_api_key("sk-live-seed-profile")),
            )
            cursor.execute(
                """INSERT INTO llm_models (
                     tenant_id, channel_id, model_id, owned_by, supports_json, supports_tools
                   )
                   VALUES (%s, %s, 'model-seed-profile-live', 'live-provider', true, false)""",
                (TENANT_ID, CHANNEL_ID),
            )
            cursor.execute(
                """INSERT INTO llm_module_bindings (
                     tenant_id, project_id, module_key, channel_id, model_id, settings_jsonb, updated_by
                   )
                   VALUES (%s, %s, 'character_agent_profile', %s, 'model-seed-profile-live', '{"temperature":0.1}'::jsonb, %s)""",
                (TENANT_ID, PROJECT_ID, CHANNEL_ID, USER_ID),
            )


def _prepare_live_ontology_database(admin_url: str, provider_base_url: str) -> None:
    _prepare_live_database_foundation(admin_url)
    with psycopg.connect(admin_url, autocommit=True) as connection:
        with connection.cursor() as cursor:
            cursor.execute(
                """INSERT INTO workflow_runs (
                     tenant_id, run_id, workflow_type, project_id, status, progress, started_by
                   )
                   VALUES (%s, %s, 'seed_pipeline', %s, 'running', 65, %s)""",
                (TENANT_ID, RUN_ID, PROJECT_ID, USER_ID),
            )
            cursor.execute(
                """INSERT INTO llm_channels (
                     tenant_id, channel_id, name, provider, base_url, encrypted_api_key, max_concurrency, enabled
                   )
                   VALUES (%s, %s, 'Seed Ontology Live Provider', 'openai-compatible', %s, %s, 1, true)""",
                (TENANT_ID, CHANNEL_ID, provider_base_url, _encrypt_api_key("sk-live-seed-ontology")),
            )
            cursor.execute(
                """INSERT INTO llm_models (
                     tenant_id, channel_id, model_id, owned_by, supports_json, supports_tools
                   )
                   VALUES (%s, %s, 'model-seed-ontology-live', 'live-provider', true, false)""",
                (TENANT_ID, CHANNEL_ID),
            )
            cursor.execute(
                """INSERT INTO llm_module_bindings (
                     tenant_id, project_id, module_key, channel_id, model_id, settings_jsonb, updated_by
                   )
                   VALUES (%s, %s, 'story_ontology', %s, 'model-seed-ontology-live', '{"temperature":0}'::jsonb, %s)""",
                (TENANT_ID, PROJECT_ID, CHANNEL_ID, USER_ID),
            )


def _prepare_live_entity_resolution_database(admin_url: str, provider_base_url: str) -> None:
    _prepare_live_database_foundation(admin_url)
    with psycopg.connect(admin_url, autocommit=True) as connection:
        with connection.cursor() as cursor:
            cursor.execute(
                """INSERT INTO workflow_runs (
                     tenant_id, run_id, workflow_type, project_id, status, progress, started_by
                   )
                   VALUES (%s, %s, 'seed_pipeline', %s, 'running', 70, %s)""",
                (TENANT_ID, RUN_ID, PROJECT_ID, USER_ID),
            )
            cursor.execute(
                """INSERT INTO llm_channels (
                     tenant_id, channel_id, name, provider, base_url, encrypted_api_key, max_concurrency, enabled
                   )
                   VALUES (%s, %s, 'Seed Entity Resolution Live Provider', 'openai-compatible', %s, %s, 1, true)""",
                (TENANT_ID, CHANNEL_ID, provider_base_url, _encrypt_api_key("sk-live-seed-entity-resolution")),
            )
            cursor.execute(
                """INSERT INTO llm_models (
                     tenant_id, channel_id, model_id, owned_by, supports_json, supports_tools
                   )
                   VALUES (%s, %s, 'model-seed-entity-resolution-live', 'live-provider', true, false)""",
                (TENANT_ID, CHANNEL_ID),
            )
            cursor.execute(
                """INSERT INTO llm_module_bindings (
                     tenant_id, project_id, module_key, channel_id, model_id, settings_jsonb, updated_by
                   )
                   VALUES (%s, %s, 'entity_resolution', %s, 'model-seed-entity-resolution-live', '{"temperature":0}'::jsonb, %s)""",
                (TENANT_ID, PROJECT_ID, CHANNEL_ID, USER_ID),
            )


def _prepare_live_sequential_reading_database(
    admin_url: str,
    provider_base_url: str,
    *,
    segment_object_key_1: str,
    segment_object_key_2: str,
) -> None:
    _prepare_live_database_foundation(admin_url)
    with psycopg.connect(admin_url, autocommit=True) as connection:
        with connection.cursor() as cursor:
            cursor.execute(
                """INSERT INTO workflow_runs (
                     tenant_id, run_id, workflow_type, project_id, status, progress, started_by
                   )
                   VALUES (%s, %s, 'seed_pipeline', %s, 'running', 40, %s)""",
                (TENANT_ID, RUN_ID, PROJECT_ID, USER_ID),
            )
            cursor.execute(
                """INSERT INTO source_files (
                     tenant_id, file_id, project_id, upload_id, object_key, filename,
                     mime_type, size_bytes, sha256, purpose, parse_status, created_by
                   )
                   VALUES (
                     %s, %s, %s, %s, %s, 'book.txt', 'text/plain', 1,
                     repeat('0', 64), 'seed', 'parsed', %s
                   )""",
                (TENANT_ID, SOURCE_FILE_ID, PROJECT_ID, UPLOAD_ID, SOURCE_OBJECT_KEY, USER_ID),
            )
            cursor.execute(
                """INSERT INTO text_segments (
                     tenant_id, segment_id, project_id, run_id, source_file_id,
                     segment_order, chapter_guess, title_guess, object_key
                   )
                   VALUES
                     (%s, %s, %s, %s, %s, 0, '第一章', '雨夜', %s),
                     (%s, %s, %s, %s, %s, 1, '第二章', '破晓', %s)""",
                (
                    TENANT_ID,
                    SEGMENT_ID,
                    PROJECT_ID,
                    RUN_ID,
                    SOURCE_FILE_ID,
                    segment_object_key_1,
                    TENANT_ID,
                    SEGMENT_ID_2,
                    PROJECT_ID,
                    RUN_ID,
                    SOURCE_FILE_ID,
                    segment_object_key_2,
                ),
            )
            cursor.execute(
                """INSERT INTO llm_channels (
                     tenant_id, channel_id, name, provider, base_url, encrypted_api_key, max_concurrency, enabled
                   )
                   VALUES (%s, %s, 'Seed Sequential Live Provider', 'openai-compatible', %s, %s, 1, true)""",
                (TENANT_ID, CHANNEL_ID, provider_base_url, _encrypt_api_key("sk-live-seed-sequential")),
            )
            cursor.execute(
                """INSERT INTO llm_models (
                     tenant_id, channel_id, model_id, owned_by, supports_json, supports_tools
                   )
                   VALUES (%s, %s, 'model-seed-sequential-live', 'live-provider', true, false)""",
                (TENANT_ID, CHANNEL_ID),
            )
            cursor.execute(
                """INSERT INTO llm_module_bindings (
                     tenant_id, project_id, module_key, channel_id, model_id, settings_jsonb, updated_by
                   )
                   VALUES (%s, %s, 'sequential_reading', %s, 'model-seed-sequential-live', '{"temperature":0}'::jsonb, %s)""",
                (TENANT_ID, PROJECT_ID, CHANNEL_ID, USER_ID),
            )


def _prepare_live_global_aggregation_database(admin_url: str, provider_base_url: str) -> None:
    _prepare_live_database_foundation(admin_url)
    with psycopg.connect(admin_url, autocommit=True) as connection:
        with connection.cursor() as cursor:
            cursor.execute(
                """INSERT INTO workflow_runs (
                     tenant_id, run_id, workflow_type, project_id, status, progress, started_by
                   )
                   VALUES (%s, %s, 'seed_pipeline', %s, 'running', 60, %s)""",
                (TENANT_ID, RUN_ID, PROJECT_ID, USER_ID),
            )
            cursor.execute(
                """INSERT INTO text_segments (
                     tenant_id, segment_id, project_id, run_id, segment_order,
                     chapter_guess, title_guess, content_excerpt, object_key, summary, metadata_jsonb
                   )
                   VALUES
                     (
                       %s, %s, %s, %s, 0, '第一章', '雨夜',
                       'PRIVATE_AGGREGATE_RAW_TEXT must not reach provider',
                       'projects/live-seed/private-segment-0.txt',
                       'PRIVATE_AGGREGATE_SEGMENT_SUMMARY must not reach provider',
                       %s::jsonb
                     ),
                     (
                       %s, %s, %s, %s, 1, '第二章', '破晓',
                       'PRIVATE_AGGREGATE_RAW_TEXT_TWO must not reach provider',
                       'projects/live-seed/private-segment-1.txt',
                       'PRIVATE_AGGREGATE_SEGMENT_SUMMARY_TWO must not reach provider',
                       %s::jsonb
                     )""",
                (
                    TENANT_ID,
                    SEGMENT_ID,
                    PROJECT_ID,
                    RUN_ID,
                    json.dumps(
                        {
                            "object_key": "projects/live-seed/private-metadata-segment-0.txt",
                            "prompt": "PRIVATE_AGGREGATE_PROMPT",
                            "api_key": "sk-private",
                        }
                    ),
                    TENANT_ID,
                    SEGMENT_ID_2,
                    PROJECT_ID,
                    RUN_ID,
                    json.dumps({"raw_content": "PRIVATE_AGGREGATE_RAW_CONTENT"}),
                ),
            )
            cursor.execute(
                """INSERT INTO segment_summaries (
                     tenant_id, project_id, run_id, segment_id, summary, source_kind, metadata_jsonb
                   )
                   VALUES
                     (
                       %s, %s, %s, %s, '雨夜公共摘要', 'sequential_reading',
                       %s::jsonb
                     ),
                     (
                       %s, %s, %s, %s, '破晓公共摘要', 'sequential_reading',
                       %s::jsonb
                     )""",
                (
                    TENANT_ID,
                    PROJECT_ID,
                    RUN_ID,
                    SEGMENT_ID,
                    json.dumps(
                        {
                            "provider_response": "PRIVATE_AGGREGATE_PROVIDER_RESPONSE",
                            "raw_body": "PRIVATE_AGGREGATE_RAW_BODY",
                        }
                    ),
                    TENANT_ID,
                    PROJECT_ID,
                    RUN_ID,
                    SEGMENT_ID_2,
                    json.dumps({"credential_ref": "aggregate-secret-ref"}),
                ),
            )
            cursor.execute(
                """INSERT INTO entities (
                     tenant_id, entity_id, project_id, source_run_id, canonical_name,
                     entity_type, importance, state_summary, first_seen_segment_id, metadata_jsonb
                   )
                   VALUES (
                     %s, gen_random_uuid(), %s, %s, '林舟', 'character',
                     'major', 'PRIVATE_AGGREGATE_ENTITY_BODY must not reach provider',
                     %s, %s::jsonb
                   )""",
                (
                    TENANT_ID,
                    PROJECT_ID,
                    RUN_ID,
                    SEGMENT_ID,
                    json.dumps({"evidence": "PRIVATE_AGGREGATE_ENTITY_EVIDENCE"}),
                ),
            )
            cursor.execute(
                """INSERT INTO relationships (
                     tenant_id, relationship_id, project_id, source_entity_name,
                     target_entity_name, relationship_type, summary, source_run_id,
                     first_seen_segment_id, evidence_text, metadata_jsonb
                   )
                   VALUES (
                     %s, gen_random_uuid(), %s, '林舟', '陆晚', 'ally',
                     'PRIVATE_AGGREGATE_RELATIONSHIP_BODY must not reach provider',
                     %s, %s, 'PRIVATE_AGGREGATE_EVIDENCE_MARKER must not reach provider',
                     %s::jsonb
                   )""",
                (
                    TENANT_ID,
                    PROJECT_ID,
                    RUN_ID,
                    SEGMENT_ID,
                    json.dumps({"source_text": "PRIVATE_AGGREGATE_SOURCE_TEXT"}),
                ),
            )
            cursor.execute(
                """INSERT INTO llm_channels (
                     tenant_id, channel_id, name, provider, base_url, encrypted_api_key, max_concurrency, enabled
                   )
                   VALUES (%s, %s, 'Seed Global Aggregation Live Provider', 'openai-compatible', %s, %s, 1, true)""",
                (TENANT_ID, CHANNEL_ID, provider_base_url, _encrypt_api_key("sk-live-seed-global-aggregation")),
            )
            cursor.execute(
                """INSERT INTO llm_models (
                     tenant_id, channel_id, model_id, owned_by, supports_json, supports_tools
                   )
                   VALUES (%s, %s, 'model-seed-global-aggregation-live', 'live-provider', true, false)""",
                (TENANT_ID, CHANNEL_ID),
            )
            cursor.execute(
                """INSERT INTO llm_module_bindings (
                     tenant_id, project_id, module_key, channel_id, model_id, settings_jsonb, updated_by
                   )
                   VALUES (
                     %s, %s, 'anchor_point_summary', %s,
                     'model-seed-global-aggregation-live', '{"temperature":0}'::jsonb, %s
                   )""",
                (TENANT_ID, PROJECT_ID, CHANNEL_ID, USER_ID),
            )


def _prepare_live_archive_candidate_database(admin_url: str, provider_base_url: str) -> None:
    _prepare_live_database_foundation(admin_url)
    with psycopg.connect(admin_url, autocommit=True) as connection:
        with connection.cursor() as cursor:
            cursor.execute(
                """INSERT INTO workflow_runs (
                     tenant_id, run_id, workflow_type, project_id, status, progress, started_by
                   )
                   VALUES (%s, %s, 'seed_pipeline', %s, 'running', 90, %s)""",
                (TENANT_ID, RUN_ID, PROJECT_ID, USER_ID),
            )
            cursor.execute(
                """INSERT INTO llm_channels (
                     tenant_id, channel_id, name, provider, base_url, encrypted_api_key, max_concurrency, enabled
                   )
                   VALUES (%s, %s, 'Seed Archive Candidate Live Provider', 'openai-compatible', %s, %s, 1, true)""",
                (TENANT_ID, CHANNEL_ID, provider_base_url, _encrypt_api_key("sk-live-seed-archive")),
            )
            cursor.execute(
                """INSERT INTO llm_models (
                     tenant_id, channel_id, model_id, owned_by, supports_json, supports_tools
                   )
                   VALUES (%s, %s, 'model-seed-archive-live', 'live-provider', true, false)""",
                (TENANT_ID, CHANNEL_ID),
            )
            cursor.execute(
                """INSERT INTO llm_module_bindings (
                     tenant_id, project_id, module_key, channel_id, model_id, settings_jsonb, updated_by
                   )
                   VALUES (%s, %s, 'narrative_archives', %s, 'model-seed-archive-live', '{"temperature":0}'::jsonb, %s)""",
                (TENANT_ID, PROJECT_ID, CHANNEL_ID, USER_ID),
            )


def _prepare_live_finalize_database(admin_url: str) -> None:
    _prepare_live_database_foundation(admin_url)
    with psycopg.connect(admin_url, autocommit=True) as connection:
        with connection.cursor() as cursor:
            cursor.execute(
                """INSERT INTO workflow_runs (
                     tenant_id, run_id, workflow_type, project_id, status, progress, started_by
                   )
                   VALUES (%s, %s, 'seed_pipeline', %s, 'running', 95, %s)""",
                (TENANT_ID, RUN_ID, PROJECT_ID, USER_ID),
            )
            cursor.execute(
                """INSERT INTO source_files (
                     tenant_id, file_id, project_id, upload_id, object_key, filename,
                     mime_type, size_bytes, sha256, purpose, parse_status, created_by
                   )
                   VALUES (
                     %s, %s, %s, %s, 'projects/live-seed/private-source-must-not-leak.txt',
                     'book.txt', 'text/plain', 1, repeat('0', 64), 'seed', 'parsed', %s
                   )""",
                (TENANT_ID, SOURCE_FILE_ID, PROJECT_ID, UPLOAD_ID, USER_ID),
            )
            cursor.execute(
                """INSERT INTO text_segments (
                     tenant_id, segment_id, project_id, run_id, source_file_id,
                     segment_order, chapter_guess, title_guess, object_key, summary
                   )
                   VALUES (
                     %s, %s, %s, %s, %s, 0, '第一章', '雨港',
                     'projects/live-seed/private-segment-must-not-leak.txt',
                     'PRIVATE_FINALIZE_RAW_TEXT must stay private'
                   )""",
                (TENANT_ID, SEGMENT_ID, PROJECT_ID, RUN_ID, SOURCE_FILE_ID),
            )
            cursor.execute(
                """INSERT INTO assets (
                     tenant_id, asset_id, project_id, scope, asset_type, category, lifecycle,
                     title, summary, content_text, payload_jsonb, tags_jsonb,
                     source_kind, source_ref, enabled, created_by
                   )
                   VALUES
                     (
                       %s, gen_random_uuid(), %s, 'project', 'character', 'cast', 'seed',
                       '林舟', '雨港守夜人', 'PRIVATE_FINALIZE_ASSET_BODY must stay private',
                       %s::jsonb, '["seed"]'::jsonb,
                       'seed_pipeline', 'seed-finalize:asset:1', true, %s
                     ),
                     (
                       %s, gen_random_uuid(), %s, 'project', 'world_rule', 'rule', 'candidate',
                       '破晓规则', '破晓会显露昨夜痕迹', 'PRIVATE_FINALIZE_RULE_BODY must stay private',
                       %s::jsonb, '["candidate", "world"]'::jsonb,
                       'seed_pipeline', 'seed-finalize:asset:2', true, %s
                     ),
                     (
                       %s, gen_random_uuid(), %s, 'project', 'discarded', 'hidden', 'seed',
                       '禁用资产', '不应计入 ready asset count', 'PRIVATE_FINALIZE_DISABLED_BODY',
                       %s::jsonb, '["seed"]'::jsonb,
                       'seed_pipeline', 'seed-finalize:asset:disabled', false, %s
                     )""",
                (
                    TENANT_ID,
                    PROJECT_ID,
                    json.dumps(
                        {
                            "source_run_id": RUN_ID,
                            "prompt": "PRIVATE_FINALIZE_PROMPT must not leak",
                            "api_key": "sk-finalize-live-leak",
                            "credential_ref": "finalize-secret-ref",
                            "object_key": "projects/live-seed/private-asset.txt",
                            "draft": "PRIVATE_FINALIZE_DRAFT",
                            "manuscript": "PRIVATE_FINALIZE_MANUSCRIPT",
                        }
                    ),
                    USER_ID,
                    TENANT_ID,
                    PROJECT_ID,
                    json.dumps({"source_run_id": RUN_ID}),
                    USER_ID,
                    TENANT_ID,
                    PROJECT_ID,
                    json.dumps({"source_run_id": RUN_ID}),
                    USER_ID,
                ),
            )
            cursor.execute(
                """INSERT INTO entities (
                     tenant_id, entity_id, project_id, source_run_id, canonical_name,
                     entity_type, importance, state_summary, first_seen_segment_id, metadata_jsonb
                   )
                   VALUES
                     (
                       %s, gen_random_uuid(), %s, %s, '林舟', 'character',
                       'major', 'PRIVATE_FINALIZE_ENTITY_BODY must stay private', %s,
                       %s::jsonb
                     ),
                     (
                       %s, gen_random_uuid(), %s, %s, '陆晚', 'character',
                       'supporting', 'PRIVATE_FINALIZE_ENTITY_BODY_TWO must stay private', %s,
                       '{}'::jsonb
                     )""",
                (
                    TENANT_ID,
                    PROJECT_ID,
                    RUN_ID,
                    SEGMENT_ID,
                    json.dumps(
                        {
                            "provider_response": "PRIVATE_FINALIZE_PROVIDER_RESPONSE",
                            "raw_body": "PRIVATE_FINALIZE_RAW_BODY",
                        }
                    ),
                    TENANT_ID,
                    PROJECT_ID,
                    RUN_ID,
                    SEGMENT_ID,
                ),
            )
            cursor.execute(
                """INSERT INTO relationships (
                     tenant_id, relationship_id, project_id, source_entity_name,
                     target_entity_name, relationship_type, summary, source_run_id,
                     first_seen_segment_id, evidence_text, metadata_jsonb
                   )
                   VALUES (
                     %s, gen_random_uuid(), %s, '林舟', '陆晚', 'ally',
                     'PRIVATE_FINALIZE_RELATIONSHIP_BODY must stay private',
                     %s, %s, 'PRIVATE_FINALIZE_EVIDENCE must stay private',
                     %s::jsonb
                   )""",
                (
                    TENANT_ID,
                    PROJECT_ID,
                    RUN_ID,
                    SEGMENT_ID,
                    json.dumps({"source_text": "PRIVATE_FINALIZE_SOURCE_TEXT"}),
                ),
            )
            cursor.execute(
                """INSERT INTO world_rule_evidence (
                     tenant_id, rule_evidence_id, project_id, run_id, segment_id,
                     rule_text, evidence_text, category, confidence, metadata_jsonb
                   )
                   VALUES (
                     %s, gen_random_uuid(), %s, %s, %s,
                     '破晓会显露昨夜痕迹',
                     'PRIVATE_FINALIZE_WORLD_RULE_EVIDENCE must stay private',
                     'magic', 0.8, %s::jsonb
                   )""",
                (
                    TENANT_ID,
                    PROJECT_ID,
                    RUN_ID,
                    SEGMENT_ID,
                    json.dumps({"content": "PRIVATE_FINALIZE_WORLD_RULE_CONTENT"}),
                ),
            )


def _prepare_live_database_foundation(admin_url: str) -> None:
    with psycopg.connect(admin_url, autocommit=True) as connection:
        with connection.cursor() as cursor:
            cursor.execute(MIGRATION_SQL.read_text(encoding="utf-8"))
            _ensure_app_login_role(cursor)
            cursor.execute("DELETE FROM tenants WHERE tenant_id = %s", (TENANT_ID,))
            cursor.execute(
                """INSERT INTO users (user_id, email, display_name)
                   VALUES (%s, 'seed-live@example.test', 'Seed Live')
                   ON CONFLICT (user_id) DO UPDATE
                     SET email = EXCLUDED.email,
                         display_name = EXCLUDED.display_name""",
                (USER_ID,),
            )
            cursor.execute(
                """INSERT INTO tenants (tenant_id, slug, name, tenant_type)
                   VALUES (%s, 'seed-live', 'Seed Live', 'personal')""",
                (TENANT_ID,),
            )
            cursor.execute(
                """INSERT INTO tenant_memberships (tenant_id, user_id, role)
                   VALUES (%s, %s, 'owner')""",
                (TENANT_ID, USER_ID),
            )
            cursor.execute(
                """INSERT INTO projects (tenant_id, project_id, title, created_by)
                   VALUES (%s, %s, 'Live Seed Project', %s)""",
                (TENANT_ID, PROJECT_ID, USER_ID),
            )
            cursor.execute(
                """INSERT INTO project_members (tenant_id, project_id, user_id, role)
                   VALUES (%s, %s, %s, 'project_owner')""",
                (TENANT_ID, PROJECT_ID, USER_ID),
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


def _read_seed_live_rows(admin_url: str) -> dict[str, list[dict[str, Any]]]:
    return _read_seed_live_rows_for(admin_url, RUN_ID, SOURCE_FILE_ID)


def _read_seed_live_rows_for(admin_url: str, run_id: str, source_file_id: str) -> dict[str, list[dict[str, Any]]]:
    with psycopg.connect(admin_url, row_factory=dict_row) as connection:
        with connection.cursor() as cursor:
            cursor.execute(
                """SELECT file_id::text, parse_status
                   FROM source_files
                   WHERE tenant_id = %s AND project_id = %s AND file_id = %s""",
                (TENANT_ID, PROJECT_ID, source_file_id),
            )
            source_files = [_normalize_row(row) for row in cursor.fetchall()]
            cursor.execute(
                """SELECT source_file_id::text, artifact_type, char_count, line_count, sha256
                   FROM project_text_artifacts
                   WHERE tenant_id = %s AND project_id = %s AND run_id = %s
                   ORDER BY created_at""",
                (TENANT_ID, PROJECT_ID, run_id),
            )
            project_text_artifacts = [_normalize_row(row) for row in cursor.fetchall()]
            cursor.execute(
                """SELECT artifact_type, object_key
                   FROM project_text_artifacts
                   WHERE tenant_id = %s AND project_id = %s AND run_id = %s
                   ORDER BY created_at""",
                (TENANT_ID, PROJECT_ID, run_id),
            )
            project_text_artifact_object_refs = [_normalize_row(row) for row in cursor.fetchall()]
            cursor.execute(
                """SELECT segment_order, chapter_guess, title_guess
                   FROM text_segments
                   WHERE tenant_id = %s AND project_id = %s AND run_id = %s
                   ORDER BY segment_order""",
                (TENANT_ID, PROJECT_ID, run_id),
            )
            text_segments = [_normalize_row(row) for row in cursor.fetchall()]
            cursor.execute(
                """SELECT segment_order, object_key
                   FROM text_segments
                   WHERE tenant_id = %s AND project_id = %s AND run_id = %s
                   ORDER BY segment_order""",
                (TENANT_ID, PROJECT_ID, run_id),
            )
            text_segment_object_refs = [_normalize_row(row) for row in cursor.fetchall()]
            cursor.execute(
                """SELECT event_type, payload_jsonb
                   FROM workflow_events
                   WHERE tenant_id = %s AND project_id = %s AND run_id = %s
                   ORDER BY sequence""",
                (TENANT_ID, PROJECT_ID, run_id),
            )
            workflow_events = [_normalize_row(row) for row in cursor.fetchall()]
            cursor.execute(
                """SELECT status, error_code
                   FROM workflow_runs
                   WHERE tenant_id = %s AND project_id = %s AND run_id = %s""",
                (TENANT_ID, PROJECT_ID, run_id),
            )
            workflow_runs = [_normalize_row(row) for row in cursor.fetchall()]
    return {
        "source_files": source_files,
        "project_text_artifacts": project_text_artifacts,
        "project_text_artifact_object_refs": project_text_artifact_object_refs,
        "text_segments": text_segments,
        "text_segment_object_refs": text_segment_object_refs,
        "workflow_events": workflow_events,
        "workflow_runs": workflow_runs,
    }


def _read_seed_sequential_reading_live_rows(admin_url: str) -> dict[str, list[dict[str, Any]]]:
    with psycopg.connect(admin_url, row_factory=dict_row) as connection:
        with connection.cursor() as cursor:
            cursor.execute(
                """SELECT segment_id::text, segment_order, chapter_guess, title_guess
                   FROM text_segments
                   WHERE tenant_id = %s AND project_id = %s AND run_id = %s
                   ORDER BY segment_order""",
                (TENANT_ID, PROJECT_ID, RUN_ID),
            )
            text_segments = [_normalize_row(row) for row in cursor.fetchall()]
            cursor.execute(
                """SELECT pass_id::text, pass_type, status, module_key, model_id, metadata_jsonb
                   FROM reading_passes
                   WHERE tenant_id = %s AND project_id = %s AND run_id = %s
                   ORDER BY created_at""",
                (TENANT_ID, PROJECT_ID, RUN_ID),
            )
            reading_passes = [_normalize_row(row) for row in cursor.fetchall()]
            cursor.execute(
                """SELECT segment_id::text, pass_id::text, summary, payload_jsonb
                   FROM reading_segment_notes
                   WHERE tenant_id = %s AND project_id = %s AND run_id = %s
                   ORDER BY segment_id""",
                (TENANT_ID, PROJECT_ID, RUN_ID),
            )
            reading_segment_notes = [_normalize_row(row) for row in cursor.fetchall()]
            cursor.execute(
                """SELECT event_type, payload_jsonb
                   FROM workflow_events
                   WHERE tenant_id = %s AND project_id = %s AND run_id = %s
                   ORDER BY sequence""",
                (TENANT_ID, PROJECT_ID, RUN_ID),
            )
            workflow_events = [_normalize_row(row) for row in cursor.fetchall()]
    return {
        "text_segments": text_segments,
        "reading_passes": reading_passes,
        "reading_segment_notes": reading_segment_notes,
        "workflow_events": workflow_events,
    }


def _read_seed_global_aggregation_live_rows(admin_url: str) -> dict[str, list[dict[str, Any]]]:
    with psycopg.connect(admin_url, row_factory=dict_row) as connection:
        with connection.cursor() as cursor:
            cursor.execute(
                """SELECT module_key, model_id, summary_count, segment_count, analysis_jsonb
                   FROM seed_analysis_snapshots
                   WHERE tenant_id = %s AND project_id = %s AND run_id = %s
                   ORDER BY updated_at""",
                (TENANT_ID, PROJECT_ID, RUN_ID),
            )
            seed_analysis_snapshots = [_normalize_row(row) for row in cursor.fetchall()]
            cursor.execute(
                """SELECT event_type, payload_jsonb
                   FROM workflow_events
                   WHERE tenant_id = %s AND project_id = %s AND run_id = %s
                   ORDER BY sequence""",
                (TENANT_ID, PROJECT_ID, RUN_ID),
            )
            workflow_events = [_normalize_row(row) for row in cursor.fetchall()]
    return {
        "seed_analysis_snapshots": seed_analysis_snapshots,
        "workflow_events": workflow_events,
    }


def _read_seed_ontology_live_rows(admin_url: str) -> dict[str, list[dict[str, Any]]]:
    with psycopg.connect(admin_url, row_factory=dict_row) as connection:
        with connection.cursor() as cursor:
            cursor.execute(
                """SELECT
                     module_key, model_id, entity_type_count,
                     relationship_type_count, world_rule_type_count, ontology_jsonb
                   FROM seed_ontology_snapshots
                   WHERE tenant_id = %s AND project_id = %s AND run_id = %s
                   ORDER BY updated_at""",
                (TENANT_ID, PROJECT_ID, RUN_ID),
            )
            seed_ontology_snapshots = [_normalize_row(row) for row in cursor.fetchall()]
            cursor.execute(
                """SELECT event_type, payload_jsonb
                   FROM workflow_events
                   WHERE tenant_id = %s AND project_id = %s AND run_id = %s
                   ORDER BY sequence""",
                (TENANT_ID, PROJECT_ID, RUN_ID),
            )
            workflow_events = [_normalize_row(row) for row in cursor.fetchall()]
    return {
        "seed_ontology_snapshots": seed_ontology_snapshots,
        "workflow_events": workflow_events,
    }


def _read_seed_entity_resolution_live_rows(admin_url: str) -> dict[str, list[dict[str, Any]]]:
    with psycopg.connect(admin_url, row_factory=dict_row) as connection:
        with connection.cursor() as cursor:
            cursor.execute(
                """SELECT status, progress
                   FROM workflow_runs
                   WHERE tenant_id = %s AND project_id = %s AND run_id = %s""",
                (TENANT_ID, PROJECT_ID, RUN_ID),
            )
            workflow_runs = [_normalize_row(row) for row in cursor.fetchall()]
            cursor.execute(
                """SELECT
                     module_key, model_id, merged_entity_count,
                     alias_count, conflict_count, resolution_jsonb
                   FROM seed_entity_resolution_snapshots
                   WHERE tenant_id = %s AND project_id = %s AND run_id = %s
                   ORDER BY updated_at""",
                (TENANT_ID, PROJECT_ID, RUN_ID),
            )
            seed_entity_resolution_snapshots = [_normalize_row(row) for row in cursor.fetchall()]
            cursor.execute(
                """SELECT event_type, payload_jsonb
                   FROM workflow_events
                   WHERE tenant_id = %s AND project_id = %s AND run_id = %s
                   ORDER BY sequence""",
                (TENANT_ID, PROJECT_ID, RUN_ID),
            )
            workflow_events = [_normalize_row(row) for row in cursor.fetchall()]
    return {
        "workflow_runs": workflow_runs,
        "seed_entity_resolution_snapshots": seed_entity_resolution_snapshots,
        "workflow_events": workflow_events,
    }


def _read_seed_agent_profile_live_rows(admin_url: str) -> dict[str, list[dict[str, Any]]]:
    with psycopg.connect(admin_url, row_factory=dict_row) as connection:
        with connection.cursor() as cursor:
            cursor.execute(
                """SELECT
                     module_key, model_id, profile_count, memory_seed_count,
                     relationship_view_count, profiles_jsonb
                   FROM seed_agent_profile_snapshots
                   WHERE tenant_id = %s AND project_id = %s AND run_id = %s
                   ORDER BY updated_at""",
                (TENANT_ID, PROJECT_ID, RUN_ID),
            )
            seed_agent_profile_snapshots = [_normalize_row(row) for row in cursor.fetchall()]
            cursor.execute(
                """SELECT event_type, payload_jsonb
                   FROM workflow_events
                   WHERE tenant_id = %s AND project_id = %s AND run_id = %s
                   ORDER BY sequence""",
                (TENANT_ID, PROJECT_ID, RUN_ID),
            )
            workflow_events = [_normalize_row(row) for row in cursor.fetchall()]
    return {
        "seed_agent_profile_snapshots": seed_agent_profile_snapshots,
        "workflow_events": workflow_events,
    }


def _read_seed_archive_candidate_live_rows(admin_url: str) -> dict[str, list[dict[str, Any]]]:
    with psycopg.connect(admin_url, row_factory=dict_row) as connection:
        with connection.cursor() as cursor:
            cursor.execute(
                """SELECT
                     asset_id::text, asset_type, category, lifecycle, title, summary,
                     content_text, payload_jsonb, tags_jsonb, source_kind, source_ref
                   FROM assets
                   WHERE tenant_id = %s
                     AND project_id = %s
                     AND source_kind = 'narrative_archives'
                   ORDER BY source_ref""",
                (TENANT_ID, PROJECT_ID),
            )
            assets = [_normalize_row(row) for row in cursor.fetchall()]
            cursor.execute(
                """SELECT
                     memory_id::text, asset_id::text, memory_type, status, summary,
                     body_text, payload_jsonb, source_kind, source_ref
                   FROM archive_memories
                   WHERE tenant_id = %s
                     AND project_id = %s
                     AND source_kind = 'narrative_archives'
                   ORDER BY source_ref""",
                (TENANT_ID, PROJECT_ID),
            )
            archive_memories = [_normalize_row(row) for row in cursor.fetchall()]
            cursor.execute(
                """SELECT event_type, status, payload_jsonb
                   FROM archive_memory_events
                   WHERE tenant_id = %s
                     AND project_id = %s
                   ORDER BY created_at""",
                (TENANT_ID, PROJECT_ID),
            )
            archive_memory_events = [_normalize_row(row) for row in cursor.fetchall()]
            cursor.execute(
                """SELECT event_type, payload_jsonb
                   FROM workflow_events
                   WHERE tenant_id = %s AND project_id = %s AND run_id = %s
                   ORDER BY sequence""",
                (TENANT_ID, PROJECT_ID, RUN_ID),
            )
            workflow_events = [_normalize_row(row) for row in cursor.fetchall()]
    return {
        "assets": assets,
        "archive_memories": archive_memories,
        "archive_memory_events": archive_memory_events,
        "workflow_events": workflow_events,
    }


def _read_seed_finalize_live_rows(admin_url: str) -> dict[str, list[dict[str, Any]]]:
    with psycopg.connect(admin_url, row_factory=dict_row) as connection:
        with connection.cursor() as cursor:
            cursor.execute(
                """SELECT
                     project_readiness_snapshot_id::text,
                     run_id::text,
                     ready_asset_count,
                     ready_entity_count,
                     ready_relationship_count,
                     ready_world_rule_count,
                     metadata_jsonb
                   FROM project_readiness_snapshots
                   WHERE tenant_id = %s AND project_id = %s AND run_id = %s""",
                (TENANT_ID, PROJECT_ID, RUN_ID),
            )
            project_readiness_snapshots = [_normalize_row(row) for row in cursor.fetchall()]
            cursor.execute(
                """SELECT status, progress, message, error_code, error_message, result_jsonb
                   FROM workflow_runs
                   WHERE tenant_id = %s AND project_id = %s AND run_id = %s""",
                (TENANT_ID, PROJECT_ID, RUN_ID),
            )
            workflow_runs = [_normalize_row(row) for row in cursor.fetchall()]
            cursor.execute(
                """SELECT event_type, payload_jsonb
                   FROM workflow_events
                   WHERE tenant_id = %s AND project_id = %s AND run_id = %s
                   ORDER BY sequence""",
                (TENANT_ID, PROJECT_ID, RUN_ID),
            )
            workflow_events = [_normalize_row(row) for row in cursor.fetchall()]
    return {
        "project_readiness_snapshots": project_readiness_snapshots,
        "workflow_runs": workflow_runs,
        "workflow_events": workflow_events,
    }


def _archive_candidate_live_forbidden_public_markers() -> tuple[str, ...]:
    return (
        "prompt",
        "provider_response",
        "provider_raw_body",
        "raw_body",
        "api_key",
        "credential_ref",
        "object_key",
        "source_object_key",
        "artifact_object_key",
        "segment_object_key",
        "projects/leaked/archive/private.txt",
        "projects/leaked/source.txt",
        "sk-live-seed-archive",
        "sk-provider-archive-leak",
        "sk-provider-memory-leak",
        "sk-provider-top-level-leak",
        "secret-ref",
        "memory-secret-ref",
        "top-level-secret-ref",
        "PRIVATE_ARCHIVE_PROMPT",
        "PRIVATE_PROVIDER_RESPONSE",
        "PRIVATE_PROVIDER_RAW_BODY",
        "PRIVATE_ARCHIVE_RAW_BODY",
        "PRIVATE_ARCHIVE_TOP_LEVEL_PROMPT",
        "PRIVATE_ARCHIVE_TOP_LEVEL_RESPONSE",
        "PRIVATE_ARCHIVE_TOP_LEVEL_RAW_BODY",
        "PRIVATE_ARCHIVE_MEMORY_BODY",
        "PRIVATE_ARCHIVE_BODY_TEXT_PAYLOAD",
        "PRIVATE_ARCHIVE_MEMORY_RAW_BODY",
        "PRIVATE_MEMORY_PROVIDER_RESPONSE",
        "draft",
        "manuscript",
        "PRIVATE_ARCHIVE_DRAFT",
        "PRIVATE_ARCHIVE_MANUSCRIPT",
        "PRIVATE_ARCHIVE_MEMORY_DRAFT",
        "PRIVATE_ARCHIVE_MEMORY_MANUSCRIPT",
        "PRIVATE_ARCHIVE_TOP_LEVEL_DRAFT",
        "PRIVATE_ARCHIVE_TOP_LEVEL_MANUSCRIPT",
    )


def _global_aggregation_live_forbidden_public_markers() -> tuple[str, ...]:
    return (
        "prompt",
        "provider_response",
        "raw_body",
        "raw_content",
        "content_excerpt",
        "api_key",
        "encrypted_api_key",
        "credential_ref",
        "object_key",
        "source_object_key",
        "artifact_object_key",
        "segment_object_key",
        "projects/live-seed/private",
        "sk-live-seed-global-aggregation",
        "sk-provider-aggregate-leak",
        "aggregate-secret-ref",
        "PRIVATE_AGGREGATE_RAW_TEXT",
        "PRIVATE_AGGREGATE_RAW_TEXT_TWO",
        "PRIVATE_AGGREGATE_SEGMENT_SUMMARY",
        "PRIVATE_AGGREGATE_ENTITY_BODY",
        "PRIVATE_AGGREGATE_RELATIONSHIP_BODY",
        "PRIVATE_AGGREGATE_PROVIDER_RESPONSE",
        "PRIVATE_AGGREGATE_RAW_BODY",
        "PRIVATE_AGGREGATE_EVIDENCE_MARKER",
        "PRIVATE_AGGREGATE_SOURCE_TEXT",
        "PRIVATE_AGGREGATE_PROMPT",
        "PRIVATE_AGGREGATE_RAW_CONTENT",
        "draft",
        "manuscript",
        "PRIVATE_AGGREGATE_DRAFT",
        "PRIVATE_AGGREGATE_MANUSCRIPT",
    )


def _finalize_live_forbidden_public_markers() -> tuple[str, ...]:
    return (
        "prompt",
        "provider_response",
        "provider_raw_body",
        "raw_body",
        "raw_content",
        "content",
        "api_key",
        "encrypted_api_key",
        "credential_ref",
        "object_key",
        "source_object_key",
        "artifact_object_key",
        "segment_object_key",
        "projects/live-seed/private",
        "sk-finalize-live-leak",
        "finalize-secret-ref",
        "readiness_report",
        "PRIVATE_FINALIZE",
        "draft",
        "manuscript",
    )


def _normalize_row(row: dict[str, Any]) -> dict[str, Any]:
    return {key: value for key, value in row.items()}


def _header(headers: dict[str, str], name: str) -> str:
    normalized = name.lower()
    for key, value in headers.items():
        if key.lower() == normalized:
            return value
    raise KeyError(name)


def _wait_for_seed_live_parse_segment_rows(admin_url: str, run_id: str, source_file_id: str) -> dict[str, list[dict[str, Any]]]:
    deadline = time.monotonic() + 45
    last: dict[str, list[dict[str, Any]]] = {}
    while time.monotonic() < deadline:
        last = _read_seed_live_rows_for(admin_url, run_id, source_file_id)
        if (
            last["source_files"] == [{"file_id": source_file_id, "parse_status": "parsed"}]
            and len(last["project_text_artifacts"]) == 1
            and len(last["text_segments"]) == 2
            and any(event["event_type"] == "seed.stage.failed" for event in last["workflow_events"])
        ):
            return last
        time.sleep(0.5)
    raise AssertionError(f"timed out waiting for live seed parse/segment rows: {last!r}")


def _assert_seed_object_readback(
    object_store: S3CompatibleObjectStore,
    persisted: dict[str, list[dict[str, Any]]],
    *,
    expected_artifact_bytes: bytes,
    expected_segment_texts: list[str],
) -> None:
    artifact_keys = [
        row["object_key"]
        for row in persisted["project_text_artifact_object_refs"]
        if row["artifact_type"] == "extracted_text"
    ]
    assert len(artifact_keys) == 1
    assert object_store.read_bytes(artifact_keys[0]) == expected_artifact_bytes
    segment_keys = [row["object_key"] for row in persisted["text_segment_object_refs"]]
    assert len(segment_keys) == len(expected_segment_texts)
    assert [object_store.read_bytes(key).decode("utf-8") for key in segment_keys] == expected_segment_texts


class _SeedWorker:
    def __init__(self, client: Client, task_queue: str) -> None:
        self.client = client
        self.task_queue = task_queue
        self.executor = None
        self.worker = None

    async def __aenter__(self) -> "_SeedWorker":
        from concurrent.futures import ThreadPoolExecutor

        self.executor = ThreadPoolExecutor(max_workers=8)
        self.worker = Worker(
            self.client,
            task_queue=self.task_queue,
            workflows=[SeedPipelineWorkflow],
            activities=[
                seed_pipeline_activity,
                parse_file_activity,
                segment_text_activity,
                sequential_reading_activity,
            ],
            activity_executor=self.executor,
        )
        await self.worker.__aenter__()
        return self

    async def __aexit__(self, exc_type: Any, exc: Any, tb: Any) -> None:
        if self.worker is not None:
            await self.worker.__aexit__(exc_type, exc, tb)
        if self.executor is not None:
            self.executor.shutdown(wait=True)


def _seed_worker(client: Client, task_queue: str) -> _SeedWorker:
    return _SeedWorker(client, task_queue)


class _GoAPI:
    def __init__(self, process: subprocess.Popen[str], base_url: str) -> None:
        self.process = process
        self.base_url = base_url

    def __enter__(self) -> str:
        return self.base_url

    def __exit__(self, exc_type: Any, exc: Any, tb: Any) -> None:
        if self.process.poll() is None:
            self.process.terminate()
            try:
                self.process.wait(timeout=10)
            except subprocess.TimeoutExpired:
                self.process.kill()
                self.process.wait(timeout=10)


def _start_live_go_api(
    database_url: str,
    temporal_address: str,
    temporal_namespace: str,
    task_queue: str,
    storage_env: dict[str, str],
) -> _GoAPI:
    port = _free_port()
    base_url = f"http://127.0.0.1:{port}"
    env = os.environ.copy()
    env.update(storage_env)
    env.update(
        {
            "DATABASE_URL": database_url,
            "TEMPORAL_ADDRESS": temporal_address,
            "TEMPORAL_NAMESPACE": temporal_namespace,
            "SEED_TASK_QUEUE": task_queue,
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
            time.sleep(0.5)
    process.terminate()
    output = process.stdout.read() if process.stdout is not None else ""
    raise AssertionError(f"Go API did not become healthy: {output}")


def _free_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.bind(("127.0.0.1", 0))
        return int(sock.getsockname()[1])


def _api_json(method: str, url: str, headers: dict[str, str], payload: dict[str, Any] | None) -> dict[str, Any]:
    body = None if payload is None else json.dumps(payload).encode("utf-8")
    request = Request(url, data=body, method=method, headers=headers)
    try:
        with urlopen(request, timeout=10) as response:
            return json.loads(response.read().decode("utf-8"))
    except HTTPError as exc:
        error_body = exc.read().decode("utf-8")
        raise AssertionError(f"{method} {url} failed with {exc.code}: {error_body}") from exc


def _api_bytes(method: str, url: str, headers: dict[str, str], payload: bytes) -> dict[str, Any]:
    request = Request(url, data=payload, method=method, headers=headers)
    try:
        with urlopen(request, timeout=10) as response:
            return json.loads(response.read().decode("utf-8"))
    except HTTPError as exc:
        error_body = exc.read().decode("utf-8")
        raise AssertionError(f"{method} {url} failed with {exc.code}: {error_body}") from exc
