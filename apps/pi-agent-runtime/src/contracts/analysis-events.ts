import type { AgentEvent } from "@earendil-works/pi-agent-core";

import type { AnalysisRuntimeContext } from "./analysis-run.js";

export type AnalysisEventType =
  | "analysis.run.started"
  | "analysis.token"
  | "analysis.tool.started"
  | "analysis.tool.completed"
  | "analysis.file.written"
  | "analysis.candidates.saved"
  | "analysis.run.failed"
  | "analysis.run.completed"
  | "analysis.run.cancelled";

export interface AnalysisWorkflowEvent {
  type: AnalysisEventType;
  tenant_id: string;
  project_id: string;
  run_id: string;
  payload: Record<string, unknown>;
}

export function mapPiAnalysisEvent(
  event: AgentEvent,
  context: AnalysisRuntimeContext
): AnalysisWorkflowEvent | null {
  const raw = event as AgentEvent & Record<string, any>;
  const base = {
    tenant_id: context.tenant_id,
    project_id: context.project_id,
    run_id: context.run_id
  };
  switch (String(raw.type)) {
    case "agent_start":
      return { ...base, type: "analysis.run.started", payload: {} };
    case "message_update":
      return {
        ...base,
        type: "analysis.token",
        payload: { token: raw.textDelta ?? raw.delta ?? raw.text ?? "" }
      };
    case "tool_execution_start":
      return {
        ...base,
        type: "analysis.tool.started",
        payload: {
          tool_name: raw.toolCall?.toolName ?? raw.toolName ?? "",
          args: publicToolArgs(raw.args ?? {})
        }
      };
    case "tool_execution_end":
      return {
        ...base,
        type: "analysis.tool.completed",
        payload: {
          tool_name: raw.toolCall?.toolName ?? raw.toolName ?? "",
          result: publicToolResult(raw.result?.details ?? raw.result?.content ?? raw.result),
          is_error: Boolean(raw.isError)
        }
      };
    case "agent_end":
      return { ...base, type: "analysis.run.completed", payload: {} };
    case "error":
      return {
        ...base,
        type: "analysis.run.failed",
        payload: { message: raw.errorMessage ?? raw.message ?? "analysis run failed" }
      };
    default:
      return null;
  }
}

function publicToolArgs(value: unknown): Record<string, unknown> {
  if (!value || typeof value !== "object" || Array.isArray(value)) {
    return {};
  }
  const record = value as Record<string, unknown>;
  const out: Record<string, unknown> = {};
  for (const [key, item] of Object.entries(record)) {
    const lower = key.toLowerCase();
    if (
      lower.includes("content")
      || lower.includes("body")
      || lower.includes("prompt")
      || lower.includes("api_key")
      || lower.includes("credential")
      || lower.includes("object_key")
    ) {
      continue;
    }
    if (typeof item === "string" && item.length > 200) {
      out[key] = `${item.slice(0, 200)}…`;
      continue;
    }
    out[key] = item;
  }
  return out;
}

function publicToolResult(value: unknown): Record<string, unknown> {
  if (!value || typeof value !== "object" || Array.isArray(value)) {
    return { ok: true };
  }
  const record = value as Record<string, unknown>;
  const out: Record<string, unknown> = {};
  for (const key of ["path", "kind", "size_bytes", "content_sha256", "file_count", "segment_count", "candidate_count", "status"]) {
    if (key in record) {
      out[key] = record[key];
    }
  }
  return Object.keys(out).length > 0 ? out : { ok: true };
}
