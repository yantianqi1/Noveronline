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

  it("maps Character Console target chapter and scene options into the runtime draft target", () => {
    const payload = validateWriterWorkflowPayload({
      tenant_id: "ten_1",
      project_id: "proj_1",
      run_id: "run_1",
      trace_id: "trace_1",
      requested_by: "usr_1",
      mode: "draft",
      instruction: "Rewrite the saved interaction as a chapter scene.",
      options: {
        module_key: "writer_composer",
        source: "character_console",
        character_interaction_id: "interaction-1",
        target_chapter_id: "chapter-1",
        target_scene_id: "scene-1"
      }
    });

    expect(payload.chapter_id).toBe("chapter-1");
    expect(payload.scene_id).toBe("scene-1");
  });

  it("maps explicit asset, graph, and worldline references from admission options", () => {
    const payload = validateWriterWorkflowPayload({
      tenant_id: "ten_1", project_id: "proj_1", run_id: "run_1", trace_id: "trace_1",
      requested_by: "usr_1", mode: "draft", instruction: "Use selected references.",
      options: {
        module_key: "writer_composer",
        selected_asset_ids: ["asset-1"],
        graph_node_ids: ["node-1"],
        worldline_path_ids: ["path-1"]
      }
    });

    expect(payload.selected_asset_ids).toEqual(["asset-1"]);
    expect(payload.graph_node_ids).toEqual(["node-1"]);
    expect(payload.worldline_path_ids).toEqual(["path-1"]);
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
