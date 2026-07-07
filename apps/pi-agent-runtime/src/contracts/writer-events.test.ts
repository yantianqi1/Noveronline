import { describe, expect, it } from "vitest";

import { mapPiEvent } from "./writer-events.js";
import type { RuntimeContext } from "./writer-run.js";

const context: RuntimeContext = {
  tenant_id: "ten_1",
  project_id: "proj_1",
  run_id: "run_1",
  trace_id: "trace_1",
  requested_by: "usr_1",
  permissions: { tools: ["query_assets"], can_write_draft: false }
};

describe("mapPiEvent", () => {
  it("maps Pi tool events to writer workflow events with context", () => {
    const mapped = mapPiEvent(
      {
        type: "tool_execution_start",
        toolCall: { toolName: "query_assets" },
        args: { query: "rain" }
      } as any,
      context
    );

    expect(mapped).toEqual({
      type: "writer.tool.started",
      tenant_id: "ten_1",
      project_id: "proj_1",
      run_id: "run_1",
      payload: {
        tool_name: "query_assets",
        args: { query: "rain" }
      }
    });
  });
});
