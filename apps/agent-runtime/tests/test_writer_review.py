from __future__ import annotations

import json
from dataclasses import dataclass, field
from typing import Any

import pytest

from mirofish_agents.common.context import AgentContext
from mirofish_agents.seed.sequential_reader import LLMFacilityError, ModuleBindingResolution
from mirofish_agents.temporal.writer_review import (
    WRITER_REVIEW_MODULE_KEY,
    WRITER_REVIEW_TASK_QUEUE,
    WRITER_REVIEW_WORKFLOW_TYPE,
    LLMFacilityWriterReviewRunner,
    validate_review_issues,
    run_writer_review_workflow_locally,
    worker_spec,
)
from mirofish_agents.temporal import writer_review
from mirofish_agents.llm_quota import QuotaEnforcedJSONChatClient


TENANT_ID = "11111111-1111-4111-8111-111111111111"
PROJECT_ID = "22222222-2222-4222-8222-222222222222"
RUN_ID = "33333333-3333-4333-8333-333333333333"
ACTOR_ID = "44444444-4444-4444-8444-444444444444"
REVIEW_ID = "55555555-5555-4555-8555-555555555555"
DRAFT_ID = "66666666-6666-4666-8666-666666666666"


def _context(**overrides: Any) -> AgentContext:
    values = {
        "tenant_id": TENANT_ID,
        "project_id": PROJECT_ID,
        "run_id": RUN_ID,
        "workflow_type": WRITER_REVIEW_WORKFLOW_TYPE,
        "actor_user_id": ACTOR_ID,
        "module_key": WRITER_REVIEW_MODULE_KEY,
        "trace_id": f"trace_{RUN_ID}",
        "permissions": {WRITER_REVIEW_MODULE_KEY: ["run"]},
    }
    values.update(overrides)
    return AgentContext(**values)


def _provider_result() -> dict[str, Any]:
    return {
        "issues": [
            {
                "severity": "high",
                "category": "pov_drift",
                "summary": "The focal perspective changes without a narrative transition.",
                "suggestion": "Keep perception anchored to the scene viewpoint character.",
            },
            {
                "severity": "medium",
                "category": "phrase_repetition",
                "summary": "Several sentence openings use the same syntactic pattern.",
                "suggestion": "Vary sentence openings while preserving the intended pacing.",
            },
        ],
        "__llm_usage": {"prompt_tokens": 30, "completion_tokens": 20, "total_tokens": 50},
    }


@dataclass
class RecordingStore:
    source: dict[str, Any] = field(default_factory=lambda: {"draft_text": "Private candidate prose.", "replayed": False})
    completed: dict[str, Any] | None = None
    failed: dict[str, Any] | None = None
    partial_issues: list[dict[str, str]] = field(default_factory=list)

    def load_candidate(self, **_: Any) -> dict[str, Any]:
        return self.source

    def complete_review(self, **kwargs: Any) -> dict[str, Any]:
        self.completed = kwargs
        self.partial_issues = list(kwargs["issues"])
        return {
            "status": "completed",
            "replayed": False,
            "review_id": kwargs["review_id"],
            "draft_id": kwargs["draft_id"],
            "issue_count": len(kwargs["issues"]),
            "model_id": kwargs["resolution"].model_id,
        }

    def fail_review(self, **kwargs: Any) -> None:
        self.failed = kwargs
        self.partial_issues.clear()


class RecordingResolver:
    calls = 0

    def resolve_module_binding(self, *, context: AgentContext, module_key: str) -> ModuleBindingResolution:
        self.calls += 1
        assert module_key == WRITER_REVIEW_MODULE_KEY
        return ModuleBindingResolution(
            tenant_id=context.tenant_id,
            project_id=context.project_id,
            module_key=module_key,
            channel_id="77777777-7777-4777-8777-777777777777",
            model_id="review-model",
            provider="openai-compatible",
            base_url="http://127.0.0.1:18080/v1",
            credential_ref="77777777-7777-4777-8777-777777777777",
            supports_json=True,
        )


class RecordingCredentialProvider:
    calls = 0

    def resolve_api_key(self, **_: Any) -> str:
        self.calls += 1
        return "private-provider-key"


class RecordingChatClient:
    calls = 0
    request: dict[str, Any] | None = None
    result: dict[str, Any]

    def __init__(self, result: dict[str, Any] | None = None) -> None:
        self.result = result or _provider_result()

    def complete_json(self, **kwargs: Any) -> dict[str, Any]:
        self.calls += 1
        self.request = kwargs
        return self.result


def _runner(store: RecordingStore, chat: RecordingChatClient | None = None) -> tuple[LLMFacilityWriterReviewRunner, RecordingResolver, RecordingCredentialProvider, RecordingChatClient]:
    resolver = RecordingResolver()
    credential = RecordingCredentialProvider()
    client = chat or RecordingChatClient()
    return (
        LLMFacilityWriterReviewRunner(
            binding_resolver=resolver,
            credential_provider=credential,
            chat_client=client,
            store=store,
        ),
        resolver,
        credential,
        client,
    )


def test_writer_review_uses_independent_module_and_returns_count_only_metadata() -> None:
    store = RecordingStore()
    runner, resolver, credential, chat = _runner(store)

    result = run_writer_review_workflow_locally(
        {"context": _context().model_dump(), "review_id": REVIEW_ID, "draft_id": DRAFT_ID},
        runner=runner,
    )

    assert result["status"] == "completed"
    assert result["issue_count"] == 2
    assert resolver.calls == credential.calls == chat.calls == 1
    assert store.completed is not None
    assert store.completed["usage"]["total_tokens"] == 50
    assert chat.request is not None
    assert chat.request["messages"][1]["content"] == "Private candidate prose."
    public = json.dumps(result)
    assert "Private candidate prose" not in public
    assert "private-provider-key" not in public
    assert "focal perspective" not in public


def test_writer_review_completed_replay_skips_binding_credential_and_provider() -> None:
    store = RecordingStore(source={
        "status": "completed", "replayed": True, "review_id": REVIEW_ID,
        "draft_id": DRAFT_ID, "issue_count": 3,
    })
    runner, resolver, credential, chat = _runner(store)

    result = runner.run_review(context=_context(), review_id=REVIEW_ID, draft_id=DRAFT_ID)

    assert result["replayed"] is True
    assert result["issue_count"] == 3
    assert resolver.calls == credential.calls == chat.calls == 0
    assert store.completed is None


@pytest.mark.parametrize(
    "result",
    [
        {"issues": []},
        {"issues": [{"severity": "score-7", "category": "pov_drift", "summary": "A", "suggestion": "B"}]},
        {"issues": [{"severity": "high", "category": "unknown", "summary": "A", "suggestion": "B"}]},
        {"issues": [{"severity": "high", "category": "pov_drift", "summary": "A", "suggestion": "B", "quote": "private"}]},
        {"issues": [{"severity": "high", "category": "pov_drift", "summary": "\u201cThis quoted candidate sentence is too long to expose.\u201d", "suggestion": "B"}]},
        {"issues": [
            {"severity": "high", "category": "pov_drift", "summary": "Same issue", "suggestion": "First"},
            {"severity": "medium", "category": "pov_drift", "summary": " same  issue ", "suggestion": "Second"},
        ]},
    ],
)
def test_writer_review_schema_rejects_empty_invalid_duplicate_or_sensitive_issues(result: dict[str, Any]) -> None:
    with pytest.raises(LLMFacilityError) as caught:
        validate_review_issues(result)
    assert caught.value.code == "LLM_RESPONSE_SCHEMA_INVALID"


def test_writer_review_schema_failure_leaves_zero_partial_issues_and_marks_terminal_failure() -> None:
    store = RecordingStore()
    chat = RecordingChatClient({"issues": [{"severity": "high", "category": "pov_drift", "summary": "Missing suggestion"}]})
    runner, _, _, _ = _runner(store, chat)

    result = run_writer_review_workflow_locally(
        {"context": _context().model_dump(), "review_id": REVIEW_ID, "draft_id": DRAFT_ID},
        runner=runner,
    )

    assert result["status"] == "failed"
    assert result["error"]["code"] == "LLM_RESPONSE_SCHEMA_INVALID"
    assert store.completed is None
    assert store.partial_issues == []
    assert store.failed is not None
    assert store.failed["code"] == "LLM_RESPONSE_SCHEMA_INVALID"


def test_writer_review_worker_is_dedicated() -> None:
    spec = worker_spec()
    assert spec == {
        "task_queue": WRITER_REVIEW_TASK_QUEUE,
        "workflows": ["WriterReviewWorkflow"],
        "activities": ["writer_review_activity"],
    }


def test_writer_review_environment_runner_enforces_shared_quota(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("DATABASE_URL", "postgresql://runtime@example.invalid/mirofish")
    monkeypatch.setenv("LLM_CREDENTIAL_ENCRYPTION_KEY", "11" * 32)

    runner = writer_review._runner_from_env()

    assert isinstance(runner, LLMFacilityWriterReviewRunner)
    assert isinstance(runner._chat_client, QuotaEnforcedJSONChatClient)


@pytest.mark.parametrize(
    "code",
    [
        "LLM_QUOTA_POLICY_UNAVAILABLE",
        "LLM_QUOTA_TOKENS_EXCEEDED",
        "LLM_QUOTA_COST_EXCEEDED",
        "LLM_QUOTA_CONCURRENCY_EXCEEDED",
        "LLM_QUOTA_BACKEND_FAILED",
        "LLM_QUOTA_RESERVATION_UNAVAILABLE",
        "LLM_PROVIDER_USAGE_MISSING",
        "LLM_USAGE_EXCEEDS_RESERVATION",
    ],
)
def test_writer_review_quota_errors_remain_stable_and_public(code: str) -> None:
    stable_code, message = writer_review._stable_error(LLMFacilityError(code, "private quota detail"))

    assert stable_code == code
    assert "private" not in message
