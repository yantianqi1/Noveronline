import { describe, expect, it } from "vitest";

import type { ComposeDraftRequest } from "../activities/pi-writer-activities.js";
import { createPiAIComposeDraft } from "./pi-ai-compose.js";

const requiredLiveEnvVars = [
  "MIROFISH_PI_WRITER_LIVE_RESOLVED_BASE_URL",
  "MIROFISH_PI_WRITER_LIVE_RESOLVED_API_KEY",
  "MIROFISH_PI_WRITER_LIVE_RESOLVED_MODEL_ID",
  "MIROFISH_PI_WRITER_LIVE_RESOLVED_CHANNEL_ID"
] as const;

type RequiredLiveEnvVar = (typeof requiredLiveEnvVars)[number];

interface LiveResolvedHandoff {
  baseUrl: string;
  apiKey: string;
  modelId: string;
  channelId: string;
  maxTokens?: number;
  temperature?: number;
}

const liveEnvState = readLiveEnvState(process.env);
const describeLive = liveEnvState === "absent" ? describe.skip : describe;

describeLive("createPiAIComposeDraft live resolved LLM Facility handoff", () => {
  it("composes a non-empty draft through an explicit OpenAI-compatible handoff", async () => {
    const handoff = requireLiveResolvedHandoff(process.env);
    const composeDraft = createPiAIComposeDraft();
    const request: ComposeDraftRequest = {
      tenant_id: "ten_live_smoke",
      project_id: "proj_live_smoke",
      run_id: `run_live_smoke_${Date.now()}`,
      module_key: "writer_composer",
      channel_id: handoff.channelId,
      model_id: handoff.modelId,
      provider: "openai-compatible",
      base_url: handoff.baseUrl,
      instruction: "Write one short, original sentence for a quiet rain scene.",
      apiKey: handoff.apiKey,
      settings: {
        max_tokens: handoff.maxTokens ?? 80,
        temperature: handoff.temperature ?? 0.2
      }
    };

    const result = await composeDraft(request).catch((error: unknown) => {
      throw sanitizedProviderError(error);
    });

    expect(result.content.trim().length).toBeGreaterThan(0);
  });
});

describe("sanitize Pi writer live provider failures", () => {
  it("does not echo provider-controlled error names", () => {
    const error = new Error("provider raw body prompt=private api_key=sk-live");
    error.name = "ProviderFailure api_key=sk-live prompt=private";

    const sanitized = sanitizedProviderError(error);

    expect(sanitized.message).toBe("Pi writer live provider invocation failed (Error); provider details were redacted");
    expect(sanitized.message).not.toContain("sk-live");
    expect(sanitized.message).not.toContain("prompt=private");
    expect(sanitized.message).not.toContain("ProviderFailure");
  });
});

function readLiveEnvState(env: NodeJS.ProcessEnv): "absent" | "partial" | "complete" {
  const present = requiredLiveEnvVars.filter((name) => env[name]?.trim());
  if (present.length === 0) {
    return "absent";
  }
  return present.length === requiredLiveEnvVars.length ? "complete" : "partial";
}

function requireLiveResolvedHandoff(env: NodeJS.ProcessEnv): LiveResolvedHandoff {
  const missing = requiredLiveEnvVars.filter((name) => !env[name]?.trim());
  if (missing.length > 0) {
    throw new Error(`Pi writer live smoke requires complete resolved LLM Facility handoff env; missing: ${missing.join(", ")}`);
  }

  return {
    baseUrl: requiredEnv(env, "MIROFISH_PI_WRITER_LIVE_RESOLVED_BASE_URL"),
    apiKey: requiredEnv(env, "MIROFISH_PI_WRITER_LIVE_RESOLVED_API_KEY"),
    modelId: requiredEnv(env, "MIROFISH_PI_WRITER_LIVE_RESOLVED_MODEL_ID"),
    channelId: requiredEnv(env, "MIROFISH_PI_WRITER_LIVE_RESOLVED_CHANNEL_ID"),
    maxTokens: optionalPositiveNumber(env.MIROFISH_PI_WRITER_LIVE_MAX_TOKENS, "MIROFISH_PI_WRITER_LIVE_MAX_TOKENS"),
    temperature: optionalNumber(env.MIROFISH_PI_WRITER_LIVE_TEMPERATURE, "MIROFISH_PI_WRITER_LIVE_TEMPERATURE")
  };
}

function requiredEnv(env: NodeJS.ProcessEnv, name: RequiredLiveEnvVar): string {
  const value = env[name]?.trim();
  if (!value) {
    throw new Error(`Pi writer live smoke is missing ${name}`);
  }
  return value;
}

function optionalPositiveNumber(value: string | undefined, name: string): number | undefined {
  const parsed = optionalNumber(value, name);
  if (parsed !== undefined && parsed <= 0) {
    throw new Error(`${name} must be greater than 0`);
  }
  return parsed;
}

function optionalNumber(value: string | undefined, name: string): number | undefined {
  if (value === undefined || value.trim() === "") {
    return undefined;
  }
  const parsed = Number(value);
  if (!Number.isFinite(parsed)) {
    throw new Error(`${name} must be a finite number`);
  }
  return parsed;
}

function sanitizedProviderError(error: unknown): Error {
  const providerFailureType = providerFailureName(error);
  return new Error(`Pi writer live provider invocation failed (${providerFailureType}); provider details were redacted`);
}

function providerFailureName(error: unknown): string {
  if (error instanceof Error) {
    const name = error.name.trim();
    if (/^[A-Za-z][A-Za-z0-9_.-]{0,48}$/.test(name)) {
      return name;
    }
  }
  return "Error";
}
