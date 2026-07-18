import { Agent, type AgentEvent, type AgentTool } from "@earendil-works/pi-agent-core";
import {
  createModels,
  createProvider,
  type AssistantMessage,
  type Model
} from "@earendil-works/pi-ai";
import { openAICompletionsApi } from "@earendil-works/pi-ai/api/openai-completions.lazy";
import { Array as ArraySchema, Object as ObjectSchema, Optional, String as StringSchema } from "typebox";

import type { PiWorldlineCastUsage } from "../activities/pi-worldline-cast-activities.js";
import type { WorldlineCastToolName } from "../contracts/worldline-cast-run.js";
import { worldlineCastRuntimeContextFromInput } from "../contracts/worldline-cast-run.js";
import {
  assertWorldlineCastToolAllowed,
  WorldlineCastToolPermissionDenied
} from "../tools/worldline-cast-permissions.js";

const emptyArgs = ObjectSchema({}, { additionalProperties: false });
const neighborsArgs = ObjectSchema({
  graph_node_ids: ArraySchema(StringSchema({ minLength: 1 }), { minItems: 1, maxItems: 20 })
}, { additionalProperties: false });
const castRefSchema = ObjectSchema({
  source_kind: StringSchema({ minLength: 1 }),
  source_id: StringSchema({ minLength: 1 })
}, { additionalProperties: false });
const commitArgs = ObjectSchema({
  agent_refs: ArraySchema(castRefSchema, { minItems: 1, maxItems: 8 }),
  source_refs: Optional(ArraySchema(castRefSchema, { maxItems: 20 })),
  rationale: StringSchema({ minLength: 1 })
}, { additionalProperties: false });

export interface WorldlineCastStageRequest {
  tenant_id: string;
  project_id: string;
  run_id: string;
  module_key: "worldline_cast_planner";
  channel_id: string;
  model_id: string;
  provider: string;
  base_url: string;
  apiKey: string;
  goal: string;
  thinking_level?: "off" | "minimal" | "low" | "medium" | "high" | "xhigh";
  tool_execution?: "sequential" | "parallel";
  tool_names: WorldlineCastToolName[];
  settings: Record<string, unknown>;
  provider_call_id?: string;
  abort_signal?: AbortSignal;
  executeTool(
    toolName: WorldlineCastToolName,
    toolCallId: string,
    args?: Record<string, unknown>
  ): Promise<Record<string, unknown>>;
  onAgentEvent?(event: AgentEvent): Promise<void>;
}

export interface WorldlineCastStageResult {
  summary: string;
  usage?: PiWorldlineCastUsage;
}

export function createPiWorldlineCastExecution() {
  return {
    runCastStage: async (request: WorldlineCastStageRequest): Promise<WorldlineCastStageResult> => {
      const runtime = createRuntime(request);
      let permissionError: WorldlineCastToolPermissionDenied | undefined;
      const tools = request.tool_names.map((name) => castTool(name, request, (error) => {
        permissionError = error;
      }));
      const agent = new Agent({
        initialState: {
          systemPrompt: systemPrompt(),
          model: runtime.model,
          thinkingLevel: request.thinking_level ?? "off",
          tools
        },
        streamFn: runtime.streamFn,
        getApiKey: (provider) => (provider === runtime.providerId ? request.apiKey : undefined),
        toolExecution: request.tool_execution ?? "sequential",
        beforeToolCall: async ({ toolCall }) => {
          try {
            const context = worldlineCastRuntimeContextFromInput(request);
            assertWorldlineCastToolAllowed(
              toolCall.name,
              toolCall.arguments as Record<string, unknown> | undefined,
              context
            );
            return undefined;
          } catch (error) {
            if (!(error instanceof WorldlineCastToolPermissionDenied)) throw error;
            permissionError = error;
            return { block: true, reason: error.message };
          }
        },
        sessionId: `${request.run_id}:worldline_cast_planner`
      });
      agent.subscribe(async (event) => {
        await request.onAgentEvent?.(event);
      });
      await promptWithAbort(agent, userPrompt(request), request.abort_signal);
      if (permissionError) throw permissionError;
      const message = finalAssistantMessage(agent.state.messages);
      const content = assistantText(message).trim();
      return {
        summary: (content || "选角完成").slice(0, 4000),
        usage: aggregateUsage(agent.state.messages)
      };
    }
  };
}

function castTool(
  name: WorldlineCastToolName,
  request: WorldlineCastStageRequest,
  onPermissionError: (error: WorldlineCastToolPermissionDenied) => void
): AgentTool<any> {
  return {
    name,
    label: name,
    description: toolDescription(name),
    parameters: toolParameters(name),
    executionMode: name === "commit_worldline_cast" ? "sequential" : "parallel",
    execute: async (_toolCallId, params, signal) => {
      if (signal?.aborted) throw new Error("worldline cast tool execution aborted");
      try {
        const args = (params && typeof params === "object" ? params : {}) as Record<string, unknown>;
        const details = await request.executeTool(name, _toolCallId, args);
        return {
          content: [{ type: "text", text: JSON.stringify(details) }],
          details
        };
      } catch (error) {
        if (error instanceof WorldlineCastToolPermissionDenied) {
          onPermissionError(error);
        }
        throw error;
      }
    }
  };
}

function toolParameters(name: WorldlineCastToolName) {
  switch (name) {
    case "query_graph_neighbors":
      return neighborsArgs;
    case "commit_worldline_cast":
      return commitArgs;
    default:
      return emptyArgs;
  }
}

function toolDescription(name: WorldlineCastToolName): string {
  const descriptions: Record<WorldlineCastToolName, string> = {
    query_project_context: "Read project metadata for the current novel project.",
    query_character_profile: "List character entities, character assets, and graph character nodes available for casting.",
    query_assets: "List enabled lore/assets that may be useful as simulation context.",
    query_graph_neighbors: "Inspect relationships around selected graph node IDs.",
    commit_worldline_cast: "Commit the final agent_refs and source_refs for this simulation goal. Call exactly once when ready."
  };
  return descriptions[name];
}

function systemPrompt(): string {
  return [
    "You are the MiroFish worldline cast planner.",
    "The author provided a simulation goal. Analyze project characters and lore, then select who must participate.",
    "Rules:",
    "- Use tools to inspect candidates; do not invent IDs.",
    "- Prefer 3–5 participating agents; never exceed 8.",
    "- agent_refs may only use source_kind asset or entity with real source_id values from tools.",
    "- source_refs may use asset, entity, or saved_path for supporting context.",
    "- Write rationale and any author-facing summary in Simplified Chinese.",
    "- When the cast is ready, call commit_worldline_cast exactly once, then reply with a short Chinese summary.",
    "- Do not prepare dossiers, start sessions, or write canon yourself."
  ].join("\n");
}

function userPrompt(request: WorldlineCastStageRequest): string {
  return JSON.stringify({
    task: "select_worldline_cast",
    goal: request.goal
  });
}

function createRuntime(request: WorldlineCastStageRequest) {
  const parentProviderCallID = request.provider_call_id?.trim();
  if (!parentProviderCallID) {
    throw new Error("LLM_PROVIDER_CALL_ID_INVALID: Pi worldline cast provider call identity is required");
  }
  const providerId = `mirofish-${request.channel_id.replace(/[^a-zA-Z0-9_-]/g, "-")}`;
  const model = openAICompatibleModel(request, providerId);
  const provider = createProvider({
    id: providerId,
    name: `MiroFish ${request.provider}`,
    baseUrl: request.base_url,
    auth: { apiKey: { name: "MiroFish LLM Facility request key", resolve: async () => ({ auth: {} }) } },
    models: [model],
    api: openAICompletionsApi()
  });
  const models = createModels();
  models.setProvider(provider);
  const resolved = models.getModel(providerId, request.model_id);
  if (!resolved) throw new Error("Pi worldline cast resolved model is unavailable");
  let turnIndex = 0;
  const streamFn = (
    modelArg: Parameters<typeof models.streamSimple>[0],
    context: Parameters<typeof models.streamSimple>[1],
    options?: Parameters<typeof models.streamSimple>[2]
  ) => {
    const turnCallID = `${parentProviderCallID}:turn:${turnIndex++}`;
    return models.streamSimple({
      ...modelArg,
      headers: {
        ...modelArg.headers,
        "Idempotency-Key": turnCallID,
        "X-MiroFish-Provider-Call-Parent": parentProviderCallID
      }
    }, context, options);
  };
  return { providerId, model: resolved, models, streamFn };
}

function openAICompatibleModel(request: WorldlineCastStageRequest, providerId: string): Model<"openai-completions"> {
  return {
    id: request.model_id,
    name: request.model_id,
    api: "openai-completions",
    provider: providerId,
    baseUrl: request.base_url,
    reasoning: Boolean(request.settings.reasoning),
    input: ["text"],
    cost: {
      input: numericSetting(request.settings, "input_cost") ?? 0,
      output: numericSetting(request.settings, "output_cost") ?? 0,
      cacheRead: 0,
      cacheWrite: 0
    },
    contextWindow: numericSetting(request.settings, "context_window") ?? 128000,
    maxTokens: numericSetting(request.settings, "max_tokens") ?? 8192
  };
}

function numericSetting(settings: Record<string, unknown>, key: string): number | undefined {
  const value = settings[key];
  return typeof value === "number" && Number.isFinite(value) ? value : undefined;
}

async function promptWithAbort(agent: Agent, prompt: string, signal?: AbortSignal): Promise<void> {
  if (signal?.aborted) throw new Error("worldline cast stage aborted");
  const abort = () => {
    void agent.abort();
  };
  signal?.addEventListener("abort", abort, { once: true });
  try {
    await agent.prompt(prompt);
  } finally {
    signal?.removeEventListener("abort", abort);
  }
}

function finalAssistantMessage(messages: unknown[]): AssistantMessage | undefined {
  for (let index = messages.length - 1; index >= 0; index -= 1) {
    const message = messages[index] as AssistantMessage | undefined;
    if (message && message.role === "assistant") return message;
  }
  return undefined;
}

function assistantText(message: AssistantMessage | undefined): string {
  if (!message?.content) return "";
  return message.content
    .filter((part): part is { type: "text"; text: string } => part.type === "text")
    .map((part) => part.text)
    .join("");
}

function aggregateUsage(messages: unknown[]): PiWorldlineCastUsage | undefined {
  let promptTokens = 0;
  let completionTokens = 0;
  for (const message of messages) {
    const usage = (message as { usage?: { input?: number; output?: number } }).usage;
    if (!usage) continue;
    promptTokens += usage.input ?? 0;
    completionTokens += usage.output ?? 0;
  }
  if (!promptTokens && !completionTokens) return undefined;
  return { prompt_tokens: promptTokens, completion_tokens: completionTokens };
}
