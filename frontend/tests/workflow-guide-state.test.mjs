import test from "node:test";
import assert from "node:assert/strict";

import {
  buildWorkflowTargets,
  resolveWorkflowStep,
} from "../src/views/guide/workflowGuideState.js";

test("resolveWorkflowStep returns upload when there is no project", () => {
  assert.equal(resolveWorkflowStep({ latestProject: null }), "upload");
});

test("resolveWorkflowStep keeps upload active during file upload", () => {
  assert.equal(
    resolveWorkflowStep({
      latestProject: { project_id: "proj_1", status: "created" },
      uploadPhase: "uploading",
    }),
    "upload",
  );
});

test("resolveWorkflowStep returns seed during processing", () => {
  assert.equal(
    resolveWorkflowStep({
      latestProject: { project_id: "proj_1", status: "created" },
      uploadPhase: "processing",
      taskStatus: "processing",
    }),
    "seed",
  );
});

test("resolveWorkflowStep returns archive after ontology is ready", () => {
  assert.equal(
    resolveWorkflowStep({
      latestProject: { project_id: "proj_1", status: "ontology_generated" },
    }),
    "archive",
  );
});

test("resolveWorkflowStep returns worldline after graph is ready", () => {
  assert.equal(
    resolveWorkflowStep({
      latestProject: { project_id: "proj_1", status: "graph_completed", graph_id: "graph_1" },
    }),
    "worldline",
  );
});

test("buildWorkflowTargets returns all sidebar navigation targets", () => {
  assert.deepEqual(buildWorkflowTargets(), {
    upload: { path: "/", hash: "#seed-upload" },
    seed: { path: "/", hash: "#seed-analysis" },
    archive: { path: "/archive-library" },
    worldline: { path: "/worldline" },
  });
});
