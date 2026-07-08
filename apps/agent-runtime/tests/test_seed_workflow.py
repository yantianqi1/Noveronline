from __future__ import annotations

import asyncio
import hashlib
import json
from concurrent.futures import ThreadPoolExecutor

import pytest
from temporalio.testing import WorkflowEnvironment
from temporalio.worker import Worker

from mirofish_agents.common.context import AgentContext
import mirofish_agents.temporal.seed as seed_module
from mirofish_agents.temporal.seed import (
    LLMFacilityArchiveCandidateRunner,
    PostgresTextArtifactWriter,
    PostgresSourceFileStatusWriter,
    PostgresArchiveCandidateWriter,
    PostgresWorkflowEventWriter,
    PostgresReadingNotesWriter,
    PostgresRuntimeFactsWriter,
    PostgresProjectReadinessUpdater,
    PostgresSeedAssetIndexer,
    PostgresSeedAnalysisWriter,
    S3CompatibleObjectStore,
    PostgresTextSegmentWriter,
    SEED_TASK_QUEUE,
    SeedPipelineWorkflow,
    _global_aggregator_from_env,
    _object_store_from_env,
    _sequential_reader_from_env,
    agent_profile_activity,
    archive_candidate_activity,
    finalize_seed_activity,
    global_aggregation_activity,
    index_assets_activity,
    parse_file_activity,
    persist_runtime_facts_activity,
    seed_pipeline_activity,
    segment_text_activity,
    sequential_reading_activity,
    run_seed_workflow_locally,
    worker_spec,
)
from mirofish_agents.seed.sequential_reader import LLMFacilityError, ModuleBindingResolution
from mirofish_agents.temporal.worker import worker_components_for_task_queue
from mirofish_agents.seed.global_aggregator import PostgresSeedAggregateSource


def _context() -> AgentContext:
    return AgentContext(
        tenant_id="tenant-1",
        project_id="project-1",
        run_id="run-1",
        workflow_type="seed_pipeline",
        actor_user_id="user-1",
        trace_id="trace-1",
        permissions={"seed_pipeline": ["run"]},
    )


def _minimal_text_pdf(text: str) -> bytes:
    escaped_text = text.replace("\\", "\\\\").replace("(", "\\(").replace(")", "\\)")
    objects = [
        b"<< /Type /Catalog /Pages 2 0 R >>",
        b"<< /Type /Pages /Kids [3 0 R] /Count 1 >>",
        b"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 612 792] /Resources << /Font << /F1 4 0 R >> >> /Contents 5 0 R >>",
        b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>",
        f"<< /Length {len(f'BT /F1 18 Tf 72 720 Td ({escaped_text}) Tj ET'.encode('ascii'))} >>\nstream\nBT /F1 18 Tf 72 720 Td ({escaped_text}) Tj ET\nendstream".encode(
            "ascii"
        ),
    ]
    output = bytearray(b"%PDF-1.4\n")
    offsets = [0]
    for index, body in enumerate(objects, start=1):
        offsets.append(len(output))
        output.extend(f"{index} 0 obj\n".encode("ascii"))
        output.extend(body)
        output.extend(b"\nendobj\n")
    xref_offset = len(output)
    output.extend(f"xref\n0 {len(objects) + 1}\n".encode("ascii"))
    output.extend(b"0000000000 65535 f \n")
    for offset in offsets[1:]:
        output.extend(f"{offset:010d} 00000 n \n".encode("ascii"))
    output.extend(
        f"trailer\n<< /Size {len(objects) + 1} /Root 1 0 R >>\nstartxref\n{xref_offset}\n%%EOF\n".encode(
            "ascii"
        )
    )
    return bytes(output)


def test_seed_pipeline_activity_requires_explicit_permission() -> None:
    context = _context().model_copy(update={"permissions": {}})

    result = seed_pipeline_activity(
        {
            "context": context.model_dump(),
            "upload_id": "upload-1",
            "options": {"language": "zh-CN"},
        }
    )

    assert result["status"] == "failed"
    assert result["error"]["code"] == "FORBIDDEN"
    assert result["tenant_id"] == "tenant-1"
    assert result["run_id"] == "run-1"


def test_seed_pipeline_skeleton_returns_explicit_pending_stage_without_outputs() -> None:
    result = run_seed_workflow_locally(
        {
            "context": _context().model_dump(),
            "upload_id": "upload-1",
            "options": {"language": "zh-CN"},
        }
    )

    assert result["status"] == "queued"
    assert result["tenant_id"] == "tenant-1"
    assert result["project_id"] == "project-1"
    assert result["run_id"] == "run-1"
    assert result["upload_id"] == "upload-1"
    assert result["next_stage"] == "parse_file"
    assert "seed_analysis" not in result
    assert "segments" not in result
    assert result["trace_events"] == [
        {
            "event_type": "workflow_stage_pending",
            "payload": {"stage": "parse_file", "activity": "seed_pipeline_activity"},
        }
    ]


def test_seed_workflow_locally_chains_uploaded_text_source_into_parse_and_segment_activities() -> None:
    workflow_writer = RecordingWorkflowEventWriter()
    artifact_writer = RecordingTextArtifactWriter()
    status_writer = RecordingSourceFileStatusWriter()
    segment_writer = RecordingTextSegmentWriter()
    object_store = InMemoryObjectStore(
        {
            "projects/project-1/source-files/upload-1/book.txt": (
                "第一章 雨夜\n雨声压住脚步。\n\n第二章 破晓\n光落在窗沿。\n"
            ).encode("utf-8")
        }
    )

    result = run_seed_workflow_locally(
        {
            "context": _context().model_dump(),
            "upload_id": "upload-1",
            "source_file_id": "file-1",
            "source_object_key": "projects/project-1/source-files/upload-1/book.txt",
            "source_mime_type": "text/plain",
            "options": {"language": "zh-CN"},
        },
        source_object_store=object_store,
        artifact_object_store=object_store,
        text_artifact_writer=artifact_writer,
        source_status_writer=status_writer,
        text_segment_writer=segment_writer,
        workflow_event_writer=workflow_writer,
    )

    assert result["status"] == "completed"
    assert result["stage"] == "segment_text"
    assert result["next_stage"] == "sequential_reading"
    assert result["segment_count"] == 2
    assert [segment["segment_order"] for segment in result["segments"]] == [0, 1]
    assert all("object_key" in segment for segment in result["segments"])
    assert "content" not in str(result["segments"])
    assert "text" not in result
    assert "content" not in result
    assert artifact_writer.artifacts[0]["source_file_id"] == "file-1"
    assert status_writer.statuses == [
        {
            "tenant_id": "tenant-1",
            "project_id": "project-1",
            "run_id": "run-1",
            "source_file_id": "file-1",
            "parse_status": "parsed",
        }
    ]
    assert segment_writer.segments[0]["tenant_id"] == "tenant-1"
    assert segment_writer.segments[0]["project_id"] == "project-1"
    assert segment_writer.segments[0]["run_id"] == "run-1"
    assert [segment["chapter_guess"] for segment in segment_writer.segments] == ["第一章", "第二章"]
    assert [
        write[0] for write in object_store.writes
    ] == [
        "projects/project-1/seed-runs/run-1/extracted/file-1.txt",
        "projects/project-1/seed-runs/run-1/segments/0000.txt",
        "projects/project-1/seed-runs/run-1/segments/0001.txt",
    ]
    assert workflow_writer.events == [
        {
            "tenant_id": "tenant-1",
            "project_id": "project-1",
            "run_id": "run-1",
            "workflow_type": "seed_pipeline",
            "event_type": "seed.stage.pending",
            "payload": {
                "stage": "parse_file",
                "status": "pending",
                "activity": "seed_pipeline_activity",
                "upload_id": "upload-1",
            },
        },
        {
            "tenant_id": "tenant-1",
            "project_id": "project-1",
            "run_id": "run-1",
            "workflow_type": "seed_pipeline",
            "event_type": "seed.stage.completed",
            "payload": {
                "stage": "parse_file",
                "status": "completed",
                "activity": "parse_file_activity",
                "source_file_id": "file-1",
                "artifact_type": "extracted_text",
                "char_count": 30,
                "line_count": 5,
            },
        },
        {
            "tenant_id": "tenant-1",
            "project_id": "project-1",
            "run_id": "run-1",
            "workflow_type": "seed_pipeline",
            "event_type": "seed.stage.pending",
            "payload": {
                "stage": "segment_text",
                "status": "pending",
                "activity": "segment_text_activity",
                "source_file_id": "file-1",
                "artifact_type": "extracted_text",
            },
        },
        {
            "tenant_id": "tenant-1",
            "project_id": "project-1",
            "run_id": "run-1",
            "workflow_type": "seed_pipeline",
            "event_type": "seed.stage.completed",
            "payload": {
                "stage": "segment_text",
                "status": "completed",
                "activity": "segment_text_activity",
                "source_file_id": "file-1",
                "segment_count": 2,
            },
        },
    ]


def test_seed_workflow_locally_reuses_env_workflow_event_writer_for_chained_stages(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    workflow_writer = RecordingWorkflowEventWriter()
    artifact_writer = RecordingTextArtifactWriter()
    segment_writer = RecordingTextSegmentWriter()
    object_store = InMemoryObjectStore(
        {
            "projects/project-1/source-files/upload-1/book.txt": (
                "第一章 雨夜\n雨声压住脚步。\n\n第二章 破晓\n光落在窗沿。\n"
            ).encode("utf-8")
        }
    )
    monkeypatch.setattr(seed_module, "_workflow_event_writer_from_env", lambda: workflow_writer)

    result = run_seed_workflow_locally(
        {
            "context": _context().model_dump(),
            "upload_id": "upload-1",
            "source_file_id": "file-1",
            "source_object_key": "projects/project-1/source-files/upload-1/book.txt",
            "source_mime_type": "text/plain",
            "options": {"language": "zh-CN"},
        },
        source_object_store=object_store,
        artifact_object_store=object_store,
        text_artifact_writer=artifact_writer,
        text_segment_writer=segment_writer,
    )

    assert result["status"] == "completed"
    assert [event["event_type"] for event in workflow_writer.events] == [
        "seed.stage.pending",
        "seed.stage.completed",
        "seed.stage.pending",
        "seed.stage.completed",
    ]
    assert [event["payload"]["stage"] for event in workflow_writer.events] == [
        "parse_file",
        "parse_file",
        "segment_text",
        "segment_text",
    ]


def test_seed_workflow_locally_reuses_workflow_status_writer_for_chained_stages(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    workflow_writer = RecordingWorkflowEventWriter()
    workflow_status_writer = RecordingWorkflowRunStatusWriter()
    artifact_writer = RecordingTextArtifactWriter()
    source_status_writer = RecordingSourceFileStatusWriter()
    segment_writer = RecordingTextSegmentWriter()
    object_store = InMemoryObjectStore(
        {
            "projects/project-1/source-files/upload-1/book.txt": (
                "第一章 雨夜\n雨声压住脚步。\n\n第二章 破晓\n光落在窗沿。\n"
            ).encode("utf-8")
        }
    )
    monkeypatch.setattr(seed_module, "_reading_notes_writer_from_env", lambda: None)

    result = run_seed_workflow_locally(
        {
            "context": _context().model_dump(),
            "upload_id": "upload-1",
            "source_file_id": "file-1",
            "source_object_key": "projects/project-1/source-files/upload-1/book.txt",
            "source_mime_type": "text/plain",
            "options": {"language": "zh-CN"},
        },
        source_object_store=object_store,
        artifact_object_store=object_store,
        text_artifact_writer=artifact_writer,
        source_status_writer=source_status_writer,
        text_segment_writer=segment_writer,
        llm_reader=SuccessfulSequentialReader(),
        reading_notes_writer=None,
        workflow_event_writer=workflow_writer,
        workflow_status_writer=workflow_status_writer,
    )

    assert result["status"] == "failed"
    assert result["stage"] == "sequential_reading"
    assert result["error"]["code"] == "READING_NOTES_WRITER_UNCONFIGURED"
    assert workflow_status_writer.running == [
        {
            "tenant_id": "tenant-1",
            "project_id": "project-1",
            "run_id": "run-1",
        }
    ]
    assert workflow_status_writer.failed == [
        {
            "tenant_id": "tenant-1",
            "project_id": "project-1",
            "run_id": "run-1",
            "code": "READING_NOTES_WRITER_UNCONFIGURED",
            "message": "reading notes writer is unconfigured",
        }
    ]
    assert workflow_status_writer.completed == []
    public_body = json.dumps(
        [result, workflow_writer.events, workflow_status_writer.running, workflow_status_writer.failed],
        ensure_ascii=False,
    )
    assert "projects/project-1/source-files/upload-1/book.txt" not in public_body
    assert "projects/project-1/seed-runs/run-1/segments" not in public_body
    assert "雨声压住脚步" not in public_body
    assert "api_key" not in public_body
    assert "credential_ref" not in public_body


def test_temporal_seed_workflow_uses_env_workflow_event_writer_for_real_worker_handoff(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    asyncio.run(_run_temporal_seed_workflow_uses_env_workflow_event_writer_for_real_worker_handoff(monkeypatch))


async def _run_temporal_seed_workflow_uses_env_workflow_event_writer_for_real_worker_handoff(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    source_object_key = "projects/project-1/source-files/upload-1/book.txt"
    source_bytes = "第一章 雨夜\n雨声压住脚步。\n\n第二章 破晓\n光落在窗沿。\n".encode("utf-8")
    object_store = InMemoryObjectStore({source_object_key: source_bytes})
    workflow_writer = RecordingWorkflowEventWriter()
    artifact_writer = RecordingTextArtifactWriter()
    status_writer = RecordingSourceFileStatusWriter()
    segment_writer = RecordingTextSegmentWriter()

    monkeypatch.delenv("DATABASE_URL", raising=False)
    monkeypatch.delenv("LLM_CREDENTIAL_ENCRYPTION_KEY", raising=False)
    monkeypatch.setattr(seed_module, "_workflow_event_writer_from_env", lambda: workflow_writer)
    monkeypatch.setattr(seed_module, "_object_store_from_env", lambda: object_store)
    monkeypatch.setattr(seed_module, "_text_artifact_writer_from_env", lambda: artifact_writer)
    monkeypatch.setattr(seed_module, "_source_file_status_writer_from_env", lambda: status_writer)
    monkeypatch.setattr(seed_module, "_text_segment_writer_from_env", lambda: segment_writer)
    monkeypatch.setattr(seed_module, "_reading_notes_writer_from_env", lambda: None)
    monkeypatch.setattr(seed_module, "_sequential_reader_from_env", lambda: None)

    payload = {
        "context": _context().model_dump(),
        "upload_id": "upload-1",
        "source_file_id": "file-1",
        "source_object_key": source_object_key,
        "source_mime_type": "text/plain; charset=utf-8",
        "source_size_bytes": len(source_bytes),
        "source_sha256": hashlib.sha256(source_bytes).hexdigest(),
        "options": {"language": "zh-CN"},
    }
    env = await WorkflowEnvironment.start_time_skipping()
    try:
        with ThreadPoolExecutor(max_workers=4) as activity_executor:
            async with Worker(
                env.client,
                task_queue="seed-env-writer-test",
                workflows=[SeedPipelineWorkflow],
                activities=[
                    seed_pipeline_activity,
                    parse_file_activity,
                    segment_text_activity,
                    sequential_reading_activity,
                ],
                activity_executor=activity_executor,
            ):
                result = await env.client.execute_workflow(
                    SeedPipelineWorkflow.run,
                    payload,
                    id="seed-env-writer-test-run",
                    task_queue="seed-env-writer-test",
                )
    finally:
        await env.shutdown()

    assert result["status"] == "failed"
    assert result["stage"] == "sequential_reading"
    assert result["error"]["code"] == "READING_NOTES_WRITER_UNCONFIGURED"
    assert status_writer.statuses[0]["parse_status"] == "parsed"
    assert artifact_writer.artifacts[0]["source_file_id"] == "file-1"
    assert len(segment_writer.segments) == 2
    assert [event["event_type"] for event in workflow_writer.events] == [
        "seed.stage.pending",
        "seed.stage.completed",
        "seed.stage.pending",
        "seed.stage.completed",
        "seed.stage.failed",
    ]
    assert [event["payload"]["stage"] for event in workflow_writer.events] == [
        "parse_file",
        "parse_file",
        "segment_text",
        "segment_text",
        "sequential_reading",
    ]
    public_event_body = json.dumps(workflow_writer.events, ensure_ascii=False, sort_keys=True)
    for forbidden in (
        "source_object_key",
        "artifact_object_key",
        '"object_key"',
        "projects/project-1/source-files",
        "projects/project-1/seed-runs/run-1/extracted",
        "projects/project-1/seed-runs/run-1/segments",
        "雨声压住脚步",
        "credential_ref",
    ):
        assert forbidden not in public_event_body


def test_seed_workflow_local_events_do_not_expose_object_storage_keys() -> None:
    workflow_writer = RecordingWorkflowEventWriter()
    artifact_writer = RecordingTextArtifactWriter()
    segment_writer = RecordingTextSegmentWriter()
    object_store = InMemoryObjectStore(
        {
            "projects/project-1/source-files/upload-1/book.txt": (
                "第一章 雨夜\n雨声压住脚步。\n\n第二章 破晓\n光落在窗沿。\n"
            ).encode("utf-8")
        }
    )

    result = run_seed_workflow_locally(
        {
            "context": _context().model_dump(),
            "upload_id": "upload-1",
            "source_file_id": "file-1",
            "source_object_key": "projects/project-1/source-files/upload-1/book.txt",
            "source_mime_type": "text/plain",
            "options": {"language": "zh-CN"},
        },
        source_object_store=object_store,
        artifact_object_store=object_store,
        text_artifact_writer=artifact_writer,
        text_segment_writer=segment_writer,
        workflow_event_writer=workflow_writer,
    )

    assert result["status"] == "completed"
    public_event_body = json.dumps(workflow_writer.events, ensure_ascii=False, sort_keys=True)
    for forbidden in (
        "source_object_key",
        "artifact_object_key",
        '"object_key"',
        "projects/project-1/source-files",
        "projects/project-1/seed-runs/run-1/extracted",
        "projects/project-1/seed-runs/run-1/segments",
    ):
        assert forbidden not in public_event_body


def test_seed_workflow_locally_can_continue_segments_into_sequential_reading() -> None:
    workflow_writer = RecordingWorkflowEventWriter()
    artifact_writer = RecordingTextArtifactWriter()
    segment_writer = RecordingTextSegmentWriter()
    notes_writer = RecordingReadingNotesWriter()
    object_store = InMemoryObjectStore(
        {
            "projects/project-1/source-files/upload-1/book.txt": (
                "第一章 雨夜\n雨声压住脚步。\n\n第二章 破晓\n光落在窗沿。\n"
            ).encode("utf-8")
        }
    )

    result = run_seed_workflow_locally(
        {
            "context": _context().model_dump(),
            "upload_id": "upload-1",
            "source_file_id": "file-1",
            "source_object_key": "projects/project-1/source-files/upload-1/book.txt",
            "source_mime_type": "text/plain",
            "options": {"language": "zh-CN"},
        },
        source_object_store=object_store,
        artifact_object_store=object_store,
        text_artifact_writer=artifact_writer,
        text_segment_writer=segment_writer,
        llm_reader=EchoSequentialReader(),
        reading_notes_writer=notes_writer,
        workflow_event_writer=workflow_writer,
    )

    assert result["status"] == "completed"
    assert result["stage"] == "sequential_reading"
    assert result["next_stage"] == "persist_runtime_facts"
    assert result["segment_count"] == 2
    assert result["note_count"] == 2
    assert notes_writer.passes[0]["module_key"] == "sequential_reading"
    assert [note["segment_id"] for note in notes_writer.passes[0]["notes"]] == [
        segment["segment_id"] for segment in segment_writer.segments
    ]
    assert workflow_writer.events[-1]["event_type"] == "seed.stage.completed"
    assert workflow_writer.events[-1]["payload"]["stage"] == "sequential_reading"
    assert "雨声压住脚步" not in str(result)
    assert "object_key" not in workflow_writer.events[-1]["payload"]


def test_seed_workflow_locally_can_continue_runtime_facts_into_global_aggregation() -> None:
    workflow_writer = RecordingWorkflowEventWriter()
    artifact_writer = RecordingTextArtifactWriter()
    segment_writer = RecordingTextSegmentWriter()
    notes_writer = RecordingReadingNotesWriter()
    facts_writer = RecordingRuntimeFactsWriter()
    aggregator = RecordingGlobalAggregator()
    object_store = InMemoryObjectStore(
        {
            "projects/project-1/source-files/upload-1/book.txt": (
                "第一章 雨夜\n雨声压住脚步。\n\n第二章 破晓\n光落在窗沿。\n"
            ).encode("utf-8")
        }
    )

    result = run_seed_workflow_locally(
        {
            "context": _context().model_dump(),
            "upload_id": "upload-1",
            "source_file_id": "file-1",
            "source_object_key": "projects/project-1/source-files/upload-1/book.txt",
            "source_mime_type": "text/plain",
            "options": {"language": "zh-CN"},
        },
        source_object_store=object_store,
        artifact_object_store=object_store,
        text_artifact_writer=artifact_writer,
        text_segment_writer=segment_writer,
        llm_reader=EchoSequentialReader(),
        reading_notes_writer=notes_writer,
        runtime_facts_writer=facts_writer,
        global_aggregator=aggregator,
        workflow_event_writer=workflow_writer,
    )

    assert result["status"] == "completed"
    assert result["stage"] == "global_aggregation"
    assert result["next_stage"] == "story_ontology"
    assert result["module_key"] == "anchor_point_summary"
    assert result["segment_count"] == 2
    assert result["summary_count"] == 1
    assert facts_writer.calls[0]["run_id"] == "run-1"
    assert aggregator.calls == [
        {
            "tenant_id": "tenant-1",
            "project_id": "project-1",
            "run_id": "run-1",
            "module_key": "anchor_point_summary",
        }
    ]
    assert [event["payload"]["stage"] for event in workflow_writer.events] == [
        "parse_file",
        "parse_file",
        "segment_text",
        "segment_text",
        "sequential_reading",
        "persist_runtime_facts",
        "global_aggregation",
    ]
    assert "雨声压住脚步" not in str(result)
    assert "雨声压住脚步" not in str(workflow_writer.events)
    assert "private aggregate" not in str(result)
    assert "private aggregate" not in str(workflow_writer.events)


def test_seed_workflow_locally_can_continue_global_aggregation_into_fail_closed_ontology() -> None:
    workflow_writer = RecordingWorkflowEventWriter()
    object_store = InMemoryObjectStore(
        {
            "projects/project-1/source-files/upload-1/book.txt": (
                "第一章 雨夜\n雨声压住脚步。\n\n第二章 破晓\n光落在窗沿。\n"
            ).encode("utf-8")
        }
    )

    result = run_seed_workflow_locally(
        {
            "context": _context().model_dump(),
            "upload_id": "upload-1",
            "source_file_id": "file-1",
            "source_object_key": "projects/project-1/source-files/upload-1/book.txt",
            "source_mime_type": "text/plain",
            "options": {"language": "zh-CN"},
        },
        source_object_store=object_store,
        artifact_object_store=object_store,
        text_artifact_writer=RecordingTextArtifactWriter(),
        text_segment_writer=RecordingTextSegmentWriter(),
        llm_reader=EchoSequentialReader(),
        reading_notes_writer=RecordingReadingNotesWriter(),
        runtime_facts_writer=RecordingRuntimeFactsWriter(),
        global_aggregator=RecordingGlobalAggregator(),
        workflow_event_writer=workflow_writer,
        continue_to_ontology=True,
    )

    assert result["status"] == "failed"
    assert result["stage"] == "story_ontology"
    assert result["module_key"] == "story_ontology"
    assert result["error"]["code"] == "ONTOLOGY_RUNNER_UNCONFIGURED"
    assert [event["payload"]["stage"] for event in workflow_writer.events] == [
        "parse_file",
        "parse_file",
        "segment_text",
        "segment_text",
        "sequential_reading",
        "persist_runtime_facts",
        "global_aggregation",
        "story_ontology",
    ]
    assert "雨声压住脚步" not in str(result)
    assert "雨声压住脚步" not in str(workflow_writer.events)
    assert "private aggregate" not in str(result)
    assert "private aggregate" not in str(workflow_writer.events)


def test_seed_workflow_locally_can_continue_ontology_into_fail_closed_entity_resolution() -> None:
    workflow_writer = RecordingWorkflowEventWriter()
    object_store = InMemoryObjectStore(
        {
            "projects/project-1/source-files/upload-1/book.txt": (
                "第一章 雨夜\n雨声压住脚步。\n\n第二章 破晓\n光落在窗沿。\n"
            ).encode("utf-8")
        }
    )

    result = run_seed_workflow_locally(
        {
            "context": _context().model_dump(),
            "upload_id": "upload-1",
            "source_file_id": "file-1",
            "source_object_key": "projects/project-1/source-files/upload-1/book.txt",
            "source_mime_type": "text/plain",
            "options": {"language": "zh-CN"},
        },
        source_object_store=object_store,
        artifact_object_store=object_store,
        text_artifact_writer=RecordingTextArtifactWriter(),
        text_segment_writer=RecordingTextSegmentWriter(),
        llm_reader=EchoSequentialReader(),
        reading_notes_writer=RecordingReadingNotesWriter(),
        runtime_facts_writer=RecordingRuntimeFactsWriter(),
        global_aggregator=RecordingGlobalAggregator(),
        ontology_runner=RecordingOntologyRunner(),
        workflow_event_writer=workflow_writer,
        continue_to_ontology=True,
        continue_to_entity_resolution=True,
    )

    assert result["status"] == "failed"
    assert result["stage"] == "entity_resolution"
    assert result["module_key"] == "entity_resolution"
    assert result["error"]["code"] == "ENTITY_RESOLUTION_RUNNER_UNCONFIGURED"
    assert [event["payload"]["stage"] for event in workflow_writer.events] == [
        "parse_file",
        "parse_file",
        "segment_text",
        "segment_text",
        "sequential_reading",
        "persist_runtime_facts",
        "global_aggregation",
        "story_ontology",
        "entity_resolution",
    ]
    assert "雨声压住脚步" not in str(result)
    assert "雨声压住脚步" not in str(workflow_writer.events)
    assert "private ontology body" not in str(result)
    assert "private ontology body" not in str(workflow_writer.events)


def test_seed_workflow_locally_can_continue_entity_resolution_into_fail_closed_agent_profiles() -> None:
    workflow_writer = RecordingWorkflowEventWriter()
    object_store = InMemoryObjectStore(
        {
            "projects/project-1/source-files/upload-1/book.txt": (
                "第一章 雨夜\n雨声压住脚步。\n\n第二章 破晓\n光落在窗沿。\n"
            ).encode("utf-8")
        }
    )

    result = run_seed_workflow_locally(
        {
            "context": _context().model_dump(),
            "upload_id": "upload-1",
            "source_file_id": "file-1",
            "source_object_key": "projects/project-1/source-files/upload-1/book.txt",
            "source_mime_type": "text/plain",
            "options": {"language": "zh-CN"},
        },
        source_object_store=object_store,
        artifact_object_store=object_store,
        text_artifact_writer=RecordingTextArtifactWriter(),
        text_segment_writer=RecordingTextSegmentWriter(),
        llm_reader=EchoSequentialReader(),
        reading_notes_writer=RecordingReadingNotesWriter(),
        runtime_facts_writer=RecordingRuntimeFactsWriter(),
        global_aggregator=RecordingGlobalAggregator(),
        ontology_runner=RecordingOntologyRunner(),
        entity_resolution_runner=RecordingEntityResolutionRunner(),
        workflow_event_writer=workflow_writer,
        continue_to_ontology=True,
        continue_to_entity_resolution=True,
        continue_to_agent_profiles=True,
    )

    assert result["status"] == "failed"
    assert result["stage"] == "agent_profiles"
    assert result["module_key"] == "character_agent_profile"
    assert result["error"]["code"] == "AGENT_PROFILE_RUNNER_UNCONFIGURED"
    assert [event["payload"]["stage"] for event in workflow_writer.events] == [
        "parse_file",
        "parse_file",
        "segment_text",
        "segment_text",
        "sequential_reading",
        "persist_runtime_facts",
        "global_aggregation",
        "story_ontology",
        "entity_resolution",
        "agent_profiles",
    ]
    assert "雨声压住脚步" not in str(result)
    assert "雨声压住脚步" not in str(workflow_writer.events)
    assert "private resolution body" not in str(result)
    assert "private resolution body" not in str(workflow_writer.events)


def test_seed_workflow_locally_can_continue_agent_profiles_into_fail_closed_archive_candidates() -> None:
    workflow_writer = RecordingWorkflowEventWriter()
    object_store = InMemoryObjectStore(
        {
            "projects/project-1/source-files/upload-1/book.txt": (
                "第一章 雨夜\n雨声压住脚步。\n\n第二章 破晓\n光落在窗沿。\n"
            ).encode("utf-8")
        }
    )

    result = run_seed_workflow_locally(
        {
            "context": _context().model_dump(),
            "upload_id": "upload-1",
            "source_file_id": "file-1",
            "source_object_key": "projects/project-1/source-files/upload-1/book.txt",
            "source_mime_type": "text/plain",
            "options": {"language": "zh-CN"},
        },
        source_object_store=object_store,
        artifact_object_store=object_store,
        text_artifact_writer=RecordingTextArtifactWriter(),
        text_segment_writer=RecordingTextSegmentWriter(),
        llm_reader=EchoSequentialReader(),
        reading_notes_writer=RecordingReadingNotesWriter(),
        runtime_facts_writer=RecordingRuntimeFactsWriter(),
        global_aggregator=RecordingGlobalAggregator(),
        ontology_runner=RecordingOntologyRunner(),
        entity_resolution_runner=RecordingEntityResolutionRunner(),
        agent_profile_runner=RecordingAgentProfileRunner(),
        workflow_event_writer=workflow_writer,
        continue_to_ontology=True,
        continue_to_entity_resolution=True,
        continue_to_agent_profiles=True,
        continue_to_archive_candidates=True,
    )

    assert result["status"] == "failed"
    assert result["stage"] == "archive_candidates"
    assert result["module_key"] == "narrative_archives"
    assert result["error"]["code"] == "ARCHIVE_CANDIDATE_RUNNER_UNCONFIGURED"
    assert [event["payload"]["stage"] for event in workflow_writer.events] == [
        "parse_file",
        "parse_file",
        "segment_text",
        "segment_text",
        "sequential_reading",
        "persist_runtime_facts",
        "global_aggregation",
        "story_ontology",
        "entity_resolution",
        "agent_profiles",
        "archive_candidates",
    ]
    assert "雨声压住脚步" not in str(result)
    assert "雨声压住脚步" not in str(workflow_writer.events)
    assert "private profile body" not in str(result)
    assert "private profile body" not in str(workflow_writer.events)


def test_seed_workflow_locally_can_continue_archive_candidates_into_fail_closed_asset_index() -> None:
    workflow_writer = RecordingWorkflowEventWriter()
    object_store = InMemoryObjectStore(
        {
            "projects/project-1/source-files/upload-1/book.txt": (
                "第一章 雨夜\n雨声压住脚步。\n\n第二章 破晓\n光落在窗沿。\n"
            ).encode("utf-8")
        }
    )

    result = run_seed_workflow_locally(
        {
            "context": _context().model_dump(),
            "upload_id": "upload-1",
            "source_file_id": "file-1",
            "source_object_key": "projects/project-1/source-files/upload-1/book.txt",
            "source_mime_type": "text/plain",
            "options": {"language": "zh-CN"},
        },
        source_object_store=object_store,
        artifact_object_store=object_store,
        text_artifact_writer=RecordingTextArtifactWriter(),
        text_segment_writer=RecordingTextSegmentWriter(),
        llm_reader=EchoSequentialReader(),
        reading_notes_writer=RecordingReadingNotesWriter(),
        runtime_facts_writer=RecordingRuntimeFactsWriter(),
        global_aggregator=RecordingGlobalAggregator(),
        ontology_runner=RecordingOntologyRunner(),
        entity_resolution_runner=RecordingEntityResolutionRunner(),
        agent_profile_runner=RecordingAgentProfileRunner(),
        archive_candidate_runner=RecordingArchiveCandidateRunner(),
        workflow_event_writer=workflow_writer,
        continue_to_ontology=True,
        continue_to_entity_resolution=True,
        continue_to_agent_profiles=True,
        continue_to_archive_candidates=True,
        continue_to_index_assets=True,
    )

    assert result["status"] == "failed"
    assert result["stage"] == "index_assets"
    assert result["error"]["code"] == "ASSET_INDEXER_UNCONFIGURED"
    assert [event["payload"]["stage"] for event in workflow_writer.events] == [
        "parse_file",
        "parse_file",
        "segment_text",
        "segment_text",
        "sequential_reading",
        "persist_runtime_facts",
        "global_aggregation",
        "story_ontology",
        "entity_resolution",
        "agent_profiles",
        "archive_candidates",
        "index_assets",
    ]
    assert "雨声压住脚步" not in str(result)
    assert "雨声压住脚步" not in str(workflow_writer.events)
    assert "private archive candidate body" not in str(result)
    assert "private archive candidate body" not in str(workflow_writer.events)


def test_seed_workflow_locally_can_continue_asset_index_into_fail_closed_finalize() -> None:
    workflow_writer = RecordingWorkflowEventWriter()
    object_store = InMemoryObjectStore(
        {
            "projects/project-1/source-files/upload-1/book.txt": (
                "第一章 雨夜\n雨声压住脚步。\n\n第二章 破晓\n光落在窗沿。\n"
            ).encode("utf-8")
        }
    )

    result = run_seed_workflow_locally(
        {
            "context": _context().model_dump(),
            "upload_id": "upload-1",
            "source_file_id": "file-1",
            "source_object_key": "projects/project-1/source-files/upload-1/book.txt",
            "source_mime_type": "text/plain",
            "options": {"language": "zh-CN"},
        },
        source_object_store=object_store,
        artifact_object_store=object_store,
        text_artifact_writer=RecordingTextArtifactWriter(),
        text_segment_writer=RecordingTextSegmentWriter(),
        llm_reader=EchoSequentialReader(),
        reading_notes_writer=RecordingReadingNotesWriter(),
        runtime_facts_writer=RecordingRuntimeFactsWriter(),
        global_aggregator=RecordingGlobalAggregator(),
        ontology_runner=RecordingOntologyRunner(),
        entity_resolution_runner=RecordingEntityResolutionRunner(),
        agent_profile_runner=RecordingAgentProfileRunner(),
        archive_candidate_runner=RecordingArchiveCandidateRunner(),
        asset_indexer=RecordingAssetIndexer(),
        workflow_event_writer=workflow_writer,
        continue_to_ontology=True,
        continue_to_entity_resolution=True,
        continue_to_agent_profiles=True,
        continue_to_archive_candidates=True,
        continue_to_index_assets=True,
        continue_to_finalize=True,
    )

    assert result["status"] == "failed"
    assert result["stage"] == "finalize"
    assert result["error"]["code"] == "PROJECT_READINESS_UPDATER_UNCONFIGURED"
    assert [event["payload"]["stage"] for event in workflow_writer.events] == [
        "parse_file",
        "parse_file",
        "segment_text",
        "segment_text",
        "sequential_reading",
        "persist_runtime_facts",
        "global_aggregation",
        "story_ontology",
        "entity_resolution",
        "agent_profiles",
        "archive_candidates",
        "index_assets",
        "finalize",
    ]
    assert "雨声压住脚步" not in str(result)
    assert "private readiness body" not in str(result)
    assert "private readiness body" not in str(workflow_writer.events)


def test_persist_runtime_facts_activity_writes_structured_canon_without_public_evidence() -> None:
    workflow_writer = RecordingWorkflowEventWriter()
    facts_writer = RecordingRuntimeFactsWriter()
    segment_id = "11111111-1111-1111-1111-111111111111"

    result = persist_runtime_facts_activity(
        {
            "context": _context().model_dump(),
            "reading_notes": [
                {
                    "segment_id": segment_id,
                    "summary": "雨夜开场。",
                    "payload_jsonb": {
                        "characters": [
                            {
                                "name": "林澈",
                                "aliases": ["小林"],
                                "labels": ["潜逃者", {"label": "雨夜核心人物", "label_type": "narrative_role"}],
                                "importance": "major",
                                "state_update": "在雨夜保持警惕。",
                                "evidence": "林澈按住伞柄，听见雨声压住脚步。",
                            }
                        ],
                        "organizations": [
                            {
                                "name": "巡夜司",
                                "aliases": [],
                                "labels": ["执法组织"],
                                "importance": "supporting",
                                "state_update": "负责城中夜巡。",
                                "evidence": "巡夜司的灯从街尾晃过。",
                            }
                        ],
                        "relationships": [
                            {
                                "source": "林澈",
                                "target": "巡夜司",
                                "type": "tracked_by",
                                "summary": "巡夜司正在追踪林澈。",
                                "evidence": "巡夜司的灯从街尾晃过，林澈压低了伞沿。",
                            }
                        ],
                        "plot_threads": [
                            {
                                "title": "雨夜追踪",
                                "status": "open",
                                "summary": "巡夜司与林澈的雨夜追踪线开启。",
                                "evidence": "巡夜司的灯从街尾晃过。",
                            }
                        ],
                        "narrative_arcs": [
                            {
                                "title": "雨夜压迫",
                                "arc_type": "tension",
                                "summary": "雨夜追踪把城市压迫感推到台前。",
                                "evidence": "雨声压住脚步。",
                            }
                        ],
                        "volume_summaries": [
                            {
                                "volume_key": "vol-1",
                                "title": "雨城卷",
                                "summary": "开篇卷建立雨夜追踪与城市压迫。",
                                "evidence": "雨声压住脚步。",
                            }
                        ],
                        "world_rules": [
                            {
                                "rule": "雨夜会削弱听觉判断。",
                                "category": "environment",
                                "evidence": "雨声压住脚步。",
                            }
                        ],
                        "events": [
                            {
                                "entity_name": "林澈",
                                "event_kind": "action",
                                "summary": "林澈在雨夜躲避巡夜司。",
                                "evidence": "林澈压低了伞沿。",
                            },
                            {
                                "scope": "world",
                                "event_kind": "environment",
                                "summary": "雨夜让城中追踪变得困难。",
                                "evidence": "雨声压住脚步。",
                            },
                            {
                                "event_type": "relationship",
                                "source": "林澈",
                                "target": "巡夜司",
                                "relationship_type": "tracked_by",
                                "summary": "巡夜司开始锁定林澈踪迹。",
                                "evidence": "巡夜司的灯从街尾晃过。",
                            },
                        ],
                        "consistency_notes": [
                            {
                                "note_type": "timeline",
                                "severity": "warning",
                                "summary": "林澈此前未提过会避开巡夜司。",
                                "evidence": "林澈压低了伞沿。",
                            }
                        ],
                    },
                }
            ],
        },
        runtime_facts_writer=facts_writer,
        workflow_event_writer=workflow_writer,
    )

    assert result == {
        "tenant_id": "tenant-1",
        "project_id": "project-1",
        "run_id": "run-1",
        "workflow_type": "seed_pipeline",
        "upload_id": None,
        "status": "completed",
        "stage": "persist_runtime_facts",
        "next_stage": "global_aggregation",
        "entity_count": 2,
        "entity_label_count": 3,
        "relationship_count": 1,
        "plot_thread_count": 1,
        "thread_lifecycle_count": 1,
        "narrative_arc_count": 1,
        "volume_summary_count": 1,
        "world_rule_count": 1,
        "character_event_count": 1,
        "world_event_count": 1,
        "relationship_event_count": 1,
        "consistency_note_count": 1,
        "segment_summary_count": 1,
        "stage_event_persisted": True,
    }
    assert facts_writer.calls == [
        {
            "tenant_id": "tenant-1",
            "project_id": "project-1",
            "run_id": "run-1",
            "reading_notes": [
                {
                    "segment_id": segment_id,
                    "summary": "雨夜开场。",
                    "payload_jsonb": {
                        "characters": [
                            {
                                "name": "林澈",
                                "aliases": ["小林"],
                                "labels": ["潜逃者", {"label": "雨夜核心人物", "label_type": "narrative_role"}],
                                "importance": "major",
                                "state_update": "在雨夜保持警惕。",
                                "evidence": "林澈按住伞柄，听见雨声压住脚步。",
                            }
                        ],
                        "organizations": [
                            {
                                "name": "巡夜司",
                                "aliases": [],
                                "labels": ["执法组织"],
                                "importance": "supporting",
                                "state_update": "负责城中夜巡。",
                                "evidence": "巡夜司的灯从街尾晃过。",
                            }
                        ],
                        "relationships": [
                            {
                                "source": "林澈",
                                "target": "巡夜司",
                                "type": "tracked_by",
                                "summary": "巡夜司正在追踪林澈。",
                                "evidence": "巡夜司的灯从街尾晃过，林澈压低了伞沿。",
                            }
                        ],
                        "plot_threads": [
                            {
                                "title": "雨夜追踪",
                                "status": "open",
                                "summary": "巡夜司与林澈的雨夜追踪线开启。",
                                "evidence": "巡夜司的灯从街尾晃过。",
                            }
                        ],
                        "narrative_arcs": [
                            {
                                "title": "雨夜压迫",
                                "arc_type": "tension",
                                "summary": "雨夜追踪把城市压迫感推到台前。",
                                "evidence": "雨声压住脚步。",
                            }
                        ],
                        "volume_summaries": [
                            {
                                "volume_key": "vol-1",
                                "title": "雨城卷",
                                "summary": "开篇卷建立雨夜追踪与城市压迫。",
                                "evidence": "雨声压住脚步。",
                            }
                        ],
                        "world_rules": [
                            {
                                "rule": "雨夜会削弱听觉判断。",
                                "category": "environment",
                                "evidence": "雨声压住脚步。",
                            }
                        ],
                        "events": [
                            {
                                "entity_name": "林澈",
                                "event_kind": "action",
                                "summary": "林澈在雨夜躲避巡夜司。",
                                "evidence": "林澈压低了伞沿。",
                            },
                            {
                                "scope": "world",
                                "event_kind": "environment",
                                "summary": "雨夜让城中追踪变得困难。",
                                "evidence": "雨声压住脚步。",
                            },
                            {
                                "event_type": "relationship",
                                "source": "林澈",
                                "target": "巡夜司",
                                "relationship_type": "tracked_by",
                                "summary": "巡夜司开始锁定林澈踪迹。",
                                "evidence": "巡夜司的灯从街尾晃过。",
                            },
                        ],
                        "consistency_notes": [
                            {
                                "note_type": "timeline",
                                "severity": "warning",
                                "summary": "林澈此前未提过会避开巡夜司。",
                                "evidence": "林澈压低了伞沿。",
                            }
                        ],
                    },
                }
            ],
        }
    ]
    assert workflow_writer.events[-1] == {
        "tenant_id": "tenant-1",
        "project_id": "project-1",
        "run_id": "run-1",
        "workflow_type": "seed_pipeline",
        "event_type": "seed.stage.completed",
        "payload": {
            "stage": "persist_runtime_facts",
            "status": "completed",
            "activity": "persist_runtime_facts_activity",
            "entity_count": 2,
            "entity_label_count": 3,
            "relationship_count": 1,
            "plot_thread_count": 1,
            "thread_lifecycle_count": 1,
            "narrative_arc_count": 1,
            "volume_summary_count": 1,
            "world_rule_count": 1,
            "character_event_count": 1,
            "world_event_count": 1,
            "relationship_event_count": 1,
            "consistency_note_count": 1,
            "segment_summary_count": 1,
        },
    }
    assert "雨声压住脚步" not in str(result)
    assert "雨声压住脚步" not in str(workflow_writer.events)
    assert "巡夜司的灯" not in str(result)
    assert "巡夜司的灯" not in str(workflow_writer.events)
    assert "林澈压低了伞沿" not in str(result)
    assert "林澈压低了伞沿" not in str(workflow_writer.events)
    assert "雨夜开场" not in str(result)
    assert "雨夜开场" not in str(workflow_writer.events)


def test_global_aggregation_activity_fails_closed_without_aggregator() -> None:
    workflow_writer = RecordingWorkflowEventWriter()

    result = global_aggregation_activity(
        {"context": _context().model_dump()},
        workflow_event_writer=workflow_writer,
    )

    assert result["status"] == "failed"
    assert result["stage"] == "global_aggregation"
    assert result["module_key"] == "anchor_point_summary"
    assert result["error"]["code"] == "GLOBAL_AGGREGATOR_UNCONFIGURED"
    assert workflow_writer.events == [
        {
            "tenant_id": "tenant-1",
            "project_id": "project-1",
            "run_id": "run-1",
            "workflow_type": "seed_pipeline",
            "event_type": "seed.stage.failed",
            "payload": {
                "stage": "global_aggregation",
                "status": "failed",
                "activity": "global_aggregation_activity",
                "module_key": "anchor_point_summary",
                "error_code": "GLOBAL_AGGREGATOR_UNCONFIGURED",
                "error_message": "global aggregator is unconfigured",
            },
        }
    ]


def test_global_aggregation_activity_records_sanitized_counts_from_injected_aggregator() -> None:
    workflow_writer = RecordingWorkflowEventWriter()

    result = global_aggregation_activity(
        {"context": _context().model_dump()},
        global_aggregator=RecordingGlobalAggregator(),
        workflow_event_writer=workflow_writer,
    )

    assert result == {
        "tenant_id": "tenant-1",
        "project_id": "project-1",
        "run_id": "run-1",
        "workflow_type": "seed_pipeline",
        "upload_id": None,
        "status": "completed",
        "stage": "global_aggregation",
        "next_stage": "story_ontology",
        "module_key": "anchor_point_summary",
        "model_id": "model-agg",
        "segment_count": 2,
        "summary_count": 1,
        "stage_event_persisted": True,
    }
    assert workflow_writer.events == [
        {
            "tenant_id": "tenant-1",
            "project_id": "project-1",
            "run_id": "run-1",
            "workflow_type": "seed_pipeline",
            "event_type": "seed.stage.completed",
            "payload": {
                "stage": "global_aggregation",
                "status": "completed",
                "activity": "global_aggregation_activity",
                "module_key": "anchor_point_summary",
                "model_id": "model-agg",
                "segment_count": 2,
                "summary_count": 1,
            },
        }
    ]
    assert "private aggregate" not in str(result)
    assert "private aggregate" not in str(workflow_writer.events)


def test_global_aggregation_activity_sanitizes_failed_aggregator_public_result() -> None:
    workflow_writer = RecordingWorkflowEventWriter()

    result = global_aggregation_activity(
        {"context": _context().model_dump()},
        global_aggregator=FailingGlobalAggregator(),
        workflow_event_writer=workflow_writer,
    )

    assert result["status"] == "failed"
    assert result["stage"] == "global_aggregation"
    assert result["module_key"] == "anchor_point_summary"
    assert result["error"] == {
        "code": "LLM_PROVIDER_ERROR",
        "message": "global aggregation failed",
    }
    assert workflow_writer.events == [
        {
            "tenant_id": "tenant-1",
            "project_id": "project-1",
            "run_id": "run-1",
            "workflow_type": "seed_pipeline",
            "event_type": "seed.stage.failed",
            "payload": {
                "stage": "global_aggregation",
                "status": "failed",
                "activity": "global_aggregation_activity",
                "module_key": "anchor_point_summary",
                "error_code": "LLM_PROVIDER_ERROR",
                "error_message": "global aggregation failed",
            },
        }
    ]
    encoded = json.dumps({"result": result, "events": workflow_writer.events}, sort_keys=True)
    for forbidden in (
        "prompt",
        "api_key",
        "sk-hidden",
        "credential_ref",
        "object_key",
        "private/raw.txt",
        "raw_text",
        "draft",
        "manuscript",
    ):
        assert forbidden not in encoded


def test_global_aggregation_activity_persists_seed_analysis_snapshot_without_public_body() -> None:
    workflow_writer = RecordingWorkflowEventWriter()
    snapshot_writer = RecordingSeedAnalysisWriter()

    result = global_aggregation_activity(
        {"context": _context().model_dump()},
        global_aggregator=RecordingGlobalAggregator(),
        seed_analysis_writer=snapshot_writer,
        workflow_event_writer=workflow_writer,
    )

    assert result == {
        "tenant_id": "tenant-1",
        "project_id": "project-1",
        "run_id": "run-1",
        "workflow_type": "seed_pipeline",
        "upload_id": None,
        "status": "completed",
        "stage": "global_aggregation",
        "next_stage": "story_ontology",
        "module_key": "anchor_point_summary",
        "model_id": "model-agg",
        "segment_count": 2,
        "summary_count": 1,
        "seed_analysis_snapshot_id": "snapshot-1",
        "stage_event_persisted": True,
    }
    assert snapshot_writer.snapshots == [
        {
            "tenant_id": "tenant-1",
            "project_id": "project-1",
            "run_id": "run-1",
            "module_key": "anchor_point_summary",
            "model_id": "model-agg",
            "segment_count": 2,
            "summary_count": 1,
            "seed_analysis": {"overview": "private aggregate must not be returned or emitted"},
        }
    ]
    assert workflow_writer.events[-1]["payload"]["seed_analysis_snapshot_id"] == "snapshot-1"
    assert "private aggregate" not in str(result)
    assert "private aggregate" not in str(workflow_writer.events)


def test_story_ontology_activity_fails_closed_without_runner() -> None:
    workflow_writer = RecordingWorkflowEventWriter()

    result = seed_module.ontology_activity(
        {"context": _context().model_dump()},
        workflow_event_writer=workflow_writer,
    )

    assert result["status"] == "failed"
    assert result["stage"] == "story_ontology"
    assert result["module_key"] == "story_ontology"
    assert result["error"]["code"] == "ONTOLOGY_RUNNER_UNCONFIGURED"
    assert "seed_ontology" not in result
    assert workflow_writer.events == [
        {
            "tenant_id": "tenant-1",
            "project_id": "project-1",
            "run_id": "run-1",
            "workflow_type": "seed_pipeline",
            "event_type": "seed.stage.failed",
            "payload": {
                "stage": "story_ontology",
                "status": "failed",
                "activity": "ontology_activity",
                "module_key": "story_ontology",
                "error_code": "ONTOLOGY_RUNNER_UNCONFIGURED",
                "error_message": "ontology runner is unconfigured",
            },
        }
    ]


def test_story_ontology_activity_records_sanitized_metadata_from_runner() -> None:
    workflow_writer = RecordingWorkflowEventWriter()
    runner = RecordingOntologyRunner()

    result = seed_module.ontology_activity(
        {"context": _context().model_dump()},
        ontology_runner=runner,
        workflow_event_writer=workflow_writer,
    )

    assert result == {
        "tenant_id": "tenant-1",
        "project_id": "project-1",
        "run_id": "run-1",
        "workflow_type": "seed_pipeline",
        "upload_id": None,
        "status": "completed",
        "stage": "story_ontology",
        "next_stage": "entity_resolution",
        "module_key": "story_ontology",
        "model_id": "model-ontology",
        "ontology_snapshot_id": "ontology-snapshot-1",
        "entity_type_count": 3,
        "relationship_type_count": 2,
        "world_rule_type_count": 1,
        "stage_event_persisted": True,
    }
    assert runner.calls == [
        {
            "tenant_id": "tenant-1",
            "project_id": "project-1",
            "run_id": "run-1",
            "module_key": "story_ontology",
        }
    ]
    assert workflow_writer.events == [
        {
            "tenant_id": "tenant-1",
            "project_id": "project-1",
            "run_id": "run-1",
            "workflow_type": "seed_pipeline",
            "event_type": "seed.stage.completed",
            "payload": {
                "stage": "story_ontology",
                "status": "completed",
                "activity": "ontology_activity",
                "module_key": "story_ontology",
                "model_id": "model-ontology",
                "ontology_snapshot_id": "ontology-snapshot-1",
                "entity_type_count": 3,
                "relationship_type_count": 2,
                "world_rule_type_count": 1,
            },
        }
    ]
    assert "private ontology body" not in str(result)
    assert "private ontology body" not in str(workflow_writer.events)


def test_llm_facility_ontology_runner_persists_schema_valid_snapshot_without_public_body_or_credentials() -> None:
    resolver = RecordingBindingResolver(_ontology_resolution())
    credentials = RecordingCredentialProvider(api_key="sk-ontology")
    chat_client = RecordingJSONChatClient(
        response_json={
            "seed_ontology": {
                "entity_types": [
                    {"name": "character", "description": "人物"},
                    {"name": "organization", "description": "组织"},
                ],
                "relationship_types": [
                    {"name": "ally", "description": "盟友关系"},
                ],
                "world_rule_types": [
                    {"name": "political_rule", "description": "城邦规则"},
                ],
                "private_notes": "private ontology body must be persisted only in the writer",
                "prompt": "must not persist",
                "credential_ref": "secret-ref",
            }
        }
    )
    writer = RecordingOntologySnapshotWriter()
    runner = seed_module.LLMFacilityOntologyRunner(
        binding_resolver=resolver,
        credential_provider=credentials,
        chat_client=chat_client,
        ontology_snapshot_writer=writer,
    )

    result = runner.generate(context=_context(), module_key="story_ontology")

    assert result == {
        "status": "completed",
        "module_key": "story_ontology",
        "model_id": "model-ontology",
        "ontology_snapshot_id": "ontology-snapshot-1",
        "entity_type_count": 2,
        "relationship_type_count": 1,
        "world_rule_type_count": 1,
    }
    assert resolver.calls == ["story_ontology"]
    assert credentials.calls == ["channel-ontology"]
    assert chat_client.calls[0]["api_key"] == "sk-ontology"
    assert '"module_key":"story_ontology"' in chat_client.calls[0]["messages"][1]["content"]
    assert writer.calls == [
        {
            "tenant_id": "tenant-1",
            "project_id": "project-1",
            "run_id": "run-1",
            "module_key": "story_ontology",
            "model_id": "model-ontology",
            "seed_ontology": {
                "entity_types": [
                    {"name": "character", "description": "人物"},
                    {"name": "organization", "description": "组织"},
                ],
                "relationship_types": [
                    {"name": "ally", "description": "盟友关系"},
                ],
                "world_rule_types": [
                    {"name": "political_rule", "description": "城邦规则"},
                ],
                "private_notes": "private ontology body must be persisted only in the writer",
            },
            "entity_type_count": 2,
            "relationship_type_count": 1,
            "world_rule_type_count": 1,
        }
    ]
    public_body = json.dumps(result, ensure_ascii=False)
    assert "private ontology body" not in public_body
    assert "prompt" not in json.dumps(writer.calls, ensure_ascii=False)
    assert "credential_ref" not in json.dumps(writer.calls, ensure_ascii=False)


def test_entity_resolution_activity_fails_closed_without_runner() -> None:
    workflow_writer = RecordingWorkflowEventWriter()

    result = seed_module.entity_resolution_activity(
        {"context": _context().model_dump()},
        workflow_event_writer=workflow_writer,
    )

    assert result["status"] == "failed"
    assert result["stage"] == "entity_resolution"
    assert result["module_key"] == "entity_resolution"
    assert result["error"]["code"] == "ENTITY_RESOLUTION_RUNNER_UNCONFIGURED"
    assert "resolution_snapshot" not in result
    assert workflow_writer.events == [
        {
            "tenant_id": "tenant-1",
            "project_id": "project-1",
            "run_id": "run-1",
            "workflow_type": "seed_pipeline",
            "event_type": "seed.stage.failed",
            "payload": {
                "stage": "entity_resolution",
                "status": "failed",
                "activity": "entity_resolution_activity",
                "module_key": "entity_resolution",
                "error_code": "ENTITY_RESOLUTION_RUNNER_UNCONFIGURED",
                "error_message": "entity resolution runner is unconfigured",
            },
        }
    ]


def test_entity_resolution_activity_records_sanitized_metadata_from_runner() -> None:
    workflow_writer = RecordingWorkflowEventWriter()
    runner = RecordingEntityResolutionRunner()

    result = seed_module.entity_resolution_activity(
        {"context": _context().model_dump()},
        entity_resolution_runner=runner,
        workflow_event_writer=workflow_writer,
    )

    assert result == {
        "tenant_id": "tenant-1",
        "project_id": "project-1",
        "run_id": "run-1",
        "workflow_type": "seed_pipeline",
        "upload_id": None,
        "status": "completed",
        "stage": "entity_resolution",
        "next_stage": "agent_profiles",
        "module_key": "entity_resolution",
        "model_id": "model-resolution",
        "resolution_snapshot_id": "resolution-snapshot-1",
        "merged_entity_count": 4,
        "alias_count": 6,
        "conflict_count": 1,
        "stage_event_persisted": True,
    }
    assert runner.calls == [
        {
            "tenant_id": "tenant-1",
            "project_id": "project-1",
            "run_id": "run-1",
            "module_key": "entity_resolution",
        }
    ]
    assert workflow_writer.events == [
        {
            "tenant_id": "tenant-1",
            "project_id": "project-1",
            "run_id": "run-1",
            "workflow_type": "seed_pipeline",
            "event_type": "seed.stage.completed",
            "payload": {
                "stage": "entity_resolution",
                "status": "completed",
                "activity": "entity_resolution_activity",
                "module_key": "entity_resolution",
                "model_id": "model-resolution",
                "resolution_snapshot_id": "resolution-snapshot-1",
                "merged_entity_count": 4,
                "alias_count": 6,
                "conflict_count": 1,
            },
        }
    ]
    assert "private resolution body" not in str(result)
    assert "private resolution body" not in str(workflow_writer.events)


def test_llm_facility_entity_resolution_runner_persists_schema_valid_snapshot_without_public_body_or_credentials() -> None:
    resolver = RecordingBindingResolver(_entity_resolution())
    credentials = RecordingCredentialProvider(api_key="sk-resolution")
    chat_client = RecordingJSONChatClient(
        response_json={
            "entity_resolution": {
                "merged_entities": [
                    {"canonical_name": "林舟", "entity_type": "character", "aliases": ["小舟"]},
                    {"canonical_name": "星港议会", "entity_type": "organization", "aliases": []},
                ],
                "aliases": [
                    {"alias": "小舟", "canonical_name": "林舟"},
                    {"alias": "议会", "canonical_name": "星港议会"},
                ],
                "conflicts": [{"summary": "林舟身份在早期章节有两种称呼"}],
                "private_notes": "private resolution body must be persisted only in the writer",
                "prompt": "must not persist",
                "credential_ref": "secret-ref",
            }
        }
    )
    writer = RecordingEntityResolutionSnapshotWriter()
    runner = seed_module.LLMFacilityEntityResolutionRunner(
        binding_resolver=resolver,
        credential_provider=credentials,
        chat_client=chat_client,
        entity_resolution_snapshot_writer=writer,
    )

    result = runner.resolve(context=_context(), module_key="entity_resolution")

    assert result == {
        "status": "completed",
        "module_key": "entity_resolution",
        "model_id": "model-resolution",
        "resolution_snapshot_id": "resolution-snapshot-1",
        "merged_entity_count": 2,
        "alias_count": 2,
        "conflict_count": 1,
    }
    assert resolver.calls == ["entity_resolution"]
    assert credentials.calls == ["channel-resolution"]
    assert chat_client.calls[0]["api_key"] == "sk-resolution"
    assert '"module_key":"entity_resolution"' in chat_client.calls[0]["messages"][1]["content"]
    assert writer.calls == [
        {
            "tenant_id": "tenant-1",
            "project_id": "project-1",
            "run_id": "run-1",
            "module_key": "entity_resolution",
            "model_id": "model-resolution",
            "entity_resolution": {
                "merged_entities": [
                    {"canonical_name": "林舟", "entity_type": "character", "aliases": ["小舟"]},
                    {"canonical_name": "星港议会", "entity_type": "organization", "aliases": []},
                ],
                "aliases": [
                    {"alias": "小舟", "canonical_name": "林舟"},
                    {"alias": "议会", "canonical_name": "星港议会"},
                ],
                "conflicts": [{"summary": "林舟身份在早期章节有两种称呼"}],
                "private_notes": "private resolution body must be persisted only in the writer",
            },
            "merged_entity_count": 2,
            "alias_count": 2,
            "conflict_count": 1,
        }
    ]
    public_body = json.dumps(result, ensure_ascii=False)
    assert "private resolution body" not in public_body
    assert "prompt" not in json.dumps(writer.calls, ensure_ascii=False)
    assert "credential_ref" not in json.dumps(writer.calls, ensure_ascii=False)


def test_agent_profile_activity_fails_closed_without_runner() -> None:
    workflow_writer = RecordingWorkflowEventWriter()

    result = agent_profile_activity(
        {"context": _context().model_dump()},
        workflow_event_writer=workflow_writer,
    )

    assert result["status"] == "failed"
    assert result["stage"] == "agent_profiles"
    assert result["module_key"] == "character_agent_profile"
    assert result["error"]["code"] == "AGENT_PROFILE_RUNNER_UNCONFIGURED"
    assert "profile_snapshot" not in result
    assert workflow_writer.events == [
        {
            "tenant_id": "tenant-1",
            "project_id": "project-1",
            "run_id": "run-1",
            "workflow_type": "seed_pipeline",
            "event_type": "seed.stage.failed",
            "payload": {
                "stage": "agent_profiles",
                "status": "failed",
                "activity": "agent_profile_activity",
                "module_key": "character_agent_profile",
                "error_code": "AGENT_PROFILE_RUNNER_UNCONFIGURED",
                "error_message": "agent profile runner is unconfigured",
            },
        }
    ]


def test_agent_profile_activity_records_sanitized_metadata_from_runner() -> None:
    workflow_writer = RecordingWorkflowEventWriter()
    runner = RecordingAgentProfileRunner()

    result = agent_profile_activity(
        {"context": _context().model_dump()},
        agent_profile_runner=runner,
        workflow_event_writer=workflow_writer,
    )

    assert result == {
        "tenant_id": "tenant-1",
        "project_id": "project-1",
        "run_id": "run-1",
        "workflow_type": "seed_pipeline",
        "upload_id": None,
        "status": "completed",
        "stage": "agent_profiles",
        "next_stage": "archive_candidates",
        "module_key": "character_agent_profile",
        "model_id": "model-profile",
        "profile_snapshot_id": "profile-snapshot-1",
        "profile_count": 5,
        "memory_seed_count": 8,
        "relationship_view_count": 3,
        "stage_event_persisted": True,
    }
    assert runner.calls == [
        {
            "tenant_id": "tenant-1",
            "project_id": "project-1",
            "run_id": "run-1",
            "module_key": "character_agent_profile",
        }
    ]
    assert workflow_writer.events == [
        {
            "tenant_id": "tenant-1",
            "project_id": "project-1",
            "run_id": "run-1",
            "workflow_type": "seed_pipeline",
            "event_type": "seed.stage.completed",
            "payload": {
                "stage": "agent_profiles",
                "status": "completed",
                "activity": "agent_profile_activity",
                "module_key": "character_agent_profile",
                "model_id": "model-profile",
                "profile_snapshot_id": "profile-snapshot-1",
                "profile_count": 5,
                "memory_seed_count": 8,
                "relationship_view_count": 3,
            },
        }
    ]
    assert "private profile body" not in str(result)
    assert "private profile body" not in str(workflow_writer.events)


def test_archive_candidate_activity_fails_closed_without_runner() -> None:
    workflow_writer = RecordingWorkflowEventWriter()

    result = archive_candidate_activity(
        {"context": _context().model_dump()},
        workflow_event_writer=workflow_writer,
    )

    assert result["status"] == "failed"
    assert result["stage"] == "archive_candidates"
    assert result["module_key"] == "narrative_archives"
    assert result["error"]["code"] == "ARCHIVE_CANDIDATE_RUNNER_UNCONFIGURED"
    assert "archive_candidates" not in result
    assert workflow_writer.events == [
        {
            "tenant_id": "tenant-1",
            "project_id": "project-1",
            "run_id": "run-1",
            "workflow_type": "seed_pipeline",
            "event_type": "seed.stage.failed",
            "payload": {
                "stage": "archive_candidates",
                "status": "failed",
                "activity": "archive_candidate_activity",
                "module_key": "narrative_archives",
                "error_code": "ARCHIVE_CANDIDATE_RUNNER_UNCONFIGURED",
                "error_message": "archive candidate runner is unconfigured",
            },
        }
    ]


def test_archive_candidate_activity_records_sanitized_metadata_from_runner() -> None:
    workflow_writer = RecordingWorkflowEventWriter()
    runner = RecordingArchiveCandidateRunner()

    result = archive_candidate_activity(
        {"context": _context().model_dump()},
        archive_candidate_runner=runner,
        workflow_event_writer=workflow_writer,
    )

    assert result == {
        "tenant_id": "tenant-1",
        "project_id": "project-1",
        "run_id": "run-1",
        "workflow_type": "seed_pipeline",
        "upload_id": None,
        "status": "completed",
        "stage": "archive_candidates",
        "next_stage": "index_assets",
        "module_key": "narrative_archives",
        "model_id": "model-archive",
        "archive_candidate_batch_id": "archive-batch-1",
        "candidate_count": 7,
        "archive_entity_candidate_count": 5,
        "memory_candidate_count": 2,
        "stage_event_persisted": True,
    }
    assert runner.calls == [
        {
            "tenant_id": "tenant-1",
            "project_id": "project-1",
            "run_id": "run-1",
            "module_key": "narrative_archives",
        }
    ]
    assert workflow_writer.events == [
        {
            "tenant_id": "tenant-1",
            "project_id": "project-1",
            "run_id": "run-1",
            "workflow_type": "seed_pipeline",
            "event_type": "seed.stage.completed",
            "payload": {
                "stage": "archive_candidates",
                "status": "completed",
                "activity": "archive_candidate_activity",
                "module_key": "narrative_archives",
                "model_id": "model-archive",
                "archive_candidate_batch_id": "archive-batch-1",
                "candidate_count": 7,
                "archive_entity_candidate_count": 5,
                "memory_candidate_count": 2,
            },
        }
    ]
    assert "private archive candidate body" not in str(result)
    assert "private archive candidate body" not in str(workflow_writer.events)


def test_llm_facility_archive_candidate_runner_persists_schema_valid_archive_assets_and_memories() -> None:
    resolver = RecordingBindingResolver(_archive_resolution())
    credentials = RecordingCredentialProvider(api_key="sk-archive")
    chat_client = RecordingJSONChatClient(
        response_json={
            "archive_entities": [
                {
                    "title": "阿澜档案",
                    "summary": "雨夜谈判中的核心人物。",
                    "category": "character",
                    "tags": ["character", "rain"],
                    "payload": {
                        "entity_name": "阿澜",
                        "entity_type": "character",
                        "core_drive": "守住秘密",
                        "prompt": "must be removed",
                    },
                    "memories": [
                        {
                            "memory_type": "motivation",
                            "summary": "她用沉默拖住谈判节奏。",
                            "body_text": "private memory body must be stored privately only",
                            "payload": {
                                "visibility": "writer_context",
                                "credential_ref": "secret-ref",
                            },
                        }
                    ],
                }
            ]
        }
    )
    writer = RecordingArchiveCandidateWriter()
    runner = LLMFacilityArchiveCandidateRunner(
        binding_resolver=resolver,
        credential_provider=credentials,
        chat_client=chat_client,
        archive_candidate_writer=writer,
    )

    result = runner.generate(context=_context(), module_key="narrative_archives")

    assert result == {
        "status": "completed",
        "module_key": "narrative_archives",
        "model_id": "model-archive",
        "archive_candidate_batch_id": "narrative-archives:run-1",
        "candidate_count": 2,
        "archive_entity_candidate_count": 1,
        "memory_candidate_count": 1,
    }
    assert resolver.calls == ["narrative_archives"]
    assert credentials.calls == ["channel-archive"]
    assert chat_client.calls[0]["api_key"] == "sk-archive"
    assert '"module_key":"narrative_archives"' in chat_client.calls[0]["messages"][1]["content"]
    assert writer.calls[0]["archive_entities"][0]["payload"] == {
        "entity_name": "阿澜",
        "entity_type": "character",
        "core_drive": "守住秘密",
    }
    assert writer.calls[0]["archive_entities"][0]["memories"][0]["payload"] == {
        "visibility": "writer_context"
    }
    assert "prompt" not in str(writer.calls)
    assert "credential_ref" not in str(writer.calls)


def test_postgres_archive_candidate_writer_persists_candidate_archive_assets_and_memories_without_public_body_or_credentials() -> None:
    connection = FakeArchiveCandidateConnection(
        [
            {"asset_id": "asset-archive-1"},
            {"memory_id": "memory-1"},
        ]
    )
    writer = PostgresArchiveCandidateWriter(connect=lambda: connection)

    result = writer.write_archive_candidates(
        context=_context(),
        archive_candidate_batch_id="narrative-archives:run-1",
        model_id="model-archive",
        archive_entities=[
            {
                "title": "阿澜档案",
                "summary": "雨夜谈判中的核心人物。",
                "category": "character",
                "tags": ["character"],
                "payload": {
                    "entity_name": "阿澜",
                    "api_key": "sk-secret",
                    "prompt": "must not persist",
                },
                "memories": [
                    {
                        "memory_type": "motivation",
                        "summary": "她用沉默拖住谈判节奏。",
                        "body_text": "private memory body is allowed only in archive_memories.body_text",
                        "payload": {
                            "body_text": "must not appear in payload",
                            "credential_ref": "secret-ref",
                        },
                    }
                ],
            }
        ],
    )

    assert result == {
        "status": "completed",
        "archive_candidate_batch_id": "narrative-archives:run-1",
        "candidate_count": 2,
        "archive_entity_candidate_count": 1,
        "memory_candidate_count": 1,
    }
    queries = [query for query, _params in connection.cursor_instance.executed]
    assert connection.cursor_instance.executed[0] == (
        "SELECT app_set_tenant_context(%s::uuid, %s::uuid, false)",
        ("tenant-1", "project-1"),
    )
    assert "INSERT INTO assets" in queries[1]
    assert "INSERT INTO archive_memories" in queries[2]
    assert "INSERT INTO archive_memory_events" in queries[3]
    joined_params = json.dumps(connection.cursor_instance.executed, ensure_ascii=False, default=str)
    assert "narrative-archives:run-1" in joined_params
    assert "private memory body is allowed only in archive_memories.body_text" in joined_params
    assert "must not appear in payload" not in joined_params
    assert "credential_ref" not in joined_params
    assert "sk-secret" not in joined_params
    assert "prompt" not in joined_params
    assert connection.committed is True
    assert connection.closed is True


def test_postgres_archive_candidate_writer_rolls_back_and_sanitizes_database_failures() -> None:
    execute_failure = FailingArchiveCandidateConnection(
        [
            {"asset_id": "asset-archive-1"},
            {"memory_id": "memory-1"},
        ],
        fail_on_execute=2,
    )
    writer = PostgresArchiveCandidateWriter(connect=lambda: execute_failure)

    with pytest.raises(LLMFacilityError) as execute_error:
        writer.write_archive_candidates(
            context=_context(),
            archive_candidate_batch_id="narrative-archives:run-1",
            model_id="model-archive",
            archive_entities=[
                {
                    "title": "阿澜档案",
                    "summary": "雨夜谈判中的核心人物。",
                    "category": "character",
                    "tags": ["character"],
                    "payload": {"entity_name": "阿澜"},
                    "memories": [],
                }
            ],
        )

    assert execute_error.value.code == "ARCHIVE_CANDIDATE_WRITE_FAILED"
    assert execute_error.value.message == "archive candidate write failed"
    _assert_untrusted_archive_candidate_db_error_redacted(execute_error.value.message)
    assert execute_failure.rolled_back is True
    assert execute_failure.committed is False
    assert execute_failure.closed is True

    commit_failure = FailingArchiveCandidateConnection(
        [
            {"asset_id": "asset-archive-1"},
        ],
        fail_on_commit=True,
    )
    commit_writer = PostgresArchiveCandidateWriter(connect=lambda: commit_failure)

    with pytest.raises(LLMFacilityError) as commit_error:
        commit_writer.write_archive_candidates(
            context=_context(),
            archive_candidate_batch_id="narrative-archives:run-1",
            model_id="model-archive",
            archive_entities=[
                {
                    "title": "阿澜档案",
                    "summary": "雨夜谈判中的核心人物。",
                    "category": "character",
                    "tags": ["character"],
                    "payload": {"entity_name": "阿澜"},
                    "memories": [],
                }
            ],
        )

    assert commit_error.value.code == "ARCHIVE_CANDIDATE_WRITE_FAILED"
    assert commit_error.value.message == "archive candidate write failed"
    _assert_untrusted_archive_candidate_db_error_redacted(commit_error.value.message)
    assert commit_failure.rolled_back is True
    assert commit_failure.committed is False
    assert commit_failure.closed is True


def test_llm_facility_archive_candidate_runner_fails_closed_when_module_unbound_without_provider_call() -> None:
    resolver = RecordingBindingResolver(
        LLMFacilityError("LLM_MODULE_UNBOUND", "narrative_archives module is not bound")
    )
    credentials = RecordingCredentialProvider(api_key="sk-archive")
    chat_client = RecordingJSONChatClient(response_json={"archive_entities": []})
    writer = RecordingArchiveCandidateWriter()
    runner = LLMFacilityArchiveCandidateRunner(
        binding_resolver=resolver,
        credential_provider=credentials,
        chat_client=chat_client,
        archive_candidate_writer=writer,
    )

    result = runner.generate(context=_context(), module_key="narrative_archives")

    assert result["status"] == "failed"
    assert result["error"]["code"] == "LLM_MODULE_UNBOUND"
    assert credentials.calls == []
    assert chat_client.calls == []
    assert writer.calls == []


def test_index_assets_activity_fails_closed_without_indexer() -> None:
    workflow_writer = RecordingWorkflowEventWriter()

    result = index_assets_activity(
        {"context": _context().model_dump()},
        workflow_event_writer=workflow_writer,
    )

    assert result["status"] == "failed"
    assert result["stage"] == "index_assets"
    assert result["error"]["code"] == "ASSET_INDEXER_UNCONFIGURED"
    assert "search_documents" not in result
    assert "embeddings" not in result
    assert workflow_writer.events == [
        {
            "tenant_id": "tenant-1",
            "project_id": "project-1",
            "run_id": "run-1",
            "workflow_type": "seed_pipeline",
            "event_type": "seed.stage.failed",
            "payload": {
                "stage": "index_assets",
                "status": "failed",
                "activity": "index_assets_activity",
                "error_code": "ASSET_INDEXER_UNCONFIGURED",
                "error_message": "asset indexer is unconfigured",
            },
        }
    ]


def test_index_assets_activity_records_sanitized_metadata_from_indexer() -> None:
    workflow_writer = RecordingWorkflowEventWriter()
    indexer = RecordingAssetIndexer()

    result = index_assets_activity(
        {"context": _context().model_dump()},
        asset_indexer=indexer,
        workflow_event_writer=workflow_writer,
    )

    assert result == {
        "tenant_id": "tenant-1",
        "project_id": "project-1",
        "run_id": "run-1",
        "workflow_type": "seed_pipeline",
        "upload_id": None,
        "status": "completed",
        "stage": "index_assets",
        "next_stage": "finalize",
        "asset_index_batch_id": "asset-index-batch-1",
        "indexed_asset_count": 9,
        "search_document_count": 12,
        "embedding_count": 4,
        "stage_event_persisted": True,
    }
    assert indexer.calls == [
        {
            "tenant_id": "tenant-1",
            "project_id": "project-1",
            "run_id": "run-1",
        }
    ]
    assert workflow_writer.events == [
        {
            "tenant_id": "tenant-1",
            "project_id": "project-1",
            "run_id": "run-1",
            "workflow_type": "seed_pipeline",
            "event_type": "seed.stage.completed",
            "payload": {
                "stage": "index_assets",
                "status": "completed",
                "activity": "index_assets_activity",
                "asset_index_batch_id": "asset-index-batch-1",
                "indexed_asset_count": 9,
                "search_document_count": 12,
                "embedding_count": 4,
            },
        }
    ]
    assert "private search document body" not in str(result)
    assert "private search document body" not in str(workflow_writer.events)
    assert "private embedding chunk" not in str(result)
    assert "private embedding chunk" not in str(workflow_writer.events)


def test_postgres_seed_asset_indexer_requires_project_context() -> None:
    indexer = PostgresSeedAssetIndexer(connect=FakeConnection)
    context = _context().model_copy(update={"project_id": None})

    with pytest.raises(ValueError, match="project_id is required"):
        indexer.index(context=context)


def test_postgres_seed_asset_indexer_projects_canon_into_assets_and_search() -> None:
    connection = FakeAssetIndexConnection(
        [
            {"entity_asset_count": 2},
            {"relationship_asset_count": 1},
            {"world_rule_asset_count": 3},
            {"plot_thread_asset_count": 1},
            {"search_document_count": 7},
        ]
    )
    indexer = PostgresSeedAssetIndexer(connect=lambda: connection)

    result = indexer.index(context=_context())

    assert result == {
        "status": "completed",
        "asset_index_batch_id": "seed-assets:run-1",
        "indexed_asset_count": 7,
        "search_document_count": 7,
        "embedding_count": 0,
    }
    queries = [query for query, _params in connection.cursor_instance.executed]
    assert len(queries) == 6
    assert connection.cursor_instance.executed[0] == (
        "SELECT app_set_tenant_context(%s::uuid, %s::uuid, false)",
        ("tenant-1", "project-1"),
    )
    assert "INSERT INTO assets" in queries[1]
    assert "FROM entities" in queries[1]
    assert "INSERT INTO assets" in queries[2]
    assert "FROM relationships" in queries[2]
    assert "INSERT INTO assets" in queries[3]
    assert "FROM world_rule_evidence" in queries[3]
    assert "INSERT INTO assets" in queries[4]
    assert "FROM plot_threads" in queries[4]
    assert "INSERT INTO global_search_index" in queries[5]
    assert all(params == ("tenant-1", "project-1", "run-1") for _query, params in connection.cursor_instance.executed[1:])
    assert "evidence_text" not in str(result)
    assert "body" not in result
    assert connection.committed is True
    assert connection.closed is True


def test_postgres_seed_asset_indexer_rolls_back_on_database_failure() -> None:
    execute_failure = FailingAssetIndexConnection(
        [
            {"entity_asset_count": 2},
            {"relationship_asset_count": 1},
            {"world_rule_asset_count": 3},
            {"plot_thread_asset_count": 1},
            {"search_document_count": 7},
        ],
        fail_on_execute=2,
    )
    indexer = PostgresSeedAssetIndexer(connect=lambda: execute_failure)

    with pytest.raises(RuntimeError, match="driver failure"):
        indexer.index(context=_context())

    assert execute_failure.rolled_back is True
    assert execute_failure.committed is False
    assert execute_failure.closed is True

    commit_failure = FailingAssetIndexConnection(
        [
            {"entity_asset_count": 2},
            {"relationship_asset_count": 1},
            {"world_rule_asset_count": 3},
            {"plot_thread_asset_count": 1},
            {"search_document_count": 7},
        ],
        fail_on_commit=True,
    )
    commit_indexer = PostgresSeedAssetIndexer(connect=lambda: commit_failure)

    with pytest.raises(RuntimeError, match="commit failure"):
        commit_indexer.index(context=_context())

    assert commit_failure.rolled_back is True
    assert commit_failure.committed is False
    assert commit_failure.closed is True


def test_postgres_project_readiness_updater_records_snapshot_counts_without_report_body() -> None:
    connection = FakeProjectReadinessConnection(
        [
            {
                "project_readiness_snapshot_id": "readiness-snapshot-1",
                "ready_asset_count": 7,
                "ready_entity_count": 3,
                "ready_relationship_count": 2,
                "ready_world_rule_count": 1,
            }
        ]
    )
    updater = PostgresProjectReadinessUpdater(connect=lambda: connection)

    result = updater.update(context=_context())

    assert result == {
        "status": "completed",
        "project_readiness_snapshot_id": "readiness-snapshot-1",
        "ready_asset_count": 7,
        "ready_entity_count": 3,
        "ready_relationship_count": 2,
        "ready_world_rule_count": 1,
    }
    queries = [query for query, _params in connection.cursor_instance.executed]
    assert connection.cursor_instance.executed[0] == (
        "SELECT app_set_tenant_context(%s::uuid, %s::uuid, false)",
        ("tenant-1", "project-1"),
    )
    assert "INSERT INTO project_readiness_snapshots" in queries[1]
    assert "FROM assets" in queries[1]
    assert "FROM entities" in queries[1]
    assert "FROM relationships" in queries[1]
    assert "FROM world_rule_evidence" in queries[1]
    assert "RETURNING" in queries[1]
    assert "project_readiness_snapshot_id::text AS project_readiness_snapshot_id" in queries[1]
    joined_params = json.dumps(connection.cursor_instance.executed, ensure_ascii=False, default=str)
    assert "tenant-1" in joined_params
    assert "project-1" in joined_params
    assert "run-1" in joined_params
    assert "readiness_report" not in joined_params
    assert "private readiness body" not in joined_params
    assert connection.committed is True
    assert connection.closed is True


def test_postgres_project_readiness_updater_accepts_psycopg_tuple_returning_rows() -> None:
    connection = FakeProjectReadinessConnection(
        [
            (
                "readiness-snapshot-1",
                7,
                3,
                2,
                1,
            )
        ]
    )
    updater = PostgresProjectReadinessUpdater(connect=lambda: connection)

    result = updater.update(context=_context())

    assert result == {
        "status": "completed",
        "project_readiness_snapshot_id": "readiness-snapshot-1",
        "ready_asset_count": 7,
        "ready_entity_count": 3,
        "ready_relationship_count": 2,
        "ready_world_rule_count": 1,
    }
    assert connection.committed is True
    assert connection.closed is True


def test_postgres_project_readiness_updater_rolls_back_and_sanitizes_database_failures() -> None:
    execute_failure = FailingProjectReadinessConnection(
        [
            {
                "project_readiness_snapshot_id": "readiness-snapshot-1",
                "ready_asset_count": 7,
                "ready_entity_count": 3,
                "ready_relationship_count": 2,
                "ready_world_rule_count": 1,
            }
        ],
        fail_on_execute=2,
    )
    updater = PostgresProjectReadinessUpdater(connect=lambda: execute_failure)

    with pytest.raises(LLMFacilityError) as execute_error:
        updater.update(context=_context())

    assert execute_error.value.code == "PROJECT_READINESS_UPDATE_FAILED"
    assert execute_error.value.message == "project readiness update failed"
    _assert_untrusted_project_readiness_db_error_redacted(execute_error.value.message)
    assert execute_failure.rolled_back is True
    assert execute_failure.committed is False
    assert execute_failure.closed is True

    commit_failure = FailingProjectReadinessConnection(
        [
            {
                "project_readiness_snapshot_id": "readiness-snapshot-1",
                "ready_asset_count": 7,
                "ready_entity_count": 3,
                "ready_relationship_count": 2,
                "ready_world_rule_count": 1,
            }
        ],
        fail_on_commit=True,
    )
    commit_updater = PostgresProjectReadinessUpdater(connect=lambda: commit_failure)

    with pytest.raises(LLMFacilityError) as commit_error:
        commit_updater.update(context=_context())

    assert commit_error.value.code == "PROJECT_READINESS_UPDATE_FAILED"
    assert commit_error.value.message == "project readiness update failed"
    _assert_untrusted_project_readiness_db_error_redacted(commit_error.value.message)
    assert commit_failure.rolled_back is True
    assert commit_failure.committed is False
    assert commit_failure.closed is True


def test_finalize_seed_activity_fails_closed_without_updater() -> None:
    workflow_writer = RecordingWorkflowEventWriter()

    result = finalize_seed_activity(
        {"context": _context().model_dump()},
        workflow_event_writer=workflow_writer,
    )

    assert result["status"] == "failed"
    assert result["stage"] == "finalize"
    assert result["error"]["code"] == "PROJECT_READINESS_UPDATER_UNCONFIGURED"
    assert "readiness_snapshot" not in result
    assert workflow_writer.events == [
        {
            "tenant_id": "tenant-1",
            "project_id": "project-1",
            "run_id": "run-1",
            "workflow_type": "seed_pipeline",
            "event_type": "seed.stage.failed",
            "payload": {
                "stage": "finalize",
                "status": "failed",
                "activity": "finalize_seed_activity",
                "error_code": "PROJECT_READINESS_UPDATER_UNCONFIGURED",
                "error_message": "project readiness updater is unconfigured",
            },
        }
    ]


def test_finalize_seed_activity_records_sanitized_metadata_from_updater() -> None:
    workflow_writer = RecordingWorkflowEventWriter()
    updater = RecordingProjectReadinessUpdater()

    result = finalize_seed_activity(
        {"context": _context().model_dump()},
        project_readiness_updater=updater,
        workflow_event_writer=workflow_writer,
    )

    assert result == {
        "tenant_id": "tenant-1",
        "project_id": "project-1",
        "run_id": "run-1",
        "workflow_type": "seed_pipeline",
        "upload_id": None,
        "status": "completed",
        "stage": "finalize",
        "project_readiness_snapshot_id": "readiness-snapshot-1",
        "ready_asset_count": 9,
        "ready_entity_count": 4,
        "ready_relationship_count": 3,
        "ready_world_rule_count": 2,
        "stage_event_persisted": True,
    }
    assert updater.calls == [
        {
            "tenant_id": "tenant-1",
            "project_id": "project-1",
            "run_id": "run-1",
        }
    ]
    assert workflow_writer.events == [
        {
            "tenant_id": "tenant-1",
            "project_id": "project-1",
            "run_id": "run-1",
            "workflow_type": "seed_pipeline",
            "event_type": "seed.stage.completed",
            "payload": {
                "stage": "finalize",
                "status": "completed",
                "activity": "finalize_seed_activity",
                "project_readiness_snapshot_id": "readiness-snapshot-1",
                "ready_asset_count": 9,
                "ready_entity_count": 4,
                "ready_relationship_count": 3,
                "ready_world_rule_count": 2,
            },
        }
    ]
    assert "private readiness body" not in str(result)
    assert "private readiness body" not in str(workflow_writer.events)


def test_finalize_seed_activity_marks_workflow_completed_with_public_metadata() -> None:
    workflow_writer = RecordingWorkflowEventWriter()
    status_writer = RecordingWorkflowRunStatusWriter()
    updater = RecordingProjectReadinessUpdater()

    result = finalize_seed_activity(
        {"context": _context().model_dump()},
        project_readiness_updater=updater,
        workflow_event_writer=workflow_writer,
        workflow_status_writer=status_writer,
    )

    assert result["status"] == "completed"
    assert result["stage"] == "finalize"
    assert result["workflow_status_persisted"] is True
    assert status_writer.completed == [
        {
            "tenant_id": "tenant-1",
            "project_id": "project-1",
            "run_id": "run-1",
            "result": {
                "stage": "finalize",
                "project_readiness_snapshot_id": "readiness-snapshot-1",
                "ready_asset_count": 9,
                "ready_entity_count": 4,
                "ready_relationship_count": 3,
                "ready_world_rule_count": 2,
            },
        }
    ]
    assert status_writer.failed == []
    public_body = json.dumps([result, workflow_writer.events, status_writer.completed], ensure_ascii=False)
    for forbidden in ("private readiness body", "prompt", "api_key", "credential_ref", "object_key", "raw_text"):
        assert forbidden not in public_body


@pytest.mark.parametrize(
    ("activity_func", "expected_stage", "expected_module_key"),
    [
        (persist_runtime_facts_activity, "persist_runtime_facts", None),
        (global_aggregation_activity, "global_aggregation", "anchor_point_summary"),
        (seed_module.ontology_activity, "story_ontology", "story_ontology"),
        (seed_module.entity_resolution_activity, "entity_resolution", "entity_resolution"),
        (agent_profile_activity, "agent_profiles", "character_agent_profile"),
        (archive_candidate_activity, "archive_candidates", "narrative_archives"),
        (index_assets_activity, "index_assets", None),
        (finalize_seed_activity, "finalize", None),
    ],
)
def test_seed_later_stage_activities_sanitize_workflow_event_writer_env_resolution_exception(
    monkeypatch: pytest.MonkeyPatch,
    activity_func: object,
    expected_stage: str,
    expected_module_key: str | None,
) -> None:
    def fail_from_env() -> None:
        raise RuntimeError(
            f"{expected_stage} event writer env failed prompt=hidden api_key=sk-hidden "
            "credential_ref=cred-hidden object_key=private draft=private manuscript=private"
        )

    monkeypatch.setattr(seed_module, "_workflow_event_writer_from_env", fail_from_env)

    result = activity_func({"context": _context().model_dump()})

    assert result["status"] == "failed"
    assert result["stage"] == expected_stage
    if expected_module_key is not None:
        assert result["module_key"] == expected_module_key
    assert result["error"] == {
        "code": "WORKFLOW_EVENT_WRITE_FAILED",
        "message": "workflow event write failed",
    }
    public_body = json.dumps(result, ensure_ascii=False, sort_keys=True)
    for forbidden in (
        "event writer env failed",
        "prompt",
        "api_key",
        "sk-hidden",
        "credential_ref",
        "object_key",
        "draft",
        "manuscript",
    ):
        assert forbidden not in public_body


class RecordingWorkflowEventWriter:
    def __init__(self) -> None:
        self.events: list[dict[str, object]] = []

    def record_workflow_event(
        self,
        *,
        context: AgentContext,
        event_type: str,
        payload: dict[str, object],
    ) -> None:
        self.events.append(
            {
                "tenant_id": context.tenant_id,
                "project_id": context.project_id,
                "run_id": context.run_id,
                "workflow_type": context.workflow_type,
                "event_type": event_type,
                "payload": payload,
            }
        )


class RecordingWorkflowRunStatusWriter:
    def __init__(self) -> None:
        self.running: list[dict[str, object]] = []
        self.completed: list[dict[str, object]] = []
        self.failed: list[dict[str, object]] = []

    def mark_running(
        self,
        *,
        context: AgentContext,
    ) -> None:
        self.running.append(
            {
                "tenant_id": context.tenant_id,
                "project_id": context.project_id,
                "run_id": context.run_id,
            }
        )

    def mark_completed(
        self,
        *,
        context: AgentContext,
        result: dict[str, object],
    ) -> None:
        self.completed.append(
            {
                "tenant_id": context.tenant_id,
                "project_id": context.project_id,
                "run_id": context.run_id,
                "result": result,
            }
        )

    def mark_failed(
        self,
        *,
        context: AgentContext,
        code: str,
        message: str,
    ) -> None:
        self.failed.append(
            {
                "tenant_id": context.tenant_id,
                "project_id": context.project_id,
                "run_id": context.run_id,
                "code": code,
                "message": message,
            }
        )


class RecordingTextArtifactWriter:
    def __init__(self) -> None:
        self.artifacts: list[dict[str, object]] = []

    def record_text_artifact(
        self,
        *,
        context: AgentContext,
        source_file_id: str,
        artifact_type: str,
        object_key: str,
        char_count: int,
        line_count: int,
        sha256: str | None = None,
        metadata_jsonb: dict[str, object] | None = None,
    ) -> None:
        self.artifacts.append(
            {
                "tenant_id": context.tenant_id,
                "project_id": context.project_id,
                "run_id": context.run_id,
                "source_file_id": source_file_id,
                "artifact_type": artifact_type,
                "object_key": object_key,
                "char_count": char_count,
                "line_count": line_count,
                "sha256": sha256,
                "metadata_jsonb": metadata_jsonb or {},
            }
        )


class RecordingTextSegmentWriter:
    def __init__(self) -> None:
        self.segments: list[dict[str, object]] = []

    def record_text_segments(
        self,
        *,
        context: AgentContext,
        source_file_id: str,
        segments: list[dict[str, object]],
    ) -> None:
        for segment in segments:
            self.segments.append(
                {
                    "tenant_id": context.tenant_id,
                    "project_id": context.project_id,
                    "run_id": context.run_id,
                    "source_file_id": source_file_id,
                    **segment,
                }
            )


class RecordingSourceFileStatusWriter:
    def __init__(self) -> None:
        self.statuses: list[dict[str, object]] = []

    def mark_source_file_status(
        self,
        *,
        context: AgentContext,
        source_file_id: str,
        parse_status: str,
    ) -> None:
        self.statuses.append(
            {
                "tenant_id": context.tenant_id,
                "project_id": context.project_id,
                "run_id": context.run_id,
                "source_file_id": source_file_id,
                "parse_status": parse_status,
            }
        )


class FailingSourceFileStatusWriter:
    def mark_source_file_status(
        self,
        *,
        context: AgentContext,
        source_file_id: str,
        parse_status: str,
    ) -> None:
        raise LLMFacilityError(
            "SOURCE_FILE_PARSE_STATUS_UPDATE_FAILED",
            "source file parse status update failed",
        )


class RecordingReadingNotesWriter:
    def __init__(self) -> None:
        self.passes: list[dict[str, object]] = []

    def record_reading_notes(
        self,
        *,
        context: AgentContext,
        pass_id: str,
        pass_type: str,
        status: str,
        module_key: str | None,
        model_id: str | None,
        notes: list[dict[str, object]],
        metadata_jsonb: dict[str, object] | None = None,
    ) -> None:
        self.passes.append(
            {
                "tenant_id": context.tenant_id,
                "project_id": context.project_id,
                "run_id": context.run_id,
                "pass_id": pass_id,
                "pass_type": pass_type,
                "status": status,
                "module_key": module_key,
                "model_id": model_id,
                "notes": notes,
                "metadata_jsonb": metadata_jsonb or {},
            }
        )


class RecordingRuntimeFactsWriter:
    def __init__(self) -> None:
        self.calls: list[dict[str, object]] = []

    def record_runtime_facts(
        self,
        *,
        context: AgentContext,
        reading_notes: list[dict[str, object]] | None = None,
    ) -> dict[str, int]:
        notes = list(reading_notes or [])
        entity_count = 0
        entity_label_count = 0
        relationship_count = 0
        plot_thread_count = 0
        thread_lifecycle_count = 0
        narrative_arc_count = 0
        volume_summary_count = 0
        world_rule_count = 0
        character_event_count = 0
        world_event_count = 0
        relationship_event_count = 0
        consistency_note_count = 0
        segment_summary_count = 0
        for note in notes:
            if isinstance(note.get("summary"), str) and note["summary"].strip():
                segment_summary_count += 1
            payload = note.get("payload_jsonb")
            if isinstance(payload, dict):
                entity_count += len(payload.get("characters", [])) if isinstance(payload.get("characters"), list) else 0
                entity_count += (
                    len(payload.get("organizations", [])) if isinstance(payload.get("organizations"), list) else 0
                )
                for entity in list(payload.get("characters", [])) + list(payload.get("organizations", [])):
                    if isinstance(entity, dict) and isinstance(entity.get("labels"), list):
                        entity_label_count += len(entity["labels"])
                relationship_count += (
                    len(payload.get("relationships", [])) if isinstance(payload.get("relationships"), list) else 0
                )
                plot_thread_count += (
                    len(payload.get("plot_threads", [])) if isinstance(payload.get("plot_threads"), list) else 0
                )
                thread_lifecycle_count += (
                    len(payload.get("plot_threads", [])) if isinstance(payload.get("plot_threads"), list) else 0
                )
                narrative_arc_count += (
                    len(payload.get("narrative_arcs", []))
                    if isinstance(payload.get("narrative_arcs"), list)
                    else 0
                )
                volume_summary_count += (
                    len(payload.get("volume_summaries", []))
                    if isinstance(payload.get("volume_summaries"), list)
                    else 0
                )
                world_rule_count += len(payload.get("world_rules", [])) if isinstance(payload.get("world_rules"), list) else 0
                if isinstance(payload.get("events"), list):
                    for event in payload["events"]:
                        if isinstance(event, dict) and event.get("event_type") == "relationship":
                            relationship_event_count += 1
                        elif isinstance(event, dict) and event.get("scope") == "world":
                            world_event_count += 1
                        else:
                            character_event_count += 1
                consistency_note_count += (
                    len(payload.get("consistency_notes", []))
                    if isinstance(payload.get("consistency_notes"), list)
                    else 0
                )
        self.calls.append(
            {
                "tenant_id": context.tenant_id,
                "project_id": context.project_id,
                "run_id": context.run_id,
                "reading_notes": notes,
            }
        )
        return {
            "entity_count": entity_count,
            "entity_label_count": entity_label_count,
            "relationship_count": relationship_count,
            "plot_thread_count": plot_thread_count,
            "thread_lifecycle_count": thread_lifecycle_count,
            "narrative_arc_count": narrative_arc_count,
            "volume_summary_count": volume_summary_count,
            "world_rule_count": world_rule_count,
            "character_event_count": character_event_count,
            "world_event_count": world_event_count,
            "relationship_event_count": relationship_event_count,
            "consistency_note_count": consistency_note_count,
            "segment_summary_count": segment_summary_count,
        }


class RecordingGlobalAggregator:
    def __init__(self) -> None:
        self.calls: list[dict[str, object]] = []

    def aggregate(
        self,
        *,
        context: AgentContext,
        module_key: str,
    ) -> dict[str, object]:
        self.calls.append(
            {
                "tenant_id": context.tenant_id,
                "project_id": context.project_id,
                "run_id": context.run_id,
                "module_key": module_key,
            }
        )
        return {
            "status": "completed",
            "module_key": module_key,
            "model_id": "model-agg",
            "segment_count": 2,
            "summary_count": 1,
            "seed_analysis": {"overview": "private aggregate must not be returned or emitted"},
        }


class FailingGlobalAggregator:
    def aggregate(
        self,
        *,
        context: AgentContext,
        module_key: str,
    ) -> dict[str, object]:
        return {
            "status": "failed",
            "module_key": module_key,
            "error": {
                "code": "PROMPT_API_KEY_EVIDENCE_LEAK",
                "message": (
                    "provider failed prompt=hidden api_key=sk-hidden "
                    "credential_ref=secret object_key=private/raw.txt raw_text=body "
                    "draft=private manuscript=private"
                ),
            },
        }


class RecordingSeedAnalysisWriter:
    def __init__(self) -> None:
        self.snapshots: list[dict[str, object]] = []

    def record_seed_analysis(
        self,
        *,
        context: AgentContext,
        module_key: str,
        model_id: str | None,
        segment_count: int,
        summary_count: int,
        seed_analysis: dict[str, object],
    ) -> str:
        self.snapshots.append(
            {
                "tenant_id": context.tenant_id,
                "project_id": context.project_id,
                "run_id": context.run_id,
                "module_key": module_key,
                "model_id": model_id,
                "segment_count": segment_count,
                "summary_count": summary_count,
                "seed_analysis": seed_analysis,
            }
        )
        return "snapshot-1"


class RecordingOntologyRunner:
    def __init__(self) -> None:
        self.calls: list[dict[str, object]] = []

    def generate(
        self,
        *,
        context: AgentContext,
        module_key: str,
    ) -> dict[str, object]:
        self.calls.append(
            {
                "tenant_id": context.tenant_id,
                "project_id": context.project_id,
                "run_id": context.run_id,
                "module_key": module_key,
            }
        )
        return {
            "status": "completed",
            "module_key": module_key,
            "model_id": "model-ontology",
            "ontology_snapshot_id": "ontology-snapshot-1",
            "entity_type_count": 3,
            "relationship_type_count": 2,
            "world_rule_type_count": 1,
            "seed_ontology": {"body": "private ontology body must not be returned or emitted"},
        }


class RecordingOntologySnapshotWriter:
    def __init__(self, error: LLMFacilityError | None = None) -> None:
        self.error = error
        self.calls: list[dict[str, object]] = []

    def record_ontology_snapshot(
        self,
        *,
        context: AgentContext,
        module_key: str,
        model_id: str | None,
        seed_ontology: dict[str, object],
        entity_type_count: int,
        relationship_type_count: int,
        world_rule_type_count: int,
    ) -> str:
        self.calls.append(
            {
                "tenant_id": context.tenant_id,
                "project_id": context.project_id,
                "run_id": context.run_id,
                "module_key": module_key,
                "model_id": model_id,
                "seed_ontology": seed_ontology,
                "entity_type_count": entity_type_count,
                "relationship_type_count": relationship_type_count,
                "world_rule_type_count": world_rule_type_count,
            }
        )
        if self.error is not None:
            raise self.error
        return "ontology-snapshot-1"


class RecordingEntityResolutionRunner:
    def __init__(self) -> None:
        self.calls: list[dict[str, object]] = []

    def resolve(
        self,
        *,
        context: AgentContext,
        module_key: str,
    ) -> dict[str, object]:
        self.calls.append(
            {
                "tenant_id": context.tenant_id,
                "project_id": context.project_id,
                "run_id": context.run_id,
                "module_key": module_key,
            }
        )
        return {
            "status": "completed",
            "module_key": module_key,
            "model_id": "model-resolution",
            "resolution_snapshot_id": "resolution-snapshot-1",
            "merged_entity_count": 4,
            "alias_count": 6,
            "conflict_count": 1,
            "resolution_snapshot": {"body": "private resolution body must not be returned or emitted"},
        }


class RecordingEntityResolutionSnapshotWriter:
    def __init__(self, error: LLMFacilityError | None = None) -> None:
        self.error = error
        self.calls: list[dict[str, object]] = []

    def record_entity_resolution_snapshot(
        self,
        *,
        context: AgentContext,
        module_key: str,
        model_id: str | None,
        entity_resolution: dict[str, object],
        merged_entity_count: int,
        alias_count: int,
        conflict_count: int,
    ) -> str:
        self.calls.append(
            {
                "tenant_id": context.tenant_id,
                "project_id": context.project_id,
                "run_id": context.run_id,
                "module_key": module_key,
                "model_id": model_id,
                "entity_resolution": entity_resolution,
                "merged_entity_count": merged_entity_count,
                "alias_count": alias_count,
                "conflict_count": conflict_count,
            }
        )
        if self.error is not None:
            raise self.error
        return "resolution-snapshot-1"


class RecordingAgentProfileSnapshotWriter:
    def __init__(self, error: LLMFacilityError | None = None) -> None:
        self.error = error
        self.calls: list[dict[str, object]] = []

    def record_agent_profile_snapshot(
        self,
        *,
        context: AgentContext,
        module_key: str,
        model_id: str | None,
        agent_profiles: dict[str, object],
        profile_count: int,
        memory_seed_count: int,
        relationship_view_count: int,
    ) -> str:
        self.calls.append(
            {
                "tenant_id": context.tenant_id,
                "project_id": context.project_id,
                "run_id": context.run_id,
                "module_key": module_key,
                "model_id": model_id,
                "agent_profiles": agent_profiles,
                "profile_count": profile_count,
                "memory_seed_count": memory_seed_count,
                "relationship_view_count": relationship_view_count,
            }
        )
        if self.error is not None:
            raise self.error
        return "profile-snapshot-1"


class RecordingAgentProfileRunner:
    def __init__(self) -> None:
        self.calls: list[dict[str, object]] = []

    def generate(
        self,
        *,
        context: AgentContext,
        module_key: str,
    ) -> dict[str, object]:
        self.calls.append(
            {
                "tenant_id": context.tenant_id,
                "project_id": context.project_id,
                "run_id": context.run_id,
                "module_key": module_key,
            }
        )
        return {
            "status": "completed",
            "module_key": module_key,
            "model_id": "model-profile",
            "profile_snapshot_id": "profile-snapshot-1",
            "profile_count": 5,
            "memory_seed_count": 8,
            "relationship_view_count": 3,
            "profiles": [{"private_profile": {"body": "private profile body must not be returned or emitted"}}],
        }


class RecordingAgentProfileContextLoader:
    def __init__(self, context_payload: dict[str, object] | None = None, error: Exception | None = None) -> None:
        self.context_payload = context_payload if context_payload is not None else {
            "entity_resolution": {
                "merged_entities": [{"canonical_name": "林舟", "entity_type": "character"}],
            }
        }
        self.error = error
        self.calls: list[dict[str, object]] = []

    def load_context(self, *, context: AgentContext) -> dict[str, object]:
        self.calls.append(
            {
                "tenant_id": context.tenant_id,
                "project_id": context.project_id,
                "run_id": context.run_id,
            }
        )
        if self.error is not None:
            raise self.error
        return self.context_payload


class RecordingArchiveCandidateRunner:
    def __init__(self) -> None:
        self.calls: list[dict[str, object]] = []

    def generate(
        self,
        *,
        context: AgentContext,
        module_key: str,
    ) -> dict[str, object]:
        self.calls.append(
            {
                "tenant_id": context.tenant_id,
                "project_id": context.project_id,
                "run_id": context.run_id,
                "module_key": module_key,
            }
        )
        return {
            "status": "completed",
            "module_key": module_key,
            "model_id": "model-archive",
            "archive_candidate_batch_id": "archive-batch-1",
            "candidate_count": 7,
            "archive_entity_candidate_count": 5,
            "memory_candidate_count": 2,
            "archive_candidates": [
                {"content": "private archive candidate body must not be returned or emitted"}
            ],
        }


class RecordingBindingResolver:
    def __init__(self, result: ModuleBindingResolution | LLMFacilityError) -> None:
        self.result = result
        self.calls: list[str] = []

    def resolve_module_binding(self, *, context: AgentContext, module_key: str) -> ModuleBindingResolution:
        self.calls.append(module_key)
        if isinstance(self.result, LLMFacilityError):
            raise self.result
        return self.result


class RecordingCredentialProvider:
    def __init__(self, api_key: str | None = None, error: LLMFacilityError | None = None) -> None:
        self.api_key = api_key
        self.error = error
        self.calls: list[str] = []

    def resolve_api_key(self, *, context: AgentContext, credential_ref: str) -> str:
        self.calls.append(credential_ref)
        if self.error is not None:
            raise self.error
        return self.api_key or ""


class RecordingJSONChatClient:
    def __init__(self, response_json: dict[str, object]) -> None:
        self.response_json = response_json
        self.calls: list[dict[str, object]] = []

    def complete_json(
        self,
        *,
        context: AgentContext,
        resolution: ModuleBindingResolution,
        api_key: str,
        messages: list[dict[str, str]],
    ) -> dict[str, object]:
        self.calls.append(
            {
                "context": context,
                "resolution": resolution,
                "api_key": api_key,
                "messages": messages,
            }
        )
        return self.response_json


class RecordingArchiveCandidateWriter:
    def __init__(self, error: LLMFacilityError | None = None) -> None:
        self.error = error
        self.calls: list[dict[str, object]] = []

    def write_archive_candidates(
        self,
        *,
        context: AgentContext,
        archive_candidate_batch_id: str,
        model_id: str | None,
        archive_entities: list[dict[str, object]],
    ) -> dict[str, object]:
        self.calls.append(
            {
                "context": context,
                "archive_candidate_batch_id": archive_candidate_batch_id,
                "model_id": model_id,
                "archive_entities": archive_entities,
            }
        )
        if self.error is not None:
            raise self.error
        memory_count = sum(len(entity.get("memories", [])) for entity in archive_entities)
        return {
            "status": "completed",
            "archive_candidate_batch_id": archive_candidate_batch_id,
            "candidate_count": len(archive_entities) + memory_count,
            "archive_entity_candidate_count": len(archive_entities),
            "memory_candidate_count": memory_count,
        }


class RecordingAssetIndexer:
    def __init__(self) -> None:
        self.calls: list[dict[str, object]] = []

    def index(
        self,
        *,
        context: AgentContext,
    ) -> dict[str, object]:
        self.calls.append(
            {
                "tenant_id": context.tenant_id,
                "project_id": context.project_id,
                "run_id": context.run_id,
            }
        )
        return {
            "status": "completed",
            "asset_index_batch_id": "asset-index-batch-1",
            "indexed_asset_count": 9,
            "search_document_count": 12,
            "embedding_count": 4,
            "search_documents": [
                {"body": "private search document body must not be returned or emitted"}
            ],
            "embeddings": [
                {"chunk_text": "private embedding chunk must not be returned or emitted"}
            ],
        }


class RecordingProjectReadinessUpdater:
    def __init__(self) -> None:
        self.calls: list[dict[str, object]] = []

    def update(
        self,
        *,
        context: AgentContext,
    ) -> dict[str, object]:
        self.calls.append(
            {
                "tenant_id": context.tenant_id,
                "project_id": context.project_id,
                "run_id": context.run_id,
            }
        )
        return {
            "status": "completed",
            "project_readiness_snapshot_id": "readiness-snapshot-1",
            "ready_asset_count": 9,
            "ready_entity_count": 4,
            "ready_relationship_count": 3,
            "ready_world_rule_count": 2,
            "readiness_report": {"body": "private readiness body must not be returned or emitted"},
        }


class InMemoryObjectStore:
    def __init__(self, objects: dict[str, bytes] | None = None) -> None:
        self.objects = dict(objects or {})
        self.writes: list[tuple[str, bytes, str]] = []

    def read_bytes(self, object_key: str) -> bytes:
        return self.objects[object_key]

    def write_bytes(self, object_key: str, data: bytes, content_type: str) -> None:
        self.objects[object_key] = data
        self.writes.append((object_key, data, content_type))


UNTRUSTED_OBJECT_STORAGE_ERROR = (
    "driver exploded prompt=hidden api_key=sk-hidden credential_ref=cred-hidden "
    "object_key=projects/project-1/source-files/upload-1/private.txt "
    "source_text=private raw manuscript draft=private manuscript=private"
)


class UnsafeObjectStore:
    def __init__(
        self,
        *,
        objects: dict[str, bytes] | None = None,
        fail_on_read: bool = False,
        fail_on_write: bool = False,
    ) -> None:
        self.objects = dict(objects or {})
        self.fail_on_read = fail_on_read
        self.fail_on_write = fail_on_write
        self.writes: list[tuple[str, bytes, str]] = []

    def read_bytes(self, object_key: str) -> bytes:
        if self.fail_on_read:
            raise RuntimeError(UNTRUSTED_OBJECT_STORAGE_ERROR)
        return self.objects[object_key]

    def write_bytes(self, object_key: str, data: bytes, content_type: str) -> None:
        if self.fail_on_write:
            raise RuntimeError(UNTRUSTED_OBJECT_STORAGE_ERROR)
        self.objects[object_key] = data
        self.writes.append((object_key, data, content_type))


def _assert_untrusted_object_storage_details_redacted(value: object) -> None:
    encoded = json.dumps(value, ensure_ascii=False, default=str)
    for token in (
        "prompt=hidden",
        "api_key",
        "sk-hidden",
        "credential_ref",
        "object_key=projects/project-1/source-files",
        "private raw manuscript",
        "draft=private",
        "manuscript=private",
    ):
        assert token not in encoded


class RecordingHTTPTransport:
    def __init__(self, response_body: bytes = b"") -> None:
        self.response_body = response_body
        self.requests: list[object] = []

    def __call__(self, request: object) -> bytes:
        self.requests.append(request)
        return self.response_body


def test_object_store_from_env_returns_none_when_unconfigured(monkeypatch: pytest.MonkeyPatch) -> None:
    for key in (
        "MIROFISH_OBJECT_STORAGE_ENDPOINT",
        "MIROFISH_OBJECT_STORAGE_BUCKET",
        "MIROFISH_OBJECT_STORAGE_ACCESS_KEY",
        "MIROFISH_OBJECT_STORAGE_SECRET_KEY",
    ):
        monkeypatch.delenv(key, raising=False)

    assert _object_store_from_env() is None


def test_object_store_from_env_creates_s3_compatible_store(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("MIROFISH_OBJECT_STORAGE_ENDPOINT", "minio:9000")
    monkeypatch.setenv("MIROFISH_OBJECT_STORAGE_BUCKET", "mirofish-uploads")
    monkeypatch.setenv("MIROFISH_OBJECT_STORAGE_ACCESS_KEY", "mirofish")
    monkeypatch.setenv("MIROFISH_OBJECT_STORAGE_SECRET_KEY", "secret")
    monkeypatch.setenv("MIROFISH_OBJECT_STORAGE_USE_SSL", "false")

    store = _object_store_from_env()

    assert isinstance(store, S3CompatibleObjectStore)
    assert store.endpoint_url == "http://minio:9000"
    assert store.bucket == "mirofish-uploads"


def test_parse_file_activity_fails_closed_when_object_store_env_is_partial(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("MIROFISH_OBJECT_STORAGE_ENDPOINT", "minio:9000")
    for key in (
        "MIROFISH_OBJECT_STORAGE_BUCKET",
        "MIROFISH_OBJECT_STORAGE_ACCESS_KEY",
        "MIROFISH_OBJECT_STORAGE_SECRET_KEY",
    ):
        monkeypatch.delenv(key, raising=False)

    result = parse_file_activity(
        {
            "context": _context().model_dump(),
            "source_file_id": "file-1",
            "source_object_key": "uploads/source-1.txt",
            "mime_type": "text/plain",
        },
        text_artifact_writer=RecordingTextArtifactWriter(),
    )

    assert result["status"] == "failed"
    assert result["error"]["code"] == "OBJECT_STORAGE_BACKEND_MISCONFIGURED"
    assert "secret" not in result["error"]["message"].lower()


def test_s3_compatible_object_store_reads_and_writes_without_exposing_secret() -> None:
    transport = RecordingHTTPTransport(response_body=b"source bytes")
    store = S3CompatibleObjectStore(
        endpoint="minio:9000",
        bucket="mirofish-uploads",
        access_key="mirofish",
        secret_key="super-secret",
        use_ssl=False,
        http_request=transport,
    )

    assert store.read_bytes("projects/project-1/source.txt") == b"source bytes"
    store.write_bytes("projects/project-1/extracted.txt", b"artifact bytes", "text/plain")

    assert len(transport.requests) == 2
    read_request = transport.requests[0]
    write_request = transport.requests[1]
    assert read_request.full_url == "http://minio:9000/mirofish-uploads/projects/project-1/source.txt"
    assert read_request.get_method() == "GET"
    assert write_request.full_url == "http://minio:9000/mirofish-uploads/projects/project-1/extracted.txt"
    assert write_request.get_method() == "PUT"
    assert write_request.data == b"artifact bytes"
    assert write_request.headers["Content-type"] == "text/plain"
    for request in transport.requests:
        assert "Authorization" in request.headers
        assert "super-secret" not in request.headers["Authorization"]


class FakeCursor:
    def __init__(self) -> None:
        self.query = ""
        self.params: tuple[object, ...] = ()
        self.executed: list[tuple[str, tuple[object, ...]]] = []

    def __enter__(self) -> "FakeCursor":
        return self

    def __exit__(self, exc_type: object, exc: object, traceback: object) -> None:
        return None

    def execute(self, query: str, params: tuple[object, ...]) -> None:
        self.query = query
        self.params = params
        self.executed.append((query, params))

    def fetchone(self) -> dict[str, object]:
        return {
            "entity_id": "entity-1",
            "seed_analysis_snapshot_id": "snapshot-1",
        }


class FakeAssetIndexCursor(FakeCursor):
    def __init__(self, rows: list[dict[str, object]]) -> None:
        super().__init__()
        self.rows = list(rows)

    def fetchone(self) -> dict[str, object]:
        if not self.rows:
            raise AssertionError("unexpected fetchone call")
        return self.rows.pop(0)


class FakeConnection:
    def __init__(self) -> None:
        self.cursor_instance = FakeCursor()
        self.committed = False
        self.rolled_back = False
        self.closed = False

    def cursor(self) -> FakeCursor:
        return self.cursor_instance

    def commit(self) -> None:
        self.committed = True

    def rollback(self) -> None:
        self.rolled_back = True

    def close(self) -> None:
        self.closed = True


class FakeOntologySnapshotCursor(FakeCursor):
    def __init__(self, rows: list[dict[str, object]]) -> None:
        super().__init__()
        self.rows = list(rows)

    def fetchone(self) -> dict[str, object]:
        if not self.rows:
            raise AssertionError("unexpected fetchone call")
        return self.rows.pop(0)


class FakeOntologySnapshotConnection(FakeConnection):
    def __init__(self, rows: list[dict[str, object]]) -> None:
        self.cursor_instance = FakeOntologySnapshotCursor(rows)
        self.committed = False
        self.rolled_back = False
        self.closed = False


class FakeAssetIndexConnection(FakeConnection):
    def __init__(self, rows: list[dict[str, object]]) -> None:
        self.cursor_instance = FakeAssetIndexCursor(rows)
        self.committed = False
        self.rolled_back = False
        self.closed = False


class FakeWorkflowStatusCursor(FakeCursor):
    def __init__(self, rows: list[dict[str, object]]) -> None:
        super().__init__()
        self.rows = list(rows)

    def fetchone(self) -> dict[str, object]:
        if not self.rows:
            raise AssertionError("unexpected fetchone call")
        return self.rows.pop(0)


class FakeWorkflowStatusConnection(FakeConnection):
    def __init__(self, rows: list[dict[str, object]]) -> None:
        self.cursor_instance = FakeWorkflowStatusCursor(rows)
        self.committed = False
        self.rolled_back = False
        self.closed = False


class FailingAssetIndexCursor(FakeAssetIndexCursor):
    def __init__(self, rows: list[dict[str, object]], *, fail_on_execute: int | None = None) -> None:
        super().__init__(rows)
        self.fail_on_execute = fail_on_execute
        self.execute_count = 0

    def execute(self, query: str, params: tuple[object, ...]) -> None:
        self.execute_count += 1
        super().execute(query, params)
        if self.fail_on_execute is not None and self.execute_count == self.fail_on_execute:
            raise RuntimeError("driver failure prompt=hidden api_key=sk-hidden credential_ref=secret")


class FailingAssetIndexConnection(FakeConnection):
    def __init__(
        self,
        rows: list[dict[str, object]],
        *,
        fail_on_execute: int | None = None,
        fail_on_commit: bool = False,
    ) -> None:
        self.cursor_instance = FailingAssetIndexCursor(rows, fail_on_execute=fail_on_execute)
        self.committed = False
        self.rolled_back = False
        self.closed = False
        self.fail_on_commit = fail_on_commit

    def commit(self) -> None:
        if self.fail_on_commit:
            raise RuntimeError("commit failure prompt=hidden api_key=sk-hidden credential_ref=secret")
        super().commit()


class FailingCursor(FakeCursor):
    def __init__(self, *, fail_on_execute: int) -> None:
        super().__init__()
        self.fail_on_execute = fail_on_execute
        self.execute_count = 0

    def execute(self, query: str, params: tuple[object, ...]) -> None:
        self.execute_count += 1
        super().execute(query, params)
        if self.execute_count == self.fail_on_execute:
            raise RuntimeError("driver failure prompt=hidden api_key=sk-hidden credential_ref=secret")


class FailingConnection(FakeConnection):
    def __init__(self, *, fail_on_execute: int | None = None, fail_on_commit: bool = False) -> None:
        super().__init__()
        self.fail_on_commit = fail_on_commit
        if fail_on_execute is not None:
            self.cursor_instance = FailingCursor(fail_on_execute=fail_on_execute)

    def commit(self) -> None:
        if self.fail_on_commit:
            raise RuntimeError("commit failure prompt=hidden api_key=sk-hidden credential_ref=secret")
        super().commit()


class FakeArchiveCandidateCursor(FakeCursor):
    def __init__(self, rows: list[dict[str, object]]) -> None:
        super().__init__()
        self.rows = list(rows)

    def fetchone(self) -> dict[str, object]:
        if not self.rows:
            raise AssertionError("unexpected fetchone call")
        return self.rows.pop(0)


class FakeArchiveCandidateConnection(FakeConnection):
    def __init__(self, rows: list[dict[str, object]]) -> None:
        self.cursor_instance = FakeArchiveCandidateCursor(rows)
        self.committed = False
        self.rolled_back = False
        self.closed = False


class FailingArchiveCandidateCursor(FakeArchiveCandidateCursor):
    def __init__(self, rows: list[dict[str, object]], *, fail_on_execute: int | None = None) -> None:
        super().__init__(rows)
        self.fail_on_execute = fail_on_execute
        self.execute_count = 0

    def execute(self, query: str, params: tuple[object, ...]) -> None:
        self.execute_count += 1
        super().execute(query, params)
        if self.fail_on_execute is not None and self.execute_count == self.fail_on_execute:
            raise RuntimeError(
                "driver failure prompt=hidden api_key=sk-hidden "
                "credential_ref=secret raw novel text"
            )


class FailingArchiveCandidateConnection(FakeConnection):
    def __init__(
        self,
        rows: list[dict[str, object]],
        *,
        fail_on_execute: int | None = None,
        fail_on_commit: bool = False,
    ) -> None:
        self.cursor_instance = FailingArchiveCandidateCursor(rows, fail_on_execute=fail_on_execute)
        self.committed = False
        self.rolled_back = False
        self.closed = False
        self.fail_on_commit = fail_on_commit

    def commit(self) -> None:
        if self.fail_on_commit:
            raise RuntimeError(
                "commit failure prompt=hidden api_key=sk-hidden "
                "credential_ref=secret raw novel text"
            )
        super().commit()


def _assert_untrusted_archive_candidate_db_error_redacted(value: object) -> None:
    encoded = json.dumps(value, ensure_ascii=False, default=str)
    for token in (
        "prompt=hidden",
        "api_key",
        "sk-hidden",
        "credential_ref",
        "raw novel text",
    ):
        assert token not in encoded


class FakeProjectReadinessCursor(FakeCursor):
    def __init__(self, rows: list[dict[str, object]]) -> None:
        super().__init__()
        self.rows = list(rows)

    def fetchone(self) -> dict[str, object]:
        if not self.rows:
            raise AssertionError("unexpected fetchone call")
        return self.rows.pop(0)


class FakeProjectReadinessConnection(FakeConnection):
    def __init__(self, rows: list[dict[str, object]]) -> None:
        self.cursor_instance = FakeProjectReadinessCursor(rows)
        self.committed = False
        self.rolled_back = False
        self.closed = False


class FailingProjectReadinessCursor(FakeProjectReadinessCursor):
    def __init__(self, rows: list[dict[str, object]], *, fail_on_execute: int | None = None) -> None:
        super().__init__(rows)
        self.fail_on_execute = fail_on_execute
        self.execute_count = 0

    def execute(self, query: str, params: tuple[object, ...]) -> None:
        self.execute_count += 1
        super().execute(query, params)
        if self.fail_on_execute is not None and self.execute_count == self.fail_on_execute:
            raise RuntimeError(
                "driver failure prompt=hidden api_key=sk-hidden "
                "credential_ref=secret private readiness body raw novel text"
            )


class FailingProjectReadinessConnection(FakeConnection):
    def __init__(
        self,
        rows: list[dict[str, object]],
        *,
        fail_on_execute: int | None = None,
        fail_on_commit: bool = False,
    ) -> None:
        self.cursor_instance = FailingProjectReadinessCursor(rows, fail_on_execute=fail_on_execute)
        self.committed = False
        self.rolled_back = False
        self.closed = False
        self.fail_on_commit = fail_on_commit

    def commit(self) -> None:
        if self.fail_on_commit:
            raise RuntimeError(
                "commit failure prompt=hidden api_key=sk-hidden "
                "credential_ref=secret private readiness body raw novel text"
            )
        super().commit()


def _assert_untrusted_project_readiness_db_error_redacted(value: object) -> None:
    encoded = json.dumps(value, ensure_ascii=False, default=str)
    for token in (
        "prompt=hidden",
        "api_key",
        "sk-hidden",
        "credential_ref",
        "private readiness body",
        "raw novel text",
    ):
        assert token not in encoded


def _archive_resolution() -> ModuleBindingResolution:
    return ModuleBindingResolution(
        tenant_id="tenant-1",
        project_id="project-1",
        module_key="narrative_archives",
        channel_id="channel-archive",
        model_id="model-archive",
        provider="openai-compatible",
        base_url="https://llm.example/v1",
        credential_ref="channel-archive",
        supports_json=True,
    )


def _ontology_resolution() -> ModuleBindingResolution:
    return ModuleBindingResolution(
        tenant_id="tenant-1",
        project_id="project-1",
        module_key="story_ontology",
        channel_id="channel-ontology",
        model_id="model-ontology",
        provider="openai-compatible",
        base_url="https://llm.example/v1",
        credential_ref="channel-ontology",
        supports_json=True,
    )


def _entity_resolution() -> ModuleBindingResolution:
    return ModuleBindingResolution(
        tenant_id="tenant-1",
        project_id="project-1",
        module_key="entity_resolution",
        channel_id="channel-resolution",
        model_id="model-resolution",
        provider="openai-compatible",
        base_url="https://llm.example/v1",
        credential_ref="channel-resolution",
        supports_json=True,
    )


def _agent_profile_resolution() -> ModuleBindingResolution:
    return ModuleBindingResolution(
        tenant_id="tenant-1",
        project_id="project-1",
        module_key="character_agent_profile",
        channel_id="channel-profile",
        model_id="model-profile",
        provider="openai-compatible",
        base_url="https://llm.example/v1",
        credential_ref="channel-profile",
        supports_json=True,
    )


class AgentProfileContextCursor:
    def __init__(
        self,
        *,
        resolution_rows: list[dict[str, object]],
        entity_rows: list[dict[str, object]],
        relationship_rows: list[dict[str, object]],
        segment_rows: list[dict[str, object]],
    ) -> None:
        self._row_sets = [resolution_rows, entity_rows, relationship_rows, segment_rows]
        self.executed: list[tuple[str, tuple[object, ...]]] = []
        self.query = ""
        self.params: tuple[object, ...] = ()

    def __enter__(self) -> "AgentProfileContextCursor":
        return self

    def __exit__(self, exc_type: object, exc: object, traceback: object) -> None:
        return None

    def execute(self, query: str, params: tuple[object, ...]) -> None:
        self.query = query
        self.params = params
        self.executed.append((query, params))

    def fetchone(self) -> dict[str, object] | None:
        if len(self.executed) != 2:
            raise AssertionError("unexpected fetchone call")
        rows = self._row_sets[0]
        return rows[0] if rows else None

    def fetchall(self) -> list[dict[str, object]]:
        if len(self.executed) == 3:
            return self._row_sets[1]
        if len(self.executed) == 4:
            return self._row_sets[2]
        if len(self.executed) == 5:
            return self._row_sets[3]
        raise AssertionError("unexpected fetchall call")


class AgentProfileContextConnection:
    def __init__(
        self,
        *,
        resolution_rows: list[dict[str, object]],
        entity_rows: list[dict[str, object]],
        relationship_rows: list[dict[str, object]],
        segment_rows: list[dict[str, object]],
    ) -> None:
        self.cursor_instance = AgentProfileContextCursor(
            resolution_rows=resolution_rows,
            entity_rows=entity_rows,
            relationship_rows=relationship_rows,
            segment_rows=segment_rows,
        )
        self.closed = False

    def cursor(self) -> AgentProfileContextCursor:
        return self.cursor_instance

    def close(self) -> None:
        self.closed = True


class QueryCursor:
    def __init__(self, rows: list[dict[str, object]]) -> None:
        self.rows = rows
        self.query = ""
        self.params: tuple[object, ...] = ()

    def __enter__(self) -> "QueryCursor":
        return self

    def __exit__(self, exc_type: object, exc: object, traceback: object) -> None:
        return None

    def execute(self, query: str, params: tuple[object, ...]) -> None:
        self.query = query
        self.params = params

    def fetchone(self) -> dict[str, object] | None:
        return self.rows[0] if self.rows else None


class QueryConnection:
    def __init__(self, rows: list[dict[str, object]]) -> None:
        self.cursor_instance = QueryCursor(rows)
        self.closed = False

    def cursor(self) -> QueryCursor:
        return self.cursor_instance

    def close(self) -> None:
        self.closed = True


class AggregateInputCursor:
    def __init__(self, *, segment_rows: list[dict[str, object]], count_rows: list[dict[str, object]]) -> None:
        self.segment_rows = segment_rows
        self.count_rows = count_rows
        self.query_count = 0
        self.executed: list[tuple[str, tuple[object, ...]]] = []

    def __enter__(self) -> "AggregateInputCursor":
        return self

    def __exit__(self, exc_type: object, exc: object, traceback: object) -> None:
        return None

    def execute(self, query: str, params: tuple[object, ...]) -> None:
        self.query_count += 1
        self.executed.append((query, params))

    def fetchall(self) -> list[dict[str, object]]:
        if self.query_count == 1:
            return self.segment_rows
        return self.count_rows


class AggregateInputConnection:
    def __init__(self, *, segment_rows: list[dict[str, object]], count_rows: list[dict[str, object]]) -> None:
        self.cursor_instance = AggregateInputCursor(segment_rows=segment_rows, count_rows=count_rows)
        self.closed = False

    def cursor(self) -> AggregateInputCursor:
        return self.cursor_instance

    def close(self) -> None:
        self.closed = True


class RecordingAggregateInputConnection(AggregateInputConnection):
    @property
    def cursor_instance(self) -> AggregateInputCursor:
        return self._cursor_instance

    @cursor_instance.setter
    def cursor_instance(self, value: AggregateInputCursor) -> None:
        self._cursor_instance = value


def test_seed_pipeline_activity_records_sanitized_pending_stage_event() -> None:
    writer = RecordingWorkflowEventWriter()

    result = seed_pipeline_activity(
        {
            "context": _context().model_dump(),
            "upload_id": "upload-1",
            "options": {
                "language": "zh-CN",
                "prompt": "must not be copied to workflow_events",
                "api_key": "sk-test",
                "raw_content": "novel body must not be copied",
            },
        },
        workflow_event_writer=writer,
    )

    assert result["status"] == "queued"
    assert writer.events == [
        {
            "tenant_id": "tenant-1",
            "project_id": "project-1",
            "run_id": "run-1",
            "workflow_type": "seed_pipeline",
            "event_type": "seed.stage.pending",
            "payload": {
                "stage": "parse_file",
                "status": "pending",
                "activity": "seed_pipeline_activity",
                "upload_id": "upload-1",
            },
        }
    ]


def test_seed_pipeline_activity_sanitizes_workflow_event_writer_exception() -> None:
    class FailingWorkflowEventWriter:
        def record_workflow_event(
            self,
            *,
            context: AgentContext,
            event_type: str,
            payload: dict[str, object],
        ) -> None:
            raise RuntimeError(
                "driver failed prompt=hidden api_key=sk-hidden credential_ref=cred-hidden "
                "object_key=projects/project-1/source-files/upload-1/book.txt draft=private manuscript=private"
            )

    result = seed_pipeline_activity(
        {
            "context": _context().model_dump(),
            "upload_id": "upload-1",
            "options": {"language": "zh-CN"},
        },
        workflow_event_writer=FailingWorkflowEventWriter(),
    )

    assert result["status"] == "failed"
    assert result["error"] == {
        "code": "WORKFLOW_EVENT_WRITE_FAILED",
        "message": "workflow event write failed",
    }
    public_body = json.dumps(result, ensure_ascii=False, sort_keys=True)
    for forbidden in (
        "driver failed",
        "prompt",
        "api_key",
        "sk-hidden",
        "credential_ref",
        "object_key",
        "projects/project-1/source-files",
        "draft",
        "manuscript",
    ):
        assert forbidden not in public_body


def test_seed_pipeline_activity_sanitizes_workflow_event_writer_env_resolution_exception(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def fail_from_env() -> None:
        raise RuntimeError(
            "event writer env failed prompt=hidden api_key=sk-hidden credential_ref=cred-hidden "
            "object_key=projects/project-1/source-files/upload-1/book.txt draft=private manuscript=private"
        )

    monkeypatch.setattr(seed_module, "_workflow_event_writer_from_env", fail_from_env)

    result = seed_pipeline_activity(
        {
            "context": _context().model_dump(),
            "upload_id": "upload-1",
            "options": {"language": "zh-CN"},
        }
    )

    assert result["status"] == "failed"
    assert result["error"] == {
        "code": "WORKFLOW_EVENT_WRITE_FAILED",
        "message": "workflow event write failed",
    }
    public_body = json.dumps(result, ensure_ascii=False, sort_keys=True)
    for forbidden in (
        "event writer env failed",
        "prompt",
        "api_key",
        "sk-hidden",
        "credential_ref",
        "object_key",
        "projects/project-1/source-files",
        "draft",
        "manuscript",
    ):
        assert forbidden not in public_body


def test_seed_pipeline_activity_marks_workflow_running_when_worker_accepts_run() -> None:
    workflow_writer = RecordingWorkflowEventWriter()
    status_writer = RecordingWorkflowRunStatusWriter()

    result = seed_pipeline_activity(
        {
            "context": _context().model_dump(),
            "upload_id": "upload-1",
            "options": {
                "language": "zh-CN",
                "prompt": "must not be copied to workflow status",
                "api_key": "sk-test",
                "raw_content": "novel body must not be copied",
            },
        },
        workflow_event_writer=workflow_writer,
        workflow_status_writer=status_writer,
    )

    assert result["status"] == "queued"
    assert result["workflow_status_persisted"] is True
    assert status_writer.running == [
        {
            "tenant_id": "tenant-1",
            "project_id": "project-1",
            "run_id": "run-1",
        }
    ]
    assert status_writer.failed == []
    assert status_writer.completed == []
    public_body = json.dumps([result, status_writer.running, workflow_writer.events], ensure_ascii=False)
    for forbidden in ("prompt", "api_key", "raw_content", "credential_ref", "draft", "manuscript"):
        assert forbidden not in public_body


def test_postgres_workflow_event_writer_inserts_sanitized_workflow_event() -> None:
    connection = FakeConnection()
    writer = PostgresWorkflowEventWriter(connect=lambda: connection)

    writer.record_workflow_event(
        context=_context(),
        event_type="seed.stage.pending",
        payload={
            "stage": "parse_file",
            "status": "pending",
            "api_key": "sk-test",
            "content": "raw body must not be stored",
        },
    )

    assert connection.cursor_instance.executed[0] == (
        "SELECT app_set_tenant_context(%s::uuid, %s::uuid, false)",
        ("tenant-1", "project-1"),
    )
    assert "INSERT INTO workflow_events" in connection.cursor_instance.query
    assert "COALESCE(MAX(sequence), 0) + 1" in connection.cursor_instance.query
    assert connection.cursor_instance.params[:5] == (
        "tenant-1",
        "run-1",
        "seed_pipeline",
        "project-1",
        "seed.stage.pending",
    )
    assert connection.cursor_instance.params[5] == '{"stage":"parse_file","status":"pending"}'
    assert connection.committed is True
    assert connection.closed is True


def test_parse_file_activity_writes_extracted_text_artifact_without_returning_raw_text() -> None:
    workflow_writer = RecordingWorkflowEventWriter()
    artifact_writer = RecordingTextArtifactWriter()
    status_writer = RecordingSourceFileStatusWriter()
    object_store = InMemoryObjectStore(
        {"uploads/source-1.txt": "第一行\n第二行\n".encode("utf-8")}
    )

    result = parse_file_activity(
        {
            "context": _context().model_dump(),
            "source_file_id": "file-1",
            "source_object_key": "uploads/source-1.txt",
            "mime_type": "text/plain",
        },
        source_object_store=object_store,
        artifact_object_store=object_store,
        text_artifact_writer=artifact_writer,
        workflow_event_writer=workflow_writer,
        source_status_writer=status_writer,
    )

    assert result["status"] == "completed"
    assert result["next_stage"] == "segment_text"
    assert result["artifact_type"] == "extracted_text"
    assert result["char_count"] == 8
    assert result["line_count"] == 2
    assert "text" not in result
    assert "content" not in result
    assert object_store.writes == [
        (
            "projects/project-1/seed-runs/run-1/extracted/file-1.txt",
            "第一行\n第二行\n".encode("utf-8"),
            "text/plain; charset=utf-8",
        )
    ]
    assert artifact_writer.artifacts == [
        {
            "tenant_id": "tenant-1",
            "project_id": "project-1",
            "run_id": "run-1",
            "source_file_id": "file-1",
            "artifact_type": "extracted_text",
            "object_key": "projects/project-1/seed-runs/run-1/extracted/file-1.txt",
            "char_count": 8,
            "line_count": 2,
            "sha256": result["sha256"],
            "metadata_jsonb": {
                "mime_type": "text/plain",
                "source_object_key": "uploads/source-1.txt",
            },
        }
    ]
    assert status_writer.statuses == [
        {
            "tenant_id": "tenant-1",
            "project_id": "project-1",
            "run_id": "run-1",
            "source_file_id": "file-1",
            "parse_status": "parsed",
        }
    ]
    assert workflow_writer.events == [
        {
            "tenant_id": "tenant-1",
            "project_id": "project-1",
            "run_id": "run-1",
            "workflow_type": "seed_pipeline",
            "event_type": "seed.stage.completed",
            "payload": {
                "stage": "parse_file",
                "status": "completed",
                "activity": "parse_file_activity",
                "source_file_id": "file-1",
                "artifact_type": "extracted_text",
                "char_count": 8,
                "line_count": 2,
            },
        }
    ]


def test_parse_file_activity_sanitizes_workflow_event_writer_env_resolution_exception(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def fail_from_env() -> None:
        raise RuntimeError(
            "parse event writer env failed prompt=hidden api_key=sk-hidden credential_ref=cred-hidden "
            "object_key=projects/project-1/source-files/upload-1/book.txt draft=private manuscript=private"
        )

    monkeypatch.setattr(seed_module, "_workflow_event_writer_from_env", fail_from_env)

    result = parse_file_activity(
        {
            "context": _context().model_dump(),
            "source_file_id": "file-1",
            "source_object_key": "uploads/source-1.txt",
            "mime_type": "text/plain",
        },
        source_object_store=InMemoryObjectStore({"uploads/source-1.txt": b"body"}),
        artifact_object_store=InMemoryObjectStore(),
        text_artifact_writer=RecordingTextArtifactWriter(),
        source_status_writer=RecordingSourceFileStatusWriter(),
    )

    assert result["status"] == "failed"
    assert result["stage"] == "parse_file"
    assert result["source_file_id"] == "file-1"
    assert result["error"] == {
        "code": "WORKFLOW_EVENT_WRITE_FAILED",
        "message": "workflow event write failed",
    }
    public_body = json.dumps(result, ensure_ascii=False, sort_keys=True)
    for forbidden in (
        "parse event writer env failed",
        "prompt",
        "api_key",
        "sk-hidden",
        "credential_ref",
        "object_key",
        "projects/project-1/source-files",
        "draft",
        "manuscript",
    ):
        assert forbidden not in public_body


def test_parse_file_activity_does_not_record_completed_event_when_source_status_update_fails() -> None:
    workflow_writer = RecordingWorkflowEventWriter()
    artifact_writer = RecordingTextArtifactWriter()
    status_writer = FailingSourceFileStatusWriter()
    object_store = InMemoryObjectStore(
        {"uploads/source-1.txt": "第一行\n第二行\n".encode("utf-8")}
    )

    result = parse_file_activity(
        {
            "context": _context().model_dump(),
            "source_file_id": "file-1",
            "source_object_key": "uploads/source-1.txt",
            "mime_type": "text/plain",
        },
        source_object_store=object_store,
        artifact_object_store=object_store,
        text_artifact_writer=artifact_writer,
        workflow_event_writer=workflow_writer,
        source_status_writer=status_writer,
    )

    assert result["status"] == "failed"
    assert result["error"]["code"] == "SOURCE_FILE_PARSE_STATUS_UPDATE_FAILED"
    assert "seed.stage.completed" not in [event["event_type"] for event in workflow_writer.events]
    assert workflow_writer.events == [
        {
            "tenant_id": "tenant-1",
            "project_id": "project-1",
            "run_id": "run-1",
            "workflow_type": "seed_pipeline",
            "event_type": "seed.stage.failed",
            "payload": {
                "stage": "parse_file",
                "status": "failed",
                "activity": "parse_file_activity",
                "source_file_id": "file-1",
                "error_code": "SOURCE_FILE_PARSE_STATUS_UPDATE_FAILED",
                "error_message": "source file parse status update failed",
            },
        }
    ]


def test_parse_file_activity_records_status_failure_event_when_failed_status_update_fails() -> None:
    workflow_writer = RecordingWorkflowEventWriter()
    status_writer = FailingSourceFileStatusWriter()

    result = parse_file_activity(
        {
            "context": _context().model_dump(),
            "source_file_id": "file-1",
            "source_object_key": "uploads/missing.txt",
            "mime_type": "text/plain",
        },
        source_object_store=InMemoryObjectStore({}),
        artifact_object_store=InMemoryObjectStore({}),
        text_artifact_writer=RecordingTextArtifactWriter(),
        workflow_event_writer=workflow_writer,
        source_status_writer=status_writer,
    )

    assert result["status"] == "failed"
    assert result["error"]["code"] == "SOURCE_FILE_PARSE_STATUS_UPDATE_FAILED"
    assert workflow_writer.events == [
        {
            "tenant_id": "tenant-1",
            "project_id": "project-1",
            "run_id": "run-1",
            "workflow_type": "seed_pipeline",
            "event_type": "seed.stage.failed",
            "payload": {
                "stage": "parse_file",
                "status": "failed",
                "activity": "parse_file_activity",
                "source_file_id": "file-1",
                "error_code": "SOURCE_FILE_PARSE_STATUS_UPDATE_FAILED",
                "error_message": "source file parse status update failed",
            },
        }
    ]


def test_parse_file_activity_extracts_pdf_text_without_returning_raw_text() -> None:
    workflow_writer = RecordingWorkflowEventWriter()
    artifact_writer = RecordingTextArtifactWriter()
    pdf_bytes = _minimal_text_pdf("Chapter One Rain Night")
    object_store = InMemoryObjectStore({"uploads/source-1.pdf": pdf_bytes})

    result = parse_file_activity(
        {
            "context": _context().model_dump(),
            "source_file_id": "file-1",
            "source_object_key": "uploads/source-1.pdf",
            "mime_type": "application/pdf",
        },
        source_object_store=object_store,
        artifact_object_store=object_store,
        text_artifact_writer=artifact_writer,
        workflow_event_writer=workflow_writer,
    )

    assert result["status"] == "completed"
    assert result["next_stage"] == "segment_text"
    assert result["artifact_type"] == "extracted_text"
    assert "text" not in result
    assert "content" not in result
    assert "Chapter One Rain Night" in object_store.writes[0][1].decode("utf-8")
    assert artifact_writer.artifacts[0]["metadata_jsonb"] == {
        "mime_type": "application/pdf",
        "source_object_key": "uploads/source-1.pdf",
    }
    assert workflow_writer.events[0]["payload"]["stage"] == "parse_file"
    assert workflow_writer.events[0]["payload"]["status"] == "completed"
    assert "Chapter One Rain Night" not in str(result)
    assert "Chapter One Rain Night" not in str(workflow_writer.events)


def test_parse_file_activity_fails_closed_for_unextractable_pdf_without_leaking_bytes() -> None:
    workflow_writer = RecordingWorkflowEventWriter()
    artifact_writer = RecordingTextArtifactWriter()
    status_writer = RecordingSourceFileStatusWriter()
    object_store = InMemoryObjectStore({"uploads/source-1.pdf": b"not a pdf prompt=hidden api_key=sk-hidden"})

    result = parse_file_activity(
        {
            "context": _context().model_dump(),
            "source_file_id": "file-1",
            "source_object_key": "uploads/source-1.pdf",
            "mime_type": "application/pdf",
        },
        source_object_store=object_store,
        artifact_object_store=object_store,
        text_artifact_writer=artifact_writer,
        workflow_event_writer=workflow_writer,
        source_status_writer=status_writer,
    )

    assert result["status"] == "failed"
    assert result["error"] == {
        "code": "FILE_PARSE_DECODE_FAILED",
        "message": "source object text extraction failed",
    }
    assert artifact_writer.artifacts == []
    assert object_store.writes == []
    assert "not a pdf" not in str(result)
    assert "api_key" not in str(result)
    assert "sk-hidden" not in str(result)
    assert "not a pdf" not in str(workflow_writer.events)
    assert "api_key" not in str(workflow_writer.events)
    assert "sk-hidden" not in str(workflow_writer.events)
    assert status_writer.statuses == [
        {
            "tenant_id": "tenant-1",
            "project_id": "project-1",
            "run_id": "run-1",
            "source_file_id": "file-1",
            "parse_status": "failed",
        }
    ]


def test_segment_text_activity_writes_real_segments_without_returning_raw_text() -> None:
    workflow_writer = RecordingWorkflowEventWriter()
    segment_writer = RecordingTextSegmentWriter()
    source_text = "第一章 雨夜\n雨声压住脚步。\n\n第二章 破晓\n光落在窗沿。\n"
    object_store = InMemoryObjectStore(
        {"projects/project-1/seed-runs/run-1/extracted/file-1.txt": source_text.encode("utf-8")}
    )

    result = segment_text_activity(
        {
            "context": _context().model_dump(),
            "source_file_id": "file-1",
            "artifact_object_key": "projects/project-1/seed-runs/run-1/extracted/file-1.txt",
            "artifact_type": "extracted_text",
        },
        artifact_object_store=object_store,
        text_segment_writer=segment_writer,
        workflow_event_writer=workflow_writer,
    )

    assert result["status"] == "completed"
    assert result["stage"] == "segment_text"
    assert result["next_stage"] == "sequential_reading"
    assert result["segment_count"] == 2
    assert result["segments"] == [
        {
            "segment_id": segment_writer.segments[0]["segment_id"],
            "segment_order": 0,
            "chapter_guess": "第一章",
            "title_guess": "雨夜",
            "object_key": "projects/project-1/seed-runs/run-1/segments/0000.txt",
        },
        {
            "segment_id": segment_writer.segments[1]["segment_id"],
            "segment_order": 1,
            "chapter_guess": "第二章",
            "title_guess": "破晓",
            "object_key": "projects/project-1/seed-runs/run-1/segments/0001.txt",
        },
    ]
    assert "text" not in result
    assert "content" not in result
    assert [segment["segment_order"] for segment in segment_writer.segments] == [0, 1]
    assert [segment["segment_id"] for segment in segment_writer.segments] == [
        result["segments"][0]["segment_id"],
        result["segments"][1]["segment_id"],
    ]
    assert [segment["chapter_guess"] for segment in segment_writer.segments] == ["第一章", "第二章"]
    assert [segment["title_guess"] for segment in segment_writer.segments] == ["雨夜", "破晓"]
    assert [write[0] for write in object_store.writes] == [
        "projects/project-1/seed-runs/run-1/segments/0000.txt",
        "projects/project-1/seed-runs/run-1/segments/0001.txt",
    ]
    assert object_store.writes[0][1].decode("utf-8") == "第一章 雨夜\n雨声压住脚步。"
    assert workflow_writer.events == [
        {
            "tenant_id": "tenant-1",
            "project_id": "project-1",
            "run_id": "run-1",
            "workflow_type": "seed_pipeline",
            "event_type": "seed.stage.pending",
            "payload": {
                "stage": "segment_text",
                "status": "pending",
                "activity": "segment_text_activity",
                "source_file_id": "file-1",
                "artifact_type": "extracted_text",
            },
        },
        {
            "tenant_id": "tenant-1",
            "project_id": "project-1",
            "run_id": "run-1",
            "workflow_type": "seed_pipeline",
            "event_type": "seed.stage.completed",
            "payload": {
                "stage": "segment_text",
                "status": "completed",
                "activity": "segment_text_activity",
                "source_file_id": "file-1",
                "segment_count": 2,
            },
        },
    ]


def test_segment_text_activity_sanitizes_workflow_event_writer_env_resolution_exception(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def fail_from_env() -> None:
        raise RuntimeError(
            "segment event writer env failed prompt=hidden api_key=sk-hidden credential_ref=cred-hidden "
            "object_key=projects/project-1/seed-runs/run-1/extracted/file-1.txt draft=private manuscript=private"
        )

    monkeypatch.setattr(seed_module, "_workflow_event_writer_from_env", fail_from_env)

    result = segment_text_activity(
        {
            "context": _context().model_dump(),
            "source_file_id": "file-1",
            "artifact_object_key": "projects/project-1/seed-runs/run-1/extracted/file-1.txt",
            "artifact_type": "extracted_text",
        },
        artifact_object_store=InMemoryObjectStore(
            {"projects/project-1/seed-runs/run-1/extracted/file-1.txt": b"body"}
        ),
        text_segment_writer=RecordingTextSegmentWriter(),
    )

    assert result["status"] == "failed"
    assert result["source_file_id"] == "file-1"
    assert result["error"] == {
        "code": "WORKFLOW_EVENT_WRITE_FAILED",
        "message": "workflow event write failed",
    }
    public_body = json.dumps(result, ensure_ascii=False, sort_keys=True)
    for forbidden in (
        "segment event writer env failed",
        "prompt",
        "api_key",
        "sk-hidden",
        "credential_ref",
        "object_key",
        "projects/project-1/seed-runs",
        "draft",
        "manuscript",
    ):
        assert forbidden not in public_body


def test_segment_text_activity_sanitizes_workflow_event_writer_env_resolution_exception_before_artifact_validation(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def fail_from_env() -> None:
        raise RuntimeError(
            "segment unsupported artifact writer env failed prompt=hidden api_key=sk-hidden "
            "credential_ref=cred-hidden object_key=private draft=private manuscript=private"
        )

    monkeypatch.setattr(seed_module, "_workflow_event_writer_from_env", fail_from_env)

    result = segment_text_activity(
        {
            "context": _context().model_dump(),
            "source_file_id": "file-1",
            "artifact_object_key": "projects/project-1/seed-runs/run-1/extracted/file-1.txt",
            "artifact_type": "normalized_text",
        },
        artifact_object_store=InMemoryObjectStore(
            {"projects/project-1/seed-runs/run-1/extracted/file-1.txt": b"body"}
        ),
        text_segment_writer=RecordingTextSegmentWriter(),
    )

    assert result["status"] == "failed"
    assert result["source_file_id"] == "file-1"
    assert result["error"] == {
        "code": "WORKFLOW_EVENT_WRITE_FAILED",
        "message": "workflow event write failed",
    }
    public_body = json.dumps(result, ensure_ascii=False, sort_keys=True)
    for forbidden in (
        "segment unsupported artifact writer env failed",
        "prompt",
        "api_key",
        "sk-hidden",
        "credential_ref",
        "object_key",
        "draft",
        "manuscript",
    ):
        assert forbidden not in public_body


def test_segment_text_activity_splits_long_unheaded_text_into_paragraph_windows() -> None:
    workflow_writer = RecordingWorkflowEventWriter()
    segment_writer = RecordingTextSegmentWriter()
    paragraph_a = "雨声压住脚步，旧街的灯一盏盏暗下。" * 90
    paragraph_b = "她把地图摊在桌面，所有标记都指向同一座塔。" * 90
    paragraph_c = "黎明前的钟声响起，城门外终于传来回信。" * 90
    source_text = f"{paragraph_a}\n\n{paragraph_b}\n\n{paragraph_c}"
    object_store = InMemoryObjectStore(
        {"projects/project-1/seed-runs/run-1/extracted/file-1.txt": source_text.encode("utf-8")}
    )

    result = segment_text_activity(
        {
            "context": _context().model_dump(),
            "source_file_id": "file-1",
            "artifact_object_key": "projects/project-1/seed-runs/run-1/extracted/file-1.txt",
            "artifact_type": "extracted_text",
        },
        artifact_object_store=object_store,
        text_segment_writer=segment_writer,
        workflow_event_writer=workflow_writer,
    )

    assert result["status"] == "completed"
    assert result["segment_count"] == 3
    assert [segment["segment_order"] for segment in segment_writer.segments] == [0, 1, 2]
    assert [segment["chapter_guess"] for segment in segment_writer.segments] == [None, None, None]
    assert [segment["title_guess"] for segment in segment_writer.segments] == [None, None, None]
    assert [
        segment["metadata_jsonb"]["segmentation_strategy"] for segment in segment_writer.segments
    ] == ["paragraph_window", "paragraph_window", "paragraph_window"]
    assert [write[0] for write in object_store.writes] == [
        "projects/project-1/seed-runs/run-1/segments/0000.txt",
        "projects/project-1/seed-runs/run-1/segments/0001.txt",
        "projects/project-1/seed-runs/run-1/segments/0002.txt",
    ]
    assert object_store.writes[0][1].decode("utf-8") == paragraph_a
    assert object_store.writes[1][1].decode("utf-8") == paragraph_b
    assert object_store.writes[2][1].decode("utf-8") == paragraph_c
    assert "雨声压住脚步" not in str(result)
    assert "地图摊在桌面" not in str(result)
    assert "钟声响起" not in str(result)
    assert "雨声压住脚步" not in str(workflow_writer.events)
    assert "地图摊在桌面" not in str(workflow_writer.events)
    assert "钟声响起" not in str(workflow_writer.events)
    assert workflow_writer.events[-1]["payload"]["segment_count"] == 3


def test_segment_text_activity_recognizes_markdown_english_chapter_headings() -> None:
    workflow_writer = RecordingWorkflowEventWriter()
    segment_writer = RecordingTextSegmentWriter()
    source_text = "# Chapter One: Rain Night\nRain hides the messenger.\n\n## Chapter Two - Dawn\nThe map opens.\n"
    object_store = InMemoryObjectStore(
        {"projects/project-1/seed-runs/run-1/extracted/file-1.md": source_text.encode("utf-8")}
    )

    result = segment_text_activity(
        {
            "context": _context().model_dump(),
            "source_file_id": "file-1",
            "artifact_object_key": "projects/project-1/seed-runs/run-1/extracted/file-1.md",
            "artifact_type": "extracted_text",
        },
        artifact_object_store=object_store,
        text_segment_writer=segment_writer,
        workflow_event_writer=workflow_writer,
    )

    assert result["status"] == "completed"
    assert result["segment_count"] == 2
    assert [segment["chapter_guess"] for segment in segment_writer.segments] == [
        "Chapter One",
        "Chapter Two",
    ]
    assert [segment["title_guess"] for segment in segment_writer.segments] == ["Rain Night", "Dawn"]
    assert [write[0] for write in object_store.writes] == [
        "projects/project-1/seed-runs/run-1/segments/0000.txt",
        "projects/project-1/seed-runs/run-1/segments/0001.txt",
    ]
    assert object_store.writes[0][1].decode("utf-8") == "# Chapter One: Rain Night\nRain hides the messenger."
    assert "Rain hides the messenger" not in str(result)
    assert "The map opens" not in str(result)
    assert "Rain hides the messenger" not in str(workflow_writer.events)
    assert "The map opens" not in str(workflow_writer.events)
    assert workflow_writer.events[-1]["payload"]["segment_count"] == 2


def test_parse_file_activity_fails_closed_without_object_storage_backend() -> None:
    artifact_writer = RecordingTextArtifactWriter()

    result = parse_file_activity(
        {
            "context": _context().model_dump(),
            "source_file_id": "file-1",
            "source_object_key": "uploads/source-1.txt",
            "mime_type": "text/plain",
        },
        text_artifact_writer=artifact_writer,
    )

    assert result["status"] == "failed"
    assert result["error"]["code"] == "OBJECT_STORAGE_BACKEND_UNCONFIGURED"
    assert artifact_writer.artifacts == []


def test_parse_file_activity_sanitizes_untrusted_object_storage_errors_in_result() -> None:
    workflow_writer = RecordingWorkflowEventWriter()
    artifact_writer = RecordingTextArtifactWriter()

    read_result = parse_file_activity(
        {
            "context": _context().model_dump(),
            "source_file_id": "file-1",
            "source_object_key": "uploads/unsafe-source.txt",
            "mime_type": "text/plain",
        },
        source_object_store=UnsafeObjectStore(fail_on_read=True),
        artifact_object_store=InMemoryObjectStore(),
        text_artifact_writer=artifact_writer,
        workflow_event_writer=workflow_writer,
    )

    assert read_result["status"] == "failed"
    assert read_result["error"] == {
        "code": "SOURCE_FILE_OBJECT_READ_FAILED",
        "message": "source object read failed",
    }
    _assert_untrusted_object_storage_details_redacted(read_result)
    _assert_untrusted_object_storage_details_redacted(workflow_writer.events)

    workflow_writer = RecordingWorkflowEventWriter()
    artifact_writer = RecordingTextArtifactWriter()
    write_result = parse_file_activity(
        {
            "context": _context().model_dump(),
            "source_file_id": "file-1",
            "source_object_key": "uploads/source-1.txt",
            "mime_type": "text/plain",
        },
        source_object_store=InMemoryObjectStore({"uploads/source-1.txt": b"plain text"}),
        artifact_object_store=UnsafeObjectStore(fail_on_write=True),
        text_artifact_writer=artifact_writer,
        workflow_event_writer=workflow_writer,
    )

    assert write_result["status"] == "failed"
    assert write_result["error"] == {
        "code": "TEXT_ARTIFACT_WRITE_FAILED",
        "message": "text artifact write failed",
    }
    assert artifact_writer.artifacts == []
    _assert_untrusted_object_storage_details_redacted(write_result)
    _assert_untrusted_object_storage_details_redacted(workflow_writer.events)


def test_parse_file_activity_sanitizes_object_store_env_resolution_exception(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    workflow_writer = RecordingWorkflowEventWriter()
    workflow_status_writer = RecordingWorkflowRunStatusWriter()
    source_status_writer = RecordingSourceFileStatusWriter()
    artifact_writer = RecordingTextArtifactWriter()

    def fail_object_store_from_env() -> None:
        raise RuntimeError(
            "object store env failed prompt=hidden api_key=sk-hidden "
            "credential_ref=cred-hidden object_key=uploads/source.txt draft=private manuscript=private"
        )

    monkeypatch.setattr(seed_module, "_object_store_from_env", fail_object_store_from_env)

    result = parse_file_activity(
        {
            "context": _context().model_dump(),
            "source_file_id": "file-1",
            "source_object_key": "uploads/source.txt",
            "mime_type": "text/plain",
        },
        text_artifact_writer=artifact_writer,
        source_status_writer=source_status_writer,
        workflow_event_writer=workflow_writer,
        workflow_status_writer=workflow_status_writer,
    )

    assert result["status"] == "failed"
    assert result["stage"] == "parse_file"
    assert result["error"] == {
        "code": "OBJECT_STORAGE_BACKEND_MISCONFIGURED",
        "message": "object storage backend is misconfigured",
    }
    assert result["workflow_status_persisted"] is True
    assert artifact_writer.artifacts == []
    assert source_status_writer.statuses == [
        {
            "tenant_id": "tenant-1",
            "project_id": "project-1",
            "run_id": "run-1",
            "source_file_id": "file-1",
            "parse_status": "failed",
        }
    ]
    assert workflow_writer.events[-1]["event_type"] == "seed.stage.failed"
    assert workflow_writer.events[-1]["payload"]["error_code"] == "OBJECT_STORAGE_BACKEND_MISCONFIGURED"
    assert workflow_status_writer.failed == [
        {
            "tenant_id": "tenant-1",
            "project_id": "project-1",
            "run_id": "run-1",
            "code": "OBJECT_STORAGE_BACKEND_MISCONFIGURED",
            "message": "object storage backend is misconfigured",
        }
    ]
    public_body = json.dumps(
        [result, workflow_writer.events, source_status_writer.statuses, workflow_status_writer.failed],
        ensure_ascii=False,
    )
    for forbidden in (
        "object store env failed",
        "prompt",
        "api_key",
        "sk-hidden",
        "credential_ref",
        "object_key",
        "uploads/source.txt",
        "draft",
        "manuscript",
    ):
        assert forbidden not in public_body


def test_parse_file_activity_fails_closed_when_source_object_integrity_mismatches() -> None:
    workflow_writer = RecordingWorkflowEventWriter()
    artifact_writer = RecordingTextArtifactWriter()
    status_writer = RecordingSourceFileStatusWriter()
    source_text = "第一章 雨夜\n对象内容已经被替换。\n"
    object_store = InMemoryObjectStore({"uploads/source-1.txt": source_text.encode("utf-8")})

    result = parse_file_activity(
        {
            "context": _context().model_dump(),
            "source_file_id": "file-1",
            "source_object_key": "uploads/source-1.txt",
            "mime_type": "text/plain",
            "source_size_bytes": len(source_text.encode("utf-8")) + 1,
            "source_sha256": "0" * 64,
        },
        source_object_store=object_store,
        artifact_object_store=object_store,
        text_artifact_writer=artifact_writer,
        source_status_writer=status_writer,
        workflow_event_writer=workflow_writer,
    )

    assert result["status"] == "failed"
    assert result["stage"] == "parse_file"
    assert result["error"] == {
        "code": "SOURCE_FILE_OBJECT_INTEGRITY_MISMATCH",
        "message": "source object integrity check failed",
    }
    assert artifact_writer.artifacts == []
    assert object_store.writes == []
    assert status_writer.statuses == [
        {
            "tenant_id": "tenant-1",
            "project_id": "project-1",
            "run_id": "run-1",
            "source_file_id": "file-1",
            "parse_status": "failed",
        }
    ]
    assert workflow_writer.events[-1]["event_type"] == "seed.stage.failed"
    assert workflow_writer.events[-1]["payload"]["error_code"] == "SOURCE_FILE_OBJECT_INTEGRITY_MISMATCH"
    public_text = json.dumps([result, workflow_writer.events], ensure_ascii=False)
    for forbidden in [
        "uploads/source-1.txt",
        source_text,
        "对象内容已经被替换",
        "source_sha256",
        "0000000000000000000000000000000000000000000000000000000000000000",
        "actual_sha256",
        "expected_sha256",
        "object_key",
        "api_key",
        "credential_ref",
        "draft",
        "manuscript",
    ]:
        assert forbidden not in public_text


def test_parse_file_activity_marks_workflow_failed_on_terminal_parse_failure() -> None:
    workflow_writer = RecordingWorkflowEventWriter()
    artifact_writer = RecordingTextArtifactWriter()
    workflow_status_writer = RecordingWorkflowRunStatusWriter()

    result = parse_file_activity(
        {
            "context": _context().model_dump(),
            "source_file_id": "file-1",
            "source_object_key": "uploads/missing.txt",
            "mime_type": "text/plain",
        },
        source_object_store=InMemoryObjectStore({}),
        artifact_object_store=InMemoryObjectStore({}),
        text_artifact_writer=artifact_writer,
        workflow_event_writer=workflow_writer,
        workflow_status_writer=workflow_status_writer,
    )

    assert result["status"] == "failed"
    assert result["stage"] == "parse_file"
    assert result["error"] == {
        "code": "SOURCE_FILE_OBJECT_READ_FAILED",
        "message": "source object read failed",
    }
    assert result["workflow_status_persisted"] is True
    assert workflow_status_writer.failed == [
        {
            "tenant_id": "tenant-1",
            "project_id": "project-1",
            "run_id": "run-1",
            "code": "SOURCE_FILE_OBJECT_READ_FAILED",
            "message": "source object read failed",
        }
    ]
    public_body = json.dumps([result, workflow_status_writer.failed, workflow_writer.events], ensure_ascii=False)
    for forbidden in ("uploads/missing.txt", "object_key", "prompt", "api_key", "credential_ref", "draft", "manuscript"):
        assert forbidden not in public_body


def test_parse_file_activity_sanitizes_workflow_status_writer_env_resolution_exception(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def fail_from_env() -> None:
        raise RuntimeError(
            "parse status writer env failed prompt=hidden api_key=sk-hidden "
            "credential_ref=cred-hidden object_key=uploads/missing.txt draft=private manuscript=private"
        )

    monkeypatch.setattr(seed_module, "_workflow_status_writer_from_env", fail_from_env)

    result = parse_file_activity(
        {
            "context": _context().model_dump(),
            "source_file_id": "file-1",
            "source_object_key": "uploads/missing.txt",
            "mime_type": "text/plain",
        },
        source_object_store=InMemoryObjectStore({}),
        artifact_object_store=InMemoryObjectStore({}),
        text_artifact_writer=RecordingTextArtifactWriter(),
        workflow_event_writer=RecordingWorkflowEventWriter(),
    )

    assert result["status"] == "failed"
    assert result["stage"] == "parse_file"
    assert result["error"] == {
        "code": "WORKFLOW_STATUS_WRITE_FAILED",
        "message": "seed workflow status write failed",
    }
    public_body = json.dumps(result, ensure_ascii=False, sort_keys=True)
    for forbidden in (
        "status writer env failed",
        "prompt",
        "api_key",
        "sk-hidden",
        "credential_ref",
        "object_key",
        "uploads/missing.txt",
        "draft",
        "manuscript",
    ):
        assert forbidden not in public_body


def test_parse_file_activity_sanitizes_source_status_writer_env_resolution_exception(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    workflow_writer = RecordingWorkflowEventWriter()
    workflow_status_writer = RecordingWorkflowRunStatusWriter()

    def fail_source_status_from_env() -> None:
        raise RuntimeError(
            "source status writer env failed prompt=hidden api_key=sk-hidden "
            "credential_ref=cred-hidden object_key=uploads/source.txt draft=private manuscript=private"
        )

    monkeypatch.setattr(seed_module, "_source_file_status_writer_from_env", fail_source_status_from_env)

    result = parse_file_activity(
        {
            "context": _context().model_dump(),
            "source_file_id": "file-1",
            "source_object_key": "uploads/source.txt",
            "mime_type": "text/plain",
        },
        source_object_store=InMemoryObjectStore({"uploads/source.txt": b"plain text"}),
        artifact_object_store=InMemoryObjectStore(),
        text_artifact_writer=RecordingTextArtifactWriter(),
        workflow_event_writer=workflow_writer,
        workflow_status_writer=workflow_status_writer,
    )

    assert result["status"] == "failed"
    assert result["stage"] == "parse_file"
    assert result["error"] == {
        "code": "SOURCE_FILE_PARSE_STATUS_UPDATE_FAILED",
        "message": "source file parse status update failed",
    }
    assert result["stage_event_persisted"] is True
    assert result["workflow_status_persisted"] is True
    assert workflow_writer.events[-1]["event_type"] == "seed.stage.failed"
    assert workflow_writer.events[-1]["payload"]["error_code"] == "SOURCE_FILE_PARSE_STATUS_UPDATE_FAILED"
    assert workflow_status_writer.failed == [
        {
            "tenant_id": "tenant-1",
            "project_id": "project-1",
            "run_id": "run-1",
            "code": "SOURCE_FILE_PARSE_STATUS_UPDATE_FAILED",
            "message": "source file parse status update failed",
        }
    ]
    public_body = json.dumps([result, workflow_writer.events, workflow_status_writer.failed], ensure_ascii=False)
    for forbidden in (
        "source status writer env failed",
        "prompt",
        "api_key",
        "sk-hidden",
        "credential_ref",
        "object_key",
        "uploads/source.txt",
        "draft",
        "manuscript",
    ):
        assert forbidden not in public_body


def test_parse_file_activity_sanitizes_text_artifact_writer_env_resolution_exception(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    workflow_writer = RecordingWorkflowEventWriter()
    workflow_status_writer = RecordingWorkflowRunStatusWriter()
    source_status_writer = RecordingSourceFileStatusWriter()
    object_store = InMemoryObjectStore({"uploads/source.txt": b"plain text"})

    def fail_text_artifact_from_env() -> None:
        raise RuntimeError(
            "text artifact writer env failed prompt=hidden api_key=sk-hidden "
            "credential_ref=cred-hidden object_key=uploads/source.txt draft=private manuscript=private"
        )

    monkeypatch.setattr(seed_module, "_text_artifact_writer_from_env", fail_text_artifact_from_env)

    result = parse_file_activity(
        {
            "context": _context().model_dump(),
            "source_file_id": "file-1",
            "source_object_key": "uploads/source.txt",
            "mime_type": "text/plain",
        },
        source_object_store=object_store,
        artifact_object_store=object_store,
        source_status_writer=source_status_writer,
        workflow_event_writer=workflow_writer,
        workflow_status_writer=workflow_status_writer,
    )

    assert result["status"] == "failed"
    assert result["stage"] == "parse_file"
    assert result["error"] == {
        "code": "TEXT_ARTIFACT_WRITE_FAILED",
        "message": "text artifact write failed",
    }
    assert result["stage_event_persisted"] is True
    assert result["workflow_status_persisted"] is True
    assert object_store.writes == []
    assert source_status_writer.statuses == [
        {
            "tenant_id": "tenant-1",
            "project_id": "project-1",
            "run_id": "run-1",
            "source_file_id": "file-1",
            "parse_status": "failed",
        }
    ]
    assert workflow_writer.events[-1]["event_type"] == "seed.stage.failed"
    assert workflow_writer.events[-1]["payload"]["error_code"] == "TEXT_ARTIFACT_WRITE_FAILED"
    assert workflow_status_writer.failed == [
        {
            "tenant_id": "tenant-1",
            "project_id": "project-1",
            "run_id": "run-1",
            "code": "TEXT_ARTIFACT_WRITE_FAILED",
            "message": "text artifact write failed",
        }
    ]
    public_body = json.dumps(
        [result, workflow_writer.events, source_status_writer.statuses, workflow_status_writer.failed],
        ensure_ascii=False,
    )
    for forbidden in (
        "text artifact writer env failed",
        "prompt",
        "api_key",
        "sk-hidden",
        "credential_ref",
        "object_key",
        "uploads/source.txt",
        "draft",
        "manuscript",
    ):
        assert forbidden not in public_body


def test_segment_text_activity_sanitizes_untrusted_object_storage_errors_in_result() -> None:
    workflow_writer = RecordingWorkflowEventWriter()
    segment_writer = RecordingTextSegmentWriter()

    read_result = segment_text_activity(
        {
            "context": _context().model_dump(),
            "source_file_id": "file-1",
            "artifact_object_key": "projects/project-1/seed-runs/run-1/extracted/file-1.txt",
            "artifact_type": "extracted_text",
        },
        artifact_object_store=UnsafeObjectStore(fail_on_read=True),
        text_segment_writer=segment_writer,
        workflow_event_writer=workflow_writer,
    )

    assert read_result["status"] == "failed"
    assert read_result["error"] == {
        "code": "TEXT_ARTIFACT_READ_FAILED",
        "message": "text artifact read failed",
    }
    _assert_untrusted_object_storage_details_redacted(read_result)
    _assert_untrusted_object_storage_details_redacted(workflow_writer.events)

    workflow_writer = RecordingWorkflowEventWriter()
    segment_writer = RecordingTextSegmentWriter()
    write_result = segment_text_activity(
        {
            "context": _context().model_dump(),
            "source_file_id": "file-1",
            "artifact_object_key": "projects/project-1/seed-runs/run-1/extracted/file-1.txt",
            "artifact_type": "extracted_text",
        },
        artifact_object_store=UnsafeObjectStore(
            objects={
                "projects/project-1/seed-runs/run-1/extracted/file-1.txt": b"Chapter 1\nprivate text"
            },
            fail_on_write=True,
        ),
        text_segment_writer=segment_writer,
        workflow_event_writer=workflow_writer,
    )

    assert write_result["status"] == "failed"
    assert write_result["error"] == {
        "code": "TEXT_SEGMENT_WRITE_FAILED",
        "message": "text segment write failed",
    }
    assert segment_writer.segments == []
    _assert_untrusted_object_storage_details_redacted(write_result)
    _assert_untrusted_object_storage_details_redacted(workflow_writer.events)


def test_segment_text_activity_sanitizes_object_store_env_resolution_exception(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    workflow_writer = RecordingWorkflowEventWriter()
    workflow_status_writer = RecordingWorkflowRunStatusWriter()
    segment_writer = RecordingTextSegmentWriter()

    def fail_object_store_from_env() -> None:
        raise RuntimeError(
            "object store env failed prompt=hidden api_key=sk-hidden "
            "credential_ref=cred-hidden object_key=projects/project-1/seed-runs/run-1/extracted/file-1.txt "
            "draft=private manuscript=private"
        )

    monkeypatch.setattr(seed_module, "_object_store_from_env", fail_object_store_from_env)

    result = segment_text_activity(
        {
            "context": _context().model_dump(),
            "source_file_id": "file-1",
            "artifact_object_key": "projects/project-1/seed-runs/run-1/extracted/file-1.txt",
            "artifact_type": "extracted_text",
        },
        text_segment_writer=segment_writer,
        workflow_event_writer=workflow_writer,
        workflow_status_writer=workflow_status_writer,
    )

    assert result["status"] == "failed"
    assert result["stage"] == "segment_text"
    assert result["error"] == {
        "code": "OBJECT_STORAGE_BACKEND_MISCONFIGURED",
        "message": "object storage backend is misconfigured",
    }
    assert result["workflow_status_persisted"] is True
    assert segment_writer.segments == []
    assert workflow_writer.events[-1]["event_type"] == "seed.stage.failed"
    assert workflow_writer.events[-1]["payload"]["error_code"] == "OBJECT_STORAGE_BACKEND_MISCONFIGURED"
    assert workflow_status_writer.failed == [
        {
            "tenant_id": "tenant-1",
            "project_id": "project-1",
            "run_id": "run-1",
            "code": "OBJECT_STORAGE_BACKEND_MISCONFIGURED",
            "message": "object storage backend is misconfigured",
        }
    ]
    public_body = json.dumps([result, workflow_writer.events, workflow_status_writer.failed], ensure_ascii=False)
    for forbidden in (
        "object store env failed",
        "prompt",
        "api_key",
        "sk-hidden",
        "credential_ref",
        "object_key",
        "projects/project-1/seed-runs",
        "draft",
        "manuscript",
    ):
        assert forbidden not in public_body


def test_segment_text_activity_marks_workflow_failed_on_terminal_segment_failure() -> None:
    workflow_writer = RecordingWorkflowEventWriter()
    segment_writer = RecordingTextSegmentWriter()
    workflow_status_writer = RecordingWorkflowRunStatusWriter()

    result = segment_text_activity(
        {
            "context": _context().model_dump(),
            "source_file_id": "file-1",
            "artifact_object_key": "projects/project-1/seed-runs/run-1/extracted/file-1.txt",
            "artifact_type": "extracted_text",
        },
        artifact_object_store=InMemoryObjectStore({}),
        text_segment_writer=segment_writer,
        workflow_event_writer=workflow_writer,
        workflow_status_writer=workflow_status_writer,
    )

    assert result["status"] == "failed"
    assert result["error"] == {
        "code": "TEXT_ARTIFACT_READ_FAILED",
        "message": "text artifact read failed",
    }
    assert result["workflow_status_persisted"] is True
    assert workflow_status_writer.failed == [
        {
            "tenant_id": "tenant-1",
            "project_id": "project-1",
            "run_id": "run-1",
            "code": "TEXT_ARTIFACT_READ_FAILED",
            "message": "text artifact read failed",
        }
    ]
    public_body = json.dumps([result, workflow_status_writer.failed, workflow_writer.events], ensure_ascii=False)
    for forbidden in (
        "projects/project-1/seed-runs/run-1/extracted",
        "object_key",
        "prompt",
        "api_key",
        "credential_ref",
        "draft",
        "manuscript",
    ):
        assert forbidden not in public_body


def test_segment_text_activity_sanitizes_workflow_status_writer_env_resolution_exception(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def fail_from_env() -> None:
        raise RuntimeError(
            "segment status writer env failed prompt=hidden api_key=sk-hidden "
            "credential_ref=cred-hidden object_key=projects/project-1/seed-runs/run-1/extracted/file-1.txt "
            "draft=private manuscript=private"
        )

    monkeypatch.setattr(seed_module, "_workflow_status_writer_from_env", fail_from_env)

    result = segment_text_activity(
        {
            "context": _context().model_dump(),
            "source_file_id": "file-1",
            "artifact_object_key": "projects/project-1/seed-runs/run-1/extracted/file-1.txt",
            "artifact_type": "extracted_text",
        },
        artifact_object_store=InMemoryObjectStore({}),
        text_segment_writer=RecordingTextSegmentWriter(),
        workflow_event_writer=RecordingWorkflowEventWriter(),
    )

    assert result["status"] == "failed"
    assert result["stage"] == "segment_text"
    assert result["error"] == {
        "code": "WORKFLOW_STATUS_WRITE_FAILED",
        "message": "seed workflow status write failed",
    }
    public_body = json.dumps(result, ensure_ascii=False, sort_keys=True)
    for forbidden in (
        "status writer env failed",
        "prompt",
        "api_key",
        "sk-hidden",
        "credential_ref",
        "object_key",
        "projects/project-1/seed-runs",
        "draft",
        "manuscript",
    ):
        assert forbidden not in public_body


def test_segment_text_activity_sanitizes_text_segment_writer_env_resolution_exception(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    workflow_writer = RecordingWorkflowEventWriter()
    workflow_status_writer = RecordingWorkflowRunStatusWriter()

    def fail_text_segment_from_env() -> None:
        raise RuntimeError(
            "text segment writer env failed prompt=hidden api_key=sk-hidden "
            "credential_ref=cred-hidden object_key=projects/project-1/seed-runs/run-1/extracted/file-1.txt "
            "draft=private manuscript=private"
        )

    monkeypatch.setattr(seed_module, "_text_segment_writer_from_env", fail_text_segment_from_env)

    result = segment_text_activity(
        {
            "context": _context().model_dump(),
            "source_file_id": "file-1",
            "artifact_object_key": "projects/project-1/seed-runs/run-1/extracted/file-1.txt",
            "artifact_type": "extracted_text",
        },
        artifact_object_store=InMemoryObjectStore(
            {"projects/project-1/seed-runs/run-1/extracted/file-1.txt": b"Chapter 1\nprivate text"}
        ),
        workflow_event_writer=workflow_writer,
        workflow_status_writer=workflow_status_writer,
    )

    assert result["status"] == "failed"
    assert result["stage"] == "segment_text"
    assert result["error"] == {
        "code": "TEXT_SEGMENT_WRITE_FAILED",
        "message": "text segment write failed",
    }
    assert result["workflow_status_persisted"] is True
    assert workflow_writer.events[-1]["event_type"] == "seed.stage.failed"
    assert workflow_writer.events[-1]["payload"]["error_code"] == "TEXT_SEGMENT_WRITE_FAILED"
    assert workflow_status_writer.failed == [
        {
            "tenant_id": "tenant-1",
            "project_id": "project-1",
            "run_id": "run-1",
            "code": "TEXT_SEGMENT_WRITE_FAILED",
            "message": "text segment write failed",
        }
    ]
    public_body = json.dumps([result, workflow_writer.events, workflow_status_writer.failed], ensure_ascii=False)
    for forbidden in (
        "text segment writer env failed",
        "prompt",
        "api_key",
        "sk-hidden",
        "credential_ref",
        "object_key",
        "projects/project-1/seed-runs",
        "private text",
        "draft",
        "manuscript",
    ):
        assert forbidden not in public_body


def test_sequential_reading_activity_fails_closed_without_llm_reader() -> None:
    workflow_writer = RecordingWorkflowEventWriter()
    notes_writer = RecordingReadingNotesWriter()

    result = sequential_reading_activity(
        {
            "context": _context().model_dump(),
            "source_file_id": "file-1",
            "segments": [
                {
                    "segment_id": "segment-1",
                    "segment_order": 0,
                    "object_key": "projects/project-1/seed-runs/run-1/segments/0000.txt",
                    "content": "raw text must not be stored in workflow events",
                }
            ],
        },
        reading_notes_writer=notes_writer,
        workflow_event_writer=workflow_writer,
    )

    assert result["status"] == "failed"
    assert result["error"]["code"] == "LLM_READER_UNCONFIGURED"
    assert notes_writer.passes == []
    assert workflow_writer.events == [
        {
            "tenant_id": "tenant-1",
            "project_id": "project-1",
            "run_id": "run-1",
            "workflow_type": "seed_pipeline",
            "event_type": "seed.stage.failed",
            "payload": {
                "stage": "sequential_reading",
                "status": "failed",
                "activity": "sequential_reading_activity",
                "module_key": "sequential_reading",
                "segment_count": 1,
                "error_code": "LLM_READER_UNCONFIGURED",
                "error_message": "LLM reader is unconfigured",
            },
        }
    ]
    assert "raw text" not in str(workflow_writer.events)
    assert "object_key" not in workflow_writer.events[0]["payload"]


def test_sequential_reading_activity_sanitizes_workflow_event_writer_env_resolution_exception(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def fail_from_env() -> None:
        raise RuntimeError(
            "sequential event writer env failed prompt=hidden api_key=sk-hidden credential_ref=cred-hidden "
            "object_key=projects/project-1/seed-runs/run-1/segments/0000.txt draft=private manuscript=private"
        )

    monkeypatch.setattr(seed_module, "_workflow_event_writer_from_env", fail_from_env)

    result = sequential_reading_activity(
        {
            "context": _context().model_dump(),
            "source_file_id": "file-1",
            "segments": [
                {
                    "segment_id": "segment-1",
                    "segment_order": 0,
                    "object_key": "projects/project-1/seed-runs/run-1/segments/0000.txt",
                }
            ],
        },
        reading_notes_writer=RecordingReadingNotesWriter(),
    )

    assert result["status"] == "failed"
    assert result["error"] == {
        "code": "WORKFLOW_EVENT_WRITE_FAILED",
        "message": "workflow event write failed",
    }
    assert result["stage"] == "sequential_reading"
    public_body = json.dumps(result, ensure_ascii=False, sort_keys=True)
    for forbidden in (
        "sequential event writer env failed",
        "prompt",
        "api_key",
        "sk-hidden",
        "credential_ref",
        "object_key",
        "projects/project-1/seed-runs",
        "draft",
        "manuscript",
    ):
        assert forbidden not in public_body


def test_sequential_reading_activity_sanitizes_object_store_env_resolution_exception(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    workflow_writer = RecordingWorkflowEventWriter()
    workflow_status_writer = RecordingWorkflowRunStatusWriter()
    notes_writer = RecordingReadingNotesWriter()
    monkeypatch.setenv("DATABASE_URL", "postgresql://seed-runtime")

    def fail_object_store_from_env() -> None:
        raise RuntimeError(
            "sequential object store env failed prompt=hidden api_key=sk-hidden "
            "credential_ref=cred-hidden object_key=projects/project-1/seed-runs/run-1/segments/0000.txt "
            "draft=private manuscript=private"
        )

    monkeypatch.setattr(seed_module, "_object_store_from_env", fail_object_store_from_env)

    result = sequential_reading_activity(
        {
            "context": _context().model_dump(),
            "source_file_id": "file-1",
            "segments": [
                {
                    "segment_id": "segment-1",
                    "segment_order": 0,
                    "object_key": "projects/project-1/seed-runs/run-1/segments/0000.txt",
                }
            ],
        },
        reading_notes_writer=notes_writer,
        workflow_event_writer=workflow_writer,
        workflow_status_writer=workflow_status_writer,
    )

    assert result["status"] == "failed"
    assert result["stage"] == "sequential_reading"
    assert result["module_key"] == "sequential_reading"
    assert result["error"] == {
        "code": "OBJECT_STORAGE_BACKEND_MISCONFIGURED",
        "message": "object storage backend is misconfigured",
    }
    assert result["workflow_status_persisted"] is True
    assert notes_writer.passes == []
    assert workflow_writer.events[-1]["event_type"] == "seed.stage.failed"
    assert workflow_writer.events[-1]["payload"]["error_code"] == "OBJECT_STORAGE_BACKEND_MISCONFIGURED"
    assert workflow_status_writer.failed == [
        {
            "tenant_id": "tenant-1",
            "project_id": "project-1",
            "run_id": "run-1",
            "code": "OBJECT_STORAGE_BACKEND_MISCONFIGURED",
            "message": "object storage backend is misconfigured",
        }
    ]
    public_body = json.dumps([result, workflow_writer.events, workflow_status_writer.failed], ensure_ascii=False)
    for forbidden in (
        "sequential object store env failed",
        "prompt",
        "api_key",
        "sk-hidden",
        "credential_ref",
        "object_key",
        "projects/project-1/seed-runs",
        "draft",
        "manuscript",
    ):
        assert forbidden not in public_body


def test_sequential_reading_activity_uses_default_llm_reader_when_available(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    workflow_writer = RecordingWorkflowEventWriter()
    notes_writer = RecordingReadingNotesWriter()
    monkeypatch.setattr(seed_module, "_sequential_reader_from_env", lambda: SuccessfulSequentialReader())

    result = sequential_reading_activity(
        {
            "context": _context().model_dump(),
            "source_file_id": "file-1",
            "segments": [
                {
                    "segment_id": "segment-1",
                    "segment_order": 0,
                    "object_key": "projects/project-1/seed-runs/run-1/segments/0000.txt",
                }
            ],
        },
        reading_notes_writer=notes_writer,
        workflow_event_writer=workflow_writer,
    )

    assert result["status"] == "completed"
    assert result["stage"] == "sequential_reading"
    assert notes_writer.passes[0]["module_key"] == "sequential_reading"
    assert workflow_writer.events[-1]["event_type"] == "seed.stage.completed"


def test_sequential_reader_from_env_builds_db_backed_llm_facility_reader(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("DATABASE_URL", "postgresql://seed-runtime")
    monkeypatch.setenv(
        "LLM_CREDENTIAL_ENCRYPTION_KEY",
        "000102030405060708090a0b0c0d0e0f101112131415161718191a1b1c1d1e1f",
    )
    object_store = InMemoryObjectStore(
        {"projects/project-1/seed-runs/run-1/segments/0000.txt": "第一章 雨夜\n雨声压住脚步。".encode("utf-8")}
    )
    transport = RecordingHTTPTransport(
        response_body=json.dumps(
            {
                "choices": [
                    {
                        "message": {
                            "content": json.dumps(
                                {
                                    "notes": [
                                        {
                                            "segment_id": "segment-1",
                                            "summary": "雨夜开场。",
                                            "payload_jsonb": {
                                                "characters": [],
                                                "organizations": [],
                                                "relationships": [],
                                                "plot_threads": [],
                                                "world_rules": [],
                                                "events": [],
                                                "consistency_notes": [],
                                            },
                                        }
                                    ]
                                },
                                ensure_ascii=False,
                            )
                        }
                    }
                ]
            }
        ).encode("utf-8")
    )
    connections = iter(
        [
            QueryConnection(
                rows=[
                    {
                        "tenant_id": "tenant-1",
                        "project_id": "project-1",
                        "module_key": "sequential_reading",
                        "channel_id": "channel-project",
                        "model_id": "model-json",
                        "provider": "openai-compatible",
                        "base_url": "https://llm.example/v1",
                        "supports_json": True,
                        "settings_jsonb": "{}",
                    }
                ]
            ),
            QueryConnection(
                rows=[
                    {
                        "encrypted_api_key": (
                            "aes-256-gcm:v1:ABEiM0RVZneImaq7:"
                            "87utEhTfLrnKAiv0vtWdTg==:qe3dwCoCLzMECbZ5"
                        )
                    }
                ]
            ),
        ]
    )

    reader = _sequential_reader_from_env(
        segment_text_store=object_store,
        http_request=transport,
        connect=lambda: next(connections),
    )
    assert reader is not None

    result = reader.read_segments(
        context=_context(),
        module_key="sequential_reading",
        segments=[
            {
                "segment_id": "segment-1",
                "segment_order": 0,
                "object_key": "projects/project-1/seed-runs/run-1/segments/0000.txt",
                "content": "caller content must be ignored",
            }
        ],
    )

    assert result["status"] == "completed"
    assert result["model_id"] == "model-json"
    assert result["notes"][0]["summary"] == "雨夜开场。"
    request = transport.requests[0]
    assert request.headers["Authorization"] == "Bearer sk-seed-live"
    assert "雨声压住脚步" in request.data.decode("utf-8")
    assert "caller content" not in request.data.decode("utf-8")


def test_global_aggregator_from_env_builds_db_backed_llm_facility_aggregator(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("DATABASE_URL", "postgresql://seed-runtime")
    monkeypatch.setenv(
        "LLM_CREDENTIAL_ENCRYPTION_KEY",
        "000102030405060708090a0b0c0d0e0f101112131415161718191a1b1c1d1e1f",
    )
    transport = RecordingHTTPTransport(
        response_body=json.dumps(
            {
                "choices": [
                    {
                        "message": {
                            "content": json.dumps(
                                {
                                    "seed_analysis": {
                                        "overview": "雨城卷建立追踪压力。",
                                        "timeline_summary": "雨夜追踪后进入破晓。",
                                        "prompt": "private prompt must not affect public counts",
                                        "api_key": "sk-hidden-aggregate",
                                        "credential": "private credential marker",
                                        "draft": "private draft marker",
                                        "manuscript": "private manuscript marker",
                                        "raw": "private raw marker",
                                    }
                                },
                                ensure_ascii=False,
                            )
                        }
                    }
                ]
            }
        ).encode("utf-8")
    )
    connections = iter(
        [
            QueryConnection(
                rows=[
                    {
                        "tenant_id": "tenant-1",
                        "project_id": "project-1",
                        "module_key": "anchor_point_summary",
                        "channel_id": "channel-project",
                        "model_id": "model-agg",
                        "provider": "openai-compatible",
                        "base_url": "https://llm.example/v1",
                        "supports_json": True,
                        "settings_jsonb": "{}",
                    }
                ]
            ),
            QueryConnection(
                rows=[
                    {
                        "encrypted_api_key": (
                            "aes-256-gcm:v1:ABEiM0RVZneImaq7:"
                            "87utEhTfLrnKAiv0vtWdTg==:qe3dwCoCLzMECbZ5"
                        )
                    }
                ]
            ),
            AggregateInputConnection(
                segment_rows=[{"segment_id": "segment-1", "summary": "雨夜开场。"}],
                count_rows=[{"fact_type": "entities", "fact_count": 2}],
            ),
        ]
    )

    aggregator = _global_aggregator_from_env(
        http_request=transport,
        connect=lambda: next(connections),
    )
    assert aggregator is not None

    result = aggregator.aggregate(context=_context(), module_key="anchor_point_summary")

    assert result["status"] == "completed"
    assert result["model_id"] == "model-agg"
    assert result["segment_count"] == 1
    assert result["summary_count"] == 2
    assert result["seed_analysis"] == {
        "overview": "雨城卷建立追踪压力。",
        "timeline_summary": "雨夜追踪后进入破晓。",
    }
    request = transport.requests[0]
    assert request.headers["Authorization"] == "Bearer sk-seed-live"
    request_body = request.data.decode("utf-8")
    assert "雨夜开场" in request_body
    assert "raw_content" not in request_body
    assert "evidence_text" not in request_body


def test_postgres_seed_aggregate_source_counts_runtime_facts_by_source_run_id() -> None:
    connection = RecordingAggregateInputConnection(
        segment_rows=[{"segment_id": "segment-1", "summary": "雨夜公共摘要。"}],
        count_rows=[
            {"fact_type": "entities", "fact_count": 1},
            {"fact_type": "relationships", "fact_count": 1},
        ],
    )
    source = PostgresSeedAggregateSource(connect=lambda: connection)

    result = source.load_aggregate_input(context=_context())

    assert result == {
        "segment_summaries": [{"segment_id": "segment-1", "summary": "雨夜公共摘要。"}],
        "fact_counts": {"entities": 1, "relationships": 1},
    }
    count_query = connection.cursor_instance.executed[-1][0]
    assert "e.source_run_id::text = i.run_id" in count_query
    assert "r.source_run_id::text = i.run_id" in count_query
    assert "e.run_id" not in count_query
    assert "r.run_id" not in count_query


def test_postgres_seed_analysis_writer_removes_aggregate_sensitive_keys() -> None:
    connection = FakeConnection()
    writer = PostgresSeedAnalysisWriter(connect=lambda: connection)

    writer.record_seed_analysis(
        context=_context(),
        module_key="anchor_point_summary",
        model_id="model-agg",
        segment_count=2,
        summary_count=1,
        seed_analysis={
            "overview": "雨城卷建立追踪压力。",
            "nested": {
                "text": "raw private text must not be stored",
                "evidence": "private evidence marker",
                "content_text": "private content text",
                "body_text": "private body text",
                "material_text": "private material text",
                "source_material": "private source material",
                "sourceMaterial": "private camel source material",
                "excerpt": "private excerpt",
                "quote": "private quote",
                "quotes": ["private quote"],
                "evidence_quotes": ["private evidence quote"],
                "evidenceQuotes": ["private camel evidence quote"],
                "contentText": "private camel content text",
                "bodyText": "private camel body text",
                "provider_response": "raw provider response",
                "credential_ref": "secret-ref",
                "safe_note": "只保留私有分析摘要。",
            },
            "content": "raw body",
            "raw_body": "raw provider body",
            "api_key": "sk-test",
        },
    )

    assert json.loads(connection.cursor_instance.params[5]) == {
        "overview": "雨城卷建立追踪压力。",
        "nested": {"safe_note": "只保留私有分析摘要。"},
    }


def test_global_aggregation_activity_records_factory_configuration_errors(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    workflow_writer = RecordingWorkflowEventWriter()
    monkeypatch.setenv("DATABASE_URL", "postgresql://seed-runtime")
    monkeypatch.setenv("LLM_CREDENTIAL_ENCRYPTION_KEY", "not-a-valid-key")

    result = global_aggregation_activity(
        {"context": _context().model_dump()},
        workflow_event_writer=workflow_writer,
    )

    assert result["status"] == "failed"
    assert result["stage"] == "global_aggregation"
    assert result["error"]["code"] == "LLM_CREDENTIAL_KEY_INVALID"
    assert workflow_writer.events[-1]["event_type"] == "seed.stage.failed"
    assert workflow_writer.events[-1]["payload"]["error_code"] == "LLM_CREDENTIAL_KEY_INVALID"
    assert "not-a-valid-key" not in str(result)
    assert "not-a-valid-key" not in str(workflow_writer.events)


def test_sequential_reading_activity_reports_invalid_default_reader_configuration(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    workflow_writer = RecordingWorkflowEventWriter()
    notes_writer = RecordingReadingNotesWriter()
    monkeypatch.setenv("DATABASE_URL", "postgresql://seed-runtime")
    monkeypatch.setenv("LLM_CREDENTIAL_ENCRYPTION_KEY", "not-a-valid-aes-key")
    monkeypatch.setattr(
        seed_module,
        "_object_store_from_env",
        lambda: InMemoryObjectStore({"projects/project-1/seed-runs/run-1/segments/0000.txt": b"text"}),
    )
    monkeypatch.setattr(seed_module, "_workflow_status_writer_from_env", lambda: None)

    result = sequential_reading_activity(
        {
            "context": _context().model_dump(),
            "source_file_id": "file-1",
            "segments": [
                {
                    "segment_id": "segment-1",
                    "segment_order": 0,
                    "object_key": "projects/project-1/seed-runs/run-1/segments/0000.txt",
                }
            ],
        },
        reading_notes_writer=notes_writer,
        workflow_event_writer=workflow_writer,
    )

    assert result["status"] == "failed"
    assert result["error"]["code"] == "LLM_CREDENTIAL_KEY_INVALID"
    assert notes_writer.passes == []
    assert workflow_writer.events[-1]["event_type"] == "seed.stage.failed"
    assert workflow_writer.events[-1]["payload"]["error_code"] == "LLM_CREDENTIAL_KEY_INVALID"
    assert "not-a-valid" not in str(workflow_writer.events)


def test_sequential_reading_activity_propagates_missing_module_binding_without_fake_notes() -> None:
    workflow_writer = RecordingWorkflowEventWriter()
    notes_writer = RecordingReadingNotesWriter()

    result = sequential_reading_activity(
        {
            "context": _context().model_dump(),
            "source_file_id": "file-1",
            "segments": [
                {
                    "segment_id": "segment-1",
                    "segment_order": 0,
                    "object_key": "projects/project-1/seed-runs/run-1/segments/0000.txt",
                }
            ],
        },
        llm_reader=FailingSequentialReader("LLM_MODULE_UNBOUND", "sequential_reading module is not bound"),
        reading_notes_writer=notes_writer,
        workflow_event_writer=workflow_writer,
    )

    assert result["status"] == "failed"
    assert result["error"]["code"] == "LLM_MODULE_UNBOUND"
    assert notes_writer.passes == []
    assert workflow_writer.events[-1]["event_type"] == "seed.stage.failed"
    assert workflow_writer.events[-1]["payload"]["error_code"] == "LLM_MODULE_UNBOUND"
    assert "object_key" not in workflow_writer.events[-1]["payload"]


def test_sequential_reading_activity_persists_schema_validated_notes() -> None:
    workflow_writer = RecordingWorkflowEventWriter()
    notes_writer = RecordingReadingNotesWriter()

    result = sequential_reading_activity(
        {
            "context": _context().model_dump(),
            "source_file_id": "file-1",
            "segments": [
                {
                    "segment_id": "segment-1",
                    "segment_order": 0,
                    "object_key": "projects/project-1/seed-runs/run-1/segments/0000.txt",
                    "content": "raw text must not leak",
                }
            ],
        },
        llm_reader=SuccessfulSequentialReader(),
        reading_notes_writer=notes_writer,
        workflow_event_writer=workflow_writer,
    )

    assert result["status"] == "completed"
    assert result["stage"] == "sequential_reading"
    assert result["next_stage"] == "persist_runtime_facts"
    assert result["note_count"] == 1
    assert "content" not in result
    assert notes_writer.passes == [
        {
            "tenant_id": "tenant-1",
            "project_id": "project-1",
            "run_id": "run-1",
            "pass_id": "pass-1",
            "pass_type": "sequential_reading",
            "status": "completed",
            "module_key": "sequential_reading",
            "model_id": "model-a",
            "notes": [
                {
                    "segment_id": "segment-1",
                    "summary": "雨夜开场。",
                    "payload_jsonb": {
                        "characters": [
                            {
                                "name": "阿澜",
                                "aliases": [],
                                "importance": "major",
                                "state_update": "进入雨夜谈判。",
                                "evidence": "雨声压住脚步。",
                            }
                        ],
                        "organizations": [],
                        "relationships": [],
                        "plot_threads": [],
                        "world_rules": [],
                        "events": [],
                        "consistency_notes": [],
                    },
                }
            ],
            "metadata_jsonb": {"segment_count": 1},
        }
    ]
    assert workflow_writer.events[-1] == {
        "tenant_id": "tenant-1",
        "project_id": "project-1",
        "run_id": "run-1",
        "workflow_type": "seed_pipeline",
        "event_type": "seed.stage.completed",
        "payload": {
            "stage": "sequential_reading",
            "status": "completed",
            "activity": "sequential_reading_activity",
            "module_key": "sequential_reading",
            "segment_count": 1,
            "note_count": 1,
            "model_id": "model-a",
        },
    }
    assert "raw text" not in str(workflow_writer.events)
    assert "object_key" not in workflow_writer.events[-1]["payload"]


def test_sequential_reading_activity_rejects_invalid_reader_schema_without_persisting_notes() -> None:
    workflow_writer = RecordingWorkflowEventWriter()
    notes_writer = RecordingReadingNotesWriter()

    result = sequential_reading_activity(
        {
            "context": _context().model_dump(),
            "source_file_id": "file-1",
            "segments": [
                {
                    "segment_id": "segment-1",
                    "segment_order": 0,
                    "object_key": "projects/project-1/seed-runs/run-1/segments/0000.txt",
                }
            ],
        },
        llm_reader=InvalidSequentialReader(),
        reading_notes_writer=notes_writer,
        workflow_event_writer=workflow_writer,
    )

    assert result["status"] == "failed"
    assert result["error"]["code"] == "SCHEMA_VALIDATION_FAILED"
    assert notes_writer.passes == []
    assert workflow_writer.events[-1]["event_type"] == "seed.stage.failed"
    assert workflow_writer.events[-1]["payload"]["error_code"] == "SCHEMA_VALIDATION_FAILED"
    assert "object_key" not in workflow_writer.events[-1]["payload"]


def test_sequential_reading_activity_marks_workflow_failed_when_notes_writer_unconfigured() -> None:
    workflow_writer = RecordingWorkflowEventWriter()
    status_writer = RecordingWorkflowRunStatusWriter()

    result = sequential_reading_activity(
        {
            "context": _context().model_dump(),
            "source_file_id": "file-1",
            "segments": [
                {
                    "segment_id": "segment-1",
                    "segment_order": 0,
                    "object_key": "projects/project-1/seed-runs/run-1/segments/private.txt",
                    "content": "private raw segment text",
                }
            ],
        },
        workflow_event_writer=workflow_writer,
        workflow_status_writer=status_writer,
    )

    assert result["status"] == "failed"
    assert result["stage"] == "sequential_reading"
    assert result["error"]["code"] == "READING_NOTES_WRITER_UNCONFIGURED"
    assert status_writer.failed == [
        {
            "tenant_id": "tenant-1",
            "project_id": "project-1",
            "run_id": "run-1",
            "code": "READING_NOTES_WRITER_UNCONFIGURED",
            "message": "reading notes writer is unconfigured",
        }
    ]
    assert status_writer.completed == []
    public_body = json.dumps([result, workflow_writer.events, status_writer.failed], ensure_ascii=False)
    assert "projects/project-1/seed-runs/run-1/segments/private.txt" not in public_body
    assert "private raw segment text" not in public_body
    assert "api_key" not in public_body
    assert "credential_ref" not in public_body


class SuccessfulSequentialReader:
    def read_segments(
        self,
        *,
        context: AgentContext,
        module_key: str,
        segments: list[dict[str, object]],
    ) -> dict[str, object]:
        return {
            "status": "completed",
            "pass_id": "pass-1",
            "module_key": module_key,
            "model_id": "model-a",
            "notes": [
                {
                    "segment_id": "segment-1",
                    "summary": "雨夜开场。",
                    "payload_jsonb": {
                        "characters": [
                            {
                                "name": "阿澜",
                                "aliases": [],
                                "importance": "major",
                                "state_update": "进入雨夜谈判。",
                                "evidence": "雨声压住脚步。",
                            }
                        ],
                        "organizations": [],
                        "relationships": [],
                        "plot_threads": [],
                        "world_rules": [],
                        "events": [],
                        "consistency_notes": [],
                        "prompt": "must be sanitized by writer",
                    },
                }
            ],
        }


class EchoSequentialReader:
    def read_segments(
        self,
        *,
        context: AgentContext,
        module_key: str,
        segments: list[dict[str, object]],
    ) -> dict[str, object]:
        return {
            "status": "completed",
            "pass_id": "pass-1",
            "module_key": module_key,
            "model_id": "model-a",
            "notes": [
                {
                    "segment_id": segment["segment_id"],
                    "summary": f"segment {segment['segment_order']}",
                    "payload_jsonb": {
                        "characters": [],
                        "organizations": [],
                        "relationships": [],
                        "plot_threads": [],
                        "world_rules": [],
                        "events": [],
                        "consistency_notes": [],
                    },
                }
                for segment in segments
            ],
        }


class InvalidSequentialReader:
    def read_segments(
        self,
        *,
        context: AgentContext,
        module_key: str,
        segments: list[dict[str, object]],
    ) -> dict[str, object]:
        return {
            "status": "completed",
            "pass_id": "pass-1",
            "module_key": module_key,
            "model_id": "model-a",
            "notes": [{"segment_id": "segment-1", "payload_jsonb": {"characters": "not-a-list"}}],
        }


class FailingSequentialReader:
    def __init__(self, code: str, message: str) -> None:
        self.code = code
        self.message = message

    def read_segments(
        self,
        *,
        context: AgentContext,
        module_key: str,
        segments: list[dict[str, object]],
    ) -> dict[str, object]:
        return {
            "status": "failed",
            "error": {"code": self.code, "message": self.message},
            "module_key": module_key,
        }


def test_parse_file_activity_records_sanitized_failed_stage_event() -> None:
    workflow_writer = RecordingWorkflowEventWriter()
    artifact_writer = RecordingTextArtifactWriter()
    object_store = InMemoryObjectStore({})

    result = parse_file_activity(
        {
            "context": _context().model_dump(),
            "source_file_id": "file-1",
            "source_object_key": "uploads/private-source.txt",
            "mime_type": "text/plain",
        },
        source_object_store=object_store,
        artifact_object_store=object_store,
        text_artifact_writer=artifact_writer,
        workflow_event_writer=workflow_writer,
    )

    assert result["status"] == "failed"
    assert result["error"]["code"] == "SOURCE_FILE_OBJECT_READ_FAILED"
    assert artifact_writer.artifacts == []
    assert workflow_writer.events == [
        {
            "tenant_id": "tenant-1",
            "project_id": "project-1",
            "run_id": "run-1",
            "workflow_type": "seed_pipeline",
            "event_type": "seed.stage.failed",
            "payload": {
                "stage": "parse_file",
                "status": "failed",
                "activity": "parse_file_activity",
                "source_file_id": "file-1",
                "error_code": "SOURCE_FILE_OBJECT_READ_FAILED",
                "error_message": "source object read failed",
            },
        }
    ]
    assert "source_object_key" not in workflow_writer.events[0]["payload"]
    assert "private-source" not in workflow_writer.events[0]["payload"]["error_message"]


def test_postgres_text_artifact_writer_requires_project_context() -> None:
    writer = PostgresTextArtifactWriter(connect=FakeConnection)
    context = _context().model_copy(update={"project_id": None})

    with pytest.raises(ValueError, match="project_id is required"):
        writer.record_text_artifact(
            context=context,
            source_file_id="file-1",
            artifact_type="extracted_text",
            object_key="artifacts/run-1/extracted.txt",
            char_count=128,
            line_count=8,
            sha256="sha256:test",
        )


def test_postgres_text_artifact_writer_upserts_sanitized_artifact_reference() -> None:
    connection = FakeConnection()
    writer = PostgresTextArtifactWriter(connect=lambda: connection)

    writer.record_text_artifact(
        context=_context(),
        source_file_id="file-1",
        artifact_type="extracted_text",
        object_key="artifacts/run-1/extracted.txt",
        char_count=128,
        line_count=8,
        sha256="sha256:test",
        metadata_jsonb={
            "prompt": "must not be stored",
            "raw_content": "full novel text must not be stored in db metadata",
            "api_key": "sk-test",
        },
    )

    assert connection.cursor_instance.executed[0] == (
        "SELECT app_set_tenant_context(%s::uuid, %s::uuid, false)",
        ("tenant-1", "project-1"),
    )
    assert "INSERT INTO project_text_artifacts" in connection.cursor_instance.query
    assert (
        "ON CONFLICT (tenant_id, project_id, run_id, artifact_type, object_key)"
        in connection.cursor_instance.query
    )
    assert connection.cursor_instance.params == (
        "tenant-1",
        "project-1",
        "run-1",
        "file-1",
        "extracted_text",
        "artifacts/run-1/extracted.txt",
        128,
        8,
        "sha256:test",
    )
    assert connection.committed is True
    assert connection.closed is True


def test_postgres_source_file_status_writer_updates_parse_status_with_tenant_context() -> None:
    connection = FakeConnection()
    writer = PostgresSourceFileStatusWriter(connect=lambda: connection)

    writer.mark_source_file_status(
        context=_context(),
        source_file_id="file-1",
        parse_status="parsed",
    )

    assert connection.cursor_instance.executed[0] == (
        "SELECT app_set_tenant_context(%s::uuid, %s::uuid, false)",
        ("tenant-1", "project-1"),
    )
    assert "UPDATE source_files" in connection.cursor_instance.query
    assert "parse_status = %s" in connection.cursor_instance.query
    assert "WHERE tenant_id = %s" in connection.cursor_instance.query
    assert "AND project_id = %s" in connection.cursor_instance.query
    assert "AND file_id = %s" in connection.cursor_instance.query
    assert "AND parse_status = %s" in connection.cursor_instance.query
    assert "object_key" not in connection.cursor_instance.query
    assert "content_text" not in connection.cursor_instance.query
    assert connection.cursor_instance.params == (
        "parsed",
        "tenant-1",
        "project-1",
        "file-1",
        "parsing",
    )
    assert connection.committed is True
    assert connection.closed is True


def test_postgres_source_file_status_writer_rolls_back_and_sanitizes_db_errors() -> None:
    connection = FailingConnection(fail_on_execute=2)
    writer = PostgresSourceFileStatusWriter(connect=lambda: connection)

    with pytest.raises(LLMFacilityError) as exc_info:
        writer.mark_source_file_status(
            context=_context(),
            source_file_id="file-1",
            parse_status="parsed",
        )

    assert exc_info.value.code == "SOURCE_FILE_PARSE_STATUS_UPDATE_FAILED"
    assert exc_info.value.message == "source file parse status update failed"
    assert connection.rolled_back is True
    assert connection.committed is False
    assert connection.closed is True
    for forbidden in ("prompt", "api_key", "credential_ref", "object_key", "raw_text", "draft", "manuscript"):
        assert forbidden not in exc_info.value.message


def test_postgres_seed_workflow_status_writer_marks_failed_with_tenant_context_and_public_error() -> None:
    connection = FakeWorkflowStatusConnection([{"workflow_updated": "1"}])
    writer = seed_module.PostgresSeedWorkflowRunStatusWriter(connect=lambda: connection)

    writer.mark_failed(
        context=_context(),
        code="READING_NOTES_WRITER_UNCONFIGURED",
        message="reading notes writer is unconfigured",
    )

    assert connection.cursor_instance.executed[0] == (
        "SELECT app_set_tenant_context(%s::uuid, %s::uuid, false)",
        ("tenant-1", "project-1"),
    )
    query, params = connection.cursor_instance.executed[1]
    assert "UPDATE workflow_runs" in query
    assert "workflow_type = 'seed_pipeline'" in query
    assert params[:4] == (
        "failed",
        "failed",
        "reading notes writer is unconfigured",
        None,
    )
    assert params[5:] == (
        "READING_NOTES_WRITER_UNCONFIGURED",
        "reading notes writer is unconfigured",
        "tenant-1",
        "project-1",
        "run-1",
    )
    encoded = json.dumps(connection.cursor_instance.executed, ensure_ascii=False, default=str)
    for forbidden in ("prompt", "api_key", "credential_ref", "object_key", "raw_text", "draft", "manuscript"):
        assert forbidden not in encoded
    assert connection.committed is True
    assert connection.closed is True


def test_postgres_seed_workflow_status_writer_marks_running_with_tenant_context() -> None:
    connection = FakeWorkflowStatusConnection([{"workflow_updated": "1"}])
    writer = seed_module.PostgresSeedWorkflowRunStatusWriter(connect=lambda: connection)

    writer.mark_running(context=_context())

    assert connection.cursor_instance.executed[0] == (
        "SELECT app_set_tenant_context(%s::uuid, %s::uuid, false)",
        ("tenant-1", "project-1"),
    )
    query, params = connection.cursor_instance.executed[1]
    assert "UPDATE workflow_runs" in query
    assert "workflow_type = 'seed_pipeline'" in query
    assert params[:7] == (
        "running",
        "running",
        "seed pipeline running",
        None,
        None,
        None,
        None,
    )
    assert params[7:] == ("tenant-1", "project-1", "run-1")
    assert connection.committed is True
    assert connection.closed is True


def test_postgres_seed_analysis_writer_upserts_sanitized_private_snapshot() -> None:
    connection = FakeConnection()
    writer = PostgresSeedAnalysisWriter(connect=lambda: connection)

    snapshot_id = writer.record_seed_analysis(
        context=_context(),
        module_key="anchor_point_summary",
        model_id="model-agg",
        segment_count=2,
        summary_count=1,
        seed_analysis={
            "overview": "雨城卷建立追踪压力。",
            "prompt": "must not be stored",
            "raw_content": "full novel text must not be stored",
            "api_key": "sk-test",
        },
    )

    assert snapshot_id == "snapshot-1"
    assert connection.cursor_instance.executed[0] == (
        "SELECT app_set_tenant_context(%s::uuid, %s::uuid, false)",
        ("tenant-1", "project-1"),
    )
    assert "INSERT INTO seed_analysis_snapshots" in connection.cursor_instance.query
    assert (
        "ON CONFLICT (tenant_id, project_id, run_id, module_key)"
        in connection.cursor_instance.query
    )
    assert connection.cursor_instance.params[:5] == (
        "tenant-1",
        "project-1",
        "run-1",
        "anchor_point_summary",
        "model-agg",
    )
    assert json.loads(connection.cursor_instance.params[5]) == {"overview": "雨城卷建立追踪压力。"}
    assert connection.cursor_instance.params[6:] == (1, 2)
    assert connection.committed is True
    assert connection.closed is True


def test_postgres_seed_analysis_writer_rolls_back_on_database_failure() -> None:
    execute_failure = FailingConnection(fail_on_execute=2)
    writer = PostgresSeedAnalysisWriter(connect=lambda: execute_failure)

    with pytest.raises(RuntimeError, match="driver failure"):
        writer.record_seed_analysis(
            context=_context(),
            module_key="anchor_point_summary",
            model_id="model-agg",
            segment_count=2,
            summary_count=1,
            seed_analysis={"overview": "雨城卷建立追踪压力。"},
        )

    assert execute_failure.rolled_back is True
    assert execute_failure.committed is False
    assert execute_failure.closed is True

    commit_failure = FailingConnection(fail_on_commit=True)
    commit_writer = PostgresSeedAnalysisWriter(connect=lambda: commit_failure)

    with pytest.raises(RuntimeError, match="commit failure"):
        commit_writer.record_seed_analysis(
            context=_context(),
            module_key="anchor_point_summary",
            model_id="model-agg",
            segment_count=2,
            summary_count=1,
            seed_analysis={"overview": "雨城卷建立追踪压力。"},
        )

    assert commit_failure.rolled_back is True
    assert commit_failure.committed is False
    assert commit_failure.closed is True


def test_postgres_ontology_snapshot_writer_upserts_sanitized_private_snapshot() -> None:
    connection = FakeOntologySnapshotConnection([{"seed_ontology_snapshot_id": "ontology-snapshot-1"}])
    writer = seed_module.PostgresOntologySnapshotWriter(connect=lambda: connection)

    snapshot_id = writer.record_ontology_snapshot(
        context=_context(),
        module_key="story_ontology",
        model_id="model-ontology",
        seed_ontology={
            "entity_types": [{"name": "character"}],
            "relationship_types": [{"name": "ally"}],
            "world_rule_types": [{"name": "political_rule"}],
            "private_notes": "private ontology body is allowed only in seed_ontology_snapshots",
            "prompt": "must not be stored",
            "raw_content": "full novel text must not be stored",
            "raw_body": "raw provider body must not be stored",
            "provider_raw_body": "provider body must not be stored",
            "provider_response": {"text": "provider response must not be stored"},
            "credential_ref": "secret-ref",
            "api_key": "sk-test",
        },
        entity_type_count=1,
        relationship_type_count=1,
        world_rule_type_count=1,
    )

    assert snapshot_id == "ontology-snapshot-1"
    assert connection.cursor_instance.executed[0] == (
        "SELECT app_set_tenant_context(%s::uuid, %s::uuid, false)",
        ("tenant-1", "project-1"),
    )
    assert "INSERT INTO seed_ontology_snapshots" in connection.cursor_instance.query
    assert (
        "ON CONFLICT (tenant_id, project_id, run_id, module_key)"
        in connection.cursor_instance.query
    )
    assert connection.cursor_instance.params[:5] == (
        "tenant-1",
        "project-1",
        "run-1",
        "story_ontology",
        "model-ontology",
    )
    assert json.loads(connection.cursor_instance.params[5]) == {
        "entity_types": [{"name": "character"}],
        "relationship_types": [{"name": "ally"}],
        "world_rule_types": [{"name": "political_rule"}],
        "private_notes": "private ontology body is allowed only in seed_ontology_snapshots",
    }
    assert connection.cursor_instance.params[6:] == (1, 1, 1)
    joined_params = json.dumps(connection.cursor_instance.executed, ensure_ascii=False, default=str)
    for forbidden in (
        "must not be stored",
        "full novel text",
        "raw provider body",
        "provider body",
        "provider response",
        "credential_ref",
        "api_key",
        "sk-test",
    ):
        assert forbidden not in joined_params
    assert connection.committed is True
    assert connection.closed is True


def test_ontology_runner_from_env_builds_db_backed_llm_facility_runner(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("DATABASE_URL", "postgresql://seed-runtime")
    monkeypatch.setenv(
        "LLM_CREDENTIAL_ENCRYPTION_KEY",
        "000102030405060708090a0b0c0d0e0f101112131415161718191a1b1c1d1e1f",
    )
    transport = RecordingHTTPTransport(
        response_body=json.dumps(
            {
                "choices": [
                    {
                        "message": {
                            "content": json.dumps(
                                {
                                    "seed_ontology": {
                                        "entity_types": [{"name": "character"}],
                                        "relationship_types": [{"name": "ally"}],
                                        "world_rule_types": [{"name": "political_rule"}],
                                    }
                                },
                                ensure_ascii=False,
                            )
                        }
                    }
                ]
            }
        ).encode("utf-8")
    )
    connections = iter(
        [
            QueryConnection(
                rows=[
                    {
                        "tenant_id": "tenant-1",
                        "project_id": "project-1",
                        "module_key": "story_ontology",
                        "channel_id": "channel-project",
                        "model_id": "model-ontology",
                        "provider": "openai-compatible",
                        "base_url": "https://llm.example/v1",
                        "supports_json": True,
                        "settings_jsonb": "{}",
                    }
                ]
            ),
            QueryConnection(
                rows=[
                    {
                        "encrypted_api_key": (
                            "aes-256-gcm:v1:ABEiM0RVZneImaq7:"
                            "87utEhTfLrnKAiv0vtWdTg==:qe3dwCoCLzMECbZ5"
                        )
                    }
                ]
            ),
            FakeOntologySnapshotConnection([{"seed_ontology_snapshot_id": "ontology-snapshot-1"}]),
        ]
    )

    runner = seed_module._ontology_runner_from_env(
        http_request=transport,
        connect=lambda: next(connections),
    )
    assert runner is not None

    result = runner.generate(context=_context(), module_key="story_ontology")

    assert result == {
        "status": "completed",
        "module_key": "story_ontology",
        "model_id": "model-ontology",
        "ontology_snapshot_id": "ontology-snapshot-1",
        "entity_type_count": 1,
        "relationship_type_count": 1,
        "world_rule_type_count": 1,
    }
    request = transport.requests[0]
    assert request.headers["Authorization"] == "Bearer sk-seed-live"
    request_body = request.data.decode("utf-8")
    assert "story_ontology" in request_body
    assert "credential_ref" not in request_body
    assert "api_key" not in request_body


def test_postgres_entity_resolution_snapshot_writer_upserts_sanitized_private_snapshot() -> None:
    connection = FakeOntologySnapshotConnection([{"seed_entity_resolution_snapshot_id": "resolution-snapshot-1"}])
    writer = seed_module.PostgresEntityResolutionSnapshotWriter(connect=lambda: connection)

    snapshot_id = writer.record_entity_resolution_snapshot(
        context=_context(),
        module_key="entity_resolution",
        model_id="model-resolution",
        entity_resolution={
            "merged_entities": [{"canonical_name": "林舟"}],
            "aliases": [{"alias": "小舟", "canonical_name": "林舟"}],
            "conflicts": [{"summary": "称呼冲突"}],
            "private_notes": "private resolution body is allowed only in seed_entity_resolution_snapshots",
            "prompt": "must not be stored",
            "raw_content": "full novel text must not be stored",
            "credential_ref": "secret-ref",
            "api_key": "sk-test",
        },
        merged_entity_count=1,
        alias_count=1,
        conflict_count=1,
    )

    assert snapshot_id == "resolution-snapshot-1"
    assert connection.cursor_instance.executed[0] == (
        "SELECT app_set_tenant_context(%s::uuid, %s::uuid, false)",
        ("tenant-1", "project-1"),
    )
    assert "INSERT INTO seed_entity_resolution_snapshots" in connection.cursor_instance.query
    assert (
        "ON CONFLICT (tenant_id, project_id, run_id, module_key)"
        in connection.cursor_instance.query
    )
    assert connection.cursor_instance.params[:5] == (
        "tenant-1",
        "project-1",
        "run-1",
        "entity_resolution",
        "model-resolution",
    )
    assert json.loads(connection.cursor_instance.params[5]) == {
        "merged_entities": [{"canonical_name": "林舟"}],
        "aliases": [{"alias": "小舟", "canonical_name": "林舟"}],
        "conflicts": [{"summary": "称呼冲突"}],
        "private_notes": "private resolution body is allowed only in seed_entity_resolution_snapshots",
    }
    assert connection.cursor_instance.params[6:] == (1, 1, 1)
    joined_params = json.dumps(connection.cursor_instance.executed, ensure_ascii=False, default=str)
    for forbidden in ("must not be stored", "full novel text", "credential_ref", "api_key", "sk-test"):
        assert forbidden not in joined_params
    assert connection.committed is True
    assert connection.closed is True


def test_entity_resolution_runner_from_env_builds_db_backed_llm_facility_runner(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("DATABASE_URL", "postgresql://seed-runtime")
    monkeypatch.setenv(
        "LLM_CREDENTIAL_ENCRYPTION_KEY",
        "000102030405060708090a0b0c0d0e0f101112131415161718191a1b1c1d1e1f",
    )
    transport = RecordingHTTPTransport(
        response_body=json.dumps(
            {
                "choices": [
                    {
                        "message": {
                            "content": json.dumps(
                                {
                                    "entity_resolution": {
                                        "merged_entities": [{"canonical_name": "林舟"}],
                                        "aliases": [{"alias": "小舟", "canonical_name": "林舟"}],
                                        "conflicts": [],
                                    }
                                },
                                ensure_ascii=False,
                            )
                        }
                    }
                ]
            }
        ).encode("utf-8")
    )
    connections = iter(
        [
            QueryConnection(
                rows=[
                    {
                        "tenant_id": "tenant-1",
                        "project_id": "project-1",
                        "module_key": "entity_resolution",
                        "channel_id": "channel-project",
                        "model_id": "model-resolution",
                        "provider": "openai-compatible",
                        "base_url": "https://llm.example/v1",
                        "supports_json": True,
                        "settings_jsonb": "{}",
                    }
                ]
            ),
            QueryConnection(
                rows=[
                    {
                        "encrypted_api_key": (
                            "aes-256-gcm:v1:ABEiM0RVZneImaq7:"
                            "87utEhTfLrnKAiv0vtWdTg==:qe3dwCoCLzMECbZ5"
                        )
                    }
                ]
            ),
            FakeOntologySnapshotConnection([{"seed_entity_resolution_snapshot_id": "resolution-snapshot-1"}]),
        ]
    )

    runner = seed_module._entity_resolution_runner_from_env(
        http_request=transport,
        connect=lambda: next(connections),
    )
    assert runner is not None

    result = runner.resolve(context=_context(), module_key="entity_resolution")

    assert result == {
        "status": "completed",
        "module_key": "entity_resolution",
        "model_id": "model-resolution",
        "resolution_snapshot_id": "resolution-snapshot-1",
        "merged_entity_count": 1,
        "alias_count": 1,
        "conflict_count": 0,
    }
    request = transport.requests[0]
    assert request.headers["Authorization"] == "Bearer sk-seed-live"
    request_body = request.data.decode("utf-8")
    assert "entity_resolution" in request_body
    assert "credential_ref" not in request_body
    assert "api_key" not in request_body


def test_postgres_agent_profile_snapshot_writer_upserts_sanitized_private_snapshot() -> None:
    connection = FakeOntologySnapshotConnection([{"seed_agent_profile_snapshot_id": "profile-snapshot-1"}])
    writer = seed_module.PostgresAgentProfileSnapshotWriter(connect=lambda: connection)

    snapshot_id = writer.record_agent_profile_snapshot(
        context=_context(),
        module_key="character_agent_profile",
        model_id="model-profile",
        agent_profiles={
            "profiles": [{"name": "林舟", "private_profile": {"body": "可私有保存的人设正文"}}],
            "memory_seeds": [{"name": "林舟", "summary": "雨夜记忆"}],
            "relationship_views": [{"source": "林舟", "target": "陆晚"}],
            "private_notes": "private profile body is allowed only in seed_agent_profile_snapshots",
            "prompt": "must not be stored",
            "raw_content": "full novel text must not be stored",
            "raw_body": "raw provider body must not be stored",
            "provider_raw_body": "provider body must not be stored",
            "provider_response": {"text": "provider response must not be stored"},
            "credential_ref": "secret-ref",
            "api_key": "sk-test",
        },
        profile_count=1,
        memory_seed_count=1,
        relationship_view_count=1,
    )

    assert snapshot_id == "profile-snapshot-1"
    assert connection.cursor_instance.executed[0] == (
        "SELECT app_set_tenant_context(%s::uuid, %s::uuid, false)",
        ("tenant-1", "project-1"),
    )
    assert "INSERT INTO seed_agent_profile_snapshots" in connection.cursor_instance.query
    assert (
        "ON CONFLICT (tenant_id, project_id, run_id, module_key)"
        in connection.cursor_instance.query
    )
    assert connection.cursor_instance.params[:5] == (
        "tenant-1",
        "project-1",
        "run-1",
        "character_agent_profile",
        "model-profile",
    )
    assert json.loads(connection.cursor_instance.params[5]) == {
        "profiles": [{"name": "林舟", "private_profile": {"body": "可私有保存的人设正文"}}],
        "memory_seeds": [{"name": "林舟", "summary": "雨夜记忆"}],
        "relationship_views": [{"source": "林舟", "target": "陆晚"}],
        "private_notes": "private profile body is allowed only in seed_agent_profile_snapshots",
    }
    assert connection.cursor_instance.params[6:] == (1, 1, 1)
    joined_params = json.dumps(connection.cursor_instance.executed, ensure_ascii=False, default=str)
    for forbidden in (
        "must not be stored",
        "full novel text",
        "raw provider body",
        "provider body",
        "provider response",
        "credential_ref",
        "api_key",
        "sk-test",
    ):
        assert forbidden not in joined_params
    assert connection.committed is True
    assert connection.closed is True


def test_llm_facility_agent_profile_runner_loads_context_before_binding_credentials_and_provider() -> None:
    call_order: list[str] = []

    class OrderedContextLoader(RecordingAgentProfileContextLoader):
        def load_context(self, *, context: AgentContext) -> dict[str, object]:
            call_order.append("context_loader")
            return super().load_context(context=context)

    class OrderedBindingResolver(RecordingBindingResolver):
        def resolve_module_binding(self, *, context: AgentContext, module_key: str) -> ModuleBindingResolution:
            call_order.append("binding")
            return super().resolve_module_binding(context=context, module_key=module_key)

    class OrderedCredentialProvider(RecordingCredentialProvider):
        def resolve_api_key(self, *, context: AgentContext, credential_ref: str) -> str:
            call_order.append("credential")
            return super().resolve_api_key(context=context, credential_ref=credential_ref)

    class OrderedChatClient(RecordingJSONChatClient):
        def complete_json(
            self,
            *,
            context: AgentContext,
            resolution: ModuleBindingResolution,
            api_key: str,
            messages: list[dict[str, str]],
        ) -> dict[str, object]:
            call_order.append("provider")
            return super().complete_json(
                context=context,
                resolution=resolution,
                api_key=api_key,
                messages=messages,
            )

    loader = OrderedContextLoader()
    runner = seed_module.LLMFacilityAgentProfileRunner(
        binding_resolver=OrderedBindingResolver(_agent_profile_resolution()),
        credential_provider=OrderedCredentialProvider(api_key="sk-profile"),
        chat_client=OrderedChatClient(
            response_json={
                "agent_profiles": {
                    "profiles": [],
                    "memory_seeds": [],
                    "relationship_views": [],
                }
            }
        ),
        agent_profile_snapshot_writer=RecordingAgentProfileSnapshotWriter(),
        agent_profile_context_loader=loader,
    )

    result = runner.generate(context=_context(), module_key="character_agent_profile")

    assert result["status"] == "completed"
    assert loader.calls == [{"tenant_id": "tenant-1", "project_id": "project-1", "run_id": "run-1"}]
    assert call_order == ["context_loader", "binding", "credential", "provider"]


def test_llm_facility_agent_profile_runner_rejects_resolution_without_provider_before_credential_call() -> None:
    resolution = _agent_profile_resolution()
    credentials = RecordingCredentialProvider(api_key="sk-profile")
    chat_client = RecordingJSONChatClient(
        response_json={
            "agent_profiles": {
                "profiles": [],
                "memory_seeds": [],
                "relationship_views": [],
            }
        }
    )
    runner = seed_module.LLMFacilityAgentProfileRunner(
        binding_resolver=RecordingBindingResolver(
            ModuleBindingResolution(
                tenant_id=resolution.tenant_id,
                project_id=resolution.project_id,
                module_key=resolution.module_key,
                channel_id=resolution.channel_id,
                model_id=resolution.model_id,
                provider="",
                base_url=resolution.base_url,
                credential_ref=resolution.credential_ref,
                supports_json=resolution.supports_json,
                settings=resolution.settings,
            )
        ),
        credential_provider=credentials,
        chat_client=chat_client,
        agent_profile_snapshot_writer=RecordingAgentProfileSnapshotWriter(),
        agent_profile_context_loader=RecordingAgentProfileContextLoader(),
    )

    result = runner.generate(context=_context(), module_key="character_agent_profile")

    assert result == {
        "status": "failed",
        "module_key": "character_agent_profile",
        "error": {
            "code": "LLM_PROVIDER_ERROR",
            "message": "resolved LLM module is missing provider",
        },
    }
    assert credentials.calls == []
    assert chat_client.calls == []


def test_llm_facility_agent_profile_runner_includes_sanitized_context_in_provider_request() -> None:
    loader = RecordingAgentProfileContextLoader(
        {
            "entity_resolution": {
                "merged_entities": [{"canonical_name": "林舟", "aliases": ["小舟"]}],
                "prompt": "must not reach provider",
                "private_notes": "private note must not reach provider",
                "body": "private body must not reach provider",
                "provider": "provider-name",
                "base_url": "https://provider.example",
                "channel_id": "channel-secret",
                "rawText": "camel raw text",
                "credential_ref": "secret-ref",
            },
            "canon": {
                "entities": [
                    {
                        "entity_id": "entity-1",
                        "canonical_name": "林舟",
                        "state_summary": "守住雨港秘密。",
                        "source_object_key": "private/source.txt",
                    }
                ],
                "relationships": [
                    {
                        "source_entity_name": "林舟",
                        "target_entity_name": "陆晚",
                        "summary": "互相试探。",
                        "evidence_text": "raw manuscript sentence",
                    }
                ],
                "segment_summaries": [
                    {
                        "segment_id": "segment-1",
                        "summary": "雨夜相遇。",
                        "raw_text": "full chapter",
                    }
                ],
            },
        }
    )
    chat_client = RecordingJSONChatClient(
        response_json={
            "agent_profiles": {
                "profiles": [{"name": "林舟", "voice": "冷静"}],
                "memory_seeds": [],
                "relationship_views": [],
            }
        }
    )
    runner = seed_module.LLMFacilityAgentProfileRunner(
        binding_resolver=RecordingBindingResolver(_agent_profile_resolution()),
        credential_provider=RecordingCredentialProvider(api_key="sk-profile"),
        chat_client=chat_client,
        agent_profile_snapshot_writer=RecordingAgentProfileSnapshotWriter(),
        agent_profile_context_loader=loader,
    )

    result = runner.generate(context=_context(), module_key="character_agent_profile")

    assert result["status"] == "completed"
    user_message = json.loads(chat_client.calls[0]["messages"][1]["content"])
    assert user_message["source_context"]["entity_resolution"]["merged_entities"] == [
        {"canonical_name": "林舟", "aliases": ["小舟"]}
    ]
    assert user_message["source_context"]["canon"]["entities"] == [
        {
            "entity_id": "entity-1",
            "canonical_name": "林舟",
            "state_summary": "守住雨港秘密。",
        }
    ]
    assert user_message["source_context"]["canon"]["relationships"] == [
        {
            "source_entity_name": "林舟",
            "target_entity_name": "陆晚",
            "summary": "互相试探。",
        }
    ]
    request_body = json.dumps(chat_client.calls[0]["messages"], ensure_ascii=False)
    for forbidden in (
        "must not reach provider",
        "private note must not reach provider",
        "private body must not reach provider",
        "provider-name",
        "provider.example",
        "channel-secret",
        "rawText",
        "camel raw text",
        "credential_ref",
        "secret-ref",
        "source_object_key",
        "private/source.txt",
        "evidence_text",
        "raw manuscript sentence",
        "raw_text",
        "full chapter",
        "api_key",
    ):
        assert forbidden not in request_body


def test_llm_facility_agent_profile_runner_fails_closed_when_context_is_empty_before_provider() -> None:
    loader = RecordingAgentProfileContextLoader({})
    resolver = RecordingBindingResolver(_agent_profile_resolution())
    credentials = RecordingCredentialProvider(api_key="sk-profile")
    chat_client = RecordingJSONChatClient(response_json={})
    runner = seed_module.LLMFacilityAgentProfileRunner(
        binding_resolver=resolver,
        credential_provider=credentials,
        chat_client=chat_client,
        agent_profile_snapshot_writer=RecordingAgentProfileSnapshotWriter(),
        agent_profile_context_loader=loader,
    )

    result = runner.generate(context=_context(), module_key="character_agent_profile")

    assert result == {
        "status": "failed",
        "module_key": "character_agent_profile",
        "error": {
            "code": "AGENT_PROFILE_CONTEXT_UNAVAILABLE",
            "message": "agent profile source context is unavailable",
        },
    }
    assert resolver.calls == []
    assert credentials.calls == []
    assert chat_client.calls == []


def test_llm_facility_agent_profile_runner_fails_closed_without_context_loader_before_provider() -> None:
    resolver = RecordingBindingResolver(_agent_profile_resolution())
    credentials = RecordingCredentialProvider(api_key="sk-profile")
    chat_client = RecordingJSONChatClient(response_json={})
    runner = seed_module.LLMFacilityAgentProfileRunner(
        binding_resolver=resolver,
        credential_provider=credentials,
        chat_client=chat_client,
        agent_profile_snapshot_writer=RecordingAgentProfileSnapshotWriter(),
        agent_profile_context_loader=None,
    )

    result = runner.generate(context=_context(), module_key="character_agent_profile")

    assert result == {
        "status": "failed",
        "module_key": "character_agent_profile",
        "error": {
            "code": "AGENT_PROFILE_CONTEXT_UNAVAILABLE",
            "message": "agent profile source context is unavailable",
        },
    }
    assert resolver.calls == []
    assert credentials.calls == []
    assert chat_client.calls == []


def test_llm_facility_agent_profile_runner_fails_closed_on_metadata_only_context_before_provider() -> None:
    loader = RecordingAgentProfileContextLoader(
        {
            "entity_resolution": {
                "snapshot_id": "resolution-snapshot-1",
                "model_id": "model-resolution",
                "merged_entity_count": 1,
                "alias_count": 0,
                "conflict_count": 0,
            }
        }
    )
    resolver = RecordingBindingResolver(_agent_profile_resolution())
    credentials = RecordingCredentialProvider(api_key="sk-profile")
    chat_client = RecordingJSONChatClient(response_json={})
    runner = seed_module.LLMFacilityAgentProfileRunner(
        binding_resolver=resolver,
        credential_provider=credentials,
        chat_client=chat_client,
        agent_profile_snapshot_writer=RecordingAgentProfileSnapshotWriter(),
        agent_profile_context_loader=loader,
    )

    result = runner.generate(context=_context(), module_key="character_agent_profile")

    assert result == {
        "status": "failed",
        "module_key": "character_agent_profile",
        "error": {
            "code": "AGENT_PROFILE_CONTEXT_UNAVAILABLE",
            "message": "agent profile source context is unavailable",
        },
    }
    assert resolver.calls == []
    assert credentials.calls == []
    assert chat_client.calls == []


def test_llm_facility_agent_profile_runner_fails_closed_on_metadata_only_context_lists_before_provider() -> None:
    loader = RecordingAgentProfileContextLoader(
        {
            "entity_resolution": {
                "merged_entities": [{"entity_id": "entity-1", "entity_type": "character"}],
                "aliases": [{"entity_id": "entity-1", "alias_count": 1}],
                "conflicts": [{"conflict_count": 1}],
            },
            "canon": {
                "entities": [{"entity_id": "entity-1", "entity_type": "character", "importance": 8}],
                "relationships": [{"relationship_id": "rel-1"}],
                "segment_summaries": [{"segment_id": "segment-1", "segment_order": 0}],
            },
        }
    )
    resolver = RecordingBindingResolver(_agent_profile_resolution())
    credentials = RecordingCredentialProvider(api_key="sk-profile")
    chat_client = RecordingJSONChatClient(response_json={})
    runner = seed_module.LLMFacilityAgentProfileRunner(
        binding_resolver=resolver,
        credential_provider=credentials,
        chat_client=chat_client,
        agent_profile_snapshot_writer=RecordingAgentProfileSnapshotWriter(),
        agent_profile_context_loader=loader,
    )

    result = runner.generate(context=_context(), module_key="character_agent_profile")

    assert result == {
        "status": "failed",
        "module_key": "character_agent_profile",
        "error": {
            "code": "AGENT_PROFILE_CONTEXT_UNAVAILABLE",
            "message": "agent profile source context is unavailable",
        },
    }
    assert resolver.calls == []
    assert credentials.calls == []
    assert chat_client.calls == []


def test_llm_facility_agent_profile_runner_fails_closed_when_context_loader_errors_before_provider() -> None:
    loader = RecordingAgentProfileContextLoader(
        error=RuntimeError(
            "driver failed prompt=hidden api_key=sk-hidden credential_ref=secret raw manuscript text"
        )
    )
    resolver = RecordingBindingResolver(_agent_profile_resolution())
    credentials = RecordingCredentialProvider(api_key="sk-profile")
    chat_client = RecordingJSONChatClient(response_json={})
    runner = seed_module.LLMFacilityAgentProfileRunner(
        binding_resolver=resolver,
        credential_provider=credentials,
        chat_client=chat_client,
        agent_profile_snapshot_writer=RecordingAgentProfileSnapshotWriter(),
        agent_profile_context_loader=loader,
    )

    result = runner.generate(context=_context(), module_key="character_agent_profile")

    assert result == {
        "status": "failed",
        "module_key": "character_agent_profile",
        "error": {
            "code": "AGENT_PROFILE_CONTEXT_LOAD_FAILED",
            "message": "agent profile source context load failed",
        },
    }
    assert resolver.calls == []
    assert credentials.calls == []
    assert chat_client.calls == []
    encoded = json.dumps(result, ensure_ascii=False)
    for forbidden in ("driver failed", "prompt", "api_key", "sk-hidden", "credential_ref", "raw manuscript text"):
        assert forbidden not in encoded


def test_postgres_agent_profile_context_loader_loads_sanitized_scoped_context_without_raw_fields() -> None:
    connection = AgentProfileContextConnection(
        resolution_rows=[
            {
                "seed_entity_resolution_snapshot_id": "resolution-snapshot-1",
                "model_id": "model-resolution",
                "merged_entity_count": 1,
                "alias_count": 1,
                "conflict_count": 0,
                "resolution_jsonb": {
                    "merged_entities": [{"canonical_name": "林舟", "aliases": ["小舟"]}],
                    "prompt": "must not reach provider",
                    "private_notes": "private note",
                    "body": "private body",
                    "provider": "provider-name",
                    "base_url": "https://provider.example",
                    "channel_id": "channel-secret",
                    "credential_ref": "secret-ref",
                },
            }
        ],
        entity_rows=[
            {
                "entity_id": "entity-1",
                "entity_type": "character",
                "canonical_name": "林舟",
                "importance": 8,
                "state_summary": "守住雨港秘密。",
                "metadata_jsonb": {"prompt": "hidden"},
            }
        ],
        relationship_rows=[
            {
                "relationship_id": "rel-1",
                "source_entity_name": "林舟",
                "target_entity_name": "陆晚",
                "relationship_type": "ally",
                "summary": "互相试探。",
                "evidence_text": "raw manuscript sentence",
            }
        ],
        segment_rows=[
            {
                "segment_id": "segment-1",
                "segment_order": 0,
                "summary": "雨夜相遇。",
                "source_object_key": "private/source.txt",
            }
        ],
    )
    loader = seed_module.PostgresAgentProfileContextLoader(connect=lambda: connection)

    context_payload = loader.load_context(context=_context())

    assert context_payload == {
        "entity_resolution": {
            "snapshot_id": "resolution-snapshot-1",
            "model_id": "model-resolution",
            "merged_entity_count": 1,
            "alias_count": 1,
            "conflict_count": 0,
            "resolution": {
                "merged_entities": [{"canonical_name": "林舟", "aliases": ["小舟"]}],
            },
        },
        "canon": {
            "entities": [
                {
                    "entity_id": "entity-1",
                    "entity_type": "character",
                    "canonical_name": "林舟",
                    "importance": 8,
                    "state_summary": "守住雨港秘密。",
                }
            ],
            "relationships": [
                {
                    "relationship_id": "rel-1",
                    "source_entity_name": "林舟",
                    "target_entity_name": "陆晚",
                    "relationship_type": "ally",
                    "summary": "互相试探。",
                }
            ],
            "segment_summaries": [
                {
                    "segment_id": "segment-1",
                    "segment_order": 0,
                    "summary": "雨夜相遇。",
                }
            ],
        },
    }
    queries = "\n".join(query for query, _params in connection.cursor_instance.executed)
    assert "seed_entity_resolution_snapshots" in queries
    assert "FROM entities" in queries
    assert "FROM relationships" in queries
    assert "FROM segment_summaries" in queries
    for forbidden in (
        "object_key",
        "source_object_key",
        "prompt",
        "credential",
        "private_notes",
        "body",
        "provider",
        "base_url",
        "channel_id",
        "api_key",
        "draft",
        "manuscript",
        "raw_text",
        "content_text",
        "evidence_text",
    ):
        assert forbidden not in queries.lower()
    assert all(
        params == ("tenant-1", "project-1", "run-1")
        for _query, params in connection.cursor_instance.executed[1:]
    )
    assert connection.closed is True


def test_agent_profile_runner_from_env_builds_db_backed_llm_facility_runner(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("DATABASE_URL", "postgresql://seed-runtime")
    monkeypatch.setenv(
        "LLM_CREDENTIAL_ENCRYPTION_KEY",
        "000102030405060708090a0b0c0d0e0f101112131415161718191a1b1c1d1e1f",
    )
    transport = RecordingHTTPTransport(
        response_body=json.dumps(
            {
                "choices": [
                    {
                        "message": {
                            "content": json.dumps(
                                {
                                    "agent_profiles": {
                                        "profiles": [{"name": "林舟", "voice": "冷静"}],
                                        "memory_seeds": [{"name": "林舟", "summary": "雨夜"}],
                                        "relationship_views": [{"source": "林舟", "target": "陆晚"}],
                                    }
                                },
                                ensure_ascii=False,
                            )
                        }
                    }
                ]
            }
        ).encode("utf-8")
    )
    connections = iter(
        [
            AgentProfileContextConnection(
                resolution_rows=[
                    {
                        "seed_entity_resolution_snapshot_id": "resolution-snapshot-1",
                        "model_id": "model-resolution",
                        "merged_entity_count": 1,
                        "alias_count": 1,
                        "conflict_count": 0,
                        "resolution_jsonb": {"merged_entities": [{"canonical_name": "林舟"}]},
                    }
                ],
                entity_rows=[],
                relationship_rows=[],
                segment_rows=[],
            ),
            QueryConnection(
                rows=[
                    {
                        "tenant_id": "tenant-1",
                        "project_id": "project-1",
                        "module_key": "character_agent_profile",
                        "channel_id": "channel-project",
                        "model_id": "model-profile",
                        "provider": "openai-compatible",
                        "base_url": "https://llm.example/v1",
                        "supports_json": True,
                        "settings_jsonb": "{}",
                    }
                ]
            ),
            QueryConnection(
                rows=[
                    {
                        "encrypted_api_key": (
                            "aes-256-gcm:v1:ABEiM0RVZneImaq7:"
                            "87utEhTfLrnKAiv0vtWdTg==:qe3dwCoCLzMECbZ5"
                        )
                    }
                ]
            ),
            FakeOntologySnapshotConnection([{"seed_agent_profile_snapshot_id": "profile-snapshot-1"}]),
        ]
    )

    runner = seed_module._agent_profile_runner_from_env(
        http_request=transport,
        connect=lambda: next(connections),
    )
    assert runner is not None

    result = runner.generate(context=_context(), module_key="character_agent_profile")

    assert result == {
        "status": "completed",
        "module_key": "character_agent_profile",
        "model_id": "model-profile",
        "profile_snapshot_id": "profile-snapshot-1",
        "profile_count": 1,
        "memory_seed_count": 1,
        "relationship_view_count": 1,
    }
    request = transport.requests[0]
    assert request.headers["Authorization"] == "Bearer sk-seed-live"
    request_body = request.data.decode("utf-8")
    assert "character_agent_profile" in request_body
    assert "source_context" in request_body
    assert "resolution-snapshot-1" in request_body
    assert "credential_ref" not in request_body
    assert "api_key" not in request_body


def test_postgres_text_segment_writer_requires_project_context() -> None:
    writer = PostgresTextSegmentWriter(connect=FakeConnection)
    context = _context().model_copy(update={"project_id": None})

    with pytest.raises(ValueError, match="project_id is required"):
        writer.record_text_segments(
            context=context,
            source_file_id="file-1",
            segments=[
                {
                    "segment_order": 0,
                    "content_excerpt": "正文片段",
                }
            ],
        )


def test_postgres_text_segment_writer_upserts_sanitized_segments() -> None:
    connection = FakeConnection()
    writer = PostgresTextSegmentWriter(connect=lambda: connection)

    writer.record_text_segments(
        context=_context(),
        source_file_id="file-1",
        segments=[
            {
                "segment_id": "11111111-1111-4111-8111-111111111111",
                "segment_order": 0,
                "chapter_guess": "第一章",
                "title_guess": "雨夜",
                "start_offset": 0,
                "end_offset": 128,
                "content_excerpt": "雨声压住了脚步。",
                "object_key": "segments/run-1/0000.txt",
                "summary": "雨夜开场。",
                "metadata_jsonb": {
                    "confidence": 0.92,
                    "prompt": "must not be stored",
                    "raw_content": "must not be stored",
                },
            }
        ],
    )

    assert connection.cursor_instance.executed[0] == (
        "SELECT app_set_tenant_context(%s::uuid, %s::uuid, false)",
        ("tenant-1", "project-1"),
    )
    assert "INSERT INTO text_segments" in connection.cursor_instance.query
    assert "segment_id" in connection.cursor_instance.query
    assert "ON CONFLICT (tenant_id, project_id, run_id, segment_order)" in connection.cursor_instance.query
    assert connection.cursor_instance.params[:14] == (
        "tenant-1",
        "11111111-1111-4111-8111-111111111111",
        "project-1",
        "run-1",
        "file-1",
        0,
        "第一章",
        "雨夜",
        0,
        128,
        "雨声压住了脚步。",
        "segments/run-1/0000.txt",
        "雨夜开场。",
        '{"confidence":0.92}',
    )
    assert connection.committed is True
    assert connection.closed is True


def test_seed_parse_segment_postgres_writers_roll_back_on_database_failure() -> None:
    workflow_connection = FailingConnection(fail_on_execute=2)
    workflow_writer = PostgresWorkflowEventWriter(connect=lambda: workflow_connection)
    with pytest.raises(RuntimeError, match="driver failure"):
        workflow_writer.record_workflow_event(
            context=_context(),
            event_type="seed.stage.pending",
            payload={"stage": "parse_file", "status": "pending"},
        )
    assert workflow_connection.rolled_back is True
    assert workflow_connection.committed is False
    assert workflow_connection.closed is True

    artifact_connection = FailingConnection(fail_on_commit=True)
    artifact_writer = PostgresTextArtifactWriter(connect=lambda: artifact_connection)
    with pytest.raises(RuntimeError, match="commit failure"):
        artifact_writer.record_text_artifact(
            context=_context(),
            source_file_id="file-1",
            artifact_type="extracted_text",
            object_key="artifacts/run-1/extracted.txt",
            char_count=128,
            line_count=8,
        )
    assert artifact_connection.rolled_back is True
    assert artifact_connection.closed is True

    segment_connection = FailingConnection(fail_on_execute=2)
    segment_writer = PostgresTextSegmentWriter(connect=lambda: segment_connection)
    with pytest.raises(RuntimeError, match="driver failure"):
        segment_writer.record_text_segments(
            context=_context(),
            source_file_id="file-1",
            segments=[
                {
                    "segment_id": "11111111-1111-4111-8111-111111111111",
                    "segment_order": 0,
                    "object_key": "segments/run-1/0000.txt",
                }
            ],
        )
    assert segment_connection.rolled_back is True
    assert segment_connection.committed is False
    assert segment_connection.closed is True


def test_postgres_reading_notes_writer_requires_project_context() -> None:
    writer = PostgresReadingNotesWriter(connect=FakeConnection)
    context = _context().model_copy(update={"project_id": None})

    with pytest.raises(ValueError, match="project_id is required"):
        writer.record_reading_notes(
            context=context,
            pass_id="pass-1",
            pass_type="sequential_reading",
            status="completed",
            module_key="sequential_reading",
            model_id="model-a",
            notes=[
                {
                    "segment_id": "segment-1",
                    "summary": "段落概要",
                    "payload_jsonb": {"characters": []},
                }
            ],
        )


def test_postgres_reading_notes_writer_upserts_sanitized_pass_and_notes() -> None:
    connection = FakeConnection()
    writer = PostgresReadingNotesWriter(connect=lambda: connection)

    writer.record_reading_notes(
        context=_context(),
        pass_id="pass-1",
        pass_type="sequential_reading",
        status="completed",
        module_key="sequential_reading",
        model_id="model-a",
        notes=[
            {
                "segment_id": "segment-1",
                "summary": "段落概要",
                "payload_jsonb": {
                    "characters": [{"name": "阿澜"}],
                    "prompt": "must not be stored",
                    "content": "raw source must not be stored",
                    "api_key": "sk-test",
                },
            }
        ],
    )

    assert len(connection.cursor_instance.executed) == 3
    assert connection.cursor_instance.executed[0] == (
        "SELECT app_set_tenant_context(%s::uuid, %s::uuid, false)",
        ("tenant-1", "project-1"),
    )
    pass_query, pass_params = connection.cursor_instance.executed[1]
    assert "INSERT INTO reading_passes" in pass_query
    assert "ON CONFLICT (pass_id)" in pass_query
    assert pass_params == (
        "tenant-1",
        "project-1",
        "run-1",
        "pass-1",
        "sequential_reading",
        "completed",
        "sequential_reading",
        "model-a",
        "{}",
    )

    note_query, note_params = connection.cursor_instance.executed[2]
    assert "INSERT INTO reading_segment_notes" in note_query
    assert "ON CONFLICT (tenant_id, run_id, segment_id, pass_id)" in note_query
    assert note_params == (
        "tenant-1",
        "project-1",
        "run-1",
        "segment-1",
        "pass-1",
        '{"characters":[{"name":"阿澜"}]}',
        "段落概要",
    )
    assert connection.committed is True
    assert connection.closed is True


def test_postgres_reading_notes_writer_rolls_back_on_database_failure() -> None:
    connection = FailingConnection(fail_on_execute=2)
    writer = PostgresReadingNotesWriter(connect=lambda: connection)

    with pytest.raises(RuntimeError, match="driver failure"):
        writer.record_reading_notes(
            context=_context(),
            pass_id="pass-1",
            pass_type="sequential_reading",
            status="completed",
            module_key="sequential_reading",
            model_id="model-a",
            notes=[
                {
                    "segment_id": "segment-1",
                    "summary": "段落概要",
                    "payload_jsonb": {"characters": [{"name": "阿澜"}]},
                }
            ],
        )

    assert connection.rolled_back is True
    assert connection.committed is False
    assert connection.closed is True


def test_postgres_runtime_facts_writer_sets_tenant_context_before_canon_writes() -> None:
    connection = FakeConnection()
    writer = PostgresRuntimeFactsWriter(connect=lambda: connection)

    counts = writer.record_runtime_facts(context=_context(), reading_notes=[])

    assert connection.cursor_instance.executed[0] == (
        "SELECT app_set_tenant_context(%s::uuid, %s::uuid, false)",
        ("tenant-1", "project-1"),
    )
    assert counts["entity_count"] == 0
    assert counts["segment_summary_count"] == 0
    assert connection.committed is True
    assert connection.closed is True


def test_postgres_runtime_facts_writer_rolls_back_on_database_failure() -> None:
    connection = FailingConnection(fail_on_execute=2)
    writer = PostgresRuntimeFactsWriter(connect=lambda: connection)

    with pytest.raises(RuntimeError, match="driver failure"):
        writer.record_runtime_facts(
            context=_context(),
            reading_notes=[
                {
                    "segment_id": "segment-1",
                    "summary": "段落概要",
                    "payload_jsonb": {
                        "characters": [],
                        "organizations": [],
                        "relationships": [],
                        "plot_threads": [],
                        "world_rules": [],
                        "events": [],
                        "consistency_notes": [],
                    },
                }
            ],
        )

    assert connection.rolled_back is True
    assert connection.committed is False
    assert connection.closed is True


def test_seed_worker_spec_registers_temporal_workflow_and_activity() -> None:
    spec = worker_spec()

    assert spec["task_queue"] == SEED_TASK_QUEUE
    assert "SeedPipelineWorkflow" in spec["workflows"]
    assert "seed_pipeline_activity" in spec["activities"]
    assert "parse_file_activity" in spec["activities"]
    assert "segment_text_activity" in spec["activities"]
    assert "sequential_reading_activity" in spec["activities"]
    assert "persist_runtime_facts_activity" in spec["activities"]
    assert "global_aggregation_activity" in spec["activities"]
    assert "ontology_activity" in spec["activities"]
    assert "entity_resolution_activity" in spec["activities"]
    assert "agent_profile_activity" in spec["activities"]
    assert "archive_candidate_activity" in spec["activities"]
    assert "index_assets_activity" in spec["activities"]
    assert "finalize_seed_activity" in spec["activities"]


def test_temporal_seed_worker_registers_parse_file_activity() -> None:
    components = worker_components_for_task_queue(SEED_TASK_QUEUE)

    assert [workflow.__name__ for workflow in components["workflows"]] == ["SeedPipelineWorkflow"]
    assert [activity.__name__ for activity in components["activities"]] == [
        "seed_pipeline_activity",
        "parse_file_activity",
        "segment_text_activity",
        "sequential_reading_activity",
        "persist_runtime_facts_activity",
        "global_aggregation_activity",
        "ontology_activity",
        "entity_resolution_activity",
        "agent_profile_activity",
        "archive_candidate_activity",
        "index_assets_activity",
        "finalize_seed_activity",
    ]
