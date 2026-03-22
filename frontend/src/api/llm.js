import { del, get, patch, post, put } from "./http.js";

export function buildLlmChannelPath(channelKey = "") {
  return channelKey ? `/api/llm/channels/${channelKey}` : "/api/llm/channels";
}

export function buildLlmChannelSyncModelsPath(channelKey) {
  return `/api/llm/channels/${channelKey}/sync-models`;
}

export function buildLlmModuleBindingPath(moduleKey) {
  return `/api/llm/module-bindings/${moduleKey}`;
}

export function getLlmSettings() {
  return get("/api/llm/settings");
}

export function createLlmChannel(payload) {
  return post(buildLlmChannelPath(), payload);
}

export function updateLlmChannel(channelKey, payload) {
  return patch(buildLlmChannelPath(channelKey), payload);
}

export function deleteLlmChannel(channelKey) {
  return del(buildLlmChannelPath(channelKey));
}

export function syncLlmChannelModels(channelKey) {
  return post(buildLlmChannelSyncModelsPath(channelKey), {});
}

export function updateLlmModuleBinding(moduleKey, payload) {
  return put(buildLlmModuleBindingPath(moduleKey), payload);
}

export function deleteLlmModuleBinding(moduleKey) {
  return del(buildLlmModuleBindingPath(moduleKey));
}
