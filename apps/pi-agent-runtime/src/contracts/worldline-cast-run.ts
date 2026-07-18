export const WORLDLINE_CAST_MODULE_KEY = "worldline_cast_planner" as const;

export type WorldlineCastModuleKey = typeof WORLDLINE_CAST_MODULE_KEY;

export type WorldlineCastToolName =
  | "query_project_context"
  | "query_character_profile"
  | "query_assets"
  | "query_graph_neighbors"
  | "commit_worldline_cast";

export const WORLDLINE_CAST_TOOLS: WorldlineCastToolName[] = [
  "query_project_context",
  "query_character_profile",
  "query_assets",
  "query_graph_neighbors",
  "commit_worldline_cast"
];

export interface WorldlineCastRef {
  source_kind: "asset" | "entity" | "saved_path" | "worldline_event";
  source_id: string;
}

export interface WorldlineCastCommit {
  agent_refs: WorldlineCastRef[];
  source_refs: WorldlineCastRef[];
  rationale: string;
}

export interface WorldlineGoalStartInput {
  tenant_id: string;
  project_id: string;
  run_id: string;
  trace_id: string;
  requested_by: string;
  goal: string;
  anchor_path_id?: string;
  options: {
    module_key: WorldlineCastModuleKey;
    thinking_level?: "off" | "minimal" | "low" | "medium" | "high" | "xhigh";
    tool_execution?: "sequential" | "parallel";
    llm_resolution?: Record<string, unknown>;
  };
}

export interface WorldlineCastRuntimeContext {
  tenant_id: string;
  project_id: string;
  run_id: string;
  permissions: {
    tools: WorldlineCastToolName[];
  };
}

export function worldlineCastRuntimeContextFromInput(input: {
  tenant_id: string;
  project_id: string;
  run_id: string;
}): WorldlineCastRuntimeContext {
  return {
    tenant_id: input.tenant_id,
    project_id: input.project_id,
    run_id: input.run_id,
    permissions: {
      tools: [...WORLDLINE_CAST_TOOLS]
    }
  };
}
