import type { ToolExecutionMode } from "@earendil-works/pi-agent-core";

export type AnalysisMode = "full" | "focused" | "resume";
export type AnalysisModuleKey = "analysis_planner" | "analysis_worker";

export type AnalysisToolName =
  | "list_workspace_files"
  | "read_workspace_file"
  | "list_source_segments"
  | "read_source_segment"
  | "write_workspace_file"
  | "update_todo"
  | "save_analysis_candidates";

export interface AnalysisRunInput {
  tenant_id: string;
  project_id: string;
  run_id: string;
  trace_id: string;
  requested_by: string;
  mode: AnalysisMode;
  instruction: string;
  upload_id?: string;
  source_file_id?: string;
  hints: Record<string, unknown>;
  options: {
    module_key: AnalysisModuleKey;
    thinking_level?: "off" | "minimal" | "low" | "medium" | "high" | "xhigh";
    tool_execution?: ToolExecutionMode;
    max_segments?: number;
    llm_resolution?: {
      module_key: string;
      channel_id: string;
      model_id: string;
      provider: string;
      base_url: string;
      credential_ref: string;
      supports_tools: boolean;
      supports_json: boolean;
      settings: Record<string, unknown>;
    };
  };
}

export interface AnalysisRuntimeContext {
  tenant_id: string;
  project_id: string;
  run_id: string;
  trace_id: string;
  requested_by: string;
  permissions: {
    tools: AnalysisToolName[];
    can_write_workspace: boolean;
    can_write_candidates: boolean;
  };
}

export function analysisRuntimeContextFromInput(input: AnalysisRunInput): AnalysisRuntimeContext {
  return {
    tenant_id: input.tenant_id,
    project_id: input.project_id,
    run_id: input.run_id,
    trace_id: input.trace_id,
    requested_by: input.requested_by,
    permissions: {
      tools: [
        "list_workspace_files",
        "read_workspace_file",
        "list_source_segments",
        "read_source_segment",
        "write_workspace_file",
        "update_todo",
        "save_analysis_candidates"
      ],
      can_write_workspace: true,
      can_write_candidates: true
    }
  };
}

export const ANALYSIS_WORKSPACE_PATH_PREFIXES = [
  "00-plan/",
  "10-source/",
  "20-notes/",
  "30-candidates/",
  "90-review/"
] as const;

export function isAllowedAnalysisWorkspacePath(path: string): boolean {
  const normalized = path.trim().replace(/^\/+/, "").replace(/\\/g, "/");
  if (!normalized || normalized.includes("..") || normalized.length > 512) {
    return false;
  }
  return ANALYSIS_WORKSPACE_PATH_PREFIXES.some((prefix) => normalized.startsWith(prefix));
}
