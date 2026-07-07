import { describe, expect, it } from "vitest";

import { assertToolAllowed, ToolPermissionDenied } from "./permissions.js";
import type { RuntimeContext } from "../contracts/writer-run.js";

const context: RuntimeContext = {
  tenant_id: "ten_1",
  project_id: "proj_1",
  run_id: "run_1",
  trace_id: "trace_1",
  requested_by: "usr_1",
  permissions: {
    tools: ["query_assets", "save_draft_revision"],
    can_write_draft: true
  }
};

describe("assertToolAllowed", () => {
  it("rejects tools outside the run allowlist", () => {
    expect(() => assertToolAllowed("manage_world_rule", {}, context)).toThrow(ToolPermissionDenied);
  });

  it("rejects mismatched tenant context", () => {
    expect(() =>
      assertToolAllowed("query_assets", { tenant_id: "ten_2" }, context)
    ).toThrow("tenant_id");
  });
});

describe("Phase 2 tool permissions", () => {
  it("allows worldline path reads when the run allowlist includes them", () => {
    assertToolAllowed(
      "query_worldline_paths",
      { tenant_id: "ten_1", project_id: "proj_1", run_id: "run_1" },
      {
        ...context,
        permissions: {
          ...context.permissions,
          tools: [...context.permissions.tools, "query_worldline_paths"]
        }
      }
    );
  });
});
