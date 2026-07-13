from __future__ import annotations

from datetime import timedelta
from typing import Any

from temporalio import activity, workflow

from mirofish_agents.common.context import AgentContext
from mirofish_agents.seed.sequential_reader import LLMFacilityError
from mirofish_agents.temporal.worldline import (
    WORLDLINE_AUTO_EVOLUTION_WORKFLOW_TYPE,
    WORLDLINE_STEP_MODULE_KEY,
    WorkflowEventWriter,
    WorkflowRunStatusWriter,
    WorldlineStepRunner,
    _sanitize_worldline_value,
    _workflow_event_writer_from_env,
    _workflow_status_writer_from_env,
    _worldline_step_runner_from_env,
)


WORLDLINE_AUTO_EVOLUTION_MODULE_KEY = WORLDLINE_STEP_MODULE_KEY
WORLDLINE_AUTO_EVOLUTION_WORLD_SCOPE = "current_world"
WORLDLINE_AUTO_EVOLUTION_MODE = "auto_evolution"
SAFE_AUTO_EVOLUTION_ERRORS = {
    "CURRENT_WORLD_REQUIRED": "worldline auto-evolution requires current_world scope",
    "FORBIDDEN": "worldline_director run permission is required",
    "LLM_CREDENTIAL_UNAVAILABLE": "worldline director credential is unavailable",
    "LLM_BINDING_QUERY_FAILED": "worldline director binding lookup failed",
    "LLM_CREDENTIAL_DECRYPTOR_UNAVAILABLE": "worldline director credential decryptor is unavailable",
    "LLM_CREDENTIAL_DECRYPT_FAILED": "worldline director credential decryption failed",
    "LLM_CREDENTIAL_KEY_INVALID": "worldline director credential key is invalid",
    "LLM_CREDENTIAL_KEY_UNCONFIGURED": "worldline director credential key is not configured",
    "LLM_CREDENTIAL_QUERY_FAILED": "worldline director credential lookup failed",
    "LLM_MODULE_CAPABILITY_MISSING": "worldline_director requires a JSON-capable model",
    "LLM_MODULE_UNBOUND": "worldline_director module is not bound",
    "LLM_PROVIDER_ERROR": "worldline provider call failed",
    "LLM_TELEMETRY_WRITE_FAILED": "worldline LLM telemetry write failed",
    "SCHEMA_VALIDATION_FAILED": "worldline provider response failed schema validation",
    "VALIDATION_FAILED": "worldline auto-evolution validation failed",
    "WORKFLOW_EVENT_WRITE_FAILED": "worldline auto-evolution workflow event write failed",
    "WORLDLINE_AUTO_EVOLUTION_NOT_ACTIVE": "worldline auto-evolution is not active for this session",
    "WORLDLINE_AUTO_EVOLUTION_INCOMPLETE": "worldline auto-evolution did not complete every requested step",
    "WORLDLINE_AUTO_EVOLUTION_STEP_FAILED": "worldline auto-evolution step failed",
    "WORLDLINE_CANDIDATE_EVENT_READ_FAILED": "worldline candidate event replay read failed",
    "WORLDLINE_CANDIDATE_EVENT_WRITE_FAILED": "worldline candidate event write failed",
    "WORLDLINE_SESSION_NOT_FOUND": "worldline session was not admitted for this tenant/project",
    "WORLDLINE_SOURCE_LOAD_FAILED": "worldline source load failed",
    "WORLDLINE_SOURCE_LOADER_UNCONFIGURED": "worldline source loader is not configured",
    "WORLDLINE_SOURCE_NOT_FOUND": "worldline sources were not found",
    "WORLDLINE_SOURCE_REF_INVALID": "worldline source references are invalid",
    "WORLDLINE_STEP_RUNNER_UNCONFIGURED": "worldline auto-evolution requires a configured director runtime",
    "WORLDLINE_STEP_STATE_INVALID": "worldline auto-evolution step returned invalid candidate state",
}


@activity.defn
def worldline_auto_evolution_step_activity(
    payload: dict[str, Any],
    step_runner: WorldlineStepRunner | None = None,
    workflow_event_writer: WorkflowEventWriter | None = None,
    workflow_status_writer: WorkflowRunStatusWriter | None = None,
) -> dict[str, Any]:
    context = AgentContext.model_validate(payload.get("context", payload))
    session_id = _required_text(payload.get("session_id"), "session_id")
    source_step_index = _integer_or_zero(payload.get("source_step_index"))
    max_steps = _integer_or_zero(payload.get("max_steps"))
    world_scope = _optional_text(payload.get("world_scope"))
    writers = _runtime_writers(workflow_event_writer, workflow_status_writer)
    validation_error = _validate_runtime_context(
        context=context,
        source_step_index=source_step_index,
        max_steps=max_steps,
        world_scope=world_scope,
    )
    if validation_error is not None:
        return _failed_result(
            context=context,
            session_id=session_id,
            source_step_index=source_step_index,
            max_steps=max_steps,
            code=validation_error[0],
            message=validation_error[1],
            workflow_event_writer=writers[0],
            workflow_status_writer=writers[1],
        )
    if step_runner is None:
        try:
            step_runner = _worldline_step_runner_from_env()
        except Exception:
            step_runner = None
    if step_runner is None:
        return _failed_result(
            context=context,
            session_id=session_id,
            source_step_index=source_step_index,
            max_steps=max_steps,
            code="WORLDLINE_STEP_RUNNER_UNCONFIGURED",
            message="worldline auto-evolution requires a configured director runtime",
            workflow_event_writer=writers[0],
            workflow_status_writer=writers[1],
        )
    options = payload.get("options") if isinstance(payload.get("options"), dict) else {}
    step_options = {
        **_sanitize_worldline_value(options),
        "source_step_index": source_step_index,
        "step_number": source_step_index,
        "max_steps": max_steps,
        "world_scope": WORLDLINE_AUTO_EVOLUTION_WORLD_SCOPE,
    }
    try:
        result = step_runner.run_step(
            context=context,
            session_id=session_id,
            mode=WORLDLINE_AUTO_EVOLUTION_MODE,
            options=step_options,
        )
    except LLMFacilityError as exc:
        return _failed_result(
            context=context,
            session_id=session_id,
            source_step_index=source_step_index,
            max_steps=max_steps,
            code=exc.code,
            message=exc.message,
            workflow_event_writer=writers[0],
            workflow_status_writer=writers[1],
        )
    except Exception:
        return _failed_result(
            context=context,
            session_id=session_id,
            source_step_index=source_step_index,
            max_steps=max_steps,
            code="WORLDLINE_AUTO_EVOLUTION_STEP_FAILED",
            message="worldline auto-evolution step failed",
            workflow_event_writer=writers[0],
            workflow_status_writer=writers[1],
        )
    if not isinstance(result, dict) or result.get("status") == "failed":
        error = result.get("error") if isinstance(result, dict) and isinstance(result.get("error"), dict) else {}
        return _failed_result(
            context=context,
            session_id=session_id,
            source_step_index=source_step_index,
            max_steps=max_steps,
            code=str(error.get("code") or "WORLDLINE_AUTO_EVOLUTION_STEP_FAILED"),
            message=str(error.get("message") or "worldline auto-evolution step failed"),
            workflow_event_writer=writers[0],
            workflow_status_writer=writers[1],
        )
    try:
        public_step = _public_step_result(result, source_step_index=source_step_index)
    except ValueError:
        return _failed_result(
            context=context,
            session_id=session_id,
            source_step_index=source_step_index,
            max_steps=max_steps,
            code="WORLDLINE_STEP_STATE_INVALID",
            message="worldline auto-evolution step returned invalid candidate state",
            workflow_event_writer=writers[0],
            workflow_status_writer=writers[1],
        )
    try:
        event_persisted = _write_event(
            writers[0],
            context=context,
            event_type="worldline.auto_evolution.step.completed",
            payload={
                "stage": "worldline_auto_evolution",
                "activity": "worldline_auto_evolution_step_activity",
                "status": "completed",
                "module_key": WORLDLINE_AUTO_EVOLUTION_MODULE_KEY,
                "session_id": session_id,
                "world_scope": WORLDLINE_AUTO_EVOLUTION_WORLD_SCOPE,
                "max_steps": max_steps,
                **public_step,
            },
        )
    except Exception:
        return _failed_result(
            context=context,
            session_id=session_id,
            source_step_index=source_step_index,
            max_steps=max_steps,
            code="WORKFLOW_EVENT_WRITE_FAILED",
            message="worldline auto-evolution workflow event write failed",
            workflow_event_writer=writers[0],
            workflow_status_writer=writers[1],
        )
    return {
        **_base_payload(context),
        "status": "completed",
        "stage": "worldline_auto_evolution",
        "session_id": session_id,
        "world_scope": WORLDLINE_AUTO_EVOLUTION_WORLD_SCOPE,
        "max_steps": max_steps,
        **public_step,
        "stage_event_persisted": event_persisted,
    }


@activity.defn
def worldline_auto_evolution_finalize_activity(
    payload: dict[str, Any],
    workflow_event_writer: WorkflowEventWriter | None = None,
    workflow_status_writer: WorkflowRunStatusWriter | None = None,
) -> dict[str, Any]:
    context = AgentContext.model_validate(payload.get("context", payload))
    session_id = _required_text(payload.get("session_id"), "session_id")
    max_steps = _positive_integer(payload.get("max_steps"), "max_steps")
    world_scope = _required_text(payload.get("world_scope"), "world_scope")
    writers = _runtime_writers(workflow_event_writer, workflow_status_writer)
    validation_error = _validate_runtime_context(
        context=context,
        source_step_index=max_steps,
        max_steps=max_steps,
        world_scope=world_scope,
    )
    if validation_error is not None:
        return _failed_result(
            context=context,
            session_id=session_id,
            source_step_index=None,
            max_steps=max_steps,
            code=validation_error[0],
            message=validation_error[1],
            workflow_event_writer=writers[0],
            workflow_status_writer=writers[1],
        )
    try:
        summary = _completion_summary(payload.get("step_results"), max_steps=max_steps)
    except ValueError:
        return _failed_result(
            context=context,
            session_id=session_id,
            source_step_index=None,
            max_steps=max_steps,
            code="WORLDLINE_AUTO_EVOLUTION_INCOMPLETE",
            message="worldline auto-evolution did not complete every requested step",
            workflow_event_writer=writers[0],
            workflow_status_writer=writers[1],
        )
    public_result = {
        "session_id": session_id,
        "mode": WORLDLINE_AUTO_EVOLUTION_MODE,
        "world_scope": WORLDLINE_AUTO_EVOLUTION_WORLD_SCOPE,
        "completed_steps": max_steps,
        "max_steps": max_steps,
        "candidate_event_count": summary["candidate_event_count"],
        "last_step": summary["last_step"],
    }
    try:
        event_persisted = _write_event(
            writers[0],
            context=context,
            event_type="worldline.auto_evolution.completed",
            payload={
                "stage": "worldline_auto_evolution",
                "activity": "worldline_auto_evolution_finalize_activity",
                "status": "completed",
                "module_key": WORLDLINE_AUTO_EVOLUTION_MODULE_KEY,
                **public_result,
            },
        )
    except Exception:
        return _finalization_failure(
            context=context,
            public_result=public_result,
            code="WORKFLOW_EVENT_WRITE_FAILED",
            message="worldline auto-evolution workflow event write failed",
            stage_event_persisted=False,
        )
    try:
        status_persisted = _mark_completed(writers[1], context=context, result=public_result)
    except Exception:
        return _finalization_failure(
            context=context,
            public_result=public_result,
            code="WORKFLOW_STATUS_WRITE_FAILED",
            message="worldline auto-evolution workflow status write failed",
            stage_event_persisted=event_persisted,
        )
    return {
        **_base_payload(context),
        "status": "completed",
        "stage": "worldline_auto_evolution",
        **public_result,
        "workflow_status_persisted": status_persisted,
        "stage_event_persisted": event_persisted,
    }


@workflow.defn
class WorldlineAutoEvolutionWorkflow:
    @workflow.run
    async def run(self, payload: dict[str, Any]) -> dict[str, Any]:
        max_steps = _workflow_max_steps(payload.get("max_steps"))
        if max_steps is None:
            invalid_payload = {**payload, "source_step_index": 0}
            return await workflow.execute_activity(
                worldline_auto_evolution_step_activity,
                invalid_payload,
                start_to_close_timeout=timedelta(minutes=20),
                schedule_to_close_timeout=timedelta(hours=2),
            )
        step_results: list[dict[str, Any]] = []
        for source_step_index in range(1, max_steps + 1):
            result = await workflow.execute_activity(
                worldline_auto_evolution_step_activity,
                {**payload, "source_step_index": source_step_index},
                start_to_close_timeout=timedelta(minutes=20),
                schedule_to_close_timeout=timedelta(hours=2),
            )
            if result.get("status") != "completed":
                return result
            step_results.append(result)
        return await workflow.execute_activity(
            worldline_auto_evolution_finalize_activity,
            {**payload, "step_results": step_results},
            start_to_close_timeout=timedelta(minutes=2),
            schedule_to_close_timeout=timedelta(minutes=10),
        )


def run_worldline_auto_evolution_workflow_locally(
    payload: dict[str, Any],
    *,
    step_runner: WorldlineStepRunner | None = None,
    workflow_event_writer: WorkflowEventWriter | None = None,
    workflow_status_writer: WorkflowRunStatusWriter | None = None,
) -> dict[str, Any]:
    max_steps = _workflow_max_steps(payload.get("max_steps"))
    if max_steps is None:
        return worldline_auto_evolution_step_activity(
            {**payload, "source_step_index": 0},
            step_runner=step_runner,
            workflow_event_writer=workflow_event_writer,
            workflow_status_writer=workflow_status_writer,
        )
    step_results: list[dict[str, Any]] = []
    for source_step_index in range(1, max_steps + 1):
        result = worldline_auto_evolution_step_activity(
            {**payload, "source_step_index": source_step_index},
            step_runner=step_runner,
            workflow_event_writer=workflow_event_writer,
            workflow_status_writer=workflow_status_writer,
        )
        if result.get("status") != "completed":
            return result
        step_results.append(result)
    return worldline_auto_evolution_finalize_activity(
        {**payload, "step_results": step_results},
        workflow_event_writer=workflow_event_writer,
        workflow_status_writer=workflow_status_writer,
    )


def _validate_runtime_context(
    *,
    context: AgentContext,
    source_step_index: int,
    max_steps: int,
    world_scope: str,
) -> tuple[str, str] | None:
    if context.workflow_type != WORLDLINE_AUTO_EVOLUTION_WORKFLOW_TYPE:
        return "VALIDATION_FAILED", f"workflow_type must be {WORLDLINE_AUTO_EVOLUTION_WORKFLOW_TYPE}"
    if context.module_key not in {None, WORLDLINE_AUTO_EVOLUTION_MODULE_KEY}:
        return "VALIDATION_FAILED", f"module_key must be {WORLDLINE_AUTO_EVOLUTION_MODULE_KEY}"
    if not context.has_permission(WORLDLINE_AUTO_EVOLUTION_MODULE_KEY, "run"):
        return "FORBIDDEN", "worldline_director run permission is required"
    if world_scope != WORLDLINE_AUTO_EVOLUTION_WORLD_SCOPE:
        return "CURRENT_WORLD_REQUIRED", "worldline auto-evolution requires current_world scope"
    if max_steps < 1:
        return "VALIDATION_FAILED", "max_steps must be a positive integer"
    if source_step_index < 1 or source_step_index > max_steps:
        return "VALIDATION_FAILED", "source_step_index must be within max_steps"
    return None


def _public_step_result(result: dict[str, Any], *, source_step_index: int) -> dict[str, Any]:
    candidate_count = _positive_integer(result.get("candidate_event_count"), "candidate_event_count")
    step = _positive_integer(result.get("step"), "step")
    public = {
        "source_step_index": source_step_index,
        "step": step,
        "candidate_event_count": candidate_count,
        "replayed": bool(result.get("replayed")),
    }
    model_id = result.get("model_id")
    if isinstance(model_id, str) and model_id.strip():
        public["model_id"] = model_id.strip()
    return public


def _completion_summary(value: Any, *, max_steps: int) -> dict[str, int]:
    if not isinstance(value, list) or len(value) != max_steps:
        raise ValueError("step_results must contain every requested step")
    candidate_count = 0
    last_step = 0
    for expected_index, result in enumerate(value, start=1):
        if not isinstance(result, dict) or result.get("status") != "completed":
            raise ValueError("step result was not completed")
        if result.get("source_step_index") != expected_index:
            raise ValueError("step result index is inconsistent")
        candidate_count += _positive_integer(result.get("candidate_event_count"), "candidate_event_count")
        last_step = _positive_integer(result.get("step"), "step")
    return {"candidate_event_count": candidate_count, "last_step": last_step}


def _failed_result(
    *,
    context: AgentContext,
    session_id: str,
    source_step_index: int | None,
    max_steps: int,
    code: str,
    message: str,
    workflow_event_writer: WorkflowEventWriter | None,
    workflow_status_writer: WorkflowRunStatusWriter | None,
) -> dict[str, Any]:
    code, message = _stable_failure(code, message)
    payload: dict[str, Any] = {
        "stage": "worldline_auto_evolution",
        "activity": "worldline_auto_evolution_step_activity",
        "status": "failed",
        "module_key": WORLDLINE_AUTO_EVOLUTION_MODULE_KEY,
        "session_id": session_id,
        "world_scope": WORLDLINE_AUTO_EVOLUTION_WORLD_SCOPE,
        "max_steps": max_steps,
        "error_code": code,
        "message": message,
    }
    event_type = "worldline.auto_evolution.failed"
    if source_step_index is not None and source_step_index > 0:
        payload["source_step_index"] = source_step_index
        event_type = "worldline.auto_evolution.step.failed"
    try:
        event_persisted = _write_event(
            workflow_event_writer,
            context=context,
            event_type=event_type,
            payload=payload,
        )
    except Exception:
        event_persisted = False
    try:
        status_persisted = _mark_failed(
            workflow_status_writer,
            context=context,
            session_id=session_id,
            code=code,
            message=message,
        )
    except Exception:
        status_persisted = False
    result = {
        **_base_payload(context),
        "status": "failed",
        "stage": "worldline_auto_evolution",
        "session_id": session_id,
        "world_scope": WORLDLINE_AUTO_EVOLUTION_WORLD_SCOPE,
        "max_steps": max_steps,
        "error": {"code": code, "message": message},
        "stage_event_persisted": event_persisted,
        "workflow_status_persisted": status_persisted,
    }
    if source_step_index is not None and source_step_index > 0:
        result["source_step_index"] = source_step_index
    return result


def _finalization_failure(
    *,
    context: AgentContext,
    public_result: dict[str, Any],
    code: str,
    message: str,
    stage_event_persisted: bool,
) -> dict[str, Any]:
    return {
        **_base_payload(context),
        "status": "failed",
        "stage": "worldline_auto_evolution",
        **public_result,
        "error": {"code": code, "message": message},
        "stage_event_persisted": stage_event_persisted,
        "workflow_status_persisted": False,
    }


def _runtime_writers(
    event_writer: WorkflowEventWriter | None,
    status_writer: WorkflowRunStatusWriter | None,
) -> tuple[WorkflowEventWriter | None, WorkflowRunStatusWriter | None]:
    if event_writer is None:
        try:
            event_writer = _workflow_event_writer_from_env()
        except Exception:
            event_writer = None
    if status_writer is None:
        try:
            status_writer = _workflow_status_writer_from_env()
        except Exception:
            status_writer = None
    return event_writer, status_writer


def _write_event(
    writer: WorkflowEventWriter | None,
    *,
    context: AgentContext,
    event_type: str,
    payload: dict[str, Any],
) -> bool:
    if writer is None:
        return False
    writer.write_event(
        tenant_id=context.tenant_id,
        project_id=context.project_id,
        run_id=context.run_id,
        event_type=event_type,
        payload=_sanitize_worldline_value(payload),
    )
    return True


def _mark_failed(
    writer: WorkflowRunStatusWriter | None,
    *,
    context: AgentContext,
    session_id: str,
    code: str,
    message: str,
) -> bool:
    if writer is None:
        return False
    writer.mark_failed(
        context=context,
        session_id=session_id,
        code=code,
        message=message,
    )
    return True


def _mark_completed(
    writer: WorkflowRunStatusWriter | None,
    *,
    context: AgentContext,
    result: dict[str, Any],
) -> bool:
    if writer is None:
        return False
    writer.mark_completed(context=context, result=result)
    return True


def _base_payload(context: AgentContext) -> dict[str, Any]:
    return {
        **context.to_trace_payload(),
        "workflow_type": WORLDLINE_AUTO_EVOLUTION_WORKFLOW_TYPE,
        "module_key": WORLDLINE_AUTO_EVOLUTION_MODULE_KEY,
    }


def _required_text(value: Any, field_name: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{field_name} is required")
    return value.strip()


def _positive_integer(value: Any, field_name: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value < 1:
        raise ValueError(f"{field_name} must be a positive integer")
    return value


def _integer_or_zero(value: Any) -> int:
    if isinstance(value, bool) or not isinstance(value, int):
        return 0
    return value


def _optional_text(value: Any) -> str:
    if not isinstance(value, str):
        return ""
    return value.strip()


def _workflow_max_steps(value: Any) -> int | None:
    if isinstance(value, bool) or not isinstance(value, int) or value < 1:
        return None
    return value


def _stable_failure(code: Any, message: Any) -> tuple[str, str]:
    normalized_code = code.strip() if isinstance(code, str) else ""
    safe_message = SAFE_AUTO_EVOLUTION_ERRORS.get(normalized_code)
    if safe_message is not None:
        return normalized_code, safe_message
    return "WORLDLINE_AUTO_EVOLUTION_STEP_FAILED", "worldline auto-evolution step failed"
