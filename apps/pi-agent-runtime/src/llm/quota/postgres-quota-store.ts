import type { PricingStatus } from "./provider-call.js";

export interface QuotaTenantContext {
  tenant_id: string;
  project_id?: string;
}

export interface QuotaQueryExecutor {
  query<T extends Record<string, unknown>>(
    text: string,
    values?: readonly unknown[],
    context?: QuotaTenantContext
  ): Promise<{ rows: T[] }>;
  transaction?<T>(
    context: QuotaTenantContext,
    work: (executor: QuotaQueryExecutor) => Promise<T>
  ): Promise<T>;
}

export interface ReserveQuotaRequest {
  tenant_id: string;
  project_id: string;
  run_id: string;
  module_key: string;
  channel_id: string;
  model_id: string;
  provider_call_id: string;
  reserved_tokens: number;
  reserved_cost_micros: number;
  pricing_status: PricingStatus;
  ttl_seconds: number;
}

export interface QuotaReservation {
  reservation_id: string;
  provider_call_id: string;
  status: "reserved" | "finalized";
  expires_at: string;
  actual_prompt_tokens?: number;
  actual_completion_tokens?: number;
  actual_cost_micros?: number;
}

export interface FinalizeQuotaRequest {
  tenant_id: string;
  project_id: string;
  reservation_id: string;
  provider_call_id: string;
  prompt_tokens: number;
  completion_tokens: number;
  actual_cost_micros?: number;
  pricing_status: PricingStatus;
}

export interface ReleaseQuotaRequest {
  tenant_id: string;
  project_id: string;
  reservation_id: string;
  provider_call_id: string;
}

export interface PiWriterQuotaStore {
  reserve(request: ReserveQuotaRequest): Promise<QuotaReservation>;
  finalize(request: FinalizeQuotaRequest): Promise<void>;
  release(request: ReleaseQuotaRequest): Promise<void>;
}

interface ReservationRow extends Record<string, unknown> {
  decision?: string;
  reservation_id?: string;
  provider_call_id?: string;
  status?: string;
  expires_at?: string | Date;
  actual_prompt_tokens?: number | string | null;
  actual_completion_tokens?: number | string | null;
  actual_cost_micros?: number | string | null;
}

export function createPostgresQuotaStore(db: QuotaQueryExecutor): PiWriterQuotaStore {
  return {
    reserve: async (request) => reserve(db, request),
    finalize: async (request) => finalize(db, request),
    release: async (request) => release(db, request)
  };
}

async function reserve(db: QuotaQueryExecutor, request: ReserveQuotaRequest): Promise<QuotaReservation> {
  validateReserveRequest(request);
  let rows: ReservationRow[];
  try {
    const run = async (executor: QuotaQueryExecutor) => executor.query<ReservationRow>(reserveSQL, [
      request.tenant_id,
      request.project_id,
      request.run_id,
      request.module_key,
      request.channel_id,
      request.model_id,
      request.provider_call_id,
      request.reserved_tokens,
      request.reserved_cost_micros,
      request.pricing_status === "billing_ready",
      request.ttl_seconds
    ], tenantContext(request));
    const result = db.transaction
      ? await db.transaction(tenantContext(request), async (executor) => {
        await executor.query("SELECT pg_advisory_xact_lock(hashtextextended($1::text || ':llm-quota', 0))", [request.tenant_id]);
        return run(executor);
      })
      : await run(db);
    rows = result.rows;
  } catch (error) {
    throw new Error("LLM_QUOTA_BACKEND_FAILED: LLM quota backend failed", { cause: error });
  }
  const row = rows[0];
  const decision = row?.decision;
  if (decision !== "reserved" && decision !== "replay_reserved" && decision !== "finalized") {
    throw reserveDecisionError(decision);
  }
  const status = requiredStatus(row?.status);
  return {
    reservation_id: requiredString(row?.reservation_id, "LLM_QUOTA_RESERVE_FAILED"),
    provider_call_id: requiredString(row?.provider_call_id, "LLM_QUOTA_RESERVE_FAILED"),
    status,
    expires_at: requiredTimestamp(row?.expires_at),
    ...optionalActualUsage(row)
  };
}

async function finalize(db: QuotaQueryExecutor, request: FinalizeQuotaRequest): Promise<void> {
  validateFinalizeRequest(request);
  let decision: string | undefined;
  try {
    const result = await db.query<{ decision?: string }>(finalizeSQL, [
      request.tenant_id,
      request.project_id,
      request.reservation_id,
      request.provider_call_id,
      request.prompt_tokens,
      request.completion_tokens,
      request.actual_cost_micros ?? null,
      request.pricing_status
    ], tenantContext(request));
    decision = result.rows[0]?.decision;
  } catch {
    throw quotaError("LLM_QUOTA_FINALIZE_FAILED", "LLM quota finalization failed");
  }
  if (decision !== "finalized" && decision !== "replay_finalized") {
    throw finalizeDecisionError(decision);
  }
}

async function release(db: QuotaQueryExecutor, request: ReleaseQuotaRequest): Promise<void> {
  validateReleaseRequest(request);
  let decision: string | undefined;
  try {
    const result = await db.query<{ decision?: string }>(releaseSQL, [
      request.tenant_id,
      request.project_id,
      request.reservation_id,
      request.provider_call_id
    ], tenantContext(request));
    decision = result.rows[0]?.decision;
  } catch {
    throw quotaError("LLM_QUOTA_BACKEND_FAILED", "LLM quota backend failed");
  }
  if (decision !== "released" && decision !== "replay_released") {
    throw releaseDecisionError(decision);
  }
}

const reserveSQL = `WITH expired AS MATERIALIZED (
  UPDATE llm_quota_reservations
     SET status = 'expired', updated_at = now()
   WHERE tenant_id = $1::uuid
     AND status = 'reserved'
     AND expires_at <= now()
  RETURNING reservation_id
), applicable AS MATERIALIZED (
  SELECT policy_id, scope_type, project_id, module_key, token_limit,
         cost_limit_micros, concurrency_limit, period_seconds
    FROM llm_quota_policies
   CROSS JOIN (SELECT COUNT(*) FROM expired) AS recovery_barrier
   WHERE tenant_id = $1::uuid
     AND enabled = TRUE
     AND (
       scope_type = 'tenant'
       OR (scope_type = 'project' AND project_id = $2::uuid)
       OR (scope_type = 'module' AND project_id = $2::uuid AND module_key = $4)
     )
), scope_locks AS MATERIALIZED (
  SELECT pg_advisory_xact_lock(hashtextextended(
           concat_ws(':', $1::text, scope_type, COALESCE(project_id::text, ''), COALESCE(module_key, '')), 0
         )) AS acquired
    FROM applicable
   ORDER BY scope_type, COALESCE(project_id::text, ''), COALESCE(module_key, '')
), lock_barrier AS MATERIALIZED (
  SELECT COUNT(*) AS acquired FROM scope_locks
), existing AS MATERIALIZED (
  SELECT reservation_id::text, provider_call_id, project_id::text, COALESCE(run_id::text, '') AS run_id,
         module_key, channel_id::text, model_id, reserved_tokens, reserved_cost_micros,
         actual_prompt_tokens, actual_completion_tokens, actual_cost_micros, status, expires_at
    FROM llm_quota_reservations AS reservation
   CROSS JOIN lock_barrier
   WHERE tenant_id = $1::uuid AND provider_call_id = $7
   FOR UPDATE OF reservation
), capacity AS MATERIALIZED (
  SELECT policy.*,
    COALESCE((SELECT SUM(quantity)::numeric FROM usage_events
      WHERE tenant_id = $1::uuid AND usage_type = 'llm_tokens'
        AND created_at >= now() - (policy.period_seconds * interval '1 second')
        AND (policy.scope_type = 'tenant' OR project_id = $2::uuid)
        AND (policy.scope_type <> 'module' OR module_key = $4)), 0) AS used_tokens,
    COALESCE((SELECT SUM(quantity)::numeric FROM usage_events
      WHERE tenant_id = $1::uuid AND usage_type = 'llm_cost_micros'
        AND created_at >= now() - (policy.period_seconds * interval '1 second')
        AND (policy.scope_type = 'tenant' OR project_id = $2::uuid)
        AND (policy.scope_type <> 'module' OR module_key = $4)), 0) AS used_cost,
    COALESCE((SELECT SUM(reserved_tokens)::numeric FROM llm_quota_reservations
      WHERE tenant_id = $1::uuid AND status = 'reserved' AND expires_at > now()
        AND (policy.scope_type = 'tenant' OR project_id = $2::uuid)
        AND (policy.scope_type <> 'module' OR module_key = $4)), 0) AS active_tokens,
    COALESCE((SELECT SUM(reserved_cost_micros)::numeric FROM llm_quota_reservations
      WHERE tenant_id = $1::uuid AND status = 'reserved' AND expires_at > now()
        AND (policy.scope_type = 'tenant' OR project_id = $2::uuid)
        AND (policy.scope_type <> 'module' OR module_key = $4)), 0) AS active_cost,
    (SELECT COUNT(*)::integer FROM llm_quota_reservations
      WHERE tenant_id = $1::uuid AND status = 'reserved' AND expires_at > now()
        AND (policy.scope_type = 'tenant' OR project_id = $2::uuid)
        AND (policy.scope_type <> 'module' OR module_key = $4)) AS active_calls
  FROM applicable AS policy
  CROSS JOIN lock_barrier
), decision AS MATERIALIZED (
  SELECT CASE
    WHEN NOT EXISTS (SELECT 1 FROM applicable) THEN 'policy_unavailable'
    WHEN EXISTS (SELECT 1 FROM existing WHERE
      project_id = $2::text AND run_id = $3::text AND module_key = $4
      AND channel_id = $5::text AND model_id = $6
      AND reserved_tokens = $8 AND reserved_cost_micros = $9
      AND status = 'reserved' AND expires_at > now()) THEN 'replay_reserved'
    WHEN EXISTS (SELECT 1 FROM existing WHERE
      project_id = $2::text AND run_id = $3::text AND module_key = $4
      AND channel_id = $5::text AND model_id = $6
      AND reserved_tokens = $8 AND reserved_cost_micros = $9
      AND status = 'finalized') THEN 'finalized'
    WHEN EXISTS (SELECT 1 FROM existing WHERE status NOT IN ('released', 'expired')) THEN 'provider_call_conflict'
    WHEN $10::boolean = FALSE AND EXISTS (SELECT 1 FROM capacity WHERE cost_limit_micros IS NOT NULL)
      THEN 'pricing_unavailable'
    WHEN EXISTS (SELECT 1 FROM capacity WHERE token_limit IS NOT NULL
      AND used_tokens + active_tokens + $8::numeric > token_limit::numeric) THEN 'tokens_exceeded'
    WHEN EXISTS (SELECT 1 FROM capacity WHERE cost_limit_micros IS NOT NULL
      AND used_cost + active_cost + $9::numeric > cost_limit_micros::numeric) THEN 'cost_exceeded'
    WHEN EXISTS (SELECT 1 FROM capacity WHERE concurrency_limit IS NOT NULL
      AND active_calls >= concurrency_limit) THEN 'concurrency_exceeded'
    WHEN EXISTS (SELECT 1 FROM existing WHERE status IN ('released', 'expired')) THEN 'reopen'
    ELSE 'allow'
  END AS code
), inserted AS (
  INSERT INTO llm_quota_reservations (
    tenant_id, provider_call_id, project_id, run_id, module_key, channel_id, model_id,
    reserved_tokens, reserved_cost_micros, status, expires_at
  )
  SELECT $1::uuid, $7, $2::uuid, NULLIF($3, '')::uuid, $4, $5::uuid, $6,
         $8::bigint, $9::bigint, 'reserved', now() + ($11::integer * interval '1 second')
    FROM decision WHERE code = 'allow'
  ON CONFLICT (tenant_id, provider_call_id) DO NOTHING
  RETURNING reservation_id::text, provider_call_id, status, expires_at,
            actual_prompt_tokens, actual_completion_tokens, actual_cost_micros
), reopened AS (
  UPDATE llm_quota_reservations AS reservation
     SET project_id = $2::uuid,
         run_id = NULLIF($3, '')::uuid,
         module_key = $4,
         channel_id = $5::uuid,
         model_id = $6,
         reserved_tokens = $8::bigint,
         reserved_cost_micros = $9::bigint,
         status = 'reserved',
         expires_at = now() + ($11::integer * interval '1 second'),
         actual_prompt_tokens = NULL,
         actual_completion_tokens = NULL,
         actual_cost_micros = NULL,
         finalized_at = NULL,
         updated_at = now()
    FROM decision
   WHERE decision.code = 'reopen'
     AND reservation.tenant_id = $1::uuid
     AND reservation.provider_call_id = $7
     AND reservation.status IN ('released', 'expired')
  RETURNING reservation.reservation_id::text, reservation.provider_call_id, reservation.status,
            reservation.expires_at, reservation.actual_prompt_tokens,
            reservation.actual_completion_tokens, reservation.actual_cost_micros
), selected AS (
  SELECT * FROM inserted
  UNION ALL
  SELECT * FROM reopened
  UNION ALL
  SELECT reservation_id, provider_call_id, status, expires_at,
         actual_prompt_tokens, actual_completion_tokens, actual_cost_micros
    FROM existing
   WHERE (SELECT code FROM decision) IN ('replay_reserved', 'finalized')
)
SELECT CASE WHEN decision.code IN ('allow', 'reopen') AND selected.reservation_id IS NOT NULL THEN 'reserved'
            WHEN decision.code IN ('allow', 'reopen') THEN 'reserve_failed'
            ELSE decision.code END AS decision,
       selected.reservation_id, selected.provider_call_id, selected.status, selected.expires_at,
       selected.actual_prompt_tokens, selected.actual_completion_tokens, selected.actual_cost_micros
  FROM decision
  LEFT JOIN selected ON TRUE`;

const finalizeSQL = `WITH existing AS MATERIALIZED (
  SELECT reservation_id::text, provider_call_id, project_id::text, COALESCE(run_id::text, '') AS run_id,
         module_key, model_id, reserved_tokens, reserved_cost_micros,
         actual_prompt_tokens, actual_completion_tokens, actual_cost_micros, status
    FROM llm_quota_reservations AS reservation
   WHERE tenant_id = $1::uuid AND reservation_id = $3::uuid
   FOR UPDATE OF reservation
), decision AS MATERIALIZED (
  SELECT CASE
    WHEN NOT EXISTS (SELECT 1 FROM existing) THEN 'reservation_not_found'
    WHEN NOT EXISTS (SELECT 1 FROM existing WHERE project_id = $2::text AND provider_call_id = $4)
      THEN 'provider_call_conflict'
    WHEN EXISTS (SELECT 1 FROM existing WHERE status = 'finalized'
      AND actual_prompt_tokens = $5 AND actual_completion_tokens = $6
      AND actual_cost_micros IS NOT DISTINCT FROM $7::bigint) THEN 'replay_finalized'
    WHEN EXISTS (SELECT 1 FROM existing WHERE status = 'finalized') THEN 'usage_conflict'
    WHEN EXISTS (SELECT 1 FROM existing WHERE status <> 'reserved') THEN 'reservation_closed'
    WHEN $5::bigint + $6::bigint > (SELECT reserved_tokens FROM existing) THEN 'usage_exceeds_reservation'
    WHEN $7::bigint IS NOT NULL AND $7::bigint > (SELECT reserved_cost_micros FROM existing) THEN 'usage_exceeds_reservation'
    WHEN ($8 = 'billing_ready' AND $7::bigint IS NULL) OR ($8 = 'pricing_unavailable' AND $7::bigint IS NOT NULL)
      THEN 'usage_invalid'
    ELSE 'allow'
  END AS code
), updated AS (
  UPDATE llm_quota_reservations AS reservation
     SET status = 'finalized', actual_prompt_tokens = $5, actual_completion_tokens = $6,
         actual_cost_micros = $7::bigint, finalized_at = now(), updated_at = now()
    FROM decision
   WHERE reservation.tenant_id = $1::uuid AND reservation.reservation_id = $3::uuid AND decision.code = 'allow'
  RETURNING reservation.project_id, reservation.run_id, reservation.module_key,
            reservation.model_id, reservation.provider_call_id
), token_usage AS (
  INSERT INTO usage_events (
    tenant_id, project_id, run_id, module_key, usage_type, quantity, unit, metadata_jsonb
  )
  SELECT $1::uuid, project_id, run_id, module_key, 'llm_tokens', $5::bigint + $6::bigint, 'tokens',
         jsonb_build_object('provider_call_id', provider_call_id, 'model_id', model_id, 'pricing_status', $8::text)
    FROM updated
  RETURNING usage_event_id
), cost_usage AS (
  INSERT INTO usage_events (
    tenant_id, project_id, run_id, module_key, usage_type, quantity, unit, metadata_jsonb
  )
  SELECT $1::uuid, updated.project_id, updated.run_id, updated.module_key,
         'llm_cost_micros', $7::bigint, 'micros',
         jsonb_build_object('provider_call_id', updated.provider_call_id, 'model_id', updated.model_id, 'pricing_status', $8::text)
    FROM updated
   CROSS JOIN (SELECT COUNT(*) FROM token_usage) AS token_barrier
   WHERE $7::bigint IS NOT NULL
  RETURNING usage_event_id
), write_barrier AS MATERIALIZED (
  SELECT (SELECT COUNT(*) FROM token_usage) + (SELECT COUNT(*) FROM cost_usage) AS writes
)
SELECT CASE WHEN decision.code = 'allow' AND write_barrier.writes >= 1 THEN 'finalized'
            WHEN decision.code = 'allow' THEN 'finalize_failed'
            ELSE decision.code END AS decision
  FROM decision CROSS JOIN write_barrier`;

const releaseSQL = `WITH existing AS MATERIALIZED (
  SELECT reservation_id::text, provider_call_id, project_id::text, status
    FROM llm_quota_reservations AS reservation
   WHERE tenant_id = $1::uuid AND reservation_id = $3::uuid
   FOR UPDATE OF reservation
), decision AS MATERIALIZED (
  SELECT CASE
    WHEN NOT EXISTS (SELECT 1 FROM existing) THEN 'reservation_not_found'
    WHEN NOT EXISTS (SELECT 1 FROM existing WHERE project_id = $2::text AND provider_call_id = $4)
      THEN 'provider_call_conflict'
    WHEN EXISTS (SELECT 1 FROM existing WHERE status = 'released') THEN 'replay_released'
    WHEN EXISTS (SELECT 1 FROM existing WHERE status <> 'reserved') THEN 'reservation_closed'
    ELSE 'allow'
  END AS code
), updated AS (
  UPDATE llm_quota_reservations AS reservation
     SET status = 'released', updated_at = now()
    FROM decision
   WHERE reservation.tenant_id = $1::uuid AND reservation.reservation_id = $3::uuid
     AND reservation.status = 'reserved' AND decision.code = 'allow'
  RETURNING reservation_id
)
SELECT CASE WHEN decision.code = 'allow' AND EXISTS (SELECT 1 FROM updated) THEN 'released'
            WHEN decision.code = 'allow' THEN 'release_failed'
            ELSE decision.code END AS decision
  FROM decision`;

function tenantContext(request: { tenant_id: string; project_id: string }): QuotaTenantContext {
  return { tenant_id: request.tenant_id, project_id: request.project_id };
}

function validateReserveRequest(request: ReserveQuotaRequest): void {
  if (!requiredContext(request) || !request.run_id.trim() || !request.module_key.trim() ||
      !request.channel_id.trim() || !request.model_id.trim() || !request.provider_call_id.trim() ||
      !nonNegativeSafeInteger(request.reserved_tokens) || !nonNegativeSafeInteger(request.reserved_cost_micros) ||
      !positiveSafeInteger(request.ttl_seconds)) {
    throw quotaError("VALIDATION_FAILED", "LLM quota reservation is invalid");
  }
}

function validateFinalizeRequest(request: FinalizeQuotaRequest): void {
  if (!requiredContext(request) || !request.reservation_id.trim() || !request.provider_call_id.trim() ||
      !nonNegativeSafeInteger(request.prompt_tokens) || !nonNegativeSafeInteger(request.completion_tokens) ||
      request.actual_cost_micros !== undefined && !nonNegativeSafeInteger(request.actual_cost_micros)) {
    throw quotaError("VALIDATION_FAILED", "LLM quota finalization is invalid");
  }
}

function validateReleaseRequest(request: ReleaseQuotaRequest): void {
  if (!requiredContext(request) || !request.reservation_id.trim() || !request.provider_call_id.trim()) {
    throw quotaError("VALIDATION_FAILED", "LLM quota release is invalid");
  }
}

function requiredContext(request: { tenant_id: string; project_id: string }): boolean {
  return Boolean(request.tenant_id.trim() && request.project_id.trim());
}

function reserveDecisionError(decision: string | undefined): Error {
  const errors: Record<string, [string, string]> = {
    policy_unavailable: ["LLM_QUOTA_POLICY_UNAVAILABLE", "LLM quota policy is unavailable"],
    pricing_unavailable: ["LLM_QUOTA_PRICING_UNAVAILABLE", "LLM pricing is required by the active quota policy"],
    tokens_exceeded: ["LLM_QUOTA_TOKENS_EXCEEDED", "LLM token quota exceeded"],
    cost_exceeded: ["LLM_QUOTA_COST_EXCEEDED", "LLM cost quota exceeded"],
    concurrency_exceeded: ["LLM_QUOTA_CONCURRENCY_EXCEEDED", "LLM quota concurrency limit reached"],
    provider_call_conflict: ["LLM_PROVIDER_CALL_CONFLICT", "LLM provider call identity conflicts with an existing reservation"],
    reservation_closed: ["LLM_QUOTA_RESERVATION_CLOSED", "LLM quota reservation is closed"]
  };
  const mapped = decision ? errors[decision] : undefined;
  return mapped ? quotaError(...mapped) : quotaError("LLM_QUOTA_RESERVE_FAILED", "LLM quota reservation failed");
}

function finalizeDecisionError(decision: string | undefined): Error {
  const errors: Record<string, [string, string]> = {
    reservation_not_found: ["LLM_QUOTA_RESERVATION_NOT_FOUND", "LLM quota reservation was not found"],
    provider_call_conflict: ["LLM_PROVIDER_CALL_CONFLICT", "LLM provider call identity conflicts with an existing reservation"],
    reservation_closed: ["LLM_QUOTA_RESERVATION_CLOSED", "LLM quota reservation is closed"],
    usage_exceeds_reservation: ["LLM_USAGE_EXCEEDS_RESERVATION", "LLM provider usage exceeded its reservation"],
    usage_conflict: ["LLM_USAGE_CONFLICT", "LLM provider usage conflicts with finalized usage"],
    usage_invalid: ["LLM_USAGE_DATA_INVALID", "LLM usage data is invalid"]
  };
  const mapped = decision ? errors[decision] : undefined;
  return mapped ? quotaError(...mapped) : quotaError("LLM_QUOTA_FINALIZE_FAILED", "LLM quota finalization failed");
}

function releaseDecisionError(decision: string | undefined): Error {
  const errors: Record<string, [string, string]> = {
    reservation_not_found: ["LLM_QUOTA_RESERVATION_NOT_FOUND", "LLM quota reservation was not found"],
    provider_call_conflict: ["LLM_PROVIDER_CALL_CONFLICT", "LLM provider call identity conflicts with an existing reservation"],
    reservation_closed: ["LLM_QUOTA_RESERVATION_CLOSED", "LLM quota reservation is closed"]
  };
  const mapped = decision ? errors[decision] : undefined;
  return mapped ? quotaError(...mapped) : quotaError("LLM_QUOTA_RELEASE_FAILED", "LLM quota reservation release failed");
}

function optionalActualUsage(row: ReservationRow): Partial<QuotaReservation> {
  return {
    ...(optionalInteger(row.actual_prompt_tokens) === undefined ? {} : { actual_prompt_tokens: optionalInteger(row.actual_prompt_tokens) }),
    ...(optionalInteger(row.actual_completion_tokens) === undefined ? {} : { actual_completion_tokens: optionalInteger(row.actual_completion_tokens) }),
    ...(optionalInteger(row.actual_cost_micros) === undefined ? {} : { actual_cost_micros: optionalInteger(row.actual_cost_micros) })
  };
}

function requiredStatus(value: unknown): QuotaReservation["status"] {
  if (value === "reserved" || value === "finalized") return value;
  throw quotaError("LLM_QUOTA_RESERVE_FAILED", "LLM quota reservation failed");
}

function requiredString(value: unknown, code: string): string {
  if (typeof value === "string" && value.trim()) return value;
  throw quotaError(code, "LLM quota reservation failed");
}

function requiredTimestamp(value: unknown): string {
  const timestamp = value instanceof Date ? value.toISOString() : typeof value === "string" ? value : "";
  if (!timestamp || Number.isNaN(Date.parse(timestamp))) {
    throw quotaError("LLM_QUOTA_RESERVE_FAILED", "LLM quota reservation failed");
  }
  return timestamp;
}

function optionalInteger(value: unknown): number | undefined {
  if (value === null || value === undefined) return undefined;
  const parsed = typeof value === "number" ? value : typeof value === "string" ? Number(value) : NaN;
  if (!nonNegativeSafeInteger(parsed)) {
    throw quotaError("LLM_USAGE_DATA_INVALID", "LLM usage data is invalid");
  }
  return parsed;
}

function positiveSafeInteger(value: unknown): value is number {
  return typeof value === "number" && Number.isSafeInteger(value) && value > 0;
}

function nonNegativeSafeInteger(value: unknown): value is number {
  return typeof value === "number" && Number.isSafeInteger(value) && value >= 0;
}

function quotaError(code: string, message: string): Error {
  return new Error(`${code}: ${message}`);
}
