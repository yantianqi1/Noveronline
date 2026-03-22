import test from "node:test";
import assert from "node:assert/strict";

import { buildProjectDeletePath, getTask } from "../src/api/project.js";

test("buildProjectDeletePath returns the delete endpoint for a project", () => {
  assert.equal(buildProjectDeletePath("proj_demo"), "/api/project/proj_demo");
});

test("getTask requests the task endpoint without using cache", async () => {
  const calls = [];
  const originalFetch = globalThis.fetch;
  globalThis.fetch = async (url, options = {}) => {
    calls.push({ url, options });
    return {
      status: 200,
      async json() {
        return { success: true, data: { task_id: "task_demo" } };
      },
    };
  };

  try {
    await getTask("task_demo");
  } finally {
    globalThis.fetch = originalFetch;
  }

  assert.equal(calls.length, 1);
  assert.match(String(calls[0].url), /\/api\/project\/task\/task_demo$/);
  assert.equal(calls[0].options.method, "GET");
  assert.equal(calls[0].options.cache, "no-store");
});
