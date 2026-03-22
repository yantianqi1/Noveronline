import test from "node:test";
import assert from "node:assert/strict";

import {
  buildSeedProjectOptions,
  resolveSeedProjectId,
  resolveSeedProjectSelection,
} from "../src/views/overview/seedProjectId.js";

test("resolveSeedProjectId prefers an explicit project id string", () => {
  assert.equal(
    resolveSeedProjectId("proj_manual", "proj_fallback"),
    "proj_manual",
  );
});

test("resolveSeedProjectId ignores click event objects and falls back to the current input", () => {
  assert.equal(
    resolveSeedProjectId({ type: "click", isTrusted: true }, "proj_current"),
    "proj_current",
  );
});

test("resolveSeedProjectId returns undefined when no usable project id exists", () => {
  assert.equal(resolveSeedProjectId("", ""), undefined);
  assert.equal(resolveSeedProjectId(undefined, "   "), undefined);
});

test("buildSeedProjectOptions maps projects into selectable options", () => {
  assert.deepEqual(
    buildSeedProjectOptions([
      { project_id: "proj_a", name: "第一卷", status: "seed_completed" },
      { project_id: "proj_b", name: "第二卷", status: "seed_processing" },
    ]),
    [
      { value: "proj_a", label: "第一卷 · proj_a" },
      { value: "proj_b", label: "第二卷 · proj_b" },
    ],
  );
});

test("resolveSeedProjectSelection keeps the current project when it still exists", () => {
  assert.equal(
    resolveSeedProjectSelection(
      [
        { project_id: "proj_a", name: "第一卷" },
        { project_id: "proj_b", name: "第二卷" },
      ],
      "proj_b",
    ),
    "proj_b",
  );
});

test("resolveSeedProjectSelection falls back to the first available project", () => {
  assert.equal(
    resolveSeedProjectSelection(
      [
        { project_id: "proj_a", name: "第一卷" },
        { project_id: "proj_b", name: "第二卷" },
      ],
      "proj_missing",
    ),
    "proj_a",
  );
  assert.equal(resolveSeedProjectSelection([], "proj_missing"), "");
});
