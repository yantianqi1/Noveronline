/**
 * LLM Module bindings panel.
 *
 * Lists available modules grouped by domain, with channel+model selectors
 * and save/unbind actions per row.
 */

import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { Save, Unlink, Zap } from "lucide-react";

import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import {
  Tooltip,
  TooltipContent,
  TooltipTrigger,
} from "@/components/ui/tooltip";
import type { LlmChannel, LlmModule } from "@/types/llm";
import {
  syncBindingDrafts,
  updateBindingDraft,
  type BindingDraft,
} from "./module-binding-drafts";
import { nextOpenBindingSelectKey } from "./binding-select-open-state";

/* ---------- Module group definitions ---------- */

interface ModuleGroupDef {
  label: string;
  prefixes: string[];
}

const MODULE_GROUPS: ModuleGroupDef[] = [
  {
    label: "种子分析",
    prefixes: [
      "story_ontology",
      "local_block_facts",
      "contextual_block_analysis",
      "anchor_point_summary",
      "entity_resolution",
      "sequential_reading",
      "character_agent_profile",
    ],
  },
  {
    label: "档案与图谱",
    prefixes: ["narrative_archives", "novel_chapter_summarizer"],
  },
  {
    label: "世界线推演",
    prefixes: ["worldline_", "parallel_world_config"],
  },
  { label: "写作", prefixes: ["writer_"] },
];

/* ---------- Props ---------- */

interface ModuleBindingsPanelProps {
  modules: LlmModule[];
  channels: LlmChannel[];
  savingKey: string;
  removingKey: string;
  batchSaving?: boolean;
  onOpenSelectKeyChange?: (openSelectKey: string) => void;
  onSaveBinding: (
    moduleKey: string,
    payload: { channel_key: string; model_id: string },
  ) => void;
  onBatchSaveBindings: (
    payload: { channel_key: string; model_id: string },
  ) => void;
  onRemoveBinding: (moduleKey: string) => void;
}

/* ---------- Component ---------- */

export default function ModuleBindingsPanel({
  modules,
  channels,
  savingKey,
  removingKey,
  batchSaving,
  onOpenSelectKeyChange,
  onSaveBinding,
  onBatchSaveBindings,
  onRemoveBinding,
}: ModuleBindingsPanelProps) {
  const [drafts, setDrafts] = useState<Record<string, BindingDraft>>({});
  const [dirtyKeys, setDirtyKeys] = useState<Set<string>>(new Set());
  const [openSelectKey, setOpenSelectKey] = useState("");
  const prevModulesJsonRef = useRef("");
  const [batchChannelKey, setBatchChannelKey] = useState("");
  const [batchModelId, setBatchModelId] = useState("");

  useEffect(() => {
    onOpenSelectKeyChange?.(openSelectKey);
  }, [onOpenSelectKeyChange, openSelectKey]);

  /* Sync drafts when modules actually change (not just on every poll re-render) */
  useEffect(() => {
    const modulesJson = JSON.stringify(
      modules.map((m) => [m.module_key, m.binding?.channel_key, m.binding?.model_id]),
    );
    if (modulesJson === prevModulesJsonRef.current) return;
    prevModulesJsonRef.current = modulesJson;

    const nextState = syncBindingDrafts({ modules, drafts, dirtyKeys });
    setDrafts(nextState.drafts);
    setDirtyKeys(nextState.dirtyKeys);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [modules]);

  /* Channel select options */
  const channelOptions = useMemo(
    () =>
      channels.map((ch) => ({
        label: ch.name,
        value: ch.channel_key,
        disabled: !ch.is_enabled,
      })),
    [channels],
  );

  /* Models for a given channel */
  function channelByKey(channelKey: string) {
    return channels.find((c) => c.channel_key === channelKey);
  }

  function availableModels(channelKey: string) {
    return channelByKey(channelKey)?.models || [];
  }

  function bindingSelectKey(moduleKey: string, field: "channel" | "model") {
    return `${moduleKey}:${field}`;
  }

  /* Group modules */
  const groupedModules = useMemo(() => {
    const assigned = new Set<string>();
    const groups: { label: string; modules: LlmModule[] }[] = [];

    for (const groupDef of MODULE_GROUPS) {
      const matched = modules.filter((m) => {
        if (assigned.has(m.module_key)) return false;
        return groupDef.prefixes.some(
          (p) => m.module_key.startsWith(p) || m.module_key === p,
        );
      });
      if (matched.length) {
        matched.forEach((m) => assigned.add(m.module_key));
        groups.push({ label: groupDef.label, modules: matched });
      }
    }
    const remaining = modules.filter((m) => !assigned.has(m.module_key));
    if (remaining.length) {
      groups.push({ label: "其他", modules: remaining });
    }
    return groups;
  }, [modules]);

  /* Draft patch */
  const applyDraftPatch = useCallback(
    (moduleKey: string, patch: Partial<BindingDraft>) => {
      const nextState = updateBindingDraft({
        drafts,
        dirtyKeys,
        moduleKey,
        patch,
      });
      setDrafts(nextState.drafts);
      setDirtyKeys(nextState.dirtyKeys);
    },
    [drafts, dirtyKeys],
  );

  function handleChannelChange(moduleKey: string, channelKey: string) {
    const models = availableModels(channelKey);
    const currentModelId = drafts[moduleKey]?.modelId || "";
    const hasCurrentModel = models.some((m) => m.model_id === currentModelId);
    applyDraftPatch(moduleKey, {
      channelKey,
      modelId: hasCurrentModel ? currentModelId : models[0]?.model_id || "",
    });
  }

  function handleModelChange(moduleKey: string, modelId: string) {
    applyDraftPatch(moduleKey, { modelId });
  }

  const handleSelectOpenChange = useCallback(
    (changedKey: string, open: boolean) => {
      setOpenSelectKey((currentKey) =>
        nextOpenBindingSelectKey(currentKey, changedKey, open),
      );
    },
    [],
  );

  function bindingStatusClass(module: LlmModule): string {
    if (!module.binding) return "unbound";
    return bindingWarning(module) ? "warn" : "ok";
  }

  function bindingWarning(module: LlmModule): string {
    if (!module.binding) return "";
    const channel = channelByKey(module.binding.channel_key);
    if (!channel) return "渠道已删除";
    if (!channel.is_enabled) return "渠道已停用";
    return "";
  }

  function saveDisabled(moduleKey: string): boolean {
    const draft = drafts[moduleKey];
    if (!draft?.channelKey || !draft?.modelId) return true;
    const channel = channelByKey(draft.channelKey);
    return !channel || !channel.is_enabled;
  }

  function handleSave(moduleKey: string) {
    if (saveDisabled(moduleKey)) return;
    const draft = drafts[moduleKey]!;
    onSaveBinding(moduleKey, {
      channel_key: draft.channelKey,
      model_id: draft.modelId,
    });
  }

  /* Resolve display names */
  function channelDisplayName(channelKey: string): string {
    return channelByKey(channelKey)?.name ?? channelKey;
  }

  /* Batch bind helpers */
  function batchModels() {
    return availableModels(batchChannelKey);
  }

  function handleBatchChannelChange(channelKey: string | null) {
    const key = channelKey ?? "";
    setBatchChannelKey(key);
    const models = availableModels(key);
    const keep = models.some((m) => m.model_id === batchModelId);
    setBatchModelId(keep ? batchModelId : models[0]?.model_id || "");
  }

  function handleBatchApply() {
    if (!batchChannelKey || !batchModelId) return;
    onBatchSaveBindings({ channel_key: batchChannelKey, model_id: batchModelId });
  }

  return (
    <Card>
      <CardHeader>
        <CardTitle>模块绑定</CardTitle>
      </CardHeader>

      <CardContent className="space-y-4">
        <p className="text-xs text-muted-foreground">
          为每个业务模块指定"渠道 + 模型"组合。
        </p>

        {/* ---------- Batch bind bar ---------- */}
        <div className="flex items-center gap-2 rounded-lg border border-dashed border-border bg-muted/30 px-3 py-2">
          <span className="shrink-0 text-xs font-medium text-muted-foreground">批量绑定</span>

          <Select
            value={batchChannelKey}
            onValueChange={handleBatchChannelChange}
          >
            <SelectTrigger size="sm" className="w-40 text-xs">
              <SelectValue placeholder="渠道">
                {batchChannelKey ? channelDisplayName(batchChannelKey) : undefined}
              </SelectValue>
            </SelectTrigger>
            <SelectContent>
              {channelOptions.map((opt) => (
                <SelectItem key={opt.value} value={opt.value} disabled={opt.disabled}>
                  {opt.label}
                </SelectItem>
              ))}
            </SelectContent>
          </Select>

          <Select
            value={batchModelId}
            onValueChange={(val) => setBatchModelId(val ?? "")}
          >
            <SelectTrigger size="sm" className="w-56 text-xs">
              <SelectValue placeholder="模型" />
            </SelectTrigger>
            <SelectContent>
              {batchModels().map((m) => (
                <SelectItem key={m.model_id} value={m.model_id}>
                  {m.model_id}
                </SelectItem>
              ))}
            </SelectContent>
          </Select>

          <Button
            size="xs"
            disabled={!batchChannelKey || !batchModelId || batchSaving}
            onClick={handleBatchApply}
          >
            <Zap className="size-3" />
            {batchSaving ? "绑定中…" : "全部绑定"}
          </Button>
        </div>

        {groupedModules.map((group) => (
          <div key={group.label} className="space-y-1">
            <h3 className="text-[11px] font-bold uppercase tracking-widest text-muted-foreground border-b border-border pb-1.5">
              {group.label}
            </h3>

            <div>
              {group.modules.map((module, idx) => {
                const draft = drafts[module.module_key];
                const statusCls = bindingStatusClass(module);
                const warning = bindingWarning(module);

                return (
                  <div
                    key={module.module_key}
                    className="grid grid-cols-[auto_1.2fr_1fr_2fr_auto] items-center gap-2 border-b border-border/30 px-2 py-2 last:border-b-0 hover:bg-muted/30 transition-colors max-md:grid-cols-[auto_1fr_1fr] max-md:gap-1.5"
                  >
                    {/* Row number */}
                    <span className="text-[11px] tabular-nums text-muted-foreground/60 w-4 text-right">
                      {idx + 1}
                    </span>

                    {/* Label + status dot */}
                    <div className="flex items-center gap-2 min-w-0 max-md:col-span-2">
                      <span
                        className={`size-1.5 shrink-0 rounded-full ${
                          statusCls === "ok"
                            ? "bg-green-600"
                            : statusCls === "warn"
                              ? "bg-amber-500"
                              : "bg-muted-foreground/30"
                        }`}
                      />
                      <span className="text-[13px] font-semibold truncate">
                        {module.label}
                      </span>
                      {warning && (
                        <Badge variant="destructive" className="text-[10px] h-4 px-1">
                          {warning}
                        </Badge>
                      )}
                    </div>

                    {/* Channel select */}
                    <Select
                      highlightItemOnHover={false}
                      value={draft?.channelKey || ""}
                      onOpenChange={(open) =>
                        handleSelectOpenChange(
                          bindingSelectKey(module.module_key, "channel"),
                          open,
                        )
                      }
                      onValueChange={(val) =>
                        handleChannelChange(module.module_key, val || "")
                      }
                    >
                      <SelectTrigger size="sm" className="w-full text-xs">
                        <SelectValue placeholder="渠道">
                          {draft?.channelKey ? channelDisplayName(draft.channelKey) : undefined}
                        </SelectValue>
                      </SelectTrigger>
                      <SelectContent>
                        {channelOptions.map((opt) => (
                          <SelectItem
                            key={opt.value}
                            value={opt.value}
                            disabled={opt.disabled}
                          >
                            {opt.label}
                          </SelectItem>
                        ))}
                      </SelectContent>
                    </Select>

                    {/* Model select */}
                    <Select
                      highlightItemOnHover={false}
                      value={draft?.modelId || ""}
                      onOpenChange={(open) =>
                        handleSelectOpenChange(
                          bindingSelectKey(module.module_key, "model"),
                          open,
                        )
                      }
                      onValueChange={(val) =>
                        handleModelChange(module.module_key, val || "")
                      }
                    >
                      <SelectTrigger size="sm" className="w-full text-xs">
                        <SelectValue placeholder="模型" />
                      </SelectTrigger>
                      <SelectContent>
                        {availableModels(draft?.channelKey || "").map((m) => (
                          <SelectItem key={m.model_id} value={m.model_id}>
                            {m.model_id}
                          </SelectItem>
                        ))}
                      </SelectContent>
                    </Select>

                    {/* Actions */}
                    <div className="flex gap-1 shrink-0 max-md:col-span-2 max-md:justify-end">
                      <Tooltip>
                        <TooltipTrigger
                          render={
                            <Button
                              size="xs"
                              disabled={
                                saveDisabled(module.module_key) ||
                                savingKey === module.module_key
                              }
                              onClick={() => handleSave(module.module_key)}
                            />
                          }
                        >
                          <Save className="size-3" />
                          保存
                        </TooltipTrigger>
                        <TooltipContent>保存当前绑定</TooltipContent>
                      </Tooltip>

                      <Tooltip>
                        <TooltipTrigger
                          render={
                            <Button
                              variant="outline"
                              size="xs"
                              disabled={
                                !module.binding ||
                                removingKey === module.module_key
                              }
                              onClick={() =>
                                onRemoveBinding(module.module_key)
                              }
                            />
                          }
                        >
                          <Unlink className="size-3" />
                          解绑
                        </TooltipTrigger>
                        <TooltipContent>解除模块绑定</TooltipContent>
                      </Tooltip>
                    </div>
                  </div>
                );
              })}
            </div>
          </div>
        ))}

        {modules.length === 0 && (
          <div className="rounded-lg border border-dashed border-border p-6 text-center text-sm text-muted-foreground">
            模块注册表为空。
          </div>
        )}
      </CardContent>
    </Card>
  );
}
