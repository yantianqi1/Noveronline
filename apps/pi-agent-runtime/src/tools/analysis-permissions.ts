import type { AnalysisRuntimeContext, AnalysisToolName } from "../contracts/analysis-run.js";
import { isAllowedAnalysisWorkspacePath } from "../contracts/analysis-run.js";

export class AnalysisToolPermissionDenied extends Error {
  readonly code = "TOOL_PERMISSION_DENIED";

  constructor(message: string) {
    super(message);
    this.name = "AnalysisToolPermissionDenied";
  }
}

export function assertAnalysisToolAllowed(
  toolName: string,
  args: Record<string, unknown> | undefined,
  context: AnalysisRuntimeContext
): void {
  const allowed = new Set(context.permissions.tools);
  if (!allowed.has(toolName as AnalysisToolName)) {
    throw new AnalysisToolPermissionDenied(`tool ${toolName} is not allowed for this analysis run`);
  }
  if (args) {
    for (const key of ["tenant_id", "project_id", "run_id"] as const) {
      const value = args[key];
      if (typeof value === "string" && value.trim() !== "" && value.trim() !== context[key]) {
        throw new AnalysisToolPermissionDenied(`tool args may not override ${key}`);
      }
    }
  }
  if (toolName === "write_workspace_file" || toolName === "update_todo") {
    if (!context.permissions.can_write_workspace) {
      throw new AnalysisToolPermissionDenied("workspace writes are not permitted");
    }
  }
  if (toolName === "save_analysis_candidates" && !context.permissions.can_write_candidates) {
    throw new AnalysisToolPermissionDenied("candidate writes are not permitted");
  }
  if (toolName === "write_workspace_file" || toolName === "read_workspace_file") {
    const path = typeof args?.path === "string" ? args.path : "";
    if (path && !isAllowedAnalysisWorkspacePath(path)) {
      throw new AnalysisToolPermissionDenied("workspace path is outside the analysis run folder");
    }
  }
}
