"use client";

import { useMemo, useState } from "react";

import { Bi } from "./bilingual-text";
import { SubmitButton } from "./submit-button";
import type { LLMChannelRecord, LLMModelRecord, LLMModuleBindingRecord, LLMModuleRecord } from "../lib/api";
import { type Locale, tx } from "../lib/locale";

type BindingDraft = {
  channelId: string;
  modelId: string;
  maxTokens: string;
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

const MODULE_GROUPS: Array<{ label: [string, string]; prefixes: string[] }> = [
  {
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
    label: ["档案与图谱", "Archives & graph"],
    prefixes: ["narrative_archives", "novel_chapter_summarizer", "graph_bond_generator", "asset_ingestion"],
  },
  {
    label: ["世界线推演", "Worldline"],
    prefixes: ["worldline_", "parallel_world_config"],
  },
  { label: ["写作", "Writer"], prefixes: ["writer_"] },
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

  const enabledChannels = useMemo(
    () => channels.filter((channel) => channel.enabled),
    [channels],
  );

  const groupedModules = useMemo(() => groupModules(modules), [modules]);

  const boundProjectCount = Object.keys(projectBindings).length;
  const missingMaxTokensCount = modules.filter((module) => {
    const draft = drafts[module.module_key];
    const maxTokens = draft?.maxTokens?.trim() || "";
    if (maxTokens) return false;
    const model = modelsForChannel(draft?.channelId || "").find((item) => item.model_id === draft?.modelId);
    return !model?.context_window;
  }).length;
  const bindingStatusClass = bindingStatus === "success" ? "success-box" : bindingStatus === "error" ? "error-box" : "";

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

  return (
    <div className="llm-bindings-panel binding-stack">
      <p className="form-hint">
        <Bi
          zh="为每个业务模块选择渠道、模型，并填写 max_tokens（输出 token 上限）。配额预留需要 max_tokens 或模型 context_window；模型同步通常不带上下文窗口，请在此显式填写。"
          en="Choose channel and model per module, and set max_tokens (output token budget). Quota reservation needs max_tokens or a model context_window; synced models often lack context window metadata."
        />
      </p>

      <div className="status-row" aria-label={tx(locale, "绑定统计", "Binding summary")}>
        <span className="status-pill">
          <Bi zh="项目已绑定" en="Project bound" />: {boundProjectCount}/{modules.length}
        </span>
        <span className="status-pill">
          <Bi zh="可用渠道" en="Channels" />: {enabledChannels.length}
        </span>
        {missingMaxTokensCount > 0 ? (
          <span className="status-pill" data-tone="warning">
            <Bi zh="缺 max_tokens" en="Missing max_tokens" />: {missingMaxTokensCount}
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

      {canManageBindings && enabledChannels.length > 0 ? (
        <form action={batchBindModuleAction} className="llm-bindings-batch-bar binding-form">
          <span className="llm-bindings-batch-label"><Bi zh="批量绑定" en="Batch bind" /></span>
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
            <span><Bi zh="max_tokens" en="max_tokens" /></span>
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
          <SubmitButton
            data-tone="primary"
            disabled={!batchChannelId || !batchModelId || (batchMaxTokens.trim() !== "" && !isPositiveIntString(batchMaxTokens))}
            idleLabel={<Bi zh="全部绑定" en="Bind all" />}
            pendingLabel={<Bi zh="绑定中…" en="Binding…" />}
          />
        </form>
      ) : null}

      {enabledChannels.length === 0 ? (
        <p className="form-hint" role="alert">
          <Bi zh="暂无可用渠道，请先在管理区创建并同步模型。" en="No channels are available. Create and sync models in the admin section first." />
        </p>
      ) : null}

      {groupedModules.map((group) => (
        <section className="llm-bindings-group" key={group.label[0]}>
          <h3 className="llm-bindings-group-title">
            <Bi zh={group.label[0]} en={group.label[1]} />
          </h3>
          <div className="data-table-wrap">
            <table className="data-table llm-bindings-table">
              <thead>
                <tr>
                  <th><Bi zh="模块" en="Module" /></th>
                  <th><Bi zh="状态" en="Status" /></th>
                  <th><Bi zh="渠道" en="Channel" /></th>
                  <th><Bi zh="模型" en="Model" /></th>
                  <th><Bi zh="max_tokens" en="max_tokens" /></th>
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

                  return (
                    <tr key={module.module_key}>
                      <td>
                        <span className="llm-bindings-module-label">
                          {moduleLabel(locale, module.module_key, module.label)}
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
                              {model.context_window ? ` · ctx ${model.context_window}` : ""}
                            </option>
                          ))}
                        </select>
                      </td>
                      <td>
                        {canManageBindings ? (
                          <div className="llm-bindings-tokens-cell">
                            <input
                              aria-label={tx(locale, "max_tokens", "max_tokens")}
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
                                  ? tx(locale, `模型 ctx ${contextWindow}`, `Model ctx ${contextWindow}`)
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
        </section>
      ))}

      {modules.length === 0 ? (
        <p><Bi zh="暂无已注册的 LLM 模块。" en="No registered LLM modules." /></p>
      ) : null}
    </div>
  );
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

function groupModules(modules: LLMModuleRecord[]) {
  const assigned = new Set<string>();
  const groups: Array<{ label: [string, string]; modules: LLMModuleRecord[] }> = [];

  for (const groupDef of MODULE_GROUPS) {
    const matched = modules.filter((module) => {
      if (assigned.has(module.module_key)) return false;
      return groupDef.prefixes.some((prefix) => (
        module.module_key.startsWith(prefix) || module.module_key === prefix
      ));
    });
    if (matched.length > 0) {
      matched.forEach((module) => assigned.add(module.module_key));
      groups.push({ label: groupDef.label, modules: matched });
    }
  }

  const remaining = modules.filter((module) => !assigned.has(module.module_key));
  if (remaining.length > 0) {
    groups.push({ label: ["其他", "Other"], modules: remaining });
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

function moduleLabel(locale: Locale, moduleKey: string, fallback: string) {
  const labels: Record<string, [string, string]> = {
    anchor_point_summary: ["锚点摘要", "Anchor Point Summary"],
    asset_ingestion: ["资产导入", "Asset Ingestion"],
    character_agent_profile: ["角色 Agent 档案", "Character Agent Profile"],
    contextual_block_analysis: ["上下文文本块分析", "Contextual Block Analysis"],
    entity_resolution: ["实体消歧", "Entity Resolution"],
    graph_bond_generator: ["图谱关系生成", "Graph Bond Generator"],
    local_block_facts: ["局部文本事实", "Local Block Facts"],
    narrative_archives: ["叙事档案", "Narrative Archives"],
    novel_chapter_summarizer: ["章节摘要", "Novel Chapter Summarizer"],
    parallel_world_config: ["世界线配置", "Worldline Config"],
    sequential_reading: ["顺序精读", "Sequential Reading"],
    story_ontology: ["故事本体", "Story Ontology"],
    style_extractor: ["风格提取", "Style Extractor"],
    worldline_agent_action: ["世界线角色行动", "Worldline Agent Action"],
    worldline_agent_dialogue: ["世界线角色对话", "Worldline Agent Dialogue"],
    worldline_agent_prepare: ["世界线角色准备", "Worldline Agent Preparation"],
    worldline_character_proposal: ["世界线角色提案", "Worldline Character Proposal"],
    worldline_director: ["世界线导演", "Worldline Director"],
    worldline_goal_evaluator: ["世界线目标评估", "Worldline Goal Evaluator"],
    writer_composer: ["正文创作", "Writer Composer"],
    writer_book_planner: ["书籍计划", "Writer Book Planner"],
    writer_dedup_extractor: ["重复风险提取", "Writer Dedup Extractor"],
    writer_orchestrator: ["写作编排", "Writer Orchestrator"],
    writer_retrieval_planner: ["写作检索规划", "Writer Retrieval Planner"],
    writer_reviewer: ["写作审校", "Writer Reviewer"],
  };
  const label = labels[moduleKey];
  return label ? tx(locale, label[0], label[1]) : fallback;
}