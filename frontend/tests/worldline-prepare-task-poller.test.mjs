import test from "node:test";
import assert from "node:assert/strict";

import { createWorldlinePrepareTaskPoller } from "../src/views/worldline/worldlinePrepareTaskPoller.js";

test("worldline prepare task poller keeps polling until prepare completes", async () => {
  let attempts = 0;
  const sleepCalls = [];
  const snapshots = [];
  const pollPrepareTask = createWorldlinePrepareTaskPoller({
    getTask: async () => {
      attempts += 1;
      if (attempts < 120) {
        return {
          data: {
            status: "processing",
            progress: 55,
            message: "世界线 prepare：正在整备 agent",
          },
        };
      }
      return {
        data: {
          status: "completed",
          progress: 100,
          message: "世界线 prepare 已完成",
        },
      };
    },
    getPreparedSession: async () => ({
      data: {
        status: attempts < 120 ? "preparing" : "ready",
        can_start: attempts >= 120,
      },
    }),
    sleep: async (ms) => {
      sleepCalls.push(ms);
    },
  });

  const snapshot = await pollPrepareTask("task_prepare_demo", "prep_demo", (value) => {
    snapshots.push(value.status);
  });

  assert.equal(snapshot.status, "ready");
  assert.equal(snapshot.can_start, true);
  assert.equal(snapshot.task_progress, 100);
  assert.equal(snapshot.task_message, "世界线 prepare 已完成");
  assert.equal(attempts, 120);
  assert.equal(sleepCalls.length, 119);
  assert.equal(snapshots.at(0), "preparing");
  assert.equal(snapshots.at(-1), "ready");
});

test("worldline prepare task poller throws task error when prepare fails", async () => {
  const pollPrepareTask = createWorldlinePrepareTaskPoller({
    getTask: async () => ({
      data: {
        status: "failed",
        progress: 100,
        error: "worldline prepare failed",
      },
    }),
    getPreparedSession: async () => ({
      data: {
        status: "failed",
        can_start: false,
      },
    }),
    sleep: async () => {},
  });

  await assert.rejects(
    () => pollPrepareTask("task_prepare_demo", "prep_demo"),
    /worldline prepare failed/,
  );
});
