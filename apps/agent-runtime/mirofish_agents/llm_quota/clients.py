from __future__ import annotations

import hashlib
import json
from typing import Any, Callable
from urllib.request import Request, urlopen

from mirofish_agents.common.context import AgentContext
from mirofish_agents.seed.sequential_reader import LLMFacilityError, ModuleBindingResolution

from .gate import ProviderQuotaGate


class QuotaAwareJSONChatClient:
    def __init__(self, *, http_request: Callable[[Request], bytes] | None = None) -> None:
        self._http_request = http_request or _urlopen_bytes

    def complete_json(
        self,
        *,
        context: AgentContext,
        resolution: ModuleBindingResolution,
        api_key: str,
        messages: list[dict[str, str]],
        provider_call_id: str,
    ) -> dict[str, Any]:
        body: dict[str, Any] = {
            "model": resolution.model_id,
            "messages": messages,
            "response_format": {"type": "json_object"},
        }
        for key in ("temperature", "max_tokens"):
            value = resolution.settings.get(key)
            if isinstance(value, (int, float)) and not isinstance(value, bool):
                body[key] = value
        request = Request(
            _chat_completions_url(resolution.base_url),
            data=json.dumps(body, ensure_ascii=False).encode("utf-8"),
            headers={
                "Authorization": f"Bearer {api_key}",
                "Content-Type": "application/json",
                "Idempotency-Key": provider_call_id,
                "X-MiroFish-Tenant-Id": context.tenant_id,
                "X-MiroFish-Project-Id": context.project_id or "",
                "X-MiroFish-Run-Id": context.run_id,
                "X-MiroFish-Module-Key": resolution.module_key,
            },
            method="POST",
        )
        try:
            response_body = self._http_request(request)
            response_json = json.loads(response_body.decode("utf-8"))
            content = response_json["choices"][0]["message"]["content"]
        except Exception as exc:
            raise LLMFacilityError("LLM_PROVIDER_ERROR", "chat completion provider call failed") from exc
        try:
            parsed = json.loads(content)
        except (TypeError, json.JSONDecodeError) as exc:
            raise LLMFacilityError("SCHEMA_VALIDATION_FAILED", "chat completion content was not valid JSON") from exc
        if not isinstance(parsed, dict):
            raise LLMFacilityError("SCHEMA_VALIDATION_FAILED", "chat completion JSON must be an object")
        usage = _usage(response_json.get("usage"))
        if usage is not None:
            parsed["__llm_usage"] = usage
        return parsed


class QuotaEnforcedJSONChatClient:
    """Adapt the existing JSON chat contract to the shared provider quota gate."""

    def __init__(
        self,
        *,
        quota_gate: ProviderQuotaGate,
        stage_prefix: str,
        provider_client: QuotaAwareJSONChatClient | None = None,
    ) -> None:
        normalized_prefix = stage_prefix.strip()
        if not normalized_prefix:
            raise ValueError("stage_prefix is required")
        self._quota_gate = quota_gate
        self._stage_prefix = normalized_prefix
        self._provider_client = provider_client or QuotaAwareJSONChatClient()

    def complete_json(
        self,
        *,
        context: AgentContext,
        resolution: ModuleBindingResolution,
        api_key: str,
        messages: list[dict[str, str]],
    ) -> dict[str, Any]:
        input_texts = _message_texts(messages)
        stage = f"{self._stage_prefix}:{_input_digest(input_texts)}"
        return self._quota_gate.execute_json(
            context=context,
            resolution=resolution,
            stage=stage,
            call_index=0,
            input_texts=input_texts,
            provider=lambda provider_call_id: self._provider_client.complete_json(
                context=context,
                resolution=resolution,
                api_key=api_key,
                messages=messages,
                provider_call_id=provider_call_id,
            ),
            validate=_object_payload,
        )


def _message_texts(messages: list[dict[str, str]]) -> list[str]:
    values = [
        message.get("content")
        for message in messages
        if isinstance(message, dict) and isinstance(message.get("content"), str)
    ]
    if len(values) != len(messages):
        raise LLMFacilityError("VALIDATION_FAILED", "provider messages are invalid")
    return values


def _input_digest(input_texts: list[str]) -> str:
    return hashlib.sha256("\x1f".join(input_texts).encode("utf-8")).hexdigest()[:16]


def _object_payload(payload: dict[str, Any]) -> dict[str, Any]:
    if not isinstance(payload, dict):
        raise LLMFacilityError("SCHEMA_VALIDATION_FAILED", "LLM provider response must be an object")
    return payload


def _usage(value: Any) -> dict[str, int] | None:
    if not isinstance(value, dict):
        return None
    prompt = _non_negative_int(value.get("prompt_tokens") if "prompt_tokens" in value else value.get("input_tokens"))
    completion = _non_negative_int(
        value.get("completion_tokens") if "completion_tokens" in value else value.get("output_tokens")
    )
    total = _non_negative_int(value.get("total_tokens"))
    if prompt is None and completion is None and total is None:
        return None
    result: dict[str, int] = {}
    if prompt is not None:
        result["prompt_tokens"] = prompt
    if completion is not None:
        result["completion_tokens"] = completion
    if total is not None:
        result["total_tokens"] = total
    return result


def _non_negative_int(value: Any) -> int | None:
    if isinstance(value, bool):
        return None
    if isinstance(value, int) and value >= 0:
        return value
    if isinstance(value, float) and value >= 0 and value.is_integer():
        return int(value)
    return None


def _chat_completions_url(base_url: str) -> str:
    normalized = base_url.strip().rstrip("/")
    if normalized.endswith("/chat/completions"):
        return normalized
    return f"{normalized}/chat/completions"


def _urlopen_bytes(request: Request) -> bytes:
    with urlopen(request, timeout=60) as response:
        return response.read()
