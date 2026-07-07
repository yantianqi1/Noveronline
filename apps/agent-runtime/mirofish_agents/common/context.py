from __future__ import annotations

from typing import Any

from pydantic import BaseModel, ConfigDict, Field, field_validator


class AgentContext(BaseModel):
    """Required scope for every Python agent runtime call."""

    model_config = ConfigDict(frozen=True)

    tenant_id: str
    project_id: str | None = None
    run_id: str
    workflow_type: str
    actor_user_id: str | None = None
    module_key: str | None = None
    trace_id: str
    permissions: dict[str, Any] = Field(default_factory=dict)

    @field_validator("tenant_id", "run_id", "workflow_type", "trace_id")
    @classmethod
    def _required_id_must_not_be_blank(cls, value: str) -> str:
        value = value.strip()
        if not value:
            raise ValueError("required runtime context id cannot be blank")
        return value

    @field_validator("project_id", "actor_user_id", "module_key")
    @classmethod
    def _optional_id_must_not_be_blank(cls, value: str | None) -> str | None:
        if value is None:
            return None
        value = value.strip()
        if not value:
            raise ValueError("runtime context id cannot be blank")
        return value

    def has_permission(self, scope: str, action: str) -> bool:
        allowed = self.permissions.get(scope)
        return isinstance(allowed, list) and action in allowed

    def to_trace_payload(self) -> dict[str, str | None]:
        return {
            "tenant_id": self.tenant_id,
            "project_id": self.project_id,
            "run_id": self.run_id,
            "workflow_type": self.workflow_type,
            "actor_user_id": self.actor_user_id,
            "trace_id": self.trace_id,
            "module_key": self.module_key,
        }
