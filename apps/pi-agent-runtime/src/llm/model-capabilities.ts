/**
 * Infer LLM capability flags when catalog metadata still carries the FALSE default.
 *
 * Aligns with apps/api/internal/llm/model_capabilities.go and the Python runtime:
 * OpenAI-compatible chat models are treated as tool/JSON capable; only known
 * non-chat or reasoning-only ids stay unsupported. Callers OR stored catalog
 * bits with inference so a false column default never blocks real chat models.
 */

export type InferredModelCapabilities = {
  supports_json: boolean;
  supports_tools: boolean;
};

export function normalizeModelId(modelId: string | null | undefined): string {
  if (typeof modelId !== "string") {
    return "";
  }
  let trimmed = modelId.trim();
  if (!trimmed) {
    return "";
  }
  while (trimmed.startsWith("[")) {
    const end = trimmed.indexOf("]");
    if (end <= 0) {
      break;
    }
    trimmed = trimmed.slice(end + 1).trim();
  }
  return trimmed.toLowerCase().replace(/\s+/g, "");
}

export function inferModelCapabilities(modelId: string | null | undefined): InferredModelCapabilities {
  const normalized = normalizeModelId(modelId);
  if (!normalized) {
    return { supports_json: false, supports_tools: false };
  }
  if (isNonChatModel(normalized) || isReasoningOnlyModel(normalized)) {
    return { supports_json: false, supports_tools: false };
  }
  return { supports_json: true, supports_tools: true };
}

export function effectiveModelCapabilities(
  modelId: string | null | undefined,
  storedJson: boolean,
  storedTools: boolean,
): InferredModelCapabilities {
  const inferred = inferModelCapabilities(modelId);
  return {
    supports_json: storedJson || inferred.supports_json,
    supports_tools: storedTools || inferred.supports_tools,
  };
}

function isReasoningOnlyModel(normalized: string): boolean {
  if (
    normalized.includes("deepseek") &&
    (normalized.includes("reasoner") ||
      normalized.includes("-r1") ||
      normalized.endsWith("r1") ||
      normalized.includes("r1-"))
  ) {
    if (
      normalized.includes("reasoner") ||
      normalized.includes("deepseek-r1") ||
      normalized.includes("deepseek_r1") ||
      normalized.includes("/r1")
    ) {
      return true;
    }
  }
  if (normalized.startsWith("qwq") || normalized.includes("-qwq")) {
    return true;
  }
  return false;
}

function isNonChatModel(normalized: string): boolean {
  const tokens = [
    "embedding",
    "embed",
    "whisper",
    "tts",
    "dall-e",
    "dalle",
    "gpt-image",
    "image-",
    "-image",
    "moderation",
    "realtime",
    "audio",
    "speech",
    "transcribe",
    "asr",
  ];
  return tokens.some((token) => normalized.includes(token));
}
