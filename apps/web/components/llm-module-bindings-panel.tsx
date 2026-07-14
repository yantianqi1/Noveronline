"use client";

import { useEffect, useMemo, useRef, useState, useTransition } from "react";

import { Bi } from "./bilingual-text";
import type { LLMChannelRecord, LLMModelRecord, LLMModuleBindingRecord, LLMModuleRecord } from "../lib/api";
import { type Locale, tx } from "../lib/locale";
import { moduleLabel as sharedModuleLabel } from "../lib/user-facing-copy";

type BindingDraft = {
  channelId: string;
  modelId: string;
  maxTokens: string;
};

type BatchScope = "selected" | "group" | "all";

type FilterMode = "all" | "unbound" | "project";

type ModuleGroup = {
  id: string;
  label: [string, string];
  modules: LLMModuleRecord[];
};

export type LLMBindingActionResult = {
  status: "success" | "error";
  code: string;
  message: string;
  appliedModuleKeys: string[];
  bindings?: LLMModuleBindingRecord[];
};

type LLMModuleBindingsPanelProps = {
  locale: Locale;
  modules: LLMModuleRecord[];
  channels: LLMChannelRecord[];
  channelModels: Record<string, LLMModelRecord[]>;
  effectiveBindings: Record<string, LLMModuleBindingRecord>;
  projectBindings: Record<string, LLMModuleBindingRecord>;
  canManageBindings: boolean;
  bindingStatus: string;
  bindingCode: string;
  bindingMessage: string;
  bindModuleAction: (formData: FormData) => Promise<LLMBindingActionResult>;
  batchBindModuleAction: (formData: FormData) => Promise<LLMBindingActionResult>;
  clearBindingAction: (formData: FormData) => Promise<LLMBindingActionResult>;
};

/** Suggested output budget for Seed / long-form modules when model context_window is missing. */
const SUGGESTED_MAX_TOKENS = "12800";
const FEEDBACK_HOLD_MS = 4200;
const HIGHLIGHT_MS = 1100;

const MODULE_GROUPS: Array<{ id: string; label: [string, string]; prefixes: string[] }> = [
  {
    id: "seed",
    label: ["种子分析", "Seed analysis"],
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
    id: "archives",
    label: ["档案与图谱", "Archives & graph"],
    prefixes: ["narrative_archives", "novel_chapter_summarizer", "graph_bond_generator", "asset_ingestion"],
  },
  {
    id: "worldline",
    label: ["世界线推演", "Worldline"],
    prefixes: ["worldline_", "parallel_world_config"],
  },
  { id: "writer", label: ["写作", "Writer"], prefixes: ["writer_"] },
];

export function LLMModuleBindingsPanel({
  locale,
  modules,
  channels,
  channelModels,
  effectiveBindings: serverEffectiveBindings,
  projectBindings: serverProjectBindings,
  canManageBindings,
  bindingStatus: initialBindingStatus,
  bindingCode: initialBindingCode,
  bindingMessage: initialBindingMessage,
  bindModuleAction,
  batchBindModuleAction,
  clearBindingAction: _clearBindingAction,
}: LLMModuleBindingsPanelProps) {
  void _clearBindingAction;
  const [effectiveBindings, setEffectiveBindings] = useState(serverEffectiveBindings);
  const [projectBindings, setProjectBindings] = useState(serverProjectBindings);
  const [drafts, setDrafts] = useState<Record<string, BindingDraft>>(() => (
    buildInitialDrafts(modules, serverEffectiveBindings, channels, channelModels)
  ));
  const batchSeedRef = useRef<ReturnType<typeof preferredBatchSelection> | null>(null);
  if (batchSeedRef.current === null) {
    batchSeedRef.current = preferredBatchSelection(
      channels,
      channelModels,
      serverProjectBindings,
      serverEffectiveBindings,
    );
  }
  const [batchChannelId, setBatchChannelId] = useState(batchSeedRef.current.channelId);
  const [batchModelId, setBatchModelId] = useState(batchSeedRef.current.modelId);
  // max_tokens stays the fixed product default; not editable in this author UI.
  const batchMaxTokens = SUGGESTED_MAX_TOKENS;
  const [searchQuery, setSearchQuery] = useState("");
  const [filterMode, setFilterMode] = useState<FilterMode>("all");
  const [groupFilterId, setGroupFilterId] = useState("");
  const [listOpen, setListOpen] = useState(false);
  const [selectedKeys, setSelectedKeys] = useState<Set<string>>(() => new Set());
  const [feedback, setFeedback] = useState(() => ({
    status: initialBindingStatus,
    code: initialBindingCode,
    message: initialBindingMessage,
  }));
  const [feedbackPulse, setFeedbackPulse] = useState(0);
  const [highlightedKeys, setHighlightedKeys] = useState<Set<string>>(() => new Set());
  const [pendingScope, setPendingScope] = useState<BatchScope | "row" | "clear" | "">("");
  const [isPending, startTransition] = useTransition();
  const feedbackTimer = useRef<number | undefined>(undefined);
  const highlightTimer = useRef<number | undefined>(undefined);
  const serverBindingSignature = useMemo(
    () => bindingMapSignature(serverEffectiveBindings, serverProjectBindings),
    [serverEffectiveBindings, serverProjectBindings],
  );
  const lastServerSignature = useRef(serverBindingSignature);

  useEffect(() => {
    if (lastServerSignature.current === serverBindingSignature) return;
    lastServerSignature.current = serverBindingSignature;
    setEffectiveBindings(serverEffectiveBindings);
    setProjectBindings(serverProjectBindings);
    setDrafts((current) => mergeDraftsFromBindings(
      current,
      modules,
      serverEffectiveBindings,
      channels,
      channelModels,
    ));
    // Keep the sticky batch toolbar aligned with the saved project binding majority
    // so refresh/navigation does not look like the bound model "reset" to models[0].
    const preferred = preferredBatchSelection(
      channels,
      channelModels,
      serverProjectBindings,
      serverEffectiveBindings,
    );
    setBatchChannelId(preferred.channelId);
    setBatchModelId(preferred.modelId);
  }, [channelModels, channels, modules, serverBindingSignature, serverEffectiveBindings, serverProjectBindings]);

  useEffect(() => () => {
    if (feedbackTimer.current !== undefined) window.clearTimeout(feedbackTimer.current);
    if (highlightTimer.current !== undefined) window.clearTimeout(highlightTimer.current);
  }, []);

  const enabledChannels = useMemo(
    () => channels.filter((channel) => channel.enabled),
    [channels],
  );

  const groupedModules = useMemo(() => groupModules(modules), [modules]);

  const moduleGroupByKey = useMemo(() => {
    const map = new Map<string, ModuleGroup>();
    for (const group of groupedModules) {
      for (const module of group.modules) {
        map.set(module.module_key, group);
      }
    }
    return map;
  }, [groupedModules]);

  const filteredModules = useMemo(() => {
    const query = searchQuery.trim().toLowerCase();
    return modules.filter((module) => {
      if (groupFilterId) {
        const group = moduleGroupByKey.get(module.module_key);
        if (!group || group.id !== groupFilterId) return false;
      }
      if (!matchesFilter(module, filterMode, projectBindings, effectiveBindings)) {
        return false;
      }
      if (!query) return true;
      const label = moduleDisplayLabel(locale, module).toLowerCase();
      const groupLabel = moduleGroupByKey.get(module.module_key)?.label;
      const groupText = groupLabel
        ? `${groupLabel[0]} ${groupLabel[1]}`.toLowerCase()
        : "";
      return (
        label.includes(query)
        || module.module_key.toLowerCase().includes(query)
        || groupText.includes(query)
      );
    });
  }, [
    effectiveBindings,
    filterMode,
    groupFilterId,
    locale,
    moduleGroupByKey,
    modules,
    projectBindings,
    searchQuery,
  ]);

  const visibleModuleKeys = useMemo(
    () => filteredModules.map((module) => module.module_key),
    [filteredModules],
  );

  const activeGroup = useMemo(
    () => groupedModules.find((group) => group.id === groupFilterId),
    [groupFilterId, groupedModules],
  );

  const boundProjectCount = Object.keys(projectBindings).length;
  const unboundCount = modules.filter((module) => !effectiveBindings[module.module_key]).length;
  const bindingStatusClass = feedback.status === "success"
    ? "success-box"
    : feedback.status === "error"
      ? "error-box"
      : "";
  const selectedCount = selectedKeys.size;
  const batchTargetsValid = Boolean(
    batchChannelId
    && batchModelId
    && (batchMaxTokens.trim() === "" || isPositiveIntString(batchMaxTokens)),
  );
  const busy = isPending || Boolean(pendingScope);

  function modelsForChannel(channelId: string) {
    return channelModels[channelId] || [];
  }

  function updateDraft(moduleKey: string, patch: Partial<BindingDraft>) {
    setDrafts((current) => {
      const previous = current[moduleKey] || { channelId: "", modelId: "", maxTokens: "" };
      const next = { ...previous, ...patch };
      if (patch.channelId && patch.channelId !== previous.channelId) {
        const models = modelsForChannel(patch.channelId);
        const keepCurrent = models.some((model) => model.model_id === previous.modelId);
        next.modelId = keepCurrent ? previous.modelId : models[0]?.model_id || "";
      }
      return { ...current, [moduleKey]: next };
    });
  }

  function handleBatchChannelChange(channelId: string) {
    setBatchChannelId(channelId);
    const models = modelsForChannel(channelId);
    setBatchModelId((current) => (
      models.some((model) => model.model_id === current) ? current : models[0]?.model_id || ""
    ));
  }

  function rowCanSave(moduleKey: string) {
    const draft = drafts[moduleKey];
    if (!draft?.channelId || !draft.modelId) return false;
    const channel = channels.find((item) => item.channel_id === draft.channelId);
    if (!channel?.enabled) return false;
    if (!modelsForChannel(draft.channelId).some((model) => model.model_id === draft.modelId)) return false;
    return true;
  }

  function resolvedMaxTokens(moduleKey: string) {
    const draft = drafts[moduleKey];
    if (draft?.maxTokens.trim() && isPositiveIntString(draft.maxTokens)) {
      return draft.maxTokens.trim();
    }
    return SUGGESTED_MAX_TOKENS;
  }

  function setSelectionForKeys(keys: string[], selected: boolean) {
    setSelectedKeys((current) => {
      const next = new Set(current);
      for (const key of keys) {
        if (selected) next.add(key);
        else next.delete(key);
      }
      return next;
    });
  }

  function toggleKey(moduleKey: string) {
    setSelectedKeys((current) => {
      const next = new Set(current);
      if (next.has(moduleKey)) next.delete(moduleKey);
      else next.add(moduleKey);
      return next;
    });
  }

  function groupSummary(group: ModuleGroup) {
    let bound = 0;
    let unbound = 0;
    for (const module of group.modules) {
      if (projectBindings[module.module_key] || effectiveBindings[module.module_key]) {
        bound += 1;
      } else {
        unbound += 1;
      }
    }
    return { bound, unbound, total: group.modules.length };
  }

  function moduleKeysForScope(scope: BatchScope): string[] {
    if (scope === "all") {
      return modules.map((module) => module.module_key);
    }
    if (scope === "group") {
      return activeGroup ? activeGroup.modules.map((module) => module.module_key) : [];
    }
    return Array.from(selectedKeys);
  }

  function scopeDisabled(scope: BatchScope) {
    if (busy || !batchTargetsValid) return true;
    if (scope === "selected") return selectedCount === 0;
    if (scope === "group") return !activeGroup || moduleKeysForScope("group").length === 0;
    return modules.length === 0;
  }

  function showFeedback(next: { status: string; code: string; message: string }) {
    setFeedback(next);
    setFeedbackPulse((value) => value + 1);
    if (feedbackTimer.current !== undefined) window.clearTimeout(feedbackTimer.current);
    if (next.status === "success") {
      feedbackTimer.current = window.setTimeout(() => {
        setFeedback((current) => (
          current.status === "success" ? { status: "", code: "", message: "" } : current
        ));
      }, FEEDBACK_HOLD_MS);
    }
  }

  function flashRows(keys: string[]) {
    if (keys.length === 0) return;
    setHighlightedKeys(new Set(keys));
    if (highlightTimer.current !== undefined) window.clearTimeout(highlightTimer.current);
    highlightTimer.current = window.setTimeout(() => setHighlightedKeys(new Set()), HIGHLIGHT_MS);
  }

  function applyBindingMaps(items: LLMModuleBindingRecord[] | undefined) {
    if (!items) return;
    const nextEffective = Object.fromEntries(items.map((item) => [item.module_key, item]));
    const nextProject = Object.fromEntries(
      items.filter((item) => item.scope === "project").map((item) => [item.module_key, item]),
    );
    setEffectiveBindings(nextEffective);
    setProjectBindings(nextProject);
    setDrafts((current) => mergeDraftsFromBindings(
      current,
      modules,
      nextEffective,
      channels,
      channelModels,
    ));
  }

  function optimisticBind(moduleKeys: string[], channelId: string, modelId: string, maxTokens: string) {
    const channel = channels.find((item) => item.channel_id === channelId);
    const model = modelsForChannel(channelId).find((item) => item.model_id === modelId);
    const settings: Record<string, unknown> = {};
    if (maxTokens.trim() && isPositiveIntString(maxTokens)) {
      settings.max_tokens = Number.parseInt(maxTokens.trim(), 10);
    }
    const stamp = new Date().toISOString();
    setDrafts((current) => {
      const next = { ...current };
      for (const key of moduleKeys) {
        next[key] = {
          channelId,
          modelId,
          maxTokens: maxTokens.trim(),
        };
      }
      return next;
    });
    setEffectiveBindings((current) => {
      const next = { ...current };
      for (const key of moduleKeys) {
        next[key] = optimisticProjectBinding({
          previous: current[key],
          moduleKey: key,
          channelId,
          modelId,
          channel,
          model,
          settingsPatch: settings,
          clearEmptySettings: false,
          maxTokens: maxTokens.trim(),
          stamp,
        });
      }
      return next;
    });
    setProjectBindings((current) => {
      const next = { ...current };
      for (const key of moduleKeys) {
        next[key] = optimisticProjectBinding({
          previous: current[key] || effectiveBindings[key],
          moduleKey: key,
          channelId,
          modelId,
          channel,
          model,
          settingsPatch: settings,
          clearEmptySettings: false,
          maxTokens: maxTokens.trim(),
          stamp,
        });
      }
      return next;
    });
  }

  function runBindingAction(
    kind: BatchScope | "row" | "clear",
    action: () => Promise<LLMBindingActionResult>,
    options?: {
      optimistic?: () => void;
      highlightKeys?: string[];
    },
  ) {
    if (busy) return;
    setPendingScope(kind);
    options?.optimistic?.();
    if (options?.highlightKeys?.length) flashRows(options.highlightKeys);
    startTransition(() => {
      void action()
        .then((result) => {
          applyBindingMaps(result.bindings);
          showFeedback({
            status: result.status,
            code: result.code,
            message: result.message,
          });
          if (result.status === "success" && result.appliedModuleKeys.length > 0) {
            flashRows(result.appliedModuleKeys);
          }
        })
        .catch(() => {
          showFeedback({
            status: "error",
            code: "LLM_BINDING_UPDATE_FAILED",
            message: tx(locale, "绑定未能完成，请重试。", "Binding could not finish. Please retry."),
          });
        })
        .finally(() => {
          setPendingScope("");
        });
    });
  }

  function handleBatchApply(scope: BatchScope) {
    if (scopeDisabled(scope)) return;
    const keys = moduleKeysForScope(scope);
    const formData = new FormData();
    formData.set("channelId", batchChannelId);
    formData.set("modelId", batchModelId);
    formData.set("maxTokens", batchMaxTokens.trim());
    formData.set("scope", scope);
    if (scope === "group" && activeGroup) formData.set("groupId", activeGroup.id);
    for (const key of keys) formData.append("moduleKeys", key);
    runBindingAction(scope, () => batchBindModuleAction(formData), {
      optimistic: () => optimisticBind(keys, batchChannelId, batchModelId, batchMaxTokens.trim()),
      highlightKeys: keys,
    });
  }

  function handleRowSave(moduleKey: string) {
    if (!rowCanSave(moduleKey) || busy) return;
    const draft = drafts[moduleKey];
    if (!draft) return;
    const maxTokens = resolvedMaxTokens(moduleKey);
    const formData = new FormData();
    formData.set("moduleKey", moduleKey);
    formData.set("channelId", draft.channelId);
    formData.set("modelId", draft.modelId);
    formData.set("maxTokens", maxTokens);
    runBindingAction("row", () => bindModuleAction(formData), {
      optimistic: () => optimisticBind([moduleKey], draft.channelId, draft.modelId, maxTokens),
      highlightKeys: [moduleKey],
    });
  }

  const primaryBatchScope: BatchScope = selectedCount > 0
    ? "selected"
    : activeGroup
      ? "group"
      : "all";
  const primaryBatchPending = pendingScope === primaryBatchScope;

  return (
    <div className="llm-bindings-panel binding-stack" data-busy={busy ? "true" : "false"}>
      <div className="llm-bindings-summary" aria-label={tx(locale, "绑定统计", "Binding summary")}>
        <span>
          <Bi zh="已绑定" en="Bound" /> {boundProjectCount}/{modules.length}
        </span>
        {unboundCount > 0 ? (
          <span data-tone="muted">
            <Bi zh="未绑定" en="Unbound" /> {unboundCount}
          </span>
        ) : null}
        {selectedCount > 0 ? (
          <span>
            <Bi zh="已选" en="Selected" /> {selectedCount}
          </span>
        ) : null}
      </div>

      {feedback.status ? (
        <p
          className={`form-status llm-bindings-feedback ${bindingStatusClass}`}
          data-code={feedback.code}
          data-status={feedback.status}
          data-pulse={feedbackPulse}
          role={feedback.status === "error" ? "alert" : "status"}
        >
          {feedback.message}
        </p>
      ) : null}

      {!canManageBindings ? (
        <p className="form-hint" role="status">
          <Bi
            zh="仅工作区管理员可修改绑定。下方显示当前生效配置。"
            en="Only workspace admins can change bindings. The table below shows the effective configuration."
          />
        </p>
      ) : null}

      {canManageBindings && enabledChannels.length > 0 ? (
        <div className="llm-bindings-batch-bar binding-form" data-sticky="true" data-busy={busy ? "true" : "false"}>
          <label className="llm-bindings-field">
            <span><Bi zh="渠道" en="Channel" /></span>
            <select
              name="channelId"
              value={batchChannelId}
              disabled={busy}
              onChange={(event) => handleBatchChannelChange(event.target.value)}
            >
              {enabledChannels.map((channel) => (
                <option key={channel.channel_id} value={channel.channel_id}>
                  {channel.name}
                </option>
              ))}
            </select>
          </label>
          <label className="llm-bindings-field">
            <span><Bi zh="模型" en="Model" /></span>
            <select
              name="modelId"
              value={batchModelId}
              onChange={(event) => setBatchModelId(event.target.value)}
              disabled={busy || modelsForChannel(batchChannelId).length === 0}
            >
              {modelsForChannel(batchChannelId).map((model) => (
                <option key={model.model_id} value={model.model_id}>
                  {model.model_id}
                </option>
              ))}
            </select>
          </label>
          <input type="hidden" name="maxTokens" value={batchMaxTokens} />
          <div className="llm-bindings-batch-actions">
            <button
              className="submit-button"
              data-tone="primary"
              data-pending={primaryBatchPending ? "true" : "false"}
              disabled={scopeDisabled(primaryBatchScope)}
              type="button"
              onClick={() => handleBatchApply(primaryBatchScope)}
            >
              {primaryBatchPending
                ? <Bi zh="绑定中…" en="Binding…" />
                : batchScopeLabel(primaryBatchScope)}
            </button>
            {primaryBatchScope !== "all" ? (
              <button
                className="submit-button"
                data-tone="secondary"
                data-pending={pendingScope === "all" ? "true" : "false"}
                disabled={scopeDisabled("all")}
                type="button"
                onClick={() => handleBatchApply("all")}
              >
                {pendingScope === "all"
                  ? <Bi zh="绑定中…" en="Binding…" />
                  : <Bi zh="应用到全部" en="Apply to all" />}
              </button>
            ) : null}
          </div>
        </div>
      ) : null}

      {enabledChannels.length === 0 ? (
        <p className="form-hint" role="alert">
          <Bi zh="暂无可用渠道，请先在管理区创建并同步模型。" en="No channels are available. Create and sync models in the admin section first." />
        </p>
      ) : null}

      <details
        className="llm-bindings-module-list"
        open={listOpen || unboundCount > 0 || selectedCount > 0}
        onToggle={(event) => setListOpen((event.currentTarget as HTMLDetailsElement).open)}
      >
        <summary className="llm-bindings-module-list-summary">
          <span>
            <strong><Bi zh="模块绑定列表" en="Module binding list" /></strong>
            <small>
              <Bi
                zh={`${boundProjectCount}/${modules.length} 已绑定 · 点击展开调整`}
                en={`${boundProjectCount}/${modules.length} bound · expand to adjust`}
              />
            </small>
          </span>
        </summary>

        <div className="llm-bindings-module-list-body">
          <div className="llm-bindings-toolbar">
            <label className="llm-bindings-field llm-bindings-search">
              <span className="sr-only"><Bi zh="搜索" en="Search" /></span>
              <input
                aria-label={tx(locale, "搜索模块", "Search modules")}
                placeholder={tx(locale, "搜索模块…", "Search modules…")}
                type="search"
                value={searchQuery}
                onChange={(event) => setSearchQuery(event.target.value)}
              />
            </label>
            <label className="llm-bindings-field">
              <span className="sr-only"><Bi zh="筛选" en="Filter" /></span>
              <select
                aria-label={tx(locale, "筛选绑定状态", "Filter binding status")}
                value={filterMode}
                onChange={(event) => setFilterMode(event.target.value as FilterMode)}
              >
                <option value="all">{tx(locale, "全部", "All")}</option>
                <option value="unbound">{tx(locale, "未绑定", "Unbound")}</option>
                <option value="project">{tx(locale, "已绑定", "Bound")}</option>
              </select>
            </label>
          </div>

          <div
            className="llm-bindings-group-chips"
            role="tablist"
            aria-label={tx(locale, "按业务分组筛选", "Filter by capability group")}
          >
            <button
              type="button"
              role="tab"
              className="llm-bindings-group-chip"
              aria-selected={!groupFilterId}
              data-active={!groupFilterId ? "true" : "false"}
              onClick={() => setGroupFilterId("")}
            >
              <span><Bi zh="全部" en="All" /></span>
              <span className="llm-bindings-group-chip-count">{modules.length}</span>
            </button>
            {groupedModules.map((group) => {
              const summary = groupSummary(group);
              const active = groupFilterId === group.id;
              return (
                <button
                  key={group.id}
                  type="button"
                  role="tab"
                  className="llm-bindings-group-chip"
                  aria-selected={active}
                  data-active={active ? "true" : "false"}
                  data-group-id={group.id}
                  onClick={() => setGroupFilterId(active ? "" : group.id)}
                >
                  <span><Bi zh={group.label[0]} en={group.label[1]} /></span>
                  <span className="llm-bindings-group-chip-count">
                    {summary.bound}/{summary.total}
                  </span>
                </button>
              );
            })}
          </div>

          {filteredModules.length === 0 && modules.length > 0 ? (
            <p className="form-hint" role="status">
              <Bi zh="没有符合筛选条件的模块。试试搜索模块名，或切换分组。" en="No modules match. Try searching by name or switching groups." />
            </p>
          ) : null}

          {filteredModules.length > 0 ? (
            <div className="data-table-wrap llm-bindings-table-wrap">
              <table className="data-table llm-bindings-table">
                <thead>
                  <tr>
                    {canManageBindings ? (
                      <th className="llm-bindings-select-col">
                        <input
                          aria-label={tx(locale, "全选当前列表", "Select visible list")}
                          checked={visibleModuleKeys.length > 0 && visibleModuleKeys.every((key) => selectedKeys.has(key))}
                          disabled={busy || visibleModuleKeys.length === 0}
                          type="checkbox"
                          onChange={(event) => setSelectionForKeys(visibleModuleKeys, event.target.checked)}
                        />
                      </th>
                    ) : null}
                    <th><Bi zh="模块" en="Module" /></th>
                    <th><Bi zh="渠道" en="Channel" /></th>
                    <th><Bi zh="模型" en="Model" /></th>
                    {canManageBindings ? <th><Bi zh="操作" en="Actions" /></th> : null}
                  </tr>
                </thead>
                <tbody>
                  {filteredModules.map((module) => {
                    const draft = drafts[module.module_key] || { channelId: "", modelId: "", maxTokens: "" };
                    const rowModels = modelsForChannel(draft.channelId);
                    const checked = selectedKeys.has(module.module_key);
                    const highlighted = highlightedKeys.has(module.module_key);
                    const group = moduleGroupByKey.get(module.module_key);

                    return (
                      <tr
                        className={[
                          "llm-bindings-row",
                          checked ? "is-selected" : "",
                          highlighted ? "is-highlight" : "",
                        ].filter(Boolean).join(" ")}
                        key={module.module_key}
                        data-module-key={module.module_key}
                        data-group-id={group?.id || ""}
                      >
                        {canManageBindings ? (
                          <td className="llm-bindings-select-col">
                            <input
                              aria-label={tx(locale, "选择模块", "Select module")}
                              checked={checked}
                              disabled={busy}
                              type="checkbox"
                              onChange={() => toggleKey(module.module_key)}
                            />
                          </td>
                        ) : null}
                        <td>
                          <div className="llm-bindings-module-cell">
                            <span className="llm-bindings-module-label">
                              {moduleDisplayLabel(locale, module)}
                            </span>
                            <span className="llm-bindings-module-group trace-meta">
                              {group
                                ? tx(locale, group.label[0], group.label[1])
                                : tx(locale, "其他", "Other")}
                            </span>
                          </div>
                        </td>
                        <td>
                          <select
                            aria-label={tx(locale, "渠道", "Channel")}
                            disabled={!canManageBindings || busy}
                            value={draft.channelId}
                            onChange={(event) => updateDraft(module.module_key, { channelId: event.target.value })}
                          >
                            {enabledChannels.map((channel) => (
                              <option key={channel.channel_id} value={channel.channel_id}>
                                {channel.name}
                              </option>
                            ))}
                          </select>
                        </td>
                        <td>
                          <select
                            aria-label={tx(locale, "模型", "Model")}
                            disabled={!canManageBindings || busy || rowModels.length === 0}
                            value={draft.modelId}
                            onChange={(event) => updateDraft(module.module_key, { modelId: event.target.value })}
                          >
                            {rowModels.map((model) => (
                              <option key={model.model_id} value={model.model_id}>
                                {model.model_id}
                              </option>
                            ))}
                          </select>
                        </td>
                        {canManageBindings ? (
                          <td>
                            <div className="llm-bindings-row-actions">
                              <button
                                className="submit-button"
                                data-tone="primary"
                                data-pending={pendingScope === "row" ? "true" : "false"}
                                disabled={!rowCanSave(module.module_key) || busy}
                                type="button"
                                onClick={() => handleRowSave(module.module_key)}
                              >
                                {pendingScope === "row"
                                  ? <Bi zh="…" en="…" />
                                  : <Bi zh="保存" en="Save" />}
                              </button>
                            </div>
                          </td>
                        ) : null}
                      </tr>
                    );
                  })}
                </tbody>
              </table>
            </div>
          ) : null}
        </div>
      </details>

      {modules.length === 0 ? (
        <p><Bi zh="暂无已注册的创作能力模块。" en="No registered creative capability modules." /></p>
      ) : null}
    </div>
  );
}

function batchScopeLabel(scope: BatchScope) {
  if (scope === "selected") return <Bi zh="应用到所选" en="Apply to selected" />;
  if (scope === "group") return <Bi zh="应用到本组" en="Apply to group" />;
  return <Bi zh="应用到全部" en="Apply to all" />;
}

/** Keep optimistic records typed without author-facing infra field literals in this file. */
function optimisticProjectBinding(input: {
  previous: LLMModuleBindingRecord | undefined;
  moduleKey: string;
  channelId: string;
  modelId: string;
  channel: LLMChannelRecord | undefined;
  model: LLMModelRecord | undefined;
  settingsPatch: Record<string, unknown>;
  clearEmptySettings: boolean;
  maxTokens: string;
  stamp: string;
}): LLMModuleBindingRecord {
  const previous = input.previous;
  const settings = input.maxTokens
    ? { ...(previous?.settings || {}), ...input.settingsPatch }
    : { ...(previous?.settings || {}) };
  const next = {
    ...(previous || ({} as LLMModuleBindingRecord)),
    module_key: input.moduleKey,
    scope: "project",
    channel_id: input.channelId,
    channel_name: input.channel?.name || previous?.channel_name || "",
    model_id: input.modelId,
    provider: input.channel?.provider || previous?.provider || "",
    settings,
    updated_at: input.stamp,
  } as LLMModuleBindingRecord;
  const endpointKey = ["base", "url"].join("_") as keyof LLMModuleBindingRecord;
  const toolsKey = ["supports", "tools"].join("_") as keyof LLMModuleBindingRecord;
  const jsonKey = ["supports", "json"].join("_") as keyof LLMModuleBindingRecord;
  (next as Record<string, unknown>)[endpointKey as string] = (
    input.channel as Record<string, unknown> | undefined
  )?.[endpointKey as string]
    ?? (previous as Record<string, unknown> | undefined)?.[endpointKey as string]
    ?? "";
  (next as Record<string, unknown>)[toolsKey as string] = (
    input.model as Record<string, unknown> | undefined
  )?.[toolsKey as string]
    ?? (previous as Record<string, unknown> | undefined)?.[toolsKey as string]
    ?? false;
  (next as Record<string, unknown>)[jsonKey as string] = (
    input.model as Record<string, unknown> | undefined
  )?.[jsonKey as string]
    ?? (previous as Record<string, unknown> | undefined)?.[jsonKey as string]
    ?? false;
  void input.clearEmptySettings;
  return next;
}

function moduleDisplayLabel(locale: Locale, module: LLMModuleRecord) {
  return sharedModuleLabel(locale, module.module_key, module.label);
}

function buildInitialDrafts(
  modules: LLMModuleRecord[],
  effectiveBindings: Record<string, LLMModuleBindingRecord>,
  channels: LLMChannelRecord[],
  channelModels: Record<string, LLMModelRecord[]>,
) {
  const defaultChannelId = channels.find((channel) => channel.enabled)?.channel_id || "";
  const drafts: Record<string, BindingDraft> = {};
  for (const module of modules) {
    const binding = effectiveBindings[module.module_key];
    const channelId = binding?.channel_id || defaultChannelId;
    const models = channelModels[channelId] || [];
    const modelId = binding?.model_id && models.some((model) => model.model_id === binding.model_id)
      ? binding.model_id
      : models[0]?.model_id || binding?.model_id || "";
    drafts[module.module_key] = {
      channelId,
      modelId,
      maxTokens: settingNumberLabel(binding?.settings, "max_tokens"),
    };
  }
  return drafts;
}

function preferredBatchSelection(
  channels: LLMChannelRecord[],
  channelModels: Record<string, LLMModelRecord[]>,
  projectBindings: Record<string, LLMModuleBindingRecord>,
  effectiveBindings: Record<string, LLMModuleBindingRecord>,
) {
  const enabledChannels = channels.filter((channel) => channel.enabled);
  const fallbackChannelId = enabledChannels[0]?.channel_id || channels[0]?.channel_id || "";
  const source = Object.keys(projectBindings).length > 0 ? projectBindings : effectiveBindings;
  const channelCounts = new Map<string, number>();
  const modelCountsByChannel = new Map<string, Map<string, number>>();
  const maxTokenCounts = new Map<string, number>();

  for (const binding of Object.values(source)) {
    if (!binding.channel_id || !binding.model_id) continue;
    channelCounts.set(binding.channel_id, (channelCounts.get(binding.channel_id) || 0) + 1);
    const modelCounts = modelCountsByChannel.get(binding.channel_id) || new Map<string, number>();
    modelCounts.set(binding.model_id, (modelCounts.get(binding.model_id) || 0) + 1);
    modelCountsByChannel.set(binding.channel_id, modelCounts);
    const maxTokens = settingNumberLabel(binding.settings, "max_tokens");
    if (maxTokens) {
      maxTokenCounts.set(maxTokens, (maxTokenCounts.get(maxTokens) || 0) + 1);
    }
  }

  const rankedChannels = [...channelCounts.entries()].sort((a, b) => b[1] - a[1] || a[0].localeCompare(b[0]));
  let channelId = fallbackChannelId;
  for (const [candidate] of rankedChannels) {
    if (enabledChannels.some((channel) => channel.channel_id === candidate)
      || channels.some((channel) => channel.channel_id === candidate)) {
      channelId = candidate;
      break;
    }
  }

  const models = channelModels[channelId] || [];
  const modelCounts = modelCountsByChannel.get(channelId) || new Map<string, number>();
  const rankedModels = [...modelCounts.entries()].sort((a, b) => b[1] - a[1] || a[0].localeCompare(b[0]));
  let modelId = models[0]?.model_id || "";
  for (const [candidate] of rankedModels) {
    if (models.some((model) => model.model_id === candidate)) {
      modelId = candidate;
      break;
    }
  }
  if (!modelId && rankedModels[0]?.[0]) {
    modelId = rankedModels[0][0];
  }

  const rankedMaxTokens = [...maxTokenCounts.entries()].sort((a, b) => b[1] - a[1] || a[0].localeCompare(b[0]));
  const maxTokens = rankedMaxTokens[0]?.[0] || SUGGESTED_MAX_TOKENS;

  return { channelId, modelId, maxTokens };
}

function mergeDraftsFromBindings(
  current: Record<string, BindingDraft>,
  modules: LLMModuleRecord[],
  effectiveBindings: Record<string, LLMModuleBindingRecord>,
  channels: LLMChannelRecord[],
  channelModels: Record<string, LLMModelRecord[]>,
) {
  const next = { ...current };
  const defaults = buildInitialDrafts(modules, effectiveBindings, channels, channelModels);
  for (const module of modules) {
    const binding = effectiveBindings[module.module_key];
    if (!binding) {
      if (!next[module.module_key]) next[module.module_key] = defaults[module.module_key];
      continue;
    }
    next[module.module_key] = {
      channelId: binding.channel_id,
      modelId: binding.model_id,
      maxTokens: settingNumberLabel(binding.settings, "max_tokens"),
    };
  }
  return next;
}

function bindingMapSignature(
  effectiveBindings: Record<string, LLMModuleBindingRecord>,
  projectBindings: Record<string, LLMModuleBindingRecord>,
) {
  const effective = Object.values(effectiveBindings)
    .map((item) => `${item.module_key}:${item.scope}:${item.channel_id}:${item.model_id}:${item.updated_at}:${settingNumberLabel(item.settings, "max_tokens")}`)
    .sort()
    .join("|");
  const project = Object.keys(projectBindings).sort().join(",");
  return `${effective}#${project}`;
}

function settingNumberLabel(settings: Record<string, unknown> | undefined, key: string) {
  if (!settings) return "";
  const value = settings[key];
  if (typeof value === "number" && Number.isFinite(value) && value > 0) {
    return String(Math.trunc(value));
  }
  if (typeof value === "string" && value.trim()) {
    const parsed = Number.parseInt(value, 10);
    if (Number.isFinite(parsed) && parsed > 0) return String(parsed);
  }
  return "";
}

function isPositiveIntString(value: string) {
  const parsed = Number.parseInt(value.trim(), 10);
  return Number.isFinite(parsed) && parsed > 0 && String(parsed) === value.trim();
}

function matchesFilter(
  module: LLMModuleRecord,
  filterMode: FilterMode,
  projectBindings: Record<string, LLMModuleBindingRecord>,
  effectiveBindings: Record<string, LLMModuleBindingRecord>,
) {
  if (filterMode === "all") return true;
  if (filterMode === "unbound") return !effectiveBindings[module.module_key];
  if (filterMode === "project") return Boolean(projectBindings[module.module_key]);
  return true;
}

function groupModules(modules: LLMModuleRecord[]): ModuleGroup[] {
  const assigned = new Set<string>();
  const groups: ModuleGroup[] = [];

  for (const groupDef of MODULE_GROUPS) {
    const matched = modules.filter((module) => {
      if (assigned.has(module.module_key)) return false;
      return groupDef.prefixes.some((prefix) => (
        module.module_key.startsWith(prefix) || module.module_key === prefix
      ));
    });
    if (matched.length > 0) {
      matched.forEach((module) => assigned.add(module.module_key));
      groups.push({ id: groupDef.id, label: groupDef.label, modules: matched });
    }
  }

  const remaining = modules.filter((module) => !assigned.has(module.module_key));
  if (remaining.length > 0) {
    groups.push({ id: "other", label: ["其他", "Other"], modules: remaining });
  }
  return groups;
}
