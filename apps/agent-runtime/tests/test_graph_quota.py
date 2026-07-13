from __future__ import annotations

from typing import Any

from mirofish_agents.common.context import AgentContext
from mirofish_agents.llm_quota import ProviderCallAdmission, ProviderQuotaGate
from mirofish_agents.seed.sequential_reader import ModuleBindingResolution
from mirofish_agents.temporal.graph import GRAPH_BOND_GENERATION_MODULE_KEY, LLMFacilityGraphBondGenerationRunner


def _context() -> AgentContext:
    return AgentContext(
        tenant_id="11111111-1111-1111-1111-111111111111",
        project_id="22222222-2222-2222-2222-222222222222",
        run_id="33333333-3333-3333-3333-333333333333",
        workflow_type="story_graph_bond_generation",
        actor_user_id="44444444-4444-4444-4444-444444444444",
        module_key=GRAPH_BOND_GENERATION_MODULE_KEY,
        trace_id="trace-graph-quota",
        permissions={GRAPH_BOND_GENERATION_MODULE_KEY: ["run"]},
    )


def _resolution() -> ModuleBindingResolution:
    return ModuleBindingResolution(
        tenant_id=_context().tenant_id,
        project_id=_context().project_id,
        module_key=GRAPH_BOND_GENERATION_MODULE_KEY,
        channel_id="55555555-5555-5555-5555-555555555555",
        model_id="model-graph",
        provider="openai-compatible",
        base_url="https://provider.example/v1",
        credential_ref="55555555-5555-5555-5555-555555555555",
        supports_json=True,
        settings={"max_tokens": 256},
    )


class QuotaStore:
    def __init__(self) -> None:
        self.request: Any = None
        self.finalized = False

    def admit(self, request: Any) -> ProviderCallAdmission:
        self.request = request
        return ProviderCallAdmission(
            reservation_id="66666666-6666-6666-6666-666666666666",
            provider_call_id=request.provider_call_id,
            reserved_tokens=2000,
            reserved_cost_micros=0,
            lock_ids=(),
        )

    def finalize(self, request: Any, admission: Any, usage: Any, response_payload: Any) -> None:
        self.finalized = True

    def fail(self, request: Any, admission: Any, error_code: str) -> None:
        raise AssertionError(f"unexpected quota failure: {error_code}")


class Resolver:
    def resolve_module_binding(self, *, context: AgentContext, module_key: str) -> ModuleBindingResolution:
        return _resolution()


class Credentials:
    def resolve_api_key(self, *, context: AgentContext, credential_ref: str) -> str:
        return "private-provider-key"


class Chat:
    def __init__(self) -> None:
        self.provider_call_ids: list[str] = []

    def complete_json(self, **kwargs: Any) -> dict[str, Any]:
        self.provider_call_ids.append(kwargs["provider_call_id"])
        return {
            "bonds": [
                {
                    "title": "Unexpected alliance",
                    "summary": "Two rivals share an oath.",
                    "source_entity_name": "Alice",
                    "target_entity_name": "Bob",
                    "relationship_type": "ally",
                }
            ],
            "plot_threads": [],
            "conflict_triggers": [],
            "__llm_usage": {"prompt_tokens": 20, "completion_tokens": 10},
        }


class Candidates:
    def __init__(self) -> None:
        self.calls = 0

    def write_candidates(self, **kwargs: Any) -> dict[str, Any]:
        self.calls += 1
        return {"candidate_count": len(kwargs["candidates"]), "bond_candidate_count": 1}


def test_graph_bond_provider_call_is_quota_gated_before_candidate_persistence() -> None:
    store = QuotaStore()
    chat = Chat()
    candidates = Candidates()
    runner = LLMFacilityGraphBondGenerationRunner(
        binding_resolver=Resolver(),
        credential_provider=Credentials(),
        chat_client=chat,
        candidate_writer=candidates,
        quota_gate=ProviderQuotaGate(store),
    )

    result = runner.generate(
        context=_context(),
        graph_id="77777777-7777-7777-7777-777777777777",
        node_ids=[
            "88888888-8888-8888-8888-888888888888",
            "99999999-9999-9999-9999-999999999999",
        ],
        focus="rain oath",
        options={},
    )

    assert result["status"] == "completed"
    assert store.finalized
    assert store.request.stage == "bond_generation"
    assert chat.provider_call_ids == [store.request.provider_call_id]
    assert candidates.calls == 1
