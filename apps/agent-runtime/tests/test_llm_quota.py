from __future__ import annotations

from dataclasses import replace
from typing import Any, Callable

import pytest

from mirofish_agents.common.context import AgentContext
from mirofish_agents.llm_quota import (
    ProviderCallAdmission,
    ProviderCallRequest,
    ProviderQuotaGate,
    ProviderUsage,
    stable_provider_call_id,
)
from mirofish_agents.seed.sequential_reader import LLMFacilityError, ModuleBindingResolution
from mirofish_agents.llm_quota.postgres import _json_payload


def _context() -> AgentContext:
    return AgentContext(
        tenant_id="11111111-1111-1111-1111-111111111111",
        project_id="22222222-2222-2222-2222-222222222222",
        run_id="33333333-3333-3333-3333-333333333333",
        workflow_type="asset_ingestion",
        actor_user_id="44444444-4444-4444-4444-444444444444",
        module_key="asset_ingestion",
        trace_id="trace-asset-ingestion",
        permissions={"asset_ingestion": ["run"]},
    )


def _resolution() -> ModuleBindingResolution:
    return ModuleBindingResolution(
        tenant_id=_context().tenant_id,
        project_id=_context().project_id,
        module_key="asset_ingestion",
        channel_id="55555555-5555-5555-5555-555555555555",
        model_id="model-json",
        provider="openai-compatible",
        base_url="https://provider.example/v1",
        credential_ref="55555555-5555-5555-5555-555555555555",
        supports_json=True,
        settings={"max_tokens": 512, "max_concurrency": 2},
    )


class RecordingQuotaStore:
    def __init__(self, *, replay_payload: dict[str, Any] | None = None) -> None:
        self.replay_payload = replay_payload
        self.admissions: list[ProviderCallRequest] = []
        self.finalized: list[tuple[ProviderCallRequest, ProviderCallAdmission, ProviderUsage, dict[str, Any]]] = []
        self.failed: list[tuple[ProviderCallRequest, ProviderCallAdmission, str]] = []

    def admit(self, request: ProviderCallRequest) -> ProviderCallAdmission:
        self.admissions.append(request)
        return ProviderCallAdmission(
            reservation_id="66666666-6666-6666-6666-666666666666",
            provider_call_id=request.provider_call_id,
            reserved_tokens=4096,
            reserved_cost_micros=100,
            lock_ids=("77777777-7777-7777-7777-777777777777",),
            replay_payload=self.replay_payload,
        )

    def finalize(
        self,
        request: ProviderCallRequest,
        admission: ProviderCallAdmission,
        usage: ProviderUsage,
        response_payload: dict[str, Any],
    ) -> None:
        self.finalized.append((request, admission, usage, response_payload))

    def fail(self, request: ProviderCallRequest, admission: ProviderCallAdmission, error_code: str) -> None:
        self.failed.append((request, admission, error_code))


def _provider_response() -> dict[str, Any]:
    return {
        "candidates": [{"title": "Rain Treaty"}],
        "__llm_usage": {"prompt_tokens": 11, "completion_tokens": 7},
    }


def test_provider_call_identity_is_stable_and_separates_stage_and_call_index() -> None:
    first = stable_provider_call_id(_context(), "asset_ingestion", "candidate_generation", 0)
    assert first == stable_provider_call_id(_context(), "asset_ingestion", "candidate_generation", 0)
    assert first.startswith("llm:")
    assert first != stable_provider_call_id(_context(), "asset_ingestion", "candidate_generation", 1)
    assert first != stable_provider_call_id(_context(), "asset_ingestion", "style_extraction", 0)
    assert first != stable_provider_call_id(
        _context().model_copy(update={"tenant_id": "aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa"}),
        "asset_ingestion",
        "candidate_generation",
        0,
    )


def test_gate_admits_before_provider_and_finalizes_actual_usage() -> None:
    store = RecordingQuotaStore()
    gate = ProviderQuotaGate(store)
    order: list[str] = []

    def provider(provider_call_id: str) -> dict[str, Any]:
        order.append("provider")
        assert store.admissions
        assert provider_call_id == store.admissions[0].provider_call_id
        return _provider_response()

    candidates = gate.execute_json(
        context=_context(),
        resolution=_resolution(),
        stage="candidate_generation",
        call_index=0,
        input_texts=["full source material"],
        provider=provider,
        validate=lambda response: response["candidates"],
    )

    assert candidates == [{"title": "Rain Treaty"}]
    assert order == ["provider"]
    assert len(store.admissions) == 1
    assert store.admissions[0].input_token_upper_bound == len("full source material".encode("utf-8"))
    assert store.admissions[0].output_token_upper_bound == 512
    assert store.finalized[0][2] == ProviderUsage(prompt_tokens=11, completion_tokens=7)
    assert store.failed == []


@pytest.mark.parametrize(
    ("provider", "validate", "expected_code"),
    [
        (
            lambda _provider_call_id: (_ for _ in ()).throw(
                LLMFacilityError("LLM_PROVIDER_UNAVAILABLE", "provider unavailable")
            ),
            lambda response: response,
            "LLM_PROVIDER_UNAVAILABLE",
        ),
        (
            lambda _provider_call_id: _provider_response(),
            lambda _response: (_ for _ in ()).throw(
                LLMFacilityError("SCHEMA_VALIDATION_FAILED", "invalid candidates")
            ),
            "SCHEMA_VALIDATION_FAILED",
        ),
        (
            lambda _provider_call_id: {"candidates": []},
            lambda response: response,
            "LLM_PROVIDER_USAGE_MISSING",
        ),
    ],
)
def test_gate_releases_reservation_and_lease_on_provider_schema_or_usage_failure(
    provider: Callable[[str], dict[str, Any]],
    validate: Callable[[dict[str, Any]], Any],
    expected_code: str,
) -> None:
    store = RecordingQuotaStore()
    gate = ProviderQuotaGate(store)

    with pytest.raises(LLMFacilityError) as exc_info:
        gate.execute_json(
            context=_context(),
            resolution=_resolution(),
            stage="candidate_generation",
            call_index=0,
            input_texts=["source"],
            provider=provider,
            validate=validate,
        )

    assert exc_info.value.code == expected_code
    assert store.finalized == []
    assert len(store.failed) == 1
    assert store.failed[0][2] == expected_code


def test_gate_replays_private_finalized_response_without_provider_side_effect() -> None:
    store = RecordingQuotaStore(replay_payload=_provider_response())
    gate = ProviderQuotaGate(store)

    result = gate.execute_json(
        context=_context(),
        resolution=_resolution(),
        stage="candidate_generation",
        call_index=0,
        input_texts=["source"],
        provider=lambda _provider_call_id: pytest.fail("replay must not call provider"),
        validate=lambda response: response["candidates"],
    )

    assert result == [{"title": "Rain Treaty"}]
    assert store.finalized == []
    assert store.failed == []


def test_gate_rejects_scope_mismatch_before_store_or_provider() -> None:
    store = RecordingQuotaStore()
    gate = ProviderQuotaGate(store)
    mismatched = replace(_resolution(), project_id="aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa")

    with pytest.raises(LLMFacilityError) as exc_info:
        gate.execute_json(
            context=_context(),
            resolution=mismatched,
            stage="candidate_generation",
            call_index=0,
            input_texts=["source"],
            provider=lambda _provider_call_id: pytest.fail("provider must not run"),
            validate=lambda response: response,
        )

    assert exc_info.value.code == "VALIDATION_FAILED"
    assert store.admissions == []


def test_private_replay_payload_removes_credentials_without_dropping_usage_or_candidates() -> None:
    payload = _json_payload(
        {
            "candidates": [{"title": "Public title", "api_key": "sk-secret"}],
            "credential_ref": "private-channel",
            "nested": {"authorization": "Bearer secret", "summary": "Allowed summary"},
            "__llm_usage": {"prompt_tokens": 4, "completion_tokens": 2},
        }
    )

    assert payload == {
        "candidates": [{"title": "Public title"}],
        "nested": {"summary": "Allowed summary"},
        "__llm_usage": {"prompt_tokens": 4, "completion_tokens": 2},
    }
