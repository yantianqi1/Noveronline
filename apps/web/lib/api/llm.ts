import type { LLMChannel, LLMModel, LLMModule, LLMModuleBinding } from "@/lib/api/llm-types";

/**
 * Pure domain logic for the LLM settings surface: grouping the module registry
 * into its fixed workbench families, and resolving each module's effective
 * binding state (project override vs inherited vs unbound). Framework-free so
 * it can be unit-tested in isolation.
 */

/** Display order + Chinese labels for the module groups the registry emits. */
export const LLM_GROUP_ORDER: { key: string; label: string; hint: string }[] = [
  { key: "Seed / Graph", label: "解析与图谱", hint: "阅读原文、抽取本体与故事图谱" },
  { key: "Archive / Assets", label: "档案与资产", hint: "叙事档案、素材入库与检索" },
  { key: "Character Console", label: "角色控制", hint: "角色对话与状态更新" },
  { key: "Worldline", label: "世界线", hint: "单世界推演与各角色行动" },
  { key: "Writer", label: "写作台", hint: "检索规划、成稿、审校与提取" },
];

export type ModuleGroup = {
  key: string;
  label: string;
  hint: string;
  modules: LLMModule[];
};

/** Group registry modules into the fixed family order, preserving registry order within a group. */
export function groupModules(modules: LLMModule[]): ModuleGroup[] {
  const byGroup = new Map<string, LLMModule[]>();
  for (const mod of modules) {
    const list = byGroup.get(mod.group) ?? [];
    list.push(mod);
    byGroup.set(mod.group, list);
  }
  const groups: ModuleGroup[] = [];
  for (const meta of LLM_GROUP_ORDER) {
    const list = byGroup.get(meta.key);
    if (list && list.length > 0) {
      groups.push({ key: meta.key, label: meta.label, hint: meta.hint, modules: list });
      byGroup.delete(meta.key);
    }
  }
  // Any group we don't have display metadata for still surfaces, at the end.
  for (const [key, list] of byGroup) {
    groups.push({ key, label: key, hint: "", modules: list });
  }
  return groups;
}

export type BindingState =
  | { kind: "unbound" }
  | { kind: "inherited"; binding: LLMModuleBinding }
  | { kind: "project"; binding: LLMModuleBinding };

/** Resolve one module's effective binding from the merged binding list. */
export function bindingFor(moduleKey: string, bindings: LLMModuleBinding[]): BindingState {
  // The Go list already ranks project scope first per module, but we re-derive
  // defensively so the UI never depends on upstream ordering.
  const candidates = bindings.filter((b) => b.module_key === moduleKey);
  if (candidates.length === 0) return { kind: "unbound" };
  const project = candidates.find((b) => b.scope === "project");
  if (project) return { kind: "project", binding: project };
  return { kind: "inherited", binding: candidates[0] };
}

export type BindingSummary = {
  total: number;
  bound: number;
  overridden: number;
  unbound: number;
};

/** Roll up binding coverage across every module in the registry. */
export function summarizeBindings(
  modules: LLMModule[],
  bindings: LLMModuleBinding[],
): BindingSummary {
  let bound = 0;
  let overridden = 0;
  for (const mod of modules) {
    const state = bindingFor(mod.module_key, bindings);
    if (state.kind !== "unbound") bound += 1;
    if (state.kind === "project") overridden += 1;
  }
  return { total: modules.length, bound, overridden, unbound: modules.length - bound };
}

/** Only enabled channels can be a binding target. */
export function enabledChannels(channels: LLMChannel[]): LLMChannel[] {
  return channels.filter((c) => c.enabled);
}

/** Look up a model's id list for a channel from the fetched catalog map. */
export function modelsForChannel(
  catalog: Record<string, LLMModel[]>,
  channelId: string,
): LLMModel[] {
  return catalog[channelId] ?? [];
}
