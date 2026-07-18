import type { WorldlineCastRuntimeContext, WorldlineCastToolName } from "../contracts/worldline-cast-run.js";

export class WorldlineCastToolPermissionDenied extends Error {
  readonly code = "TOOL_PERMISSION_DENIED";

  constructor(message: string) {
    super(message);
    this.name = "WorldlineCastToolPermissionDenied";
  }
}

export function assertWorldlineCastToolAllowed(
  toolName: string,
  args: Record<string, unknown> | undefined,
  context: WorldlineCastRuntimeContext
): void {
  const allowed = new Set(context.permissions.tools);
  if (!allowed.has(toolName as WorldlineCastToolName)) {
    throw new WorldlineCastToolPermissionDenied(`tool ${toolName} is not allowed for this worldline cast run`);
  }
  if (args) {
    for (const key of ["tenant_id", "project_id", "run_id"] as const) {
      const value = args[key];
      if (typeof value === "string" && value.trim() !== "" && value.trim() !== context[key]) {
        throw new WorldlineCastToolPermissionDenied(`tool args may not override ${key}`);
      }
    }
  }
  if (toolName === "commit_worldline_cast") {
    const agentRefs = Array.isArray(args?.agent_refs) ? args.agent_refs : [];
    if (agentRefs.length < 1) {
      throw new WorldlineCastToolPermissionDenied("commit_worldline_cast requires at least one agent_ref");
    }
    if (agentRefs.length > 8) {
      throw new WorldlineCastToolPermissionDenied("commit_worldline_cast allows at most 8 agent_refs");
    }
  }
}
