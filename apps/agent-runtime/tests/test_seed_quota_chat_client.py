from __future__ import annotations

from typing import Any

from mirofish_agents.common.context import AgentContext
from mirofish_agents.seed.quota_chat_client import SeedQuotaAwareJSONChatClient
from mirofish_agents.seed.sequential_reader import LLMFacilityError, ModuleBindingResolution
from mirofish_agents.temporal.seed import _seed_chat_client


class RecordingQuotaGate:
    def __init__(self) -> None:
        self.calls: list[dict[str, Any]] = []

    def execute_json(self, **kwargs: Any) -> dict[str, Any]:
        self.calls.append(kwargs)
        return kwargs["validate"](
            kwargs["provider"]("llm:stable-seed-provider-call")
        )


class RecordingProviderClient:
    def __init__(self, response: dict[str, Any] | None = None) -> None:
        self.provider_call_ids: list[str] = []
        self.response = response

    def complete_json(self, **kwargs: Any) -> dict[str, Any]:
        self.provider_call_ids.append(kwargs["provider_call_id"])
        return self.response or {
            "seed_analysis": {"summary": "public summary"},
            "__llm_usage": {"prompt_tokens": 3, "completion_tokens": 2},
        }


def _sequential_messages(segment_ids: list[str]) -> list[dict[str, str]]:
    import json

    return [
        {"role": "system", "content": "Return structured notes."},
        {
            "role": "user",
            "content": json.dumps(
                {"segments": [{"segment_id": segment_id, "text": "private"} for segment_id in segment_ids]}
            ),
        },
    ]


def test_seed_quota_chat_client_routes_provider_call_through_gate() -> None:
    gate = RecordingQuotaGate()
    provider = RecordingProviderClient()
    client = SeedQuotaAwareJSONChatClient(quota_gate=gate, provider_client=provider)
    context = AgentContext(
        tenant_id="11111111-1111-4111-8111-111111111111",
        project_id="22222222-2222-4222-8222-222222222222",
        run_id="33333333-3333-4333-8333-333333333333",
        workflow_type="seed_pipeline",
        actor_user_id="44444444-4444-4444-8444-444444444444",
        trace_id="55555555-5555-4555-8555-555555555555",
        permissions={"seed_pipeline": ["run"]},
    )
    resolution = ModuleBindingResolution(
        tenant_id=context.tenant_id,
        project_id=context.project_id,
        module_key="anchor_point_summary",
        channel_id="66666666-6666-4666-8666-666666666666",
        model_id="77777777-7777-4777-8777-777777777777",
        provider="openai-compatible",
        base_url="https://provider.invalid/v1",
        credential_ref="private-ref",
        supports_json=True,
        settings={},
    )
    messages = [{"role": "user", "content": "private source text"}]

    result = client.complete_json(
        context=context,
        resolution=resolution,
        api_key="sk-private",
        messages=messages,
    )

    assert result["seed_analysis"]["summary"] == "public summary"
    assert provider.provider_call_ids == ["llm:stable-seed-provider-call"]
    assert len(gate.calls) == 1
    assert gate.calls[0]["stage"].startswith("seed_anchor_point_summary:")
    assert "private source text" not in gate.calls[0]["stage"]
    assert gate.calls[0]["call_index"] == 0
    assert gate.calls[0]["input_texts"] == ["private source text"]


def test_seed_quota_chat_client_rejects_unknown_seed_module_before_provider() -> None:
    gate = RecordingQuotaGate()
    provider = RecordingProviderClient()
    client = SeedQuotaAwareJSONChatClient(quota_gate=gate, provider_client=provider)
    context = AgentContext(
        tenant_id="11111111-1111-4111-8111-111111111111",
        project_id="22222222-2222-4222-8222-222222222222",
        run_id="33333333-3333-4333-8333-333333333333",
        workflow_type="seed_pipeline",
        actor_user_id=None,
        trace_id="55555555-5555-4555-8555-555555555555",
        permissions={"seed_pipeline": ["run"]},
    )
    resolution = ModuleBindingResolution(
        tenant_id=context.tenant_id,
        project_id=context.project_id,
        module_key="writer_composer",
        channel_id="66666666-6666-4666-8666-666666666666",
        model_id="77777777-7777-4777-8777-777777777777",
        provider="openai-compatible",
        base_url="https://provider.invalid/v1",
        credential_ref="private-ref",
        supports_json=True,
        settings={},
    )

    try:
        client.complete_json(
            context=context,
            resolution=resolution,
            api_key="sk-private",
            messages=[{"role": "user", "content": "private source text"}],
        )
    except LLMFacilityError as exc:
        assert exc.code == "VALIDATION_FAILED"
        assert exc.message == "unsupported Seed module for quota-aware provider call"
    else:
        raise AssertionError("unknown module did not fail closed")
    assert gate.calls == []
    assert provider.provider_call_ids == []


def test_seed_quota_chat_client_uses_distinct_identity_for_changed_retry_input() -> None:
    gate = RecordingQuotaGate()
    provider = RecordingProviderClient()
    client = SeedQuotaAwareJSONChatClient(quota_gate=gate, provider_client=provider)
    context = AgentContext(
        tenant_id="11111111-1111-4111-8111-111111111111",
        project_id="22222222-2222-4222-8222-222222222222",
        run_id="33333333-3333-4333-8333-333333333333",
        workflow_type="seed_pipeline",
        actor_user_id=None,
        trace_id="55555555-5555-4555-8555-555555555555",
        permissions={"seed_pipeline": ["run"]},
    )
    resolution = ModuleBindingResolution(
        tenant_id=context.tenant_id,
        project_id=context.project_id,
        module_key="sequential_reading",
        channel_id="66666666-6666-4666-8666-666666666666",
        model_id="77777777-7777-4777-8777-777777777777",
        provider="openai-compatible",
        base_url="https://provider.invalid/v1",
        credential_ref="private-ref",
        supports_json=True,
        settings={},
    )

    for source_text in ("first selected segments", "changed retry segments"):
        client.complete_json(
            context=context,
            resolution=resolution,
            api_key="sk-private",
            messages=[{"role": "user", "content": source_text}],
        )

    assert gate.calls[0]["stage"] != gate.calls[1]["stage"]
    assert "first selected segments" not in gate.calls[0]["stage"]
    assert "changed retry segments" not in gate.calls[1]["stage"]


def test_seed_quota_chat_client_rejects_wrong_sequential_segment_id_before_cache_finalize() -> None:
    expected_id = "88888888-8888-4888-8888-888888888888"
    provider = RecordingProviderClient(
        response={
            "notes": [
                {
                    "segment_id": "22222222-2222-4222-8222-222222222222",
                    "summary": "wrong project id",
                    "payload_jsonb": {},
                }
            ],
            "__llm_usage": {"prompt_tokens": 3, "completion_tokens": 2},
        }
    )
    gate = RecordingQuotaGate()
    client = SeedQuotaAwareJSONChatClient(quota_gate=gate, provider_client=provider)
    context = AgentContext(
        tenant_id="11111111-1111-4111-8111-111111111111",
        project_id="22222222-2222-4222-8222-222222222222",
        run_id="33333333-3333-4333-8333-333333333333",
        workflow_type="seed_pipeline",
        actor_user_id=None,
        trace_id="55555555-5555-4555-8555-555555555555",
        permissions={"seed_pipeline": ["run"]},
    )
    resolution = ModuleBindingResolution(
        tenant_id=context.tenant_id,
        project_id=context.project_id,
        module_key="sequential_reading",
        channel_id="66666666-6666-4666-8666-666666666666",
        model_id="deepseek-v4-flash",
        provider="openai-compatible",
        base_url="https://provider.invalid/v1",
        credential_ref="private-ref",
        supports_json=True,
        settings={},
    )

    try:
        client.complete_json(
            context=context,
            resolution=resolution,
            api_key="sk-private",
            messages=_sequential_messages([expected_id]),
        )
    except LLMFacilityError as exc:
        assert exc.code == "SCHEMA_VALIDATION_FAILED"
        assert exc.message == "sequential reading note segment_id must reference its input batch"
    else:
        raise AssertionError("wrong sequential segment id reached the replay cache")


def test_seed_production_chat_factory_enables_quota_gate() -> None:
    client = _seed_chat_client(database_url="postgresql://seed-runtime.invalid/app")

    assert isinstance(client, SeedQuotaAwareJSONChatClient)


def test_seed_quota_chat_client_gives_distinct_call_identity_per_enrichment_batch() -> None:
    """Batched enrichment must not collide on one idempotency key (doc 42 R4).

    The quota gate keys idempotency on stable_provider_call_id(context, module,
    stage, call_index) where stage embeds a digest of the input text. Two batches
    over different entity subsets produce different user payloads, hence distinct
    stages and distinct provider call identities — so batch 2 is a real LLM call,
    not a replay of batch 1.
    """
    from mirofish_agents.llm_quota.gate import stable_provider_call_id

    gate = RecordingQuotaGate()
    provider = RecordingProviderClient()
    client = SeedQuotaAwareJSONChatClient(quota_gate=gate, provider_client=provider)
    context = AgentContext(
        tenant_id="11111111-1111-4111-8111-111111111111",
        project_id="22222222-2222-4222-8222-222222222222",
        run_id="33333333-3333-4333-8333-333333333333",
        workflow_type="seed_pipeline",
        actor_user_id=None,
        trace_id="55555555-5555-4555-8555-555555555555",
        permissions={"seed_pipeline": ["run"]},
    )
    resolution = ModuleBindingResolution(
        tenant_id=context.tenant_id,
        project_id=context.project_id,
        module_key="character_agent_profile",
        channel_id="66666666-6666-4666-8666-666666666666",
        model_id="77777777-7777-4777-8777-777777777777",
        provider="openai-compatible",
        base_url="https://provider.invalid/v1",
        credential_ref="private-ref",
        supports_json=True,
        settings={},
    )
    batch_one = [{"role": "user", "content": '{"batch_entities":["甲","乙"],"source_context":{}}'}]
    batch_two = [{"role": "user", "content": '{"batch_entities":["丙","丁"],"source_context":{}}'}]

    for messages in (batch_one, batch_two):
        client.complete_json(
            context=context,
            resolution=resolution,
            api_key="sk-private",
            messages=messages,
        )

    assert len(gate.calls) == 2
    first_stage = gate.calls[0]["stage"]
    second_stage = gate.calls[1]["stage"]
    assert first_stage != second_stage
    first_call_id = stable_provider_call_id(
        context, "character_agent_profile", first_stage, gate.calls[0]["call_index"]
    )
    second_call_id = stable_provider_call_id(
        context, "character_agent_profile", second_stage, gate.calls[1]["call_index"]
    )
    assert first_call_id != second_call_id
