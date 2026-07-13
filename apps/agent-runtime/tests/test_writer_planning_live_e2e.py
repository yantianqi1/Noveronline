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
from psycopg.conninfo import conninfo_to_dict, make_conninfo
from temporalio.client import Client
from temporalio.worker import Worker

from mirofish_agents.temporal.writer_planning import (
    WriterBookPlanWorkflow,
    WriterDedupExtractionWorkflow,
    writer_book_plan_activity,
    writer_dedup_activity,
    writer_planning_failure_activity,
)


KEY_MATERIAL = "000102030405060708090a0b0c0d0e0f101112131415161718191a1b1c1d1e1f"
APP_ROLE = "mirofish_writer_review_live_app"
APP_PASSWORD = "mirofish_writer_review_live_password"
TENANT_ID = "91111111-1111-4111-8111-111111111111"
USER_ID = "92222222-2222-4222-8222-222222222222"
PROJECT_ID = "93333333-3333-4333-8333-333333333333"
WRITER_RUN_ID = "94444444-4444-4444-8444-444444444444"
DRAFT_ID = "95555555-5555-4555-8555-555555555555"
BLOCK_ID = "96666666-6666-4666-8666-666666666666"
CHANNEL_ID = "97777777-7777-4777-8777-777777777777"
DEDUP_RUN_ID = "98888888-8888-4888-8888-888888888888"
BOOK_RUN_ID = "99999999-9999-4999-8999-999999999999"
BOOK_PLAN_ID = "9aaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa"


def test_writer_planning_live_temporal_app_role_provider_and_ledgers(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    asyncio.run(_run_live(monkeypatch))


async def _run_live(monkeypatch: pytest.MonkeyPatch) -> None:
    admin_url = os.environ.get("MIROFISH_WRITER_PLANNING_LIVE_DATABASE_URL", "").strip()
    temporal_address = os.environ.get("MIROFISH_WRITER_PLANNING_LIVE_TEMPORAL_ADDRESS", "").strip()
    if not admin_url or not temporal_address:
        pytest.skip("set planning live PostgreSQL and Temporal environment variables")
    queue = f"writer-planning-live-{os.getpid()}-{int(time.time() * 1000)}"
    provider = _LocalProvider()
    provider.start()
    try:
        _prepare(admin_url, provider.base_url)
        monkeypatch.setenv("DATABASE_URL", _app_url(admin_url))
        monkeypatch.setenv("LLM_CREDENTIAL_ENCRYPTION_KEY", KEY_MATERIAL)
        client = await Client.connect(temporal_address)
        with ThreadPoolExecutor(max_workers=2) as executor:
            worker = Worker(
                client,
                task_queue=queue,
                workflows=[WriterDedupExtractionWorkflow, WriterBookPlanWorkflow],
                activities=[writer_dedup_activity, writer_book_plan_activity, writer_planning_failure_activity],
                activity_executor=executor,
            )
            async with worker:
                dedup = await client.execute_workflow(
                    WriterDedupExtractionWorkflow.run,
                    _payload(DEDUP_RUN_ID, "writer_dedup_extraction", "writer_dedup_extractor", block_ids=[BLOCK_ID]),
                    id=f"writer-planning-live-dedup-{DEDUP_RUN_ID}",
                    task_queue=queue,
                )
                book = await client.execute_workflow(
                    WriterBookPlanWorkflow.run,
                    _payload(BOOK_RUN_ID, "writer_book_plan_generation", "writer_book_planner", book_plan_id=BOOK_PLAN_ID, expected_version=1),
                    id=f"writer-planning-live-book-{BOOK_RUN_ID}",
                    task_queue=queue,
                )
        state = _read_state(admin_url)
    finally:
        provider.close()
        _cleanup(admin_url)

    assert dedup == {"tenant_id": TENANT_ID, "project_id": PROJECT_ID, "run_id": DEDUP_RUN_ID, "workflow_type": "writer_dedup_extraction", "actor_user_id": USER_ID, "module_key": "writer_dedup_extractor", "trace_id": f"trace_{DEDUP_RUN_ID}", "status": "completed", "replayed": False, "candidate_count": 1}
    assert book["status"] == "completed" and book["candidate"] is True and book["version"] == 2
    assert len(provider.requests) == 2
    assert state["patterns"] == [("candidate", False, DEDUP_RUN_ID)]
    assert state["book"] == ("draft", 2, "completed", BOOK_RUN_ID)
    assert state["workflows"] == [("writer_book_plan_generation", "completed"), ("writer_dedup_extraction", "completed")]
    assert state["reservations"] == [("writer_book_planner", "finalized"), ("writer_dedup_extractor", "finalized")]
    assert state["usage_count"] == 4 and state["activity_count"] == 2 and state["private_trace_count"] == 2
    public = json.dumps({"dedup": dedup, "book": book, "events": state["events"]}, sort_keys=True)
    for forbidden in ("Private adopted", "sk-writer-planning-live", "credential_ref", "content_text", "prompt", "response"):
        assert forbidden not in public


def _payload(run_id: str, workflow_type: str, module_key: str, **values: Any) -> dict[str, Any]:
    return {
        "context": {
            "tenant_id": TENANT_ID, "project_id": PROJECT_ID, "run_id": run_id,
            "workflow_type": workflow_type, "actor_user_id": USER_ID,
            "module_key": module_key, "trace_id": f"trace_{run_id}",
            "permissions": {module_key: ["run"]},
        },
        **values,
    }


class _LocalProvider:
    def __init__(self) -> None:
        self.requests: list[dict[str, Any]] = []
        outer = self

        class Handler(BaseHTTPRequestHandler):
            def do_POST(self) -> None:  # noqa: N802
                body = json.loads(self.rfile.read(int(self.headers.get("Content-Length", "0"))))
                if self.path != "/v1/chat/completions" or self.headers.get("Authorization") != "Bearer sk-writer-planning-live":
                    self.send_response(401); self.end_headers(); return
                outer.requests.append(body)
                system = body["messages"][0]["content"]
                result = (
                    {"patterns": [{"pattern_text": "Repeated threshold gesture", "pattern_kind": "description", "occurrence_count": 2}]}
                    if "repetition-risk" in system
                    else {"premise": "A city must choose memory or safety.", "acts": [{"title": "Signal", "summary": "The hidden cost appears.", "chapter_start": 1, "chapter_end": 6}]}
                )
                encoded = json.dumps({"choices": [{"message": {"content": json.dumps(result)}}], "usage": {"prompt_tokens": 20, "completion_tokens": 10, "total_tokens": 30}}).encode()
                self.send_response(200); self.send_header("Content-Type", "application/json"); self.send_header("Content-Length", str(len(encoded))); self.end_headers(); self.wfile.write(encoded)

            def log_message(self, format: str, *args: Any) -> None:
                return None

        self.server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        self.base_url = f"http://127.0.0.1:{self.server.server_address[1]}/v1"

    def start(self) -> None:
        self.thread.start()

    def close(self) -> None:
        self.server.shutdown(); self.server.server_close(); self.thread.join(timeout=2)


def _prepare(admin_url: str, provider_url: str) -> None:
    with psycopg.connect(admin_url, autocommit=True) as connection:
        cursor = connection.cursor()
        cursor.execute("DELETE FROM tenants WHERE tenant_id = %s", (TENANT_ID,))
        cursor.execute("DELETE FROM users WHERE user_id = %s", (USER_ID,))
        cursor.execute("INSERT INTO users (user_id,email,display_name) VALUES (%s,'writer-planning-live@example.test','Writer Planning Live')", (USER_ID,))
        cursor.execute("INSERT INTO tenants (tenant_id,slug,name,tenant_type) VALUES (%s,'writer-planning-live','Writer Planning Live','personal')", (TENANT_ID,))
        cursor.execute("INSERT INTO tenant_memberships (tenant_id,user_id,role) VALUES (%s,%s,'owner')", (TENANT_ID, USER_ID))
        cursor.execute("INSERT INTO projects (tenant_id,project_id,title,created_by) VALUES (%s,%s,'Writer Planning Live',%s)", (TENANT_ID, PROJECT_ID, USER_ID))
        cursor.execute("INSERT INTO project_members (tenant_id,project_id,user_id,role) VALUES (%s,%s,%s,'project_owner')", (TENANT_ID, PROJECT_ID, USER_ID))
        cursor.execute("INSERT INTO workflow_runs (tenant_id,run_id,workflow_type,project_id,status,progress,started_by) VALUES (%s,%s,'writer_run',%s,'completed',100,%s)", (TENANT_ID, WRITER_RUN_ID, PROJECT_ID, USER_ID))
        cursor.execute("INSERT INTO writer_runs (tenant_id,run_id,workflow_run_id,project_id,mode,status,module_key,instruction,created_by) VALUES (%s,%s,%s,%s,'draft','completed','writer_composer','private',%s)", (TENANT_ID, WRITER_RUN_ID, WRITER_RUN_ID, PROJECT_ID, USER_ID))
        cursor.execute("INSERT INTO writer_drafts (tenant_id,draft_id,run_id,project_id,content_text,word_count,status) VALUES (%s,%s,%s,%s,'Private adopted source. The bell rang twice at the threshold.',10,'adopted')", (TENANT_ID, DRAFT_ID, WRITER_RUN_ID, PROJECT_ID))
        cursor.execute("INSERT INTO manuscript_blocks (tenant_id,block_id,project_id,source_draft_id,block_order,content_text,word_count,status,created_by) VALUES (%s,%s,%s,%s,1,'Private adopted source. The bell rang twice at the threshold.',10,'active',%s)", (TENANT_ID, BLOCK_ID, PROJECT_ID, DRAFT_ID, USER_ID))
        for run_id, workflow_type in ((DEDUP_RUN_ID, "writer_dedup_extraction"), (BOOK_RUN_ID, "writer_book_plan_generation")):
            cursor.execute("INSERT INTO workflow_runs (tenant_id,run_id,workflow_type,project_id,status,progress,started_by) VALUES (%s,%s,%s,%s,'queued',0,%s)", (TENANT_ID, run_id, workflow_type, PROJECT_ID, USER_ID))
            cursor.execute("INSERT INTO workflow_events (tenant_id,run_id,workflow_type,project_id,event_type,sequence,payload_jsonb) VALUES (%s,%s,%s,%s,'workflow.queued',1,'{\"status\":\"queued\"}')", (TENANT_ID, run_id, workflow_type, PROJECT_ID))
        cursor.execute("INSERT INTO book_plans (tenant_id,project_id,book_plan_id,title,status,premise,target_chapter_count,last_run_id,last_run_status,created_by) VALUES (%s,%s,%s,'City Memory','draft','A private draft premise.',6,%s,'queued',%s)", (TENANT_ID, PROJECT_ID, BOOK_PLAN_ID, BOOK_RUN_ID, USER_ID))
        cursor.execute("INSERT INTO book_run_events (tenant_id,project_id,book_plan_id,run_id,sequence,event_type,status,item_count) VALUES (%s,%s,%s,%s,1,'planning.admitted','queued',0)", (TENANT_ID, PROJECT_ID, BOOK_PLAN_ID, BOOK_RUN_ID))
        cursor.execute("INSERT INTO llm_channels (tenant_id,channel_id,name,provider,base_url,encrypted_api_key,max_concurrency,enabled) VALUES (%s,%s,'Writer Planning Local','openai-compatible',%s,%s,2,true)", (TENANT_ID, CHANNEL_ID, provider_url, _encrypt("sk-writer-planning-live")))
        cursor.execute("INSERT INTO llm_models (tenant_id,channel_id,model_id,owned_by,supports_json,supports_tools,input_cost,output_cost) VALUES (%s,%s,'writer-planning-live','local',true,false,1,2)", (TENANT_ID, CHANNEL_ID))
        for module in ("writer_dedup_extractor", "writer_book_planner"):
            cursor.execute("INSERT INTO llm_module_bindings (tenant_id,project_id,module_key,channel_id,model_id,settings_jsonb,updated_by) VALUES (%s,%s,%s,%s,'writer-planning-live','{\"max_tokens\":256}',%s)", (TENANT_ID, PROJECT_ID, module, CHANNEL_ID, USER_ID))
        cursor.execute("INSERT INTO llm_quota_policies (tenant_id,scope_type,token_limit,cost_limit_micros,concurrency_limit,period_seconds,updated_by) VALUES (%s,'tenant',1000000,1000000,2,3600,%s)", (TENANT_ID, USER_ID))


def _read_state(admin_url: str) -> dict[str, Any]:
    with psycopg.connect(admin_url) as connection:
        cursor = connection.cursor()
        return {
            "patterns": cursor.execute("SELECT lifecycle,enabled,source_workflow_run_id::text FROM writer_dedup_patterns WHERE tenant_id=%s", (TENANT_ID,)).fetchall(),
            "book": cursor.execute("SELECT status,optimistic_version,last_run_status,last_run_id::text FROM book_plans WHERE tenant_id=%s", (TENANT_ID,)).fetchone(),
            "workflows": cursor.execute("SELECT workflow_type,status FROM workflow_runs WHERE tenant_id=%s AND run_id IN (%s,%s) ORDER BY workflow_type", (TENANT_ID, DEDUP_RUN_ID, BOOK_RUN_ID)).fetchall(),
            "reservations": cursor.execute("SELECT module_key,status FROM llm_quota_reservations WHERE tenant_id=%s ORDER BY module_key", (TENANT_ID,)).fetchall(),
            "usage_count": cursor.execute("SELECT count(*) FROM usage_events WHERE tenant_id=%s", (TENANT_ID,)).fetchone()[0],
            "activity_count": cursor.execute("SELECT count(*) FROM llm_activity WHERE tenant_id=%s AND status='completed'", (TENANT_ID,)).fetchone()[0],
            "private_trace_count": cursor.execute("SELECT count(*) FROM agent_trace_events WHERE tenant_id=%s AND redaction_level='full'", (TENANT_ID,)).fetchone()[0],
            "events": cursor.execute("SELECT event_type,payload_jsonb FROM workflow_events WHERE tenant_id=%s ORDER BY run_id,sequence", (TENANT_ID,)).fetchall(),
        }


def _app_url(admin_url: str) -> str:
    values = conninfo_to_dict(admin_url); values.update(user=APP_ROLE, password=APP_PASSWORD)
    return make_conninfo(**values)


def _encrypt(value: str) -> str:
    iv = bytes(range(12)); encrypted = AESGCM(bytes.fromhex(KEY_MATERIAL)).encrypt(iv, value.encode(), None)
    return f"aes-256-gcm:v1:{base64.b64encode(iv).decode()}:{base64.b64encode(encrypted[-16:]).decode()}:{base64.b64encode(encrypted[:-16]).decode()}"


def _cleanup(admin_url: str) -> None:
    if not admin_url:
        return
    with psycopg.connect(admin_url, autocommit=True) as connection:
        connection.execute("DELETE FROM tenants WHERE tenant_id=%s", (TENANT_ID,))
        connection.execute("DELETE FROM users WHERE user_id=%s", (USER_ID,))
