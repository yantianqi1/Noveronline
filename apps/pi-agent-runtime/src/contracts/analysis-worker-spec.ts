import type { AnalysisRunInput } from "./analysis-run.js";

export const ANALYSIS_TASK_QUEUE = "analysis-streaming";
export const PI_ANALYSIS_WORKFLOW_NAME = "PiAnalysisRunWorkflow";
export const PI_ANALYSIS_ACTIVITY_NAME = "runPiAnalysisRunActivity";

export interface PiAnalysisWorkerSpec {
  taskQueue: string;
  workflows: string[];
  activities: string[];
}

export function piAnalysisWorkerSpec(): PiAnalysisWorkerSpec {
  return {
    taskQueue: ANALYSIS_TASK_QUEUE,
    workflows: [PI_ANALYSIS_WORKFLOW_NAME],
    activities: [PI_ANALYSIS_ACTIVITY_NAME]
  };
}

export function validateAnalysisWorkflowPayload(payload: unknown): AnalysisRunInput {
  const value = payload as Partial<AnalysisRunInput> & Record<string, unknown> | null;
  if (!value || typeof value !== "object") {
    throw new Error("analysis workflow payload is required");
  }
  const tenantId = requireString(value, "tenant_id");
  const projectId = requireString(value, "project_id");
  const runId = requireString(value, "run_id");
  const traceId = requireString(value, "trace_id");
  const requestedBy = optionalString(value.requested_by) ?? "";
  const modeRaw = optionalString(value.mode) ?? "full";
  if (modeRaw !== "full" && modeRaw !== "focused" && modeRaw !== "resume") {
    throw new Error("mode must be full, focused, or resume");
  }
  const instruction =
    optionalString(value.instruction)
    ?? "Analyze the uploaded novel into structured story knowledge.";
  const optionsRaw = (value.options && typeof value.options === "object"
    ? value.options
    : { module_key: "analysis_planner" }) as AnalysisRunInput["options"] & Record<string, unknown>;
  const moduleKey = optionalString(optionsRaw.module_key) ?? "analysis_planner";
  if (moduleKey !== "analysis_planner" && moduleKey !== "analysis_worker") {
    throw new Error("options.module_key must be analysis_planner or analysis_worker");
  }
  const hints = value.hints && typeof value.hints === "object" && !Array.isArray(value.hints)
    ? (value.hints as Record<string, unknown>)
    : {};
  return {
    tenant_id: tenantId,
    project_id: projectId,
    run_id: runId,
    trace_id: traceId,
    requested_by: requestedBy,
    mode: modeRaw,
    instruction,
    upload_id: optionalString(value.upload_id),
    source_file_id: optionalString(value.source_file_id),
    hints,
    options: {
      module_key: moduleKey,
      thinking_level: optionsRaw.thinking_level,
      tool_execution: optionsRaw.tool_execution,
      max_segments: typeof optionsRaw.max_segments === "number" ? optionsRaw.max_segments : undefined,
      llm_resolution: optionsRaw.llm_resolution
    }
  };
}

function requireString(value: Record<string, unknown>, key: string): string {
  const raw = value[key];
  if (typeof raw !== "string" || raw.trim() === "") {
    throw new Error(`${key} is required`);
  }
  return raw.trim();
}

function optionalString(value: unknown): string | undefined {
  return typeof value === "string" && value.trim() !== "" ? value.trim() : undefined;
}
