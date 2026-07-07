import {
  createModels,
  createProvider,
  type AssistantMessage,
  type Context,
  type Model
} from "@earendil-works/pi-ai";
import { openAICompletionsApi } from "@earendil-works/pi-ai/api/openai-completions.lazy";

import type { ComposeDraftRequest, ComposeDraftResult } from "../activities/pi-writer-activities.js";

export interface PiAIComposeDeps {
  createModels: typeof createModels;
  createProvider: typeof createProvider;
  openAICompletionsApi: typeof openAICompletionsApi;
}

const defaultDeps: PiAIComposeDeps = {
  createModels,
  createProvider,
  openAICompletionsApi
};

export function createPiAIComposeDraft(deps: PiAIComposeDeps = defaultDeps) {
  return async function composeDraft(request: ComposeDraftRequest): Promise<ComposeDraftResult> {
    const providerId = providerIdFromChannel(request.channel_id);
    const model = openAICompatibleModel(request, providerId);
    const provider = deps.createProvider({
      id: providerId,
      name: `MiroFish ${request.provider}`,
      baseUrl: request.base_url,
      auth: {
        apiKey: {
          name: "MiroFish LLM Facility request key",
          resolve: async () => ({ auth: {} })
        }
      },
      models: [model],
      api: deps.openAICompletionsApi()
    });
    const models = deps.createModels();
    models.setProvider(provider);
    const resolvedModel = models.getModel(providerId, request.model_id);
    if (!resolvedModel) {
      throw new Error(`resolved model ${request.model_id} is not registered for ${providerId}`);
    }

    const message = await models.complete(resolvedModel, contextFromRequest(request), {
      apiKey: request.apiKey,
      temperature: numberSetting(request.settings, "temperature"),
      maxTokens: numberSetting(request.settings, "max_tokens"),
      sessionId: request.run_id,
      metadata: {
        tenant_id: request.tenant_id,
        project_id: request.project_id,
        run_id: request.run_id,
        module_key: request.module_key
      }
    });
    return {
      content: textContent(message),
      usage: {
        prompt_tokens: message.usage.input,
        completion_tokens: message.usage.output,
        cost_estimate: message.usage.cost.total
      }
    };
  };
}

function openAICompatibleModel(request: ComposeDraftRequest, providerId: string): Model<"openai-completions"> {
  const maxTokens = numberSetting(request.settings, "max_tokens") ?? 4000;
  return {
    id: request.model_id,
    name: request.model_id,
    api: "openai-completions",
    provider: providerId,
    baseUrl: request.base_url,
    reasoning: Boolean(request.settings.reasoning),
    input: ["text"],
    cost: {
      input: numberSetting(request.settings, "input_cost") ?? 0,
      output: numberSetting(request.settings, "output_cost") ?? 0,
      cacheRead: 0,
      cacheWrite: 0
    },
    contextWindow: numberSetting(request.settings, "context_window") ?? 128000,
    maxTokens
  };
}

function contextFromRequest(request: ComposeDraftRequest): Context {
  const systemPrompt = stringSetting(request.settings, "system_prompt");
  return {
    systemPrompt,
    messages: [
      {
        role: "user",
        content: request.instruction,
        timestamp: Date.now()
      }
    ]
  };
}

function textContent(message: AssistantMessage): string {
  if (message.stopReason === "error" || message.stopReason === "aborted") {
    throw new Error(message.errorMessage ?? "Pi AI provider returned an error");
  }
  return message.content
    .filter((block) => block.type === "text")
    .map((block) => block.text)
    .join("");
}

function providerIdFromChannel(channelId: string): string {
  return `mirofish-${channelId.replace(/[^a-zA-Z0-9_-]/g, "-")}`;
}

function numberSetting(settings: Record<string, unknown>, key: string): number | undefined {
  const value = settings[key];
  return typeof value === "number" && Number.isFinite(value) ? value : undefined;
}

function stringSetting(settings: Record<string, unknown>, key: string): string | undefined {
  const value = settings[key];
  return typeof value === "string" && value.trim() !== "" ? value : undefined;
}
