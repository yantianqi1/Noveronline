import { createHash } from "node:crypto";

export type PiWriterProviderModule = string;
export type PiWriterProviderStage = "orchestrator" | "composer" | "planner" | "rerank" | "consistency" | "embedding";
export type PricingStatus = "billing_ready" | "pricing_unavailable";

export interface ProviderCallIdentityInput {
  tenant_id: string;
  project_id: string;
  run_id: string;
  module_key: PiWriterProviderModule;
  stage: PiWriterProviderStage;
  call_index: number;
}

export interface ProviderCallBudget {
  reserved_tokens: number;
  reserved_cost_micros: number;
  pricing_status: PricingStatus;
}

export interface ProviderUsage {
  prompt_tokens: number;
  completion_tokens: number;
  cost_estimate?: number;
}

const defaultContextWindow = 128_000;

export function stableProviderCallId(input: ProviderCallIdentityInput): string {
  if (!input.tenant_id.trim() || !input.project_id.trim() || !input.run_id.trim() ||
      !Number.isSafeInteger(input.call_index) || input.call_index < 0) {
    throw new Error("LLM_PROVIDER_CALL_ID_INVALID: provider call identity is incomplete");
  }
  const digest = createHash("sha256")
    .update([input.tenant_id, input.project_id, input.run_id, input.module_key, input.stage, String(input.call_index)].join("\0"))
    .digest("hex");
  return `pi-writer:v1:${input.module_key}:${input.stage}:${input.call_index}:${digest}`;
}

export function providerCallBudget(settings: Record<string, unknown>): ProviderCallBudget {
  const reservedTokens = positiveSafeInteger(settings.quota_reserved_tokens)
    ?? positiveSafeInteger(settings.context_window)
    ?? defaultContextWindow;
  const inputCost = finiteNonNegative(settings.input_cost);
  const outputCost = finiteNonNegative(settings.output_cost);
  if (inputCost === undefined || outputCost === undefined) {
    return {
      reserved_tokens: reservedTokens,
      reserved_cost_micros: 0,
      pricing_status: "pricing_unavailable"
    };
  }
  const reservedCost = Math.ceil(reservedTokens * Math.max(inputCost, outputCost));
  if (!Number.isSafeInteger(reservedCost) || reservedCost < 0) {
    throw new Error("LLM_MODEL_PRICING_INVALID: LLM model pricing is invalid");
  }
  return {
    reserved_tokens: reservedTokens,
    reserved_cost_micros: reservedCost,
    pricing_status: "billing_ready"
  };
}

export function validateProviderUsage(value: Partial<ProviderUsage> | undefined): ProviderUsage {
  if (!value) {
    throw new Error("LLM_PROVIDER_USAGE_MISSING: LLM provider did not return usage");
  }
  const promptTokens = value.prompt_tokens;
  const completionTokens = value.completion_tokens;
  if (!nonNegativeSafeInteger(promptTokens) || !nonNegativeSafeInteger(completionTokens) ||
      value.cost_estimate !== undefined && finiteNonNegative(value.cost_estimate) === undefined) {
    throw new Error("LLM_PROVIDER_USAGE_INVALID: LLM provider returned invalid usage");
  }
  return {
    prompt_tokens: promptTokens,
    completion_tokens: completionTokens,
    ...(value.cost_estimate === undefined ? {} : { cost_estimate: value.cost_estimate })
  };
}

export function usageCostMicros(usage: ProviderUsage, pricingStatus: PricingStatus): number | undefined {
  if (pricingStatus === "pricing_unavailable") return undefined;
  const cost = finiteNonNegative(usage.cost_estimate);
  if (cost === undefined) {
    throw new Error("LLM_PROVIDER_COST_MISSING: LLM provider did not return valid cost usage");
  }
  const micros = Math.round(cost * 1_000_000);
  if (!Number.isSafeInteger(micros) || micros < 0) {
    throw new Error("LLM_PROVIDER_COST_INVALID: LLM provider returned invalid cost usage");
  }
  return micros;
}

function positiveSafeInteger(value: unknown): number | undefined {
  return typeof value === "number" && Number.isSafeInteger(value) && value > 0 ? value : undefined;
}

function nonNegativeSafeInteger(value: unknown): value is number {
  return typeof value === "number" && Number.isSafeInteger(value) && value >= 0;
}

function finiteNonNegative(value: unknown): number | undefined {
  return typeof value === "number" && Number.isFinite(value) && value >= 0 ? value : undefined;
}
