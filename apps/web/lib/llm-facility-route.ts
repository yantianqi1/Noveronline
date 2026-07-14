const CHANNEL_KEY_PATTERN = /^[a-z0-9]{12}$/;
export const DEFAULT_LLM_MODULE_KEY = "writer_composer";
const MODULE_PATH_ALIASES: Record<string, string> = {
  novel_chapter_summarizer: "summary",
  writer_book_planner: "plan",
  writer_composer: "compose",
  writer_dedup_extractor: "dedup",
  writer_reviewer: "review",
};
const MODULE_KEYS_BY_PATH = Object.fromEntries(
  Object.entries(MODULE_PATH_ALIASES).map(([moduleKey, pathSegment]) => [pathSegment, moduleKey]),
);

export function llmModuleSegment(moduleKey: string) {
  return moduleKey.trim().replace(/_/g, "-");
}

export function llmModuleKeyFromSegment(moduleSegment: string) {
  return moduleSegment.trim().replace(/-/g, "_");
}

export function llmModulePathSegment(moduleKey: string) {
  return MODULE_PATH_ALIASES[moduleKey] || llmModuleSegment(moduleKey);
}

export function llmModuleKeyFromPathSegment(pathSegment: string) {
  return MODULE_KEYS_BY_PATH[pathSegment] || llmModuleKeyFromSegment(pathSegment);
}

export function llmChannelKey(channelId: string) {
  const first = stableHash(channelId, 0x811c9dc5);
  const second = stableHash(channelId, 0x9e3779b9);
  return `${first.toString(36).padStart(7, "0")}${second.toString(36).padStart(7, "0")}`.slice(0, 12);
}

/** Stable DOM id / hash target for a channel management card. */
export function llmChannelAnchorId(channelId: string) {
  const trimmed = channelId.trim();
  if (!trimmed) {
    return "";
  }
  return `channel-${llmChannelKey(trimmed)}`;
}

export function resolveLLMChannelKey(channelIds: string[], channelKey: string) {
  const direct = channelIds.filter((channelId) => channelId === channelKey);
  if (direct.length === 1) {
    return direct[0];
  }
  const matches = channelIds.filter((channelId) => llmChannelKey(channelId) === channelKey);
  return matches.length === 1 ? matches[0] : undefined;
}

export function canonicalLLMFacilitySearch(input: URLSearchParams) {
  const result = new URLSearchParams(input);
  const channelValue = result.get("channel")?.trim() || result.get("channelId")?.trim() || "";
  const moduleValue = result.get("module")?.trim() || result.get("moduleKey")?.trim() || "";
  const runValue = result.get("run")?.trim() || result.get("runId")?.trim() || "";

  for (const key of ["channel", "channelId", "module", "moduleKey", "run", "runId"]) {
    result.delete(key);
  }
  if (channelValue) {
    result.set("channel", CHANNEL_KEY_PATTERN.test(channelValue) ? channelValue : llmChannelKey(channelValue));
  }
  if (moduleValue) {
    result.set("module", llmModuleSegment(llmModuleKeyFromSegment(moduleValue)));
  }
  if (runValue) {
    result.set("run", runValue);
  }

  for (const [key, value] of result.entries()) {
    if (!value.trim()) {
      result.delete(key);
    }
  }
  return result;
}

function stableHash(value: string, seed: number) {
  let hash = seed >>> 0;
  for (let index = 0; index < value.length; index += 1) {
    hash ^= value.charCodeAt(index);
    hash = Math.imul(hash, 0x01000193) >>> 0;
  }
  return hash;
}
