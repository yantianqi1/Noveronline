export type LLMAdminContext = {
  tenantId: string;
  actorUserId?: string;
  sessionCookie?: string;
  csrfToken?: string;
};

export type LLMAdminFailure = { ok: false; code: string; message: string };

export type QuotaPolicy = {
  policy_id: string;
  scope_type: "tenant" | "project" | "module";
  project_id?: string;
  module_key?: string;
  token_limit: number | null;
  cost_limit_micros: number | null;
  concurrency_limit: number | null;
  period_seconds: number;
  enabled: boolean;
  version: string;
  created_at: string;
  updated_at: string;
};

export type PolicyUsage = {
  policy: QuotaPolicy;
  period_from: string;
  period_to: string;
  used_tokens: number;
  used_cost_micros: number;
  reserved_tokens: number;
  reserved_cost_micros: number;
  active_reservations: number;
  remaining_tokens: number | null;
  remaining_cost_micros: number | null;
  remaining_concurrency: number | null;
};

export type ResolutionPreview = {
  project_id: string;
  module_key: string;
  resolution_order: string[];
  applicable: PolicyUsage[];
  limiting_scopes: string[];
  status: "effective" | "unconfigured";
};

export type Reservation = {
  reservation_id: string;
  provider_call_id: string;
  project_id: string;
  run_id?: string;
  module_key: string;
  channel_id: string;
  model_id: string;
  reserved_tokens: number;
  reserved_cost_micros: number;
  actual_prompt_tokens: number | null;
  actual_completion_tokens: number | null;
  actual_cost_micros: number | null;
  status: "reserved" | "finalized" | "released" | "expired";
  expires_at: string;
  finalized_at?: string;
  created_at: string;
  updated_at: string;
};

export type Reconciliation = {
  provider_call_id: string;
  reservation_id?: string;
  project_id?: string;
  run_id?: string;
  module_key?: string;
  model_id?: string;
  reservation_status?: string;
  activity_status?: string;
  reserved_tokens: number | null;
  actual_tokens: number | null;
  usage_tokens: number | null;
  actual_cost_micros: number | null;
  usage_cost_micros: number | null;
  pricing_status: "available" | "unavailable";
  billing_status: "reconciled" | "pricing_unavailable" | "attention_required";
  issues: string[];
};

export type ProviderHealth = {
  channel_id: string;
  model_id: string;
  status: "healthy";
  status_code: number;
  latency_ms: number;
  supports_tools: boolean;
  supports_json: boolean;
  checked_at: string;
};

export type PolicyWrite = {
  scope_type: "tenant" | "project" | "module";
  project_id?: string;
  module_key?: string;
  token_limit?: number | null;
  cost_limit_micros?: number | null;
  concurrency_limit?: number | null;
  period_seconds: number;
  enabled?: boolean;
  expected_version?: string;
};

const API_BASE_URL = process.env.MIROFISH_API_BASE_URL ?? "http://localhost:8080";

export async function listQuotaPolicies(context: LLMAdminContext, projectId: string) {
  return adminRequest<{ items: QuotaPolicy[] }>(context, `/v1/llm-admin/policies?project_id=${encodeURIComponent(projectId)}`);
}

export async function createQuotaPolicy(context: LLMAdminContext, input: PolicyWrite) {
  return adminRequest<QuotaPolicy>(context, "/v1/llm-admin/policies", { method: "POST", body: JSON.stringify(input) });
}

export async function updateQuotaPolicy(context: LLMAdminContext, policyId: string, input: PolicyWrite) {
  return adminRequest<QuotaPolicy>(context, `/v1/llm-admin/policies/${encodeURIComponent(policyId)}`, { method: "PUT", body: JSON.stringify(input) });
}

export async function deleteQuotaPolicy(context: LLMAdminContext, policyId: string, expectedVersion: string) {
  return adminRequest<{ ok: true; policy_id: string }>(context, `/v1/llm-admin/policies/${encodeURIComponent(policyId)}?expected_version=${encodeURIComponent(expectedVersion)}`, { method: "DELETE" });
}

export async function previewQuotaResolution(context: LLMAdminContext, projectId: string, moduleKey: string) {
  const query = new URLSearchParams({ project_id: projectId, module_key: moduleKey });
  return adminRequest<ResolutionPreview>(context, `/v1/llm-admin/resolution?${query.toString()}`);
}

export async function listQuotaReservations(context: LLMAdminContext, projectId: string, status = "") {
  const query = new URLSearchParams({ project_id: projectId, limit: "100" });
  if (status) query.set("status", status);
  return adminRequest<{ items: Reservation[] }>(context, `/v1/llm-admin/reservations?${query.toString()}`);
}

export async function listBillingReconciliation(context: LLMAdminContext, projectId: string, moduleKey = "") {
  const query = new URLSearchParams({ project_id: projectId, limit: "100" });
  if (moduleKey) query.set("module_key", moduleKey);
  return adminRequest<{ items: Reconciliation[] }>(context, `/v1/llm-admin/reconciliation?${query.toString()}`);
}

export async function checkProviderHealth(context: LLMAdminContext, input: { project_id: string; channel_id: string; model_id: string }) {
  return adminRequest<ProviderHealth>(context, "/v1/llm-admin/provider-health", { method: "POST", body: JSON.stringify(input) });
}

async function adminRequest<T>(context: LLMAdminContext, path: string, init: RequestInit = {}): Promise<({ ok: true } & T) | LLMAdminFailure> {
  try {
    const response = await fetch(`${API_BASE_URL}${path}`, {
      ...init,
      cache: "no-store",
      headers: adminHeaders(context, init.method ?? "GET"),
    });
    const payload: unknown = await response.json().catch(() => null);
    if (!response.ok) return decodeFailure(payload);
    if (!isRecord(payload)) return { ok: false, code: "LLM_ADMIN_INVALID_RESPONSE", message: "LLM admin returned an invalid response" };
    return { ok: true, ...(payload as T) };
  } catch {
    return { ok: false, code: "LLM_ADMIN_UNAVAILABLE", message: "LLM admin service is unavailable" };
  }
}

function adminHeaders(context: LLMAdminContext, method: string) {
  const headers: Record<string, string> = { "X-Tenant-Id": context.tenantId };
  if (method !== "GET") headers["Content-Type"] = "application/json";
  if (context.sessionCookie) headers.Cookie = `mirofish_session=${context.sessionCookie}`;
  else if (context.actorUserId) headers["X-User-Id"] = context.actorUserId;
  if (method !== "GET" && context.csrfToken) headers["X-CSRF-Token"] = context.csrfToken;
  return headers;
}

function decodeFailure(payload: unknown): LLMAdminFailure {
  if (isRecord(payload) && isRecord(payload.error)) {
    const code = typeof payload.error.code === "string" ? payload.error.code : "LLM_ADMIN_FAILED";
    const message = typeof payload.error.message === "string" ? payload.error.message : "LLM admin request failed";
    return { ok: false, code, message };
  }
  return { ok: false, code: "LLM_ADMIN_FAILED", message: "LLM admin request failed" };
}

function isRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === "object" && value !== null && !Array.isArray(value);
}
