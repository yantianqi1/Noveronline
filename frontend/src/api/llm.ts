/**
 * LLM Facility API client — channel management, module bindings, activity.
 */

import { del, get, patch, post, put } from "@/api/http";
import type { ApiResponse } from "@/api/http";

/* ---------- Path helpers ---------- */

export function buildLlmChannelPath(channelKey = ""): string {
  return channelKey ? `/api/llm/channels/${channelKey}` : "/api/llm/channels";
}

export function buildLlmChannelSyncModelsPath(channelKey: string): string {
  return `/api/llm/channels/${channelKey}/sync-models`;
}

export function buildLlmModuleBindingPath(moduleKey: string): string {
  return `/api/llm/module-bindings/${moduleKey}`;
}

/* ---------- Settings ---------- */

export function getLlmSettings(): Promise<ApiResponse> {
  return get("/api/llm/settings");
}

/* ---------- Channel CRUD ---------- */

export function createLlmChannel(payload: unknown): Promise<ApiResponse> {
  return post(buildLlmChannelPath(), payload);
}

export function updateLlmChannel(channelKey: string, payload: unknown): Promise<ApiResponse> {
  return patch(buildLlmChannelPath(channelKey), payload);
}

export function deleteLlmChannel(channelKey: string): Promise<ApiResponse> {
  return del(buildLlmChannelPath(channelKey));
}

export function syncLlmChannelModels(channelKey: string): Promise<ApiResponse> {
  return post(buildLlmChannelSyncModelsPath(channelKey), {});
}

/* ---------- Module bindings ---------- */

export function updateLlmModuleBinding(
  moduleKey: string,
  payload: unknown,
): Promise<ApiResponse> {
  return put(buildLlmModuleBindingPath(moduleKey), payload);
}

export function deleteLlmModuleBinding(moduleKey: string): Promise<ApiResponse> {
  return del(buildLlmModuleBindingPath(moduleKey));
}

/* ---------- Activity ---------- */

export function getLlmActivity(): Promise<ApiResponse> {
  return get("/api/llm/activity");
}
