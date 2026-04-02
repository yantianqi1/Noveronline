import test from "node:test";
import assert from "node:assert/strict";

import {
  getPreparedWorldlineAgents,
  getPreparedWorldlineSession,
  getWorldlineAgentDetail,
  getWorldlineAgentMemory,
  getWorldlineAgentMemoryContext,
  prepareWorldlineSession,
  startPreparedWorldlineSession,
  startWorldlineAutoEvolve,
} from "../src/api/worldline.js";

test("startWorldlineAutoEvolve posts to the session auto evolve endpoint", async () => {
  const calls = [];
  const originalFetch = globalThis.fetch;
  globalThis.fetch = async (url, options = {}) => {
    calls.push({ url, options });
    return {
      status: 202,
      async json() {
        return { success: true, data: { tasks: [] } };
      },
    };
  };

  try {
    await startWorldlineAutoEvolve({
      session_id: "ws_demo",
      mode: "continuous",
      branch_ids: ["branch_1"],
      goal_text: "主角公开真相",
      max_steps: 6,
    });
  } finally {
    globalThis.fetch = originalFetch;
  }

  assert.equal(calls.length, 1);
  assert.match(String(calls[0].url), /\/api\/worldline\/session\/ws_demo\/auto-evolve$/);
  assert.equal(calls[0].options.method, "POST");
  assert.match(String(calls[0].options.body), /"mode":"continuous"/);
  assert.doesNotMatch(String(calls[0].options.body), /"branch_ids":/);
});

test("worldline memory APIs build the expected query paths", async () => {
  const calls = [];
  const originalFetch = globalThis.fetch;
  globalThis.fetch = async (url, options = {}) => {
    calls.push({ url, options });
    return {
      status: 200,
      async json() {
        return { success: true, data: {} };
      },
    };
  };

  try {
    await getWorldlineAgentMemory("ws_demo", { agent_id: "agent_1", limit: 8 });
    await getWorldlineAgentMemoryContext("ws_demo", {
      agent_id: "agent_1",
      message: "现在该怎么办？",
      limit: 5,
    });
  } finally {
    globalThis.fetch = originalFetch;
  }

  assert.equal(calls.length, 2);
  assert.match(
    String(calls[0].url),
    /\/api\/worldline\/session\/ws_demo\/agent-memory\?agent_id=agent_1&limit=8$/,
  );
  assert.match(
    String(calls[1].url),
    /\/api\/worldline\/session\/ws_demo\/agent-memory-context\?agent_id=agent_1&limit=5&message=/,
  );
  assert.equal(calls[0].options.method, "GET");
  assert.equal(calls[1].options.method, "GET");
});

test("worldline prepare APIs build the expected request paths", async () => {
  const calls = [];
  const originalFetch = globalThis.fetch;
  globalThis.fetch = async (url, options = {}) => {
    calls.push({ url, options });
    return {
      status: 200,
      async json() {
        return { success: true, data: {} };
      },
    };
  };

  try {
    await prepareWorldlineSession({ archive_ids: ["arc_1"], variables: ["密信提前泄露"] });
    await getPreparedWorldlineSession("prep_demo");
    await getPreparedWorldlineAgents("prep_demo");
    await startPreparedWorldlineSession("prep_demo", { project_id: "proj_demo" });
    await getWorldlineAgentDetail("ws_demo", "agent_1");
  } finally {
    globalThis.fetch = originalFetch;
  }

  assert.equal(calls.length, 5);
  assert.match(String(calls[0].url), /\/api\/worldline\/session\/prepare$/);
  assert.equal(calls[0].options.method, "POST");
  assert.match(String(calls[1].url), /\/api\/worldline\/session\/prepare\/prep_demo$/);
  assert.equal(calls[1].options.method, "GET");
  assert.match(String(calls[2].url), /\/api\/worldline\/session\/prepare\/prep_demo\/agents$/);
  assert.equal(calls[2].options.method, "GET");
  assert.match(String(calls[3].url), /\/api\/worldline\/session\/prepare\/prep_demo\/start$/);
  assert.equal(calls[3].options.method, "POST");
  assert.match(String(calls[4].url), /\/api\/worldline\/session\/ws_demo\/agents\/agent_1$/);
  assert.equal(calls[4].options.method, "GET");
});
