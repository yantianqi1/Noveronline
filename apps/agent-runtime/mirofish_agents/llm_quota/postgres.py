from __future__ import annotations

import json
import os
import re
import uuid
from dataclasses import dataclass
from decimal import Decimal, InvalidOperation, ROUND_CEILING
from typing import Any, Callable

from mirofish_agents.seed.sequential_reader import LLMFacilityError

from .models import ProviderCallAdmission, ProviderCallRequest, ProviderUsage


_MAX_INT64 = (1 << 63) - 1
_DEFAULT_TTL_SECONDS = 900
_ERROR_CODE = re.compile(r"^[A-Z][A-Z0-9_]{2,80}$")
_PRIVATE_DROP = object()
_SENSITIVE_REPLAY_KEYS = {
    "accesstoken",
    "apikey",
    "authorization",
    "credential",
    "credentialref",
    "encryptedapikey",
    "password",
    "refreshtoken",
    "secret",
}
_MODULE_RESOURCE_NAMESPACE = uuid.UUID("d84ddf36-75cd-4e8f-ab28-a29d46cd908f")
_OWNER_NAMESPACE = uuid.UUID("0f3d1c90-5236-43f6-8f48-ea402f524ffc")
# Marker reservation_id: matching released/expired rows may be reopened for the same provider_call_id.
_REOPEN_SENTINEL = "__reopen__"


@dataclass(frozen=True)
class _Policy:
    policy_id: str
    scope_type: str
    project_id: str
    module_key: str
    token_limit: int | None
    cost_limit_micros: int | None
    concurrency_limit: int | None
    period_seconds: int


@dataclass(frozen=True)
class _ModelBudget:
    context_window: int | None
    input_rate: Decimal | None
    output_rate: Decimal | None
    channel_max_concurrency: int


class PostgresQuotaStore:
    def __init__(self, *, connect: Callable[[], Any], ttl_seconds: int = _DEFAULT_TTL_SECONDS) -> None:
        if isinstance(ttl_seconds, bool) or not isinstance(ttl_seconds, int) or ttl_seconds <= 0:
            raise LLMFacilityError("LLM_QUOTA_CONFIG_INVALID", "LLM quota TTL must be a positive integer")
        self._connect = connect
        self._ttl_seconds = ttl_seconds

    @classmethod
    def from_database_url(cls, database_url: str, *, ttl_seconds: int | None = None) -> "PostgresQuotaStore":
        try:
            import psycopg
        except ImportError as exc:  # pragma: no cover - runtime packaging boundary
            raise RuntimeError("psycopg is required for PostgreSQL LLM quota enforcement") from exc
        configured_ttl = ttl_seconds if ttl_seconds is not None else _ttl_seconds_from_env()
        return cls(connect=lambda: psycopg.connect(database_url), ttl_seconds=configured_ttl)

    def admit(self, request: ProviderCallRequest) -> ProviderCallAdmission:
        _validate_request(request)
        connection = self._connect()
        try:
            with connection.cursor() as cursor:
                _set_tenant_context(cursor, request)
                cursor.execute(
                    """UPDATE llm_quota_reservations
                       SET status = 'expired', updated_at = now()
                       WHERE tenant_id = %s AND status = 'reserved' AND expires_at <= now()""",
                    (request.tenant_id,),
                )
                policies = _load_policies(cursor, request)
                if not policies:
                    raise LLMFacilityError("LLM_QUOTA_POLICY_UNAVAILABLE", "LLM quota policy is unavailable")
                _lock_policy_scopes(cursor, request, policies)
                model = _load_model_budget(cursor, request)
                reserved_tokens = _reserved_tokens(request, model)
                reserved_cost = _reserved_cost(request, model, policies)
                existing = _existing_reservation(
                    cursor,
                    request,
                    reserved_tokens=reserved_tokens,
                    reserved_cost_micros=reserved_cost,
                )
                if existing is not None and existing.replay_payload is not None:
                    connection.commit()
                    return existing
                if existing is None or existing.reservation_id == _REOPEN_SENTINEL:
                    for policy in policies:
                        _check_policy_capacity(
                            cursor,
                            request,
                            policy,
                            reserved_tokens=reserved_tokens,
                            reserved_cost_micros=reserved_cost,
                        )
                    if existing is not None and existing.reservation_id == _REOPEN_SENTINEL:
                        reservation_id = _reopen_reservation(
                            cursor,
                            request,
                            reserved_tokens=reserved_tokens,
                            reserved_cost_micros=reserved_cost,
                            ttl_seconds=self._ttl_seconds,
                        )
                    else:
                        reservation_id = _insert_reservation(
                            cursor,
                            request,
                            reserved_tokens=reserved_tokens,
                            reserved_cost_micros=reserved_cost,
                            ttl_seconds=self._ttl_seconds,
                        )
                else:
                    reservation_id = existing.reservation_id
                lock_ids = _acquire_concurrency_locks(
                    cursor,
                    request,
                    channel_limit=model.channel_max_concurrency,
                    ttl_seconds=self._ttl_seconds,
                )
            connection.commit()
            return ProviderCallAdmission(
                reservation_id=reservation_id,
                provider_call_id=request.provider_call_id,
                reserved_tokens=reserved_tokens,
                reserved_cost_micros=reserved_cost,
                lock_ids=lock_ids,
                input_cost_micros_per_token=model.input_rate,
                output_cost_micros_per_token=model.output_rate,
            )
        except LLMFacilityError:
            _rollback_quietly(connection)
            raise
        except Exception as exc:
            _rollback_quietly(connection)
            raise LLMFacilityError("LLM_QUOTA_BACKEND_FAILED", "LLM quota backend failed") from exc
        finally:
            connection.close()

    def finalize(
        self,
        request: ProviderCallRequest,
        admission: ProviderCallAdmission,
        usage: ProviderUsage,
        response_payload: dict[str, Any],
    ) -> None:
        _validate_request(request)
        _validate_admission(request, admission)
        actual_tokens = _checked_sum(usage.prompt_tokens, usage.completion_tokens, "LLM usage tokens")
        if actual_tokens > admission.reserved_tokens:
            raise LLMFacilityError("LLM_USAGE_EXCEEDS_RESERVATION", "LLM provider usage exceeded its reservation")
        actual_cost = _actual_cost(admission, usage)
        if actual_cost is not None and actual_cost > admission.reserved_cost_micros:
            raise LLMFacilityError("LLM_USAGE_EXCEEDS_RESERVATION", "LLM provider cost exceeded its reservation")
        private_payload = _json_payload(response_payload)
        # Return the same sanitized shape that a Temporal replay will load.
        # Mutating the caller-owned response keeps first execution and replay
        # deterministic without persisting credential-like fields.
        response_payload.clear()
        response_payload.update(private_payload)
        connection = self._connect()
        try:
            with connection.cursor() as cursor:
                _set_tenant_context(cursor, request)
                status = _lock_reservation(cursor, request, admission)
                if status == "finalized":
                    connection.commit()
                    return
                if status != "reserved":
                    raise LLMFacilityError("LLM_QUOTA_RESERVATION_CLOSED", "LLM quota reservation is closed")
                _write_private_replay(cursor, request, private_payload)
                cursor.execute(
                    """UPDATE llm_quota_reservations
                       SET status = 'finalized', actual_prompt_tokens = %s,
                           actual_completion_tokens = %s, actual_cost_micros = %s,
                           finalized_at = now(), updated_at = now()
                       WHERE tenant_id = %s AND reservation_id = %s""",
                    (
                        usage.prompt_tokens,
                        usage.completion_tokens,
                        actual_cost,
                        request.tenant_id,
                        admission.reservation_id,
                    ),
                )
                _write_usage(cursor, request, usage, actual_cost)
                _write_activity(cursor, request, usage=usage, actual_cost=actual_cost, status="completed", error_code=None)
                _delete_locks(cursor, request, admission.lock_ids)
            connection.commit()
        except LLMFacilityError:
            _rollback_quietly(connection)
            raise
        except Exception as exc:
            _rollback_quietly(connection)
            raise LLMFacilityError("LLM_TELEMETRY_WRITE_FAILED", "LLM telemetry write failed") from exc
        finally:
            connection.close()

    def fail(self, request: ProviderCallRequest, admission: ProviderCallAdmission, error_code: str) -> None:
        _validate_request(request)
        _validate_admission(request, admission)
        stable_code = error_code if isinstance(error_code, str) and _ERROR_CODE.fullmatch(error_code) else "LLM_PROVIDER_ERROR"
        connection = self._connect()
        try:
            with connection.cursor() as cursor:
                _set_tenant_context(cursor, request)
                status = _lock_reservation(cursor, request, admission)
                if status == "finalized":
                    _delete_locks(cursor, request, admission.lock_ids)
                    connection.commit()
                    return
                if status not in {"reserved", "released"}:
                    raise LLMFacilityError("LLM_QUOTA_RESERVATION_CLOSED", "LLM quota reservation is closed")
                if status == "reserved":
                    cursor.execute(
                        """UPDATE llm_quota_reservations SET status = 'released', updated_at = now()
                           WHERE tenant_id = %s AND reservation_id = %s AND status = 'reserved'""",
                        (request.tenant_id, admission.reservation_id),
                    )
                _write_activity(cursor, request, usage=None, actual_cost=None, status="failed", error_code=stable_code)
                _delete_locks(cursor, request, admission.lock_ids)
            connection.commit()
        except LLMFacilityError:
            _rollback_quietly(connection)
            raise
        except Exception as exc:
            _rollback_quietly(connection)
            raise LLMFacilityError("LLM_QUOTA_RELEASE_FAILED", "LLM quota reservation release failed") from exc
        finally:
            connection.close()


def _load_policies(cursor: Any, request: ProviderCallRequest) -> list[_Policy]:
    cursor.execute(
        """SELECT policy_id::text, scope_type, COALESCE(project_id::text, ''),
                  COALESCE(module_key, ''), token_limit, cost_limit_micros,
                  concurrency_limit, period_seconds
           FROM llm_quota_policies
           WHERE tenant_id = %s AND enabled AND (
             scope_type = 'tenant' OR
             (scope_type = 'project' AND project_id = %s) OR
             (scope_type = 'module' AND project_id = %s AND module_key = %s)
           )
           ORDER BY CASE scope_type WHEN 'module' THEN 1 WHEN 'project' THEN 2 ELSE 3 END""",
        (request.tenant_id, request.project_id, request.project_id, request.module_key),
    )
    policies: list[_Policy] = []
    for row in cursor.fetchall():
        policies.append(
            _Policy(
                policy_id=str(row[0]),
                scope_type=str(row[1]),
                project_id=str(row[2] or ""),
                module_key=str(row[3] or ""),
                token_limit=_nullable_int(row[4]),
                cost_limit_micros=_nullable_int(row[5]),
                concurrency_limit=_nullable_int(row[6]),
                period_seconds=int(row[7]),
            )
        )
    return policies


def _lock_policy_scopes(cursor: Any, request: ProviderCallRequest, policies: list[_Policy]) -> None:
    keys = sorted(
        f"{request.tenant_id}:{policy.scope_type}:{policy.project_id}:{policy.module_key}"
        for policy in policies
    )
    for key in keys:
        cursor.execute("SELECT pg_advisory_xact_lock(hashtextextended(%s, 0))", (key,))


def _load_model_budget(cursor: Any, request: ProviderCallRequest) -> _ModelBudget:
    cursor.execute(
        """SELECT model.context_window, model.input_cost, model.output_cost, channel.max_concurrency
           FROM llm_channels channel
           LEFT JOIN llm_models model
             ON model.channel_id = channel.channel_id AND model.model_id = %s
           WHERE channel.channel_id = %s AND channel.enabled
             AND (channel.tenant_id = %s OR channel.tenant_id IS NULL)
           ORDER BY channel.tenant_id NULLS LAST
           LIMIT 1""",
        (request.model_id, request.channel_id, request.tenant_id),
    )
    row = cursor.fetchone()
    if row is None:
        raise LLMFacilityError("LLM_CHANNEL_UNAVAILABLE", "LLM channel is unavailable")
    channel_limit = _nullable_int(row[3])
    if channel_limit is None or channel_limit <= 0:
        raise LLMFacilityError("LLM_CHANNEL_UNAVAILABLE", "LLM channel concurrency is unavailable")
    return _ModelBudget(
        context_window=_nullable_int(row[0]),
        input_rate=_nullable_decimal(row[1]),
        output_rate=_nullable_decimal(row[2]),
        channel_max_concurrency=channel_limit,
    )


def _reserved_tokens(request: ProviderCallRequest, model: _ModelBudget) -> int:
    output = request.output_token_upper_bound
    if output is None:
        if model.context_window is None or model.context_window <= 0:
            raise LLMFacilityError(
                "LLM_QUOTA_RESERVATION_UNAVAILABLE",
                "LLM output token reservation requires max_tokens or model context_window",
            )
        output = max(0, model.context_window - request.input_token_upper_bound)
    return _checked_sum(request.input_token_upper_bound, output, "LLM token reservation")


def _reserved_cost(request: ProviderCallRequest, model: _ModelBudget, policies: list[_Policy]) -> int:
    cost_required = any(policy.cost_limit_micros is not None for policy in policies)
    if model.input_rate is None or (request.output_token_upper_bound != 0 and model.output_rate is None):
        if cost_required:
            raise LLMFacilityError("LLM_MODEL_PRICING_UNAVAILABLE", "LLM model pricing is unavailable")
        return 0
    output = request.output_token_upper_bound
    if output is None:
        if model.context_window is None:
            raise LLMFacilityError("LLM_QUOTA_RESERVATION_UNAVAILABLE", "LLM token reservation is unavailable")
        output = max(0, model.context_window - request.input_token_upper_bound)
    return _cost_micros(request.input_token_upper_bound, output, model.input_rate, model.output_rate or Decimal(0))


def _existing_reservation(
    cursor: Any,
    request: ProviderCallRequest,
    *,
    reserved_tokens: int,
    reserved_cost_micros: int,
) -> ProviderCallAdmission | None:
    cursor.execute(
        """SELECT reservation_id::text, project_id::text, COALESCE(run_id::text, ''),
                  module_key, channel_id::text, model_id, reserved_tokens,
                  reserved_cost_micros, status
           FROM llm_quota_reservations
           WHERE tenant_id = %s AND provider_call_id = %s
           FOR UPDATE""",
        (request.tenant_id, request.provider_call_id),
    )
    row = cursor.fetchone()
    if row is None:
        return None
    matches = (
        str(row[1]) == request.project_id
        and str(row[2]) == request.run_id
        and str(row[3]) == request.module_key
        and str(row[4]) == request.channel_id
        and str(row[5]) == request.model_id
        and int(row[6]) == reserved_tokens
        and int(row[7]) == reserved_cost_micros
    )
    status = str(row[8])
    if status == "finalized" and matches:
        payload = _load_private_replay(cursor, request)
        return ProviderCallAdmission(
            reservation_id=str(row[0]),
            provider_call_id=request.provider_call_id,
            reserved_tokens=reserved_tokens,
            reserved_cost_micros=reserved_cost_micros,
            lock_ids=(),
            replay_payload=payload,
        )
    if status in {"released", "expired"} or not matches:
        # Stable provider_call_id is reused across Temporal retries and operator
        # re-runs of the same run_id. Prior released/expired rows, or rows left
        # after the operator rebound a different channel/model/budget, must be
        # reopened instead of hard-failing with CALL_CONFLICT.
        return ProviderCallAdmission(
            reservation_id=_REOPEN_SENTINEL,
            provider_call_id=request.provider_call_id,
            reserved_tokens=reserved_tokens,
            reserved_cost_micros=reserved_cost_micros,
            lock_ids=(),
        )
    if status != "reserved":
        raise LLMFacilityError("LLM_QUOTA_RESERVATION_CLOSED", "LLM quota reservation is closed")
    return ProviderCallAdmission(
        reservation_id=str(row[0]),
        provider_call_id=request.provider_call_id,
        reserved_tokens=reserved_tokens,
        reserved_cost_micros=reserved_cost_micros,
        lock_ids=(),
    )


def _reopen_reservation(
    cursor: Any,
    request: ProviderCallRequest,
    *,
    reserved_tokens: int,
    reserved_cost_micros: int,
    ttl_seconds: int,
) -> str:
    cursor.execute(
        """UPDATE llm_quota_reservations
           SET project_id = %s,
               run_id = %s,
               module_key = %s,
               channel_id = %s,
               model_id = %s,
               reserved_tokens = %s,
               reserved_cost_micros = %s,
               status = 'reserved',
               expires_at = now() + (%s * interval '1 second'),
               actual_prompt_tokens = NULL,
               actual_completion_tokens = NULL,
               actual_cost_micros = NULL,
               finalized_at = NULL,
               updated_at = now()
           WHERE tenant_id = %s
             AND provider_call_id = %s
             AND status IN ('released', 'expired', 'reserved', 'finalized')
           RETURNING reservation_id::text""",
        (
            request.project_id,
            request.run_id,
            request.module_key,
            request.channel_id,
            request.model_id,
            reserved_tokens,
            reserved_cost_micros,
            ttl_seconds,
            request.tenant_id,
            request.provider_call_id,
        ),
    )
    row = cursor.fetchone()
    if row is None:
        raise LLMFacilityError("LLM_QUOTA_RESERVE_FAILED", "LLM quota reservation failed")
    return str(row[0])


def _check_policy_capacity(
    cursor: Any,
    request: ProviderCallRequest,
    policy: _Policy,
    *,
    reserved_tokens: int,
    reserved_cost_micros: int,
) -> None:
    scope_filter = ""
    if policy.scope_type in {"project", "module"}:
        scope_filter += " AND project_id = %(project_id)s"
    if policy.scope_type == "module":
        scope_filter += " AND module_key = %(module_key)s"
    cursor.execute(
        f"""SELECT
          COALESCE((SELECT SUM(quantity)::bigint FROM usage_events
            WHERE tenant_id = %(tenant_id)s AND usage_type = 'llm_tokens'
              AND created_at >= now() - (%(period_seconds)s * interval '1 second') {scope_filter}), 0),
          COALESCE((SELECT SUM(quantity)::bigint FROM usage_events
            WHERE tenant_id = %(tenant_id)s AND usage_type = 'llm_cost_micros'
              AND created_at >= now() - (%(period_seconds)s * interval '1 second') {scope_filter}), 0),
          COALESCE((SELECT SUM(reserved_tokens)::bigint FROM llm_quota_reservations
            WHERE tenant_id = %(tenant_id)s AND status = 'reserved' AND expires_at > now() {scope_filter}), 0),
          COALESCE((SELECT SUM(reserved_cost_micros)::bigint FROM llm_quota_reservations
            WHERE tenant_id = %(tenant_id)s AND status = 'reserved' AND expires_at > now() {scope_filter}), 0),
          COALESCE((SELECT COUNT(*)::int FROM llm_quota_reservations
            WHERE tenant_id = %(tenant_id)s AND status = 'reserved' AND expires_at > now() {scope_filter}), 0)""",
        {
            "tenant_id": request.tenant_id,
            "project_id": request.project_id,
            "module_key": request.module_key,
            "period_seconds": policy.period_seconds,
        },
    )
    row = cursor.fetchone()
    if row is None:
        raise LLMFacilityError("LLM_QUOTA_BACKEND_FAILED", "LLM quota backend failed")
    used_tokens, used_cost, active_tokens, active_cost, active_calls = (int(value) for value in row)
    if policy.token_limit is not None and _exceeds(policy.token_limit, used_tokens, active_tokens, reserved_tokens):
        raise LLMFacilityError("LLM_QUOTA_TOKENS_EXCEEDED", "LLM token quota exceeded")
    if policy.cost_limit_micros is not None and _exceeds(
        policy.cost_limit_micros, used_cost, active_cost, reserved_cost_micros
    ):
        raise LLMFacilityError("LLM_QUOTA_COST_EXCEEDED", "LLM cost quota exceeded")
    if policy.concurrency_limit is not None and active_calls >= policy.concurrency_limit:
        raise LLMFacilityError("LLM_QUOTA_CONCURRENCY_EXCEEDED", "LLM quota concurrency limit reached")


def _insert_reservation(
    cursor: Any,
    request: ProviderCallRequest,
    *,
    reserved_tokens: int,
    reserved_cost_micros: int,
    ttl_seconds: int,
) -> str:
    cursor.execute(
        """INSERT INTO llm_quota_reservations (
             tenant_id, provider_call_id, project_id, run_id, module_key, channel_id,
             model_id, reserved_tokens, reserved_cost_micros, expires_at
           ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s,
                     now() + (%s * interval '1 second'))
           RETURNING reservation_id::text""",
        (
            request.tenant_id,
            request.provider_call_id,
            request.project_id,
            request.run_id,
            request.module_key,
            request.channel_id,
            request.model_id,
            reserved_tokens,
            reserved_cost_micros,
            ttl_seconds,
        ),
    )
    row = cursor.fetchone()
    if row is None:
        raise LLMFacilityError("LLM_QUOTA_RESERVE_FAILED", "LLM quota reservation failed")
    return str(row[0])


def _acquire_concurrency_locks(
    cursor: Any,
    request: ProviderCallRequest,
    *,
    channel_limit: int,
    ttl_seconds: int,
) -> tuple[str, ...]:
    owner_id = str(uuid.uuid5(_OWNER_NAMESPACE, request.provider_call_id))
    locks = [
        _acquire_slot(
            cursor,
            request,
            resource_type="llm_channel",
            resource_id=request.channel_id,
            owner_id=owner_id,
            capacity=channel_limit,
            ttl_seconds=ttl_seconds,
        )
    ]
    if request.module_max_concurrency is not None:
        try:
            locks.append(
                _acquire_slot(
                    cursor,
                    request,
                    resource_type="llm_module",
                    resource_id=str(
                        uuid.uuid5(
                            _MODULE_RESOURCE_NAMESPACE,
                            f"{request.tenant_id}:{request.project_id}:{request.module_key}",
                        )
                    ),
                    owner_id=owner_id,
                    capacity=request.module_max_concurrency,
                    ttl_seconds=ttl_seconds,
                )
            )
        except Exception:
            _delete_locks(cursor, request, tuple(locks))
            raise
    return tuple(locks)


def _acquire_slot(
    cursor: Any,
    request: ProviderCallRequest,
    *,
    resource_type: str,
    resource_id: str,
    owner_id: str,
    capacity: int,
    ttl_seconds: int,
) -> str:
    cursor.execute(
        """DELETE FROM resource_locks
           WHERE tenant_id = %s AND resource_type = %s AND resource_id = %s
             AND expires_at <= now()""",
        (request.tenant_id, resource_type, resource_id),
    )
    cursor.execute(
        """SELECT lock_id::text FROM resource_locks
           WHERE tenant_id = %s AND resource_type = %s AND resource_id = %s
             AND owner_run_id = %s AND expires_at > now()
           LIMIT 1""",
        (request.tenant_id, resource_type, resource_id, owner_id),
    )
    existing = cursor.fetchone()
    if existing is not None:
        cursor.execute(
            """UPDATE resource_locks SET expires_at = now() + (%s * interval '1 second'), updated_at = now()
               WHERE tenant_id = %s AND lock_id = %s""",
            (ttl_seconds, request.tenant_id, str(existing[0])),
        )
        return str(existing[0])
    for slot in range(capacity):
        cursor.execute(
            """INSERT INTO resource_locks (
                 tenant_id, resource_type, resource_id, owner_run_id, lock_mode, expires_at
               ) VALUES (%s, %s, %s, %s, %s, now() + (%s * interval '1 second'))
               ON CONFLICT (tenant_id, resource_type, resource_id, lock_mode) DO NOTHING
               RETURNING lock_id::text""",
            (request.tenant_id, resource_type, resource_id, owner_id, f"slot:{slot}", ttl_seconds),
        )
        row = cursor.fetchone()
        if row is not None:
            return str(row[0])
    raise LLMFacilityError("LLM_CONCURRENCY_LIMITED", "LLM concurrency limit reached")


def _lock_reservation(cursor: Any, request: ProviderCallRequest, admission: ProviderCallAdmission) -> str:
    cursor.execute(
        """SELECT status, provider_call_id FROM llm_quota_reservations
           WHERE tenant_id = %s AND reservation_id = %s FOR UPDATE""",
        (request.tenant_id, admission.reservation_id),
    )
    row = cursor.fetchone()
    if row is None:
        raise LLMFacilityError("LLM_QUOTA_RESERVATION_NOT_FOUND", "LLM quota reservation was not found")
    if str(row[1]) != request.provider_call_id:
        raise LLMFacilityError("LLM_PROVIDER_CALL_CONFLICT", "LLM provider call identity conflicts with its reservation")
    return str(row[0])


def _write_private_replay(cursor: Any, request: ProviderCallRequest, response_payload: dict[str, Any]) -> None:
    cursor.execute("SELECT pg_advisory_xact_lock(hashtextextended(%s, 0))", (f"trace:{request.tenant_id}:{request.trace_id}",))
    cursor.execute(
        """INSERT INTO agent_traces (
             tenant_id, trace_id, run_id, project_id, module_key, agent_name,
             status, started_at, completed_at
           ) VALUES (%s, %s, %s, %s, %s, 'llm_quota_gate', 'completed', now(), now())
           ON CONFLICT (tenant_id, trace_id) DO UPDATE SET
             status = 'completed', completed_at = now(), updated_at = now()""",
        (request.tenant_id, request.trace_id, request.run_id, request.project_id, request.module_key),
    )
    cursor.execute(
        """SELECT payload_jsonb FROM agent_trace_events
           WHERE tenant_id = %s AND trace_id = %s AND event_type = 'llm.provider.response'
             AND payload_jsonb->>'provider_call_id' = %s
           LIMIT 1""",
        (request.tenant_id, request.trace_id, request.provider_call_id),
    )
    if cursor.fetchone() is not None:
        return
    cursor.execute(
        "SELECT COALESCE(MAX(event_order), 0) + 1 FROM agent_trace_events WHERE tenant_id = %s AND trace_id = %s",
        (request.tenant_id, request.trace_id),
    )
    order_row = cursor.fetchone()
    event_order = int(order_row[0]) if order_row is not None else 1
    cursor.execute(
        """INSERT INTO agent_trace_events (
             tenant_id, trace_id, event_order, event_type, payload_jsonb, redaction_level
           ) VALUES (%s, %s, %s, 'llm.provider.response', %s::jsonb, 'full')""",
        (
            request.tenant_id,
            request.trace_id,
            event_order,
            json.dumps(
                {"provider_call_id": request.provider_call_id, "response": response_payload},
                ensure_ascii=False,
                separators=(",", ":"),
            ),
        ),
    )


def _load_private_replay(cursor: Any, request: ProviderCallRequest) -> dict[str, Any]:
    cursor.execute(
        """SELECT payload_jsonb FROM agent_trace_events
           WHERE tenant_id = %s AND trace_id = %s AND event_type = 'llm.provider.response'
             AND payload_jsonb->>'provider_call_id' = %s
           ORDER BY event_order DESC LIMIT 1""",
        (request.tenant_id, request.trace_id, request.provider_call_id),
    )
    row = cursor.fetchone()
    if row is None:
        raise LLMFacilityError("LLM_PROVIDER_REPLAY_UNAVAILABLE", "LLM provider replay payload is unavailable")
    payload = row[0]
    if isinstance(payload, str):
        try:
            payload = json.loads(payload)
        except json.JSONDecodeError as exc:
            raise LLMFacilityError("LLM_PROVIDER_REPLAY_UNAVAILABLE", "LLM provider replay payload is unavailable") from exc
    response = payload.get("response") if isinstance(payload, dict) else None
    if not isinstance(response, dict):
        raise LLMFacilityError("LLM_PROVIDER_REPLAY_UNAVAILABLE", "LLM provider replay payload is unavailable")
    return response


def _write_usage(cursor: Any, request: ProviderCallRequest, usage: ProviderUsage, actual_cost: int | None) -> None:
    metadata = json.dumps(
        {"provider_call_id": request.provider_call_id, "model_id": request.model_id},
        separators=(",", ":"),
    )
    cursor.execute(
        """INSERT INTO usage_events (
             tenant_id, project_id, run_id, module_key, usage_type, quantity, unit, metadata_jsonb
           ) VALUES (%s, %s, %s, %s, 'llm_tokens', %s, 'tokens', %s::jsonb)""",
        (request.tenant_id, request.project_id, request.run_id, request.module_key, usage.total_tokens, metadata),
    )
    if actual_cost is not None:
        cursor.execute(
            """INSERT INTO usage_events (
                 tenant_id, project_id, run_id, module_key, usage_type, quantity, unit, metadata_jsonb
               ) VALUES (%s, %s, %s, %s, 'llm_cost_micros', %s, 'micros', %s::jsonb)""",
            (request.tenant_id, request.project_id, request.run_id, request.module_key, actual_cost, metadata),
        )


def _write_activity(
    cursor: Any,
    request: ProviderCallRequest,
    *,
    usage: ProviderUsage | None,
    actual_cost: int | None,
    status: str,
    error_code: str | None,
) -> None:
    metadata: dict[str, Any] = {
        "provider_call_id": request.provider_call_id,
        "pricing_status": "available" if actual_cost is not None else "unavailable",
    }
    if error_code is not None:
        metadata["error_code"] = error_code
    cursor.execute(
        """INSERT INTO llm_activity (
             tenant_id, project_id, run_id, module_key, channel_id, model_id,
             status, prompt_tokens, completion_tokens, cost_estimate, error_jsonb
           ) SELECT %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s::jsonb
           WHERE NOT EXISTS (
             SELECT 1 FROM llm_activity
             WHERE tenant_id = %s AND project_id = %s AND run_id = %s AND module_key = %s
               AND status = %s AND error_jsonb->>'provider_call_id' = %s
           )""",
        (
            request.tenant_id,
            request.project_id,
            request.run_id,
            request.module_key,
            request.channel_id,
            request.model_id,
            status,
            usage.prompt_tokens if usage is not None else None,
            usage.completion_tokens if usage is not None else None,
            actual_cost,
            json.dumps(metadata, separators=(",", ":")),
            request.tenant_id,
            request.project_id,
            request.run_id,
            request.module_key,
            status,
            request.provider_call_id,
        ),
    )


def _delete_locks(cursor: Any, request: ProviderCallRequest, lock_ids: tuple[str, ...]) -> None:
    for lock_id in lock_ids:
        cursor.execute(
            "DELETE FROM resource_locks WHERE tenant_id = %s AND lock_id = %s",
            (request.tenant_id, lock_id),
        )


def _actual_cost(admission: ProviderCallAdmission, usage: ProviderUsage) -> int | None:
    if admission.input_cost_micros_per_token is None or admission.output_cost_micros_per_token is None:
        return None
    return _cost_micros(
        usage.prompt_tokens,
        usage.completion_tokens,
        admission.input_cost_micros_per_token,
        admission.output_cost_micros_per_token,
    )


def _cost_micros(input_tokens: int, output_tokens: int, input_rate: Decimal, output_rate: Decimal) -> int:
    if input_rate < 0 or output_rate < 0:
        raise LLMFacilityError("LLM_MODEL_PRICING_INVALID", "LLM model pricing is invalid")
    value = (Decimal(input_tokens) * input_rate) + (Decimal(output_tokens) * output_rate)
    rounded = int(value.to_integral_value(rounding=ROUND_CEILING))
    if rounded < 0 or rounded > _MAX_INT64:
        raise LLMFacilityError("LLM_MODEL_PRICING_INVALID", "LLM model pricing is invalid")
    return rounded


def _validate_request(request: ProviderCallRequest) -> None:
    for value in (request.tenant_id, request.project_id, request.run_id, request.channel_id):
        try:
            uuid.UUID(value)
        except (ValueError, AttributeError) as exc:
            raise LLMFacilityError("VALIDATION_FAILED", "LLM quota context contains an invalid identifier") from exc
    if not request.module_key.strip() or not request.model_id.strip() or not request.provider_call_id.strip():
        raise LLMFacilityError("VALIDATION_FAILED", "LLM quota context is incomplete")
    if request.input_token_upper_bound < 0 or (
        request.output_token_upper_bound is not None and request.output_token_upper_bound < 0
    ):
        raise LLMFacilityError("VALIDATION_FAILED", "LLM quota token reservation is invalid")


def _validate_admission(request: ProviderCallRequest, admission: ProviderCallAdmission) -> None:
    if admission.provider_call_id != request.provider_call_id or not admission.reservation_id:
        raise LLMFacilityError("LLM_PROVIDER_CALL_CONFLICT", "LLM provider call identity conflicts with its reservation")


def _set_tenant_context(cursor: Any, request: ProviderCallRequest) -> None:
    cursor.execute(
        "SELECT app_set_tenant_context(%s::uuid, NULLIF(%s, '')::uuid, false)",
        (request.tenant_id, request.actor_user_id or ""),
    )


def _checked_sum(left: int, right: int, label: str) -> int:
    if left < 0 or right < 0 or left > _MAX_INT64 - right:
        raise LLMFacilityError("LLM_USAGE_DATA_INVALID", f"{label} is invalid")
    return left + right


def _exceeds(limit: int, *values: int) -> bool:
    remaining = limit
    for value in values:
        if value < 0 or value > remaining:
            return True
        remaining -= value
    return False


def _nullable_int(value: Any) -> int | None:
    if value is None:
        return None
    if isinstance(value, bool):
        raise LLMFacilityError("LLM_QUOTA_BACKEND_FAILED", "LLM quota backend failed")
    return int(value)


def _nullable_decimal(value: Any) -> Decimal | None:
    if value is None:
        return None
    try:
        parsed = Decimal(str(value))
    except (InvalidOperation, ValueError) as exc:
        raise LLMFacilityError("LLM_MODEL_PRICING_INVALID", "LLM model pricing is invalid") from exc
    if not parsed.is_finite() or parsed < 0:
        raise LLMFacilityError("LLM_MODEL_PRICING_INVALID", "LLM model pricing is invalid")
    return parsed


def _json_payload(value: dict[str, Any]) -> dict[str, Any]:
    try:
        sanitized = _sanitize_private_replay(value)
        encoded = json.dumps(sanitized, ensure_ascii=False, allow_nan=False, separators=(",", ":"))
        decoded = json.loads(encoded)
    except (TypeError, ValueError, json.JSONDecodeError) as exc:
        raise LLMFacilityError("SCHEMA_VALIDATION_FAILED", "LLM provider response was not JSON serializable") from exc
    if not isinstance(decoded, dict):
        raise LLMFacilityError("SCHEMA_VALIDATION_FAILED", "LLM provider response must be an object")
    return decoded


def _sanitize_private_replay(value: Any) -> Any:
    if isinstance(value, dict):
        result: dict[str, Any] = {}
        for key, child in value.items():
            if not isinstance(key, str):
                continue
            normalized = re.sub(r"[^a-z0-9]", "", key.lower())
            if normalized in _SENSITIVE_REPLAY_KEYS or normalized.endswith("apikey"):
                continue
            cleaned = _sanitize_private_replay(child)
            if cleaned is not _PRIVATE_DROP:
                result[key] = cleaned
        return result
    if isinstance(value, list):
        return [cleaned for item in value if (cleaned := _sanitize_private_replay(item)) is not _PRIVATE_DROP]
    if isinstance(value, str):
        lowered = value.strip().lower()
        if lowered.startswith("sk-") or lowered.startswith("bearer "):
            return _PRIVATE_DROP
    return value


def _ttl_seconds_from_env() -> int:
    raw = os.environ.get("MIROFISH_LLM_QUOTA_TTL_SECONDS", "").strip()
    if not raw:
        return _DEFAULT_TTL_SECONDS
    try:
        value = int(raw)
    except ValueError as exc:
        raise LLMFacilityError("LLM_QUOTA_CONFIG_INVALID", "LLM quota TTL must be a positive integer") from exc
    if value <= 0:
        raise LLMFacilityError("LLM_QUOTA_CONFIG_INVALID", "LLM quota TTL must be a positive integer")
    return value


def _rollback_quietly(connection: Any) -> None:
    try:
        connection.rollback()
    except Exception:
        return
