import {
  LLMFacilityShell,
  LLMTelemetryLoading,
  LLMTelemetryPanels,
  type LLMBillingUsageSummary,
  type LLMQuotaPoliciesSummary,
} from "../../../../../../components/llm-facility-shell";
import { Suspense } from "react";
import {
  apiBaseUrl,
  deleteLLMChannel,
  deleteLLMModuleBinding,
  getCurrentUser,
  getLLMActivity,
  getLLMChannelModels,
  getLLMModuleBindings,
  getLLMModules,
  getLLMSettings,
  getLLMUsage,
  resolveLLMModuleBinding,
  syncLLMChannelModels,
  updateLLMChannelModel,
  upsertLLMModuleBinding,
  type ApiContext,
  type LLMChannelRecord,
  type LLMChannelSummary,
  type LLMChannelsSummary,
  type LLMModelRecord,
} from "../../../../../../lib/api";
import { tx } from "../../../../../../lib/locale";
import {
  canonicalLLMFacilitySearch,
  DEFAULT_LLM_MODULE_KEY,
  llmChannelKey,
  llmModuleKeyFromSegment,
  llmModulePathSegment,
  llmModuleSegment,
  resolveLLMChannelKey,
} from "../../../../../../lib/llm-facility-route";
import { currentRequestLocale } from "../../../../../../lib/request-locale";
import { currentRequestSessionCookie } from "../../../../../../lib/request-session";
import { webApiContext, webReadApiContext } from "../../../../../../lib/server-auth";
import { workspacePathForProject } from "../../../../../../lib/workspace-route";
import { redirect } from "next/navigation";

export const dynamic = "force-dynamic";

export default async function LLMFacilityPage({
  params,
  searchParams,
}: {
  params: Promise<{ tenantSlug: string; projectId: string }>;
  searchParams?: Promise<{
    bindingCode?: string;
    bindingMessage?: string;
    bindingStatus?: string;
    channelCode?: string;
    channel?: string;
    channelId?: string;
    channelMessage?: string;
    channelStatus?: string;
    moduleKey?: string;
    module?: string;
    run?: string;
    runId?: string;
    syncCode?: string;
    syncMessage?: string;
    syncStatus?: string;
    modelCode?: string;
    modelMessage?: string;
    modelStatus?: string;
    quotaCode?: string;
    quotaMessage?: string;
    quotaStatus?: string;
  }>;
}) {
  const { tenantSlug, projectId } = await params;
  const locale = await currentRequestLocale();
  const query = searchParams ? await searchParams : {};
  const moduleKey = llmModuleKeyFromSegment(query.module?.trim() || query.moduleKey?.trim() || DEFAULT_LLM_MODULE_KEY);
  const runId = query.run?.trim() || query.runId?.trim() || "";
  const apiContext = webReadApiContext({
    tenantId: tenantSlug,
    projectId,
    moduleKey,
    runId: runId || undefined,
  });
  const sessionCookie = currentRequestSessionCookie({ required: false });
  const currentUser = sessionCookie
    ? await getCurrentUser({ sessionCookie })
    : { ok: false as const, code: "UNAUTHENTICATED", message: "unauthenticated", request_id: "" };
  const tenantRole = currentUser.ok
    ? currentUser.active_tenants.find((tenant) => tenant.tenant_id === tenantSlug)?.role
    : undefined;
  const canManageAdmin = tenantRole === "owner" || tenantRole === "admin";
  const canManageBindings = canManageAdmin;

  const resolutionPromise = resolveLLMModuleBinding(apiContext);
  const modulesPromise = getLLMModules(apiContext);
  const bindingsPromise = getLLMModuleBindings(apiContext);
  const channelsPromise = getLLMChannels(apiContext);
  const settingsPromise = getLLMSettings(apiContext);
  const quotaPoliciesPromise = getQuotaPolicies(apiContext);
  const channels = await channelsPromise;
  const channelSelector = query.channel?.trim() || query.channelId?.trim() || "";
  const channelIds = channels.ok ? channels.items.map((channel) => channel.channel_id) : [];
  const defaultChannelId = channels.ok ? channels.items[0]?.channel_id || "" : "";
  const selectedChannelId = resolveLLMChannelKey(channelIds, channelSelector)
    || defaultChannelId;
  const hasDefaultChannelQuery = Boolean(channelSelector && selectedChannelId === defaultChannelId);
  const hasDefaultModuleQuery = Boolean(
    (query.module?.trim() || query.moduleKey?.trim()) && moduleKey === DEFAULT_LLM_MODULE_KEY,
  );
  if (hasDefaultChannelQuery || hasDefaultModuleQuery) {
    redirect(llmFacilityRoute(tenantSlug, projectId, searchParamsFromRecord(query), defaultChannelId));
  }
  const modelsPromise = selectedChannelId
    ? getLLMChannelModels({ ...apiContext, channelId: selectedChannelId })
    : Promise.resolve({
        ok: false as const,
        code: "LLM_CHANNEL_REQUIRED",
        message: tx(locale, "请选择渠道", "Select a channel"),
        request_id: "",
      });
  const [resolution, modules, bindings, settingsSnapshot, quotaPolicies, models] = await Promise.all([
    resolutionPromise,
    modulesPromise,
    bindingsPromise,
    settingsPromise,
    quotaPoliciesPromise,
    modelsPromise,
  ]);
  const channelModels = await loadChannelModels(apiContext, channels);

  async function bindModuleAction(formData: FormData) {
    "use server";

    const nextModuleKey = stringFromFormData(formData, "moduleKey") || DEFAULT_LLM_MODULE_KEY;
    const nextChannelId = stringFromFormData(formData, "channelId");
    const nextModelId = stringFromFormData(formData, "modelId");
    const context = await webApiContext({ tenantId: tenantSlug, projectId });
    const existingBindings = await getLLMModuleBindings(context);
    const existingSettings = existingBindings.ok
      ? existingBindings.items.find((item) => item.scope === "project" && item.module_key === nextModuleKey)?.settings
      : undefined;
    const settings = moduleBindingSettingsFromForm(formData, existingSettings, { clearEmptyMaxTokens: true });
    const result = await upsertLLMModuleBinding({
      ...context,
      projectId,
      moduleKey: nextModuleKey,
      channelId: nextChannelId,
      modelId: nextModelId,
      settings,
    });
    const maxTokensLabel = settingsNumberLabel(settings, "max_tokens");
    const nextQuery = new URLSearchParams({
      module: llmModuleSegment(nextModuleKey),
      bindingStatus: result.ok ? "success" : "error",
      bindingCode: result.ok ? "LLM_BINDING_UPDATED" : result.code,
      bindingMessage: result.ok
        ? tx(
            locale,
            maxTokensLabel
              ? `「${moduleLabel(locale, result.module_key)}」已绑定至 ${result.channel_name || result.channel_id} / ${result.model_id}，max_tokens=${maxTokensLabel}`
              : `「${moduleLabel(locale, result.module_key)}」已绑定至 ${result.channel_name || result.channel_id} / ${result.model_id}`,
            maxTokensLabel
              ? `“${moduleLabel(locale, result.module_key, result.module_key)}” bound to ${result.channel_name || result.channel_id} / ${result.model_id}, max_tokens=${maxTokensLabel}`
              : `“${moduleLabel(locale, result.module_key, result.module_key)}” bound to ${result.channel_name || result.channel_id} / ${result.model_id}`,
          )
        : bindingFailureMessage(locale, result.code, result.message),
    });
    redirect(llmFacilityRoute(tenantSlug, projectId, nextQuery, defaultChannelId));
  }

  async function batchBindModuleAction(formData: FormData) {
    "use server";

    const nextChannelId = stringFromFormData(formData, "channelId");
    const nextModelId = stringFromFormData(formData, "modelId");
    const context = await webApiContext({ tenantId: tenantSlug, projectId });
    const [modulesResult, existingBindings] = await Promise.all([
      getLLMModules(context),
      getLLMModuleBindings(context),
    ]);
    const moduleItems = modulesResult.ok ? modulesResult.items : [];
    const projectSettingsByModule = new Map(
      existingBindings.ok
        ? existingBindings.items
          .filter((item) => item.scope === "project")
          .map((item) => [item.module_key, item.settings] as const)
        : [],
    );
    let successCount = 0;
    let lastError = "";
    let lastCode = "LLM_BINDING_UPDATE_FAILED";
    let appliedMaxTokens = "";

    for (const module of moduleItems) {
      const settings = moduleBindingSettingsFromForm(
        formData,
        projectSettingsByModule.get(module.module_key),
        { clearEmptyMaxTokens: false },
      );
      if (!appliedMaxTokens) {
        appliedMaxTokens = settingsNumberLabel(settings, "max_tokens");
      }
      const result = await upsertLLMModuleBinding({
        ...context,
        projectId,
        moduleKey: module.module_key,
        channelId: nextChannelId,
        modelId: nextModelId,
        settings,
      });
      if (result.ok) {
        successCount += 1;
      } else {
        lastCode = result.code;
        lastError = result.message;
      }
    }

    const total = moduleItems.length;
    const nextQuery = new URLSearchParams({
      bindingStatus: successCount === total ? "success" : "error",
      bindingCode: successCount === total ? "LLM_BINDING_BATCH_UPDATED" : lastCode,
      bindingMessage: successCount === total
        ? tx(
            locale,
            appliedMaxTokens
              ? `已将 ${successCount} 个模块绑定至同一模型，max_tokens=${appliedMaxTokens}`
              : `已将 ${successCount} 个模块绑定至同一模型`,
            appliedMaxTokens
              ? `Bound ${successCount} modules to the same model, max_tokens=${appliedMaxTokens}`
              : `Bound ${successCount} modules to the same model`,
          )
        : tx(
            locale,
            `批量绑定部分失败：${successCount}/${total} 成功。${bindingFailureMessage(locale, lastCode, lastError)}`,
            `Batch bind partially failed: ${successCount}/${total} succeeded. ${bindingFailureMessage(locale, lastCode, lastError)}`,
          ),
    });
    redirect(llmFacilityRoute(tenantSlug, projectId, nextQuery, defaultChannelId));
  }

  async function clearBindingAction(formData: FormData) {
    "use server";

    const nextModuleKey = stringFromFormData(formData, "moduleKey") || DEFAULT_LLM_MODULE_KEY;
    const result = await deleteLLMModuleBinding({
      ...(await webApiContext({ tenantId: tenantSlug, projectId })),
      projectId,
      moduleKey: nextModuleKey,
    });
    const nextQuery = new URLSearchParams({
      channel: channelQueryValue(selectedChannelId),
      module: llmModuleSegment(nextModuleKey),
      bindingStatus: result.ok ? "success" : "error",
      bindingCode: result.ok ? "LLM_BINDING_CLEARED" : result.code,
      bindingMessage: result.ok
        ? tx(locale, "已恢复项目默认绑定", "Project default restored")
        : bindingFailureMessage(locale, result.code, result.message),
    });
    redirect(llmFacilityRoute(tenantSlug, projectId, nextQuery, defaultChannelId));
  }

  async function createChannelAction(formData: FormData) {
    "use server";

    const context = await webApiContext({ tenantId: tenantSlug });
    const result = await createLLMChannel(context, channelPayload(formData));
    const nextQuery = new URLSearchParams({
      module: llmModuleSegment(moduleKey),
      channel: channelQueryValue(result.ok ? result.channel_id : selectedChannelId),
      channelStatus: result.ok ? "success" : "error",
      channelCode: result.ok ? "LLM_CHANNEL_CREATED" : result.code,
      channelMessage: result.ok
        ? tx(locale, `已创建渠道「${result.name}」`, `Channel “${result.name}” created`)
        : result.message,
    });
    redirect(llmFacilityRoute(tenantSlug, projectId, nextQuery, defaultChannelId));
  }

  async function deleteChannelAction(formData: FormData) {
    "use server";

    const targetChannelId = stringFromFormData(formData, "channelId");
    const result = await deleteLLMChannel({
      ...(await webApiContext({ tenantId: tenantSlug })),
      channelId: targetChannelId,
    });
    const nextQuery = new URLSearchParams({
      module: llmModuleSegment(moduleKey),
      channel: channelQueryValue(result.ok ? result.channel_id : targetChannelId),
      channelStatus: result.ok ? "success" : "error",
      channelCode: result.ok ? "LLM_CHANNEL_DISABLED" : result.code,
      channelMessage: result.ok
        ? tx(locale, `已停用渠道「${result.name}」`, `Channel “${result.name}” disabled`)
        : result.message,
    });
    redirect(llmFacilityRoute(tenantSlug, projectId, nextQuery, defaultChannelId));
  }

  async function updateChannelAction(formData: FormData) {
    "use server";

    const targetChannelId = stringFromFormData(formData, "channelId");
    const context = await webApiContext({ tenantId: tenantSlug });
    const result = await updateLLMChannel(context, targetChannelId, channelPayload(formData));
    const nextQuery = new URLSearchParams({
      module: llmModuleSegment(moduleKey),
      channel: channelQueryValue(targetChannelId),
      channelStatus: result.ok ? "success" : "error",
      channelCode: result.ok ? "LLM_CHANNEL_UPDATED" : result.code,
      channelMessage: result.ok
        ? tx(locale, `已更新渠道「${result.name}」`, `Channel “${result.name}” updated`)
        : result.message,
    });
    redirect(llmFacilityRoute(tenantSlug, projectId, nextQuery, defaultChannelId));
  }

  async function syncChannelAction(formData: FormData) {
    "use server";

    const targetChannelId = stringFromFormData(formData, "channelId");
    const result = await syncLLMChannelModels({
      ...(await webApiContext({ tenantId: tenantSlug })),
      channelId: targetChannelId,
    });
    const nextQuery = new URLSearchParams({
      module: llmModuleSegment(moduleKey),
      channel: channelQueryValue(result.ok ? result.channel.channel_id : targetChannelId),
      syncStatus: result.ok ? "success" : "error",
      syncCode: result.ok ? "LLM_MODELS_SYNCED" : result.code,
      syncMessage: result.ok
        ? tx(
            locale,
            `已为「${result.channel.name || result.channel.channel_id}」同步 ${result.models.length} 个模型`,
            `${result.models.length} models synced for “${result.channel.name || result.channel.channel_id}”`,
          )
        : result.message,
    });
    redirect(llmFacilityRoute(tenantSlug, projectId, nextQuery, defaultChannelId));
  }

  async function updateModelAction(formData: FormData) {
    "use server";

    const targetChannelId = stringFromFormData(formData, "channelId") || selectedChannelId;
    const targetModelId = stringFromFormData(formData, "modelId");
    const contextWindow = optionalPositiveNumberFromFormData(formData, "contextWindow");
    const inputCost = optionalNonNegativeFloatFromFormData(formData, "inputCost");
    const outputCost = optionalNonNegativeFloatFromFormData(formData, "outputCost");
    const result = await updateLLMChannelModel({
      ...(await webApiContext({ tenantId: tenantSlug })),
      channelId: targetChannelId,
      modelId: targetModelId,
      contextWindow,
      supportsTools: stringFromFormData(formData, "supportsTools") === "on",
      supportsJSON: stringFromFormData(formData, "supportsJSON") === "on",
      inputCost,
      outputCost,
    });
    const nextQuery = new URLSearchParams({
      module: llmModuleSegment(moduleKey),
      channel: channelQueryValue(targetChannelId),
      modelStatus: result.ok ? "success" : "error",
      modelCode: result.ok ? "LLM_MODEL_UPDATED" : result.code,
      modelMessage: result.ok
        ? tx(
            locale,
            result.context_window
              ? `已更新模型「${result.model_id}」：context_window=${result.context_window}`
              : `已更新模型「${result.model_id}」`,
            result.context_window
              ? `Updated model “${result.model_id}”: context_window=${result.context_window}`
              : `Updated model “${result.model_id}”`,
          )
        : result.message,
    });
    redirect(llmFacilityRoute(tenantSlug, projectId, nextQuery, defaultChannelId));
  }

  async function upsertQuotaPolicyAction(formData: FormData) {
    "use server";

    const scopeType = stringFromFormData(formData, "scopeType") || "module";
    const context = await webApiContext({ tenantId: tenantSlug, projectId });
    const result = await putQuotaPolicy(context, {
      scope_type: scopeType,
      project_id: scopeType === "tenant" ? undefined : projectId,
      module_key: scopeType === "module" ? stringFromFormData(formData, "moduleKey") : undefined,
      token_limit: optionalNonNegativeNumberFromFormData(formData, "tokenLimit"),
      cost_limit_micros: optionalNonNegativeNumberFromFormData(formData, "costLimitMicros"),
      concurrency_limit: optionalPositiveNumberFromFormData(formData, "concurrencyLimit"),
      period_seconds: requiredPositiveNumberFromFormData(formData, "periodSeconds"),
      enabled: stringFromFormData(formData, "enabled") === "on",
    });
    const nextQuery = new URLSearchParams({
      module: llmModuleSegment(moduleKey),
      channel: channelQueryValue(selectedChannelId),
      quotaStatus: result.ok ? "success" : "error",
      quotaCode: result.ok ? "LLM_QUOTA_POLICY_UPDATED" : result.code,
      quotaMessage: result.ok
        ? tx(locale, "配额策略已保存", "Quota policy saved")
        : result.message,
    });
    redirect(llmFacilityRoute(tenantSlug, projectId, nextQuery, defaultChannelId));
  }

  return (
    <LLMFacilityShell
      locale={locale}
      tenantSlug={tenantSlug}
      projectId={projectId}
      moduleKey={moduleKey}
      runId={runId}
      selectedChannelId={selectedChannelId || ""}
      canManageAdmin={canManageAdmin}
      canManageBindings={canManageBindings}
      channelModels={channelModels}
      bindingStatus={query.bindingStatus?.trim() || ""}
      bindingCode={query.bindingCode?.trim() || ""}
      bindingMessage={query.bindingMessage?.trim() || ""}
      channelStatus={query.channelStatus?.trim() || ""}
      channelCode={query.channelCode?.trim() || ""}
      channelMessage={query.channelMessage?.trim() || ""}
      syncStatus={query.syncStatus?.trim() || ""}
      syncCode={query.syncCode?.trim() || ""}
      syncMessage={query.syncMessage?.trim() || ""}
      modelStatus={query.modelStatus?.trim() || ""}
      modelCode={query.modelCode?.trim() || ""}
      modelMessage={query.modelMessage?.trim() || ""}
      quotaStatus={query.quotaStatus?.trim() || ""}
      quotaCode={query.quotaCode?.trim() || ""}
      quotaMessage={query.quotaMessage?.trim() || ""}
      bindModuleAction={bindModuleAction}
      batchBindModuleAction={batchBindModuleAction}
      clearBindingAction={clearBindingAction}
      createChannelAction={createChannelAction}
      updateChannelAction={updateChannelAction}
      deleteChannelAction={deleteChannelAction}
      syncChannelAction={syncChannelAction}
      updateModelAction={updateModelAction}
      upsertQuotaPolicyAction={upsertQuotaPolicyAction}
      resolution={resolution}
      modules={modules}
      bindings={bindings}
      channels={channels}
      settingsSnapshot={settingsSnapshot}
      models={models}
      quotaPolicies={quotaPolicies}
      telemetryContent={
        <Suspense fallback={<LLMTelemetryLoading />}>
          <LLMTelemetryData
            apiContext={apiContext}
            locale={locale}
            moduleKey={moduleKey}
            projectId={projectId}
            runId={runId}
            tenantSlug={tenantSlug}
          />
        </Suspense>
      }
    />
  );
}

async function LLMTelemetryData({
  apiContext,
  locale,
  moduleKey,
  projectId,
  runId,
  tenantSlug,
}: {
  apiContext: ApiContext & { projectId: string; moduleKey: string; runId?: string };
  locale: Awaited<ReturnType<typeof currentRequestLocale>>;
  moduleKey: string;
  projectId: string;
  runId: string;
  tenantSlug: string;
}) {
  const [activity, usage, billingUsage] = await Promise.all([
    getLLMActivity(apiContext),
    getLLMUsage(apiContext),
    getBillingUsage(apiContext),
  ]);

  return (
    <LLMTelemetryPanels
      activity={activity}
      billingUsage={billingUsage}
      locale={locale}
      moduleKey={moduleKey}
      projectId={projectId}
      runId={runId}
      tenantSlug={tenantSlug}
      usage={usage}
    />
  );
}

function llmFacilityRoute(
  tenantId: string,
  projectId: string,
  query: URLSearchParams,
  defaultChannelId = "",
) {
  const canonicalSearch = canonicalLLMFacilitySearch(query);
  if (canonicalSearch.get("module") === llmModuleSegment(DEFAULT_LLM_MODULE_KEY)) {
    canonicalSearch.delete("module");
  }
  if (defaultChannelId && canonicalSearch.get("channel") === llmChannelKey(defaultChannelId)) {
    canonicalSearch.delete("channel");
  }
  const moduleSegment = canonicalSearch.get("module") || "";
  const moduleKey = moduleSegment ? llmModuleKeyFromSegment(moduleSegment) : DEFAULT_LLM_MODULE_KEY;
  const section = moduleKey === DEFAULT_LLM_MODULE_KEY
    ? "llm-facility"
    : `llm-facility/${llmModulePathSegment(moduleKey)}`;
  canonicalSearch.delete("module");
  const path = workspacePathForProject(
    [],
    { tenant_id: tenantId, project_id: projectId, name: "" },
    section,
  );
  const search = canonicalSearch.toString();
  return search ? `${path}?${search}` : path;
}

function channelQueryValue(channelId: string) {
  return channelId ? llmChannelKey(channelId) : "";
}

async function loadChannelModels(
  apiContext: ApiContext & { projectId: string },
  channels: LLMChannelsSummary,
): Promise<Record<string, LLMModelRecord[]>> {
  if (!channels.ok || channels.items.length === 0) {
    return {};
  }
  const entries = await Promise.all(channels.items.map(async (channel) => {
    const models = await getLLMChannelModels({ ...apiContext, channelId: channel.channel_id });
    return [channel.channel_id, models.ok ? models.items : []] as const;
  }));
  return Object.fromEntries(entries);
}

function bindingFailureMessage(locale: Awaited<ReturnType<typeof currentRequestLocale>>, code: string, fallback: string) {
  if (code === "AUTH_ACCESS_DENIED") {
    return tx(locale, "无权修改绑定，需要工作区 owner/admin 权限。", "Binding changes require workspace owner/admin access.");
  }
  if (code === "LLM_BINDING_TARGET_NOT_FOUND") {
    return tx(locale, "所选渠道与模型不匹配，请确认该渠道已同步此模型。", "The selected channel and model do not match. Sync models for that channel first.");
  }
  if (code === "VALIDATION_FAILED") {
    return tx(locale, "绑定参数无效，请重新选择渠道和模型。", "Invalid binding parameters. Re-select the channel and model.");
  }
  return fallback;
}

function moduleLabel(locale: Awaited<ReturnType<typeof currentRequestLocale>>, moduleKey: string, fallback = moduleKey) {
  const labels: Record<string, [string, string]> = {
    writer_composer: ["正文创作", "Writer Composer"],
    writer_reviewer: ["写作审校", "Writer Reviewer"],
    sequential_reading: ["顺序精读", "Sequential Reading"],
    anchor_point_summary: ["锚点摘要", "Anchor Point Summary"],
    narrative_archives: ["叙事档案", "Narrative Archives"],
    asset_ingestion: ["资产导入", "Asset Ingestion"],
    style_extractor: ["风格提取", "Style Extractor"],
    graph_bond_generator: ["图谱关系生成", "Graph Bond Generator"],
    worldline_director: ["世界线导演", "Worldline Director"],
  };
  const label = labels[moduleKey];
  return label ? tx(locale, label[0], label[1]) : fallback;
}

function searchParamsFromRecord(query: Record<string, string | undefined>) {
  const result = new URLSearchParams();
  for (const [key, value] of Object.entries(query)) {
    if (value !== undefined) {
      result.set(key, value);
    }
  }
  return result;
}

function stringFromFormData(formData: FormData, key: string) {
  const value = formData.get(key);
  return typeof value === "string" ? value.trim() : "";
}

function positiveNumberFromFormData(formData: FormData, key: string) {
  const value = Number.parseInt(stringFromFormData(formData, key), 10);
  return Number.isFinite(value) && value > 0 ? value : 1;
}

function optionalPositiveNumberFromFormData(formData: FormData, key: string) {
  const rawValue = stringFromFormData(formData, key);
  if (!rawValue) {
    return undefined;
  }
  const value = Number.parseInt(rawValue, 10);
  return Number.isFinite(value) && value > 0 ? value : undefined;
}

function moduleBindingSettingsFromForm(
  formData: FormData,
  existing: Record<string, unknown> | undefined,
  options: { clearEmptyMaxTokens: boolean },
): Record<string, unknown> {
  const settings: Record<string, unknown> = { ...(existing || {}) };
  const rawMaxTokens = stringFromFormData(formData, "maxTokens");
  if (rawMaxTokens) {
    const maxTokens = optionalPositiveNumberFromFormData(formData, "maxTokens");
    if (maxTokens !== undefined) {
      settings.max_tokens = maxTokens;
    }
  } else if (options.clearEmptyMaxTokens) {
    delete settings.max_tokens;
  }

  const rawMaxConcurrency = stringFromFormData(formData, "moduleMaxConcurrency");
  if (rawMaxConcurrency) {
    const maxConcurrency = optionalPositiveNumberFromFormData(formData, "moduleMaxConcurrency");
    if (maxConcurrency !== undefined) {
      settings.max_concurrency = maxConcurrency;
    }
  } else if (options.clearEmptyMaxTokens && formData.has("moduleMaxConcurrency")) {
    delete settings.max_concurrency;
  }

  return settings;
}

function settingsNumberLabel(settings: Record<string, unknown>, key: string) {
  const value = settings[key];
  if (typeof value === "number" && Number.isFinite(value) && value > 0) {
    return String(Math.trunc(value));
  }
  return "";
}

function requiredPositiveNumberFromFormData(formData: FormData, key: string) {
  const value = Number.parseInt(stringFromFormData(formData, key), 10);
  return Number.isFinite(value) && value > 0 ? value : 0;
}

function optionalNonNegativeNumberFromFormData(formData: FormData, key: string) {
  const rawValue = stringFromFormData(formData, key);
  if (!rawValue) return undefined;
  const value = Number.parseInt(rawValue, 10);
  return Number.isFinite(value) && value >= 0 ? value : undefined;
}

function optionalNonNegativeFloatFromFormData(formData: FormData, key: string) {
  const rawValue = stringFromFormData(formData, key);
  if (!rawValue) return undefined;
  const value = Number.parseFloat(rawValue);
  return Number.isFinite(value) && value >= 0 ? value : undefined;
}

function channelPayload(formData: FormData) {
  return {
    name: stringFromFormData(formData, "name"),
    provider: stringFromFormData(formData, "provider") || "openai-compatible",
    base_url: stringFromFormData(formData, "baseUrl"),
    api_key: stringFromFormData(formData, "apiKey"),
    max_concurrency: positiveNumberFromFormData(formData, "maxConcurrency"),
    external_provider_opt_in: stringFromFormData(formData, "externalProviderOptIn") === "on",
    enabled: stringFromFormData(formData, "enabled") === "on",
  };
}

async function getLLMChannels(
  input: ApiContext & { projectId: string },
): Promise<LLMChannelsSummary> {
  try {
    const response = await fetch(`${apiBaseUrl()}/v1/projects/${input.projectId}/llm/channels`, {
      headers: managedHeaders(input),
      cache: "no-store",
    });
    const payload = await responseJSON(response);
    if (!response.ok) return managedFailure(payload, response.status, "LLM_CATALOG_QUERY_FAILED");
    return { ok: true, items: Array.isArray(payload.items) ? payload.items as LLMChannelRecord[] : [] };
  } catch {
    return managedNetworkFailure("LLM_CATALOG_QUERY_FAILED");
  }
}

async function mutateManagedLLMChannel(
  input: ApiContext,
  method: "POST" | "PATCH",
  channelId: string,
  rawPayload: ReturnType<typeof channelPayload>,
): Promise<LLMChannelSummary> {
  try {
    const endpoint = channelId ? `/v1/llm/channels/${channelId}` : "/v1/llm/channels";
    const payload: Record<string, unknown> = { ...rawPayload };
    if (method === "PATCH") delete payload.provider;
    const response = await fetch(`${apiBaseUrl()}${endpoint}`, {
      method,
      headers: { ...managedHeaders(input), "Content-Type": "application/json" },
      body: JSON.stringify(payload),
      cache: "no-store",
    });
    const decoded = await responseJSON(response);
    if (!response.ok) return managedFailure(decoded, response.status, "LLM_CHANNEL_UPDATE_FAILED");
    return { ok: true, ...decoded } as LLMChannelSummary;
  } catch {
    return managedNetworkFailure("LLM_CHANNEL_UPDATE_FAILED");
  }
}

function createLLMChannel(input: ApiContext, payload: ReturnType<typeof channelPayload>) {
  return mutateManagedLLMChannel(input, "POST", "", payload);
}

function updateLLMChannel(input: ApiContext, channelId: string, payload: ReturnType<typeof channelPayload>) {
  return mutateManagedLLMChannel(input, "PATCH", channelId, payload);
}

async function getQuotaPolicies(
  input: ApiContext & { projectId: string; moduleKey?: string },
): Promise<LLMQuotaPoliciesSummary> {
  try {
    const url = new URL(`${apiBaseUrl()}/v1/projects/${input.projectId}/llm/quota-policies`);
    if (input.moduleKey) url.searchParams.set("module_key", input.moduleKey);
    const response = await fetch(url, { headers: managedHeaders(input), cache: "no-store" });
    const payload = await responseJSON(response);
    if (!response.ok) return managedFailure(payload, response.status, "LLM_QUOTA_POLICY_QUERY_FAILED");
    return { ok: true, items: Array.isArray(payload.items) ? payload.items as never[] : [] };
  } catch {
    return managedNetworkFailure("LLM_QUOTA_POLICY_QUERY_FAILED");
  }
}

async function getBillingUsage(
  input: ApiContext & { projectId: string; moduleKey?: string },
): Promise<LLMBillingUsageSummary> {
  try {
    const url = new URL(`${apiBaseUrl()}/v1/projects/${input.projectId}/llm/billing-usage`);
    if (input.moduleKey) url.searchParams.set("module_key", input.moduleKey);
    const response = await fetch(url, { headers: managedHeaders(input), cache: "no-store" });
    const payload = await responseJSON(response);
    if (!response.ok) return managedFailure(payload, response.status, "LLM_BILLING_USAGE_QUERY_FAILED");
    return { ok: true, items: Array.isArray(payload.items) ? payload.items as never[] : [] };
  } catch {
    return managedNetworkFailure("LLM_BILLING_USAGE_QUERY_FAILED");
  }
}

async function putQuotaPolicy(input: ApiContext & { projectId: string }, payload: Record<string, unknown>) {
  try {
    const response = await fetch(`${apiBaseUrl()}/v1/projects/${input.projectId}/llm/quota-policies`, {
      method: "PUT",
      headers: { ...managedHeaders(input), "Content-Type": "application/json" },
      body: JSON.stringify(payload),
      cache: "no-store",
    });
    const decoded = await responseJSON(response);
    if (!response.ok) return managedFailure(decoded, response.status, "LLM_QUOTA_POLICY_UPDATE_FAILED");
    return { ok: true as const, ...decoded };
  } catch {
    return managedNetworkFailure("LLM_QUOTA_POLICY_UPDATE_FAILED");
  }
}

function managedHeaders(input: ApiContext) {
  const headers: Record<string, string> = { "X-Tenant-Id": input.tenantId };
  if (input.sessionCookie) {
    headers.Cookie = `mirofish_session=${input.sessionCookie}`;
    if (input.csrfToken) headers["X-CSRF-Token"] = input.csrfToken;
  } else if (input.actorUserId) {
    headers["X-User-Id"] = input.actorUserId;
  }
  return headers;
}

async function responseJSON(response: Response): Promise<Record<string, unknown>> {
  const payload = await response.json().catch(() => ({}));
  return payload && typeof payload === "object" ? payload as Record<string, unknown> : {};
}

function managedFailure(payload: Record<string, unknown>, status: number, fallbackCode: string) {
  const error = payload.error && typeof payload.error === "object" ? payload.error as Record<string, unknown> : {};
  return {
    ok: false as const,
    code: typeof error.code === "string" ? error.code : fallbackCode,
    message: typeof error.message === "string" ? error.message : `HTTP ${status}`,
    request_id: typeof error.request_id === "string" ? error.request_id : "",
  };
}

function managedNetworkFailure(code: string) {
  return { ok: false as const, code, message: "LLM Facility request failed", request_id: "" };
}
