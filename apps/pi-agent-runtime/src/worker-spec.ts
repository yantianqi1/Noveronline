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
  const instruction = requireString(value, "instruction");
  if (!value.options || typeof value.options !== "object") {
    throw new Error("options is required");
  }
  const moduleKey = value.options.module_key;
  if (moduleKey !== "writer_composer" && moduleKey !== "writer_orchestrator") {
    throw new Error("options.module_key must be writer_composer or writer_orchestrator");
  }
  return {
    tenant_id: tenantId,
    project_id: projectId,
    run_id: runId,
    trace_id: traceId,
    requested_by: requestedBy,
    mode,
    chapter_id: value.chapter_id,
    scene_id: value.scene_id,
    instruction,
    selected_asset_ids: value.selected_asset_ids ?? [],
    worldline_path_ids: value.worldline_path_ids ?? [],
    options: {
      module_key: moduleKey,
      thinking_level: value.options.thinking_level,
      tool_execution: value.options.tool_execution,
      target_words: value.options.target_words,
      review_after_write: value.options.review_after_write,
      llm_resolution: value.options.llm_resolution
    }
  };
}

function requireString<T extends Record<string, unknown>>(value: T, key: keyof T): string {
  const field = value[key];
  if (typeof field !== "string" || field.trim() === "") {
    throw new Error(`${String(key)} is required`);
  }
  return field;
}
