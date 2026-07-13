from __future__ import annotations

import json
from typing import Any

from mirofish_agents.common.context import AgentContext
from mirofish_agents.llm_quota import ProviderCallAdmission, ProviderQuotaGate
from mirofish_agents.seed.sequential_reader import ModuleBindingResolution
from mirofish_agents.temporal.assets import (
    ASSET_INGESTION_MODULE_KEY,
    LLMFacilityAssetIngestionRunner,
    OpenAICompatibleEmbeddingClient,
)


def _context() -> AgentContext:
    return AgentContext(
        tenant_id="11111111-1111-1111-1111-111111111111",
        project_id="22222222-2222-2222-2222-222222222222",
        run_id="33333333-3333-3333-3333-333333333333",
        workflow_type="asset_ingestion",
        actor_user_id="44444444-4444-4444-4444-444444444444",
        module_key=ASSET_INGESTION_MODULE_KEY,
        trace_id="trace-asset-quota",
        permissions={ASSET_INGESTION_MODULE_KEY: ["run"]},
    )


def _resolution(module_key: str = ASSET_INGESTION_MODULE_KEY) -> ModuleBindingResolution:
    return ModuleBindingResolution(
        tenant_id=_context().tenant_id,
        project_id=_context().project_id,
        module_key=module_key,
        channel_id="55555555-5555-5555-5555-555555555555",
        model_id="model-1",
        provider="openai-compatible",
        base_url="https://provider.example/v1",
        credential_ref="55555555-5555-5555-5555-555555555555",
        supports_json=True,
        settings={"max_tokens": 128},
    )


class Resolver:
    def resolve_module_binding(self, *, context: AgentContext, module_key: str) -> ModuleBindingResolution:
        assert context == _context()
        return _resolution(module_key)


class Credentials:
    def resolve_api_key(self, *, context: AgentContext, credential_ref: str) -> str:
        assert context == _context()
        return "private-provider-key"


class QuotaChat:
    def __init__(self) -> None:
        self.calls: list[str] = []

    def complete_json(self, **kwargs: Any) -> dict[str, Any]:
        self.calls.append(kwargs["provider_call_id"])
        return {
            "candidates": [
                {
                    "asset_type": "world_rule",
                    "title": "Rain Law",
                    "summary": "Rain opens the northern gate.",
                    "payload": {},
                    "tags": ["rain"],
                }
            ],
            "__llm_usage": {"prompt_tokens": 12, "completion_tokens": 8},
        }


class Candidates:
    def __init__(self) -> None:
        self.calls: list[dict[str, Any]] = []

    def write_candidates(self, **kwargs: Any) -> dict[str, Any]:
        self.calls.append(kwargs)
        return {"candidate_count": len(kwargs["candidates"]), "asset_type_counts": {"world_rule": 1}}


class QuotaStore:
    def __init__(self) -> None:
        self.request: Any = None
        self.finalized: Any = None

    def admit(self, request: Any) -> ProviderCallAdmission:
        self.request = request
        return ProviderCallAdmission(
            reservation_id="66666666-6666-6666-6666-666666666666",
            provider_call_id=request.provider_call_id,
            reserved_tokens=1000,
            reserved_cost_micros=0,
            lock_ids=(),
        )

    def finalize(self, request: Any, admission: Any, usage: Any, response_payload: Any) -> None:
        self.finalized = (request, admission, usage, response_payload)

    def fail(self, request: Any, admission: Any, error_code: str) -> None:
        raise AssertionError(f"unexpected quota failure: {error_code}")


def test_asset_ingestion_provider_call_uses_quota_gate_and_stable_identity() -> None:
    store = QuotaStore()
    chat = QuotaChat()
    candidates = Candidates()
    runner = LLMFacilityAssetIngestionRunner(
        binding_resolver=Resolver(),
        credential_provider=Credentials(),
        chat_client=chat,
        candidate_writer=candidates,
        quota_gate=ProviderQuotaGate(store),
    )

    result = runner.ingest(
        context=_context(),
        module_key=ASSET_INGESTION_MODULE_KEY,
        material_text="complete source material",
        hint_type="world_rule",
        scope="project",
        options={},
    )

    assert result["status"] == "completed"
    assert len(chat.calls) == 1
    assert chat.calls[0] == store.request.provider_call_id
    assert store.request.stage == "candidate_generation"
    assert store.finalized[2].total_tokens == 20
    assert len(candidates.calls) == 1


def test_embedding_client_propagates_stable_identity_and_usage_without_changing_vector_shape() -> None:
    captured: dict[str, Any] = {}

    def request(http_request: Any) -> bytes:
        captured["headers"] = dict(http_request.header_items())
        return json.dumps(
            {
                "data": [{"index": 0, "embedding": [1.0, 0.0, 0.0]}],
                "usage": {"prompt_tokens": 5, "total_tokens": 5},
            }
        ).encode("utf-8")

    client = OpenAICompatibleEmbeddingClient(http_request=request)
    result = client.embed_texts(
        context=_context(),
        resolution=_resolution("asset_search_embedding"),
        api_key="private-provider-key",
        texts=["full asset text"],
        provider_call_id="llm:stable-call",
    )

    assert result == [[1.0, 0.0, 0.0]]
    assert result.llm_usage == {"prompt_tokens": 5, "completion_tokens": 0, "total_tokens": 5}
    assert captured["headers"]["Idempotency-key"] == "llm:stable-call"
