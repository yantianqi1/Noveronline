from __future__ import annotations

import hashlib
from typing import Any

from mirofish_agents.common.context import AgentContext
from mirofish_agents.llm_quota import ProviderQuotaGate, QuotaAwareJSONChatClient
from mirofish_agents.seed.sequential_reader import LLMFacilityError, ModuleBindingResolution


_SEED_PROVIDER_STAGES = {
    "sequential_reading": "seed_sequential_reading",
    "anchor_point_summary": "seed_anchor_point_summary",
    "story_ontology": "seed_story_ontology",
    "entity_resolution": "seed_entity_resolution",
    "character_agent_profile": "seed_character_agent_profile",
    "narrative_archives": "seed_narrative_archives",
}


class SeedQuotaAwareJSONChatClient:
    """Preserve the Seed chat-client contract while enforcing the shared quota gate."""

    def __init__(
        self,
        *,
        quota_gate: ProviderQuotaGate,
        provider_client: QuotaAwareJSONChatClient | None = None,
    ) -> None:
        self._quota_gate = quota_gate
        self._provider_client = provider_client or QuotaAwareJSONChatClient()

    def complete_json(
        self,
        *,
        context: AgentContext,
        resolution: ModuleBindingResolution,
        api_key: str,
        messages: list[dict[str, str]],
    ) -> dict[str, Any]:
        stage = _SEED_PROVIDER_STAGES.get(resolution.module_key)
        if stage is None:
            raise LLMFacilityError(
                "VALIDATION_FAILED",
                "unsupported Seed module for quota-aware provider call",
            )
        input_texts = [
            message["content"]
            for message in messages
            if isinstance(message, dict) and isinstance(message.get("content"), str)
        ]
        if len(input_texts) != len(messages):
            raise LLMFacilityError("VALIDATION_FAILED", "Seed provider messages are invalid")
        provider_stage = _provider_stage(stage, input_texts)
        return self._quota_gate.execute_json(
            context=context,
            resolution=resolution,
            stage=provider_stage,
            call_index=0,
            input_texts=input_texts,
            provider=lambda provider_call_id: self._provider_client.complete_json(
                context=context,
                resolution=resolution,
                api_key=api_key,
                messages=messages,
                provider_call_id=provider_call_id,
            ),
            validate=_validated_provider_payload,
        )


def _validated_provider_payload(payload: dict[str, Any]) -> dict[str, Any]:
    if not isinstance(payload, dict):
        raise LLMFacilityError("SCHEMA_VALIDATION_FAILED", "Seed provider response must be an object")
    return payload


def _provider_stage(stage: str, input_texts: list[str]) -> str:
    digest = hashlib.sha256("\x1f".join(input_texts).encode("utf-8")).hexdigest()[:16]
    return f"{stage}:{digest}"
