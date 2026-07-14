import { Cpu } from "lucide-react";
import type { ReactNode } from "react";

import { Bi, FailureText } from "./bilingual-text";
import type {
  LLMActivitySummary,
  LLMChannelRecord,
  LLMChannelModelsSummary,
  LLMChannelsSummary,
  LLMModuleBindingsSummary,
  LLMModulesSummary,
  LLMModuleResolutionSummary,
  LLMSettingsSummary,
  LLMUsageSummary,
} from "../lib/api";
import type { LLMModelRecord } from "../lib/api";
import { llmChannelAnchorId, llmChannelKey, llmModuleSegment } from "../lib/llm-facility-route";
import { type Locale, tx } from "../lib/locale";
import { LLMChannelFocus } from "./llm-channel-focus";
import { LLMCreateChannelDialog } from "./llm-create-channel-dialog";
import { LLMModuleBindingsPanel, type LLMBindingActionResult } from "./llm-module-bindings-panel";
import { TechnicalDetailsDrawer } from "./technical-details-drawer";
import { WorkspaceHeader } from "./workspace-header";

type LLMFacilityShellProps = {
  locale: Locale;
  tenantSlug: string;
  projectId: string;
  moduleKey: string;
  runId: string;
  selectedChannelId: string;
  /** When false, channel/governance/catalog/telemetry admin surfaces are hidden. */
  canManageAdmin?: boolean;
  bindingStatus: string;
  bindingCode: string;
  bindingMessage: string;
  channelStatus: string;
  channelCode: string;
  channelMessage: string;
  syncStatus: string;
  syncCode: string;
  syncMessage: string;
  modelStatus: string;
  modelCode: string;
  modelMessage: string;
  quotaStatus: string;
  quotaCode: string;
  quotaMessage: string;
  bindModuleAction: (formData: FormData) => Promise<LLMBindingActionResult>;
  batchBindModuleAction: (formData: FormData) => Promise<LLMBindingActionResult>;
  clearBindingAction: (formData: FormData) => Promise<LLMBindingActionResult>;
  canManageBindings: boolean;
  channelModels: Record<string, LLMModelRecord[]>;
  createChannelAction: (formData: FormData) => Promise<void>;
  updateChannelAction: (formData: FormData) => Promise<void>;
  deleteChannelAction: (formData: FormData) => Promise<void>;
  syncChannelAction: (formData: FormData) => Promise<void>;
  testModelAction: (formData: FormData) => Promise<void>;
  updateModelAction: (formData: FormData) => Promise<void>;
  upsertQuotaPolicyAction: (formData: FormData) => Promise<void>;
  healthStatus: string;
  healthCode: string;
  healthMessage: string;
  resolution: LLMModuleResolutionSummary;
  modules: LLMModulesSummary;
  bindings: LLMModuleBindingsSummary;
  channels: LLMChannelsSummary;
  settingsSnapshot: LLMSettingsSummary;
  models: LLMChannelModelsSummary;
  quotaPolicies: LLMQuotaPoliciesSummary;
  telemetryContent: ReactNode;
};

export type LLMQuotaPolicyRecord = {
  policy_id: string;
  scope_type: "tenant" | "project" | "module";
  project_id?: string;
  module_key?: string;
  token_limit?: number;
  cost_limit_micros?: number;
  concurrency_limit?: number;
  period_seconds: number;
  enabled: boolean;
  updated_at: string;
};

export type LLMQuotaPoliciesSummary =
  | { ok: true; items: LLMQuotaPolicyRecord[] }
  | { ok: false; code: string; message: string; request_id: string };

export type LLMBillingUsageRecord = {
  tenant_id: string;
  project_id?: string;
  module_key?: string;
  model_id?: string;
  provider_calls: number;
  tokens: number;
  cost_micros?: number;
  billing_status: "billing_ready" | "pricing_unavailable" | "unavailable";
};

export type LLMBillingUsageSummary =
  | { ok: true; items: LLMBillingUsageRecord[] }
  | { ok: false; code: string; message: string; request_id: string };

export function LLMFacilityShell({
  locale,
  tenantSlug,
  projectId,
  moduleKey,
  runId,
  selectedChannelId,
  canManageAdmin = false,
  bindingStatus,
  bindingCode,
  bindingMessage,
  channelStatus,
  channelCode,
  channelMessage,
  syncStatus,
  syncCode,
  syncMessage,
  modelStatus,
  modelCode,
  modelMessage,
  quotaStatus,
  quotaCode,
  quotaMessage,
  bindModuleAction,
  batchBindModuleAction,
  clearBindingAction,
  canManageBindings,
  channelModels,
  createChannelAction,
  updateChannelAction,
  deleteChannelAction,
  syncChannelAction,
  testModelAction,
  updateModelAction,
  upsertQuotaPolicyAction,
  healthStatus,
  healthCode,
  healthMessage,
  resolution,
  modules,
  bindings,
  channels,
  settingsSnapshot,
  models,
  quotaPolicies,
  telemetryContent,
}: LLMFacilityShellProps) {
  const projectBindingCount = bindings.ok
    ? bindings.items.filter((item) => item.scope === "project").length
    : 0;
  const moduleCount = modules.ok ? modules.items.length : 0;
  const statusLabel = resolution.ok
    ? tx(locale, "可调用", "ready")
    : tx(locale, "未配置", "unconfigured");
  const defaultChannelId = channels.ok ? channels.items[0]?.channel_id || "" : "";
  const effectiveBindings = bindings.ok
    ? Object.fromEntries(bindings.items.map((item) => [item.module_key, item]))
    : {};
  const projectBindings = bindings.ok
    ? Object.fromEntries(bindings.items.filter((item) => item.scope === "project").map((item) => [item.module_key, item]))
    : {};
  const selectedChannelKey = selectedChannelId && selectedChannelId !== defaultChannelId
    ? llmChannelKey(selectedChannelId)
    : "";

  const diagnosticsDrawer = canManageAdmin ? (
    <TechnicalDetailsDrawer
      description={<Bi zh="渠道调用与用量仅管理角色使用" en="Channel calls and usage are for admin roles" />}
      label={<Bi zh="调用诊断" en="Call diagnostics" />}
    >
      <section className="panel" aria-labelledby="telemetry-filter-heading">
        <p className="eyebrow"><Bi zh="调用筛选" en="Telemetry filter" /></p>
        <h2 id="telemetry-filter-heading"><Bi zh="筛选调用记录" en="Filter telemetry" /></h2>
        <TelemetryFilter
          moduleKey={moduleKey}
          runId={runId}
          selectedChannelKey={selectedChannelKey}
          modules={modules}
          locale={locale}
        />
      </section>

      <details className="llm-module-group" open>
        <summary>
          <span><Bi zh="调用与用量" en="Calls and usage" /></span>
          <small><Bi zh="活动、令牌与计费" en="Activity, tokens and billing" /></small>
        </summary>
        <div className="llm-module-content">
          {telemetryContent}
        </div>
      </details>
    </TechnicalDetailsDrawer>
  ) : null;

  return (
    <div className="llm-facility-root">
      <WorkspaceHeader
        actions={diagnosticsDrawer}
        className="llm-facility-header"
        description={<Bi zh="为项目各创作能力绑定渠道与模型。" en="Bind channels and models for each creative capability." />}
        icon={<Cpu size={22} strokeWidth={1.8} />}
        meta={(
          <>
            <span className="status-pill">
              <Bi zh="已绑定" en="Bound" />: {projectBindingCount}/{moduleCount || "—"}
            </span>
            <span className="status-pill">{moduleLabel(locale, moduleKey, moduleKey)} · {statusLabel}</span>
          </>
        )}
        title={<Bi zh="模型设置" en="Model settings" />}
      />

      <div className="workbench-grid llm-facility-workbench" data-layout="single">
        <main>
        <section
          className="panel llm-author-surface"
          aria-label={tx(locale, "项目模型绑定", "Project model bindings")}
          data-surface="author"
        >
          {modules.ok && channels.ok ? (
            <LLMModuleBindingsPanel
              locale={locale}
              modules={modules.items}
              channels={channels.items}
              channelModels={channelModels}
              effectiveBindings={effectiveBindings}
              projectBindings={projectBindings}
              canManageBindings={canManageBindings}
              bindingStatus={bindingStatus}
              bindingCode={bindingCode}
              bindingMessage={bindingMessage}
              bindModuleAction={bindModuleAction}
              batchBindModuleAction={batchBindModuleAction}
              clearBindingAction={clearBindingAction}
            />
          ) : (
            <p className="form-status error-box" role="alert">
              <Bi zh="模块或渠道加载失败，暂时无法配置绑定。" en="Unable to load modules or channels for binding." /> <FailureText />
            </p>
          )}
        </section>

        {canManageAdmin ? (
          <>
        {/* Keep admin open after create/update/sync so redirect remount does not collapse layout mid-scroll. */}
        <details
          className="llm-module-group"
          data-surface="admin"
          open={Boolean(channelStatus || syncStatus) ? true : undefined}
        >
          <summary><span><Bi zh="管理：渠道管理" en="Admin: Channel management" /></span><small><Bi zh="创建、更新与同步模型" en="Create, update and sync models" /></small></summary>
          <div className="llm-module-content">
        <section className="panel" aria-labelledby="channel-management-heading" id="llm-channel-management">
          <p className="eyebrow"><Bi zh="渠道管理" en="Channel Management" /></p>
          <h2 id="channel-management-heading"><Bi zh="渠道与模型同步" en="Channels and model sync" /></h2>
          <LLMChannelFocus />
          <ChannelManagement
            channelStatus={channelStatus}
            channelCode={channelCode}
            channelMessage={channelMessage}
            syncStatus={syncStatus}
            syncCode={syncCode}
            syncMessage={syncMessage}
            healthStatus={healthStatus}
            healthCode={healthCode}
            healthMessage={healthMessage}
            createChannelAction={createChannelAction}
            updateChannelAction={updateChannelAction}
            deleteChannelAction={deleteChannelAction}
            syncChannelAction={syncChannelAction}
            testModelAction={testModelAction}
            channelModels={channelModels}
            channels={channels}
            locale={locale}
          />
        </section>
          </div>
        </details>

        <details className="llm-module-group" data-surface="admin">
          <summary><span><Bi zh="管理：配置与治理" en="Admin: Configuration and governance" /></span><small><Bi zh="绑定、工作区设置与配额" en="Bindings, workspace settings and quotas" /></small></summary>
          <div className="llm-module-content">
        <section
          className={`panel ${bindings.ok ? "" : "error-box"}`}
          aria-labelledby="module-bindings-heading"
        >
          <p className="eyebrow"><Bi zh="模块绑定" en="Module Bindings" /></p>
          <h2 id="module-bindings-heading"><Bi zh="已配置模块" en="Configured modules" /></h2>
          <ModuleBindingsTable bindings={bindings} locale={locale} />
        </section>
        <section
          className={`panel ${settingsSnapshot.ok ? "" : "error-box"}`}
          aria-labelledby="tenant-settings-heading"
        >
          <p className="eyebrow"><Bi zh="工作区设置" en="Workspace Settings" /></p>
          <h2 id="tenant-settings-heading"><Bi zh="设置概览" en="Settings snapshot" /></h2>
          <TenantSettingsSummary settingsSnapshot={settingsSnapshot} locale={locale} />
        </section>

        <section className="panel" aria-labelledby="quota-policy-heading">
          <p className="eyebrow"><Bi zh="配额策略" en="Quota Policies" /></p>
          <h2 id="quota-policy-heading"><Bi zh="调用预算与并发" en="Call budgets and concurrency" /></h2>
          <QuotaPolicyManagement
            projectId={projectId}
            selectedModuleKey={moduleKey}
            modules={modules}
            policies={quotaPolicies}
            status={quotaStatus}
            code={quotaCode}
            message={quotaMessage}
            action={upsertQuotaPolicyAction}
            locale={locale}
          />
        </section>
          </div>
        </details>

        <details className="llm-module-group" data-surface="admin">
          <summary><span><Bi zh="管理：目录与资源" en="Admin: Catalog and resources" /></span><small><Bi zh="模块、渠道与模型清单" en="Modules, channels and model inventory" /></small></summary>
          <div className="llm-module-content">

        <section
          className={`panel ${modules.ok ? "" : "error-box"}`}
          aria-labelledby="module-catalog-heading"
        >
          <p className="eyebrow"><Bi zh="模块目录" en="Module Catalog" /></p>
          <h2 id="module-catalog-heading"><Bi zh="已注册模块" en="Registered modules" /></h2>
          <ModuleCatalogTable modules={modules} locale={locale} />
        </section>

        <section
          className={`panel ${channels.ok ? "" : "error-box"}`}
          aria-labelledby="channels-heading"
        >
          <p className="eyebrow"><Bi zh="渠道" en="Channels" /></p>
          <h2 id="channels-heading"><Bi zh="可用渠道" en="Available channels" /></h2>
          <ChannelsTable channels={channels} selectedChannelId={selectedChannelId} locale={locale} />
        </section>

        <section className={`panel ${models.ok ? "" : "error-box"}`} aria-labelledby="models-heading">
          <p className="eyebrow"><Bi zh="模型" en="Models" /></p>
          <h2 id="models-heading"><Bi zh="渠道模型" en="Channel models" /></h2>
          <p className="form-hint">
            <Bi
              zh="同步后请补齐上下文窗口与输出上限，便于配额预留。"
              en="After sync, set context window and output limits for quota reservation."
            />
          </p>
          {modelStatus ? (
            <p
              className={`form-status ${modelStatus === "success" ? "success-box" : modelStatus === "error" ? "error-box" : ""}`}
              data-code={modelCode}
              data-status={modelStatus}
              role={modelStatus === "error" ? "alert" : "status"}
            >
              {modelMessage}
            </p>
          ) : null}
          <ModelsTable
            canManage={canManageAdmin}
            locale={locale}
            models={models}
            selectedChannelId={selectedChannelId}
            testModelAction={testModelAction}
            updateModelAction={updateModelAction}
          />
        </section>
          </div>
        </details>
          </>
        ) : null}
        </main>
      </div>
    </div>
  );
}

export function LLMTelemetryPanels({
  activity,
  usage,
  billingUsage,
  tenantSlug,
  projectId,
  moduleKey,
  runId,
  locale,
}: {
  activity: LLMActivitySummary;
  usage: LLMUsageSummary;
  billingUsage: LLMBillingUsageSummary;
  tenantSlug: string;
  projectId: string;
  moduleKey: string;
  runId: string;
  locale: Locale;
}) {
  return (
    <>
          <section
            className={`panel ${activity.ok ? "" : "error-box"}`}
            aria-labelledby="activity-heading"
          >
            <p className="eyebrow"><Bi zh="调用活动" en="Activity" /></p>
            <h2 id="activity-heading"><Bi zh="最近调用" en="Recent calls" /></h2>
            <ActivityTable activity={activity} usage={usage} locale={locale} />
          </section>

          <section
            className={`panel ${usage.ok ? "" : "error-box"}`}
            aria-labelledby="usage-heading"
          >
            <p className="eyebrow"><Bi zh="用量" en="Usage" /></p>
            <h2 id="usage-heading"><Bi zh="用量统计" en="Usage totals" /></h2>
            <UsageTable
              usage={usage}
              activity={activity}
              tenantSlug={tenantSlug}
              projectId={projectId}
              moduleKey={moduleKey}
              runId={runId}
              locale={locale}
            />
          </section>

          <section
            className={`panel ${billingUsage.ok ? "" : "error-box"}`}
            aria-labelledby="billing-usage-heading"
          >
            <p className="eyebrow"><Bi zh="计费汇总" en="Billing Summary" /></p>
            <h2 id="billing-usage-heading"><Bi zh="可计费真实用量" en="Billing-ready actual usage" /></h2>
            <BillingUsageTable summary={billingUsage} locale={locale} />
          </section>
    </>
  );
}

export function LLMTelemetryLoading() {
  return (
    <div className="llm-telemetry-loading" aria-hidden="true">
      <span />
      <span />
      <span />
    </div>
  );
}

function TelemetryFilter({
  moduleKey,
  runId,
  selectedChannelKey,
  modules,
  locale,
}: {
  moduleKey: string;
  runId: string;
  selectedChannelKey: string;
  modules: LLMModulesSummary;
  locale: Locale;
}) {
  return (
    <form className="binding-form" method="get">
      <input type="hidden" name="channel" value={selectedChannelKey} />
      <label htmlFor="telemetry-module"><Bi zh="模块" en="Module" /></label>
      <select id="telemetry-module" name="module" defaultValue={llmModuleSegment(moduleKey)}>
        {modules.ok
          ? modules.items.map((registeredModule) => (
              <option key={registeredModule.module_key} value={llmModuleSegment(registeredModule.module_key)}>
                {moduleLabel(locale, registeredModule.module_key, registeredModule.label)}
              </option>
            ))
          : (
              <option value={llmModuleSegment(moduleKey)}>{moduleKey}</option>
            )}
      </select>

      <label htmlFor="telemetry-run-id"><Bi zh="任务 ID" en="Run ID" /></label>
      <input id="telemetry-run-id" name="run" defaultValue={runId} placeholder="run_..." />

      <button type="submit">{tx(locale, "筛选调用记录", "Filter telemetry")}</button>
    </form>
  );
}

function ChannelManagement({
  channelStatus,
  channelCode,
  channelMessage,
  syncStatus,
  syncCode,
  syncMessage,
  healthStatus,
  healthCode,
  healthMessage,
  createChannelAction,
  updateChannelAction,
  deleteChannelAction,
  syncChannelAction,
  testModelAction,
  channelModels,
  channels,
  locale,
}: {
  channelStatus: string;
  channelCode: string;
  channelMessage: string;
  syncStatus: string;
  syncCode: string;
  syncMessage: string;
  healthStatus: string;
  healthCode: string;
  healthMessage: string;
  createChannelAction: (formData: FormData) => Promise<void>;
  updateChannelAction: (formData: FormData) => Promise<void>;
  deleteChannelAction: (formData: FormData) => Promise<void>;
  syncChannelAction: (formData: FormData) => Promise<void>;
  testModelAction: (formData: FormData) => Promise<void>;
  channelModels: Record<string, LLMModelRecord[]>;
  channels: LLMChannelsSummary;
  locale: Locale;
}) {
  const channelStatusClass = channelStatus === "success" ? "success-box" : "error-box";
  const syncStatusClass = syncStatus === "success" ? "success-box" : "error-box";
  const healthStatusClass = healthStatus === "success" ? "success-box" : "error-box";

  const channelStatusSlot = (
    <>
      {channelStatus ? (
        <p
          className={`form-status ${channelStatusClass}`}
          data-code={channelCode}
          data-status={channelStatus}
          role="status"
          tabIndex={-1}
        >
          {channelMessage}
        </p>
      ) : null}
      {syncStatus ? (
        <p
          className={`form-status ${syncStatusClass}`}
          data-code={syncCode}
          data-status={syncStatus}
          role="status"
          tabIndex={-1}
        >
          {syncMessage}
        </p>
      ) : null}
      {healthStatus ? (
        <p
          className={`form-status ${healthStatusClass}`}
          data-code={healthCode}
          data-status={healthStatus}
          role={healthStatus === "error" ? "alert" : "status"}
          tabIndex={-1}
        >
          {healthMessage}
        </p>
      ) : null}
    </>
  );

  return (
    <div className="binding-stack">
      <LLMCreateChannelDialog
        createChannelAction={createChannelAction}
        forceOpen={channelStatus === "error"}
        locale={locale}
        statusSlot={channelStatusSlot}
      />

      {channels.ok && channels.items.some((channel) => channel.scope === "tenant") ? (
        <div className="llm-channel-edit-list" aria-label={tx(locale, "已配置渠道", "Configured channels")}>
          {channels.items
            .filter((channel) => channel.scope === "tenant")
            .map((channel) => {
              const anchorId = llmChannelAnchorId(channel.channel_id);
              return (
              <details
                className="llm-channel-edit-card"
                id={anchorId}
                key={channel.channel_id}
              >
                <summary>
                  <span className="llm-channel-edit-title">
                    <strong>{channel.name}</strong>
                    <span className="status-pill" data-tone={channel.enabled ? "success" : "warning"}>
                      {channel.enabled ? tx(locale, "已启用", "Enabled") : tx(locale, "已停用", "Disabled")}
                    </span>
                  </span>
                  <small className="llm-channel-edit-meta">
                    <span>{channel.provider || "openai-compatible"}</span>
                    <span title={channel.base_url}>{channel.base_url}</span>
                    <span>
                      {channel.last_sync_status
                        ? tx(locale, `同步：${channel.last_sync_status}`, `Sync: ${channel.last_sync_status}`)
                        : tx(locale, "未同步", "Not synced")}
                    </span>
                  </small>
                </summary>
                <div className="llm-channel-edit-body channel-edit-row">
                  <form action={updateChannelAction} className="binding-form">
                    <input type="hidden" name="channelId" value={channel.channel_id} />
                    <label htmlFor={`channel-name-${channel.channel_id}`}><Bi zh="更新渠道" en="Update channel" /></label>
                    <input id={`channel-name-${channel.channel_id}`} name="name" defaultValue={channel.name} required />
                    <label htmlFor={`channel-base-${channel.channel_id}`}><Bi zh="基础 URL" en="Base URL" /></label>
                    <input
                      id={`channel-base-${channel.channel_id}`}
                      name="baseUrl"
                      defaultValue={channel.base_url}
                      required
                      type="url"
                    />
                    <label htmlFor={`channel-key-${channel.channel_id}`}><Bi zh="更换 API 密钥" en="Rotate API key" /></label>
                    <input id={`channel-key-${channel.channel_id}`} name="apiKey" type="password" />
                    <label htmlFor={`channel-limit-${channel.channel_id}`}><Bi zh="最大并发数" en="Max concurrency" /></label>
                    <input
                      id={`channel-limit-${channel.channel_id}`}
                      min="1"
                      name="maxConcurrency"
                      required
                      type="number"
                      defaultValue={String(channel.max_concurrency || 1)}
                    />
                    <label className="checkbox-row">
                      <input name="enabled" type="checkbox" defaultChecked={channel.enabled} />
                      <Bi zh="启用" en="Enabled" />
                    </label>
                    <label className="checkbox-row">
                      <input
                        name="externalProviderOptIn"
                        type="checkbox"
                        defaultChecked={channelExternalOptIn(channel)}
                      />
                      <Bi zh="允许调用该外部 HTTPS 提供方" en="Allow calls to this external HTTPS provider" />
                    </label>
                    <button type="submit"><Bi zh="更新渠道" en="Update channel" /></button>
                  </form>
                  <div className="llm-channel-edit-actions">
                    <form action={syncChannelAction} className="inline-action-form">
                      <input type="hidden" name="channelId" value={channel.channel_id} />
                      <span>{channel.last_sync_status || tx(locale, "未同步", "not synced")}</span>
                      <button type="submit" disabled={!channel.enabled}>
                        <Bi zh="同步模型" en="Sync models" />
                      </button>
                    </form>
                    <ChannelModelTestForm
                      channelId={channel.channel_id}
                      disabled={!channel.enabled}
                      locale={locale}
                      models={channelModels[channel.channel_id] || []}
                      testModelAction={testModelAction}
                    />
                    <form action={deleteChannelAction} className="inline-action-form">
                      <input type="hidden" name="channelId" value={channel.channel_id} />
                      <span>{channel.name}</span>
                      <button type="submit" disabled={!channel.enabled}>
                        <Bi zh="停用" en="Disable" />
                      </button>
                    </form>
                  </div>
                </div>
              </details>
              );
            })}
        </div>
      ) : null}

      <p className="form-hint"><Bi zh="API 密钥由服务端加密存储，页面不会回显。" en="API keys are encrypted server-side and never shown again." /></p>
    </div>
  );
}

function channelExternalOptIn(channel: LLMChannelRecord) {
  return Boolean((channel as LLMChannelRecord & { external_provider_opt_in?: boolean }).external_provider_opt_in);
}

function ChannelModelTestForm({
  channelId,
  disabled,
  locale,
  models,
  testModelAction,
}: {
  channelId: string;
  disabled: boolean;
  locale: Locale;
  models: LLMModelRecord[];
  testModelAction: (formData: FormData) => Promise<void>;
}) {
  const preferred = models.find((model) => model.supports_json) || models[0];
  if (!preferred) {
    return (
      <p className="form-hint">
        <Bi zh="先同步模型后再测试连通性" en="Sync models before testing connectivity" />
      </p>
    );
  }
  return (
    <form action={testModelAction} className="inline-action-form llm-model-test-form">
      <input type="hidden" name="channelId" value={channelId} />
      <label className="sr-only" htmlFor={`test-model-${channelId}`}>
        <Bi zh="测试模型" en="Test model" />
      </label>
      <select
        id={`test-model-${channelId}`}
        name="modelId"
        defaultValue={preferred.model_id}
        disabled={disabled || models.length === 0}
      >
        {models.map((model) => (
          <option key={model.model_id} value={model.model_id}>
            {model.model_id}
          </option>
        ))}
      </select>
      <button type="submit" disabled={disabled || models.length === 0}>
        <Bi zh="测试模型" en="Test model" />
      </button>
    </form>
  );
}

function QuotaPolicyManagement({
  projectId,
  selectedModuleKey,
  modules,
  policies,
  status,
  code,
  message,
  action,
  locale,
}: {
  projectId: string;
  selectedModuleKey: string;
  modules: LLMModulesSummary;
  policies: LLMQuotaPoliciesSummary;
  status: string;
  code: string;
  message: string;
  action: (formData: FormData) => Promise<void>;
  locale: Locale;
}) {
  return (
    <div className="binding-stack">
      {status ? (
        <p className={`form-status ${status === "success" ? "success-box" : "error-box"}`} role={status === "error" ? "alert" : "status"} data-code={code}>
          {message}
        </p>
      ) : null}
      <form action={action} className="binding-form">
        <label htmlFor="quota-scope"><Bi zh="策略范围" en="Policy scope" /></label>
        <select id="quota-scope" name="scopeType" defaultValue="module">
          <option value="tenant">{tx(locale, "工作区", "Workspace")}</option>
          <option value="project">{tx(locale, "项目", "Project")}</option>
          <option value="module">{tx(locale, "模块", "Module")}</option>
        </select>
        <input type="hidden" name="projectId" value={projectId} />

        <label htmlFor="quota-module"><Bi zh="模块" en="Module" /></label>
        <select id="quota-module" name="moduleKey" defaultValue={selectedModuleKey}>
          {modules.ok
            ? modules.items.map((item) => (
                <option key={item.module_key} value={item.module_key}>{moduleLabel(locale, item.module_key, item.label)}</option>
              ))
            : <option value={selectedModuleKey}>{selectedModuleKey}</option>}
        </select>

        <label htmlFor="quota-token-limit"><Bi zh="令牌上限" en="Token limit" /></label>
        <input id="quota-token-limit" name="tokenLimit" min="0" step="1" type="number" />

        <label htmlFor="quota-cost-limit"><Bi zh="成本上限（微单位）" en="Cost limit (micros)" /></label>
        <input id="quota-cost-limit" name="costLimitMicros" min="0" step="1" type="number" />

        <label htmlFor="quota-concurrency-limit"><Bi zh="并发上限" en="Concurrency limit" /></label>
        <input id="quota-concurrency-limit" name="concurrencyLimit" min="1" step="1" type="number" />

        <label htmlFor="quota-period"><Bi zh="统计周期（秒）" en="Window (seconds)" /></label>
        <input id="quota-period" name="periodSeconds" min="1" step="1" type="number" required defaultValue="2592000" />

        <label className="checkbox-row">
          <input name="enabled" type="checkbox" defaultChecked />
          <Bi zh="执行策略" en="Enforce policy" />
        </label>
        <button type="submit"><Bi zh="保存策略" en="Save policy" /></button>
      </form>

      {!policies.ok ? (
        <p role="alert"><Bi zh="配额策略加载失败" en="Unable to load quota policies" /> <FailureText /></p>
      ) : policies.items.length === 0 ? (
        <p><Bi zh="尚未配置配额策略，生产调用将关闭失败。" en="No quota policy is configured; production calls fail closed." /></p>
      ) : (
        <div className="data-table-wrap">
          <table className="data-table">
            <thead><tr>
              <th><Bi zh="范围" en="Scope" /></th>
              <th><Bi zh="令牌" en="Tokens" /></th>
              <th><Bi zh="成本" en="Cost" /></th>
              <th><Bi zh="并发" en="Concurrency" /></th>
              <th><Bi zh="周期" en="Window" /></th>
              <th><Bi zh="状态" en="Status" /></th>
            </tr></thead>
            <tbody>{policies.items.map((policy) => (
              <tr key={policy.policy_id}>
                <td>{quotaScopeLabel(locale, policy)}</td>
                <td>{policy.token_limit ?? "-"}</td>
                <td>{policy.cost_limit_micros ?? "-"}</td>
                <td>{policy.concurrency_limit ?? "-"}</td>
                <td>{policy.period_seconds}s</td>
                <td>{policy.enabled ? tx(locale, "执行中", "Enforced") : tx(locale, "已停用", "Disabled")}</td>
              </tr>
            ))}</tbody>
          </table>
        </div>
      )}
    </div>
  );
}

function quotaScopeLabel(locale: Locale, policy: LLMQuotaPolicyRecord) {
  if (policy.scope_type === "tenant") return tx(locale, "工作区", "Workspace");
  if (policy.scope_type === "project") return `${tx(locale, "项目", "Project")}: ${policy.project_id || "-"}`;
  return `${tx(locale, "模块", "Module")}: ${policy.module_key || "-"}`;
}

function BillingUsageTable({ summary, locale }: { summary: LLMBillingUsageSummary; locale: Locale }) {
  if (!summary.ok) {
    return <p role="alert"><Bi zh="计费汇总加载失败" en="Unable to load billing summary" /> <FailureText /></p>;
  }
  if (summary.items.length === 0) {
    return <p><Bi zh="尚无可汇总的成功调用。" en="No successful calls are available for aggregation." /></p>;
  }
  return (
    <div className="data-table-wrap">
      <table className="data-table">
        <thead><tr>
          <th><Bi zh="项目" en="Project" /></th>
          <th><Bi zh="模块" en="Module" /></th>
          <th><Bi zh="模型" en="Model" /></th>
          <th><Bi zh="调用" en="Calls" /></th>
          <th><Bi zh="令牌" en="Tokens" /></th>
          <th><Bi zh="成本" en="Cost" /></th>
          <th><Bi zh="计费状态" en="Billing status" /></th>
        </tr></thead>
        <tbody>{summary.items.map((item) => (
          <tr key={`${item.project_id}-${item.module_key}-${item.model_id}`}>
            <td title={item.project_id || ""}>{item.project_id ? `${item.project_id.slice(0, 8)}…` : "-"}</td>
            <td title={item.module_key || ""}>{item.module_key ? moduleLabel(locale, item.module_key, item.module_key) : "-"}</td>
            <td>{item.model_id || "-"}</td>
            <td>{item.provider_calls}</td>
            <td>{item.tokens}</td>
            <td>{item.cost_micros ?? tx(locale, "不可用", "unavailable")}</td>
            <td>{billingStatusLabel(locale, item.billing_status)}</td>
          </tr>
        ))}</tbody>
      </table>
    </div>
  );
}

function billingStatusLabel(locale: Locale, status: LLMBillingUsageRecord["billing_status"]) {
  if (status === "billing_ready") return tx(locale, "可计费", "Billing ready");
  if (status === "pricing_unavailable") return tx(locale, "缺少价格", "Pricing unavailable");
  return tx(locale, "不可用", "Unavailable");
}

function ModuleCatalogTable({ modules, locale }: { modules: LLMModulesSummary; locale: Locale }) {
  if (!modules.ok) {
    return (
      <p>
        <Bi zh="模块加载失败" en="Unable to load modules" /> <FailureText />
      </p>
    );
  }

  if (modules.items.length === 0) {
    return <p><Bi zh="暂无已注册的 LLM 模块。" en="No registered LLM modules." /></p>;
  }

  return (
    <div className="data-table-wrap">
      <table className="data-table">
        <thead>
          <tr>
            <th><Bi zh="分组" en="Group" /></th>
            <th><Bi zh="模块" en="Module" /></th>
            <th><Bi zh="职责" en="Role" /></th>
          </tr>
        </thead>
        <tbody>
          {modules.items.map((item) => (
            <tr key={item.module_key}>
              <td>{scopeLabel(locale, item.group)}</td>
              <td title={item.module_key}>{moduleLabel(locale, item.module_key, item.label)}</td>
              <td>{item.label && item.label !== item.module_key ? item.label : "—"}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

function ChannelsTable({
  channels,
  selectedChannelId,
  locale,
}: {
  channels: LLMChannelsSummary;
  selectedChannelId: string;
  locale: Locale;
}) {
  if (!channels.ok) {
    return (
      <p>
        <Bi zh="渠道加载失败" en="Unable to load channels" /> <FailureText />
      </p>
    );
  }

  if (channels.items.length === 0) {
    return <p><Bi zh="尚未配置 LLM 渠道。" en="No LLM channels configured." /></p>;
  }

  return (
    <div className="data-table-wrap">
      <table className="data-table">
        <thead>
          <tr>
            <th><Bi zh="名称" en="Name" /></th>
            <th><Bi zh="提供方" en="Provider" /></th>
            <th><Bi zh="范围" en="Scope" /></th>
            <th><Bi zh="状态" en="Status" /></th>
            <th><Bi zh="同步" en="Sync" /></th>
          </tr>
        </thead>
        <tbody>
          {channels.items.map((item) => (
            <tr key={item.channel_id}>
              <td>{item.channel_id === selectedChannelId ? `${item.name} *` : item.name}</td>
              <td>{item.provider}</td>
              <td>{scopeLabel(locale, item.scope)}</td>
              <td>{item.enabled ? tx(locale, "已启用", "Enabled") : tx(locale, "已停用", "Disabled")}</td>
              <td>{item.last_sync_status ? `${statusLabel(locale, item.last_sync_status)} ${item.last_sync_at || ""}` : "-"}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

function ModelsTable({
  models,
  selectedChannelId,
  locale,
  canManage,
  testModelAction,
  updateModelAction,
}: {
  models: LLMChannelModelsSummary;
  selectedChannelId: string;
  locale: Locale;
  canManage: boolean;
  testModelAction: (formData: FormData) => Promise<void>;
  updateModelAction: (formData: FormData) => Promise<void>;
}) {
  if (!models.ok) {
    return (
      <p>
        <Bi zh="模型加载失败" en="Unable to load models" /> <FailureText />
      </p>
    );
  }

  if (models.items.length === 0) {
    return <p><Bi zh="该渠道暂无已同步模型。" en="No models synced for this channel." /></p>;
  }

  if (!canManage || !selectedChannelId) {
    return (
      <div className="data-table-wrap">
        <table className="data-table">
          <thead>
            <tr>
              <th><Bi zh="模型" en="Model" /></th>
              <th><Bi zh="上下文" en="Context" /></th>
              <th><Bi zh="工具调用" en="Tools" /></th>
              <th>JSON</th>
              <th><Bi zh="输入价" en="Input cost" /></th>
              <th><Bi zh="输出价" en="Output cost" /></th>
            </tr>
          </thead>
          <tbody>
            {models.items.map((item) => (
              <tr key={item.model_id}>
                <td>{item.model_id}</td>
                <td>{item.context_window || "-"}</td>
                <td>{item.supports_tools ? tx(locale, "是", "Yes") : tx(locale, "否", "No")}</td>
                <td>{item.supports_json ? tx(locale, "是", "Yes") : tx(locale, "否", "No")}</td>
                <td>{item.input_cost || "-"}</td>
                <td>{item.output_cost || "-"}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    );
  }

  return (
    <div className="llm-models-edit-list">
      {models.items.map((item) => (
        <form action={updateModelAction} className="llm-model-edit-card binding-form" key={item.model_id}>
          <input type="hidden" name="channelId" value={selectedChannelId} />
          <input type="hidden" name="modelId" value={item.model_id} />
          <div className="llm-model-edit-title">
            <strong>{item.model_id}</strong>
            {!item.context_window ? (
              <span className="status-pill" data-tone="warning">
                <Bi zh="缺 context_window" en="Missing context_window" />
              </span>
            ) : null}
          </div>
          <div className="llm-model-edit-grid">
            <label>
              <span><Bi zh="上下文窗口" en="Context window" /></span>
              <input
                defaultValue={item.context_window || ""}
                inputMode="numeric"
                min={1}
                name="contextWindow"
                placeholder="128000"
                type="number"
              />
            </label>
            <label>
              <span><Bi zh="输入价 / token" en="Input cost / token" /></span>
              <input
                defaultValue={item.input_cost || ""}
                min={0}
                name="inputCost"
                placeholder="0.001"
                step="any"
                type="number"
              />
            </label>
            <label>
              <span><Bi zh="输出价 / token" en="Output cost / token" /></span>
              <input
                defaultValue={item.output_cost || ""}
                min={0}
                name="outputCost"
                placeholder="0.002"
                step="any"
                type="number"
              />
            </label>
            <label className="llm-model-edit-check">
              <input defaultChecked={item.supports_tools} name="supportsTools" type="checkbox" />
              <span><Bi zh="工具调用" en="Tools" /></span>
            </label>
            <label className="llm-model-edit-check">
              <input defaultChecked={item.supports_json} name="supportsJSON" type="checkbox" />
              <span>JSON</span>
            </label>
            <div className="llm-model-edit-actions">
              <button type="submit">
                <Bi zh="保存模型设置" en="Save model settings" />
              </button>
              <button
                type="submit"
                formAction={testModelAction}
                formNoValidate
              >
                <Bi zh="测试连通" en="Test link" />
              </button>
            </div>
          </div>
        </form>
      ))}
    </div>
  );
}

function ModuleBindingsTable({ bindings, locale }: { bindings: LLMModuleBindingsSummary; locale: Locale }) {
  if (!bindings.ok) {
    return (
      <p>
        <Bi zh="绑定加载失败" en="Unable to load bindings" /> <FailureText />
      </p>
    );
  }

  if (bindings.items.length === 0) {
    return <p><Bi zh="尚未配置模块绑定。" en="No module bindings configured." /></p>;
  }

  return (
    <div className="data-table-wrap">
      <table className="data-table">
        <thead>
          <tr>
            <th><Bi zh="模块" en="Module" /></th>
            <th><Bi zh="范围" en="Scope" /></th>
            <th><Bi zh="渠道" en="Channel" /></th>
            <th><Bi zh="模型" en="Model" /></th>
            <th><Bi zh="输出上限" en="Output limit" /></th>
          </tr>
        </thead>
        <tbody>
          {bindings.items.map((item) => (
            <tr key={`${item.scope}-${item.module_key}`}>
              <td title={item.module_key}>{moduleLabel(locale, item.module_key, item.module_key)}</td>
              <td>{scopeLabel(locale, item.scope)}</td>
              <td>{item.channel_name || item.channel_id}</td>
              <td>{item.model_id}</td>
              <td>{settingsNumberDisplay(item.settings, "max_tokens")}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

function settingsNumberDisplay(settings: Record<string, unknown> | undefined, key: string) {
  const value = settings?.[key];
  if (typeof value === "number" && Number.isFinite(value) && value > 0) {
    return Math.trunc(value);
  }
  return "—";
}

function TenantSettingsSummary({ settingsSnapshot, locale }: { settingsSnapshot: LLMSettingsSummary; locale: Locale }) {
  if (!settingsSnapshot.ok) {
    return (
      <p>
        <Bi zh="设置加载失败" en="Unable to load settings" /> <FailureText />
      </p>
    );
  }

  return (
    <div className="binding-stack">
      <dl>
        <dt><Bi zh="已注册模块" en="Registered modules" /></dt>
        <dd>{settingsSnapshot.modules.length}</dd>
        <dt><Bi zh="可见渠道" en="Visible channels" /></dt>
        <dd>{settingsSnapshot.channels.length}</dd>
        <dt><Bi zh="工作区默认绑定" en="Workspace defaults" /></dt>
        <dd>{settingsSnapshot.tenant_bindings.length}</dd>
      </dl>
      {settingsSnapshot.tenant_bindings.length === 0 ? (
        <p><Bi zh="尚未配置工作区默认绑定。" en="No workspace default bindings configured." /></p>
      ) : (
        <div className="data-table-wrap">
          <table className="data-table">
            <thead>
              <tr>
                <th><Bi zh="模块" en="Module" /></th>
                <th><Bi zh="渠道" en="Channel" /></th>
                <th><Bi zh="模型" en="Model" /></th>
                <th><Bi zh="输出上限" en="Output limit" /></th>
              </tr>
            </thead>
            <tbody>
              {settingsSnapshot.tenant_bindings.map((binding) => (
                <tr key={`tenant-settings-${binding.module_key}`}>
                  <td>{moduleLabel(locale, binding.module_key, binding.module_key)}</td>
                  <td>{binding.channel_name || binding.channel_id}</td>
                  <td>{binding.model_id}</td>
                  <td>{settingsNumberDisplay(binding.settings, "max_tokens")}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </div>
  );
}

function ActivityTable({
  activity,
  usage,
  locale,
}: {
  activity: LLMActivitySummary;
  usage: LLMUsageSummary;
  locale: Locale;
}) {
  if (!activity.ok) {
    return (
      <p>
        <Bi zh="调用记录加载失败" en="Unable to load activity" /> <FailureText />
      </p>
    );
  }

  if (activity.items.length === 0) {
    return <p><Bi zh="暂无调用记录。" en="No activity recorded." /></p>;
  }

  return (
    <div className="data-table-wrap">
      <table className="data-table">
        <thead>
          <tr>
            <th><Bi zh="状态" en="Status" /></th>
            <th><Bi zh="模块" en="Module" /></th>
            <th><Bi zh="任务" en="Run" /></th>
            <th><Bi zh="令牌" en="Tokens" /></th>
            <th><Bi zh="延迟" en="Latency" /></th>
            <th><Bi zh="错误" en="Error" /></th>
          </tr>
        </thead>
        <tbody>
          {activity.items.map((item) => (
            <tr key={item.activity_id}>
              <td>{statusLabel(locale, item.status)}</td>
              <td title={item.module_key}>{moduleLabel(locale, item.module_key, item.module_key)}</td>
              <td title={item.run_id || ""}>{item.run_id ? `${item.run_id.slice(0, 8)}…` : "-"}</td>
              <td>{activityTokenDisplay(
                locale,
                item.prompt_tokens,
                item.completion_tokens,
                item.module_key,
                item.run_id,
                usage,
              )}</td>
              <td>{item.latency_ms ? `${item.latency_ms}ms` : "-"}</td>
              <td>{safeActivityErrorCode(item.error) || "-"}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

function UsageTable({
  usage,
  activity,
  tenantSlug,
  projectId,
  moduleKey,
  runId,
  locale,
}: {
  usage: LLMUsageSummary;
  activity: LLMActivitySummary;
  tenantSlug: string;
  projectId: string;
  moduleKey: string;
  runId: string;
  locale: Locale;
}) {
  const telemetryStatus = usageTelemetryStatus(usage, activity);
  const quotaStatus = quotaSurfaceStatus(usage);
  const measuredTokens = measuredTokenTotal(usage);

  if (!usage.ok) {
    return (
      <div className="compact-action-list">
        <UsageScope
          tenantSlug={tenantSlug}
          projectId={projectId}
          moduleKey={moduleKey}
          runId={runId}
          telemetryStatus={telemetryStatus}
          quotaStatus={quotaStatus}
          locale={locale}
        />
        <p role="alert">
          {usageFailureLabel(locale, usage.code)} <FailureText />
        </p>
      </div>
    );
  }

  return (
    <div className="compact-action-list">
      <UsageScope
        tenantSlug={tenantSlug}
        projectId={projectId}
        moduleKey={moduleKey}
        runId={runId}
        telemetryStatus={telemetryStatus}
        quotaStatus={quotaStatus}
        locale={locale}
      />
      {telemetryStatus === "zero_truth" ? (
        <p><strong>0 {tx(locale, "令牌", "tokens")}</strong></p>
      ) : telemetryStatus === "unavailable" ? (
        <p role="status"><Bi zh="真实令牌用量不可用。" en="Actual token usage is unavailable." /></p>
      ) : (
        <p><strong>{measuredTokens} {tx(locale, "令牌", "tokens")}</strong></p>
      )}
      {usage.items.length > 0 && telemetryStatus === "recorded" ? (
        <div className="data-table-wrap">
          <table className="data-table">
            <thead>
              <tr>
                <th><Bi zh="类型" en="Type" /></th>
                <th><Bi zh="数量" en="Quantity" /></th>
                <th><Bi zh="单位" en="Unit" /></th>
                <th><Bi zh="模块" en="Module" /></th>
                <th><Bi zh="任务" en="Run" /></th>
              </tr>
            </thead>
            <tbody>
              {usage.items.map((item) => (
                <tr key={`${item.usage_type}-${item.module_key}-${item.run_id}`}>
                  <td>{usageTypeLabel(locale, item.usage_type)}</td>
                  <td>{item.quantity}</td>
                  <td>{unitLabel(locale, item.unit)}</td>
                  <td title={item.module_key || ""}>{item.module_key ? moduleLabel(locale, item.module_key, item.module_key) : "-"}</td>
                  <td title={item.run_id || ""}>{item.run_id ? `${item.run_id.slice(0, 8)}…` : "-"}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      ) : null}
    </div>
  );
}

function UsageScope({
  tenantSlug,
  projectId,
  moduleKey,
  runId,
  telemetryStatus,
  quotaStatus,
  locale,
}: {
  tenantSlug: string;
  projectId: string;
  moduleKey: string;
  runId: string;
  telemetryStatus: "recorded" | "unavailable" | "zero_truth";
  quotaStatus: "exceeded" | "unavailable";
  locale: Locale;
}) {
  return (
    <>
      <div className="status-row" aria-label={tx(locale, "用量与配额状态", "Usage and quota status")}>
        <span className="status-pill" data-usage-status={telemetryStatus}>
          <Bi zh="用量" en="Usage" />: {usageStatusLabel(locale, telemetryStatus)}
        </span>
        <span className="status-pill" data-quota-status={quotaStatus}>
          <Bi zh="配额" en="Quota" />: {quotaStatusLabel(locale, quotaStatus)}
        </span>
      </div>
      <p className="trace-meta">
        <Bi zh="模块" en="Module" /> {moduleLabel(locale, moduleKey, moduleKey)}
        {runId ? <> / <Bi zh="任务" en="Run" /> {runId.slice(0, 8)}…</> : null}
      </p>
    </>
  );
}

function usageTelemetryStatus(
  usage: LLMUsageSummary,
  activity: LLMActivitySummary,
): "recorded" | "unavailable" | "zero_truth" {
  if (!usage.ok || usage.items.some((item) => item.unit !== "tokens" || !Number.isFinite(item.quantity) || item.quantity < 0)) {
    return "unavailable";
  }
  if (usage.items.length > 0) {
    return "recorded";
  }
  if (!activity.ok || activity.items.some((item) => item.status.toLowerCase() === "completed")) {
    return "unavailable";
  }
  return "zero_truth";
}

function measuredTokenTotal(usage: LLMUsageSummary) {
  if (!usage.ok) {
    return 0;
  }
  return usage.items.reduce((total, item) => total + item.quantity, 0);
}

function quotaSurfaceStatus(usage: LLMUsageSummary): "exceeded" | "unavailable" {
  return !usage.ok && QUOTA_EXCEEDED_CODES.has(usage.code) ? "exceeded" : "unavailable";
}

const QUOTA_EXCEEDED_CODES = new Set([
  "LLM_QUOTA_EXCEEDED",
  "LLM_QUOTA_TOKENS_EXCEEDED",
  "LLM_QUOTA_COST_EXCEEDED",
  "LLM_QUOTA_CONCURRENCY_EXCEEDED",
]);

function usageFailureLabel(locale: Locale, code: string) {
  if (code === "AUTH_ACCESS_DENIED" || code === "UNAUTHENTICATED") {
    return tx(locale, "无权查看用量", "Usage access denied");
  }
  if (code === "LLM_QUOTA_EXCEEDED") {
    return tx(locale, "令牌配额已用尽", "Token quota exceeded");
  }
  return tx(locale, "用量加载失败", "Unable to load usage");
}

function usageStatusLabel(locale: Locale, status: "recorded" | "unavailable" | "zero_truth") {
  const labels = {
    recorded: ["已记录", "Recorded"],
    unavailable: ["不可用", "Unavailable"],
    zero_truth: ["暂无用量", "No usage yet"],
  } as const;
  return tx(locale, labels[status][0], labels[status][1]);
}

function quotaStatusLabel(locale: Locale, status: "exceeded" | "unavailable") {
  return status === "exceeded"
    ? tx(locale, "已超额", "exceeded")
    : tx(locale, "不可用", "unavailable");
}

function activityTokenDisplay(
  locale: Locale,
  promptTokens: number,
  completionTokens: number,
  moduleKey: string,
  runId: string,
  usage: LLMUsageSummary,
) {
  const total = promptTokens + completionTokens;
  const hasMatchingUsage = usage.ok && usage.items.some((item) => (
    item.module_key === moduleKey && item.run_id === runId && item.unit === "tokens"
  ));
  if (Number.isFinite(total) && total > 0 && hasMatchingUsage) {
    return total;
  }
  return tx(locale, "不可用", "unavailable");
}

function safeActivityErrorCode(error: Record<string, unknown> | null) {
  const code = typeof error?.code === "string" ? error.code : "";
  if (!SAFE_ACTIVITY_ERROR_CODES.has(code)) {
    return "";
  }
  return ACTIVITY_ERROR_LABELS[code] || "调用失败";
}

const SAFE_ACTIVITY_ERROR_CODES = new Set([
  "LLM_CONCURRENCY_ACQUIRE_FAILED",
  "LLM_CONCURRENCY_LEASE_EXPIRED",
  "LLM_CONCURRENCY_LIMITED",
  "LLM_CONCURRENCY_RELEASE_FAILED",
  "LLM_MODULE_UNBOUND",
  "LLM_PROVIDER_ERROR",
  "LLM_PROVIDER_RATE_LIMITED",
  "LLM_PROVIDER_UNAVAILABLE",
  "LLM_QUOTA_EXCEEDED",
  "LLM_QUOTA_TOKENS_EXCEEDED",
  "LLM_QUOTA_COST_EXCEEDED",
  "LLM_QUOTA_CONCURRENCY_EXCEEDED",
  "LLM_QUOTA_USAGE_UNAVAILABLE",
  "LLM_TELEMETRY_WRITE_FAILED",
]);

const ACTIVITY_ERROR_LABELS: Record<string, string> = {
  LLM_CONCURRENCY_ACQUIRE_FAILED: "并发占用失败",
  LLM_CONCURRENCY_LEASE_EXPIRED: "并发租约过期",
  LLM_CONCURRENCY_LIMITED: "并发已达上限",
  LLM_CONCURRENCY_RELEASE_FAILED: "并发释放失败",
  LLM_MODULE_UNBOUND: "能力未绑定",
  LLM_PROVIDER_ERROR: "模型服务错误",
  LLM_PROVIDER_RATE_LIMITED: "模型限流",
  LLM_PROVIDER_UNAVAILABLE: "模型服务不可用",
  LLM_QUOTA_EXCEEDED: "额度已用尽",
  LLM_QUOTA_TOKENS_EXCEEDED: "Token 额度已用尽",
  LLM_QUOTA_COST_EXCEEDED: "成本额度已用尽",
  LLM_QUOTA_CONCURRENCY_EXCEEDED: "并发额度已用尽",
  LLM_QUOTA_USAGE_UNAVAILABLE: "用量不可用",
  LLM_TELEMETRY_WRITE_FAILED: "用量写入失败",
};

function scopeLabel(locale: Locale, value: string) {
  const labels: Record<string, [string, string]> = {
    "Archive / Assets": ["档案 / 资产", "Archive / Assets"],
    "Seed / Graph": ["导入分析 / 图谱", "Import / Graph"],
    Worldline: ["世界线", "Worldline"],
    Writer: ["写作", "Writer"],
    project: ["项目", "Project"],
    tenant: ["工作区", "Workspace"],
  };
  const label = labels[value];
  return label ? tx(locale, label[0], label[1]) : value;
}

function statusLabel(locale: Locale, value: string) {
  const labels: Record<string, [string, string]> = {
    completed: ["已完成", "Completed"],
    error: ["错误", "Error"],
    failed: ["失败", "Failed"],
    not_synced: ["未同步", "Not synced"],
    ok: ["正常", "Ready"],
    pending: ["等待中", "Pending"],
    running: ["运行中", "Running"],
    success: ["成功", "Success"],
  };
  const label = labels[value.toLowerCase()];
  return label ? tx(locale, label[0], label[1]) : value;
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

function usageTypeLabel(locale: Locale, value: string) {
  const labels: Record<string, [string, string]> = {
    calls: ["调用次数", "Calls"],
    completion_tokens: ["生成令牌", "Completion tokens"],
    prompt_tokens: ["输入令牌", "Prompt tokens"],
    tokens: ["令牌", "Tokens"],
  };
  const label = labels[value.toLowerCase()];
  return label ? tx(locale, label[0], label[1]) : value;
}

function unitLabel(locale: Locale, value: string) {
  const labels: Record<string, [string, string]> = {
    call: ["次", "calls"],
    calls: ["次", "calls"],
    token: ["令牌", "tokens"],
    tokens: ["令牌", "tokens"],
  };
  const label = labels[value.toLowerCase()];
  return label ? tx(locale, label[0], label[1]) : value;
}
