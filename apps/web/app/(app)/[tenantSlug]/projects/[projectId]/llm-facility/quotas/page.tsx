import { redirect } from "next/navigation";
import { LLMQuotaAdminShell } from "../../../../../../../components/llm-quota-admin-shell";
import {
  checkProviderHealth,
  createQuotaPolicy,
  deleteQuotaPolicy,
  listBillingReconciliation,
  listQuotaPolicies,
  listQuotaReservations,
  previewQuotaResolution,
  updateQuotaPolicy,
  type LLMAdminContext,
  type PolicyWrite,
  type ProviderHealth,
} from "../../../../../../../lib/llm-admin-api";
import { currentRequestLocale } from "../../../../../../../lib/request-locale";
import { webApiContext } from "../../../../../../../lib/server-auth";

export const dynamic = "force-dynamic";
const DEFAULT_MODULE = "writer_composer";

export default async function LLMQuotaAdminPage({ params, searchParams }: {
  params: Promise<{ tenantSlug: string; projectId: string }>;
  searchParams?: Promise<Record<string, string | string[] | undefined>>;
}) {
  const { tenantSlug, projectId } = await params;
  const locale = await currentRequestLocale();
  const query = searchParams ? await searchParams : {};
  const moduleKey = queryValue(query.moduleKey) || DEFAULT_MODULE;
  const reservationStatus = queryValue(query.reservationStatus);
  const context = await adminContext(tenantSlug, projectId);
  const [policies, resolution, reservations, reconciliation] = await Promise.all([
    listQuotaPolicies(context, projectId),
    previewQuotaResolution(context, projectId, moduleKey),
    listQuotaReservations(context, projectId, reservationStatus),
    listBillingReconciliation(context, projectId, moduleKey),
  ]);

  async function createPolicyAction(formData: FormData) {
    "use server";
    const result = await createQuotaPolicy(await adminContext(tenantSlug, projectId), policyInput(formData, projectId));
    redirectWithResult(tenantSlug, projectId, moduleKey, reservationStatus, result.ok, result.ok ? "LLM_QUOTA_POLICY_CREATED" : result.code, result.ok ? "Quota policy created" : result.message);
  }

  async function updatePolicyAction(formData: FormData) {
    "use server";
    const policyId = field(formData, "policyId");
    const input = policyInput(formData, projectId);
    input.expected_version = field(formData, "expectedVersion");
    const result = await updateQuotaPolicy(await adminContext(tenantSlug, projectId), policyId, input);
    redirectWithResult(tenantSlug, projectId, moduleKey, reservationStatus, result.ok, result.ok ? "LLM_QUOTA_POLICY_UPDATED" : result.code, result.ok ? "Quota policy updated" : result.message);
  }

  async function deletePolicyAction(formData: FormData) {
    "use server";
    const result = await deleteQuotaPolicy(await adminContext(tenantSlug, projectId), field(formData, "policyId"), field(formData, "expectedVersion"));
    redirectWithResult(tenantSlug, projectId, moduleKey, reservationStatus, result.ok, result.ok ? "LLM_QUOTA_POLICY_DELETED" : result.code, result.ok ? "Quota policy deleted" : result.message);
  }

  async function healthAction(formData: FormData) {
    "use server";
    const result = await checkProviderHealth(await adminContext(tenantSlug, projectId), {
      project_id: projectId,
      channel_id: field(formData, "channelId"),
      model_id: field(formData, "modelId"),
    });
    const next = baseQuery(moduleKey, reservationStatus);
    if (result.ok) {
      next.set("healthStatus", result.status);
      next.set("healthChannel", result.channel_id);
      next.set("healthModel", result.model_id);
      next.set("healthCode", String(result.status_code));
      next.set("healthLatency", String(result.latency_ms));
      next.set("healthTools", String(result.supports_tools));
      next.set("healthJSON", String(result.supports_json));
      next.set("healthCheckedAt", result.checked_at);
    } else {
      next.set("status", "error"); next.set("code", result.code); next.set("message", result.message);
    }
    redirect(`/${tenantSlug}/projects/${projectId}/llm-facility/quotas?${next.toString()}`);
  }

  return <LLMQuotaAdminShell
    locale={locale}
    tenantSlug={tenantSlug}
    projectId={projectId}
    moduleKey={moduleKey}
    reservationStatus={reservationStatus}
    policies={policies}
    resolution={resolution}
    reservations={reservations}
    reconciliation={reconciliation}
    health={healthFromQuery(query)}
    notice={queryValue(query.message) ? { status: queryValue(query.status), code: queryValue(query.code), message: queryValue(query.message) } : undefined}
    createPolicyAction={createPolicyAction}
    updatePolicyAction={updatePolicyAction}
    deletePolicyAction={deletePolicyAction}
    healthAction={healthAction}
  />;
}

async function adminContext(tenantId: string, projectId: string): Promise<LLMAdminContext> {
  return webApiContext({ tenantId, projectId });
}

function policyInput(formData: FormData, projectId: string): PolicyWrite {
  const scope = field(formData, "scopeType") as PolicyWrite["scope_type"];
  return {
    scope_type: scope,
    project_id: scope === "tenant" ? undefined : projectId,
    module_key: scope === "module" ? field(formData, "moduleKey") : undefined,
    token_limit: optionalInteger(formData, "tokenLimit"),
    cost_limit_micros: optionalInteger(formData, "costLimitMicros"),
    concurrency_limit: optionalInteger(formData, "concurrencyLimit"),
    period_seconds: requiredInteger(formData, "periodSeconds"),
    enabled: field(formData, "enabled") === "on",
  };
}

function healthFromQuery(query: Record<string, string | string[] | undefined>): ({ ok: true } & ProviderHealth) | undefined {
  if (queryValue(query.healthStatus) !== "healthy") return undefined;
  return {
    ok: true,
    status: "healthy",
    channel_id: queryValue(query.healthChannel),
    model_id: queryValue(query.healthModel),
    status_code: Number(queryValue(query.healthCode)),
    latency_ms: Number(queryValue(query.healthLatency)),
    supports_tools: queryValue(query.healthTools) === "true",
    supports_json: queryValue(query.healthJSON) === "true",
    checked_at: queryValue(query.healthCheckedAt),
  };
}

function redirectWithResult(tenantSlug: string, projectId: string, moduleKey: string, reservationStatus: string, ok: boolean, code: string, message: string): never {
  const query = baseQuery(moduleKey, reservationStatus);
  query.set("status", ok ? "success" : "error"); query.set("code", code); query.set("message", message);
  redirect(`/${tenantSlug}/projects/${projectId}/llm-facility/quotas?${query.toString()}`);
}

function baseQuery(moduleKey: string, reservationStatus: string) { const query = new URLSearchParams({ moduleKey }); if (reservationStatus) query.set("reservationStatus", reservationStatus); return query; }
function queryValue(value: string | string[] | undefined) { return Array.isArray(value) ? value[0]?.trim() ?? "" : value?.trim() ?? ""; }
function field(formData: FormData, key: string) { const value = formData.get(key); return typeof value === "string" ? value.trim() : ""; }
function optionalInteger(formData: FormData, key: string) { const value = field(formData, key); return value === "" ? null : Number.parseInt(value, 10); }
function requiredInteger(formData: FormData, key: string) { return Number.parseInt(field(formData, key), 10); }
