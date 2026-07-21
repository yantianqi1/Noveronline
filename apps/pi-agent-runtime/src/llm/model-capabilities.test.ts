import { describe, expect, it } from "vitest";

import {
  effectiveModelCapabilities,
  inferModelCapabilities,
  normalizeModelId,
} from "./model-capabilities.js";

describe("model-capabilities", () => {
  it("normalizes proxy tags and case", () => {
    expect(normalizeModelId("[free]DeepSeek-V4-Flash")).toBe("deepseek-v4-flash");
    expect(normalizeModelId("  gpt-4o  ")).toBe("gpt-4o");
    expect(normalizeModelId(null)).toBe("");
  });

  it("treats common chat models as tool and json capable", () => {
    for (const modelId of [
      "deepseek-v4-flash",
      "deepseek-chat",
      "gpt-4o",
      "claude-3-5-sonnet",
      "qwen-plus",
      "glm-4",
    ]) {
      const caps = inferModelCapabilities(modelId);
      expect(caps.supports_tools, modelId).toBe(true);
      expect(caps.supports_json, modelId).toBe(true);
    }
  });

  it("ORs stored false with inference for chat models", () => {
    const caps = effectiveModelCapabilities("deepseek-v4-flash", false, false);
    expect(caps.supports_tools).toBe(true);
    expect(caps.supports_json).toBe(true);
  });

  it("keeps stored true", () => {
    const caps = effectiveModelCapabilities("anything", true, true);
    expect(caps.supports_tools).toBe(true);
    expect(caps.supports_json).toBe(true);
  });

  it("rejects reasoning-only and non-chat models", () => {
    for (const modelId of [
      "deepseek-reasoner",
      "deepseek-r1",
      "text-embedding-3-small",
      "whisper-1",
      "dall-e-3",
      "qwq-32b",
    ]) {
      const caps = inferModelCapabilities(modelId);
      expect(caps.supports_tools, modelId).toBe(false);
      expect(caps.supports_json, modelId).toBe(false);
      expect(effectiveModelCapabilities(modelId, false, false).supports_tools, modelId).toBe(false);
    }
  });
});
