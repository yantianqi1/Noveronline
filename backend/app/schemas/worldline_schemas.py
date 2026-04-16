"""Pydantic request schemas for /api/worldline routes."""

from __future__ import annotations

from typing import Any

from ._base import AllowExtraBase, ProjectContextMixin


class CreateSessionRequest(ProjectContextMixin):
    label: str = ""
    variables: list[Any] = []
    focus_question: str | None = None
    branch_count: int | None = None
    archives: list[Any] | None = None
    archive_ids: list[str] | None = None
    entity_types: list[str] | None = None
    config: dict[str, Any] | None = None


class StepRequest(ProjectContextMixin):
    branch_id: str | None = None
    steps: int = 1
    evolution_intensity: str = "medium"
    custom_depth: int | None = None


class InjectVariableRequest(ProjectContextMixin):
    branch_id: str | None = None
    variable: str | dict[str, Any] | None = None
    name: str = ""
    description: str = ""
    impact_axis: str = ""


class AgentActionRequest(ProjectContextMixin):
    branch_id: str | None = None
    actor: str | None = None
    agent_id: str | None = None
    action: str = ""
    intent: str = ""
    target: str = ""


class AgentDialogueRequest(ProjectContextMixin):
    branch_id: str | None = None
    actor: str | None = None
    agent_id: str | None = None
    message: str = ""
    mode: str = "template"
    limit: int = 20


class AutoEvolveRequest(ProjectContextMixin):
    branch_ids: list[str] | None = None
    mode: str = ""
    goal_text: str = ""
    max_steps: int | None = None


class PrepareSessionRequest(ProjectContextMixin):
    label: str = ""
    variables: list[Any] | None = None
    focus_question: str | None = None
    archives: list[Any] | None = None
    archive_ids: list[str] | None = None
    entity_types: list[str] | None = None
    config: dict[str, Any] | None = None


class StartFromPrepareRequest(ProjectContextMixin):
    pass


class AdoptEventsRequest(ProjectContextMixin):
    event_ids: list[str] = []
    action: str = ""


class EditEventRequest(ProjectContextMixin):
    consequence: str = ""
