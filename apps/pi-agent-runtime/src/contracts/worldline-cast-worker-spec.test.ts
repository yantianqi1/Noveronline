import { describe, expect, it } from "vitest";

import {
  assertWorldlineCastToolAllowed,
  WorldlineCastToolPermissionDenied
} from "../tools/worldline-cast-permissions.js";
import { WORLDLINE_CAST_TOOLS, worldlineCastRuntimeContextFromInput } from "./worldline-cast-run.js";
import {
  piWorldlineCastWorkerSpec,
  validateWorldlineGoalStartPayload,
  WORLDLINE_CAST_TASK_QUEUE
} from "./worldline-cast-worker-spec.js";

describe("worldline cast worker contracts", () => {
  it("exposes cast task queue and workflow names", () => {
    const spec = piWorldlineCastWorkerSpec();
    expect(spec.taskQueue).toBe(WORLDLINE_CAST_TASK_QUEUE);
    expect(spec.workflows).toEqual(["PiWorldlineGoalStartWorkflow"]);
    expect(spec.activities).toEqual(["runPiWorldlineGoalStartActivity"]);
  });

  it("validates goal-start payloads", () => {
    const input = validateWorldlineGoalStartPayload({
      tenant_id: "00000000-0000-4000-8000-000000000001",
      project_id: "00000000-0000-4000-8000-000000000002",
      run_id: "00000000-0000-4000-8000-000000000003",
      trace_id: "trace_1",
      goal: "探索对峙",
      options: { module_key: "worldline_cast_planner" }
    });
    expect(input.goal).toBe("探索对峙");
    expect(input.options.module_key).toBe("worldline_cast_planner");
  });

  it("rejects empty agent refs on commit", () => {
    const context = worldlineCastRuntimeContextFromInput({
      tenant_id: "t",
      project_id: "p",
      run_id: "r"
    });
    expect(context.permissions.tools).toEqual(WORLDLINE_CAST_TOOLS);
    expect(() => assertWorldlineCastToolAllowed("commit_worldline_cast", {
      agent_refs: [],
      rationale: "x"
    }, context)).toThrow(WorldlineCastToolPermissionDenied);
  });

  it("allows a valid commit shape", () => {
    const context = worldlineCastRuntimeContextFromInput({
      tenant_id: "t",
      project_id: "p",
      run_id: "r"
    });
    expect(() => assertWorldlineCastToolAllowed("commit_worldline_cast", {
      agent_refs: [{ source_kind: "entity", source_id: "00000000-0000-4000-8000-000000000011" }],
      rationale: "主角必须到场"
    }, context)).not.toThrow();
  });
});
