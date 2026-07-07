import type { AgentEvent } from "@earendil-works/pi-agent-core";

import type { RuntimeContext } from "./writer-run.js";

export type WriterEventType =
  | "writer.run.started"
  | "writer.token"
  | "writer.tool.started"
  | "writer.tool.completed"
  | "writer.draft.saved"
  | "writer.run.failed"
  | "writer.run.completed"
  | "writer.run.cancelled";

export interface WriterWorkflowEvent {
  type: WriterEventType;
  tenant_id: string;
  project_id: string;
  run_id: string;
  payload: Record<string, unknown>;
}

export function mapPiEvent(event: AgentEvent, context: RuntimeContext): WriterWorkflowEvent | null {
  const raw = event as AgentEvent & Record<string, any>;
  const base = {
    tenant_id: context.tenant_id,
    project_id: context.project_id,
    run_id: context.run_id
  };
  switch (String(raw.type)) {
    case "agent_start":
      return { ...base, type: "writer.run.started", payload: {} };
    case "message_update":
      return {
        ...base,
        type: "writer.token",
        payload: { token: raw.textDelta ?? raw.delta ?? raw.text ?? "" }
      };
    case "tool_execution_start":
      return {
        ...base,
        type: "writer.tool.started",
        payload: {
          tool_name: raw.toolCall?.toolName ?? raw.toolName ?? "",
          args: raw.args ?? {}
        }
      };
    case "tool_execution_end":
      return {
        ...base,
        type: "writer.tool.completed",
        payload: {
          tool_name: raw.toolCall?.toolName ?? raw.toolName ?? "",
          result: raw.result?.details ?? raw.result?.content ?? raw.result,
          is_error: Boolean(raw.isError)
        }
      };
    case "agent_end":
      return { ...base, type: "writer.run.completed", payload: {} };
    case "error":
      return {
        ...base,
        type: "writer.run.failed",
        payload: { message: raw.errorMessage ?? raw.message ?? "writer run failed" }
      };
    default:
      return null;
  }
}
