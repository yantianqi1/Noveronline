/**
 * Module binding draft state management.
 *
 * Pure functions for tracking unsaved binding changes. Ported from
 * src-vue/views/llm-facility/llmModuleBindingDrafts.js.
 */

import type { LlmModule, LlmModuleBindingInfo } from "@/types/llm";

export interface BindingDraft {
  channelKey: string;
  modelId: string;
}

export interface BindingDraftState {
  drafts: Record<string, BindingDraft>;
  dirtyKeys: Set<string>;
}

export function createBindingDraft(module: LlmModule): BindingDraft {
  return {
    channelKey: module?.binding?.channel_key || "",
    modelId: module?.binding?.model_id || "",
  };
}

export function draftMatchesBinding(
  draft: BindingDraft | undefined,
  binding: LlmModuleBindingInfo | null | undefined,
): boolean {
  return (
    (draft?.channelKey || "") === (binding?.channel_key || "") &&
    (draft?.modelId || "") === (binding?.model_id || "")
  );
}

export function syncBindingDrafts({
  modules = [],
  drafts = {},
  dirtyKeys = new Set<string>(),
}: {
  modules?: LlmModule[];
  drafts?: Record<string, BindingDraft>;
  dirtyKeys?: Set<string>;
} = {}): BindingDraftState {
  const nextDrafts: Record<string, BindingDraft> = {};
  const nextDirtyKeys = new Set<string>();

  for (const module of modules) {
    const moduleKey = module.module_key;
    const syncedDraft = createBindingDraft(module);
    const currentDraft = drafts[moduleKey];
    const isDirty = dirtyKeys.has(moduleKey);

    if (!currentDraft) {
      nextDrafts[moduleKey] = syncedDraft;
      continue;
    }
    if (isDirty && !draftMatchesBinding(currentDraft, module.binding)) {
      nextDrafts[moduleKey] = currentDraft;
      nextDirtyKeys.add(moduleKey);
      continue;
    }
    nextDrafts[moduleKey] = syncedDraft;
  }

  return {
    drafts: nextDrafts,
    dirtyKeys: nextDirtyKeys,
  };
}

export function updateBindingDraft({
  drafts = {},
  dirtyKeys = new Set<string>(),
  moduleKey = "",
  patch = {},
}: {
  drafts?: Record<string, BindingDraft>;
  dirtyKeys?: Set<string>;
  moduleKey?: string;
  patch?: Partial<BindingDraft>;
} = {}): BindingDraftState {
  return {
    drafts: {
      ...drafts,
      [moduleKey]: {
        ...(drafts[moduleKey] || { channelKey: "", modelId: "" }),
        ...patch,
      },
    },
    dirtyKeys: new Set([...dirtyKeys, moduleKey]),
  };
}
