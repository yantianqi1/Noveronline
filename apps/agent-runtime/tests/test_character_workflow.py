from __future__ import annotations

import json
from dataclasses import dataclass, field
from typing import Any

from mirofish_agents.common.context import AgentContext
from mirofish_agents.seed.sequential_reader import LLMFacilityError, ModuleBindingResolution
from mirofish_agents.temporal.character import (
    CHARACTER_DIALOGUE_MODULE_KEY,
    CHARACTER_DIALOGUE_WORKFLOW_TYPE,
    LLMFacilityCharacterDialogueRunner,
    _validate_provider_result,
    run_character_dialogue_workflow_locally,
    worker_spec,
)


TENANT_ID = "11111111-1111-4111-8111-111111111111"
PROJECT_ID = "22222222-2222-4222-8222-222222222222"
RUN_ID = "33333333-3333-4333-8333-333333333333"
ACTOR_ID = "44444444-4444-4444-8444-444444444444"
INTERACTION_ID = "55555555-5555-4555-8555-555555555555"
USER_TURN_ID = "66666666-6666-4666-8666-666666666666"


def _context(**overrides: Any) -> AgentContext:
    values = {
        "tenant_id": TENANT_ID,
        "project_id": PROJECT_ID,
        "run_id": RUN_ID,
        "workflow_type": CHARACTER_DIALOGUE_WORKFLOW_TYPE,
        "actor_user_id": ACTOR_ID,
        "module_key": CHARACTER_DIALOGUE_MODULE_KEY,
        "trace_id": f"trace_{RUN_ID}",
        "permissions": {CHARACTER_DIALOGUE_MODULE_KEY: ["run"]},
    }
    values.update(overrides)
    return AgentContext(**values)


@dataclass
class RecordingStore:
    source: dict[str, Any] = field(
        default_factory=lambda: {
            "mode": "dialogue",
            "pov_agent_id": "agent-1",
            "world_scope": "current_world",
            "history": [],
            "user_turn": {"summary": "Ask about the gate."},
        }
    )
    persisted: dict[str, Any] | None = None
    failed: tuple[str, str] | None = None

    def load_context(self, **kwargs: Any) -> dict[str, Any]:
        assert kwargs["interaction_id"] == INTERACTION_ID
        assert kwargs["user_turn_id"] == USER_TURN_ID
        return self.source

    def persist_result(self, **kwargs: Any) -> dict[str, Any]:
        self.persisted = kwargs
        result = kwargs["result"]
        return {
            "status": "completed",
            "replayed": False,
            "interaction_id": INTERACTION_ID,
            "turn_id": "77777777-7777-4777-8777-777777777777",
            "turn_order": 2,
            "memory_candidate_count": len(result["memory_candidates"]),
            "relation_candidate_count": len(result["relation_candidates"]),
            "world_state_candidate_count": len(result["world_state_candidates"]),
        }

    def mark_failed(self, **kwargs: Any) -> None:
        self.failed = (kwargs["code"], kwargs["message"])


class RecordingResolver:
    module_key = ""

    def resolve_module_binding(self, *, context: AgentContext, module_key: str) -> ModuleBindingResolution:
        self.module_key = module_key
        return ModuleBindingResolution(
            tenant_id=context.tenant_id,
            project_id=context.project_id,
            module_key=module_key,
            channel_id="channel-1",
            model_id="model-character",
            provider="openai-compatible",
            base_url="http://127.0.0.1:18080/v1",
            credential_ref="credential-1",
            supports_json=True,
        )


class CredentialProvider:
    def resolve_api_key(self, **_: Any) -> str:
        return "secret-key"


class RecordingChatClient:
    request: dict[str, Any] | None = None

    def complete_json(self, **kwargs: Any) -> dict[str, Any]:
        self.request = kwargs
        return {
            "reply_summary": "The gate was opened from inside.",
            "speaker_type": "agent",
            "speaker_id": "agent-1",
            "memory_candidates": [{"summary": "The visitor asked about the gate."}],
            "relation_candidates": [{
                "source_entity_name": "Gatekeeper",
                "target_entity_name": "Visitor",
                "relationship_type": "distrusts",
                "change": "The gatekeeper became suspicious.",
            }],
            "world_state_candidates": [{"proposal": "Inspect the inner lock."}],
            "response": "provider raw response must not escape",
        }


def test_character_dialogue_uses_exact_module_and_returns_only_public_metadata() -> None:
    store = RecordingStore()
    resolver = RecordingResolver()
    chat = RecordingChatClient()
    runner = LLMFacilityCharacterDialogueRunner(
        binding_resolver=resolver,
        credential_provider=CredentialProvider(),
        chat_client=chat,
        store=store,
    )

    result = run_character_dialogue_workflow_locally(
        {"context": _context().model_dump(), "interaction_id": INTERACTION_ID, "user_turn_id": USER_TURN_ID},
        runner=runner,
    )

    assert result["status"] == "completed"
    assert resolver.module_key == "character_dialogue"
    assert result["memory_candidate_count"] == 1
    assert result["relation_candidate_count"] == 1
    assert result["world_state_candidate_count"] == 1
    assert store.persisted is not None
    assert all(item["lifecycle"] == "candidate" for item in store.persisted["result"]["memory_candidates"])
    public = json.dumps(result)
    assert "opened from inside" not in public
    assert "provider raw" not in public
    assert "secret-key" not in public


def test_character_dialogue_replay_does_not_call_llm_or_write_again() -> None:
    store = RecordingStore(
        source={
            "status": "completed",
            "replayed": True,
            "interaction_id": INTERACTION_ID,
            "turn_id": "77777777-7777-4777-8777-777777777777",
            "turn_order": 2,
        }
    )
    resolver = RecordingResolver()
    runner = LLMFacilityCharacterDialogueRunner(
        binding_resolver=resolver,
        credential_provider=CredentialProvider(),
        chat_client=RecordingChatClient(),
        store=store,
    )

    result = runner.run_dialogue(context=_context(), interaction_id=INTERACTION_ID, user_turn_id=USER_TURN_ID)

    assert result["replayed"] is True
    assert resolver.module_key == ""
    assert store.persisted is None


def test_character_dialogue_unbound_failure_is_explicit_and_sanitized() -> None:
    store = RecordingStore()

    class UnboundResolver:
        def resolve_module_binding(self, **_: Any) -> ModuleBindingResolution:
            raise LLMFacilityError("LLM_MODULE_UNBOUND", "raw prompt api_key=secret")

    runner = LLMFacilityCharacterDialogueRunner(
        binding_resolver=UnboundResolver(),
        credential_provider=CredentialProvider(),
        chat_client=RecordingChatClient(),
        store=store,
    )
    result = run_character_dialogue_workflow_locally(
        {"context": _context().model_dump(), "interaction_id": INTERACTION_ID, "user_turn_id": USER_TURN_ID},
        runner=runner,
    )

    assert result["status"] == "failed"
    assert result["error"] == {"code": "LLM_MODULE_UNBOUND", "message": "character_dialogue module is not bound"}
    assert store.failed == ("LLM_MODULE_UNBOUND", "character_dialogue module is not bound")
    assert "secret" not in json.dumps(result)


def test_character_dialogue_rejects_wrong_context_before_runtime() -> None:
    store = RecordingStore()
    runner = LLMFacilityCharacterDialogueRunner(
        binding_resolver=RecordingResolver(),
        credential_provider=CredentialProvider(),
        chat_client=RecordingChatClient(),
        store=store,
    )
    result = run_character_dialogue_workflow_locally(
        {
            "context": _context(workflow_type="worldline_step").model_dump(),
            "interaction_id": INTERACTION_ID,
            "user_turn_id": USER_TURN_ID,
        },
        runner=runner,
    )
    assert result["error"]["code"] == "VALIDATION_FAILED"
    assert store.persisted is None


def test_character_candidates_cannot_claim_canon_or_manuscript_lifecycle() -> None:
    validated = _validate_provider_result(
        {
            "reply_summary": "A reply",
            "memory_candidates": [{"lifecycle": "canon", "summary": "proposal"}],
            "relation_candidates": [{
                "lifecycle": "adopted",
                "summary": "relationship proposal",
                "source_entity_name": "A",
                "target_entity_name": "B",
                "relationship_type": "trusts",
            }],
            "world_state_candidates": [{"lifecycle": "manuscript", "proposal": "world proposal"}],
        }
    )
    for key in ("memory_candidates", "relation_candidates", "world_state_candidates"):
        assert validated[key][0]["lifecycle"] == "candidate"


def test_character_candidates_strip_high_risk_provider_fields() -> None:
    validated = _validate_provider_result(
        {
            "reply_summary": "A reply",
            "memory_candidates": [{
                "summary": "A safe memory",
                "prompt": "hidden",
                "api_key": "sk-hidden",
                "nested": {"credential_ref": "secret", "safe": True},
            }],
            "relation_candidates": [],
            "world_state_candidates": [],
        }
    )
    candidate = validated["memory_candidates"][0]
    assert "prompt" not in candidate and "api_key" not in candidate
    assert candidate["nested"] == {"safe": True}


def test_character_worker_spec_is_isolated() -> None:
    assert worker_spec() == {
        "task_queue": "character-interactive",
        "workflows": ["CharacterDialogueWorkflow"],
        "activities": ["character_dialogue_activity"],
    }
