import type { WorldlineGoalStartInput } from "./worldline-cast-run.js";
import { WORLDLINE_CAST_MODULE_KEY } from "./worldline-cast-run.js";

export const WORLDLINE_CAST_TASK_QUEUE = "worldline-cast-streaming";
export const PI_WORLDLINE_GOAL_START_WORKFLOW_NAME = "PiWorldlineGoalStartWorkflow";
export const PI_WORLDLINE_GOAL_START_ACTIVITY_NAME = "runPiWorldlineGoalStartActivity";

export interface PiWorldlineCastWorkerSpec {
  taskQueue: string;
  workflows: string[];
  activities: string[];
}

export function piWorldlineCastWorkerSpec(): PiWorldlineCastWorkerSpec {
  return {
    taskQueue: WORLDLINE_CAST_TASK_QUEUE,
    workflows: [PI_WORLDLINE_GOAL_START_WORKFLOW_NAME],
    activities: [PI_WORLDLINE_GOAL_START_ACTIVITY_NAME]
  };
}

export function validateWorldlineGoalStartPayload(payload: unknown): WorldlineGoalStartInput {
  const value = payload as Partial<WorldlineGoalStartInput> & Record<string, unknown> | null;
  if (!value || typeof value !== "object") {
    throw new Error("worldline goal-start workflow payload is required");
  }
  const tenantId = requireString(value, "tenant_id");
  const projectId = requireString(value, "project_id");
  const runId = requireString(value, "run_id");
  const traceId = requireString(value, "trace_id");
  const goal = requireString(value, "goal");
  const requestedBy = optionalString(value.requested_by) ?? "";
  const optionsRaw = (value.options && typeof value.options === "object"
    ? value.options
    : { module_key: WORLDLINE_CAST_MODULE_KEY }) as WorldlineGoalStartInput["options"] & Record<string, unknown>;
  const moduleKey = optionalString(optionsRaw.module_key) ?? WORLDLINE_CAST_MODULE_KEY;
  if (moduleKey !== WORLDLINE_CAST_MODULE_KEY) {
    throw new Error("options.module_key must be worldline_cast_planner");
  }
  return {
    tenant_id: tenantId,
    project_id: projectId,
    run_id: runId,
    trace_id: traceId,
    requested_by: requestedBy,
    goal,
    anchor_path_id: optionalString(value.anchor_path_id),
    options: {
      module_key: moduleKey,
      thinking_level: optionsRaw.thinking_level as WorldlineGoalStartInput["options"]["thinking_level"],
      tool_execution: optionsRaw.tool_execution as WorldlineGoalStartInput["options"]["tool_execution"],
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
