import test from "node:test";
import assert from "node:assert/strict";

import { createGraphBuildTaskPoller } from "../src/views/story-graph/graphBuildTaskPoller.js";

test("graph build poller keeps polling until the task completes", async () => {
  let attempts = 0;
  const progressMessages = [];
  const sleepCalls = [];
  const pollTask = createGraphBuildTaskPoller({
    getTask: async () => {
      attempts += 1;
      if (attempts < 35) {
        return {
          data: {
            status: "processing",
            progress: 45,
            message: "正在装配节点、边和证据...",
          },
        };
      }
      return {
        data: {
          status: "completed",
          progress: 100,
          message: "任务完成",
          result: { graph_id: "local_graph_demo" },
        },
      };
    },
    sleep: async (ms) => {
      sleepCalls.push(ms);
    },
  });

  const task = await pollTask("task-demo", (snapshot) => {
    progressMessages.push(snapshot.message);
  });

  assert.equal(task.status, "completed");
  assert.equal(task.result.graph_id, "local_graph_demo");
  assert.equal(attempts, 35);
  assert.equal(sleepCalls.length, 34);
  assert.equal(progressMessages.at(-1), "任务完成");
});

test("graph build poller throws task error when the task fails", async () => {
  const pollTask = createGraphBuildTaskPoller({
    getTask: async () => ({
      data: {
        status: "failed",
        progress: 45,
        message: "任务失败",
        error: "graph build failed",
      },
    }),
    sleep: async () => {},
  });

  await assert.rejects(
    () => pollTask("task-demo"),
    /graph build failed/,
  );
});
