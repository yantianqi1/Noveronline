from __future__ import annotations

import hashlib
import json
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
        validate = _validated_provider_payload
        if resolution.module_key == "sequential_reading":
            expected_segment_ids = _sequential_segment_ids(messages)
            if expected_segment_ids:
                validate = lambda payload: _validated_sequential_reading_payload(
                    payload,
                    expected_segment_ids=expected_segment_ids,
                )
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
            validate=validate,
        )


def _validated_provider_payload(payload: dict[str, Any]) -> dict[str, Any]:
    if not isinstance(payload, dict):
        raise LLMFacilityError("SCHEMA_VALIDATION_FAILED", "Seed provider response must be an object")
    return payload


def _sequential_segment_ids(messages: list[dict[str, str]]) -> frozenset[str]:
    for message in reversed(messages):
        if message.get("role") != "user":
            continue
        try:
            body = json.loads(message["content"])
        except (KeyError, TypeError, json.JSONDecodeError):
            return frozenset()
        segments = body.get("segments") if isinstance(body, dict) else None
        if not isinstance(segments, list):
            return frozenset()
        segment_ids = {
            segment["segment_id"].strip()
            for segment in segments
            if isinstance(segment, dict)
            and isinstance(segment.get("segment_id"), str)
            and segment["segment_id"].strip()
        }
        return frozenset(segment_ids) if len(segment_ids) == len(segments) else frozenset()
    return frozenset()


def _validated_sequential_reading_payload(
    payload: dict[str, Any],
    *,
    expected_segment_ids: frozenset[str],
) -> dict[str, Any]:
    _validated_provider_payload(payload)
    notes = payload.get("notes")
    if not isinstance(notes, list):
        raise LLMFacilityError("SCHEMA_VALIDATION_FAILED", "sequential reading notes must be an array")
    returned_segment_ids: list[str] = []
    for note in notes:
        if not isinstance(note, dict):
            raise LLMFacilityError("SCHEMA_VALIDATION_FAILED", "sequential reading notes must be objects")
        segment_id = note.get("segment_id")
        if not isinstance(segment_id, str) or segment_id.strip() not in expected_segment_ids:
            raise LLMFacilityError(
                "SCHEMA_VALIDATION_FAILED",
                "sequential reading note segment_id must reference its input batch",
            )
        if note.get("summary") is not None and not isinstance(note.get("summary"), str):
            raise LLMFacilityError("SCHEMA_VALIDATION_FAILED", "sequential reading note summary must be text")
        if not isinstance(note.get("payload_jsonb"), dict):
            raise LLMFacilityError(
                "SCHEMA_VALIDATION_FAILED",
                "sequential reading note payload_jsonb must be an object",
            )
        returned_segment_ids.append(segment_id.strip())
    if len(returned_segment_ids) != len(set(returned_segment_ids)):
        raise LLMFacilityError("SCHEMA_VALIDATION_FAILED", "sequential reading notes must not duplicate segments")
    if set(returned_segment_ids) != set(expected_segment_ids):
        raise LLMFacilityError("SCHEMA_VALIDATION_FAILED", "sequential reading notes must cover the input batch")
    return payload


def _provider_stage(stage: str, input_texts: list[str]) -> str:
    digest = hashlib.sha256("\x1f".join(input_texts).encode("utf-8")).hexdigest()[:16]
    return f"{stage}:{digest}"
