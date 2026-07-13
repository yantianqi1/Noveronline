from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal
from typing import Any


@dataclass(frozen=True)
class ProviderCallRequest:
    tenant_id: str
    project_id: str
    run_id: str
    actor_user_id: str | None
    trace_id: str
    workflow_type: str
    module_key: str
    channel_id: str
    model_id: str
    provider_call_id: str
    stage: str
    call_index: int
    input_token_upper_bound: int
    output_token_upper_bound: int | None
    module_max_concurrency: int | None


@dataclass(frozen=True)
class ProviderCallAdmission:
    reservation_id: str
    provider_call_id: str
    reserved_tokens: int
    reserved_cost_micros: int
    lock_ids: tuple[str, ...]
    replay_payload: dict[str, Any] | None = None
    input_cost_micros_per_token: Decimal | None = None
    output_cost_micros_per_token: Decimal | None = None


@dataclass(frozen=True)
class ProviderUsage:
    prompt_tokens: int
    completion_tokens: int

    @property
    def total_tokens(self) -> int:
        return self.prompt_tokens + self.completion_tokens
