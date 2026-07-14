import { describe, expect, it } from "vitest";

import { analysisRuntimeContextFromInput } from "../contracts/analysis-run.js";
import {
  AnalysisToolPermissionDenied,
  assertAnalysisToolAllowed
} from "./analysis-permissions.js";

describe("analysis tool permissions", () => {
  const context = analysisRuntimeContextFromInput({
    tenant_id: "11111111-1111-1111-1111-111111111111",
    project_id: "22222222-2222-2222-2222-222222222222",
    run_id: "33333333-3333-3333-3333-333333333333",
    trace_id: "trace-1",
    requested_by: "44444444-4444-4444-4444-444444444444",
    mode: "full",
    instruction: "analyze",
    hints: {},
    options: { module_key: "analysis_worker" }
  });

  it("allows listed workspace tools with safe paths", () => {
    expect(() =>
      assertAnalysisToolAllowed(
        "write_workspace_file",
        { path: "20-notes/sequential/1.md", content: "note" },
        context
      )
    ).not.toThrow();
  });

  it("rejects path escape and unknown tools", () => {
    expect(() =>
      assertAnalysisToolAllowed(
        "write_workspace_file",
        { path: "../secret.txt", content: "x" },
        context
      )
    ).toThrow(AnalysisToolPermissionDenied);

    expect(() =>
      assertAnalysisToolAllowed("delete_project", {}, context)
    ).toThrow(AnalysisToolPermissionDenied);
  });

  it("rejects candidate writes when permission disabled", () => {
    const readOnly = {
      ...context,
      permissions: {
        ...context.permissions,
        can_write_candidates: false,
        tools: context.permissions.tools.filter((tool) => tool !== "save_analysis_candidates")
      }
    };
    expect(() =>
      assertAnalysisToolAllowed("save_analysis_candidates", { candidates: [] }, readOnly)
    ).toThrow(AnalysisToolPermissionDenied);
  });
});
