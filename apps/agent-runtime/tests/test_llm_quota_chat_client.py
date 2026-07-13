from __future__ import annotations

from typing import Any

import pytest

from mirofish_agents.common.context import AgentContext
from mirofish_agents.llm_quota import QuotaEnforcedJSONChatClient
from mirofish_agents.seed.sequential_reader import LLMFacilityError, ModuleBindingResolution
from mirofish_agents.temporal.character import _runner_from_env as character_runner_from_env
from mirofish_agents.temporal.worldline import _worldline_step_runner_from_env
from mirofish_agents.temporal.worldline_prepare import _prepare_runner_from_env


class RecordingGate:
    def __init__(self) -> None:
        self.calls: list[dict[str, Any]] = []

    def execute_json(self, **kwargs: Any) -> dict[str, Any]:
        self.calls.append(kwargs)
        return kwargs["validate"](kwargs["provider"]("llm:stable-provider-call"))


class RecordingProvider:
    def __init__(self) -> None:
        self.call_ids: list[str] = []

    def complete_json(self, **kwargs: Any) -> dict[str, Any]:
        self.call_ids.append(kwargs["provider_call_id"])
        return {"candidate_events": [], "__llm_usage": {"prompt_tokens": 3, "completion_tokens": 2}}


def _context() -> AgentContext:
    return AgentContext(
        tenant_id="11111111-1111-4111-8111-111111111111",
        project_id="22222222-2222-4222-8222-222222222222",
        run_id="33333333-3333-4333-8333-333333333333",
        workflow_type="worldline_step",
        actor_user_id="44444444-4444-4444-8444-444444444444",
        trace_id="55555555-5555-4555-8555-555555555555",
        module_key="worldline_director",
        permissions={"worldline_director": ["run"]},
    )


def _resolution() -> ModuleBindingResolution:
    return ModuleBindingResolution(
        tenant_id="11111111-1111-4111-8111-111111111111",
        project_id="22222222-2222-4222-8222-222222222222",
        module_key="worldline_director",
        channel_id="66666666-6666-4666-8666-666666666666",
        model_id="77777777-7777-4777-8777-777777777777",
        provider="openai-compatible",
        base_url="https://provider.invalid/v1",
        credential_ref="private-ref",
        supports_json=True,
        settings={},
    )


def test_quota_enforced_chat_uses_stable_private_input_digest() -> None:
    gate = RecordingGate()
    provider = RecordingProvider()
    client = QuotaEnforcedJSONChatClient(
        quota_gate=gate,
        stage_prefix="worldline_director",
        provider_client=provider,
    )

    result = client.complete_json(
        context=_context(),
        resolution=_resolution(),
        api_key="sk-private",
        messages=[{"role": "user", "content": "private novel context"}],
    )

    assert result["candidate_events"] == []
    assert provider.call_ids == ["llm:stable-provider-call"]
    assert gate.calls[0]["stage"].startswith("worldline_director:")
    assert "private novel context" not in gate.calls[0]["stage"]
    assert gate.calls[0]["input_texts"] == ["private novel context"]


def test_quota_enforced_chat_rejects_invalid_messages_before_admission() -> None:
    gate = RecordingGate()
    client = QuotaEnforcedJSONChatClient(quota_gate=gate, stage_prefix="character_dialogue")

    with pytest.raises(LLMFacilityError, match="provider messages are invalid"):
        client.complete_json(
            context=_context(),
            resolution=_resolution(),
            api_key="sk-private",
            messages=[{"role": "user"}],  # type: ignore[list-item]
        )

    assert gate.calls == []


def test_worldline_production_factory_enforces_quota(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("DATABASE_URL", "postgresql://worldline-runtime.invalid/app")

    runner = _worldline_step_runner_from_env()

    assert runner is not None
    assert isinstance(runner._chat_client, QuotaEnforcedJSONChatClient)
    assert runner._telemetry_writer is None


def test_character_production_factory_enforces_quota(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("DATABASE_URL", "postgresql://character-runtime.invalid/app")

    runner = character_runner_from_env()

    assert runner is not None
    assert isinstance(runner._chat_client, QuotaEnforcedJSONChatClient)


def test_worldline_prepare_production_factory_enforces_quota(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("DATABASE_URL", "postgresql://worldline-prepare-runtime.invalid/app")

    runner = _prepare_runner_from_env()

    assert runner is not None
    assert isinstance(runner._chat_client, QuotaEnforcedJSONChatClient)
    assert runner._telemetry_writer is None
