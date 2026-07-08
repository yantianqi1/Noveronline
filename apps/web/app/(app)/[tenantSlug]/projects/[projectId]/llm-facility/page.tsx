import { LLMFacilityShell } from "../../../../../../components/llm-facility-shell";
import {
  createLLMChannel,
  deleteLLMChannel,
  deleteLLMModuleBinding,
  getLLMActivity,
  getLLMChannelModels,
  getLLMChannels,
  getLLMModuleBindings,
  getLLMModules,
  getLLMSettings,
  getLLMUsage,
  resolveLLMModuleBinding,
  syncLLMChannelModels,
  updateLLMChannel,
  upsertLLMModuleBinding,
} from "../../../../../../lib/api";
import { webApiContext } from "../../../../../../lib/server-auth";
import { redirect } from "next/navigation";

export const dynamic = "force-dynamic";

const DEFAULT_MODULE_KEY = "writer_composer";

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
    channelId?: string;
    channelMessage?: string;
    channelStatus?: string;
    moduleKey?: string;
    runId?: string;
    syncCode?: string;
    syncMessage?: string;
    syncStatus?: string;
  }>;
}) {
  const { tenantSlug, projectId } = await params;
  const query = searchParams ? await searchParams : {};
  const moduleKey = query.moduleKey?.trim() || DEFAULT_MODULE_KEY;
  const runId = query.runId?.trim() || "";
  const apiContext = await webApiContext({
    tenantId: tenantSlug,
    projectId,
    moduleKey,
    runId: runId || undefined,
  });

  const [resolution, modules, bindings, channels, settingsSnapshot, activity, usage] = await Promise.all([
    resolveLLMModuleBinding(apiContext),
    getLLMModules(apiContext),
    getLLMModuleBindings(apiContext),
    getLLMChannels(apiContext),
    getLLMSettings(apiContext),
    getLLMActivity(apiContext),
    getLLMUsage(apiContext),
  ]);
  const selectedChannelId = query.channelId?.trim() || (channels.ok ? channels.items[0]?.channel_id : "");
  const models = selectedChannelId
    ? await getLLMChannelModels({ ...apiContext, channelId: selectedChannelId })
    : {
        ok: false as const,
        code: "LLM_CHANNEL_REQUIRED",
        message: "No channel selected for model catalog",
        request_id: "",
      };

  async function bindModuleAction(formData: FormData) {
    "use server";

    const nextModuleKey = stringFromFormData(formData, "moduleKey") || DEFAULT_MODULE_KEY;
    const nextChannelId = stringFromFormData(formData, "channelId");
    const nextModelId = stringFromFormData(formData, "modelId");
    const moduleMaxConcurrency = optionalPositiveNumberFromFormData(formData, "moduleMaxConcurrency");
    const result = await upsertLLMModuleBinding({
      ...(await webApiContext({ tenantId: tenantSlug, projectId })),
      projectId,
      moduleKey: nextModuleKey,
      channelId: nextChannelId,
      modelId: nextModelId,
      settings: moduleMaxConcurrency ? { max_concurrency: moduleMaxConcurrency } : {},
    });
    const nextQuery = new URLSearchParams({
      channelId: nextChannelId,
      moduleKey: nextModuleKey,
      bindingStatus: result.ok ? "success" : "error",
      bindingCode: result.ok ? "LLM_BINDING_UPDATED" : result.code,
      bindingMessage: result.ok
        ? `${result.module_key} bound to ${result.channel_name || result.channel_id} / ${result.model_id}`
        : result.message,
    });
    redirect(`/${tenantSlug}/projects/${projectId}/llm-facility?${nextQuery.toString()}`);
  }

  async function clearBindingAction(formData: FormData) {
    "use server";

    const nextModuleKey = stringFromFormData(formData, "moduleKey") || DEFAULT_MODULE_KEY;
    const result = await deleteLLMModuleBinding({
      ...(await webApiContext({ tenantId: tenantSlug, projectId })),
      projectId,
      moduleKey: nextModuleKey,
    });
    const nextQuery = new URLSearchParams({
      channelId: selectedChannelId,
      moduleKey: nextModuleKey,
      bindingStatus: result.ok ? "success" : "error",
      bindingCode: result.ok ? "LLM_BINDING_CLEARED" : result.code,
      bindingMessage: result.ok
        ? `${result.module_key} project override cleared`
        : result.message,
    });
    redirect(`/${tenantSlug}/projects/${projectId}/llm-facility?${nextQuery.toString()}`);
  }

  async function createChannelAction(formData: FormData) {
    "use server";

    const result = await createLLMChannel({
      ...(await webApiContext({ tenantId: tenantSlug })),
      name: stringFromFormData(formData, "name"),
      provider: stringFromFormData(formData, "provider") || "openai-compatible",
      baseUrl: stringFromFormData(formData, "baseUrl"),
      apiKey: stringFromFormData(formData, "apiKey"),
      maxConcurrency: positiveNumberFromFormData(formData, "maxConcurrency"),
      enabled: stringFromFormData(formData, "enabled") === "on",
    });
    const nextQuery = new URLSearchParams({
      moduleKey,
      channelId: result.ok ? result.channel_id : selectedChannelId,
      channelStatus: result.ok ? "success" : "error",
      channelCode: result.ok ? "LLM_CHANNEL_CREATED" : result.code,
      channelMessage: result.ok ? `${result.name} created` : result.message,
    });
    redirect(`/${tenantSlug}/projects/${projectId}/llm-facility?${nextQuery.toString()}`);
  }

  async function deleteChannelAction(formData: FormData) {
    "use server";

    const targetChannelId = stringFromFormData(formData, "channelId");
    const result = await deleteLLMChannel({
      ...(await webApiContext({ tenantId: tenantSlug })),
      channelId: targetChannelId,
    });
    const nextQuery = new URLSearchParams({
      moduleKey,
      channelId: result.ok ? result.channel_id : targetChannelId,
      channelStatus: result.ok ? "success" : "error",
      channelCode: result.ok ? "LLM_CHANNEL_DISABLED" : result.code,
      channelMessage: result.ok ? `${result.name} disabled` : result.message,
    });
    redirect(`/${tenantSlug}/projects/${projectId}/llm-facility?${nextQuery.toString()}`);
  }

  async function updateChannelAction(formData: FormData) {
    "use server";

    const targetChannelId = stringFromFormData(formData, "channelId");
    const result = await updateLLMChannel({
      ...(await webApiContext({ tenantId: tenantSlug })),
      channelId: targetChannelId,
      name: stringFromFormData(formData, "name"),
      baseUrl: stringFromFormData(formData, "baseUrl"),
      apiKey: stringFromFormData(formData, "apiKey"),
      maxConcurrency: positiveNumberFromFormData(formData, "maxConcurrency"),
      enabled: stringFromFormData(formData, "enabled") === "on",
    });
    const nextQuery = new URLSearchParams({
      moduleKey,
      channelId: targetChannelId,
      channelStatus: result.ok ? "success" : "error",
      channelCode: result.ok ? "LLM_CHANNEL_UPDATED" : result.code,
      channelMessage: result.ok ? `${result.name} updated` : result.message,
    });
    redirect(`/${tenantSlug}/projects/${projectId}/llm-facility?${nextQuery.toString()}`);
  }

  async function syncChannelAction(formData: FormData) {
    "use server";

    const targetChannelId = stringFromFormData(formData, "channelId");
    const result = await syncLLMChannelModels({
      ...(await webApiContext({ tenantId: tenantSlug })),
      channelId: targetChannelId,
    });
    const nextQuery = new URLSearchParams({
      moduleKey,
      channelId: result.ok ? result.channel.channel_id : targetChannelId,
      syncStatus: result.ok ? "success" : "error",
      syncCode: result.ok ? "LLM_MODELS_SYNCED" : result.code,
      syncMessage: result.ok
        ? `${result.models.length} models synced for ${result.channel.name || result.channel.channel_id}`
        : result.message,
    });
    redirect(`/${tenantSlug}/projects/${projectId}/llm-facility?${nextQuery.toString()}`);
  }

  return (
    <LLMFacilityShell
      tenantSlug={tenantSlug}
      projectId={projectId}
      moduleKey={moduleKey}
      runId={runId}
      selectedChannelId={selectedChannelId || ""}
      bindingStatus={query.bindingStatus?.trim() || ""}
      bindingCode={query.bindingCode?.trim() || ""}
      bindingMessage={query.bindingMessage?.trim() || ""}
      channelStatus={query.channelStatus?.trim() || ""}
      channelCode={query.channelCode?.trim() || ""}
      channelMessage={query.channelMessage?.trim() || ""}
      syncStatus={query.syncStatus?.trim() || ""}
      syncCode={query.syncCode?.trim() || ""}
      syncMessage={query.syncMessage?.trim() || ""}
      bindModuleAction={bindModuleAction}
      clearBindingAction={clearBindingAction}
      createChannelAction={createChannelAction}
      updateChannelAction={updateChannelAction}
      deleteChannelAction={deleteChannelAction}
      syncChannelAction={syncChannelAction}
      resolution={resolution}
      modules={modules}
      bindings={bindings}
      channels={channels}
      settingsSnapshot={settingsSnapshot}
      models={models}
      activity={activity}
      usage={usage}
    />
  );
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
