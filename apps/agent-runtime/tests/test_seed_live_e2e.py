from __future__ import annotations

import asyncio
import hashlib
import json
import os
import socket
import subprocess
import time
from pathlib import Path
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

import psycopg
import pytest
from psycopg import sql
from psycopg.conninfo import conninfo_to_dict, make_conninfo
from psycopg.rows import dict_row
from temporalio.client import Client
from temporalio.worker import Worker

from mirofish_agents.temporal.seed import (
    SeedPipelineWorkflow,
    S3CompatibleObjectStore,
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


class _InMemoryObjectStore:
    def __init__(self, objects: dict[str, bytes]) -> None:
        self.objects = dict(objects)

    def read_bytes(self, object_key: str) -> bytes:
        return self.objects[object_key]

    def write_bytes(self, object_key: str, data: bytes, content_type: str) -> None:
        self.objects[object_key] = data


def _live_database_url() -> str:
    database_url = os.environ.get("MIROFISH_SEED_LIVE_DATABASE_URL", "").strip()
    if not database_url:
        pytest.skip("set MIROFISH_SEED_LIVE_DATABASE_URL to run the live Seed Postgres parse/segment E2E")
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


def _normalize_row(row: dict[str, Any]) -> dict[str, Any]:
    return {key: value for key, value in row.items()}


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
