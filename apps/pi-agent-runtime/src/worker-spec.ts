import type { WriterRunInput } from "./contracts/writer-run.js";

export const WRITER_TASK_QUEUE = "writer-streaming";
export const PI_WRITER_WORKFLOW_NAME = "PiWriterRunWorkflow";
export const PI_WRITER_ACTIVITY_NAME = "runPiWriterRunActivity";

export interface PiWriterWorkerSpec {
  taskQueue: string;
  workflows: string[];
  activities: string[];
}

export function piWriterWorkerSpec(): PiWriterWorkerSpec {
  return {
    taskQueue: WRITER_TASK_QUEUE,
    workflows: [PI_WRITER_WORKFLOW_NAME],
    activities: [PI_WRITER_ACTIVITY_NAME]
  };
}

export function validateWriterWorkflowPayload(payload: unknown): WriterRunInput {
  const value = payload as Partial<WriterRunInput> | null;
  if (!value || typeof value !== "object") {
    throw new Error("writer workflow payload is required");
  }
  const tenantId = requireString(value, "tenant_id");
  const projectId = requireString(value, "project_id");
  const runId = requireString(value, "run_id");
  const traceId = requireString(value, "trace_id");
  const requestedBy = requireString(value, "requested_by");
  const mode = requireString(value, "mode") as WriterRunInput["mode"];
  if (mode !== "draft" && mode !== "continue" && mode !== "outline" && mode !== "revise") {
    throw new Error("mode must be draft, continue, outline, or revise");
  }
  const instruction = requireString(value, "instruction");
  if (!value.options || typeof value.options !== "object") {
    throw new Error("options is required");
  }
  const moduleKey = value.options.module_key;
  if (moduleKey !== "writer_composer" && moduleKey !== "writer_orchestrator") {
    throw new Error("options.module_key must be writer_composer or writer_orchestrator");
  }
  const rawOptions = value.options as WriterRunInput["options"] & Record<string, unknown>;
  const revise = parseReviseOptions(rawOptions.revise);
  if (mode === "revise" && !revise) {
    throw new Error("options.revise is required when mode is revise");
  }
  return {
    tenant_id: tenantId,
    project_id: projectId,
    run_id: runId,
    trace_id: traceId,
    requested_by: requestedBy,
    mode,
    chapter_id:
      optionalString(value.chapter_id) ??
      optionalString(rawOptions.chapter_id) ??
      optionalString(rawOptions.target_chapter_id),
    scene_id:
      optionalString(value.scene_id) ??
      optionalString(rawOptions.scene_id) ??
      optionalString(rawOptions.target_scene_id),
    instruction,
    selected_asset_ids: stringArray(value.selected_asset_ids ?? rawOptions.selected_asset_ids ?? rawOptions.asset_ids),
    graph_node_ids: stringArray(value.graph_node_ids ?? rawOptions.graph_node_ids),
    worldline_path_ids: stringArray(value.worldline_path_ids ?? rawOptions.worldline_path_ids),
    worldline_session_ids: stringArray(value.worldline_session_ids ?? rawOptions.worldline_session_ids),
    options: {
      module_key: moduleKey,
      thinking_level: value.options.thinking_level,
      tool_execution: value.options.tool_execution,
      target_words: value.options.target_words,
      review_after_write: value.options.review_after_write,
      llm_resolution: value.options.llm_resolution,
      ...(revise ? { revise } : {})
    }
  };
}

function parseReviseOptions(value: unknown): WriterRunInput["options"]["revise"] | undefined {
  if (!value || typeof value !== "object") return undefined;
  const record = value as Record<string, unknown>;
  const blockId = optionalString(record.block_id);
  const selectionText = optionalString(record.selection_text);
  if (!blockId || !selectionText) return undefined;
  const action = optionalString(record.action);
  const allowed = new Set(["rewrite", "expand", "condense", "polish", "correct", "custom"]);
  return {
    block_id: blockId,
    selection_text: selectionText,
    selection_start: typeof record.selection_start === "number" ? record.selection_start : undefined,
    selection_end: typeof record.selection_end === "number" ? record.selection_end : undefined,
    expected_version: typeof record.expected_version === "number" ? record.expected_version : undefined,
    action: action && allowed.has(action) ? (action as NonNullable<WriterRunInput["options"]["revise"]>["action"]) : undefined
  };
}

function optionalString(value: unknown): string | undefined {
  return typeof value === "string" && value.trim() !== "" ? value.trim() : undefined;
}

function stringArray(value: unknown): string[] {
  if (value === undefined) return [];
  if (!Array.isArray(value) || value.some((item) => typeof item !== "string" || item.trim() === "")) {
    throw new Error("writer reference ids must be string arrays");
  }
  return value.map((item) => item.trim());
}

function requireString<T extends Record<string, unknown>>(value: T, key: keyof T): string {
  const field = value[key];
  if (typeof field !== "string" || field.trim() === "") {
    throw new Error(`${String(key)} is required`);
  }
  return field;
}
