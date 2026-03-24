import test from "node:test";
import assert from "node:assert/strict";

import {
  buildAutoEvolvePayload,
  createInitialAutoTaskMap,
  mergeAutoTaskSnapshot,
} from "../src/views/worldline/worldlineAutoEvolutionState.js";

test("buildAutoEvolvePayload returns null for manual mode", () => {
  assert.equal(
    buildAutoEvolvePayload({
      createMode: "manual",
      goalText: "主角登基",
      maxSteps: 6,
    }),
    null,
  );
});

test("buildAutoEvolvePayload trims goal text and drops legacy branch selection input", () => {
  assert.deepEqual(
    buildAutoEvolvePayload({
      createMode: "continuous",
      selectedAutoBranchIds: ["branch_2", "branch_1"],
      goalText: "  主角公开真相  ",
      maxSteps: 8,
    }),
    {
      mode: "continuous",
      goal_text: "主角公开真相",
      max_steps: 8,
    },
  );
});

test("buildAutoEvolvePayload makes first-round mode explicit and keeps continuous max steps unbounded", () => {
  assert.deepEqual(
    buildAutoEvolvePayload({
      createMode: "first_round",
      goalText: "不会生效",
      maxSteps: 90,
    }),
    {
      mode: "first_round",
      goal_text: "",
      max_steps: 1,
    },
  );

  assert.equal(
    buildAutoEvolvePayload({
      createMode: "continuous",
      goalText: "",
      maxSteps: 90,
    }).max_steps,
    90,
  );
});

test("createInitialAutoTaskMap seeds a single main-world placeholder", () => {
  assert.deepEqual(
    createInitialAutoTaskMap([
      { branch_id: "branch_1", title: "世界线 1" },
      { branch_id: "branch_2", title: "世界线 2" },
    ]),
    {
      main: { branch_id: "main", branch_title: "当前世界", task_id: "", status: "idle" },
    },
  );
});

test("mergeAutoTaskSnapshot updates task state by branch id", () => {
  const current = {
    branch_1: { branch_id: "branch_1", branch_title: "世界线 1", task_id: "", status: "idle" },
  };

  assert.deepEqual(
    mergeAutoTaskSnapshot(current, {
      branch_id: "branch_1",
      task_id: "task_demo",
      status: "processing",
      progress: 45,
      message: "自动演化中",
    }),
    {
      branch_1: {
        branch_id: "branch_1",
        branch_title: "世界线 1",
        task_id: "task_demo",
        status: "processing",
        progress: 45,
        message: "自动演化中",
      },
    },
  );
});
