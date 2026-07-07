import { Agent, type AgentOptions } from "@earendil-works/pi-agent-core";

import type { RuntimeContext, WriterRunInput } from "../contracts/writer-run.js";
import { mapPiEvent, type WriterWorkflowEvent } from "../contracts/writer-events.js";

export interface LlmFacilityResolution {
  provider: string;
  model: unknown;
  apiKey: string;
}

export interface WriterAgentDeps {
  resolveLlm: (input: WriterRunInput) => Promise<LlmFacilityResolution>;
  emitEvent: (event: WriterWorkflowEvent) => Promise<void>;
  beforeTool: (toolName: string, args: unknown, context: RuntimeContext) => Promise<void>;
  afterTool: (toolName: string, result: unknown, context: RuntimeContext) => Promise<void>;
}

export async function createPiWriterAgent(
  input: WriterRunInput,
  context: RuntimeContext,
  deps: WriterAgentDeps
): Promise<Agent> {
  const llm = await deps.resolveLlm(input);
  const options: AgentOptions = {
    initialState: {
      model: llm.model as any,
      messages: [
        {
          role: "user",
          content: [{ type: "text", text: input.instruction }]
        }
      ] as any
    },
    getApiKey(provider: string) {
      if (provider !== llm.provider) return undefined;
      return llm.apiKey;
    },
    beforeToolCall: async (toolContext) => {
      const raw = toolContext as unknown as { toolCall?: { toolName?: string }; args?: unknown };
      await deps.beforeTool(raw.toolCall?.toolName ?? "", raw.args, context);
      return undefined;
    },
    afterToolCall: async (toolContext) => {
      const raw = toolContext as unknown as {
        toolCall?: { toolName?: string };
        result?: unknown;
      };
      await deps.afterTool(raw.toolCall?.toolName ?? "", raw.result, context);
      return undefined;
    },
    sessionId: context.run_id,
    toolExecution: input.options.tool_execution ?? "parallel"
  };
  const agent = new Agent(options);
  agent.subscribe(async (event) => {
    const mapped = mapPiEvent(event, context);
    if (mapped) await deps.emitEvent(mapped);
  });
  return agent;
}
