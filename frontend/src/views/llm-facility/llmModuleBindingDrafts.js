export function createBindingDraft(module) {
  return {
    channelKey: module?.binding?.channel_key || "",
    modelId: module?.binding?.model_id || "",
  };
}

export function draftMatchesBinding(draft, binding) {
  return (draft?.channelKey || "") === (binding?.channel_key || "")
    && (draft?.modelId || "") === (binding?.model_id || "");
}

export function syncBindingDrafts({
  modules = [],
  drafts = {},
  dirtyKeys = new Set(),
} = {}) {
  const nextDrafts = {};
  const nextDirtyKeys = new Set();

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
  dirtyKeys = new Set(),
  moduleKey = "",
  patch = {},
} = {}) {
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
