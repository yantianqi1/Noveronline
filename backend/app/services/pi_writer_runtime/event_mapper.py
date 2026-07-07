"""Map Pi SDK events to stable MiroFish writer workflow events."""

from __future__ import annotations

from typing import Any


_EVENT_TYPE_MAP = {
    "agent_start": "writer.run.started",
    "message_update": "writer.token",
    "tool_execution_start": "writer.tool.started",
    "tool_execution_end": "writer.tool.completed",
    "agent_end": "writer.run.completed",
    "error": "writer.run.failed",
    "abort": "writer.run.cancelled",
}


def map_pi_event(event: dict[str, Any], context: dict[str, str]) -> dict[str, Any]:
    """Translate a Pi event into the public writer event contract."""

    pi_type = event.get("type") or ""
    event_type = _EVENT_TYPE_MAP.get(pi_type, pi_type)
    payload = _payload_for_event(pi_type, event)
    return {
        "type": event_type,
        "tenant_id": context["tenant_id"],
        "project_id": context["project_id"],
        "run_id": context["run_id"],
        "payload": payload,
    }


def writer_event(event_type: str, context: dict[str, str], payload: dict[str, Any] | None = None) -> dict[str, Any]:
    return {
        "type": event_type,
        "tenant_id": context["tenant_id"],
        "project_id": context["project_id"],
        "run_id": context["run_id"],
        "payload": payload or {},
    }


def _payload_for_event(pi_type: str, event: dict[str, Any]) -> dict[str, Any]:
    if pi_type == "message_update":
        return {"token": event.get("textDelta") or event.get("delta") or event.get("text") or ""}
    if pi_type in {"tool_execution_start", "tool_execution_end"}:
        return {
            "tool_name": event.get("toolName") or event.get("tool_name") or event.get("name") or "",
            "args": event.get("args") or {},
            "result": event.get("result"),
            "is_error": bool(event.get("isError") or event.get("is_error")),
        }
    if pi_type in {"error", "abort"}:
        return {"message": event.get("message") or event.get("error") or ""}
    return {k: v for k, v in event.items() if k != "type"}
