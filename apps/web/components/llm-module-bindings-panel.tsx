"use client";

import { useMemo, useState } from "react";

import { Bi } from "./bilingual-text";
import { SubmitButton } from "./submit-button";
import type { LLMChannelRecord, LLMModelRecord, LLMModuleBindingRecord, LLMModuleRecord } from "../lib/api";
import { type Locale, tx } from "../lib/locale";
import { moduleLabel as sharedModuleLabel } from "../lib/user-facing-copy";

type BindingDraft = {
  channelId: string;
  modelId: string;
  maxTokens: string;
};

type BatchScope = "selected" | "group" | "all";

type FilterMode = "all" | "unbound" | "project" | "missing-limit";

type ModuleGroup = {
  id: string;
  label: [string, string];
  modules: LLMModuleRecord[];
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
  bindModuleAction: (formData: FormData) => Promise<void>;
  batchBindModuleAction: (formData: FormData) => Promise<void>;
  clearBindingAction: (formData: FormData) => Promise<void>;
};

/** Suggested output budget for Seed / long-form modules when model context_window is missing. */
const SUGGESTED_MAX_TOKENS = "12800";

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
  effectiveBindings,
  projectBindings,
  canManageBindings,
  bindingStatus,
  bindingCode,
  bindingMessage,
  bindModuleAction,
  batchBindModuleAction,
  clearBindingAction,
}: LLMModuleBindingsPanelProps) {
  const [drafts, setDrafts] = useState<Record<string, BindingDraft>>(() => (
    buildInitialDrafts(modules, effectiveBindings, channels, channelModels)
  ));
  const [batchChannelId, setBatchChannelId] = useState(channels[0]?.channel_id || "");
  const [batchModelId, setBatchModelId] = useState(() => (
    channelModels[channels[0]?.channel_id || ""]?.[0]?.model_id || ""
  ));
  const [batchMaxTokens, setBatchMaxTokens] = useState(SUGGESTED_MAX_TOKENS);
  const [searchQuery, setSearchQuery] = useState("");
  const [filterMode, setFilterMode] = useState<FilterMode>("all");
  const [selectedKeys, setSelectedKeys] = useState<Set<string>>(() => new Set());
  const [openGroupIds, setOpenGroupIds] = useState<Set<string>>(() => new Set());
  const [activeGroupId, setActiveGroupId] = useState("");

  const enabledChannels = useMemo(
    () => channels.filter((channel) => channel.enabled),
    [channels],
  );

  const groupedModules = useMemo(() => groupModules(modules), [modules]);

  const filteredGroups = useMemo(() => {
    const query = searchQuery.trim().toLowerCase();
    return groupedModules
      .map((group) => ({
        ...group,
        modules: group.modules.filter((module) => {
          if (!matchesFilter(module, filterMode, drafts, projectBindings, effectiveBindings, channelModels)) {
            return false;
          }
          if (!query) return true;
          const label = moduleDisplayLabel(locale, module).toLowerCase();
          return label.includes(query) || module.module_key.toLowerCase().includes(query);
        }),
      }))
      .filter((group) => group.modules.length > 0);
  }, [
    channelModels,
    drafts,
    effectiveBindings,
    filterMode,
    groupedModules,
    locale,
    projectBindings,
    searchQuery,
  ]);

  const visibleModuleKeys = useMemo(
    () => filteredGroups.flatMap((group) => group.modules.map((module) => module.module_key)),
    [filteredGroups],
  );

  const boundProjectCount = Object.keys(projectBindings).length;
  const unboundCount = modules.filter((module) => !effectiveBindings[module.module_key]).length;
  const missingMaxTokensCount = modules.filter((module) => (
    isMissingMaxTokens(module.module_key, drafts, channelModels)
  )).length;
  const bindingStatusClass = bindingStatus === "success" ? "success-box" : bindingStatus === "error" ? "error-box" : "";
  const selectedCount = selectedKeys.size;
  const batchTargetsValid = Boolean(
    batchChannelId
    && batchModelId
    && (batchMaxTokens.trim() === "" || isPositiveIntString(batchMaxTokens)),
  );

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
    if (draft.maxTokens.trim() && !isPositiveIntString(draft.maxTokens)) return false;
    return true;
  }

  function toggleGroupOpen(groupId: string, open: boolean) {
    setOpenGroupIds((current) => {
      const next = new Set(current);
      if (open) next.add(groupId);
      else next.delete(groupId);
      return next;
    });
    if (open) setActiveGroupId(groupId);
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

  function fillMissingOutputLimits(keys: string[]) {
    setDrafts((current) => {
      const next = { ...current };
      for (const key of keys) {
        const draft = next[key];
        if (!draft || draft.maxTokens.trim()) continue;
        const model = modelsForChannel(draft.channelId).find((item) => item.model_id === draft.modelId);
        next[key] = {
          ...draft,
          maxTokens: model?.context_window ? String(model.context_window) : SUGGESTED_MAX_TOKENS,
        };
      }
      return next;
    });
    if (!batchMaxTokens.trim()) {
      setBatchMaxTokens(SUGGESTED_MAX_TOKENS);
    }
  }

  function groupSummary(group: ModuleGroup) {
    let bound = 0;
    let unbound = 0;
    let missingLimit = 0;
    for (const module of group.modules) {
      if (projectBindings[module.module_key] || effectiveBindings[module.module_key]) {
        bound += 1;
      } else {
        unbound += 1;
      }
      if (isMissingMaxTokens(module.module_key, drafts, channelModels)) {
        missingLimit += 1;
      }
    }
    return { bound, unbound, missingLimit, total: group.modules.length };
  }

  function moduleKeysForScope(scope: BatchScope): string[] {
    if (scope === "all") {
      return modules.map((module) => module.module_key);
    }
    if (scope === "group") {
      const group = groupedModules.find((item) => item.id === activeGroupId);
      return group ? group.modules.map((module) => module.module_key) : [];
    }
    return Array.from(selectedKeys);
  }

  function scopeDisabled(scope: BatchScope) {
    if (!batchTargetsValid) return true;
    if (scope === "selected") return selectedCount === 0;
    if (scope === "group") return !activeGroupId || moduleKeysForScope("group").length === 0;
    return modules.length === 0;
  }

  const clearTargets = Array.from(selectedKeys).filter((key) => Boolean(projectBindings[key]));

  return (
    <div className="llm-bindings-panel binding-stack">
      <p className="form-hint">
        <Bi
          zh="按业务分组管理创作能力的渠道与模型；可搜索、多选后批量应用。"
          en="Manage channels and models by capability group. Search, multi-select, then apply in batch."
        />
      </p>

      <div className="status-row" aria-label={tx(locale, "绑定统计", "Binding summary")}>
        <span className="status-pill">
          <Bi zh="项目已绑定" en="Project bound" />: {boundProjectCount}/{modules.length}
        </span>
        <span className="status-pill">
          <Bi zh="未绑定" en="Unbound" />: {unboundCount}
        </span>
        <span className="status-pill">
          <Bi zh="可用渠道" en="Channels" />: {enabledChannels.length}
        </span>
        {missingMaxTokensCount > 0 ? (
          <span className="status-pill" data-tone="warning">
            <Bi zh="缺输出上限" en="Missing output limit" />: {missingMaxTokensCount}
          </span>
        ) : null}
        {selectedCount > 0 ? (
          <span className="status-pill">
            <Bi zh="已选" en="Selected" />: {selectedCount}
          </span>
        ) : null}
      </div>

      {bindingStatus ? (
        <p
          className={`form-status ${bindingStatusClass}`}
          data-code={bindingCode}
          data-status={bindingStatus}
          role={bindingStatus === "error" ? "alert" : "status"}
        >
          {bindingMessage}
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

      <div className="llm-bindings-toolbar">
        <label className="llm-bindings-field llm-bindings-search">
          <span><Bi zh="搜索" en="Search" /></span>
          <input
            aria-label={tx(locale, "搜索模块", "Search modules")}
            placeholder={tx(locale, "按名称筛选…", "Filter by name…")}
            type="search"
            value={searchQuery}
            onChange={(event) => setSearchQuery(event.target.value)}
          />
        </label>
        <label className="llm-bindings-field">
          <span><Bi zh="筛选" en="Filter" /></span>
          <select
            aria-label={tx(locale, "筛选绑定状态", "Filter binding status")}
            value={filterMode}
            onChange={(event) => setFilterMode(event.target.value as FilterMode)}
          >
            <option value="all">{tx(locale, "全部", "All")}</option>
            <option value="unbound">{tx(locale, "未绑定", "Unbound")}</option>
            <option value="project">{tx(locale, "项目已绑定", "Project bound")}</option>
            <option value="missing-limit">{tx(locale, "缺输出上限", "Missing output limit")}</option>
          </select>
        </label>
        {canManageBindings ? (
          <div className="llm-bindings-toolbar-actions">
            <button
              className="submit-button"
              data-tone="secondary"
              disabled={visibleModuleKeys.length === 0}
              type="button"
              onClick={() => setSelectionForKeys(visibleModuleKeys, true)}
            >
              <Bi zh="全选可见" en="Select visible" />
            </button>
            <button
              className="submit-button"
              data-tone="secondary"
              disabled={selectedCount === 0}
              type="button"
              onClick={() => setSelectedKeys(new Set())}
            >
              <Bi zh="清除选择" en="Clear selection" />
            </button>
          </div>
        ) : null}
      </div>

      {canManageBindings && enabledChannels.length > 0 ? (
        <div className="llm-bindings-batch-bar binding-form" data-sticky="true">
          <span className="llm-bindings-batch-label"><Bi zh="批量操作" en="Batch actions" /></span>
          <label className="llm-bindings-field">
            <span><Bi zh="渠道" en="Channel" /></span>
            <select
              name="channelId"
              value={batchChannelId}
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
              disabled={modelsForChannel(batchChannelId).length === 0}
            >
              {modelsForChannel(batchChannelId).map((model) => (
                <option key={model.model_id} value={model.model_id}>
                  {model.model_id}
                </option>
              ))}
            </select>
          </label>
          <label className="llm-bindings-field llm-bindings-field-tokens">
            <span><Bi zh="输出上限" en="Output limit" /></span>
            <input
              inputMode="numeric"
              min={1}
              name="maxTokens"
              placeholder={SUGGESTED_MAX_TOKENS}
              type="number"
              value={batchMaxTokens}
              onChange={(event) => setBatchMaxTokens(event.target.value)}
            />
          </label>
          <div className="llm-bindings-batch-actions">
            {(["selected", "group", "all"] as const).map((scope) => (
              <form action={batchBindModuleAction} className="inline-action-form" key={scope}>
                <input type="hidden" name="channelId" value={batchChannelId} />
                <input type="hidden" name="modelId" value={batchModelId} />
                <input type="hidden" name="maxTokens" value={batchMaxTokens.trim()} />
                <input type="hidden" name="scope" value={scope} />
                {scope === "group" ? <input type="hidden" name="groupId" value={activeGroupId} /> : null}
                {moduleKeysForScope(scope).map((moduleKey) => (
                  <input key={`${scope}-${moduleKey}`} type="hidden" name="moduleKeys" value={moduleKey} />
                ))}
                <SubmitButton
                  data-tone={scope === "all" ? "primary" : "secondary"}
                  disabled={scopeDisabled(scope)}
                  idleLabel={batchScopeLabel(scope)}
                  pendingLabel={<Bi zh="绑定中…" en="Binding…" />}
                />
              </form>
            ))}
            <button
              className="submit-button"
              data-tone="secondary"
              disabled={moduleKeysForScope(selectedCount > 0 ? "selected" : "all").length === 0}
              type="button"
              onClick={() => fillMissingOutputLimits(
                moduleKeysForScope(selectedCount > 0 ? "selected" : activeGroupId ? "group" : "all"),
              )}
            >
              <Bi zh="一键补全输出上限" en="Fill output limits" />
            </button>
            {clearTargets.length > 0 ? (
              <form action={clearBindingAction} className="inline-action-form">
                {clearTargets.map((moduleKey) => (
                  <input key={`clear-${moduleKey}`} type="hidden" name="moduleKeys" value={moduleKey} />
                ))}
                <SubmitButton
                  data-tone="secondary"
                  idleLabel={<Bi zh="恢复所选默认" en="Restore selected defaults" />}
                  pendingLabel={<Bi zh="处理中…" en="Working…" />}
                />
              </form>
            ) : null}
          </div>
          <p className="llm-bindings-batch-hint trace-meta">
            {activeGroupId
              ? tx(
                  locale,
                  `当前组：${groupedModules.find((group) => group.id === activeGroupId)?.label[0] || activeGroupId}`,
                  `Active group: ${groupedModules.find((group) => group.id === activeGroupId)?.label[1] || activeGroupId}`,
                )
              : tx(locale, "展开某一组后可「应用到本组」", "Expand a group to enable “Apply to group”")}
            {selectedCount > 0
              ? ` · ${tx(locale, `已选 ${selectedCount} 项`, `${selectedCount} selected`)}`
              : ""}
          </p>
        </div>
      ) : null}

      {enabledChannels.length === 0 ? (
        <p className="form-hint" role="alert">
          <Bi zh="暂无可用渠道，请先在管理区创建并同步模型。" en="No channels are available. Create and sync models in the admin section first." />
        </p>
      ) : null}

      {filteredGroups.length === 0 && modules.length > 0 ? (
        <p className="form-hint" role="status">
          <Bi zh="没有符合筛选条件的模块。" en="No modules match the current filters." />
        </p>
      ) : null}

      {filteredGroups.map((group) => {
        const fullGroup = groupedModules.find((item) => item.id === group.id) || group;
        const summary = groupSummary(fullGroup);
        const groupKeys = group.modules.map((module) => module.module_key);
        const selectedInGroup = groupKeys.filter((key) => selectedKeys.has(key)).length;
        const allGroupSelected = groupKeys.length > 0 && selectedInGroup === groupKeys.length;
        const isOpen = openGroupIds.has(group.id) || Boolean(searchQuery.trim()) || filterMode !== "all";

        return (
          <details
            className="llm-bindings-group llm-bindings-accordion"
            data-group-id={group.id}
            key={group.id}
            open={isOpen}
            onToggle={(event) => {
              const open = (event.currentTarget as HTMLDetailsElement).open;
              toggleGroupOpen(group.id, open);
            }}
          >
            <summary className="llm-bindings-group-summary">
              <span className="llm-bindings-group-title-text">
                <Bi zh={group.label[0]} en={group.label[1]} />
              </span>
              <span className="llm-bindings-group-meta">
                <span className="status-pill">
                  <Bi zh="已绑" en="Bound" /> {summary.bound}/{summary.total}
                </span>
                {summary.unbound > 0 ? (
                  <span className="status-pill">
                    <Bi zh="未绑" en="Unbound" /> {summary.unbound}
                  </span>
                ) : null}
                {summary.missingLimit > 0 ? (
                  <span className="status-pill" data-tone="warning">
                    <Bi zh="缺上限" en="No limit" /> {summary.missingLimit}
                  </span>
                ) : null}
              </span>
            </summary>

            <div className="llm-bindings-group-body">
              {canManageBindings ? (
                <div className="llm-bindings-group-toolbar">
                  <label className="checkbox-row">
                    <input
                      checked={allGroupSelected}
                      type="checkbox"
                      onChange={(event) => setSelectionForKeys(groupKeys, event.target.checked)}
                    />
                    <Bi zh="全选本组" en="Select group" />
                    <span className="trace-meta">({selectedInGroup}/{groupKeys.length})</span>
                  </label>
                  <button
                    className="submit-button"
                    data-tone="secondary"
                    type="button"
                    onClick={() => {
                      setActiveGroupId(group.id);
                      fillMissingOutputLimits(groupKeys);
                    }}
                  >
                    <Bi zh="补全本组输出上限" en="Fill group output limits" />
                  </button>
                </div>
              ) : null}

              <div className="data-table-wrap">
                <table className="data-table llm-bindings-table">
                  <thead>
                    <tr>
                      {canManageBindings ? <th className="llm-bindings-select-col"><Bi zh="选" en="Sel" /></th> : null}
                      <th><Bi zh="模块" en="Module" /></th>
                      <th><Bi zh="状态" en="Status" /></th>
                      <th><Bi zh="渠道" en="Channel" /></th>
                      <th><Bi zh="模型" en="Model" /></th>
                      <th><Bi zh="输出上限" en="Output limit" /></th>
                      <th><Bi zh="操作" en="Actions" /></th>
                    </tr>
                  </thead>
                  <tbody>
                    {group.modules.map((module) => {
                      const draft = drafts[module.module_key] || { channelId: "", modelId: "", maxTokens: "" };
                      const effective = effectiveBindings[module.module_key];
                      const hasProjectBinding = Boolean(projectBindings[module.module_key]);
                      const status = bindingStatusForModule(locale, effective, hasProjectBinding);
                      const rowModels = modelsForChannel(draft.channelId);
                      const selectedModel = rowModels.find((model) => model.model_id === draft.modelId);
                      const contextWindow = selectedModel?.context_window || 0;
                      const needsMaxTokens = !draft.maxTokens.trim() && !contextWindow;
                      const checked = selectedKeys.has(module.module_key);

                      return (
                        <tr
                          className={checked ? "llm-bindings-row is-selected" : "llm-bindings-row"}
                          key={module.module_key}
                          data-module-key={module.module_key}
                        >
                          {canManageBindings ? (
                            <td className="llm-bindings-select-col">
                              <input
                                aria-label={tx(locale, "选择模块", "Select module")}
                                checked={checked}
                                type="checkbox"
                                onChange={() => toggleKey(module.module_key)}
                              />
                            </td>
                          ) : null}
                          <td>
                            <span className="llm-bindings-module-label">
                              {moduleDisplayLabel(locale, module)}
                            </span>
                          </td>
                          <td>
                            <span className={`llm-binding-status-dot ${status.tone}`} aria-hidden="true" />
                            <span className="llm-binding-status-text">{status.label}</span>
                          </td>
                          <td>
                            <select
                              aria-label={tx(locale, "渠道", "Channel")}
                              disabled={!canManageBindings}
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
                              disabled={!canManageBindings || rowModels.length === 0}
                              value={draft.modelId}
                              onChange={(event) => updateDraft(module.module_key, { modelId: event.target.value })}
                            >
                              {rowModels.map((model) => (
                                <option key={model.model_id} value={model.model_id}>
                                  {model.model_id}
                                  {model.context_window
                                    ? ` · ${tx(locale, "上下文", "ctx")} ${model.context_window}`
                                    : ""}
                                </option>
                              ))}
                            </select>
                          </td>
                          <td>
                            {canManageBindings ? (
                              <div className="llm-bindings-tokens-cell">
                                <input
                                  aria-label={tx(locale, "输出上限", "Output limit")}
                                  className={needsMaxTokens ? "llm-bindings-tokens-input is-warning" : "llm-bindings-tokens-input"}
                                  inputMode="numeric"
                                  min={1}
                                  name={`maxTokensDisplay-${module.module_key}`}
                                  placeholder={contextWindow ? String(contextWindow) : SUGGESTED_MAX_TOKENS}
                                  type="number"
                                  value={draft.maxTokens}
                                  onChange={(event) => updateDraft(module.module_key, { maxTokens: event.target.value })}
                                />
                                <span className="trace-meta">
                                  {draft.maxTokens.trim()
                                    ? tx(locale, "绑定设置", "Binding setting")
                                    : contextWindow
                                      ? tx(locale, `模型上下文 ${contextWindow}`, `Model context ${contextWindow}`)
                                      : tx(locale, "建议 12800", "Suggest 12800")}
                                </span>
                              </div>
                            ) : (
                              <span className="trace-meta">
                                {settingNumberLabel(effective?.settings, "max_tokens") || "—"}
                              </span>
                            )}
                          </td>
                          <td>
                            {canManageBindings ? (
                              <div className="llm-bindings-row-actions">
                                <form action={bindModuleAction} className="inline-action-form">
                                  <input type="hidden" name="moduleKey" value={module.module_key} />
                                  <input type="hidden" name="channelId" value={draft.channelId} />
                                  <input type="hidden" name="modelId" value={draft.modelId} />
                                  <input type="hidden" name="maxTokens" value={draft.maxTokens.trim()} />
                                  <SubmitButton
                                    data-tone="primary"
                                    disabled={!rowCanSave(module.module_key)}
                                    idleLabel={<Bi zh="保存" en="Save" />}
                                    pendingLabel={<Bi zh="保存中…" en="Saving…" />}
                                  />
                                </form>
                                <form action={clearBindingAction} className="inline-action-form">
                                  <input type="hidden" name="moduleKey" value={module.module_key} />
                                  <SubmitButton
                                    data-tone="secondary"
                                    disabled={!hasProjectBinding}
                                    idleLabel={<Bi zh="恢复默认" en="Restore default" />}
                                    pendingLabel={<Bi zh="处理中…" en="Working…" />}
                                  />
                                </form>
                              </div>
                            ) : (
                              <span className="trace-meta">{effective?.model_id || "—"}</span>
                            )}
                          </td>
                        </tr>
                      );
                    })}
                  </tbody>
                </table>
              </div>
            </div>
          </details>
        );
      })}

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

function isMissingMaxTokens(
  moduleKey: string,
  drafts: Record<string, BindingDraft>,
  channelModels: Record<string, LLMModelRecord[]>,
) {
  const draft = drafts[moduleKey];
  const maxTokens = draft?.maxTokens?.trim() || "";
  if (maxTokens) return false;
  const models = channelModels[draft?.channelId || ""] || [];
  const model = models.find((item) => item.model_id === draft?.modelId);
  return !model?.context_window;
}

function matchesFilter(
  module: LLMModuleRecord,
  filterMode: FilterMode,
  drafts: Record<string, BindingDraft>,
  projectBindings: Record<string, LLMModuleBindingRecord>,
  effectiveBindings: Record<string, LLMModuleBindingRecord>,
  channelModels: Record<string, LLMModelRecord[]>,
) {
  if (filterMode === "all") return true;
  if (filterMode === "unbound") return !effectiveBindings[module.module_key];
  if (filterMode === "project") return Boolean(projectBindings[module.module_key]);
  if (filterMode === "missing-limit") {
    return isMissingMaxTokens(module.module_key, drafts, channelModels);
  }
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

function bindingStatusForModule(
  locale: Locale,
  effective: LLMModuleBindingRecord | undefined,
  hasProjectBinding: boolean,
) {
  if (!effective) {
    return { tone: "unbound", label: tx(locale, "未绑定", "Unbound") };
  }
  if (hasProjectBinding || effective.scope === "project") {
    return { tone: "project", label: tx(locale, "项目已绑定", "Project bound") };
  }
  if (effective.scope === "tenant") {
    return { tone: "fallback", label: tx(locale, "工作区默认", "Workspace default") };
  }
  return { tone: "fallback", label: tx(locale, "平台默认", "Platform default") };
}
