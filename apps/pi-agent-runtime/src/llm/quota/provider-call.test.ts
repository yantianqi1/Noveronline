import { describe, expect, it } from "vitest";

import {
  providerCallBudget,
  stableProviderCallId,
  usageCostMicros,
  validateProviderUsage
} from "./provider-call.js";

const identity = {
  tenant_id: "tenant-1",
  project_id: "project-1",
  run_id: "run-1",
  module_key: "writer_orchestrator" as const,
  stage: "orchestrator" as const,
  call_index: 0
};

describe("Pi writer provider-call quota contract", () => {
  it("builds deterministic but stage-specific provider-call identities", () => {
    const first = stableProviderCallId(identity);
    const replay = stableProviderCallId({ ...identity });
    const composer = stableProviderCallId({
      ...identity,
      module_key: "writer_composer",
      stage: "composer"
    });
    const nextCall = stableProviderCallId({ ...identity, call_index: 1 });

    expect(first).toBe(replay);
    expect(first).toMatch(/^pi-writer:v1:writer_orchestrator:orchestrator:0:[a-f0-9]{64}$/);
    expect(new Set([first, composer, nextCall])).toHaveLength(3);
    expect(first).not.toContain(identity.tenant_id);
    expect(first).not.toContain(identity.project_id);
    expect(first).not.toContain(identity.run_id);
  });

  it("reserves configured token capacity and marks missing pricing unavailable", () => {
    expect(providerCallBudget({ quota_reserved_tokens: 4096, input_cost: 1.5, output_cost: 4 })).toEqual({
      reserved_tokens: 4096,
      reserved_cost_micros: 16384,
      pricing_status: "billing_ready"
    });
    expect(providerCallBudget({ context_window: 32768, max_tokens: 2048 })).toEqual({
      reserved_tokens: 32768,
      reserved_cost_micros: 0,
      pricing_status: "pricing_unavailable"
    });
  });

  it("requires valid actual usage and never fabricates cost without pricing", () => {
    expect(validateProviderUsage({ prompt_tokens: 11, completion_tokens: 17, cost_estimate: 0.0045 })).toEqual({
      prompt_tokens: 11,
      completion_tokens: 17,
      cost_estimate: 0.0045
    });
    expect(usageCostMicros({ prompt_tokens: 11, completion_tokens: 17, cost_estimate: 0 }, "pricing_unavailable")).toBeUndefined();
    expect(usageCostMicros({ prompt_tokens: 11, completion_tokens: 17, cost_estimate: 0.0045 }, "billing_ready")).toBe(4500);
    expect(() => validateProviderUsage(undefined)).toThrow("LLM_PROVIDER_USAGE_MISSING");
    expect(() => validateProviderUsage({ prompt_tokens: 1.5, completion_tokens: 2 })).toThrow("LLM_PROVIDER_USAGE_INVALID");
  });
});
