from __future__ import annotations

import inspect
from dataclasses import dataclass, field
from typing import Any

import pytest

from mirofish_agents.common.context import AgentContext
from mirofish_agents.seed.sequential_reader import LLMFacilityError, ModuleBindingResolution
from mirofish_agents.temporal.writer_planning import (
    WRITER_BOOK_PLANNER_MODULE_KEY,
    WRITER_BOOK_PLAN_WORKFLOW_TYPE,
    WRITER_DEDUP_MODULE_KEY,
    WRITER_DEDUP_WORKFLOW_TYPE,
    LLMFacilityWriterPlanningRunner,
    PostgresWriterPlanningStore,
    validate_book_plan_candidate,
    validate_dedup_candidates,
    worker_spec,
)


TENANT_ID = "11111111-1111-4111-8111-111111111111"
PROJECT_ID = "22222222-2222-4222-8222-222222222222"
RUN_ID = "33333333-3333-4333-8333-333333333333"
ACTOR_ID = "44444444-4444-4444-8444-444444444444"
BOOK_PLAN_ID = "55555555-5555-4555-8555-555555555555"


def _context(workflow_type: str, module_key: str) -> AgentContext:
    return AgentContext(
        tenant_id=TENANT_ID,
        project_id=PROJECT_ID,
        run_id=RUN_ID,
        workflow_type=workflow_type,
        actor_user_id=ACTOR_ID,
        module_key=module_key,
        trace_id=f"trace_{RUN_ID}",
        permissions={module_key: ["run"]},
    )


class RecordingResolver:
    def __init__(self) -> None:
        self.modules: list[str] = []

    def resolve_module_binding(self, *, context: AgentContext, module_key: str) -> ModuleBindingResolution:
        self.modules.append(module_key)
        return ModuleBindingResolution(
            tenant_id=context.tenant_id,
            project_id=context.project_id,
            module_key=module_key,
            channel_id="66666666-6666-4666-8666-666666666666",
            model_id="writer-planning-model",
            provider="openai-compatible",
            base_url="http://127.0.0.1:18080/v1",
            credential_ref="66666666-6666-4666-8666-666666666666",
            supports_json=True,
        )


class RecordingCredential:
    def resolve_api_key(self, **_: Any) -> str:
        return "private-planning-key"


class RecordingChat:
    def __init__(self, response: dict[str, Any]) -> None:
        self.response = response
        self.requests: list[dict[str, Any]] = []

    def complete_json(self, **kwargs: Any) -> dict[str, Any]:
        self.requests.append(kwargs)
        return self.response


@dataclass
class RecordingStore:
    dedup_source: dict[str, Any] = field(default_factory=lambda: {
        "replayed": False,
        "source_text": "Private adopted manuscript source.",
        "source_count": 2,
    })
    book_source: dict[str, Any] = field(default_factory=lambda: {
        "replayed": False,
        "title": "Rain Treaty",
        "premise": "Private planning premise.",
        "target_chapter_count": 6,
        "expected_version": 1,
    })
    completed_dedup: dict[str, Any] | None = None
    completed_book: dict[str, Any] | None = None
    failed: dict[str, Any] | None = None

    def load_dedup_source(self, **_: Any) -> dict[str, Any]:
        return self.dedup_source

    def complete_dedup(self, **kwargs: Any) -> dict[str, Any]:
        self.completed_dedup = kwargs
        return {"status": "completed", "replayed": False, "candidate_count": len(kwargs["patterns"])}

    def load_book_plan(self, **_: Any) -> dict[str, Any]:
        return self.book_source

    def complete_book_plan(self, **kwargs: Any) -> dict[str, Any]:
        self.completed_book = kwargs
        return {"status": "completed", "replayed": False, "book_plan_id": kwargs["book_plan_id"], "candidate": True}

    def fail_workflow(self, **kwargs: Any) -> None:
        self.failed = kwargs


def test_dedup_extractor_uses_exact_module_and_persists_candidates_only() -> None:
    store = RecordingStore()
    resolver = RecordingResolver()
    chat = RecordingChat({
        "patterns": [{"pattern_text": "Repeated weather-led opening", "pattern_kind": "sentence_shape", "occurrence_count": 3}],
        "__llm_usage": {"prompt_tokens": 20, "completion_tokens": 10, "total_tokens": 30},
    })
    runner = LLMFacilityWriterPlanningRunner(
        binding_resolver=resolver, credential_provider=RecordingCredential(), chat_client=chat, store=store,
    )

    result = runner.run_dedup(context=_context(WRITER_DEDUP_WORKFLOW_TYPE, WRITER_DEDUP_MODULE_KEY))

    assert result == {"status": "completed", "replayed": False, "candidate_count": 1}
    assert resolver.modules == [WRITER_DEDUP_MODULE_KEY]
    assert store.completed_dedup is not None
    assert store.completed_dedup["patterns"][0]["lifecycle"] == "candidate"
    assert store.completed_dedup["patterns"][0]["enabled"] is False
    assert "Private adopted" not in str(result)
    assert "private-planning-key" not in str(result)


def test_book_plan_generation_uses_exact_module_and_keeps_plan_candidate() -> None:
    store = RecordingStore()
    resolver = RecordingResolver()
    chat = RecordingChat({
        "premise": "A negotiator must trade certainty for peace.",
        "acts": [{"title": "Terms", "summary": "The bargain is framed.", "chapter_start": 1, "chapter_end": 3}],
        "__llm_usage": {"prompt_tokens": 18, "completion_tokens": 12, "total_tokens": 30},
    })
    runner = LLMFacilityWriterPlanningRunner(
        binding_resolver=resolver, credential_provider=RecordingCredential(), chat_client=chat, store=store,
    )

    result = runner.run_book_plan(
        context=_context(WRITER_BOOK_PLAN_WORKFLOW_TYPE, WRITER_BOOK_PLANNER_MODULE_KEY),
        book_plan_id=BOOK_PLAN_ID,
        expected_version=1,
    )

    assert result["candidate"] is True
    assert resolver.modules == [WRITER_BOOK_PLANNER_MODULE_KEY]
    assert store.completed_book is not None
    assert store.completed_book["candidate"]["status"] == "draft"
    assert "Private planning premise" not in str(result)


@pytest.mark.parametrize(
    "response",
    [
        {"patterns": []},
        {"patterns": [{"pattern_text": "raw", "pattern_kind": "unknown", "occurrence_count": 2}]},
        {"patterns": [{"pattern_text": "raw", "pattern_kind": "phrase", "occurrence_count": 1, "body": "private"}]},
    ],
)
def test_dedup_schema_rejects_empty_unknown_or_private_fields(response: dict[str, Any]) -> None:
    with pytest.raises(LLMFacilityError) as caught:
        validate_dedup_candidates(response, source_text="Private adopted manuscript source.")
    assert caught.value.code == "LLM_RESPONSE_SCHEMA_INVALID"


@pytest.mark.parametrize(
    "response",
    [
        {"premise": "A", "acts": []},
        {"premise": "A", "acts": [{"title": "One", "summary": "Two", "chapter_start": 2, "chapter_end": 1}]},
        {"premise": "A", "acts": [{"title": "One", "summary": "Two", "chapter_start": 1, "chapter_end": 2, "body": "private"}]},
    ],
)
def test_book_plan_schema_rejects_empty_invalid_ranges_or_private_fields(response: dict[str, Any]) -> None:
    with pytest.raises(LLMFacilityError) as caught:
        validate_book_plan_candidate(response, target_chapter_count=6)
    assert caught.value.code == "LLM_RESPONSE_SCHEMA_INVALID"


def test_completed_replay_skips_binding_credential_and_provider() -> None:
    store = RecordingStore(dedup_source={"replayed": True, "status": "completed", "candidate_count": 4})
    resolver = RecordingResolver()
    chat = RecordingChat({})
    runner = LLMFacilityWriterPlanningRunner(
        binding_resolver=resolver, credential_provider=RecordingCredential(), chat_client=chat, store=store,
    )

    result = runner.run_dedup(context=_context(WRITER_DEDUP_WORKFLOW_TYPE, WRITER_DEDUP_MODULE_KEY))

    assert result["candidate_count"] == 4
    assert resolver.modules == []
    assert chat.requests == []


def test_writer_planning_worker_is_dedicated() -> None:
    assert worker_spec() == {
        "task_queue": "writer-planning",
        "workflows": ["WriterDedupExtractionWorkflow", "WriterBookPlanWorkflow"],
        "activities": ["writer_dedup_activity", "writer_book_plan_activity", "writer_planning_failure_activity"],
    }


def test_runtime_revalidates_adopted_source_when_activity_executes() -> None:
    source = inspect.getsource(PostgresWriterPlanningStore.load_dedup_source)
    assert "JOIN writer_drafts" in source
    assert "draft.status = 'adopted'" in source
    assert "block.source_draft_id" in source
