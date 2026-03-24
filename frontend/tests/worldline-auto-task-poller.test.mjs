import test from "node:test";
import assert from "node:assert/strict";

import { createWorldlineAutoTaskPoller } from "../src/views/worldline/worldlineAutoTaskPoller.js";

test("worldline auto task poller keeps polling until the task completes", async () => {
  let attempts = 0;
  const sleepCalls = [];
  const snapshots = [];
  const pollTask = createWorldlineAutoTaskPoller({
    getTask: async () => {
      attempts += 1;
      if (attempts < 3) {
        return {
          data: {
            status: "processing",
            progress: 40,
            message: "世界线自动演化中",
          },
        };
      }
      return {
        data: {
          status: "completed",
          progress: 100,
          message: "任务完成",
          result: { stop_reason: "goal_reached" },
        },
      };
    },
    sleep: async (ms) => {
      sleepCalls.push(ms);
    },
  });

  const task = await pollTask("task_worldline_demo", (snapshot) => {
    snapshots.push(snapshot.status);
  });

  assert.equal(task.status, "completed");
  assert.equal(task.result.stop_reason, "goal_reached");
  assert.equal(attempts, 3);
  assert.equal(sleepCalls.length, 2);
  assert.deepEqual(snapshots, ["processing", "processing", "completed"]);
});

test("worldline auto task poller throws task error when the task fails", async () => {
  const pollTask = createWorldlineAutoTaskPoller({
    getTask: async () => ({
      data: {
        status: "failed",
        progress: 100,
        error: "worldline auto evolve failed",
      },
    }),
    sleep: async () => {},
  });

  await assert.rejects(
    () => pollTask("task_worldline_demo"),
    /worldline auto evolve failed/,
  );
});
