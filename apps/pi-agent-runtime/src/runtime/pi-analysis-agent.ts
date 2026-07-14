import { Agent, type AgentEvent, type AgentTool } from "@earendil-works/pi-agent-core";
import {
  createModels,
  createProvider,
  type AssistantMessage,
  type Model
} from "@earendil-works/pi-ai";
import { openAICompletionsApi } from "@earendil-works/pi-ai/api/openai-completions.lazy";
import { Object as ObjectSchema, Optional, String as StringSchema, Number as NumberSchema } from "typebox";

import type {
  AnalysisStageRequest,
  AnalysisStageResult,
  PiAnalysisUsage
} from "../activities/pi-analysis-activities.js";
import type { AnalysisToolName } from "../contracts/analysis-run.js";
import { assertAnalysisToolAllowed, AnalysisToolPermissionDenied } from "../tools/analysis-permissions.js";
import { analysisRuntimeContextFromInput } from "../contracts/analysis-run.js";

const emptyArgs = ObjectSchema({}, { additionalProperties: false });
const pathArgs = ObjectSchema({
  path: StringSchema({ minLength: 1 })
}, { additionalProperties: false });
const listSegmentsArgs = ObjectSchema({
  limit: Optional(NumberSchema({ minimum: 1, maximum: 200 }))
}, { additionalProperties: false });
const readSegmentArgs = ObjectSchema({
  segment_index: NumberSchema({ minimum: 0 })
}, { additionalProperties: false });
const writeFileArgs = ObjectSchema({
  path: StringSchema({ minLength: 1 }),
  kind: Optional(StringSchema()),
  content: StringSchema(),
  mime_type: Optional(StringSchema())
}, { additionalProperties: false });
const updateTodoArgs = ObjectSchema({
  todo: Optional(ObjectSchema({}, { additionalProperties: true })),
  items: Optional(ObjectSchema({}, { additionalProperties: true }))
}, { additionalProperties: true });
const saveCandidatesArgs = ObjectSchema({
  candidates: Optional(ObjectSchema({}, { additionalProperties: true }))
}, { additionalProperties: true });

export function createPiAnalysisExecution() {
  return {
    runAnalysisStage: async (request: AnalysisStageRequest): Promise<AnalysisStageResult> => {
      const runtime = createRuntime(request);
      const useTools = request.tool_names.length > 0 && request.settings.force_no_tools !== true;
      let permissionError: AnalysisToolPermissionDenied | undefined;
      const tools = useTools
        ? request.tool_names.map((name) => analysisTool(name, request, (error) => {
          permissionError = error;
        }))
        : [];
      const agent = new Agent({
        initialState: {
          systemPrompt: systemPrompt(request),
          model: runtime.model,
          thinkingLevel: request.thinking_level ?? "off",
          tools
        },
        streamFn: runtime.streamFn,
        getApiKey: (provider) => (provider === runtime.providerId ? request.apiKey : undefined),
        toolExecution: request.tool_execution ?? "sequential",
        beforeToolCall: async ({ toolCall }) => {
          try {
            const context = analysisRuntimeContextFromInput({
              tenant_id: request.tenant_id,
              project_id: request.project_id,
              run_id: request.run_id,
              trace_id: request.run_id,
              requested_by: "",
              mode: request.mode,
              instruction: request.instruction,
              hints: request.hints,
              options: { module_key: request.module_key }
            });
            context.permissions.tools = request.tool_names;
            assertAnalysisToolAllowed(toolCall.name, toolCall.arguments as Record<string, unknown> | undefined, context);
            return undefined;
          } catch (error) {
            if (!(error instanceof AnalysisToolPermissionDenied)) throw error;
            permissionError = error;
            return { block: true, reason: error.message };
          }
        },
        sessionId: `${request.run_id}:${request.module_key}`
      });
      agent.subscribe(async (event) => {
        await request.onAgentEvent?.(event);
        const delta = textDelta(event);
        if (delta) await request.onToken?.(delta);
      });
      await promptWithAbort(agent, userPrompt(request), request.abort_signal);
      if (permissionError) throw permissionError;
      const message = finalAssistantMessage(agent.state.messages);
      const content = assistantText(message).trim();
      if (!content) {
        throw Object.assign(new Error(`Pi analysis ${request.module_key} returned empty output`), {
          code: "ANALYSIS_STAGE_EMPTY"
        });
      }
      return {
        summary: content.slice(0, 4000),
        usage: aggregateUsage(agent.state.messages)
      };
    }
  };
}

function analysisTool(
  name: AnalysisToolName,
  request: AnalysisStageRequest,
  onPermissionError: (error: AnalysisToolPermissionDenied) => void
): AgentTool<any> {
  return {
    name,
    label: name,
    description: toolDescription(name),
    parameters: toolParameters(name),
    executionMode: name === "write_workspace_file" || name === "update_todo" || name === "save_analysis_candidates"
      ? "sequential"
      : "parallel",
    execute: async (toolCallId, params, signal) => {
      if (signal?.aborted) throw new Error("analysis tool execution aborted");
      try {
        const args = (params && typeof params === "object" ? params : {}) as Record<string, unknown>;
        const details = await request.executeTool(name, toolCallId, args);
        return {
          content: [{ type: "text", text: JSON.stringify(details) }],
          details
        };
      } catch (error) {
        if (error instanceof AnalysisToolPermissionDenied) {
          onPermissionError(error);
        }
        throw error;
      }
    }
  };
}

function toolParameters(name: AnalysisToolName) {
  switch (name) {
    case "list_workspace_files":
      return emptyArgs;
    case "read_workspace_file":
      return pathArgs;
    case "list_source_segments":
      return listSegmentsArgs;
    case "read_source_segment":
      return readSegmentArgs;
    case "write_workspace_file":
      return writeFileArgs;
    case "update_todo":
      return updateTodoArgs;
    case "save_analysis_candidates":
      return saveCandidatesArgs;
    default:
      return emptyArgs;
  }
}

function toolDescription(name: AnalysisToolName): string {
  const descriptions: Record<AnalysisToolName, string> = {
    list_workspace_files: "List files already written in this analysis workspace folder.",
    read_workspace_file: "Read one workspace file by path (for example 00-plan/task-pack.md).",
    list_source_segments: "List available source novel segments with titles and previews.",
    read_source_segment: "Read one source segment body by segment_index.",
    write_workspace_file: "Write or overwrite a workspace file under 00-plan/, 20-notes/, 30-candidates/, or 90-review/.",
    update_todo: "Update 00-plan/todo.json with current task statuses.",
    save_analysis_candidates: "Persist structured candidate rows extracted from the novel."
  };
  return descriptions[name];
}

function systemPrompt(request: AnalysisStageRequest): string {
  if (request.module_key === "analysis_planner") {
    return [
      "You are the MiroFish novel analysis planner.",
      "Inspect the uploaded source via tools, then write a concrete task pack and todo list into the workspace.",
      "Required writes:",
      "- 00-plan/task-pack.md with ordered analysis tasks",
      "- 00-plan/todo.json with items status pending/in_progress/done",
      "Do not invent source text. Use tools. Keep outputs novel-domain specific.",
      "When finished, reply with a short summary of the plan."
    ].join("\n");
  }
  return [
    "You are the MiroFish novel analysis worker.",
    "Follow 00-plan/task-pack.md and process source segments with tools.",
    "Required writes:",
    "- 20-notes/sequential/<index>.md notes for each processed segment",
    "- 30-candidates/characters.json as {\"items\":[...]}",
    "- 30-candidates/relationships.json as {\"items\":[...]}",
    "- 30-candidates/world_rules.json as {\"items\":[...]}",
    "- 90-review/summary.md review summary",
    "Update 00-plan/todo.json as you progress.",
    "Candidates are non-canon proposals, not adopted assets.",
    "Do not invent evidence outside the source segments you read.",
    "When finished, reply with a short summary of what you extracted."
  ].join("\n");
}

function userPrompt(request: AnalysisStageRequest): string {
  return JSON.stringify({
    task: request.module_key === "analysis_planner" ? "plan_analysis" : "execute_analysis",
    mode: request.mode,
    instruction: request.instruction,
    hints: request.hints,
    workspace_roots: ["00-plan/", "10-source/", "20-notes/", "30-candidates/", "90-review/"]
  });
}

function createRuntime(request: AnalysisStageRequest) {
  const parentProviderCallID = request.provider_call_id?.trim();
  if (!parentProviderCallID) {
    throw new Error("LLM_PROVIDER_CALL_ID_INVALID: Pi analysis provider call identity is required");
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
  if (!resolved) throw new Error("Pi analysis resolved model is unavailable");
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

function openAICompatibleModel(request: AnalysisStageRequest, providerId: string): Model<"openai-completions"> {
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
    maxTokens: numericSetting(request.settings, "max_tokens") ?? 8000,
    headers: {
      "Idempotency-Key": request.provider_call_id!.trim(),
      "X-MiroFish-Tenant-Id": request.tenant_id,
      "X-MiroFish-Project-Id": request.project_id,
      "X-MiroFish-Run-Id": request.run_id,
      "X-MiroFish-Module-Key": request.module_key
    }
  };
}

function finalAssistantMessage(messages: unknown[]): AssistantMessage {
  for (let index = messages.length - 1; index >= 0; index -= 1) {
    const message = messages[index] as AssistantMessage;
    if (message?.role === "assistant") {
      if (message.stopReason === "error" || message.stopReason === "aborted") {
        throw Object.assign(new Error("Pi analysis provider call failed"), {
          code: "LLM_PROVIDER_ERROR"
        });
      }
      return message;
    }
  }
  throw Object.assign(new Error("Pi analysis provider returned no assistant message"), {
    code: "LLM_PROVIDER_ERROR"
  });
}

function assistantText(message: AssistantMessage): string {
  return message.content.filter((block) => block.type === "text").map((block) => block.text).join("");
}

function messageUsage(message: AssistantMessage): PiAnalysisUsage {
  return {
    prompt_tokens: message.usage.input,
    completion_tokens: message.usage.output,
    cost_estimate: message.usage.cost.total
  };
}

function aggregateUsage(messages: unknown[]): PiAnalysisUsage {
  const assistantMessages = messages.filter((message): message is AssistantMessage =>
    Boolean(message && typeof message === "object" && (message as AssistantMessage).role === "assistant")
  );
  return assistantMessages.reduce((total, message) => {
    const usage = messageUsage(message);
    return {
      prompt_tokens: (total.prompt_tokens ?? 0) + (usage.prompt_tokens ?? 0),
      completion_tokens: (total.completion_tokens ?? 0) + (usage.completion_tokens ?? 0),
      cost_estimate: (total.cost_estimate ?? 0) + (usage.cost_estimate ?? 0)
    };
  }, { prompt_tokens: 0, completion_tokens: 0, cost_estimate: 0 } satisfies PiAnalysisUsage);
}

async function promptWithAbort(agent: Agent, prompt: string, signal?: AbortSignal): Promise<void> {
  if (!signal) {
    await agent.prompt(prompt);
    return;
  }
  if (signal.aborted) {
    throw Object.assign(new Error("WORKFLOW_CANCELLED: Pi analysis activity was cancelled"), {
      code: "WORKFLOW_CANCELLED"
    });
  }
  const abort = () => {
    void agent.abort();
  };
  signal.addEventListener("abort", abort, { once: true });
  try {
    await agent.prompt(prompt);
    if (signal.aborted) {
      throw Object.assign(new Error("WORKFLOW_CANCELLED: Pi analysis activity was cancelled"), {
        code: "WORKFLOW_CANCELLED"
      });
    }
  } finally {
    signal.removeEventListener("abort", abort);
  }
}

function textDelta(event: AgentEvent): string {
  if (event.type !== "message_update" || event.assistantMessageEvent.type !== "text_delta") return "";
  return event.assistantMessageEvent.delta;
}

function numericSetting(settings: Record<string, unknown>, key: string): number | undefined {
  const value = settings[key];
  return typeof value === "number" && Number.isFinite(value) ? value : undefined;
}
