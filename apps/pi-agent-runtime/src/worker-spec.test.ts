import { describe, expect, it } from "vitest";

import {
  PI_WRITER_WORKFLOW_NAME,
  WRITER_TASK_QUEUE,
  piWriterWorkerSpec,
  validateWriterWorkflowPayload
} from "./worker-spec.js";

describe("piWriterWorkerSpec", () => {
  it("exposes the Temporal task queue, workflow, and activity contract", () => {
    expect(piWriterWorkerSpec()).toEqual({
      taskQueue: WRITER_TASK_QUEUE,
      workflows: [PI_WRITER_WORKFLOW_NAME],
      activities: ["runPiWriterRunActivity"]
    });
  });
});

describe("validateWriterWorkflowPayload", () => {
  it("requires tenant, project, run, actor, mode, and instruction context", () => {
    const payload = validateWriterWorkflowPayload({
      tenant_id: "ten_1",
      project_id: "proj_1",
      run_id: "run_1",
      trace_id: "trace_1",
      requested_by: "usr_1",
      mode: "draft",
      instruction: "写下一场雨夜谈判",
      options: { module_key: "writer_composer" }
    });

    expect(payload.tenant_id).toBe("ten_1");
    expect(payload.project_id).toBe("proj_1");
    expect(payload.run_id).toBe("run_1");
    expect(payload.trace_id).toBe("trace_1");
    expect(payload.options.module_key).toBe("writer_composer");
  });

  it("fails explicitly when runtime context is incomplete", () => {
    expect(() =>
      validateWriterWorkflowPayload({
        tenant_id: "ten_1",
        project_id: "proj_1",
        run_id: "",
        trace_id: "trace_1",
        requested_by: "usr_1",
        mode: "draft",
        instruction: "写下一场雨夜谈判",
        options: { module_key: "writer_composer" }
      })
    ).toThrow("run_id is required");
  });

  it("fails explicitly when trace context is missing", () => {
    expect(() =>
      validateWriterWorkflowPayload({
        tenant_id: "ten_1",
        project_id: "proj_1",
        run_id: "run_1",
        trace_id: "",
        requested_by: "usr_1",
        mode: "draft",
        instruction: "写下一场雨夜谈判",
        options: { module_key: "writer_composer" }
      })
    ).toThrow("trace_id is required");
  });
});
