import { describe, expect, it } from "vitest";

import { mapPiAnalysisEvent } from "./analysis-events.js";
import { analysisRuntimeContextFromInput } from "./analysis-run.js";

describe("mapPiAnalysisEvent", () => {
  const context = analysisRuntimeContextFromInput({
    tenant_id: "11111111-1111-1111-1111-111111111111",
    project_id: "22222222-2222-2222-2222-222222222222",
    run_id: "33333333-3333-3333-3333-333333333333",
    trace_id: "trace-1",
    requested_by: "44444444-4444-4444-4444-444444444444",
    mode: "full",
    instruction: "analyze",
    hints: {},
    options: { module_key: "analysis_planner" }
  });

  it("maps tool completion without private prompt/body fields", () => {
    const event = mapPiAnalysisEvent(
      {
        type: "tool_execution_end",
        toolName: "write_workspace_file",
        result: {
          details: {
            path: "20-notes/sequential/1.md",
            content: "full note body",
            api_key: "sk-secret",
            prompt: "hidden"
          }
        },
        isError: false
      } as any,
      context
    );

    expect(event?.type).toBe("analysis.tool.completed");
    expect(event?.payload.tool_name).toBe("write_workspace_file");
    const result = event?.payload.result as Record<string, unknown>;
    expect(result.path).toBe("20-notes/sequential/1.md");
    expect(result.content).toBeUndefined();
    expect(result.api_key).toBeUndefined();
    expect(result.prompt).toBeUndefined();
  });

  it("maps agent lifecycle events", () => {
    expect(mapPiAnalysisEvent({ type: "agent_start" } as any, context)?.type).toBe(
      "analysis.run.started"
    );
    expect(mapPiAnalysisEvent({ type: "agent_end" } as any, context)?.type).toBe(
      "analysis.run.completed"
    );
  });
});
