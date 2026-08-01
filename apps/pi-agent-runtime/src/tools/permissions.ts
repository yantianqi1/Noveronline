import type { RuntimeContext } from "../contracts/writer-run.js";

export class ToolPermissionDenied extends Error {
  code = "TOOL_PERMISSION_DENIED";
}

export function assertToolAllowed(
  toolName: string,
  args: unknown,
  context: RuntimeContext
): void {
  if (!context.permissions.tools.includes(toolName)) {
    throw new ToolPermissionDenied(`tool is not allowed for this run: ${toolName}`);
  }
  const payload = args as Partial<{
    tenant_id: string;
    project_id: string;
    run_id: string;
  }> | null;
  if (!payload) return;
  if (payload.tenant_id && payload.tenant_id !== context.tenant_id) {
    throw new ToolPermissionDenied("tool tenant_id does not match runtime context");
  }
  if (payload.project_id && payload.project_id !== context.project_id) {
    throw new ToolPermissionDenied("tool project_id does not match runtime context");
  }
  if (payload.run_id && payload.run_id !== context.run_id) {
    throw new ToolPermissionDenied("tool run_id does not match runtime context");
  }
}
