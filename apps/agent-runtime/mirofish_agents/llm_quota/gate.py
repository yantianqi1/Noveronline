from __future__ import annotations

import hashlib
from collections.abc import Callable, Sequence
from typing import Any, Protocol, TypeVar

from mirofish_agents.common.context import AgentContext
from mirofish_agents.seed.sequential_reader import LLMFacilityError, ModuleBindingResolution

from .models import ProviderCallAdmission, ProviderCallRequest, ProviderUsage


T = TypeVar("T")


class ProviderQuotaStore(Protocol):
    def admit(self, request: ProviderCallRequest) -> ProviderCallAdmission:
        ...

    def finalize(
        self,
        request: ProviderCallRequest,
        admission: ProviderCallAdmission,
        usage: ProviderUsage,
        response_payload: dict[str, Any],
    ) -> None:
        ...

    def fail(self, request: ProviderCallRequest, admission: ProviderCallAdmission, error_code: str) -> None:
        ...


class ProviderQuotaGate:
    def __init__(self, store: ProviderQuotaStore) -> None:
        self._store = store

    def execute_json(
        self,
        *,
        context: AgentContext,
        resolution: ModuleBindingResolution,
        stage: str,
        call_index: int,
        input_texts: Sequence[str],
        provider: Callable[[str], dict[str, Any]],
        validate: Callable[[dict[str, Any]], T],
    ) -> T:
        request = _request(
            context=context,
            resolution=resolution,
            stage=stage,
            call_index=call_index,
            input_texts=input_texts,
            output_token_upper_bound=_optional_positive_int(resolution.settings.get("max_tokens")),
        )
        return self._execute(request=request, provider=provider, validate=validate)

    def execute_embedding(
        self,
        *,
        context: AgentContext,
        resolution: ModuleBindingResolution,
        stage: str,
        call_index: int,
        input_texts: Sequence[str],
        provider: Callable[[str], dict[str, Any]],
        validate: Callable[[dict[str, Any]], T],
    ) -> T:
        request = _request(
            context=context,
            resolution=resolution,
            stage=stage,
            call_index=call_index,
            input_texts=input_texts,
            output_token_upper_bound=0,
        )
        return self._execute(request=request, provider=provider, validate=validate)

    def _execute(
        self,
        *,
        request: ProviderCallRequest,
        provider: Callable[[str], dict[str, Any]],
        validate: Callable[[dict[str, Any]], T],
    ) -> T:
        admission = self._store.admit(request)
        if admission.provider_call_id != request.provider_call_id:
            raise LLMFacilityError("LLM_PROVIDER_CALL_CONFLICT", "LLM provider call identity conflicts with its reservation")
        if admission.replay_payload is not None:
            _provider_usage(admission.replay_payload)
            return validate(admission.replay_payload)

        try:
            response = provider(request.provider_call_id)
        except LLMFacilityError as exc:
            self._fail(request, admission, exc.code)
            raise
        except Exception as exc:
            error = LLMFacilityError("LLM_PROVIDER_ERROR", "LLM provider call failed")
            self._fail(request, admission, error.code)
            raise error from exc

        try:
            if not isinstance(response, dict):
                raise LLMFacilityError("SCHEMA_VALIDATION_FAILED", "LLM provider response must be an object")
            value = validate(response)
            usage = _provider_usage(response)
        except LLMFacilityError as exc:
            self._fail(request, admission, exc.code)
            raise
        except Exception as exc:
            error = LLMFacilityError("SCHEMA_VALIDATION_FAILED", "LLM provider response failed schema validation")
            self._fail(request, admission, error.code)
            raise error from exc

        self._store.finalize(request, admission, usage, response)
        return value

    def _fail(self, request: ProviderCallRequest, admission: ProviderCallAdmission, error_code: str) -> None:
        try:
            self._store.fail(request, admission, error_code)
        except Exception as exc:
            raise LLMFacilityError(
                "LLM_QUOTA_RELEASE_FAILED",
                "LLM quota reservation and concurrency lease release failed",
            ) from exc


def stable_provider_call_id(context: AgentContext, module_key: str, stage: str, call_index: int) -> str:
    normalized_module = _required_text(module_key, "module_key")
    normalized_stage = _required_text(stage, "stage")
    if call_index < 0:
        raise LLMFacilityError("VALIDATION_FAILED", "provider call index must be non-negative")
    project_id = _required_text(context.project_id, "project_id")
    canonical = "\x1f".join(
        (
            _required_text(context.tenant_id, "tenant_id"),
            project_id,
            _required_text(context.run_id, "run_id"),
            normalized_module,
            normalized_stage,
            str(call_index),
        )
    )
    return "llm:" + hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def _request(
    *,
    context: AgentContext,
    resolution: ModuleBindingResolution,
    stage: str,
    call_index: int,
    input_texts: Sequence[str],
    output_token_upper_bound: int | None,
) -> ProviderCallRequest:
    project_id = _required_text(context.project_id, "project_id")
    module_key = _required_text(resolution.module_key, "module_key")
    if resolution.tenant_id.strip() != context.tenant_id.strip():
        raise LLMFacilityError("VALIDATION_FAILED", "LLM binding tenant scope does not match provider call context")
    if resolution.project_id is not None and resolution.project_id.strip() != project_id:
        raise LLMFacilityError("VALIDATION_FAILED", "LLM binding project scope does not match provider call context")
    if context.module_key is not None and context.module_key != module_key:
        raise LLMFacilityError("VALIDATION_FAILED", "LLM module scope does not match provider call context")
    if call_index < 0:
        raise LLMFacilityError("VALIDATION_FAILED", "provider call index must be non-negative")
    input_upper_bound = 0
    for value in input_texts:
        if not isinstance(value, str):
            raise LLMFacilityError("VALIDATION_FAILED", "provider input must be text")
        input_upper_bound += len(value.encode("utf-8"))
    module_max_concurrency = _optional_positive_int(resolution.settings.get("max_concurrency"))
    return ProviderCallRequest(
        tenant_id=_required_text(context.tenant_id, "tenant_id"),
        project_id=project_id,
        run_id=_required_text(context.run_id, "run_id"),
        actor_user_id=context.actor_user_id,
        trace_id=_required_text(context.trace_id, "trace_id"),
        workflow_type=_required_text(context.workflow_type, "workflow_type"),
        module_key=module_key,
        channel_id=_required_text(resolution.channel_id, "channel_id"),
        model_id=_required_text(resolution.model_id, "model_id"),
        provider_call_id=stable_provider_call_id(context, module_key, stage, call_index),
        stage=_required_text(stage, "stage"),
        call_index=call_index,
        input_token_upper_bound=input_upper_bound,
        output_token_upper_bound=output_token_upper_bound,
        module_max_concurrency=module_max_concurrency,
    )


def _provider_usage(response: dict[str, Any]) -> ProviderUsage:
    raw = response.get("__llm_usage")
    if not isinstance(raw, dict):
        raise LLMFacilityError("LLM_PROVIDER_USAGE_MISSING", "LLM provider did not return valid usage")
    prompt = _non_negative_int(raw.get("prompt_tokens") if "prompt_tokens" in raw else raw.get("input_tokens"))
    completion = _non_negative_int(
        raw.get("completion_tokens") if "completion_tokens" in raw else raw.get("output_tokens")
    )
    if prompt is None or completion is None:
        total = _non_negative_int(raw.get("total_tokens"))
        if prompt is not None and completion is None and total is not None and total >= prompt:
            completion = total - prompt
        elif completion is not None and prompt is None and total is not None and total >= completion:
            prompt = total - completion
    if prompt is None or completion is None:
        raise LLMFacilityError("LLM_PROVIDER_USAGE_MISSING", "LLM provider did not return valid usage")
    return ProviderUsage(prompt_tokens=prompt, completion_tokens=completion)


def _required_text(value: Any, field_name: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise LLMFacilityError("VALIDATION_FAILED", f"{field_name} is required")
    return value.strip()


def _optional_positive_int(value: Any) -> int | None:
    if isinstance(value, bool) or not isinstance(value, int) or value <= 0:
        return None
    return value


def _non_negative_int(value: Any) -> int | None:
    if isinstance(value, bool):
        return None
    if isinstance(value, int) and value >= 0:
        return value
    if isinstance(value, float) and value >= 0 and value.is_integer():
        return int(value)
    return None
