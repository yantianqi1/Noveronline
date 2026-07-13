import { describe, expect, it } from "vitest";
import type { AssistantMessage, Context, Model, MutableModels, Provider } from "@earendil-works/pi-ai";

import type { ComposeDraftRequest } from "../activities/pi-writer-activities.js";
import { createPiAIComposeDraft, type PiAIComposeDeps } from "./pi-ai-compose.js";

const request: ComposeDraftRequest = {
  tenant_id: "ten_1",
  project_id: "proj_1",
  run_id: "run_1",
  module_key: "writer_composer",
  channel_id: "channel-1",
  model_id: "model-1",
  provider: "openai-compatible",
  base_url: "https://llm.example.test/v1",
  instruction: "写下一场雨夜谈判",
  apiKey: "sk-test",
  settings: { temperature: 0.7, max_tokens: 1200 }
};

describe("createPiAIComposeDraft", () => {
  it("passes the LLM Facility key explicitly and maps the assistant draft", async () => {
    const calls: string[] = [];
    const model: Model<"openai-completions"> = {
      id: "model-1",
      name: "model-1",
      api: "openai-completions",
      provider: "mirofish-channel-1",
      baseUrl: "https://llm.example.test/v1",
      reasoning: false,
      input: ["text"],
      cost: { input: 0, output: 0, cacheRead: 0, cacheWrite: 0 },
      contextWindow: 128000,
      maxTokens: 1200
    };
    const assistant: AssistantMessage = {
      role: "assistant",
      content: [{ type: "text", text: "雨敲在谈判桌边，沉默像一根绷紧的线。" }],
      api: "openai-completions",
      provider: "mirofish-channel-1",
      model: "model-1",
      usage: {
        input: 11,
        output: 17,
        cacheRead: 0,
        cacheWrite: 0,
        totalTokens: 28,
        cost: { input: 0.0011, output: 0.0034, cacheRead: 0, cacheWrite: 0, total: 0.0045 }
      },
      stopReason: "stop",
      timestamp: 1
    };
    const models = {
      setProvider(provider: Provider) {
        calls.push(`provider:${provider.id}:${provider.baseUrl}`);
      },
      getModel(provider: string, modelId: string) {
        calls.push(`model:${provider}:${modelId}`);
        return model;
      },
      async complete(inputModel: Model<string>, context: Context, options?: {
        apiKey?: string;
        temperature?: number;
        maxTokens?: number;
        sessionId?: string;
        headers?: Record<string, string | null>;
      }) {
        const firstMessage = context.messages[0];
        calls.push(`complete:${options?.apiKey}:${options?.temperature}:${options?.maxTokens}:${options?.sessionId}:${firstMessage?.role}`);
        expect(inputModel).toBe(model);
        expect(firstMessage?.content).toBe("写下一场雨夜谈判");
        expect(options?.headers).toEqual({
          "X-MiroFish-Tenant-Id": "ten_1",
          "X-MiroFish-Project-Id": "proj_1",
          "X-MiroFish-Run-Id": "run_1",
          "X-MiroFish-Module-Key": "writer_composer"
        });
        return assistant;
      }
    } as unknown as MutableModels;

    const composeDraft = createPiAIComposeDraft({
      createModels: () => models,
      createProvider: ((input) => {
        calls.push(`create:${input.id}:${input.models[0]?.id}`);
        return input as unknown as Provider;
      }) as PiAIComposeDeps["createProvider"],
      openAICompletionsApi: () => ({}) as never
    });

    const result = await composeDraft(request);

    expect(result).toEqual({
      content: "雨敲在谈判桌边，沉默像一根绷紧的线。",
      usage: {
        prompt_tokens: 11,
        completion_tokens: 17,
        cost_estimate: 0.0045
      }
    });
    expect(calls).toEqual([
      "create:mirofish-channel-1:model-1",
      "provider:mirofish-channel-1:https://llm.example.test/v1",
      "model:mirofish-channel-1:model-1",
      "complete:sk-test:0.7:1200:run_1:user"
    ]);
  });
});
